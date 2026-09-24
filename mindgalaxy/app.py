"""
mindgalaxy.app
================

A tiny Flask app that serves the live, always-current galaxy: the 3D
visualization page plus a JSON API that recomputes the galaxy from
whatever is currently in the database.

Two modes:

* single-user (the default, used by `mindgalaxy serve`): no accounts, every
  entry belongs to whoever runs it.
* multi-user (the hosted site, see index.py): people sign up with a username
  and a 4-digit passkey, and each person only ever sees their own galaxy.

When ANTHROPIC_API_KEY is set, Claude adds a drill-down "gas cloud" for any
subject and draws lines only between thoughts that are truly related (see
mindgalaxy/ai.py). Without it the offline curated knowledge is used.
"""
from __future__ import annotations

import datetime as _dt
import functools
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Optional

from flask import Flask, g, jsonify, redirect, request, session

from . import auth
from .ai import MEDICAL, AIError, KnowledgeAI, QuotaError
from .engine import build_galaxy
from .exporter import render_html
from .storage import DEFAULT_DB_PATH, Storage

LOGIN_TEMPLATE = Path(__file__).resolve().parent / "templates" / "login.html"
AI_DAILY_LIMIT = int(os.environ.get("MINDGALAXY_AI_DAILY_LIMIT", "80"))
MAX_ENTRY_CHARS = 2000
MAX_PATH_DEPTH = 5


def _client_ip() -> str:
    # Vercel sets these itself; locally they're absent and remote_addr is used.
    real = request.headers.get("X-Real-IP")
    if real:
        return real.strip()
    fwd = request.headers.get("X-Forwarded-For", "")
    return fwd.split(",")[0].strip() or (request.remote_addr or "unknown")


def assemble_galaxy(store: Storage, ai_on: bool) -> dict[str, Any]:
    """Compute the galaxy; with AI on, replace loose links with AI-judged ones.

    The word-overlap lines from the engine stay for everyday thoughts, but a
    symptom, disease or hospital star only gets lines that Claude judged to be
    genuinely related (and, for hospitals, that were verified on the web).
    """
    galaxy = build_galaxy(store.all_entries())
    galaxy["ai"] = ai_on
    if not ai_on or not galaxy["stars"]:
        return galaxy
    analyses = store.analyses()
    index = {s["id"]: i for i, s in enumerate(galaxy["stars"])}
    medical = set()
    for i, s in enumerate(galaxy["stars"]):
        s["analysis"] = analyses.get(s["id"])
        if s["analysis"] and s["analysis"].get("category") in MEDICAL:
            medical.add(i)
    edges = [e for e in galaxy["edges"]
             if e.get("type") != "topic" and e["source"] not in medical and e["target"] not in medical]
    for link in store.links():
        if link["a"] in index and link["b"] in index:
            edges.append({
                "source": index[link["a"]], "target": index[link["b"]], "weight": 0.9,
                "type": "hospital" if link["kind"] == "treated_at" else "ai",
                "kind": link["kind"], "reason": link["reason"], "extra": link["extra"],
            })
    galaxy["edges"] = edges
    return galaxy


def link_allowed(kind: str, cat_a: str, cat_b: str) -> bool:
    """The hard rules for medical links, applied on top of the model's judgement."""
    cats = {cat_a, cat_b}
    if kind == "treated_at":
        return cats == {"hospital", "disease"}  # and it must still pass web verification
    if kind == "symptom_of":
        return cats == {"symptom", "disease"}
    if "hospital" in cats:
        # a hospital only connects to another mention of the same hospital
        return kind == "same_subject" and cats == {"hospital"}
    return True


