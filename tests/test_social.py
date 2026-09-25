"""The galaxy ecosystem: requests, statuses, chat, sharing, block, the black
hole, and view-once media."""
import json

import pytest

from mindgalaxy import social as social_module
from mindgalaxy.app import create_app
from mindgalaxy.storage import Storage

from .test_ai_features import FakeAI


@pytest.fixture
def app(tmp_path):
    a = create_app(db_path=str(tmp_path / "eco.db"), multi_user=True, secret_key="s", ai=FakeAI())
    a.config["TESTING"] = True
    return a


_ips = iter(range(1, 10_000))


def user(app, name):
    c = app.test_client()
    assert c.post("/api/signup", json={"username": name, "pin": "1234"},
                  environ_base={"REMOTE_ADDR": f"10.7.{next(_ips) // 250}.{next(_ips) % 250}"}).status_code == 200
    return c


def request(c, to, kind, **extra):
    return c.post("/api/requests", json={"to": to, "kind": kind, **extra})


def incoming(c):
    return c.get("/api/universe").get_json()["requests_in"]


def accept_all(c):
    for r in incoming(c):
        assert c.post(f"/api/requests/{r['id']}/respond", json={"accept": True}).status_code == 200


def make(app, a, b, status):
    """Walk two fresh clients to a status the legitimate way."""
    request(a, b_name(b), "friend")
    accept_all(b)
    if status in ("enemy", "partner"):
        request(a, b_name(b), status)
        accept_all(b)


def b_name(c):
    return c.get("/api/me").get_json()["username"]


def status_of(c, name):
    for g in c.get("/api/universe").get_json()["galaxies"]:
        if g["username"] == name:
            return g["status"]
    return "not visible"


# ---------------------------------------------------------------------------
def test_universe_shows_other_galaxies_but_not_their_thoughts(app):
    a, b = user(app, "alice"), user(app, "bob")
    b.post("/api/entries", json={"text": "bob's private thought"})
    names = [g["username"] for g in a.get("/api/universe").get_json()["galaxies"]]
    assert "bob" in names
    assert a.get("/api/galaxies/bob/thoughts").status_code == 403


def test_friend_request_flow(app):
    a, b = user(app, "alice"), user(app, "bob")
    assert request(a, "bob", "friend").status_code == 201
    assert request(a, "bob", "friend").status_code == 409  # no duplicates
    assert request(b, "alice", "friend").status_code == 409  # nor crossed duplicates
    assert request(a, "alice", "friend").status_code == 400  # not yourself
    assert request(a, "nobody", "friend").status_code == 404
    accept_all(b)
    assert status_of(a, "bob") == "friend" and status_of(b, "alice") == "friend"


def test_declined_request_changes_nothing(app):
    a, b = user(app, "alice"), user(app, "bob")
    request(a, "bob", "friend")
    rid = incoming(b)[0]["id"]
    b.post(f"/api/requests/{rid}/respond", json={"accept": False})
    assert status_of(a, "bob") is None
    assert a.post(f"/api/requests/{rid}/respond", json={"accept": True}).status_code == 404  # not the recipient


def test_only_recipient_can_answer_and_only_once(app):
    a, b, c = user(app, "alice"), user(app, "bob"), user(app, "carol")
    request(a, "bob", "friend")
    rid = incoming(b)[0]["id"]
    assert c.post(f"/api/requests/{rid}/respond", json={"accept": True}).status_code == 404
    b.post(f"/api/requests/{rid}/respond", json={"accept": True})
    assert b.post(f"/api/requests/{rid}/respond", json={"accept": True}).status_code == 409


@pytest.mark.parametrize("kind", ["enemy", "partner", "peace", "unpartner"])
def test_stronger_statuses_need_the_right_starting_point(app, kind):
    a, _ = user(app, "alice"), user(app, "bob")
    assert request(a, "bob", kind).status_code == 409


