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
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

from flask import Flask, g, jsonify, redirect, request, send_from_directory, session

from . import auth
from .ai import MEDICAL, AIError, KnowledgeAI, QuotaError
from .engine import build_galaxy
from .calls import Calls
from .social import Media, Social, SocialError
from .exporter import render_html
from .storage import DEFAULT_DB_PATH, Storage

LOGIN_TEMPLATE = Path(__file__).resolve().parent / "templates" / "login.html"
AI_DAILY_LIMIT = int(os.environ.get("MINDGALAXY_AI_DAILY_LIMIT", "80"))
MAX_ENTRY_CHARS = 2000
MAX_PATH_DEPTH = 5
# Bump when the linking rules change, so older thoughts get re-checked.
LINK_VERSION = 2
# Idle sign-out: after 5 quiet minutes the page shows a 5-minute countdown;
# the server independently ends sessions untouched for longer than both.
IDLE_WARN_SECONDS = int(os.environ.get("MINDGALAXY_IDLE_WARN_SECONDS", str(5 * 60)))
IDLE_COUNTDOWN_SECONDS = int(os.environ.get("MINDGALAXY_IDLE_COUNTDOWN_SECONDS", str(5 * 60)))
IDLE_LIMIT = _dt.timedelta(seconds=IDLE_WARN_SECONDS + IDLE_COUNTDOWN_SECONDS + 60)


def _client_ip() -> str:
    # Vercel's edge overwrites these headers with the real client address, so
    # they're trustworthy there. Anywhere else a client could forge them to
    # dodge the per-network limits, so use the socket's address instead.
    if os.environ.get("VERCEL"):
        real = request.headers.get("X-Real-IP") or request.headers.get("X-Forwarded-For", "").split(",")[0]
        if real.strip():
            return real.strip()
    return request.remote_addr or "unknown"


_ice_cache: dict[str, Any] = {"at": 0.0, "servers": None}


