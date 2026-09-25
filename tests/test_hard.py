"""Adversarial tests: races, forged sessions, idle expiry, cross-user access,
hostile input, partial failures, and the free-provider fallback chain run
against a real local HTTP server."""
import datetime as dt
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from flask.sessions import SecureCookieSessionInterface

from mindgalaxy import app as app_module
from mindgalaxy import auth, free_ai
from mindgalaxy.ai import AIError, KnowledgeAI, QuotaError
from mindgalaxy.app import create_app
from mindgalaxy.free_ai import FreeProvider, ProviderError, conform, parse_json_object
from mindgalaxy.storage import Storage

from .test_ai_features import FakeAI


def make_app(tmp_path, ai=None, secret="s3cret"):
    app = create_app(db_path=str(tmp_path / "hard.db"), multi_user=True, secret_key=secret, ai=ai)
    app.config["TESTING"] = True
    return app


def signup(c, username="alice", pin="1234", ip="10.0.0.1"):
    return c.post("/api/signup", json={"username": username, "pin": pin}, environ_base={"REMOTE_ADDR": ip})


def login(c, username="alice", pin="1234", ip="10.0.0.1"):
    return c.post("/api/login", json={"username": username, "pin": pin}, environ_base={"REMOTE_ADDR": ip})


# ---------------------------------------------------------------------------
# Races
# ---------------------------------------------------------------------------
def test_simultaneous_signups_for_same_name_create_exactly_one_account(tmp_path):
    app = make_app(tmp_path)
    Storage(app.config["DB_PATH"]).close()  # create schema up front
    results = []

    def attempt(n):
        with app.test_client() as c:
            results.append(signup(c, "racer", f"{n:04d}", ip=f"10.1.0.{n}").status_code)

    threads = [threading.Thread(target=attempt, args=(n,)) for n in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(set(results)) in ([200, 409], [200]) and results.count(200) == 1, results
    with Storage(app.config["DB_PATH"]) as s:
        assert s.conn.execute("SELECT COUNT(*) FROM users WHERE username='racer'").fetchone()[0] == 1


def test_parallel_wrong_pins_still_lock_the_account(tmp_path):
    app = make_app(tmp_path)
    signup(app.test_client())
    codes = []

    def attempt(n):
        with app.test_client() as c:
            codes.append(login(c, pin="0000", ip=f"10.2.0.{n}").status_code)

    threads = [threading.Thread(target=attempt, args=(n,)) for n in range(15)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert 500 not in codes
    assert login(app.test_client(), ip="10.3.0.1").status_code == 423  # right PIN, still locked


def test_lock_expires(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    signup(app.test_client())
    c = app.test_client()
    for _ in range(auth.MAX_ATTEMPTS):
        login(c, pin="0000")
    assert login(c).status_code == 423
    future = dt.datetime.utcnow() + auth.LOCK_FOR + dt.timedelta(seconds=5)
    monkeypatch.setattr(auth, "_now", lambda: future)
    assert login(c).status_code == 200


# ---------------------------------------------------------------------------
# Sessions: forgery, idle expiry, deleted users
# ---------------------------------------------------------------------------
def _cookie_for(app, data):
    return SecureCookieSessionInterface().get_signing_serializer(app).dumps(data)


def test_forged_session_cookie_is_rejected(tmp_path):
    app = make_app(tmp_path)
    signup(app.test_client())
    attacker = make_app(tmp_path, secret="attackers-guess")
    forged = _cookie_for(attacker, {"uid": 1, "seen": time.time()})
    c = app.test_client()
    c.set_cookie("session", forged)
    assert c.get("/api/stars").status_code == 401


def test_tampered_cookie_is_rejected(tmp_path):
    app = make_app(tmp_path)
    c = app.test_client()
    signup(c)
    good = c.get_cookie("session").value
    c.set_cookie("session", good[:-2] + ("AA" if not good.endswith("AA") else "BB"))
    assert c.get("/api/stars").status_code == 401


def test_idle_session_expires_server_side(tmp_path):
    app = make_app(tmp_path)
    c = app.test_client()
    signup(c)
    with c.session_transaction() as s:
        s["seen"] = time.time() - app_module.IDLE_LIMIT.total_seconds() - 1
    assert c.get("/api/stars").status_code == 401
    assert c.get("/").status_code == 302
    # and it stays signed out: the session was cleared, not just refused
    assert c.get("/api/me").status_code == 401


def test_activity_keeps_session_alive_indefinitely(tmp_path):
    app = make_app(tmp_path)
    c = app.test_client()
    signup(c)
    limit = app_module.IDLE_LIMIT.total_seconds()
    for _ in range(5):  # five back-to-back "almost idle" periods = far past the limit in total
        with c.session_transaction() as s:
            s["seen"] = time.time() - limit + 30
        assert c.post("/api/ping", json={}).status_code == 200
    assert c.get("/api/stars").status_code == 200


def test_session_for_deleted_user(tmp_path):
    app = make_app(tmp_path)
    c = app.test_client()
    signup(c)
    with Storage(app.config["DB_PATH"]) as s:
        s.conn.execute("DELETE FROM users")
        s.conn.commit()
    assert c.get("/api/me").status_code == 401


def test_me_reports_idle_timings(tmp_path):
    c = make_app(tmp_path).test_client()
    signup(c)
    me = c.get("/api/me").get_json()
    assert me["idle_warn_seconds"] == app_module.IDLE_WARN_SECONDS
    assert me["idle_countdown_seconds"] == app_module.IDLE_COUNTDOWN_SECONDS


# ---------------------------------------------------------------------------
# Cross-user access and CSRF
# ---------------------------------------------------------------------------
def test_no_cross_user_access_by_id(tmp_path):
    app = make_app(tmp_path, ai=FakeAI())
    a, b = app.test_client(), app.test_client()
    signup(a, "alice")
    signup(b, "bob", ip="10.0.0.2")
    alice_id = a.post("/api/entries", json={"text": "I like to eat noodles"}).get_json()["id"]
    assert b.post(f"/api/entries/{alice_id}/enrich", json={}).status_code == 404
    assert b.post("/api/explore", json={"entry_id": alice_id, "path": []}).status_code == 404
    assert b.get("/api/stars").get_json()["count"] == 0


def test_links_never_cross_users(tmp_path):
    ai = FakeAI({"pad thai": [("noodles", "made_from")]})
    app = make_app(tmp_path, ai=ai)
    a, b = app.test_client(), app.test_client()
    signup(a, "alice")
    signup(b, "bob", ip="10.0.0.2")
    nid = a.post("/api/entries", json={"text": "I like to eat noodles"}).get_json()["id"]
    a.post(f"/api/entries/{nid}/enrich", json={})
    pid = b.post("/api/entries", json={"text": "Made pad thai tonight"}).get_json()["id"]
    assert b.post(f"/api/entries/{pid}/enrich", json={}).get_json()["links"] == 0


@pytest.mark.parametrize("kwargs", [
    {"data": "username=alice&pin=1234", "content_type": "application/x-www-form-urlencoded"},
    {"data": '{"username":"alice","pin":"1234"}', "content_type": "text/plain"},
])
def test_non_json_posts_rejected(tmp_path, kwargs):
    app = make_app(tmp_path)
    c = app.test_client()
    signup(c)
    assert c.post("/api/login", **kwargs).status_code == 415
    assert c.post("/api/entries", **kwargs).status_code == 415
    assert c.post("/api/logout", **kwargs).status_code in (200, 415)


def test_spoofed_ip_header_ignored_off_vercel(tmp_path, monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    app = make_app(tmp_path)
    for n in range(auth.SIGNUPS_PER_IP_PER_DAY):
        app.test_client().post("/api/signup", json={"username": f"u{n}x", "pin": "1234"},
                               headers={"X-Real-IP": f"99.0.0.{n}"})
    resp = app.test_client().post("/api/signup", json={"username": "sneaky", "pin": "1234"},
                                  headers={"X-Real-IP": "99.9.9.9"})
    assert resp.status_code == 429


def test_proxy_ip_header_trusted_on_vercel(tmp_path, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    app = make_app(tmp_path)
    for n in range(auth.SIGNUPS_PER_IP_PER_DAY + 2):
        r = app.test_client().post("/api/signup", json={"username": f"v{n}x", "pin": "1234"},
                                   headers={"X-Real-IP": f"98.0.0.{n}"})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Hostile and malformed input
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text,code", [
    ("x" * 2000, 201), ("x" * 2001, 400), ("   \n\t ", 400), ("🍜 ラーメン نودلز ‮", 201),
    ("'; DROP TABLE entries; --", 201), ("<img src=x onerror=alert(1)>", 201), ("a\x00b", 201),
])
def test_entry_text_edge_cases(tmp_path, text, code):
    c = make_app(tmp_path).test_client()
    signup(c)
    assert c.post("/api/entries", json={"text": text}).status_code == code
    if code == 201:
        stars = c.get("/api/stars").get_json()["stars"]
        assert stars[-1]["text"] == text.strip()  # stored and returned verbatim


@pytest.mark.parametrize("body", ["[1,2]", "null", '"text"', '{"text": 5}', '{"text": null}', '{"text": {"a": 1}}', "{bad json"])
def test_malformed_entry_bodies_never_500(tmp_path, body):
    c = make_app(tmp_path).test_client()
    signup(c)
    resp = c.post("/api/entries", data=body, content_type="application/json")
    assert resp.status_code < 500


@pytest.mark.parametrize("payload", [
    {"entry_id": "abc"}, {"entry_id": None}, {"entry_id": -1}, {"entry_id": 10**30},
    {"entry_id": 1, "path": "notalist"}, {"entry_id": 1, "path": [{"x": 1}] * 50},
])
def test_explore_bad_payloads_never_500(tmp_path, payload):
    c = make_app(tmp_path, ai=FakeAI()).test_client()
    signup(c)
    c.post("/api/entries", json={"text": "I like to eat noodles"})
    assert c.post("/api/explore", json=payload).status_code < 500


def test_explore_path_is_bounded(tmp_path):
    ai = FakeAI()
    seen = {}
    real = ai.explore
    ai.explore = lambda subject, category, path: (seen.setdefault("path", path), real(subject, category, path))[1]
    c = make_app(tmp_path, ai=ai).test_client()
    signup(c)
    eid = c.post("/api/entries", json={"text": "I like to eat noodles"}).get_json()["id"]
    c.post("/api/explore", json={"entry_id": eid, "path": ["y" * 10000] * 40})
    assert len(seen["path"]) == app_module.MAX_PATH_DEPTH and all(len(p) == 120 for p in seen["path"])


@pytest.mark.parametrize("username", ["a'--", "admin\"; DROP", "../../etc", "ÄLICE", "x" * 25, ""])
def test_hostile_usernames_rejected_cleanly(tmp_path, username):
    c = make_app(tmp_path).test_client()
    assert signup(c, username).status_code == 400
    assert login(c, username).status_code == 401


# ---------------------------------------------------------------------------
# Partial failures: enrich must be resumable and idempotent
# ---------------------------------------------------------------------------
def test_enrich_resumes_after_quota_runs_out_mid_way(tmp_path, monkeypatch):
    ai = FakeAI({"pad thai": [("noodles", "made_from")]})
    c = make_app(tmp_path, ai=ai).test_client()
    signup(c)
    n = c.post("/api/entries", json={"text": "I like to eat noodles"}).get_json()["id"]
    c.post(f"/api/entries/{n}/enrich", json={})  # 1 call
    monkeypatch.setattr(app_module, "AI_DAILY_LIMIT", 2)
    p = c.post("/api/entries", json={"text": "Made pad thai tonight"}).get_json()["id"]
    assert c.post(f"/api/entries/{p}/enrich", json={}).status_code == 429  # analyzed, then out of quota
    monkeypatch.setattr(app_module, "AI_DAILY_LIMIT", 100)
    assert c.post(f"/api/entries/{p}/enrich", json={}).get_json()["links"] == 1
    # repeated enrich calls never duplicate links
    for _ in range(3):
        c.post(f"/api/entries/{p}/enrich", json={})
    assert sum(1 for e in c.get("/api/stars").get_json()["edges"] if e["type"] == "ai") == 1


def test_hospital_check_outage_is_retried_later(tmp_path):
    ai = FakeAI({"cleveland clinic": [("coronary heart disease", "treated_at")]})
    calls = {"n": 0}
    real = ai.verify_hospital

    def flaky(*a):
        calls["n"] += 1
        if calls["n"] == 1:
            raise AIError("Couldn't reach Wikipedia")
        return real(*a)

    ai.verify_hospital = flaky
    c = make_app(tmp_path, ai=ai).test_client()
    signup(c)
    d = c.post("/api/entries", json={"text": "My dad has heart disease"}).get_json()["id"]
    c.post(f"/api/entries/{d}/enrich", json={})
    h = c.post("/api/entries", json={"text": "Visited Cleveland Clinic for a checkup"}).get_json()["id"]
    assert c.post(f"/api/entries/{h}/enrich", json={}).get_json()["links"] == 0  # outage: skipped for now
    assert c.post(f"/api/entries/{h}/enrich", json={}).get_json()["links"] == 1  # retried and linked
    assert c.post(f"/api/entries/{h}/enrich", json={}).get_json()["links"] == 0  # done: no more calls


def test_hospital_verdict_cached_across_users(tmp_path):
    ai = FakeAI({"cleveland clinic": [("coronary heart disease", "treated_at")]}, verified=False)
    app = make_app(tmp_path, ai=ai)
    for n, name in enumerate(["alice", "bob"]):
        c = app.test_client()
        signup(c, name, ip=f"10.9.0.{n}")
        d = c.post("/api/entries", json={"text": "My dad has heart disease"}).get_json()["id"]
        c.post(f"/api/entries/{d}/enrich", json={})
        h = c.post("/api/entries", json={"text": "Visited Cleveland Clinic for a checkup"}).get_json()["id"]
        c.post(f"/api/entries/{h}/enrich", json={})
    assert ai.verify_calls == 1  # the negative verdict was cached and reused


def test_relate_with_bogus_ids_is_ignored(tmp_path):
    class Liar(FakeAI):
        def relate(self, new, others):
            return [{"other_id": 999999, "kind": "related", "reason": "made up"}]

    ai = Liar()
    c = make_app(tmp_path, ai=ai).test_client()
    signup(c)
    a = c.post("/api/entries", json={"text": "I like to eat noodles"}).get_json()["id"]
    c.post(f"/api/entries/{a}/enrich", json={})
    b = c.post("/api/entries", json={"text": "Made pad thai tonight"}).get_json()["id"]
    # the real KnowledgeAI.relate filters ids; a raw bogus id must not crash the endpoint either
    assert c.post(f"/api/entries/{b}/enrich", json={}).status_code < 500


def test_big_galaxy_stays_fast(tmp_path):
    ai = FakeAI()
    app = make_app(tmp_path, ai=ai)
    c = app.test_client()
    signup(c)
    with Storage(app.config["DB_PATH"], user_id=1) as s:
        ids = s.add_many([f"thought number {n} about topic {n % 17} and noodles {n % 5}" for n in range(300)])
        for i in ids:
            s.set_analysis(i, {"category": "other", "subject": f"t{i}", "linked": True})
        for i in range(0, 290, 3):
            s.add_link(ids[i], ids[i + 1], "related", "r")
    start = time.time()
    g = c.get("/api/stars").get_json()
    assert g["count"] == 300 and time.time() - start < 15


# ---------------------------------------------------------------------------
# Free-provider chain against a real HTTP server
# ---------------------------------------------------------------------------
class _Handler(BaseHTTPRequestHandler):
    script: dict = {}
    log: list = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        name = self.path.split("/")[1]
        _Handler.log.append((name, "response_format" in body, self.headers.get("Authorization")))
        status, payload = _Handler.script[name](body)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload.encode())


@pytest.fixture
def fake_llm_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _Handler.log = []
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _chat(content):
    return json.dumps({"choices": [{"message": {"content": content}}]})


SCHEMA = {"type": "object", "properties": {"kind": {"type": "string", "enum": ["choices", "detail"]},
                                           "n": {"type": "integer"},
                                           "items": {"type": "array", "items": {"type": "string"}}},
          "required": ["kind", "n", "items"], "additionalProperties": False}


def test_provider_chain_falls_through_rate_limits_and_json_mode_errors(fake_llm_server):
    _Handler.script = {
        "a": lambda body: (429, '{"error": "rate limited"}'),
        "b": lambda body: (400, '{"error":"json mode unsupported"}') if "response_format" in body
        else (200, _chat('Sure! Here you go:\n```json\n{"kind": "Choices", "n": "7", "items": ["x", null, 3]}\n```')),
        "c": lambda body: (200, _chat('{"kind":"detail","n":1,"items":[]}')),
    }
    providers = [FreeProvider(n, f"{fake_llm_server}/{n}", f"key-{n}", "m") for n in "abc"]
    ai = KnowledgeAI(free_providers=providers)
    out = ai._json("sys", "user", SCHEMA, "low")
    assert out == {"kind": "choices", "n": 7, "items": ["x", "3"]}
    assert [(n, rf) for n, rf, _ in _Handler.log] == [("a", True), ("b", True), ("b", False)]
    assert _Handler.log[0][2] == "Bearer key-a"  # each provider gets its own key


def test_all_free_providers_down_without_claude(fake_llm_server, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _Handler.script = {"a": lambda b: (503, "{}"), "b": lambda b: (200, _chat("I cannot help with that."))}
    providers = [FreeProvider(n, f"{fake_llm_server}/{n}", "k", "m") for n in "ab"]
    with pytest.raises(AIError) as e:
        KnowledgeAI(free_providers=providers)._json("s", "u", SCHEMA, "low")
    assert "free AI services" in str(e.value)


def test_free_chain_falls_back_to_claude(fake_llm_server):
    from types import SimpleNamespace as NS

    _Handler.script = {"a": lambda b: (500, "{}")}
    reply = NS(stop_reason="end_turn", content=[NS(type="text", text='{"kind":"detail","n":2,"items":["z"]}')])
    claude = NS(beta=NS(messages=NS(create=lambda **k: reply)))
    ai = KnowledgeAI(client=claude, free_providers=[FreeProvider("a", f"{fake_llm_server}/a", "k", "m")])
    assert ai._json("s", "u", SCHEMA, "low")["items"] == ["z"]


def test_unreachable_provider_is_skipped():
    dead = FreeProvider("dead", "http://127.0.0.1:9", "k", "m")
    with pytest.raises(ProviderError):
        dead.complete_json("s", "u", SCHEMA)


@pytest.mark.parametrize("raw,expected", [
    ('{"a": 1}', {"a": 1}),
    ('```json\n{"a": "}"}\n```', {"a": "}"}),
    ('Here it is: {"a": {"b": [1, 2]}} hope that helps', {"a": {"b": [1, 2]}}),
])
def test_parse_json_object(raw, expected):
    assert parse_json_object(raw) == expected


@pytest.mark.parametrize("raw", ["", "no json here", "[1, 2, 3]", "{broken", '"just a string"'])
def test_parse_json_object_rejects_junk(raw):
    with pytest.raises(ProviderError):
        parse_json_object(raw)


def test_conform_never_trusts_shapes():
    from mindgalaxy.ai import ANALYZE_SCHEMA, EXPLORE_SCHEMA, RELATE_SCHEMA

    junk = {"category": "FOOD", "subject": None, "symptoms": "cough", "extra": "ignored"}
    out = conform(junk, ANALYZE_SCHEMA)
    assert out["category"] == "food" and out["subject"] == "" and out["symptoms"] == []
    assert set(out) == set(ANALYZE_SCHEMA["properties"])
    assert conform({"category": "spaceship"}, ANALYZE_SCHEMA)["category"] == "other"
    assert conform({"links": [{"other_id": "12", "kind": "friends"}]}, RELATE_SCHEMA) == \
        {"links": [{"other_id": 12, "kind": "related", "reason": ""}]}
    node = conform({"kind": "detail", "items": [{"name": "Pho", "facts": [{"label": "x"}]}]}, EXPLORE_SCHEMA)
    assert node["items"][0]["facts"] == [{"label": "x", "value": ""}] and node["items"][0]["steps"] == []


def test_relate_drops_ids_not_offered():
    class Canned(KnowledgeAI):
        def _json(self, *a, **k):
            return {"links": [{"other_id": 3, "kind": "related", "reason": "ok"},
                              {"other_id": 3, "kind": "related", "reason": "dup"},
                              {"other_id": -1, "kind": "related", "reason": "coerced junk"},
                              {"other_id": 42, "kind": "related", "reason": "not offered"},
                              {"other_id": 4, "kind": "related", "reason": ""}]}

    others = [{"id": i, "category": "other", "subject": "s", "text": "t"} for i in (3, 4)]
    links = Canned(free_providers=[]).relate({"id": 9, "category": "other", "subject": "s", "text": "t"}, others)
    assert [l["other_id"] for l in links] == [3]


# ---------------------------------------------------------------------------
# Free hospital verification (Wikipedia route)
# ---------------------------------------------------------------------------
class _Verdict(KnowledgeAI):
    def __init__(self, verdict):
        super().__init__(free_providers=[FreeProvider("x", "http://unused", "k", "m")])
        self.verdict = verdict

    def _json(self, *a, **k):
        return self.verdict


PAGE = {"title": "Cleveland Clinic", "url": "https://en.wikipedia.org/wiki/Cleveland_Clinic",
        "text": "... ranked #1 for cardiology ...", "website": "https://my.clevelandclinic.org/"}


def test_wikipedia_route_uses_wikimedia_urls_only(monkeypatch):
    monkeypatch.setattr("mindgalaxy.ai.wikipedia_evidence", lambda h, l: PAGE)
    out = _Verdict({"same_hospital": True, "recognized": True, "why": "Ranked #1", "department": "Heart"}) \
        .verify_hospital("Cleveland Clinic", "Ohio", "heart disease")
    assert out["find_doctor_url"] == PAGE["website"] and out["evidence_urls"] == [PAGE["url"]]


@pytest.mark.parametrize("verdict", [
    {"same_hospital": False, "recognized": True, "why": "", "department": ""},
    {"same_hospital": True, "recognized": False, "why": "", "department": ""},
])
def test_wikipedia_route_rejects_wrong_page_or_no_evidence(monkeypatch, verdict):
    monkeypatch.setattr("mindgalaxy.ai.wikipedia_evidence", lambda h, l: PAGE)
    assert _Verdict(verdict).verify_hospital("Cleveland Clinic", "", "flu") is None


def test_wikipedia_route_no_article(monkeypatch):
    monkeypatch.setattr("mindgalaxy.ai.wikipedia_evidence", lambda h, l: None)
    assert _Verdict({}).verify_hospital("Tiny Clinic", "", "flu") is None


def test_wikipedia_outage_raises_retryable_error(monkeypatch):
    def down(h, l):
        raise ProviderError("down")

    monkeypatch.setattr("mindgalaxy.ai.wikipedia_evidence", down)
    with pytest.raises(AIError) as e:
        _Verdict({}).verify_hospital("X", "", "flu")
    assert not isinstance(e.value, QuotaError)


def test_providers_from_env(monkeypatch):
    for _, key, *_ in free_ai.KNOWN_PROVIDERS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GEMINI_API_KEY", "m")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-custom")
    monkeypatch.setenv("FREE_AI_BASE_URL", "http://x/v1")
    monkeypatch.setenv("FREE_AI_MODEL", "local")
    names = [(p.name, p.model) for p in free_ai.providers_from_env()]
    assert names == [("Gemini", "gemini-custom"), ("Groq", "openai/gpt-oss-120b"), ("Custom", "local")]
    ai = KnowledgeAI()
    assert ai.enabled and ai.name.startswith("free:Gemini/gemini-custom")


# ---------------------------------------------------------------------------
# Storage resilience
# ---------------------------------------------------------------------------
def test_migration_is_idempotent_and_keeps_data(tmp_path):
    p = tmp_path / "m.db"
    for n in range(4):
        with Storage(p, user_id=7) as s:
            s.add(f"entry {n}")
    with Storage(p, user_id=7) as s:
        assert s.count() == 4
        cols = [r[1] for r in s.conn.execute("PRAGMA table_info(entries)").fetchall()]
        assert cols.count("user_id") == 1 and cols.count("analysis") == 1


def test_keyless_provider_sends_no_authorization_header(fake_llm_server):
    # anonymous free tiers reject requests carrying any Authorization header
    _Handler.script = {"anon": lambda body: (200, _chat('{"kind":"detail","n":0,"items":[]}'))}
    FreeProvider("anon", f"{fake_llm_server}/anon", "", "m").complete_json("s", "u", SCHEMA)
    assert _Handler.log[-1][2] is None