def test_chat_only_between_friends(app):
    a, b, c = user(app, "alice"), user(app, "bob"), user(app, "carol")
    assert a.post("/api/chat/bob", json={"text": "hi"}).status_code == 403
    make(app, a, b, "friend")
    assert a.post("/api/chat/bob", json={"text": "hi 👋 my number is 555-0100"}).status_code == 201
    msgs = b.get("/api/chat/alice").get_json()["messages"]
    assert msgs[0]["text"] == "hi 👋 my number is 555-0100" and msgs[0]["mine"] is False
    assert c.get("/api/chat/alice").status_code == 403  # nobody else can read it


def test_chat_limits(app):
    a, b = user(app, "alice"), user(app, "bob")
    make(app, a, b, "friend")
    assert a.post("/api/chat/bob", json={"text": "x" * 1001}).status_code == 400
    assert a.post("/api/chat/bob", json={"text": "   "}).status_code == 400


def test_typed_media_marker_cannot_be_forged(app):
    a, b = user(app, "alice"), user(app, "bob")
    make(app, a, b, "friend")
    a.post("/api/chat/bob", json={"text": "\x00media:1:image"})
    msg = b.get("/api/chat/alice").get_json()["messages"][0]
    assert "media" not in msg and msg["text"] == "media:1:image"


def test_enemies_need_both_to_agree_and_cannot_chat(app):
    a, b = user(app, "alice"), user(app, "bob")
    make(app, a, b, "friend")
    request(a, "bob", "enemy")
    assert status_of(a, "bob") == "friend"  # not until bob accepts
    accept_all(b)
    assert status_of(a, "bob") == "enemy"
    assert a.post("/api/chat/bob", json={"text": "hi"}).status_code == 403


def test_make_peace(app):
    a, b = user(app, "alice"), user(app, "bob")
    make(app, a, b, "enemy")
    request(b, "alice", "peace")
    accept_all(a)
    assert status_of(a, "bob") == "friend"


def test_report_rules(app):
    a, b, c = user(app, "alice"), user(app, "bob"), user(app, "carol")
    make(app, a, c, "friend")
    assert a.post("/api/report", json={"username": "carol"}).status_code == 409  # friends can't report
    make(app, a, b, "enemy")
    r = a.post("/api/report", json={"username": "bob"})
    assert r.status_code == 200 and r.get_json() == {"reports": 1, "needed": 5, "swallowed": False}
    assert a.post("/api/report", json={"username": "bob"}).status_code == 429  # once a day


def _age_reports(app, n, reporter, reported):
    with Storage(app.config["DB_PATH"]) as s:
        for _ in range(n):
            s.conn.execute("INSERT INTO reports (reporter, reported, created_at) VALUES (?, ?, ?)",
                           (reporter, reported, "2026-01-01T00:00:00"))
        s.conn.commit()


def _uid(app, name):
    with Storage(app.config["DB_PATH"]) as s:
        return s.get_user(name)["id"]


def test_black_hole_swallows_after_enough_reports(app):
    a, b = user(app, "alice"), user(app, "bob")
    make(app, a, b, "friend")
    a.post("/api/chat/bob", json={"text": "we used to be friends"})
    request(a, "bob", "enemy")
    accept_all(b)
    _age_reports(app, 4, _uid(app, "alice"), _uid(app, "bob"))
    r = a.post("/api/report", json={"username": "bob"}).get_json()
    assert r["swallowed"] is True
    # both see the swallow once
    sa = a.get("/api/universe").get_json()["swallows"]
    sb = b.get("/api/universe").get_json()["swallows"]
    assert sa == [{"with": "bob", "swallowed": "bob", "you_were_swallowed": False, "at": sa[0]["at"]}]
    assert sb[0]["you_were_swallowed"] is True
    a.post("/api/swallows/seen", json={})
    assert a.get("/api/universe").get_json()["swallows"] == []
    # severed forever: no status, no chat, chat history gone, no requests in either direction
    assert status_of(a, "bob") == "not visible" and status_of(b, "alice") == "not visible"
    with Storage(app.config["DB_PATH"]) as s:
        assert s.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
    assert request(b, "alice", "friend").status_code == 403
    assert request(a, "bob", "friend").status_code == 403
    assert "bob" not in a.get("/api/users/search?q=bo").get_json()["users"]