def ice_servers() -> list[dict[str, Any]]:
    """How browsers find each other for calls. Public STUN always; plus
    Cloudflare's TURN relay (free up to 1,000 GB/month) when
    CF_TURN_KEY_ID and CF_TURN_API_TOKEN are set, for networks that block
    direct connections. TURN relays encrypted media it cannot read."""
    servers: list[dict[str, Any]] = [{"urls": ["stun:stun.cloudflare.com:3478", "stun:stun.l.google.com:19302"]}]
    key_id, token = os.environ.get("CF_TURN_KEY_ID"), os.environ.get("CF_TURN_API_TOKEN")
    if not (key_id and token):
        return servers
    if _ice_cache["servers"] and time.time() - _ice_cache["at"] < 3600:
        return servers + _ice_cache["servers"]
    import logging
    import urllib.error
    import urllib.request

    got: Any = None
    # the current endpoint, then the older one (both return {"iceServers": ...})
    for path in ("generate-ice-servers", "generate"):
        req = urllib.request.Request(
            f"https://rtc.live.cloudflare.com/v1/turn/keys/{key_id}/credentials/{path}",
            data=json.dumps({"ttl": 4 * 3600}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                got = json.loads(resp.read().decode()).get("iceServers")
            if got:
                break
        except urllib.error.HTTPError as e:
            # Cloudflare's own message; the key and token are never logged
            logging.getLogger("mindgalaxy.calls").warning(
                "Cloudflare TURN (%s) returned HTTP %s: %s", path, e.code, e.read().decode(errors="replace")[:300])
        except Exception as e:  # noqa: BLE001 -- calls still work on most networks without TURN
            logging.getLogger("mindgalaxy.calls").warning("Cloudflare TURN (%s) unreachable: %r", path, e)
    if not got:
        return servers
    got = got if isinstance(got, list) else [got]
    _ice_cache.update(at=time.time(), servers=got)
    return servers + got


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
    shared = store.family_shared_ids()
    index = {s["id"]: i for i, s in enumerate(galaxy["stars"])}
    medical = set()
    for i, s in enumerate(galaxy["stars"]):
        s["analysis"] = analyses.get(s["id"])
        s["share_family"] = s["id"] in shared
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
    app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024 + 64 * 1024  # media limit plus headroom
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
    # AI calls are slow network waits, so independent ones run side by side.
    _pool = ThreadPoolExecutor(max_workers=4)

    def _store(user_id: Optional[int] = None) -> Storage:
        return Storage(app.config["DB_PATH"], user_id=user_id)

    def _json_object() -> dict[str, Any]:
        """The request's JSON body if it's an object, else {} (lists, strings, junk)."""
        payload = request.get_json(force=True, silent=True)
        return payload if isinstance(payload, dict) else {}

    def _error(message: str, status: int):
        return jsonify({"error": message}), status

    def _ai_error(e: AIError):
        return _error(str(e), 429 if isinstance(e, QuotaError) else 502)

    def _signed_in() -> bool:
        """True while the session is live. A session stays signed in for as
        long as it's in use; once nothing has touched it for IDLE_LIMIT (the
        page's 5-minute idle wait plus its 5-minute countdown, plus slack) it
        is ended here too, so closing the tab can't leave it signed in."""
        if not session.get("uid"):
            return False
        now = time.time()
        if now - session.get("seen", 0) > IDLE_LIMIT.total_seconds():
            session.clear()
            return False
        if now - session.get("seen", 0) > 15:  # don't rewrite the cookie on every request
            session["seen"] = now
        return True

    def login_required(view: Callable) -> Callable:
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            if multi_user:
                if not _signed_in():
                    return _error("Please sign in.", 401)
                # JSON-only writes: a cross-site form can't send this content
                # type without a CORS preflight, which blocks CSRF. Encrypted
                # media uploads are raw bytes, so they carry a custom header
                # instead, which also forces a preflight.
                media_upload = (request.headers.get("X-MindGalaxy") == "1"
                                and request.mimetype == "application/octet-stream")
                if request.method == "POST" and not (request.is_json or media_upload):
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
        if multi_user and not _signed_in():
            return redirect("/login")
        return render_html({}, title="Galactic Connections", mode="server")

    static_dir = Path(__file__).resolve().parent / "static"
    site_files = {"icon.svg", "favicon.ico", "favicon-32.png", "apple-touch-icon.png", "icon-192.png",
                  "icon-512.png", "manifest.webmanifest"}

    @app.get("/<path:name>")
    def site_file(name: str):
        """The site icon and web-app manifest (anything else is a 404)."""
        if name not in site_files:
            return _error("Not found.", 404)
        resp = send_from_directory(static_dir, name, max_age=7 * 24 * 3600)
        if name.endswith(".webmanifest"):
            resp.mimetype = "application/manifest+json"
        return resp

    @app.get("/<any(universe, calls, tour):script>.js")
    def hosted_script(script: str):
        """The ecosystem, calls and tour scripts exist only on the hosted site."""
        if not multi_user:
            return app.response_class("", mimetype="text/javascript")
        js = (Path(__file__).resolve().parent / "templates" / f"{script}.js").read_text(encoding="utf-8")
        return app.response_class(js, mimetype="text/javascript")

    @app.get("/login")
    def login_page():
        if not multi_user or _signed_in():
            return redirect("/")
        return LOGIN_TEMPLATE.read_text(encoding="utf-8")

    # -- accounts --------------------------------------------------------
    def _auth(action: Callable) -> Any:
        if not multi_user:
            return _error("Accounts are only used on the hosted site.", 404)
        if not request.is_json:
            return _error("Expected a JSON request.", 415)
        payload = _json_object()
        try:
            with _store() as store:
                user = action(store, str(payload.get("username", "")), str(payload.get("pin", "")), _client_ip())
        except auth.AuthError as e:
            return _error(e.message, e.status)
        session.clear()
        session.permanent = True
        session["uid"] = user.id
        session["seen"] = time.time()
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
        tour_done = True
        if multi_user:
            with _store() as store:
                row = store.conn.execute("SELECT tour_done FROM users WHERE id = ?", (g.uid,)).fetchone()
            tour_done = bool(row and row[0])
        return jsonify({"username": username, "multi_user": multi_user, "ai": knowledge.enabled, "tour_done": tour_done,
                        "idle_warn_seconds": IDLE_WARN_SECONDS, "idle_countdown_seconds": IDLE_COUNTDOWN_SECONDS})

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
        payload = _json_object()
        text = payload.get("text")
        text = text.strip() if isinstance(text, str) else ""
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
            analysis = entry["analysis"]
            if analysis and analysis.get("linked") == LINK_VERSION:
                return jsonify({"analysis": analysis, "links": 0})
            # Resumable: if an earlier attempt classified the thought but ran
            # out of quota (or hit an outage) before linking, pick up there.
            try:
                if not analysis:
                    _spend_ai(store)
                    analysis = knowledge.analyze(entry["text"])
                    store.set_analysis(entry_id, analysis)
                new = {**_brief(entry_id, analysis), "text": entry["text"]}
                # Prepare the first level of the gas cloud *while* the links
                # are being worked out (the AI calls run side by side), so the
                # star is ready to explore the moment it appears.
                prefetch_key = _explore_key(analysis["subject"], analysis["category"], [])
                prefetch = None
                if store.cache_get(prefetch_key) is None:
                    try:
                        _spend_ai(store)
                        prefetch = _pool.submit(knowledge.explore, analysis["subject"], analysis["category"], [])
                    except QuotaError:
                        prefetch = None
                analyses = store.analyses()
                others = [{**_brief(e.id, analyses[e.id]), "text": e.text}
                          for e in store.all_entries() if e.id != entry_id and e.id in analyses][-150:]
                by_id = {o["id"]: o for o in others}
                links, unfinished = 0, False
                if others:
                    _spend_ai(store)
                    for link in knowledge.relate(new, others):
                        other = by_id.get(link["other_id"])
                        if other is None:  # never trust the model to stick to the ids offered
                            continue
                        if not link_allowed(link["kind"], new["category"], other["category"]):
                            continue
                        extra = None
                        if link["kind"] == "treated_at":
                            try:
                                extra = _verify_hospital(store, new, other)
                            except QuotaError:
                                raise
                            except AIError:
                                unfinished = True  # couldn't check right now; retry later
                                continue
                            if not extra:
                                continue
                        if store.add_link(entry_id, other["id"], link["kind"], link["reason"], extra):
                            links += 1
                if not unfinished:
                    analysis["linked"] = LINK_VERSION
                    store.set_analysis(entry_id, analysis)
            except AIError as e:
                return _ai_error(e)
            if prefetch is not None:
                try:
                    store.cache_put(prefetch_key, prefetch.result(timeout=90))
                except Exception:  # noqa: BLE001 -- it'll simply be fetched on click instead
                    pass
        return jsonify({"analysis": analysis, "links": links})

    def _explore_key(subject: str, category: str, path: list[str]) -> str:
        # Keyed by subject and path only -- never the user or the note -- so
        # one person's "noodles" answer serves everyone.
        return "explore:v3:" + hashlib.sha256(json.dumps([knowledge.name, category, subject, path]).encode()).hexdigest()

    def _explore_level(store: Storage, subject: str, category: str, path: list[str]) -> dict[str, Any]:
        key = _explore_key(subject, category, path)
        node = store.cache_get(key)
        if node is None:
            _spend_ai(store)
            node = knowledge.explore(subject, category, path)
            store.cache_put(key, node)
        return node

    @app.post("/api/explore")
    @login_required
    def api_explore():
        """One level of the drill-down gas cloud around a star."""
        if not knowledge.enabled:
            return _error("AI knowledge isn't configured on this server.", 404)
        payload = _json_object()
        raw_path = payload.get("path")
        path = [str(p)[:120] for p in raw_path][:MAX_PATH_DEPTH] if isinstance(raw_path, list) else []
        try:
            entry_id = int(payload.get("entry_id"))
            if not 0 < entry_id < 2**62:
                raise ValueError
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
                node = _explore_level(store, subject, category, path)
            except AIError as e:
                return _ai_error(e)
        return jsonify({"subject": subject, "category": category, "path": path, "node": node})

    @app.post("/api/ping")
    @login_required
    def api_ping():
        """Heartbeat from an active page: keeps the session alive while in use."""
        return jsonify({"ok": True, "idle_warn_seconds": IDLE_WARN_SECONDS,
                        "countdown_seconds": IDLE_COUNTDOWN_SECONDS})

    # -- the galaxy ecosystem (multi-user only; rules live in social.py) --
    def social_route(view: Callable) -> Callable:
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            if not multi_user:
                return _error("The galaxy ecosystem is only on the hosted site.", 404)
            try:
                with _store() as store:
                    return view(Social(store), g.uid, *args, **kwargs)
            except SocialError as e:
                return _error(e.message, e.status)
        return login_required(wrapper)

    def _body() -> dict[str, Any]:
        return _json_object()

    def _int(value: Any) -> Optional[int]:
        try:
            n = int(value)
        except (TypeError, ValueError):
            return None
        return n if 0 < n < 2**62 else None

    @app.get("/api/universe")
    @social_route
    def api_universe(social: Social, me: int):
        return jsonify(social.universe(me))

    @app.get("/api/users/search")
    @social_route
    def api_user_search(social: Social, me: int):
        return jsonify({"users": social.search(me, request.args.get("q", ""))})

    @app.post("/api/requests")
    @social_route
    def api_send_request(social: Social, me: int):
        b = _body()
        rid = social.send_request(me, str(b.get("to", "")), str(b.get("kind", "")), _int(b.get("family_id")))
        return jsonify({"id": rid}), 201

    @app.post("/api/requests/<int:request_id>/respond")
    @social_route
    def api_respond(social: Social, me: int, request_id: int):
        b = _body()
        return jsonify(social.respond(me, request_id, bool(b.get("accept")), b.get("role")))

    @app.post("/api/families/<int:family_id>/role")
    @social_route
    def api_family_role(social: Social, me: int, family_id: int):
        social.set_role(me, family_id, str(_body().get("role", "")))
        return jsonify({"ok": True})

    @app.post("/api/family-links")
    @social_route
    def api_family_link(social: Social, me: int):
        b = _body()
        family_id, their_family_id = _int(b.get("family_id")), _int(b.get("their_family_id"))
        if not family_id:
            return _error("Choose your family.", 400)
        return jsonify({"id": social.send_family_link(me, family_id, str(b.get("to", "")), their_family_id)}), 201

    @app.post("/api/tour/done")
    @login_required
    def api_tour_done():
        with _store() as store:
            store.conn.execute("UPDATE users SET tour_done = 1 WHERE id = ?", (g.uid,))
            store.conn.commit()
        return jsonify({"ok": True})

    # -- calls (peer-to-peer; the server only decides who may call whom) --
    @app.post("/api/presence")
    @social_route
    def api_presence(social: Social, me: int):
        Calls(social).set_presence(me, str(_body().get("peer_id", "")))
        return jsonify({"ok": True})

    def _names(value: Any) -> list[str]:
        return [str(n) for n in value][:12] if isinstance(value, list) else []

    @app.post("/api/calls/check")
    @social_route
    def api_call_check(social: Social, me: int):
        b = _body()
        Calls(social).check_group(me, _names(b.get("usernames")), str(b.get("kind", "")))
        return jsonify({"ok": True})

    @app.post("/api/calls")
    @social_route
    def api_call_create(social: Social, me: int):
        b = _body()
        return jsonify(Calls(social).create_room(me, _names(b.get("usernames")), str(b.get("kind", "")))), 201

    @app.get("/api/calls/<room_id>")
    @social_route
    def api_call_room(social: Social, me: int, room_id: str):
        return jsonify(Calls(social).room(me, room_id))

    @app.post("/api/calls/<room_id>/join")
    @social_route
    def api_call_join(social: Social, me: int, room_id: str):
        return jsonify(Calls(social).join(me, room_id, str(_body().get("peer_id", ""))))

    @app.post("/api/calls/<room_id>/leave")
    @social_route
    def api_call_leave(social: Social, me: int, room_id: str):
        Calls(social).leave(me, room_id)
        return jsonify({"ok": True})

    @app.get("/api/calls/ice")
    @login_required
    def api_ice():
        return jsonify({"iceServers": ice_servers()})

    @app.post("/api/requests/<int:request_id>/cancel")
    @social_route
    def api_cancel(social: Social, me: int, request_id: int):
        social.cancel_request(me, request_id)
        return jsonify({"ok": True})

    @app.post("/api/unfriend")
    @social_route
    def api_unfriend(social: Social, me: int):
        social.unfriend(me, str(_body().get("username", "")))
        return jsonify({"ok": True})

    @app.post("/api/block")
    @social_route
    def api_block(social: Social, me: int):
        social.block(me, str(_body().get("username", "")))
        return jsonify({"ok": True})

    @app.post("/api/unblock")
    @social_route
    def api_unblock(social: Social, me: int):
        social.unblock(me, str(_body().get("username", "")))
        return jsonify({"ok": True})

    @app.post("/api/report")
    @social_route
    def api_report(social: Social, me: int):
        return jsonify(social.report(me, str(_body().get("username", ""))))

    @app.post("/api/swallows/seen")
    @social_route
    def api_swallows_seen(social: Social, me: int):
        social.mark_swallows_seen(me)
        return jsonify({"ok": True})

    @app.post("/api/families")
    @social_route
    def api_create_family(social: Social, me: int):
        return jsonify({"id": social.create_family(me, str(_body().get("name", "")))}), 201

    @app.post("/api/families/<int:family_id>/leave")
    @social_route
    def api_leave_family(social: Social, me: int, family_id: int):
        social.leave_family_alone(me, family_id)
        return jsonify({"ok": True})

    @app.get("/api/chat/<username>")
    @social_route
    def api_chat_read(social: Social, me: int, username: str):
        after = _int(request.args.get("after")) or 0
        return jsonify({"messages": social.messages(me, username, after)})

    @app.post("/api/chat/<username>")
    @social_route
    def api_chat_send(social: Social, me: int, username: str):
        return jsonify({"id": social.send_message(me, username, str(_body().get("text", "")))}), 201

    @app.post("/api/keys")
    @social_route
    def api_set_key(social: Social, me: int):
        Media(social).set_key(me, str(_body().get("jwk", "")))
        return jsonify({"ok": True})

    @app.get("/api/keys/<username>")
    @social_route
    def api_get_key(social: Social, me: int, username: str):
        return jsonify({"jwk": Media(social).get_key(me, username)})

    @app.post("/api/chat/<username>/media")
    @social_route
    def api_send_media(social: Social, me: int, username: str):
        if request.mimetype != "application/octet-stream":
            return _error("Send the encrypted bytes as application/octet-stream.", 415)
        h = request.headers
        media_id = Media(social).send(me, username, h.get("X-Media-Kind", ""), h.get("X-Media-Mime", ""),
                                      h.get("X-Media-IV", ""), h.get("X-Media-Key", ""), request.get_data())
        return jsonify({"id": media_id}), 201

    @app.post("/api/media/<int:media_id>/open")
    @social_route
    def api_open_media(social: Social, me: int, media_id: int):
        m = Media(social).open_once(me, media_id)
        resp = app.response_class(m["data"], mimetype="application/octet-stream")
        resp.headers.update({"X-Media-Kind": m["kind"], "X-Media-Mime": m["mime"], "X-Media-IV": m["iv"],
                             "X-Media-Key": m["sender_key"], "Cache-Control": "no-store"})
        return resp

    @app.get("/api/galaxies/<username>/thoughts")
    @social_route
    def api_shared_thoughts(social: Social, me: int, username: str):
        return jsonify(social.visible_thoughts(me, username))

    @app.post("/api/entries/<int:entry_id>/share")
    @social_route
    def api_share(social: Social, me: int, entry_id: int):
        return jsonify(social.set_family_share(me, entry_id, bool(_body().get("family"))))

    @app.get("/api/health")
    def health():
        # Says only *whether* the call relay is set up and answering -- never
        # any credential -- so it can be checked without signing in.
        relay = any("turn:" in str(s.get("urls")) for s in ice_servers())
        return jsonify({"status": "ok", "ai": knowledge.enabled, "call_relay": relay})

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
