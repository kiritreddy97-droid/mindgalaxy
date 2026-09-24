"""
mindgalaxy.ai
==============

AI-backed knowledge for the hosted site. Answers come from free AI providers
first (Gemini, Groq, OpenRouter ... -- see free_ai.py), falling back to
Claude when ANTHROPIC_API_KEY is set. With neither configured the galaxy uses
the offline curated knowledge in knowledge.py.

* analyze(text)        -> what a thought is about: a category (food,
                          disease, hospital, ...) and a canonical subject
                          ("i like to eat noodles" -> "noodles").
* explore(...)         -> one level of a drill-down through any subject:
                          noodles -> country -> kind of noodle -> dish style
                          -> dishes with origin and recipe.
* relate(...)          -> which of a user's other thoughts are *truly*
                          related to a new one, with a reason. Deliberately
                          strict, especially for anything medical.
* verify_hospital(...) -> checks on the web whether a hospital is genuinely
                          renowned for treating a condition, and finds its
                          official find-a-doctor page. Only a URL that came
                          back from the web search is ever shown.
"""
from __future__ import annotations

import importlib.util
import json
import os
from typing import Any, Optional

from .free_ai import FreeProvider, ProviderError, providers_from_env, wikipedia_evidence

DEFAULT_MODEL = "claude-opus-5"

CATEGORIES = [
    "food", "drink", "ingredient", "material", "product", "vehicle", "animal", "plant",
    "place", "person", "organisation", "activity", "science", "maths", "technology",
    "symptom", "disease", "hospital", "feeling", "other",
]
MEDICAL = {"symptom", "disease", "hospital"}
LINK_KINDS = ["same_subject", "part_of", "made_from", "symptom_of", "causes", "treated_at", "used_for", "related"]


class AIError(Exception):
    """The model couldn't produce a usable answer (refusal, timeout, bad output)."""


class QuotaError(AIError):
    """The user has used up today's allowance of uncached AI calls."""


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


_STR = {"type": "string"}
_STRS = {"type": "array", "items": _STR}

ANALYZE_SCHEMA = _obj({
    "category": {"type": "string", "enum": CATEGORIES},
    "subject": _STR,
    "summary": _STR,
    "symptoms": _STRS,
    "conditions": _STRS,
    "hospital_name": _STR,
    "hospital_location": _STR,
})

EXPLORE_SCHEMA = _obj({
    "heading": _STR,
    "kind": {"type": "string", "enum": ["choices", "detail"]},
    "prompt": _STR,
    "choices": {"type": "array", "items": _obj({"label": _STR, "blurb": _STR})},
    "items": {"type": "array", "items": _obj({
        "name": _STR,
        "origin": _STR,
        "summary": _STR,
        "facts": {"type": "array", "items": _obj({"label": _STR, "value": _STR})},
        "ingredients": _STRS,
        "steps": _STRS,
        "steps_label": _STR,
    })},
    "note": _STR,
})

RELATE_SCHEMA = _obj({
    "links": {"type": "array", "items": _obj({
        "other_id": {"type": "integer"},
        "kind": {"type": "string", "enum": LINK_KINDS},
        "reason": _STR,
    })},
})

VERIFY_SCHEMA = _obj({
    "recognized": {"type": "boolean"},
    "why": _STR,
    "department": _STR,
    "find_doctor_url": _STR,
    "evidence_urls": _STRS,
})

ANALYZE_SYSTEM = """You classify short personal notes for a journaling app that turns each note into a star.
Return the note's category and its subject: the canonical name of the main thing it is about, in plain
lowercase English, as someone would search for it ("i like to eat noodles" -> "noodles"; "my knee hurts
when i climb stairs" -> "knee pain"; "went to AIIMS Delhi today" -> "aiims new delhi").
summary: one short sentence describing what the note is about.
symptoms / conditions: any medical symptoms or diseases the note mentions (empty lists if none).
hospital_name / hospital_location: only if the note names a specific hospital, else empty strings.
Use category "symptom" when the note is mainly about something the writer is feeling physically,
"disease" for a named illness or condition, "hospital" for a named hospital or clinic."""

