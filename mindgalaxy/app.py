"""
mindgalaxy.app
================

A tiny Flask app that serves the live, always-current galaxy: the 3D
visualization page plus a JSON API that recomputes the galaxy from
whatever is currently in the database.
"""
from __future__ import annotations

import datetime as _dt

from flask import Flask, jsonify, request

from .engine import build_galaxy
from .exporter import render_html
from .storage import DEFAULT_DB_PATH, Storage


def create_app(db_path: str = str(DEFAULT_DB_PATH)) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path

    def _store() -> Storage:
        return Storage(app.config["DB_PATH"])

    @app.get("/")
    def index():
        return render_html({}, title="My Mind Galaxy", mode="server")

    @app.get("/api/stars")
    def api_stars():
        with _store() as store:
            entries = store.all_entries()
        galaxy = build_galaxy(entries)
        return jsonify(galaxy)

    @app.post("/api/entries")
    def api_add_entry():
        payload = request.get_json(force=True, silent=True) or {}
        text = (payload.get("text") or "").strip()
        if not text:
            return jsonify({"error": "text is required"}), 400
        with _store() as store:
            entry_id = store.add(text, _dt.datetime.utcnow())
            count = store.count()
        return jsonify({"id": entry_id, "count": count}), 201

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
