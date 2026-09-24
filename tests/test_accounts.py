import sqlite3

import pytest

from mindgalaxy import auth
from mindgalaxy.app import create_app
from mindgalaxy.storage import Storage


@pytest.fixture
def app(tmp_path):
    app = create_app(db_path=str(tmp_path / "multi.db"), multi_user=True, secret_key="test-secret")
    app.config["TESTING"] = True
    return app


def _signup(client, username="alice", pin="1234", ip="1.1.1.1"):
    return client.post("/api/signup", json={"username": username, "pin": pin}, headers={"X-Real-IP": ip})


def _login(client, username="alice", pin="1234", ip="1.1.1.1"):
    return client.post("/api/login", json={"username": username, "pin": pin}, headers={"X-Real-IP": ip})


def test_multi_user_requires_secret_key(tmp_path):
    with pytest.raises(RuntimeError):
        create_app(db_path=str(tmp_path / "x.db"), multi_user=True)


def test_signed_out_visitors_are_sent_to_login(app):
    c = app.test_client()
    assert c.get("/").status_code == 302
    assert c.get("/login").status_code == 200
    assert c.get("/api/stars").status_code == 401
    assert c.post("/api/entries", json={"text": "hi"}).status_code == 401


def test_signup_then_use_galaxy(app):
    c = app.test_client()
    resp = _signup(c)
    assert resp.status_code == 200
    assert resp.get_json()["username"] == "alice"
    assert c.get("/api/me").get_json()["username"] == "alice"
    assert c.post("/api/entries", json={"text": "I like to eat noodles"}).status_code == 201
    assert c.get("/api/stars").get_json()["count"] == 1
    assert c.get("/").status_code == 200


@pytest.mark.parametrize("username,pin", [
    ("al", "1234"), ("has space", "1234"), ("alice", "123"), ("alice", "12345"), ("alice", "12a4"),
])
def test_signup_validation(app, username, pin):
    assert _signup(app.test_client(), username, pin).status_code == 400


def test_duplicate_username_rejected_case_insensitively(app):
    _signup(app.test_client(), "Alice")
    assert _signup(app.test_client(), "alice", "9999").status_code == 409


def test_login_and_logout(app):
    _signup(app.test_client())
    c = app.test_client()
    assert _login(c, pin="0000").status_code == 401
    assert _login(c).status_code == 200
    assert c.get("/api/stars").status_code == 200
    c.post("/api/logout", json={})
    assert c.get("/api/stars").status_code == 401


def test_unknown_user_gets_same_error_as_wrong_pin(app):
    _signup(app.test_client())
    a = _login(app.test_client(), "nobody", "1234").get_json()["error"]
    b = _login(app.test_client(), "alice", "9999").get_json()["error"]
    assert a == b


def test_account_locks_after_five_wrong_pins(app):
    _signup(app.test_client())
    c = app.test_client()
    for _ in range(4):
        assert _login(c, pin="0000").status_code == 401
    assert _login(c, pin="0000").status_code == 423
    # even the right passkey is refused while locked
    assert _login(c).status_code == 423


def test_ip_is_throttled_across_accounts(app):
    c = app.test_client()
    for n in range(auth.IP_FAILURES_PER_HOUR):
        _login(c, f"user{n:03d}", "0000", ip="6.6.6.6")
    assert _login(c, "user999", "0000", ip="6.6.6.6").status_code == 429
    assert _login(c, "user999", "0000", ip="7.7.7.7").status_code == 401


def test_signups_per_ip_are_limited(app):
    for n in range(auth.SIGNUPS_PER_IP_PER_DAY):
        assert _signup(app.test_client(), f"user{n}", ip="2.2.2.2").status_code == 200
    assert _signup(app.test_client(), "oneTooMany", ip="2.2.2.2").status_code == 429


def test_each_user_only_sees_their_own_galaxy(app):
    a, b = app.test_client(), app.test_client()
    _signup(a, "alice")
    _signup(b, "bob", "4321", ip="3.3.3.3")
    a.post("/api/entries", json={"text": "Alice's secret thought"})
    b.post("/api/entries", json={"text": "Bob's thought"})
    assert [s["text"] for s in a.get("/api/stars").get_json()["stars"]] == ["Alice's secret thought"]
    assert [s["text"] for s in b.get("/api/stars").get_json()["stars"]] == ["Bob's thought"]


def test_writes_must_be_json(app):
    c = app.test_client()
    _signup(c)
    resp = c.post("/api/entries", data={"text": "form post"})
    assert resp.status_code == 415


def test_pins_are_hashed(tmp_path):
    stored = auth.hash_pin("1234")
    assert "1234" not in stored
    assert auth.check_pin("1234", stored)
    assert not auth.check_pin("4321", stored)


def test_old_database_is_migrated(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE entries (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, created_at TEXT NOT NULL)")
    conn.execute("INSERT INTO entries (text, created_at) VALUES ('old thought', '2026-01-01T00:00:00')")
    conn.commit()
    conn.close()
    with Storage(path) as store:
        assert [e.text for e in store.all_entries()] == ["old thought"]
    with Storage(path, user_id=1) as store:
        assert store.all_entries() == []