EXPLORE_SYSTEM = """You power the "gas cloud" around a star in a journaling app: the user explores the subject of
one of their notes one level at a time, like opening nested nebulae. Each call returns ONE level.
Answers are shared by everyone exploring the same subject, so write for a general reader.

Return kind "choices" to offer the next level (3-10 choices, each with a one-line blurb), or kind
"detail" when the path is specific enough to show concrete things (up to 6 items).

Choose the levels that suit the subject:
- Foods, dishes and ingredients (e.g. noodles, rice, bread, cheese): level 1 = the countries or regions
  where it is a genuine, significant tradition; level 2 = the basic kinds that actually exist in that
  country (for noodles: wheat, egg, rice, buckwheat, flat, glass noodles ...; only kinds really used
  there); level 3 = the styles of dish made from that kind there (soup like pho or ramen, stir-fried
  like pad thai or chow mein, cold, dry-tossed ...); then "detail" = the actual dishes.
  Food detail items: origin = where and roughly when the dish comes from; summary; facts (e.g. typical
  noodle, broth, region, when eaten); ingredients; steps = a concise home recipe (at most 8 steps),
  steps_label "Recipe".
- Materials and products (e.g. cement, steel, watches): kinds -> grades or uses -> detail with
  properties, typical uses, facts (strength, cost range ...), steps only if a process is natural
  (e.g. "How it's made" or "How to mix").
- Diseases: level 1 choices such as Overview, Symptoms, Causes and risk factors, Diagnosis, Treatment
  options, Prevention, When to see a doctor; detail items are plain-language explanations.
- Symptoms: first level = common possible causes grouped by how serious they are, and "Warning signs
  that need urgent care"; detail explains each. Never diagnose: note must say this is general
  information, not a diagnosis, and to see a doctor (or emergency services for warning signs).
- Hospitals: departments or specialties the hospital is known for -> detail. Never name individual
  doctors; point to the hospital's own find-a-doctor service instead.
- Anything else: the 2-4 levels a knowledgeable guide would naturally use.

Only include options that genuinely exist at this point of the path. Be accurate: say "disputed" or
"uncertain" rather than inventing origins, dates or numbers. Keep blurbs and summaries short. Unused
fields: empty string or empty list. After 4 levels always return "detail"."""

RELATE_SYSTEM = """You decide which of a user's earlier notes are truly related to their new note, for drawing
lines between stars. Be strict: link only when a knowledgeable person would say the two are directly
and substantively connected, and explain the connection in one short sentence (the reason is shown
to the user). Sharing a word, a broad domain ("both are food") or a mood is not enough.
Kinds: same_subject (the same thing), part_of, made_from (e.g. a dish and its main ingredient),
symptom_of (a symptom that is a common, recognised sign of that condition), causes, treated_at,
used_for, related (any other strong, specific link).
Medical rules:
- symptom_of only between a symptom and a disease in which that symptom is a common, recognised sign.
- treated_at only between a hospital and a disease, and only if that hospital is nationally or
  internationally renowned for treating that specific disease (this will be checked on the web).
- never link a hospital to a symptom, and never link a hospital just because it is a hospital.
Return at most 6 links; return an empty list if nothing is truly related. other_id must be one of
the given ids."""

VERIFY_RESEARCH = """Is {hospital}{loc} nationally or internationally recognised for treating {condition}
specifically? Search for real evidence such as national rankings, a dedicated centre or department for
this condition, or notable outcomes. Also find the hospital's own official web page for finding a
doctor or specialist (for that department if possible). Report what you found, with the URLs."""

VERIFY_WIKIPEDIA_SCHEMA = _obj({
    "same_hospital": {"type": "boolean"},
    "recognized": {"type": "boolean"},
    "why": _STR,
    "department": _STR,
})

VERIFY_WIKIPEDIA = """Below is the Wikipedia article "{title}". First decide whether it is about the hospital
"{hospital}" at all (same_hospital). Then decide whether the article gives concrete evidence that this
hospital is nationally or internationally recognised for treating {condition} specifically -- for example
a ranking, a dedicated centre or institute for it, or notable firsts or outcomes. recognized must be false
if the article only says the hospital is large, famous or general, or never mentions this condition or its
specialty. why: one or two sentences a patient could understand, based only on the article.
department: the relevant department or centre named in the article, or an empty string.

Article:
{text}"""

