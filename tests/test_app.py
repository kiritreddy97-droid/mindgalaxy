import pytest

from mindgalaxy.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "app_test.db"))
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_index_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"<html" in resp.data.lower()


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_stars_empty_initially(client):
    resp = client.get("/api/stars")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 0


def test_add_entry_then_appears_in_stars(client):
    resp = client.post("/api/entries", json={"text": "A brand new thought about clouds"})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["count"] == 1

    resp = client.get("/api/stars")
    data = resp.get_json()
    assert data["count"] == 1
    assert data["stars"][0]["text"] == "A brand new thought about clouds"


def test_add_entry_rejects_empty_text(client):
    resp = client.post("/api/entries", json={"text": "   "})
    assert resp.status_code == 400
