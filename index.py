"""
Vercel entrypoint.

Vercel's Python builder looks for a Flask `app` object in one of a fixed
set of files (app.py, index.py, server.py, main.py, ...) at the repo root.
mindgalaxy uses an application-factory pattern (mindgalaxy.app.create_app),
so this thin wrapper exposes the WSGI app where Vercel can find it.

The hosted site is multi-user: everyone signs up with a username and a
4-digit passkey and gets their own private galaxy. Project environment
variables (see README.md, "Deploying to Vercel"):

* SECRET_KEY         -- required; signs login sessions.
* TURSO_DATABASE_URL / TURSO_AUTH_TOKEN -- required for accounts and
                        entries to persist (without them storage falls back
                        to /tmp, which is wiped on every cold start).
* GEMINI_API_KEY / GROQ_API_KEY / ... -- optional, free; turn on AI gas
                        clouds and truly-related links (see README.md).
"""
import os

from flask import Flask

from mindgalaxy.app import create_app

db_path = os.environ.get("MINDGALAXY_DB_PATH", "/tmp/mindgalaxy.db")
secret_key = os.environ.get("SECRET_KEY")

if secret_key:
    app = create_app(db_path=db_path, multi_user=True, secret_key=secret_key)
else:
    # Fail loudly and clearly rather than serving a site where anyone could
    # forge a login session.
    app = Flask(__name__)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def not_configured(path):
        return ("MindGalaxy isn't configured yet: set the SECRET_KEY environment "
                "variable in the Vercel project settings, then redeploy.", 500)