VERIFY_STRUCTURE = """From the research notes below, decide whether {hospital} is genuinely recognised for
treating {condition}. recognized must be false unless the notes contain concrete evidence.
why: one or two sentences a patient could understand. department: the relevant department or centre.
find_doctor_url: the hospital's official find-a-doctor or department page, copied exactly from the
source URLs listed below, or an empty string if none of them is one. evidence_urls: the source URLs
that support the answer, copied exactly.

Source URLs:
{urls}

Research notes:
{notes}"""


class KnowledgeAI:
    def __init__(self, client: Any = None, model: Optional[str] = None,
                 free_providers: Optional[list[FreeProvider]] = None):
        self.model = model or os.environ.get("MINDGALAXY_MODEL", DEFAULT_MODEL)
        self._client = client
        self.free = providers_from_env() if free_providers is None else free_providers

    @property
    def claude_on(self) -> bool:
        if self._client is not None:
            return True
        # Claude is optional (pip install mindgalaxy[claude]); a key alone isn't enough.
        return bool(os.environ.get("ANTHROPIC_API_KEY")) and importlib.util.find_spec("anthropic") is not None

    @property
    def enabled(self) -> bool:
        return bool(self.free) or self.claude_on

    @property
    def name(self) -> str:
        """Identifies the answer source, so cached answers are kept per source."""
        if self.free:
            return "free:" + ",".join(f"{p.name}/{p.model}" for p in self.free)
        return self.model

    @property
    def client(self) -> Any:
        if self._client is None:
            import anthropic

            # Stay well inside the serverless function's time limit.
            self._client = anthropic.Anthropic(timeout=110.0, max_retries=1)
        return self._client

    def _request(self, **kwargs: Any) -> Any:
        import anthropic

        extra: dict[str, Any] = {}
        if self.model.startswith(("claude-opus-5", "claude-fable-5")):
            # If a safety classifier declines, re-run on Anthropic's
            # recommended fallback model instead of failing the request.
            extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        try:
            resp = self.client.beta.messages.create(model=self.model, thinking={"type": "adaptive"},
                                                    **extra, **kwargs)
        except anthropic.APIError as e:  # timeouts, rate limits, overloads, bad requests
            raise AIError(f"Claude request failed: {e.__class__.__name__}") from e
        if resp.stop_reason == "refusal":
            raise AIError("Claude declined to answer this one.")
        return resp

    def _json(self, system: str, user: str, schema: dict[str, Any], effort: str) -> dict[str, Any]:
        """Ask the free providers in turn; Claude (if configured) is the last resort."""
        for provider in self.free:
            try:
                return provider.complete_json(system, user, schema)
            except ProviderError:
                continue  # rate-limited, out of quota or down: try the next one
        if self.claude_on:
            return self._claude_json(system, user, schema, effort)
        raise AIError("The free AI services are busy or out of today's quota. Try again in a little while.")

    def _claude_json(self, system: str, user: str, schema: dict[str, Any], effort: str) -> dict[str, Any]:
        resp = self._request(
            max_tokens=16000, system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        )
        if resp.stop_reason == "max_tokens":
            raise AIError("The answer was too long.")
        text = next((b.text for b in resp.content if b.type == "text"), "")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise AIError("Claude returned malformed JSON.") from e

    # ------------------------------------------------------------------
    def analyze(self, text: str) -> dict[str, Any]:
        out = self._json(ANALYZE_SYSTEM, f"Note:\n{text}", ANALYZE_SCHEMA, effort="low")
        out["subject"] = (out.get("subject") or "").strip().lower()[:80] or text.strip().lower()[:80]
        return out

    def explore(self, subject: str, category: str, path: list[str]) -> dict[str, Any]:
        # Deliberately not given the user's note: answers are cached and
        # shared between everyone who explores the same subject.
        trail = " > ".join(path) if path else "(top level)"
        user = (f"Subject: {subject}\nCategory: {category}\n"
                f"Choices made so far: {trail}\nLevel number: {len(path) + 1}")
        return self._json(EXPLORE_SYSTEM, user, EXPLORE_SCHEMA, effort="low")

    def relate(self, new: dict[str, Any], others: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not others:
            return []
        lines = [f"[{o['id']}] ({o['category']}: {o['subject']}) {o['text'][:240]}" for o in others]
        user = (f"New note [{new['id']}] ({new['category']}: {new['subject']}): {new['text'][:600]}\n\n"
                "Earlier notes:\n" + "\n".join(lines))
        out = self._json(RELATE_SYSTEM, user, RELATE_SCHEMA, effort="medium")
        valid = {o["id"] for o in others}
        seen, links = set(), []
        for l in out.get("links", []):
            if l["other_id"] in valid and l["other_id"] not in seen and l.get("reason"):
                seen.add(l["other_id"])
                links.append(l)
        return links[:6]

    def verify_hospital(self, hospital: str, location: str, condition: str) -> Optional[dict[str, Any]]:
        """Is this hospital genuinely renowned for treating this condition?"""
        if self.free or not self.claude_on:
            return self._verify_with_wikipedia(hospital, location, condition)
        return self._verify_with_web_search(hospital, location, condition)

    def _verify_with_wikipedia(self, hospital: str, location: str, condition: str) -> Optional[dict[str, Any]]:
        """Free route: judge from the hospital's Wikipedia article; link its
        official website from Wikidata. Both URLs come from Wikimedia, never
        from the model."""
        try:
            page = wikipedia_evidence(hospital, location)
        except ProviderError as e:
            raise AIError("Couldn't reach Wikipedia to check the hospital.") from e
        if not page:
            return None
        out = self._json(
            "You check claims carefully and only accept concrete evidence from the text you are given.",
            VERIFY_WIKIPEDIA.format(hospital=hospital, condition=condition, title=page["title"], text=page["text"]),
            VERIFY_WIKIPEDIA_SCHEMA, effort="medium",
        )
        if not (out.get("same_hospital") and out.get("recognized")):
            return None
        return {"hospital": hospital, "location": location, "condition": condition,
                "why": out.get("why", ""), "department": out.get("department", ""),
                "find_doctor_url": page["website"], "evidence_urls": [page["url"]]}

    def _verify_with_web_search(self, hospital: str, location: str, condition: str) -> Optional[dict[str, Any]]:
        loc = f" ({location})" if location else ""
        messages: list[dict[str, Any]] = [{"role": "user", "content": VERIFY_RESEARCH.format(
            hospital=hospital, loc=loc, condition=condition)}]
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}]
        urls: list[str] = []
        notes: list[str] = []
        for _ in range(3):
            resp = self._request(max_tokens=16000, messages=messages, tools=tools,
                                 output_config={"effort": "medium"})
            for b in resp.content:
                if b.type == "web_search_tool_result" and isinstance(b.content, list):
                    urls += [r.url for r in b.content if getattr(r, "url", None)]
                elif b.type == "text":
                    notes.append(b.text)
            if resp.stop_reason != "pause_turn":
                break
            messages = messages[:1] + [{"role": "assistant", "content": resp.content}]
        urls = list(dict.fromkeys(urls))
        if not urls:
            return None
        out = self._json(
            "You check claims carefully and only accept concrete evidence.",
            VERIFY_STRUCTURE.format(hospital=hospital, condition=condition,
                                    urls="\n".join(urls[:40]), notes="\n".join(notes)[:12000]),
            VERIFY_SCHEMA, effort="medium",
        )
        if not out.get("recognized"):
            return None
        evidence = [u for u in out.get("evidence_urls", []) if u in urls]
        doctor_url = out.get("find_doctor_url", "")
        # Only show links that actually came back from the web search, so a
        # guessed or made-up URL can never reach the page.
        if doctor_url not in urls:
            doctor_url = ""
        if not evidence:
            return None
        return {"hospital": hospital, "location": location, "condition": condition,
                "why": out.get("why", ""), "department": out.get("department", ""),
                "find_doctor_url": doctor_url, "evidence_urls": evidence[:4]}
