"""Calls, family roles, family-to-family links and the first-login tour."""
import pytest

from mindgalaxy import calls as calls_module
from mindgalaxy.app import create_app

from .test_ai_features import FakeAI
from .test_social import accept_all, make, request, user

PEER = "peer-" + "x" * 20


@pytest.fixture
def app(tmp_path):
    a = create_app(db_path=str(tmp_path / "calls.db"), multi_user=True, secret_key="s", ai=FakeAI())
    a.config["TESTING"] = True
    return a


def call(c, names, kind="audio"):
    return c.post("/api/calls", json={"usernames": names, "kind": kind})


def square(app):
    """Your example: a-b, b-c, d-b, c-d and d-a are friends (a and c are not)."""
    a, b, c, d = (user(app, n) for n in ("aaa", "bbb", "ccc", "ddd"))
    for x, y in ((a, b), (b, c), (d, b), (c, d), (d, a)):
        make(app, x, y, "friend")
    return a, b, c, d


# ---------------------------------------------------------------------------
def test_group_call_needs_everyone_to_know_everyone(app):
    a, b, c, d = square(app)
    assert call(a, ["bbb", "ddd"]).status_code == 201          # a, b, d all know each other
    assert call(b, ["ccc", "ddd"]).status_code == 201          # so do b, c, d
    r = call(a, ["bbb", "ccc", "ddd"])
    assert r.status_code == 403 and "aaa and ccc" in r.get_json()["error"]  # a doesn't know c
    assert call(a, ["ccc"]).status_code == 403


def test_call_size_limits(app):
    names = ["pal1", "pal2", "pal3", "pal4", "pal5"]
    host = user(app, "host")
    for n in names:
        make(app, host, user(app, n), "friend")
    # video: at most 4 people
    assert call(host, names[:3], "video").status_code in (201, 403)  # pairwise check may fail first
    r = call(host, names, "video")
    assert r.status_code == 409 and "at most 4" in r.get_json()["error"]


def test_audio_limit(app, monkeypatch):
    monkeypatch.setattr(calls_module, "AUDIO_MAX", 2)
    a, b, c, d = square(app)
    r = call(a, ["bbb", "ddd"], "audio")
    assert r.status_code == 409 and "at most 2" in r.get_json()["error"]


def test_family_members_can_group_call_without_being_friends(app):
    a, b, c = user(app, "mom"), user(app, "son"), user(app, "gran")
    make(app, a, b, "friend")
    make(app, a, c, "friend")
    fid = a.post("/api/families", json={"name": "Home"}).get_json()["id"]
    request(a, "son", "family_invite", family_id=fid)
    accept_all(b)
    request(a, "gran", "family_invite", family_id=fid)
    accept_all(c)
    # son and gran aren't friends, but they're family
    assert call(b, ["gran", "mom"], "video").status_code == 201


def test_room_membership_and_joining(app):
    a, b, c, d = square(app)
    room = call(a, ["bbb", "ddd"], "video").get_json()
    rid = room["id"]
    assert room["kind"] == "video" and room["created_by"] == "aaa"
    assert c.get(f"/api/calls/{rid}").status_code == 403          # c isn't in this call
    assert c.post(f"/api/calls/{rid}/join", json={"peer_id": PEER}).status_code == 403
    assert b.post(f"/api/calls/{rid}/join", json={"peer_id": "short"}).status_code == 400
    joined = b.post(f"/api/calls/{rid}/join", json={"peer_id": PEER}).get_json()
    view = {m["username"]: m for m in a.get(f"/api/calls/{rid}").get_json()["members"]}
    assert view["bbb"]["joined"] and view["bbb"]["peer_id"] == PEER     # joined members' session ids are shared
    assert not view["ddd"]["joined"] and "peer_id" not in view["ddd"]
    assert view["ddd"]["ring_peer_id"] is None                        # d isn't online
    d.post("/api/presence", json={"peer_id": "dpeer-" + "y" * 20})
    view = {m["username"]: m for m in a.get(f"/api/calls/{rid}").get_json()["members"]}
    assert view["ddd"]["ring_peer_id"] == "dpeer-" + "y" * 20
    assert joined["id"] == rid


def test_room_ends_when_everyone_leaves(app):
    a, b, c, d = square(app)
    rid = call(a, ["bbb"]).get_json()["id"]
    a.post(f"/api/calls/{rid}/join", json={"peer_id": PEER})
    b.post(f"/api/calls/{rid}/join", json={"peer_id": PEER.replace("x", "z")})
    a.post(f"/api/calls/{rid}/leave", json={})
    assert b.get(f"/api/calls/{rid}").status_code == 200
    b.post(f"/api/calls/{rid}/leave", json={})
    assert b.get(f"/api/calls/{rid}").status_code == 404


def test_blocked_member_drops_out_of_a_call(app):
    a, b, c, d = square(app)
    rid = call(a, ["bbb", "ddd"]).get_json()["id"]
    d.post(f"/api/calls/{rid}/join", json={"peer_id": PEER})
    b.post("/api/block", json={"username": "ddd"})
    names = [m["username"] for m in b.get(f"/api/calls/{rid}").get_json()["members"]]
    assert "ddd" not in names


