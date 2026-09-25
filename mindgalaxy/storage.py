"""
mindgalaxy.storage
===================

SQLite-backed storage for journal entries. By default this is a single
portable .db file (no server, no external database). When the
TURSO_DATABASE_URL environment variable is set, entries are stored in a
Turso (libSQL) database instead -- same schema, same SQL, just reachable
over the network -- which is what makes persistence possible on a
stateless deployment like Vercel, where the local filesystem does not
survive between invocations.

Entries can belong to a user (the hosted, multi-user site) or to nobody
(user_id NULL -- the local CLI and single-user `mindgalaxy serve`). A
Storage opened with a user_id only ever sees that user's entries.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any, Iterable, Optional

from .engine import Entry

DEFAULT_DB_PATH = Path.home() / ".mindgalaxy" / "galaxy.db"

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        pin_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        locked_until TEXT
    )""",
    # AI-judged "truly related" links between two of a user's entries.
    """CREATE TABLE IF NOT EXISTS links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        a INTEGER NOT NULL,
        b INTEGER NOT NULL,
        kind TEXT NOT NULL,
        reason TEXT NOT NULL,
        extra TEXT
    )""",
    "CREATE INDEX IF NOT EXISTS links_user ON links (user_id)",
    # Shared cache of AI answers (keyed by subject + path, never by user).
    """CREATE TABLE IF NOT EXISTS ai_cache (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    # Timestamped events used for rate limits: failed logins, sign-ups and
    # uncached AI calls.
    """CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        subject TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS events_lookup ON events (kind, subject, created_at)",
    # ---- the galaxy ecosystem (see social.py) ----
    # One row per pair of users with a status; always stored with a < b.
    """CREATE TABLE IF NOT EXISTS relations (
        a INTEGER NOT NULL,
        b INTEGER NOT NULL,
        status TEXT NOT NULL,
        since TEXT NOT NULL,
        PRIMARY KEY (a, b)
    )""",
    """CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user INTEGER NOT NULL,
        to_user INTEGER NOT NULL,
        kind TEXT NOT NULL,
        family_id INTEGER,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS requests_to ON requests (to_user, status)",
    """CREATE TABLE IF NOT EXISTS blocks (
        blocker INTEGER NOT NULL,
        blocked INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (blocker, blocked)
    )""",
    # Pairs cut apart forever by the black hole (a < b), with who was swallowed
    # and whether each side has watched it happen yet.
    """CREATE TABLE IF NOT EXISTS severed (
        a INTEGER NOT NULL,
        b INTEGER NOT NULL,
        swallowed INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        a_seen INTEGER NOT NULL DEFAULT 0,
        b_seen INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (a, b)
    )""",
    """CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reporter INTEGER NOT NULL,
        reported INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS families (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        created_by INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS family_members (
        family_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        joined_at TEXT NOT NULL,
        PRIMARY KEY (family_id, user_id)
    )""",
    """CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user INTEGER NOT NULL,
        to_user INTEGER NOT NULL,
        text TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS messages_pair ON messages (from_user, to_user, id)",
    # Each user's current public key (ECDH P-256, JWK). The private half never
    # leaves their browser.
    """CREATE TABLE IF NOT EXISTS public_keys (
        user_id INTEGER PRIMARY KEY,
        jwk TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    # View-once media: only ciphertext, deleted the moment it's opened (or
    # after MEDIA_TTL_DAYS unopened). The chat keeps a stub message.
    """CREATE TABLE IF NOT EXISTS media (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user INTEGER NOT NULL,
        to_user INTEGER NOT NULL,
        kind TEXT NOT NULL,
        mime TEXT NOT NULL,
        iv TEXT NOT NULL,
        sender_key TEXT NOT NULL,
        data BLOB NOT NULL,
        created_at TEXT NOT NULL
    )""",
]

# Columns added to `entries` after the first release; existing databases are
# migrated in place with ALTER TABLE.
_ENTRY_COLUMNS = {"user_id": "INTEGER", "analysis": "TEXT", "share_family": "INTEGER NOT NULL DEFAULT 0"}

_migrated: set[str] = set()


def _connect(db_path: Path | str):
    """
    Open a connection to either a local SQLite file or, if TURSO_DATABASE_URL
    is set, a remote Turso (libSQL) database. Both expose the same
    sqlite3-style DB-API (connect / execute / commit / cursor.lastrowid), so
    the rest of Storage doesn't need to know which one it's talking to.
    Returns the connection plus the remote URL (None for a local file).
    """
    turso_url = os.environ.get("TURSO_DATABASE_URL")
    if turso_url:
        import libsql

        return libsql.connect(turso_url, auth_token=os.environ.get("TURSO_AUTH_TOKEN", "")), turso_url

    import sqlite3

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(path)), None


def _now() -> _dt.datetime:
    return _dt.datetime.utcnow()


class Storage:
    """Thin wrapper around a SQLite (or Turso/libSQL) database of journal entries."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH, user_id: Optional[int] = None):
        self.db_path = Path(db_path)
        self.user_id = user_id
        self.conn, remote_key = _connect(db_path)
        # Schema setup is several network round trips on Turso, so do it once
        # per process there; a local file is cheap enough to check every time.
        if remote_key is None or remote_key not in _migrated:
            self._migrate()
            if remote_key:
                _migrated.add(remote_key)

    def _migrate(self) -> None:
        for stmt in _SCHEMA:
            self.conn.execute(stmt)
        have = {r[1] for r in self.conn.execute("PRAGMA table_info(entries)").fetchall()}
        for col, typ in _ENTRY_COLUMNS.items():
            if col not in have:
                self.conn.execute(f"ALTER TABLE entries ADD COLUMN {col} {typ}")
        self.conn.execute("CREATE INDEX IF NOT EXISTS entries_user ON entries (user_id)")
        self.conn.commit()

    # -- scoping ---------------------------------------------------------
    def _owner(self) -> tuple[str, tuple]:
        if self.user_id is None:
            return "user_id IS NULL", ()
        return "user_id = ?", (self.user_id,)

    # -- entries ---------------------------------------------------------
    def add(self, text: str, created_at: Optional[_dt.datetime] = None) -> int:
        text = text.strip()
        if not text:
            raise ValueError("Cannot add an empty entry.")
        created_at = created_at or _now()
        cur = self.conn.execute(
            "INSERT INTO entries (text, created_at, user_id) VALUES (?, ?, ?)",
            (text, created_at.isoformat(), self.user_id),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def add_many(self, texts: Iterable[str], created_at: Optional[_dt.datetime] = None) -> list[int]:
        return [self.add(t, created_at) for t in texts if t and t.strip()]

    def all_entries(self) -> list[Entry]:
        where, args = self._owner()
        rows = self.conn.execute(
            f"SELECT id, text, created_at FROM entries WHERE {where} ORDER BY created_at", args
        ).fetchall()
        return [
            Entry(id=r[0], text=r[1], created_at=_dt.datetime.fromisoformat(r[2]))
            for r in rows
        ]

    def get_entry(self, entry_id: int) -> Optional[dict[str, Any]]:
        where, args = self._owner()
        row = self.conn.execute(
            f"SELECT id, text, created_at, analysis FROM entries WHERE id = ? AND {where}",
            (entry_id, *args),
        ).fetchone()
        if not row:
            return None
        return {"id": row[0], "text": row[1], "created_at": row[2],
                "analysis": json.loads(row[3]) if row[3] else None}

    def analyses(self) -> dict[int, dict[str, Any]]:
        where, args = self._owner()
        rows = self.conn.execute(
            f"SELECT id, analysis FROM entries WHERE {where} AND analysis IS NOT NULL", args
        ).fetchall()
        return {r[0]: json.loads(r[1]) for r in rows}

    def family_shared_ids(self) -> set[int]:
        where, args = self._owner()
        return {r[0] for r in self.conn.execute(
            f"SELECT id FROM entries WHERE {where} AND share_family = 1", args).fetchall()}

    def set_analysis(self, entry_id: int, analysis: dict[str, Any]) -> None:
        where, args = self._owner()
        self.conn.execute(
            f"UPDATE entries SET analysis = ? WHERE id = ? AND {where}",
            (json.dumps(analysis), entry_id, *args),
        )
        self.conn.commit()

    def count(self) -> int:
        where, args = self._owner()
        return int(self.conn.execute(f"SELECT COUNT(*) FROM entries WHERE {where}", args).fetchone()[0])

    def clear(self) -> None:
        where, args = self._owner()
        self.conn.execute(f"DELETE FROM entries WHERE {where}", args)
        self.conn.execute(f"DELETE FROM links WHERE {where}", args)
        self.conn.commit()

    # -- links -----------------------------------------------------------
    def add_link(self, a: int, b: int, kind: str, reason: str, extra: Optional[dict] = None) -> bool:
        """Store a link unless the same one exists already; True if added."""
        a, b = min(a, b), max(a, b)
        where, args = self._owner()
        if self.conn.execute(
            f"SELECT 1 FROM links WHERE a = ? AND b = ? AND kind = ? AND {where}", (a, b, kind, *args)
        ).fetchone():
            return False
        self.conn.execute(
            "INSERT INTO links (user_id, a, b, kind, reason, extra) VALUES (?, ?, ?, ?, ?, ?)",
            (self.user_id, a, b, kind, reason, json.dumps(extra) if extra else None),
        )
        self.conn.commit()
        return True

    def links(self) -> list[dict[str, Any]]:
        where, args = self._owner()
        rows = self.conn.execute(
            f"SELECT a, b, kind, reason, extra FROM links WHERE {where}", args
        ).fetchall()
        return [{"a": r[0], "b": r[1], "kind": r[2], "reason": r[3],
                 "extra": json.loads(r[4]) if r[4] else None} for r in rows]

    # -- users -----------------------------------------------------------
    def create_user(self, username: str, pin_hash: str) -> Optional[int]:
        """Create a user; None if the username is taken (even by a sign-up
        that raced this one -- the UNIQUE constraint is the real check)."""
        try:
            cur = self.conn.execute(
                "INSERT INTO users (username, pin_hash, created_at) VALUES (?, ?, ?)",
                (username, pin_hash, _now().isoformat()),
            )
        except Exception as e:  # sqlite3.IntegrityError locally; libsql raises its own type
            if "UNIQUE" in str(e).upper():
                self.conn.rollback()
                return None
            raise
        self.conn.commit()
        return int(cur.lastrowid)

    def get_user(self, username: str) -> Optional[dict[str, Any]]:
        row = self.conn.execute(
            "SELECT id, username, pin_hash, failed_attempts, locked_until FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if not row:
            return None
        return {"id": row[0], "username": row[1], "pin_hash": row[2], "failed_attempts": row[3],
                "locked_until": _dt.datetime.fromisoformat(row[4]) if row[4] else None}

    def get_user_by_id(self, user_id: int) -> Optional[dict[str, Any]]:
        row = self.conn.execute("SELECT id, username FROM users WHERE id = ?", (user_id,)).fetchone()
        return {"id": row[0], "username": row[1]} if row else None

    def record_login_failure(self, user_id: int, max_attempts: int, lock_for: _dt.timedelta) -> bool:
        """Count a wrong passkey; lock the account once max_attempts is reached.
        Returns True if the account is now locked."""
        row = self.conn.execute("SELECT failed_attempts FROM users WHERE id = ?", (user_id,)).fetchone()
        attempts = int(row[0]) + 1
        if attempts >= max_attempts:
            self.conn.execute(
                "UPDATE users SET failed_attempts = 0, locked_until = ? WHERE id = ?",
                ((_now() + lock_for).isoformat(), user_id),
            )
        else:
            self.conn.execute("UPDATE users SET failed_attempts = ? WHERE id = ?", (attempts, user_id))
        self.conn.commit()
        return attempts >= max_attempts

    def reset_login_failures(self, user_id: int) -> None:
        self.conn.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?", (user_id,))
        self.conn.commit()

    # -- rate-limit events ----------------------------------------------
    def log_event(self, kind: str, subject: str) -> None:
        self.conn.execute(
            "INSERT INTO events (kind, subject, created_at) VALUES (?, ?, ?)",
            (kind, subject, _now().isoformat()),
        )
        self.conn.commit()

    def count_events(self, kind: str, subject: str, since: _dt.datetime) -> int:
        return int(self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE kind = ? AND subject = ? AND created_at >= ?",
            (kind, subject, since.isoformat()),
        ).fetchone()[0])

    # -- AI cache --------------------------------------------------------
    def cache_get(self, key: str) -> Optional[Any]:
        row = self.conn.execute("SELECT value FROM ai_cache WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def cache_put(self, key: str, value: Any) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO ai_cache (key, value, created_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), _now().isoformat()),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
