import datetime as dt

import pytest

from mindgalaxy.engine import Entry, build_galaxy
from mindgalaxy.knowledge import detect_topics, solve_math
from mindgalaxy.knowledge_base import RELATIONS, TOPICS


@pytest.mark.parametrize("text,topic", [
    ("i love to cook", "food"), ("i like to eat", "food"),
    ("i love milk", "milk"), ("i need to buy milk", "milk"),
    ("i feel like buying a car", "car"), ("thinking of car", "car"),
    ("i need a watch", "watch"), ("lost track of time", "watch"),
    ("dreaming of a house", "house"), ("hospital visit today", "hospital"),
    ("school starts monday", "school"), ("applying to university", "university"),
    ("our marriage", "marriage"), ("my wife is amazing", "spouse"),
    ("we are pregnant", "pregnancy"), ("the birth of our son", "birth"),
    ("my child's first steps", "child"), ("new technology", "technology"),
    ("need a new phone", "phone"), ("staying healthy", "health"),
    ("i have a fever", "disease"), ("maths problem", "maths"), ("sexual health", "sex"),
])
def test_detect_primary_topic(text, topic):
    assert detect_topics(text)[0] == topic


@pytest.mark.parametrize("text", ["we watched a movie", "went home early", "birthday party", "I stayed up late"])
def test_no_false_positives(text):
    assert detect_topics(text) == []


@pytest.mark.parametrize("text,answer", [
    ("solve 2x + 3 = 11", "x = 4"),
    ("solve x^2 - 5x + 6 = 0", "x = 3 or x = 2"),
    ("solve 3y - 4 = 2y + 6", "y = 10"),
    ("what is 15% of 240", "36"),
    ("sqrt(144) + 3^2", "21"),
    ("what is 7 times 8", "56"),
])
def test_solve_math(text, answer):
    assert solve_math(text)["answer"] == answer


@pytest.mark.parametrize("text", ["ran 5-10 miles today", "meeting at 9/24", "i love milk"])
def test_math_not_triggered_by_ordinary_numbers(text):
    assert solve_math(text) is None


def test_knowledge_base_integrity():
    for tid, t in TOPICS.items():
        assert t["label"] and t["facets"], tid
        for f in t["facets"]:
            assert f["name"] and f["items"], (tid, f["name"])
    for a, b, why in RELATIONS:
        assert a in TOPICS and b in TOPICS and why


def test_galaxy_carries_topics_and_interconnections():
    now = dt.datetime(2026, 9, 1)
    entries = [Entry(1, "i love milk", now), Entry(2, "i like to cook", now),
               Entry(3, "thinking of buying a car", now)]
    g = build_galaxy(entries, now=now)
    assert {"milk", "food", "car"} <= set(g["topics"])
    assert g["stars"][0]["topics"][0] == "milk"
    topic_edges = [e for e in g["edges"] if e["type"] == "topic"]
    # milk <-> cooking share no words but are related topics
    assert any({e["source"], e["target"]} == {0, 1} for e in topic_edges)
    assert all(e.get("reason") for e in topic_edges)


def test_single_star_gets_knowledge():
    g = build_galaxy([Entry(1, "solve 2x + 3 = 11", dt.datetime(2026, 9, 1))], now=dt.datetime(2026, 9, 1))
    star = g["stars"][0]
    assert star["math"]["answer"] == "x = 4"
    assert "maths" in star["topics"] and "maths" in g["topics"]
