"""KnowledgeAI's request handling, against a mocked Anthropic client."""
import json
from types import SimpleNamespace as NS

import pytest

from mindgalaxy.ai import AIError, KnowledgeAI


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def _client(*responses):
    msgs = FakeMessages(responses)
    return NS(beta=NS(messages=msgs)), msgs


def _json_reply(obj, stop="end_turn"):
    return NS(stop_reason=stop, content=[NS(type="text", text=json.dumps(obj))])


def _search_reply(urls, text="notes"):
    results = NS(type="web_search_tool_result", content=[NS(url=u) for u in urls])
    return NS(stop_reason="end_turn", content=[results, NS(type="text", text=text)])


def test_opus_requests_use_structured_output_and_fallbacks():
    client, msgs = _client(_json_reply({"category": "food", "subject": "Noodles ", "summary": "",
                                        "symptoms": [], "conditions": [], "hospital_name": "",
                                        "hospital_location": ""}))
    out = KnowledgeAI(client=client, model="claude-opus-5").analyze("i like to eat noodles")
    assert out["subject"] == "noodles"
    call = msgs.calls[0]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["thinking"] == {"type": "adaptive"}
    assert call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]


def test_refusal_raises():
    client, _ = _client(NS(stop_reason="refusal", content=[]))
    with pytest.raises(AIError):
        KnowledgeAI(client=client).analyze("x")


def test_verify_hospital_drops_urls_not_from_search():
    client, _ = _client(
        _search_reply(["https://hospital.org/heart", "https://news.org/ranking"]),
        _json_reply({"recognized": True, "why": "Ranked #1", "department": "Heart Institute",
                     "find_doctor_url": "https://hospital.org/made-up-doctor-page",
                     "evidence_urls": ["https://news.org/ranking", "https://invented.example/x"]}),
    )
    out = KnowledgeAI(client=client).verify_hospital("Hospital", "City", "heart disease")
    assert out["find_doctor_url"] == ""
    assert out["evidence_urls"] == ["https://news.org/ranking"]


def test_verify_hospital_rejects_when_not_recognized():
    client, _ = _client(
        _search_reply(["https://hospital.org/"]),
        _json_reply({"recognized": False, "why": "", "department": "", "find_doctor_url": "",
                     "evidence_urls": []}),
    )
    assert KnowledgeAI(client=client).verify_hospital("Hospital", "", "flu") is None


def test_verify_hospital_resumes_paused_search():
    paused = NS(stop_reason="pause_turn", content=[NS(type="web_search_tool_result",
                                                     content=[NS(url="https://a.org/1")])])
    client, msgs = _client(
        paused,
        _search_reply(["https://a.org/doctors"]),
        _json_reply({"recognized": True, "why": "Renowned", "department": "Oncology",
                     "find_doctor_url": "https://a.org/doctors", "evidence_urls": ["https://a.org/1"]}),
    )
    out = KnowledgeAI(client=client).verify_hospital("A", "", "cancer")
    assert out["find_doctor_url"] == "https://a.org/doctors"
    assert msgs.calls[1]["messages"][-1]["role"] == "assistant"
