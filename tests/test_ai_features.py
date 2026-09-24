"""Claude-powered features, exercised against a fake model so tests run offline."""
import pytest

from mindgalaxy import app as app_module
from mindgalaxy.ai import KnowledgeAI
from mindgalaxy.app import create_app, link_allowed

ANALYSES = {
    "I like to eat noodles": {"category": "food", "subject": "noodles"},
    "Made pad thai tonight": {"category": "food", "subject": "pad thai"},
    "I have chest pain and feel breathless": {"category": "symptom", "subject": "chest pain"},
    "My dad has heart disease": {"category": "disease", "subject": "coronary heart disease"},
    "Visited Cleveland Clinic for a checkup": {"category": "hospital", "subject": "cleveland clinic",
                                               "hospital_name": "Cleveland Clinic", "hospital_location": "Ohio, USA"},
    "My cousin works at General Hospital": {"category": "hospital", "subject": "general hospital",
                                            "hospital_name": "General Hospital", "hospital_location": ""},
}


class FakeAI(KnowledgeAI):
    def __init__(self, relate_links=None, verified=True):
        super().__init__(client=object(), model="fake-model")
        self.relate_links = relate_links or {}
        self.verified = verified
        self.explore_calls = 0
        self.verify_calls = 0

    def analyze(self, text):
        base = {"summary": text, "symptoms": [], "conditions": [], "hospital_name": "", "hospital_location": ""}
        return {**base, **ANALYSES[text]}

    def explore(self, subject, category, path):
        self.explore_calls += 1
        if len(path) < 2:
            return {"heading": subject, "kind": "choices", "prompt": "Pick one",
                    "choices": [{"label": "Japan", "blurb": "Ramen, udon, soba"}], "items": [], "note": ""}
        return {"heading": "Dishes", "kind": "detail", "prompt": "", "choices": [], "note": "",
                "items": [{"name": "Tonkotsu ramen", "origin": "Fukuoka, Japan", "summary": "Pork-bone broth",
                           "facts": [], "ingredients": ["noodles"], "steps": ["Boil"], "steps_label": "Recipe"}]}

    def relate(self, new, others):
        wanted = self.relate_links.get(new["subject"], [])
        by_subject = {o["subject"]: o["id"] for o in others}
        return [{"other_id": by_subject[s], "kind": k, "reason": f"{new['subject']} / {s}"}
                for s, k in wanted if s in by_subject]

    def verify_hospital(self, hospital, location, condition):
        self.verify_calls += 1
        if not self.verified:
            return None
        return {"hospital": hospital, "location": location, "condition": condition, "why": "Top-ranked heart centre",
                "department": "Heart, Vascular & Thoracic Institute",
                "find_doctor_url": "https://my.clevelandclinic.org/staff", "evidence_urls": ["https://example.org/rank"]}


def _client(tmp_path, ai):
    app = create_app(db_path=str(tmp_path / "ai.db"), multi_user=True, secret_key="s", ai=ai)
    c = app.test_client()
    c.post("/api/signup", json={"username": "alice", "pin": "1234"})
    return c


def _add(c, text):
    entry_id = c.post("/api/entries", json={"text": text}).get_json()["id"]
    assert c.post(f"/api/entries/{entry_id}/enrich", json={}).status_code == 200
    return entry_id


def _edges(c):
    g = c.get("/api/stars").get_json()
    ids = [s["id"] for s in g["stars"]]
    return g, [(ids[e["source"]], ids[e["target"]], e) for e in g["edges"]]


def test_link_rules():
    assert link_allowed("symptom_of", "symptom", "disease")
    assert not link_allowed("symptom_of", "symptom", "food")
    assert link_allowed("treated_at", "hospital", "disease")
    assert not link_allowed("treated_at", "hospital", "symptom")
    assert not link_allowed("related", "hospital", "disease")
    assert link_allowed("same_subject", "hospital", "hospital")
    assert link_allowed("made_from", "food", "food")


def test_explore_drills_down_and_is_cached(tmp_path):
    ai = FakeAI()
    c = _client(tmp_path, ai)
    entry_id = _add(c, "I like to eat noodles")
    first = c.post("/api/explore", json={"entry_id": entry_id, "path": []}).get_json()
    assert first["subject"] == "noodles" and first["node"]["kind"] == "choices"
    deep = c.post("/api/explore", json={"entry_id": entry_id, "path": ["Japan", "Wheat noodles"]}).get_json()
    assert deep["node"]["items"][0]["origin"] == "Fukuoka, Japan"
    c.post("/api/explore", json={"entry_id": entry_id, "path": []})
    assert ai.explore_calls == 2  # the repeat came from the cache


