"""
mindgalaxy.calls
=================

Audio and video calls between connected galaxies.

Calls run peer-to-peer in the browsers (WebRTC, always encrypted); the
server never sees or stores any audio or video, and nothing is recorded.
What the server does decide is *who may call whom*:

* a call is a "room" whose members are fixed when it's created;
* every pair of members must be connected -- friends, life partners, the
  same family, or families linked by their elders. So if A, B and D all
  know each other but C only knows B and D, then A+B+D can call together and
  so can B+C+D, but C can never be in a call that A is in;
* audio calls hold up to AUDIO_MAX people, video calls up to VIDEO_MAX
  (every browser sends its stream to every other one);
* a member joins with the id of their current page session, and the others
  only ever connect to ids the server lists for that room.

Ringing and connection set-up go through a PeerJS "switchboard"; each page
session registers a random, unguessable id here (presence), and it's only
revealed to people allowed to call them.
"""
from __future__ import annotations

import datetime as _dt
import re
import secrets
from itertools import combinations
from typing import Any, Optional

from .social import Social, SocialError

AUDIO_MAX = 10
VIDEO_MAX = 4
ONLINE_SECONDS = 150
ROOM_HOURS = 6
PEER_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def _now() -> _dt.datetime:
    return _dt.datetime.utcnow()


class Calls:
    def __init__(self, social: Social):
        self.s = social
        self.db = social.db

    # -- presence ---------------------------------------------------------
    def set_presence(self, me: int, peer_id: str) -> None:
        if not PEER_RE.match(peer_id or ""):
            raise SocialError("That isn't a valid session id.")
        self.db.execute("INSERT OR REPLACE INTO presence (user_id, peer_id, seen) VALUES (?, ?, ?)",
                        (me, peer_id, _now().isoformat()))
        self.db.commit()

    def online_peer(self, uid: int) -> Optional[str]:
        cutoff = (_now() - _dt.timedelta(seconds=ONLINE_SECONDS)).isoformat()
        row = self.s._one("SELECT peer_id FROM presence WHERE user_id = ? AND seen >= ?", (uid, cutoff))
        return row[0] if row else None

    def online_contacts(self, me: int, usernames: list[str]) -> dict[str, bool]:
        out = {}
        for name in usernames[:100]:
            try:
                uid = self.s.user_id(name)
            except SocialError:
                continue
            out[name] = self.s.can_chat(me, uid) and self.online_peer(uid) is not None
        return out

    # -- rooms ------------------------------------------------------------
    def check_group(self, me: int, usernames: list[str], kind: str) -> list[int]:
        """The member ids if this group may call together, else a SocialError
        saying who doesn't know whom."""
        if kind not in ("audio", "video"):
            raise SocialError("A call is either audio or video.")
        ids = [me]
        for name in usernames:
            uid = self.s.user_id(name)
            if uid not in ids:
                ids.append(uid)
        if len(ids) < 2:
            raise SocialError("Pick at least one person to call.")
        limit = VIDEO_MAX if kind == "video" else AUDIO_MAX
        if len(ids) > limit:
            raise SocialError(f"{kind.title()} calls can have at most {limit} people.", 409)
        for x, y in combinations(ids, 2):
            if not self.s.can_chat(x, y):
                raise SocialError(f"{self.s.username(x)} and {self.s.username(y)} aren't connected, so they can't "
                                  "be in the same call. Everyone in a call must know everyone else.", 403)
        return ids

    def create_room(self, me: int, usernames: list[str], kind: str) -> dict[str, Any]:
        ids = self.check_group(me, usernames, kind)
        room_id = secrets.token_urlsafe(12)
        self.db.execute("INSERT INTO call_rooms (id, created_by, kind, created_at) VALUES (?, ?, ?, ?)",
                        (room_id, me, kind, _now().isoformat()))
        for uid in ids:
            self.db.execute("INSERT INTO call_members (room_id, user_id) VALUES (?, ?)", (room_id, uid))
        cutoff = (_now() - _dt.timedelta(hours=ROOM_HOURS)).isoformat()
        old = [r[0] for r in self.s._all("SELECT id FROM call_rooms WHERE created_at < ?", (cutoff,))]
        for rid in old:
            self.db.execute("DELETE FROM call_members WHERE room_id = ?", (rid,))
            self.db.execute("DELETE FROM call_rooms WHERE id = ?", (rid,))
        self.db.commit()
        return self.room(me, room_id)

    def room(self, me: int, room_id: str) -> dict[str, Any]:
        row = self.s._one("SELECT created_by, kind, created_at FROM call_rooms WHERE id = ?", (room_id,))
        if not row:
            raise SocialError("This call has ended.", 404)
        members = self.s._all("SELECT m.user_id, u.username, m.joined, m.peer_id FROM call_members m "
                              "JOIN users u ON u.id = m.user_id WHERE m.room_id = ?", (room_id,))
        if me not in [m[0] for m in members]:
            raise SocialError("You're not part of this call.", 403)
        out = []
        for uid, name, joined, peer in members:
            if uid == me:
                out.append({"username": name, "me": True, "joined": bool(joined)})
                continue
            # a member cut off since the call started (block, black hole) is dropped
            if not self.s.can_chat(me, uid):
                continue
            entry = {"username": name, "joined": bool(joined)}
            if joined:
                entry["peer_id"] = peer
            else:
                entry["ring_peer_id"] = self.online_peer(uid)
            out.append(entry)
        return {"id": room_id, "kind": row[1], "created_by": self.s.username(row[0]), "members": out}

    def join(self, me: int, room_id: str, peer_id: str) -> dict[str, Any]:
        if not PEER_RE.match(peer_id or ""):
            raise SocialError("That isn't a valid session id.")
        self.room(me, room_id)  # membership check
        self.db.execute("UPDATE call_members SET joined = 1, peer_id = ? WHERE room_id = ? AND user_id = ?",
                        (peer_id, room_id, me))
        self.db.commit()
        return self.room(me, room_id)

    def leave(self, me: int, room_id: str) -> None:
        self.db.execute("UPDATE call_members SET joined = 0, peer_id = NULL WHERE room_id = ? AND user_id = ?",
                        (room_id, me))
        left = self.s._one("SELECT COUNT(*) FROM call_members WHERE room_id = ? AND joined = 1", (room_id,))[0]
        if not left:
            self.db.execute("DELETE FROM call_members WHERE room_id = ?", (room_id,))
            self.db.execute("DELETE FROM call_rooms WHERE id = ?", (room_id,))
        self.db.commit()
