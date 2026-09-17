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
"""
from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path
from typing import Iterable, Optional

from .engine import Entry

DEFAULT_DB_PATH = Path.home() / ".mindgalaxy" / "galaxy.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _connect(db_path: Path | str):
    """
    Open a connection to either a local SQLite file or, if TURSO_DATABASE_URL
    is set, a remote Turso (libSQL) database. Both expose the same
    sqlite3-style DB-API (connect / execute / commit / cursor.lastrowid), so
    the rest of Storage doesn't need to know which one it's talking to.
    """
    turso_url = os.environ.get("TURSO_DATABASE_URL")
    if turso_url:
        import libsql

        return libsql.connect(turso_url, auth_token=os.environ.get("TURSO_AUTH_TOKEN"))

    import sqlite3

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(path))


class Storage:
    """Thin wrapper around a SQLite (or Turso/libSQL) database of journal entries."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.conn = _connect(db_path)
        self.conn.execute(_SCHEMA)
        self.conn.commit()

    def add(self, text: str, created_at: Optional[_dt.datetime] = None) -> int:
        text = text.strip()
        if not text:
            raise ValueError("Cannot add an empty entry.")
        created_at = created_at or _dt.datetime.utcnow()
        cur = self.conn.execute(
            "INSERT INTO entries (text, created_at) VALUES (?, ?)",
            (text, created_at.isoformat()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def add_many(self, texts: Iterable[str], created_at: Optional[_dt.datetime] = None) -> list[int]:
        return [self.add(t, created_at) for t in texts if t and t.strip()]

    def all_entries(self) -> list[Entry]:
        rows = self.conn.execute(
            "SELECT id, text, created_at FROM entries ORDER BY created_at"
        ).fetchall()
        return [
            Entry(id=r[0], text=r[1], created_at=_dt.datetime.fromisoformat(r[2]))
            for r in rows
        ]

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0])

    def clear(self) -> None:
        self.conn.execute("DELETE FROM entries")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
