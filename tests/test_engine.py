import datetime as dt

import pytest

from mindgalaxy.engine import Entry, build_galaxy


def make_entries(specs):
    """specs: list of (days_ago, text)."""
    now = dt.datetime(2026, 1, 1)
    out = []
    for i, (days_ago, text) in enumerate(specs, start=1):
        out.append(Entry(id=i, text=text, created_at=now - dt.timedelta(days=days_ago)))
    return out, now


def test_empty_galaxy():
    galaxy = build_galaxy([])
    assert galaxy["stars"] == []
    assert galaxy["edges"] == []
    assert galaxy["clusters"] == {}
    assert galaxy["count"] == 0


def test_single_entry():
    entries, now = make_entries([(0, "A single lonely thought about the sea.")])
    galaxy = build_galaxy(entries, now=now)
    assert galaxy["count"] == 1
    star = galaxy["stars"][0]
    assert star["id"] == 1
    assert star["cluster"] == 0
    assert 0.0 <= star["brightness"] <= 1.0
    assert star["novelty"] == 0.0  # nothing to compare against


def test_every_star_has_required_fields():
    specs = [(i, f"Entry number {i} about topic {'guitar' if i % 2 else 'novel writing'}") for i in range(20)]
    entries, now = make_entries(specs)
    galaxy = build_galaxy(entries, now=now)
    assert galaxy["count"] == 20
    required = {
        "id", "text", "created_at", "x", "y", "z", "cluster", "cluster_name",
        "cluster_status", "novelty", "brightness", "magnitude", "is_shooting_star",
    }
    for star in galaxy["stars"]:
        assert required.issubset(star.keys())
        assert isinstance(star["x"], float)
        assert isinstance(star["is_shooting_star"], bool)
        assert star["cluster_status"] in ("active", "dormant")


def test_novelty_is_bounded():
    specs = [(i, f"Random musings entry {i} " + ("apple " * (i % 5))) for i in range(15)]
    entries, now = make_entries(specs)
    galaxy = build_galaxy(entries, now=now)
    for star in galaxy["stars"]:
        assert 0.0 <= star["novelty"] <= 1.0


def test_brightness_decays_with_age():
    entries, now = make_entries([
        (0, "Fresh thought about the ocean and tides."),
        (400, "An old thought about the ocean and tides from long ago."),
    ])
    galaxy = build_galaxy(entries, now=now)
    fresh, old = galaxy["stars"][0], galaxy["stars"][1]
    assert fresh["brightness"] > old["brightness"]


def test_recent_frequent_theme_is_active_not_dormant():
    now = dt.datetime(2026, 1, 1)
    entries = [
        Entry(id=i, text="Guitar practice chord lesson today", created_at=now - dt.timedelta(days=d))
        for i, d in enumerate([1, 4, 8, 12, 16], start=1)
    ]
    galaxy = build_galaxy(entries, now=now)
    statuses = {c["status"] for c in galaxy["clusters"].values()}
    assert "active" in statuses


def test_abandoned_theme_is_flagged_dormant():
    now = dt.datetime(2026, 1, 1)
    # A steady cadence of "novel" entries that stopped 200 days ago...
    novel_entries = [
        Entry(id=i, text="Novel chapter draft about the lighthouse keeper Mireille",
              created_at=now - dt.timedelta(days=200 + d))
        for i, d in enumerate([0, 10, 20, 30, 40], start=1)
    ]
    # ...plus a completely different, currently-active theme so the novel
    # thread doesn't just become "the whole galaxy" (and so clustering has
    # more than one group to find).
    other_entries = [
        Entry(id=i + 10, text="Gym workout deadlift squat bench press session",
              created_at=now - dt.timedelta(days=d))
        for i, d in enumerate([1, 3, 5, 7, 9, 11, 13], start=1)
    ]
    galaxy = build_galaxy(novel_entries + other_entries, now=now)
    novel_star = next(s for s in galaxy["stars"] if "Mireille" in s["text"])
    assert novel_star["cluster_status"] == "dormant"


def test_outlier_entry_can_be_flagged_shooting_star():
    now = dt.datetime(2026, 1, 1)
    # A tight cluster of near-identical entries...
    entries = [
        Entry(id=i, text="Went for a gym workout and lifted weights today",
              created_at=now - dt.timedelta(days=i))
        for i in range(1, 15)
    ]
    # ...plus one wildly unrelated outlier.
    entries.append(Entry(
        id=99,
        text="Quantum entangled photons whisper secrets about the birth of spacetime itself",
        created_at=now,
    ))
    galaxy = build_galaxy(entries, now=now)
    outlier = next(s for s in galaxy["stars"] if s["id"] == 99)
    assert outlier["novelty"] > 0.5


def test_edges_reference_valid_star_indices():
    specs = [(i, f"Entry {i} about " + ("hiking trail" if i % 3 else "guitar chord")) for i in range(25)]
    entries, now = make_entries(specs)
    galaxy = build_galaxy(entries, now=now)
    n = galaxy["count"]
    for edge in galaxy["edges"]:
        assert 0 <= edge["source"] < n
        assert 0 <= edge["target"] < n
        assert edge["source"] != edge["target"]
        assert edge["type"] in ("constellation", "bridge")
        assert 0.0 <= edge["weight"] <= 1.0


def test_deterministic_output_for_same_input():
    specs = [(i, f"Entry {i} about " + ("hiking trail" if i % 3 else "guitar chord")) for i in range(20)]
    entries, now = make_entries(specs)
    g1 = build_galaxy(entries, now=now)
    g2 = build_galaxy(entries, now=now)
    assert [s["cluster"] for s in g1["stars"]] == [s["cluster"] for s in g2["stars"]]
    assert [round(s["x"], 6) for s in g1["stars"]] == [round(s["x"], 6) for s in g2["stars"]]
