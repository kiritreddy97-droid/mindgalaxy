"""Nearby places with Google ratings: off without a key, capped, never stored."""
import json

import pytest

from mindgalaxy import places
from mindgalaxy.app import create_app

from .test_ai_features import FakeAI
from .test_social import user

GOOGLE_REPLY = {"places": [
    {"displayName": {"text": "City Eye Hospital"}, "location": {"latitude": 17.39, "longitude": 78.49},
     "rating": 4.6, "userRatingCount": 2150, "formattedAddress": "Road 1, Hyderabad",
     "googleMapsUri": "https://maps.google.com/?cid=1", "currentOpeningHours": {"openNow": True},
     "primaryTypeDisplayName": {"text": "Eye care center"},
     "reviews": [
         {"rating": 5, "text": {"text": "Great doctors"}, "relativePublishTimeDescription": "a month ago",
          "authorAttribution": {"displayName": "Asha", "uri": "https://www.google.com/maps/contrib/1"}},
         {"rating": 1, "text": {"text": "Waited 3 hours"}, "relativePublishTimeDescription": "2 weeks ago",
          "authorAttribution": {"displayName": "Ravi"}}]},
    {"displayName": {"text": "Closed Clinic"}, "location": {"latitude": 17.38, "longitude": 78.48},
     "businessStatus": "CLOSED_PERMANENTLY"},
    {"displayName": {"text": "Quick Vision"}, "location": {"latitude": 17.40, "longitude": 78.50},
     "rating": 1.8, "userRatingCount": 40},
]}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    places._cache.clear()
    a = create_app(db_path=str(tmp_path / "p.db"), multi_user=True, secret_key="s", ai=FakeAI())
    a.config["TESTING"] = True
    return a


def ask(c, **kw):
    body = {"kind": "health", "query": "eye hospital", "lat": 17.3851, "lon": 78.4867, **kw}
    return c.post("/api/nearby", json=body)


def test_off_without_a_key(app):
    c = user(app, "asha1")
    assert ask(c).get_json() == {"available": False, "reason": "off"}
    assert app.test_client().get("/api/health").get_json()["places"] is False


def test_needs_sign_in(app, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "k")
    assert app.test_client().post("/api/nearby", json={}).status_code == 401


def test_ratings_reviews_and_rounding(app, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "test-key")
    seen = {}

    def fake_fetch(req):
        seen["body"] = json.loads(req.data)
        seen["key"] = req.get_header("X-goog-api-key")
        return GOOGLE_REPLY
    monkeypatch.setattr(places, "search", lambda key, q, lat, lon, r: places.normalise(fake_fetch(_Req(key, q, lat, lon)), lat, lon))
    r = ask(user(app, "asha2")).get_json()
    assert r["available"] is True
    names = [p["name"] for p in r["places"]]
    assert names == ["City Eye Hospital", "Quick Vision"]           # permanently closed places are dropped
    best = r["places"][0]
    assert best["rating"] == 4.6 and best["count"] == 2150 and best["open_now"] is True
    assert [x["rating"] for x in best["reviews"]] == [5, 1]          # bad reviews are kept, not filtered out
    assert best["reviews"][1]["text"] == "Waited 3 hours"
    assert seen["body"]["locationBias"]["circle"]["center"] == {"latitude": 17.385, "longitude": 78.487}   # ~100 m
    assert seen["key"] == "test-key"


class _Req:
    def __init__(self, key, q, lat, lon):
        import urllib.request
        r = urllib.request.Request(places.ENDPOINT, data=json.dumps({"textQuery": q, "locationBias": {"circle": {
            "center": {"latitude": lat, "longitude": lon}}}}).encode(), headers={"X-Goog-Api-Key": key})
        self.data, self.get_header = r.data, r.get_header


def test_daily_and_monthly_caps(app, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "k")
    calls = []
    monkeypatch.setattr(places, "search", lambda *a: calls.append(a) or [])
    monkeypatch.setattr("mindgalaxy.app.PLACES_DAILY_PER_USER", 2)
    monkeypatch.setattr("mindgalaxy.app.PLACES_MONTHLY_CAP", 3)
    a, b = user(app, "capper1"), user(app, "capper2")
    assert ask(a, lat=10).get_json()["available"] and ask(a, lat=11).get_json()["available"]
    assert ask(a, lat=12).get_json() == {"available": False, "reason": "daily"}
    assert ask(b, lat=13).get_json()["available"]
    assert ask(b, lat=14).get_json() == {"available": False, "reason": "monthly"}
    assert len(calls) == 3


def test_bad_input(app, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "k")
    c = user(app, "asha3")
    assert ask(c, lat="north").status_code == 400
    assert ask(c, lat=123).status_code == 400
    assert ask(c, query="").status_code == 400


def test_google_errors_fall_back_quietly(app, monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "k")

    def boom(*a):
        raise places.PlacesError("Google Places error 403: API not enabled")
    monkeypatch.setattr(places, "search", boom)
    assert ask(user(app, "asha4")).get_json() == {"available": False, "reason": "error"}


def test_search_builds_the_request_and_caches(monkeypatch):
    places._cache.clear()
    sent = []

    def fetch(req):
        sent.append(req)
        return GOOGLE_REPLY
    got = places.search("key-1", "eye hospital", 17.385, 78.487, 10000, fetch=fetch)
    again = places.search("key-1", "eye hospital", 17.385, 78.487, 10000, fetch=fetch)
    assert got == again and len(sent) == 1                       # second lookup served from the 10-minute cache
    req = sent[0]
    assert req.full_url == places.ENDPOINT and req.get_method() == "POST"
    assert req.get_header("X-goog-api-key") == "key-1"
    assert "places.reviews" in req.get_header("X-goog-fieldmask") and "places.rating" in req.get_header("X-goog-fieldmask")
    assert json.loads(req.data)["textQuery"] == "eye hospital"