def create_app(
    db_path: str = str(DEFAULT_DB_PATH),
    multi_user: bool = False,
    secret_key: Optional[str] = None,
    ai: Optional[KnowledgeAI] = None,
) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path
    app.config["MULTI_USER"] = multi_user
    if multi_user:
        if not secret_key:
            raise RuntimeError("Multi-user mode needs a SECRET_KEY to sign login sessions.")
        app.config.update(
            SECRET_KEY=secret_key,
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SAMESITE="Lax",
            SESSION_COOKIE_SECURE=bool(os.environ.get("VERCEL")),
            PERMANENT_SESSION_LIFETIME=_dt.timedelta(days=30),
        )
    knowledge = ai if ai is not None else KnowledgeAI()

    def _store(user_id: Optional[int] = None) -> Storage:
        return Storage(app.config["DB_PATH"], user_id=user_id)

    def _error(message: str, status: int):
        return jsonify({"error": message}), status

    def _ai_error(e: AIError):
        return _error(str(e), 429 if isinstance(e, QuotaError) else 502)

    def login_required(view: Callable) -> Callable:
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            if multi_user:
                if not session.get("uid"):
                    return _error("Please sign in.", 401)
                # JSON-only writes: a cross-site form can't send this content
                # type without a CORS preflight, which blocks CSRF.
                if request.method == "POST" and not request.is_json:
                    return _error("Expected a JSON request.", 415)
            g.uid = session.get("uid") if multi_user else None
            return view(*args, **kwargs)
        return wrapper

    def _spend_ai(store: Storage) -> None:
        """Count one uncached Claude call against the user's daily allowance."""
        who = str(g.uid if g.uid is not None else "local")
        since = _dt.datetime.utcnow() - _dt.timedelta(days=1)
        if store.count_events("ai", who, since) >= AI_DAILY_LIMIT:
            raise QuotaError("You've reached today's limit for new AI lookups. Try again tomorrow.")
        store.log_event("ai", who)

    # -- pages -----------------------------------------------------------
    @app.get("/")
    def index():
        if multi_user and not session.get("uid"):
            return redirect("/login")
        return render_html({}, title="My Mind Galaxy", mode="server")

    @app.get("/login")
    def login_page():
        if not multi_user or session.get("uid"):
            return redirect("/")
        return LOGIN_TEMPLATE.read_text(encoding="utf-8")

    # -- accounts --------------------------------------------------------
    def _auth(action: Callable) -> Any:
        if not multi_user:
            return _error("Accounts are only used on the hosted site.", 404)
        if not request.is_json:
            return _error("Expected a JSON request.", 415)
        payload = request.get_json(silent=True) or {}
        try:
            with _store() as store:
                user = action(store, str(payload.get("username", "")), str(payload.get("pin", "")), _client_ip())
        except auth.AuthError as e:
            return _error(e.message, e.status)
        session.clear()
        session.permanent = True
        session["uid"] = user.id
        return jsonify({"username": user.username})

    @app.post("/api/signup")
    def api_signup():
        return _auth(auth.signup)

    @app.post("/api/login")
    def api_login():
        return _auth(auth.login)

    @app.post("/api/logout")
    def api_logout():
        session.clear()
        return jsonify({"ok": True})

    @app.get("/api/me")
    @login_required
    def api_me():
        username = None
        if multi_user:
            with _store() as store:
                user = store.get_user_by_id(g.uid)
            if not user:
                session.clear()
                return _error("Please sign in.", 401)
            username = user["username"]
        return jsonify({"username": username, "multi_user": multi_user, "ai": knowledge.enabled})

    # -- galaxy ----------------------------------------------------------
    @app.get("/api/stars")
    @login_required
    def api_stars():
        with _store(g.uid) as store:
            galaxy = assemble_galaxy(store, knowledge.enabled)
        return jsonify(galaxy)

    @app.post("/api/entries")
    @login_required
    def api_add_entry():
        payload = request.get_json(force=True, silent=True) or {}
        text = (payload.get("text") or "").strip()
        if not text:
            return _error("text is required", 400)
        if len(text) > MAX_ENTRY_CHARS:
            return _error(f"Thoughts can be at most {MAX_ENTRY_CHARS} characters.", 400)
        with _store(g.uid) as store:
            entry_id = store.add(text, _dt.datetime.utcnow())
            count = store.count()
        return jsonify({"id": entry_id, "count": count, "ai": knowledge.enabled}), 201

    def _brief(entry_id: int, analysis: Optional[dict[str, Any]]) -> dict[str, Any]:
        analysis = analysis or {}
        return {"id": entry_id, "category": analysis.get("category", "other"),
                "subject": analysis.get("subject", ""),
                "hospital_name": analysis.get("hospital_name", ""),
                "hospital_location": analysis.get("hospital_location", "")}

    def _verify_hospital(store: Storage, a: dict[str, Any], b: dict[str, Any]) -> Optional[dict[str, Any]]:
        """A hospital-disease link survives only if the web confirms it."""
        hospital, condition = (a, b) if a["category"] == "hospital" else (b, a)
        if not hospital["hospital_name"]:
            return None
        key = "hospital:v1:" + hashlib.sha256(json.dumps(
            [hospital["hospital_name"].lower(), hospital["hospital_location"].lower(),
             condition["subject"]]).encode()).hexdigest()
        cached = store.cache_get(key)
        if cached is not None:
            return cached or None
        _spend_ai(store)
        result = knowledge.verify_hospital(hospital["hospital_name"], hospital["hospital_location"],
                                           condition["subject"])
        store.cache_put(key, result or {})
        return result

    @app.post("/api/entries/<int:entry_id>/enrich")
    @login_required
    def api_enrich(entry_id: int):
        """Classify a new thought and link it to the thoughts truly related to it."""
        if not knowledge.enabled:
            return _error("AI knowledge isn't configured on this server.", 404)
        with _store(g.uid) as store:
            entry = store.get_entry(entry_id)
            if not entry:
                return _error("No such thought.", 404)
            if entry["analysis"]:
                return jsonify({"analysis": entry["analysis"], "links": 0})
            try:
                _spend_ai(store)
                analysis = knowledge.analyze(entry["text"])
                store.set_analysis(entry_id, analysis)
                new = {**_brief(entry_id, analysis), "text": entry["text"]}
                analyses = store.analyses()
                others = [{**_brief(e.id, analyses[e.id]), "text": e.text}
                          for e in store.all_entries() if e.id != entry_id and e.id in analyses][-150:]
                by_id = {o["id"]: o for o in others}
                links = 0
                if others:
                    _spend_ai(store)
                    for link in knowledge.relate(new, others):
                        other = by_id[link["other_id"]]
                        if not link_allowed(link["kind"], new["category"], other["category"]):
                            continue
                        extra = None
                        if link["kind"] == "treated_at":
                            extra = _verify_hospital(store, new, other)
                            if not extra:
                                continue
                        store.add_link(entry_id, other["id"], link["kind"], link["reason"], extra)
                        links += 1
            except AIError as e:
                return _ai_error(e)
        return jsonify({"analysis": analysis, "links": links})

    @app.post("/api/explore")
    @login_required
    def api_explore():
        """One level of the drill-down gas cloud around a star."""
        if not knowledge.enabled:
            return _error("AI knowledge isn't configured on this server.", 404)
        payload = request.get_json(force=True, silent=True) or {}
        path = [str(p)[:120] for p in (payload.get("path") or [])][:MAX_PATH_DEPTH]
        try:
            entry_id = int(payload.get("entry_id"))
        except (TypeError, ValueError):
            return _error("entry_id is required", 400)
        with _store(g.uid) as store:
            entry = store.get_entry(entry_id)
            if not entry:
                return _error("No such thought.", 404)
            try:
                analysis = entry["analysis"]
                if not analysis:
                    _spend_ai(store)
                    analysis = knowledge.analyze(entry["text"])
                    store.set_analysis(entry_id, analysis)
                subject, category = analysis["subject"], analysis["category"]
                # Keyed by subject and path only -- never the user or the
                # note -- so one person's "noodles" answer serves everyone.
                key = "explore:v1:" + hashlib.sha256(
                    json.dumps([knowledge.model, category, subject, path]).encode()).hexdigest()
                node = store.cache_get(key)
                if node is None:
                    _spend_ai(store)
                    node = knowledge.explore(subject, category, path)
                    store.cache_put(key, node)
            except AIError as e:
                return _ai_error(e)
        return jsonify({"subject": subject, "category": category, "path": path, "node": node})

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