def test_swallow_detaches_shared_families(app):
    a, b, c = user(app, "alice"), user(app, "bob"), user(app, "carol")
    make(app, a, b, "friend")
    make(app, a, c, "friend")
    fid = a.post("/api/families", json={"name": "Home"}).get_json()["id"]
    request(a, "bob", "family_invite", family_id=fid)
    accept_all(b)
    request(a, "bob", "enemy")
    accept_all(b)
    _age_reports(app, 4, _uid(app, "alice"), _uid(app, "bob"))
    a.post("/api/report", json={"username": "bob"})
    fams = a.get("/api/universe").get_json()["families"]
    assert fams[0]["members"] == ["alice"]


def test_partner_sees_all_thoughts_and_leaving_needs_agreement(app):
    a, b = user(app, "alice"), user(app, "bob")
    b.post("/api/entries", json={"text": "bob's secret"})
    make(app, a, b, "partner")
    assert a.get("/api/galaxies/bob/thoughts").get_json()["thoughts"][0]["text"] == "bob's secret"
    request(a, "bob", "unpartner")
    assert status_of(a, "bob") == "partner"  # both must agree
    accept_all(b)
    assert status_of(a, "bob") == "friend"
    assert a.get("/api/galaxies/bob/thoughts").status_code == 403


def test_family_sharing_rules(app):
    a, b, c = user(app, "alice"), user(app, "bob"), user(app, "carol")
    make(app, a, b, "friend")
    fid = a.post("/api/families", json={"name": "Home"}).get_json()["id"]
    assert request(a, "carol", "family_invite", family_id=fid).status_code == 409  # not friends
    request(a, "bob", "family_invite", family_id=fid)
    accept_all(b)
    ok = b.post("/api/entries", json={"text": "I like to eat noodles"}).get_json()["id"]
    b.post(f"/api/entries/{ok}/enrich", json={})
    private = b.post("/api/entries", json={"text": "Made pad thai tonight"}).get_json()["id"]
    b.post(f"/api/entries/{private}/enrich", json={})
    unchecked = b.post("/api/entries", json={"text": "not analysed yet"}).get_json()["id"]
    # the fake AI rates everything "everyone" unless told otherwise; mark one mature
    with Storage(app.config["DB_PATH"]) as s:
        s.conn.execute("UPDATE entries SET analysis = ? WHERE id = ?",
                       (json.dumps({"category": "other", "subject": "x", "rating": "mature"}), private))
        s.conn.execute("UPDATE entries SET analysis = ? WHERE id = ?",
                       (json.dumps({"category": "food", "subject": "noodles", "rating": "everyone"}), ok))
        s.conn.commit()
    assert b.post(f"/api/entries/{ok}/share", json={"family": True}).status_code == 200
    assert b.post(f"/api/entries/{private}/share", json={"family": True}).status_code == 409
    assert b.post(f"/api/entries/{unchecked}/share", json={"family": True}).status_code == 409
    seen = [t["text"] for t in a.get("/api/galaxies/bob/thoughts").get_json()["thoughts"]]
    assert seen == ["I like to eat noodles"]
    assert a.post(f"/api/entries/{ok}/share", json={"family": True}).status_code == 404  # not alice's thought
    # family members can chat
    assert a.post("/api/chat/bob", json={"text": "hi family"}).status_code == 201