def test_explore_cache_is_shared_but_entries_are_private(tmp_path):
    ai = FakeAI()
    app = create_app(db_path=str(tmp_path / "ai.db"), multi_user=True, secret_key="s", ai=ai)
    a, b = app.test_client(), app.test_client()
    a.post("/api/signup", json={"username": "alice", "pin": "1234"})
    b.post("/api/signup", json={"username": "bob", "pin": "1234"}, headers={"X-Real-IP": "9.9.9.9"})
    a_id = _add(a, "I like to eat noodles")
    b_id = _add(b, "I like to eat noodles")
    a.post("/api/explore", json={"entry_id": a_id, "path": []})
    b.post("/api/explore", json={"entry_id": b_id, "path": []})
    assert ai.explore_calls == 1
    # bob can't explore (or even see) alice's thought
    assert b.post("/api/explore", json={"entry_id": a_id, "path": []}).status_code == 404


def test_food_links_are_drawn(tmp_path):
    ai = FakeAI({"pad thai": [("noodles", "made_from")]})
    c = _client(tmp_path, ai)
    n = _add(c, "I like to eat noodles")
    p = _add(c, "Made pad thai tonight")
    _, edges = _edges(c)
    assert any({a, b} == {n, p} and e["type"] == "ai" for a, b, e in edges)


def test_medical_stars_only_get_ai_links(tmp_path):
    ai = FakeAI({"coronary heart disease": [("chest pain", "symptom_of")]})
    c = _client(tmp_path, ai)
    food = _add(c, "I like to eat noodles")
    symptom = _add(c, "I have chest pain and feel breathless")
    disease = _add(c, "My dad has heart disease")
    _, edges = _edges(c)
    medical = {symptom, disease}
    for a, b, e in edges:
        if a in medical or b in medical:
            assert e["type"] == "ai", e
    assert any({a, b} == medical and e["kind"] == "symptom_of" for a, b, e in edges)
    assert not any(food in (a, b) and (a in medical or b in medical) for a, b, e in edges)


def test_hospital_linked_only_when_verified(tmp_path):
    ai = FakeAI({"cleveland clinic": [("coronary heart disease", "treated_at")]})
    c = _client(tmp_path, ai)
    disease = _add(c, "My dad has heart disease")
    hospital = _add(c, "Visited Cleveland Clinic for a checkup")
    _, edges = _edges(c)
    link = [e for a, b, e in edges if {a, b} == {disease, hospital}]
    assert len(link) == 1 and link[0]["type"] == "hospital"
    assert link[0]["extra"]["find_doctor_url"].startswith("https://")


def test_unverified_hospital_is_not_linked(tmp_path):
    ai = FakeAI({"general hospital": [("coronary heart disease", "treated_at")]}, verified=False)
    c = _client(tmp_path, ai)
    disease = _add(c, "My dad has heart disease")
    hospital = _add(c, "My cousin works at General Hospital")
    _, edges = _edges(c)
    assert ai.verify_calls == 1
    assert not any({a, b} == {disease, hospital} for a, b, e in edges)


def test_hospital_never_linked_to_symptom(tmp_path):
    ai = FakeAI({"cleveland clinic": [("chest pain", "treated_at"), ("chest pain", "related")]})
    c = _client(tmp_path, ai)
    symptom = _add(c, "I have chest pain and feel breathless")
    hospital = _add(c, "Visited Cleveland Clinic for a checkup")
    _, edges = _edges(c)
    assert ai.verify_calls == 0
    assert not any({a, b} == {symptom, hospital} for a, b, e in edges)


def test_daily_ai_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "AI_DAILY_LIMIT", 2)
    c = _client(tmp_path, FakeAI())
    entry_id = _add(c, "I like to eat noodles")  # 1 call (nothing to relate to yet)
    assert c.post("/api/explore", json={"entry_id": entry_id, "path": []}).status_code == 200
    resp = c.post("/api/explore", json={"entry_id": entry_id, "path": ["Japan"]})
    assert resp.status_code == 429


def test_ai_endpoints_off_without_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app = create_app(db_path=str(tmp_path / "x.db"))
    c = app.test_client()
    entry_id = c.post("/api/entries", json={"text": "noodles"}).get_json()["id"]
    assert c.post(f"/api/entries/{entry_id}/enrich", json={}).status_code == 404
    assert c.get("/api/stars").get_json()["ai"] is False