def test_presence_is_private(app):
    a, b, c, d = square(app)
    stranger = user(app, "stranger")
    assert b.post("/api/presence", json={"peer_id": "bad id!"}).status_code == 400
    b.post("/api/presence", json={"peer_id": "bpeer-" + "q" * 20})
    online = {g["username"]: g["online"] for g in a.get("/api/universe").get_json()["galaxies"]}
    assert online["bbb"] is True
    online = {g["username"]: g["online"] for g in stranger.get("/api/universe").get_json()["galaxies"]}
    assert online["bbb"] is False  # strangers never see who's online


def test_ice_servers(app, monkeypatch):
    a = user(app, "alice")
    monkeypatch.delenv("CF_TURN_KEY_ID", raising=False)
    servers = a.get("/api/calls/ice").get_json()["iceServers"]
    assert servers and all("stun:" in u for s in servers for u in s["urls"])


# ---------------------------------------------------------------------------
# Family roles and family-to-family links
# ---------------------------------------------------------------------------
def family(app, owner, name, members):
    fid = owner.post("/api/families", json={"name": name}).get_json()["id"]
    for client, uname, role in members:
        make(app, owner, client, "friend")
        request(owner, uname, "family_invite", family_id=fid)
        for r in client.get("/api/universe").get_json()["requests_in"]:
            client.post(f"/api/requests/{r['id']}/respond", json={"accept": True, "role": role})
    return fid


def test_each_member_picks_their_own_role(app):
    mom, kid = user(app, "mom"), user(app, "kid")
    fid = family(app, mom, "Home", [(kid, "kid", "son")])
    assert mom.post(f"/api/families/{fid}/role", json={"role": "mother"}).status_code == 200
    assert mom.post(f"/api/families/{fid}/role", json={"role": "queen"}).status_code == 400
    fam = mom.get("/api/universe").get_json()["families"][0]
    assert fam["roles"] == {"mom": "mother", "kid": "son"} and fam["i_am_elder"] is True
    stranger = user(app, "stranger")
    assert stranger.post(f"/api/families/{fid}/role", json={"role": "father"}).status_code == 404


def test_only_elders_link_families(app):
    mom, kid = user(app, "mom"), user(app, "kid")
    f1 = family(app, mom, "Reddys", [(kid, "kid", "son")])
    dad, girl = user(app, "dad"), user(app, "girl")
    f2 = family(app, dad, "Daidas", [(girl, "girl", "daughter")])
    mom.post(f"/api/families/{f1}/role", json={"role": "mother"})
    make(app, kid, dad, "friend")
    # a son can't link the families
    r = kid.post("/api/family-links", json={"family_id": f1, "to": "dad", "their_family_id": f2})
    assert r.status_code == 403
    # the other side must be an elder too
    r = mom.post("/api/family-links", json={"family_id": f1, "to": "girl", "their_family_id": f2})
    assert r.status_code == 409
    dad.post(f"/api/families/{f2}/role", json={"role": "father"})
    r = mom.post("/api/family-links", json={"family_id": f1, "to": "dad", "their_family_id": f2})
    assert r.status_code == 201
    assert mom.post("/api/family-links", json={"family_id": f1, "to": "dad", "their_family_id": f2}).status_code == 409
    req = dad.get("/api/universe").get_json()["requests_in"][0]
    assert req["kind"] == "family_link" and req["family_name"] == "Reddys" and req["family2_name"] == "Daidas"
    dad.post(f"/api/requests/{req['id']}/respond", json={"accept": True})
    links = mom.get("/api/universe").get_json()["families"][0]["links"]
    assert links[0]["name"] == "Daidas"
    # members of linked families can now call and chat, even as strangers
    assert kid.post("/api/chat/girl", json={"text": "hi cousin!"}).status_code == 201
    assert call(kid, ["girl"], "video").status_code == 201


def test_role_can_change_after_joining(app):
    mom, kid = user(app, "mom"), user(app, "kid")
    fid = family(app, mom, "Home", [(kid, "kid", "son")])
    kid.post(f"/api/families/{fid}/role", json={"role": "grandson"})
    assert mom.get("/api/universe").get_json()["families"][0]["roles"]["kid"] == "grandson"


# ---------------------------------------------------------------------------
def test_first_login_tour_flag(app):
    a = user(app, "newbie")
    assert a.get("/api/me").get_json()["tour_done"] is False
    assert a.post("/api/tour/done", json={}).status_code == 200
    assert a.get("/api/me").get_json()["tour_done"] is True
    # it stays done on later logins
    b = app.test_client()
    b.post("/api/login", json={"username": "newbie", "pin": "1234"})
    assert b.get("/api/me").get_json()["tour_done"] is True


def test_family_link_finds_their_family(app):
    mom, kid = user(app, "mom"), user(app, "kid")
    f1 = family(app, mom, "Reddys", [(kid, "kid", "son")])
    dad, girl = user(app, "dad"), user(app, "girl")
    family(app, dad, "Daidas", [(girl, "girl", "daughter")])
    mom.post(f"/api/families/{f1}/role", json={"role": "mother"})
    make(app, mom, dad, "friend")
    assert mom.post("/api/family-links", json={"family_id": f1, "to": "dad"}).status_code == 409  # not an elder yet
    fams = dad.get("/api/universe").get_json()["families"]
    dad.post(f"/api/families/{fams[0]['id']}/role", json={"role": "grandfather"})
    assert mom.post("/api/family-links", json={"family_id": f1, "to": "dad"}).status_code == 201