def test_family_leaving_needs_another_member(app):
    a, b = user(app, "alice"), user(app, "bob")
    make(app, a, b, "friend")
    fid = a.post("/api/families", json={"name": "Home"}).get_json()["id"]
    request(a, "bob", "family_invite", family_id=fid)
    accept_all(b)
    assert b.post(f"/api/families/{fid}/leave", json={}).status_code == 409
    request(b, "alice", "family_leave", family_id=fid)
    accept_all(a)
    assert a.get("/api/universe").get_json()["families"][0]["members"] == ["alice"]
    assert a.post(f"/api/families/{fid}/leave", json={}).status_code == 200  # last member leaves freely
    assert a.get("/api/universe").get_json()["families"] == []


def test_family_size_cap(app, monkeypatch):
    monkeypatch.setattr(social_module, "FAMILY_MAX", 2)
    a, b, c = user(app, "alice"), user(app, "bob"), user(app, "carol")
    make(app, a, b, "friend")
    make(app, a, c, "friend")
    fid = a.post("/api/families", json={"name": "Home"}).get_json()["id"]
    request(a, "bob", "family_invite", family_id=fid)
    accept_all(b)
    assert request(a, "carol", "family_invite", family_id=fid).status_code == 409


def test_block_is_one_sided_and_instant(app):
    a, b = user(app, "alice"), user(app, "bob")
    b.post("/api/entries", json={"text": "bob's secret"})
    make(app, a, b, "partner")
    assert b.post("/api/block", json={"username": "alice"}).status_code == 200
    assert a.get("/api/galaxies/bob/thoughts").status_code == 403
    assert a.post("/api/chat/bob", json={"text": "hi"}).status_code == 403
    assert request(a, "bob", "friend").status_code == 403
    assert status_of(a, "bob") == "not visible"
    b.post("/api/unblock", json={"username": "alice"})
    assert request(a, "bob", "friend").status_code == 201  # starts over as strangers


def test_unfriend_is_one_sided_for_friends_only(app):
    a, b = user(app, "alice"), user(app, "bob")
    make(app, a, b, "partner")
    assert a.post("/api/unfriend", json={"username": "bob"}).status_code == 409
    c, d = user(app, "carol"), user(app, "dave")
    make(app, c, d, "friend")
    assert c.post("/api/unfriend", json={"username": "dave"}).status_code == 200
    assert status_of(c, "dave") is None


def test_request_rate_limit(app, monkeypatch):
    monkeypatch.setattr(social_module, "REQUESTS_PER_DAY", 2)
    a = user(app, "alice")
    for n in ("bob", "carol", "dave"):
        user(app, n)
    assert request(a, "bob", "friend").status_code == 201
    assert request(a, "carol", "friend").status_code == 201
    assert request(a, "dave", "friend").status_code == 429


def test_ecosystem_is_hosted_only(tmp_path):
    c = create_app(db_path=str(tmp_path / "solo.db")).test_client()
    assert c.get("/api/universe").status_code == 404


# ---------------------------------------------------------------------------
# View-once encrypted media
# ---------------------------------------------------------------------------
PUB = json.dumps({"kty": "EC", "crv": "P-256", "x": "abc", "y": "def"})


def send_media(c, to, data=b"\x01ciphertext", kind="image", mime="image/jpeg", headers=None):
    h = {"X-MindGalaxy": "1", "X-Media-Kind": kind, "X-Media-Mime": mime, "X-Media-IV": "aXY=",
         "X-Media-Key": PUB}
    h.update(headers or {})
    return c.post(f"/api/chat/{to}/media", data=data, content_type="application/octet-stream", headers=h)


def test_public_keys_only(app):
    a = user(app, "alice")
    assert a.post("/api/keys", json={"jwk": PUB}).status_code == 200
    private = json.dumps({"kty": "EC", "crv": "P-256", "x": "a", "y": "b", "d": "SECRET"})
    assert a.post("/api/keys", json={"jwk": private}).status_code == 400  # never store a private key
    assert a.post("/api/keys", json={"jwk": "junk"}).status_code == 400


def test_keys_only_for_chat_partners(app):
    a, b = user(app, "alice"), user(app, "bob")
    b.post("/api/keys", json={"jwk": PUB})
    assert a.get("/api/keys/bob").status_code == 403
    make(app, a, b, "friend")
    assert a.get("/api/keys/bob").get_json()["jwk"] == PUB


