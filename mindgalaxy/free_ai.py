"""
mindgalaxy.free_ai
===================

Free alternatives to the Claude API, so the hosted site can run at no cost.

* FreeProvider -- any "OpenAI-compatible" chat endpoint with a permanent free
  tier. Configured from environment variables (see providers_from_env);
  several can be chained, and when one is rate-limited or out of quota the
  next one answers. Provider list and limits: github.com/mnfst/awesome-free-llm-apis
* wikipedia_evidence -- free, key-less evidence for hospital checks: the
  hospital's Wikipedia article plus its official website from Wikidata.

Only the standard library is used for HTTP, so no extra dependencies.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

USER_AGENT = "MindGalaxy/1.0 (https://github.com/kiritreddy97-droid/mindgalaxy)"
TIMEOUT = 60


class ProviderError(Exception):
    """This provider couldn't answer (quota, outage, bad output); try the next."""


# name, API-key env var, base URL, default model, model env var
KNOWN_PROVIDERS = [
    ("Gemini", "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai",
     "gemini-2.5-flash", "GEMINI_MODEL"),
    ("Groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b", "GROQ_MODEL"),
    ("OpenRouter", "OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", "openai/gpt-oss-20b:free",
     "OPENROUTER_MODEL"),
    ("NVIDIA", "NVIDIA_API_KEY", "https://integrate.api.nvidia.com/v1", "meta/llama-3.3-70b-instruct",
     "NVIDIA_MODEL"),
]


@dataclass
class FreeProvider:
    name: str
    base_url: str
    api_key: str
    model: str

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            self.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}",
                     "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise ProviderError(f"{self.name} returned HTTP {e.code}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise ProviderError(f"{self.name} unreachable") from e

    def complete_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system + "\n\nReply with a single JSON object (no markdown, "
                 "no commentary) matching this JSON Schema:\n" + json.dumps(schema)},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
            "max_tokens": 8000,
            "response_format": {"type": "json_object"},
        }
        try:
            data = self._post(body)
        except ProviderError as e:
            if "HTTP 400" not in str(e):
                raise
            body.pop("response_format")  # some models reject JSON mode; the prompt still asks for JSON
            data = self._post(body)
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"{self.name} sent an unexpected response") from e
        return conform(parse_json_object(text, self.name), schema)


def providers_from_env() -> list[FreeProvider]:
    """Every free provider with a key set, in order: Gemini, Groq, OpenRouter,
    NVIDIA, then a custom one from FREE_AI_BASE_URL / FREE_AI_API_KEY / FREE_AI_MODEL."""
    out = []
    for name, key_var, base, model, model_var in KNOWN_PROVIDERS:
        key = os.environ.get(key_var)
        if key:
            out.append(FreeProvider(name, base, key, os.environ.get(model_var, model)))
    base, model = os.environ.get("FREE_AI_BASE_URL"), os.environ.get("FREE_AI_MODEL")
    if base and model:
        out.append(FreeProvider("Custom", base, os.environ.get("FREE_AI_API_KEY", ""), model))
    return out


def parse_json_object(text: str, who: str = "model") -> dict[str, Any]:
    """Pull the JSON object out of a reply, tolerating code fences or chatter."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ProviderError(f"{who} didn't return JSON")
        try:
            value = json.loads(text[start:end + 1])
        except json.JSONDecodeError as e:
            raise ProviderError(f"{who} returned malformed JSON") from e
    if not isinstance(value, dict):
        raise ProviderError(f"{who} returned JSON that isn't an object")
    return value


def conform(value: Any, schema: dict[str, Any]) -> Any:
    """Coerce a free model's looser JSON into exactly the shape the schema
    promises, filling anything missing with an empty value, so the rest of
    the app can rely on it like it relies on Claude's structured output."""
    kind = schema.get("type")
    if kind == "object":
        src = value if isinstance(value, dict) else {}
        return {k: conform(src.get(k), sub) for k, sub in schema["properties"].items()}
    if kind == "array":
        items = value if isinstance(value, list) else []
        return [conform(v, schema["items"]) for v in items if v is not None]
    if kind == "boolean":
        return value if isinstance(value, bool) else str(value).lower() == "true"
    if kind == "integer":
        try:
            return int(value)
        except (TypeError, ValueError):
            return -1
    text = "" if value is None else str(value)
    if "enum" in schema and text not in schema["enum"]:
        low = text.lower()
        return low if low in schema["enum"] else schema["enum"][-1]
    return text


# ---------------------------------------------------------------------------
# Free hospital evidence: Wikipedia + Wikidata (no key, no cost)
# ---------------------------------------------------------------------------
def _get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        raise ProviderError("Wikipedia unreachable") from e


def wikipedia_evidence(hospital: str, location: str) -> Optional[dict[str, str]]:
    """The hospital's Wikipedia article text and URL, plus its official website
    from Wikidata when listed. None if no matching article exists."""
    api = "https://en.wikipedia.org/w/api.php?"
    found = _get_json(api + urllib.parse.urlencode({
        "action": "query", "list": "search", "format": "json", "srlimit": 3,
        "srsearch": f"{hospital} {location}".strip(),
    }))
    hits = (found.get("query") or {}).get("search") or []
    if not hits:
        return None
    title = hits[0]["title"]
    page = _get_json(api + urllib.parse.urlencode({
        "action": "query", "format": "json", "prop": "extracts|pageprops", "explaintext": 1,
        "redirects": 1, "titles": title,
    }))
    pages = list(((page.get("query") or {}).get("pages") or {}).values())
    if not pages or "extract" not in pages[0]:
        return None
    info = pages[0]
    url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(info["title"].replace(" ", "_"))
    website = ""
    qid = (info.get("pageprops") or {}).get("wikibase_item")
    if qid and re.fullmatch(r"Q\d+", qid):
        try:
            entity = _get_json(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")["entities"][qid]
            claims = entity.get("claims", {}).get("P856") or []  # P856 = official website
            if claims:
                website = claims[0]["mainsnak"]["datavalue"]["value"]
        except (ProviderError, KeyError, IndexError, TypeError):
            website = ""
    if website and not website.startswith(("https://", "http://")):
        website = ""
    return {"title": info["title"], "url": url, "text": info["extract"][:15000], "website": website}
