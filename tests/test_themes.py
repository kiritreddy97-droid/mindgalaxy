"""Constellations follow what a thought is about, not just its words."""
import datetime as dt

from mindgalaxy.app import theme_hint
from mindgalaxy.engine import Entry, build_galaxy


def _entries(texts):
    now = dt.datetime(2026, 9, 27, 12)
    return [Entry(i + 1, t, now - dt.timedelta(hours=i)) for i, t in enumerate(texts)]


def test_small_galaxy_keeps_health_apart_from_food():
    entries = _entries(["Famous chicken curry in Hyderabad", "I love chicken curry", "I WISH MY VISION RECOVERS SOON"])
    hints = {1: theme_hint({"category": "food", "subject": "chicken curry"}),
             2: theme_hint({"category": "food", "subject": "chicken curry"}),
             3: theme_hint({"category": "symptom", "subject": "vision loss"})}
    stars = {s["id"]: s for s in build_galaxy(entries, hints=hints)["stars"]}
    assert stars[1]["cluster"] == stars[2]["cluster"]
    assert stars[3]["cluster"] != stars[1]["cluster"]
    assert "Curry" not in stars[3]["cluster_name"]


def test_hints_never_invent_lines():
    entries = _entries(["pizza tonight", "sushi for lunch", "tacos on friday", "ramen at midnight",
                        "burgers with dad", "pancakes this morning"])
    hints = {e.id: theme_hint({"category": "food", "subject": "meal"}) for e in entries}
    edges = build_galaxy(entries, hints=hints)["edges"]
    plain = build_galaxy(entries)["edges"]
    assert len(edges) == len(plain)   # lines still come only from shared words


def test_without_hints_nothing_changes():
    entries = _entries(["guitar practice", "guitar chords", "running shoes"])
    assert build_galaxy(entries)["stars"][0]["cluster"] == build_galaxy(entries, hints={})["stars"][0]["cluster"]