def test_media_opens_exactly_once_for_recipient_only(app):
    a, b, c = user(app, "alice"), user(app, "bob"), user(app, "carol")
    make(app, a, b, "friend")
    r = send_media(a, "bob", data=b"\x00\x01encrypted-bytes")
    assert r.status_code == 201
    mid = r.get_json()["id"]
    msg = b.get("/api/chat/alice").get_json()["messages"][0]
    assert msg["media"] == {"id": mid, "kind": "image", "waiting": True}
    assert a.post(f"/api/media/{mid}/open", json={}).status_code == 410  # not even the sender
    assert c.post(f"/api/media/{mid}/open", json={}).status_code == 410
    opened = b.post(f"/api/media/{mid}/open", json={})
    assert opened.status_code == 200 and opened.data == b"\x00\x01encrypted-bytes"
    assert opened.headers["X-Media-IV"] == "aXY=" and opened.headers["Cache-Control"] == "no-store"
    assert b.post(f"/api/media/{mid}/open", json={}).status_code == 410  # gone for good
    assert b.get("/api/chat/alice").get_json()["messages"][0]["media"]["waiting"] is False
    with Storage(app.config["DB_PATH"]) as s:
        assert s.conn.execute("SELECT COUNT(*) FROM media").fetchone()[0] == 0  # nothing kept on the server


def test_media_rules(app):
    a, b = user(app, "alice"), user(app, "bob")
    assert send_media(a, "bob").status_code == 403  # strangers can't
    make(app, a, b, "friend")
    assert send_media(a, "bob", kind="exe", mime="application/x-msdownload").status_code == 400
    assert send_media(a, "bob", kind="image", mime="video/mp4").status_code == 400  # kind must match type
    assert send_media(a, "bob", data=b"").status_code == 400
    assert send_media(a, "bob", data=b"x" * (4 * 1024 * 1024 + 1)).status_code == 413
    assert send_media(a, "bob", headers={"X-MindGalaxy": ""}).status_code == 415  # CSRF header required
    assert send_media(a, "bob", kind="audio", mime="audio/webm").status_code == 201
    assert send_media(a, "bob", kind="video", mime="video/mp4").status_code == 201


def test_unopened_media_expires(app):
    a, b = user(app, "alice"), user(app, "bob")
    make(app, a, b, "friend")
    mid = send_media(a, "bob").get_json()["id"]
    with Storage(app.config["DB_PATH"]) as s:
        s.conn.execute("UPDATE media SET created_at = '2020-01-01T00:00:00' WHERE id = ?", (mid,))
        s.conn.commit()
    send_media(a, "bob")  # any upload sweeps expired media
    assert b.post(f"/api/media/{mid}/open", json={}).status_code == 410


def test_swallow_destroys_pending_media(app):
    a, b = user(app, "alice"), user(app, "bob")
    make(app, a, b, "friend")
    mid = send_media(a, "bob").get_json()["id"]
    request(a, "bob", "enemy")
    accept_all(b)
    _age_reports(app, 4, _uid(app, "alice"), _uid(app, "bob"))
    a.post("/api/report", json={"username": "bob"})
    assert b.post(f"/api/media/{mid}/open", json={}).status_code == 410
    with Storage(app.config["DB_PATH"]) as s:
        assert s.conn.execute("SELECT COUNT(*) FROM media").fetchone()[0] == 0


def test_universe_script_only_on_hosted_site(app, tmp_path):
    c = user(app, "alice")
    assert b'src="/universe.js"' in c.get("/").data
    js = c.get("/universe.js")
    assert js.status_code == 200 and js.mimetype == "text/javascript" and b"MindGalaxy" in js.data
    from mindgalaxy.exporter import render_html
    assert "src=\"/universe.js\"" not in render_html({}, mode="standalone")
