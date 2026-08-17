"""
mindgalaxy.exporter
=====================

Bakes a computed galaxy (see mindgalaxy.engine.build_galaxy) into a single,
fully self-contained HTML file that renders the interactive 3D galaxy with
no server required — open it straight in a browser, or email/share it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "galaxy.html"
THREE_JS_PATH = Path(__file__).resolve().parent / "vendor" / "three.min.js"
THREE_JS_CDN_URL = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"

_three_js_cache: str | None = None


def _three_js_tag() -> str:
    """
    Prefer the locally vendored copy of three.js (mindgalaxy/vendor/three.min.js)
    so exported pages have zero external dependencies and work completely
    offline. If that file isn't present -- e.g. a lightweight checkout that
    didn't include it -- fall back to loading it from a CDN instead of
    failing outright.
    """
    global _three_js_cache
    if THREE_JS_PATH.exists():
        if _three_js_cache is None:
            _three_js_cache = THREE_JS_PATH.read_text(encoding="utf-8")
        return f"<script>/* three.js r128 (MIT License) — vendored inline so this page works fully offline */\n{_three_js_cache}</script>"
    return f'<script src="{THREE_JS_CDN_URL}"></script>'


def render_html(galaxy: dict[str, Any], title: str = "My Mind Galaxy", mode: str = "standalone") -> str:
    """Render the galaxy template to an HTML string for the given mode."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    payload = json.dumps(galaxy) if mode == "standalone" else "{}"
    html = (
        template
        .replace("__THREE_JS_TAG__", _three_js_tag())
        .replace("__GALAXY_DATA__", payload)
        .replace("__GALAXY_TITLE__", title)
        .replace("__MODE__", mode)
    )
    return html


def export_standalone(galaxy: dict[str, Any], output_path: str | Path, title: str = "My Mind Galaxy") -> Path:
    """Write a standalone, shareable HTML snapshot of the galaxy to disk."""
    html = render_html(galaxy, title=title, mode="standalone")
    output_path = Path(output_path)
    output_path.write_text(html, encoding="utf-8")
    return output_path
