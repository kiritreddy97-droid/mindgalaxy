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
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

USER_AGENT = "MindGalaxy/1.0 (https://github.com/kiritreddy97-droid/mindgalaxy)"
TIMEOUT = 60


log = logging.getLogger("mindgalaxy.ai")


class ProviderError(Exception):
    """This provider couldn't answer (quota, outage, bad output); try the next."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


# name, API-key env var, base URL, default model, model env var
# Groq first: it runs on dedicated inference chips and answers in a second or
# two; Gemini is the backup.
KNOWN_PROVIDERS = [
    ("Groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b", "GROQ_MODEL"),
    ("Gemini", "GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai",
     "gemini-3.8-flash", "GEMINI_MODEL"),
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
        headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
        if self.api_key:  # key-less (anonymous) endpoints reject any Authorization header
            headers["Authorization"] = f"Bearer {self.api_key}"
        return self._request("/chat/completions", headers, json.dumps(body).encode())

    def _request(self, path: str, headers: dict[str, str], data: Optional[bytes] = None) -> dict[str, Any]:
        req = urllib.request.Request(self.base_url.rstrip("/") + path, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            detail = _error_detail(e)
            # Logged so a failing provider is diagnosable from the server logs
            # (the user only sees a short message). The key is never logged.
            log.warning("AI provider %s (model %s) returned HTTP %s: %s", self.name, self.model, e.code, detail)
            raise ProviderError(f"{self.name} returned HTTP {e.code}: {detail}", e.code) from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            log.warning("AI provider %s unreachable: %r", self.name, e)
            raise ProviderError(f"{self.name} unreachable") from e

    def _available_models(self) -> list[str]:
        """The models this key can use, best first (see rank_models)."""
        headers = {"User-Agent": USER_AGENT}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            listing = self._request("/models", headers)
        except ProviderError:
            return []
        ids = [str(m.get("id", "")).removeprefix("models/") for m in listing.get("data", []) if isinstance(m, dict)]
        return rank_models(ids, self.model)

    def _discover_model(self) -> Optional[str]:
        """Best replacement when the configured model doesn't exist (models
        get renamed and retired over time)."""
        ranked = self._available_models()
        return ranked[0] if ranked else None

    def _post_with_fallbacks(self, body: dict[str, Any], max_attempts: int = 4) -> dict[str, Any]:
        """Post, moving down this provider's models when one can't answer:
        retired (404) -> switch for good to the best available model;
        overloaded or out of its free quota (429/5xx) -> try the next model
        for this request (free limits are per model); JSON mode rejected
        (other 400s) -> retry without it."""
        tried: set[str] = set()
        ranked: Optional[list[str]] = None
        last: Optional[ProviderError] = None
        for _ in range(max_attempts):
            try:
                return self._post(body)
            except ProviderError as e:
                last = e
                retired = e.status == 404 or (e.status == 400 and "model" in str(e).lower() and "not" in str(e).lower())
                if e.status == 400 and not retired:
                    # Drop whichever optional setting the provider objected to:
                    # not every model takes a reasoning setting or JSON mode.
                    msg = str(e).lower()
                    optional = ["reasoning_effort", "response_format"]
                    if "json" in msg or "response_format" in msg:
                        optional.reverse()
                    drop = next((k for k in optional if k in body), None)
                    if drop:
                        body.pop(drop)
                        continue
                if not (retired or e.status in (429, 500, 502, 503)):
                    raise
                tried.add(body["model"])
                if ranked is None:
                    ranked = self._available_models()
                nxt = next((m for m in ranked if m not in tried), None)
                if nxt is None:
                    raise
                log.warning("AI provider %s: %s can't answer (HTTP %s), trying %s", self.name, body["model"], e.status, nxt)
                if retired and body["model"] == self.model:
                    self.model = nxt  # retired models stay retired
                body["model"] = nxt
        raise last  # type: ignore[misc]

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
            # These are lookups, not puzzles: little "thinking" answers much faster.
            "reasoning_effort": "low",
        }
        data = self._post_with_fallbacks(body)
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"{self.name} sent an unexpected response") from e
        return conform(parse_json_object(text, self.name), schema)


def _error_detail(e: urllib.error.HTTPError) -> str:
    """The provider's own error message, shortened."""
    try:
        raw = e.read().decode(errors="replace")
    except Exception:  # noqa: BLE001 -- best effort only
        return ""
    try:
        err = json.loads(raw)
        if isinstance(err, list) and err:
            err = err[0]
        msg = err.get("error", err) if isinstance(err, dict) else err
        msg = msg.get("message", msg) if isinstance(msg, dict) else msg
        raw = str(msg)
    except (json.JSONDecodeError, AttributeError):
        pass
    return re.sub(r"\s+", " ", raw)[:300]


def rank_models(ids: list[str], wanted: str) -> list[str]:
    """Available model ids ranked as replacements for `wanted`: same family
    first (e.g. Gemini Flash, then Flash-Lite), stable before preview, newest
    first; specialised variants (image, speech, embeddings ...) left out."""
    skip = ("image", "tts", "audio", "live", "embed", "vision", "native", "guard", "whisper", "robotics", "computer")
    usable = [m for m in ids if m and not any(s in m.lower() for s in skip)]
    family = "flash" if "flash" in wanted.lower() else ""

    def rank(m: str) -> tuple:
        low = m.lower()
        nums = re.findall(r"\d+(?:\.\d+)?", m)
        return (
            1 if family and family in low else 0,
            0 if "lite" in low else 1,
            0 if ("exp" in low or "preview" in low) else 1,
            float(nums[0]) if nums else 0.0,
        )

    return sorted(dict.fromkeys(usable), key=rank, reverse=True)


def pick_model(ids: list[str], wanted: str) -> Optional[str]:
    ranked = rank_models(ids, wanted)
    return ranked[0] if ranked else None


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
