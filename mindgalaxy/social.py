"""
mindgalaxy.social
==================

The galaxy ecosystem: every user's galaxy sits in a shared universe, and
galaxies can be strung together.

Statuses between two users (both must accept every change):

    (none) --friend request--> friend --enemy request--> enemy --peace--> friend
                               friend --partner request--> partner --leave--> friend
    family: a group of up to 9 galaxies; joining and leaving both need
            another member to accept.

* friends, partners and family members can chat;
* a life partner can read all of the other's thoughts;
* family members see only thoughts their owner switched to "share with
  family", and never ones the AI rated 18+ or violent;
* enemies can report each other (once a day). When one side has been
  reported REPORTS_TO_SWALLOW times the black hole swallows it: the pair is
  severed forever -- their chat is deleted, sharing between them ends, and
  neither can ever send the other a request again.
* anyone can block anyone, one-sided and instantly: it ends the relationship
  and hides chat, requests and shared thoughts between the two (nothing is
  deleted), so nobody can be stuck sharing with someone against their will.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from .storage import Storage

REPORTS_TO_SWALLOW = 5
FAMILY_MAX = 9
REQUESTS_PER_DAY = 30
MESSAGES_PER_HOUR = 120
MAX_MESSAGE_CHARS = 1000

# kind -> (status required now, status after acceptance)
TRANSITIONS = {
    "friend": (None, "friend"),
    "enemy": ("friend", "enemy"),
    "peace": ("enemy", "friend"),
    "partner": ("friend", "partner"),
    "unpartner": ("partner", "friend"),
}
FAMILY_KINDS = ("family_invite", "family_leave")
CHAT_STATUSES = ("friend", "partner")


class SocialError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _now() -> str:
    return _dt.datetime.utcnow().isoformat()


def _pair(x: int, y: int) -> tuple[int, int]:
    return (x, y) if x < y else (y, x)


class Social:
    """All ecosystem rules, over an open Storage connection."""

    def __init__(self, store: Storage):
        self.store = store
        self.db = store.conn

    def _one(self, sql: str, args: tuple = ()) -> Optional[tuple]:
        return self.db.execute(sql, args).fetchone()

    def _all(self, sql: str, args: tuple = ()) -> list[tuple]:
        return self.db.execute(sql, args).fetchall()

    # -- lookups ---------------------------------------------------------
    def user_id(self, username: str) -> int:
        row = self._one("SELECT id FROM users WHERE username = ?", ((username or "").strip().lower(),))
        if not row:
            raise SocialError("No galaxy with that name.", 404)
        return int(row[0])

    def username(self, uid: int) -> str:
        row = self._one("SELECT username FROM users WHERE id = ?", (uid,))
        return row[0] if row else "?"

    def status(self, x: int, y: int) -> Optional[str]:
        row = self._one("SELECT status FROM relations WHERE a = ? AND b = ?", _pair(x, y))
        return row[0] if row else None

    def blocked_between(self, x: int, y: int) -> bool:
        return bool(self._one("SELECT 1 FROM blocks WHERE (blocker = ? AND blocked = ?) OR (blocker = ? AND blocked = ?)",
                              (x, y, y, x)))

    def severed(self, x: int, y: int) -> bool:
        return bool(self._one("SELECT 1 FROM severed WHERE a = ? AND b = ?", _pair(x, y)))

    def families_of(self, uid: int) -> list[int]:
        return [r[0] for r in self._all("SELECT family_id FROM family_members WHERE user_id = ?", (uid,))]

    def family_members(self, family_id: int) -> list[int]:
        return [r[0] for r in self._all("SELECT user_id FROM family_members WHERE family_id = ?", (family_id,))]

    def share_family(self, x: int, y: int) -> bool:
        return bool(set(self.families_of(x)) & set(self.families_of(y)))

    def _usable_pair(self, me: int, other: int) -> None:
        if me == other:
            raise SocialError("That's your own galaxy.")
        if self.severed(me, other):
            raise SocialError("The black hole swallowed the string between you. You can never connect again.", 403)
        if self.blocked_between(me, other):
            raise SocialError("You can't interact with this galaxy.", 403)

    def _set_status(self, x: int, y: int, status: Optional[str]) -> None:
        a, b = _pair(x, y)
        self.db.execute("DELETE FROM relations WHERE a = ? AND b = ?", (a, b))
        if status:
            self.db.execute("INSERT INTO relations (a, b, status, since) VALUES (?, ?, ?, ?)", (a, b, status, _now()))

    # -- requests --------------------------------------------------------
    def send_request(self, me: int, to_name: str, kind: str, family_id: Optional[int] = None) -> int:
        other = self.user_id(to_name)
        self._usable_pair(me, other)
        since = (_dt.datetime.utcnow() - _dt.timedelta(days=1)).isoformat()
        if int(self._one("SELECT COUNT(*) FROM requests WHERE from_user = ? AND created_at >= ?", (me, since))[0]) \
                >= REQUESTS_PER_DAY:
            raise SocialError("You've sent a lot of requests today. Try again tomorrow.", 429)
        if kind in TRANSITIONS:
            need, _ = TRANSITIONS[kind]
            have = self.status(me, other)
            if have != need:
                raise SocialError(_why_not(kind, have), 409)
            family_id = None
        elif kind == "family_invite":
            if family_id not in self.families_of(me):
                raise SocialError("You can only invite people into a family you belong to.", 403)
            if self.status(me, other) not in ("friend", "partner"):
                raise SocialError("Only friends can be invited into a family.", 409)
            if other in self.family_members(family_id):
                raise SocialError("They're already in this family.", 409)
            if len(self.family_members(family_id)) >= FAMILY_MAX:
                raise SocialError(f"A family can have at most {FAMILY_MAX} galaxies.", 409)
        elif kind == "family_leave":
            members = self.family_members(family_id) if family_id else []
            if me not in members or other not in members:
                raise SocialError("Both of you must be in that family.", 409)
        else:
            raise SocialError("Unknown request type.")
        if self._one("SELECT 1 FROM requests WHERE status = 'pending' AND kind = ? AND COALESCE(family_id, 0) = ? "
                     "AND ((from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?))",
                     (kind, family_id or 0, me, other, other, me)):
            raise SocialError("There's already a pending request for that between you.", 409)
        cur = self.db.execute(
            "INSERT INTO requests (from_user, to_user, kind, family_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (me, other, kind, family_id, _now()))
        self.db.commit()
        return int(cur.lastrowid)

    def respond(self, me: int, request_id: int, accept: bool) -> dict[str, Any]:
        row = self._one("SELECT from_user, to_user, kind, family_id, status FROM requests WHERE id = ?", (request_id,))
        if not row or row[1] != me:
            raise SocialError("No such request.", 404)
        sender, _, kind, family_id, state = row
        if state != "pending":
            raise SocialError("That request was already answered.", 409)
        if accept:
            self._usable_pair(me, sender)
            self._apply(sender, me, kind, family_id)
        self.db.execute("UPDATE requests SET status = ? WHERE id = ?", ("accepted" if accept else "declined", request_id))
        self.db.commit()
        return {"accepted": accept, "kind": kind, "status": self.status(me, sender)}

    def _apply(self, sender: int, me: int, kind: str, family_id: Optional[int]) -> None:
        if kind in TRANSITIONS:
            need, after = TRANSITIONS[kind]
            if self.status(sender, me) != need:
                raise SocialError("Things changed since that request was sent; it no longer applies.", 409)
            self._set_status(sender, me, after)
        elif kind == "family_invite":
            if family_id not in self.families_of(sender):
                raise SocialError("That family no longer includes them.", 409)
            if len(self.family_members(family_id)) >= FAMILY_MAX:
                raise SocialError(f"That family is full ({FAMILY_MAX} galaxies).", 409)
            self.db.execute("INSERT OR IGNORE INTO family_members (family_id, user_id, joined_at) VALUES (?, ?, ?)",
                            (family_id, me, _now()))
        elif kind == "family_leave":
            self._leave_family(sender, family_id)

    def _leave_family(self, uid: int, family_id: int) -> None:
        self.db.execute("DELETE FROM family_members WHERE family_id = ? AND user_id = ?", (family_id, uid))
        if not self.family_members(family_id):
            self.db.execute("DELETE FROM families WHERE id = ?", (family_id,))

    def cancel_request(self, me: int, request_id: int) -> None:
        self.db.execute("UPDATE requests SET status = 'cancelled' WHERE id = ? AND from_user = ? AND status = 'pending'",
                        (request_id, me))
        self.db.commit()

    def unfriend(self, me: int, other_name: str) -> None:
        """Friends (only) can part ways without asking; stronger bonds need
        both to agree (or a block)."""
        other = self.user_id(other_name)
        if self.status(me, other) != "friend":
            raise SocialError("Only a friendship can be ended this way.", 409)
        self._set_status(me, other, None)
        self.db.commit()

    # -- families --------------------------------------------------------
    def create_family(self, me: int, name: str) -> int:
        name = (name or "").strip()[:40]
        if not name:
            raise SocialError("Give the family a name.")
        if len(self.families_of(me)) >= 5:
            raise SocialError("You can be in at most 5 families.", 409)
        cur = self.db.execute("INSERT INTO families (name, created_by, created_at) VALUES (?, ?, ?)", (name, me, _now()))
        fid = int(cur.lastrowid)
        self.db.execute("INSERT INTO family_members (family_id, user_id, joined_at) VALUES (?, ?, ?)", (fid, me, _now()))
        self.db.commit()
        return fid

    def leave_family_alone(self, me: int, family_id: int) -> None:
        """The last member (or one with no one else left) can leave freely."""
        members = self.family_members(family_id)
        if me not in members:
            raise SocialError("You're not in that family.", 404)
        if len(members) > 1:
            raise SocialError("Ask another family member to accept your leaving.", 409)
        self._leave_family(me, family_id)
        self.db.commit()

    # -- block & the black hole ------------------------------------------
    def block(self, me: int, other_name: str) -> None:
        other = self.user_id(other_name)
        if me == other:
            raise SocialError("You can't block yourself.")
        self.db.execute("INSERT OR IGNORE INTO blocks (blocker, blocked, created_at) VALUES (?, ?, ?)", (me, other, _now()))
        self._set_status(me, other, None)
        self.db.execute("UPDATE requests SET status = 'cancelled' WHERE status = 'pending' AND "
                        "((from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?))", (me, other, other, me))
        self.db.commit()

    def unblock(self, me: int, other_name: str) -> None:
        other = self.user_id(other_name)
        self.db.execute("DELETE FROM blocks WHERE blocker = ? AND blocked = ?", (me, other))
        self.db.commit()

    def report(self, me: int, enemy_name: str) -> dict[str, Any]:
        enemy = self.user_id(enemy_name)
        self._usable_pair(me, enemy)
        if self.status(me, enemy) != "enemy":
            raise SocialError("You can only report a galaxy you're enemies with.", 409)
        since = (_dt.datetime.utcnow() - _dt.timedelta(days=1)).isoformat()
        if self._one("SELECT 1 FROM reports WHERE reporter = ? AND reported = ? AND created_at >= ?", (me, enemy, since)):
            raise SocialError("You can report this galaxy once a day.", 429)
        self.db.execute("INSERT INTO reports (reporter, reported, created_at) VALUES (?, ?, ?)", (me, enemy, _now()))
        count = int(self._one("SELECT COUNT(*) FROM reports WHERE reporter = ? AND reported = ?", (me, enemy))[0])
        swallowed = count >= REPORTS_TO_SWALLOW
        if swallowed:
            self._swallow(reporter=me, victim=enemy)
        self.db.commit()
        return {"reports": count, "needed": REPORTS_TO_SWALLOW, "swallowed": swallowed}

    def _swallow(self, reporter: int, victim: int) -> None:
        """The black hole between two enemies consumes one of them: the pair
        is severed forever and everything they shared is lost."""
        a, b = _pair(reporter, victim)
        self.db.execute("INSERT OR REPLACE INTO severed (a, b, swallowed, created_at) VALUES (?, ?, ?, ?)",
                        (a, b, victim, _now()))
        self._set_status(reporter, victim, None)
        self.db.execute("DELETE FROM messages WHERE (from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?)",
                        (a, b, b, a))
        self.db.execute("DELETE FROM media WHERE (from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?)",
                        (a, b, b, a))
        self.db.execute("DELETE FROM requests WHERE (from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?)",
                        (a, b, b, a))
        self.db.execute("DELETE FROM reports WHERE (reporter = ? AND reported = ?) OR (reporter = ? AND reported = ?)",
                        (a, b, b, a))
        # detached from each other's families for ever
        for fid in set(self.families_of(reporter)) & set(self.families_of(victim)):
            self._leave_family(victim, fid)

    def unseen_swallows(self, me: int) -> list[dict[str, Any]]:
        out = []
        for a, b, victim, at, ua, ub in self._all(
                "SELECT s.a, s.b, s.swallowed, s.created_at, ua.username, ub.username FROM severed s "
                "JOIN users ua ON ua.id = s.a JOIN users ub ON ub.id = s.b "
                "WHERE (s.a = ? AND s.a_seen = 0) OR (s.b = ? AND s.b_seen = 0)", (me, me)):
            out.append({"with": ub if me == a else ua, "swallowed": ua if victim == a else ub,
                        "you_were_swallowed": victim == me, "at": at})
        return out

    def mark_swallows_seen(self, me: int) -> None:
        self.db.execute("UPDATE severed SET a_seen = 1 WHERE a = ?", (me,))
        self.db.execute("UPDATE severed SET b_seen = 1 WHERE b = ?", (me,))
        self.db.commit()

    # -- chat ------------------------------------------------------------
    def can_chat(self, me: int, other: int) -> bool:
        if me == other or self.blocked_between(me, other) or self.severed(me, other):
            return False
        return self.status(me, other) in CHAT_STATUSES or self.share_family(me, other)

    def send_message(self, me: int, to_name: str, text: str) -> int:
        other = self.user_id(to_name)
        # control characters out: they could forge the media marker below
        text = "".join(ch for ch in (text or "") if ch in "\n\t" or ord(ch) >= 32).strip()
        if not text:
            raise SocialError("Write something first.")
        if len(text) > MAX_MESSAGE_CHARS:
            raise SocialError(f"Messages can be at most {MAX_MESSAGE_CHARS} characters.")
        if not self.can_chat(me, other):
            raise SocialError("You can only chat with friends, your partner and family.", 403)
        since = (_dt.datetime.utcnow() - _dt.timedelta(hours=1)).isoformat()
        if int(self._one("SELECT COUNT(*) FROM messages WHERE from_user = ? AND created_at >= ?", (me, since))[0]) \
                >= MESSAGES_PER_HOUR:
            raise SocialError("Slow down a little: too many messages this hour.", 429)
        cur = self.db.execute("INSERT INTO messages (from_user, to_user, text, created_at) VALUES (?, ?, ?, ?)",
                              (me, other, text, _now()))
        self.db.commit()
        return int(cur.lastrowid)

    def messages(self, me: int, other_name: str, after: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        other = self.user_id(other_name)
        if not self.can_chat(me, other):
            raise SocialError("You can only chat with friends, your partner and family.", 403)
        rows = self._all(
            "SELECT id, from_user, text, created_at FROM messages WHERE id > ? AND "
            "((from_user = ? AND to_user = ?) OR (from_user = ? AND to_user = ?)) ORDER BY id DESC LIMIT ?",
            (after, me, other, other, me, limit))
        out = []
        for r in reversed(rows):
            msg = {"id": r[0], "mine": r[1] == me, "text": r[2], "at": r[3]}
            if r[2].startswith("\x00media:"):
                _, media_id, kind = r[2][1:].split(":")
                msg["text"] = ""
                msg["media"] = {"id": int(media_id), "kind": kind}
            out.append(msg)
        waiting = Media(self).status([m["media"]["id"] for m in out if "media" in m])
        for m in out:
            if "media" in m:
                m["media"]["waiting"] = m["media"]["id"] in waiting
        return out

    # -- shared thoughts -------------------------------------------------
    def visible_thoughts(self, me: int, owner_name: str) -> dict[str, Any]:
        owner = self.user_id(owner_name)
        if owner == me:
            raise SocialError("That's your own galaxy.")
        if self.blocked_between(me, owner) or self.severed(me, owner):
            raise SocialError("This galaxy is closed to you.", 403)
        if self.status(me, owner) == "partner":
            scope = "partner"
            rows = self._all("SELECT id, text, created_at, analysis FROM entries WHERE user_id = ? ORDER BY created_at",
                             (owner,))
        elif self.share_family(me, owner):
            scope = "family"
            rows = self._all("SELECT id, text, created_at, analysis FROM entries WHERE user_id = ? AND share_family = 1 "
                             "ORDER BY created_at", (owner,))
            rows = [r for r in rows if _family_safe(r[3])]
        else:
            raise SocialError("Only its owner can open this galaxy.", 403)
        return {"owner": self.username(owner), "scope": scope,
                "thoughts": [{"id": r[0], "text": r[1], "created_at": r[2]} for r in rows]}

    def set_family_share(self, me: int, entry_id: int, share: bool) -> dict[str, Any]:
        row = self._one("SELECT analysis FROM entries WHERE id = ? AND user_id = ?", (entry_id, me))
        if not row:
            raise SocialError("No such thought.", 404)
        if share and not _family_safe(row[0]):
            raise SocialError("This thought was rated 18+ or violent (or hasn't been checked yet), so it can't be "
                              "shared with family.", 409)
        self.db.execute("UPDATE entries SET share_family = ? WHERE id = ? AND user_id = ?", (1 if share else 0, entry_id, me))
        self.db.commit()
        return {"shared": share}

    # -- the universe ----------------------------------------------------
    def universe(self, me: int, others_limit: int = 40) -> dict[str, Any]:
        """Everything the universe view needs: galaxies around mine, strings,
        requests, families and any black-hole swallows not yet watched.

        Polled every few seconds against a remote database, so it uses a fixed
        handful of batched queries rather than a few per galaxy."""
        blocked_by_me = {r[0] for r in self._all("SELECT blocked FROM blocks WHERE blocker = ?", (me,))}
        blocked = blocked_by_me | {r[0] for r in self._all("SELECT blocker FROM blocks WHERE blocked = ?", (me,))}
        severed = {r[0] if r[1] == me else r[1] for r in self._all("SELECT a, b FROM severed WHERE a = ? OR b = ?", (me, me))}
        rel = {(b if a == me else a): status
               for a, b, status in self._all("SELECT a, b, status FROM relations WHERE a = ? OR b = ?", (me, me))}
        fam_rows = self._all(
            "SELECT f.id, f.name, m.user_id, u.username FROM families f "
            "JOIN family_members m ON m.family_id = f.id JOIN users u ON u.id = m.user_id "
            "WHERE f.id IN (SELECT family_id FROM family_members WHERE user_id = ?) ORDER BY f.id, m.joined_at", (me,))
        fams: dict[int, dict[str, Any]] = {}
        family_of: dict[int, list[str]] = {}
        for fid, fname, uid, uname in fam_rows:
            fams.setdefault(fid, {"id": fid, "name": fname, "members": []})["members"].append(uname)
            if uid != me:
                family_of.setdefault(uid, []).append(fname)
        hidden = blocked | severed
        related = (set(rel) | set(family_of)) - hidden
        recent = [r[0] for r in self._all("SELECT id FROM users WHERE id != ? ORDER BY id DESC LIMIT ?",
                                          (me, others_limit + len(hidden)))]
        ids = list(related) + [u for u in recent if u not in related and u not in hidden]
        ids = ids[: max(others_limit, len(related))]
        names, counts = {}, {}
        if ids:
            marks = ",".join("?" * len(ids))
            names = dict(self._all(f"SELECT id, username FROM users WHERE id IN ({marks})", tuple(ids)))
            counts = dict(self._all(f"SELECT user_id, COUNT(*) FROM entries WHERE user_id IN ({marks}) GROUP BY user_id",
                                    tuple(ids)))
        galaxies = [{"username": names.get(uid, "?"), "status": rel.get(uid), "families": family_of.get(uid, []),
                     "stars": int(counts.get(uid, 0)),
                     "can_chat": rel.get(uid) in CHAT_STATUSES or uid in family_of}
                    for uid in ids]
        reqs_in = [{"id": r[0], "from": r[1], "kind": r[2], "family_id": r[3], "at": r[4], "family_name": r[5]}
                   for r in self._all(
                       "SELECT r.id, u.username, r.kind, r.family_id, r.created_at, f.name, r.from_user FROM requests r "
                       "JOIN users u ON u.id = r.from_user LEFT JOIN families f ON f.id = r.family_id "
                       "WHERE r.to_user = ? AND r.status = 'pending' ORDER BY r.id DESC", (me,))
                   if r[6] not in blocked]
        reqs_out = [{"id": r[0], "to": r[1], "kind": r[2], "family_id": r[3]}
                    for r in self._all(
                        "SELECT r.id, u.username, r.kind, r.family_id FROM requests r JOIN users u ON u.id = r.to_user "
                        "WHERE r.from_user = ? AND r.status = 'pending' ORDER BY r.id DESC", (me,))]
        blocked_names = [r[0] for r in self._all(
            "SELECT u.username FROM blocks b JOIN users u ON u.id = b.blocked WHERE b.blocker = ?", (me,))]
        return {"me": self.username(me), "galaxies": galaxies, "requests_in": reqs_in, "requests_out": reqs_out,
                "families": list(fams.values()), "swallows": self.unseen_swallows(me), "blocked": blocked_names}

    def _family_name(self, family_id: Optional[int]) -> Optional[str]:
        row = self._one("SELECT name FROM families WHERE id = ?", (family_id,)) if family_id else None
        return row[0] if row else None

    def search(self, me: int, q: str, limit: int = 10) -> list[str]:
        q = (q or "").strip().lower()
        if len(q) < 2:
            return []
        rows = self._all("SELECT id, username FROM users WHERE username LIKE ? ESCAPE '\\' AND id != ? ORDER BY username "
                         "LIMIT ?", (q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%", me, limit * 2))
        return [name for uid, name in rows if not self.blocked_between(me, uid) and not self.severed(me, uid)][:limit]


def _family_safe(analysis_json: Optional[str]) -> bool:
    """Only thoughts the AI has checked and rated suitable for everyone."""
    import json

    if not analysis_json:
        return False
    try:
        return json.loads(analysis_json).get("rating") == "everyone"
    except (ValueError, AttributeError):
        return False


def _why_not(kind: str, have: Optional[str]) -> str:
    if kind == "friend":
        return "You're already connected." if have else "Can't send that request."
    need = TRANSITIONS[kind][0]
    plural = {"friend": "friends", "enemy": "enemies", "partner": "partners"}
    return f"That needs you to be {plural.get(need, need)} first." if need else "Can't send that request."


# ---------------------------------------------------------------------------
# View-once encrypted media
# ---------------------------------------------------------------------------
MEDIA_KINDS = {"image": ("image/",), "audio": ("audio/",), "video": ("video/",)}
MAX_MEDIA_BYTES = 4 * 1024 * 1024  # Vercel caps request bodies at 4.5 MB
MEDIA_TTL_DAYS = 7
MEDIA_PER_HOUR = 30


def _media_marker(media_id: int, kind: str) -> str:
    return f"\x00media:{media_id}:{kind}"


class Media:
    """Media is encrypted in the sender's browser to the recipient's public
    key; the server only ever holds ciphertext, hands it to the recipient
    once, and deletes it. The chat keeps a small stub ("Photo - opened")."""

    def __init__(self, social: Social):
        self.s = social
        self.db = social.db

    def set_key(self, me: int, jwk: str) -> None:
        jwk = (jwk or "").strip()
        try:
            import json

            parsed = json.loads(jwk)
        except ValueError:
            raise SocialError("That isn't a public key.")
        if not isinstance(parsed, dict) or parsed.get("kty") != "EC" or parsed.get("crv") != "P-256" or "d" in parsed:
            raise SocialError("Only a public P-256 key can be registered.")  # never accept a private key
        if len(jwk) > 1000:
            raise SocialError("That key is too large.")
        self.db.execute("INSERT OR REPLACE INTO public_keys (user_id, jwk, updated_at) VALUES (?, ?, ?)", (me, jwk, _now()))
        self.db.commit()

    def get_key(self, me: int, username: str) -> Optional[str]:
        other = self.s.user_id(username)
        if not self.s.can_chat(me, other):
            raise SocialError("You can only send media to friends, your partner and family.", 403)
        row = self.s._one("SELECT jwk FROM public_keys WHERE user_id = ?", (other,))
        return row[0] if row else None

    def _cleanup(self) -> None:
        cutoff = (_dt.datetime.utcnow() - _dt.timedelta(days=MEDIA_TTL_DAYS)).isoformat()
        self.db.execute("DELETE FROM media WHERE created_at < ?", (cutoff,))

    def send(self, me: int, to_name: str, kind: str, mime: str, iv: str, sender_key: str, data: bytes) -> int:
        other = self.s.user_id(to_name)
        if not self.s.can_chat(me, other):
            raise SocialError("You can only send media to friends, your partner and family.", 403)
        mime = (mime or "").strip().lower()[:80]
        if kind not in MEDIA_KINDS or not mime.startswith(MEDIA_KINDS[kind]):
            raise SocialError("Only photos, audio and video can be sent.")
        if not data:
            raise SocialError("The file is empty.")
        if len(data) > MAX_MEDIA_BYTES:
            raise SocialError("Media can be at most 4 MB.", 413)
        if not iv or len(iv) > 64 or not sender_key or len(sender_key) > 1000:
            raise SocialError("Missing encryption details.")
        since = (_dt.datetime.utcnow() - _dt.timedelta(hours=1)).isoformat()
        if int(self.s._one("SELECT COUNT(*) FROM media WHERE from_user = ? AND created_at >= ?", (me, since))[0]) \
                >= MEDIA_PER_HOUR:
            raise SocialError("Too many media messages this hour.", 429)
        self._cleanup()
        cur = self.db.execute(
            "INSERT INTO media (from_user, to_user, kind, mime, iv, sender_key, data, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (me, other, kind, mime, iv, sender_key, data, _now()))
        media_id = int(cur.lastrowid)
        self.db.execute("INSERT INTO messages (from_user, to_user, text, created_at) VALUES (?, ?, ?, ?)",
                        (me, other, _media_marker(media_id, kind), _now()))
        self.db.commit()
        return media_id

    def open_once(self, me: int, media_id: int) -> dict[str, Any]:
        """Hand the ciphertext to its recipient exactly once, then delete it."""
        row = self.s._one("SELECT from_user, to_user, kind, mime, iv, sender_key, data FROM media WHERE id = ?",
                          (media_id,))
        if not row or row[1] != me:
            raise SocialError("This media has already been opened or has expired.", 410)
        sender = row[0]
        if not self.s.can_chat(me, sender):
            raise SocialError("You can't open media from this galaxy.", 403)
        self.db.execute("DELETE FROM media WHERE id = ?", (media_id,))
        self.db.commit()
        return {"kind": row[2], "mime": row[3], "iv": row[4], "sender_key": row[5], "data": bytes(row[6])}

    def status(self, media_ids: list[int]) -> set[int]:
        """Which of these media are still waiting to be opened."""
        if not media_ids:
            return set()
        marks = ",".join("?" * len(media_ids))
        return {r[0] for r in self.s._all(f"SELECT id FROM media WHERE id IN ({marks})", tuple(media_ids))}
