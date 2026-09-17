"""
Vercel entrypoint.

Vercel's Python builder looks for a Flask `app` object in one of a fixed
set of files (app.py, index.py, server.py, main.py, ...) at the repo root.
mindgalaxy uses an application-factory pattern (mindgalaxy.app.create_app),
so this thin wrapper exposes the WSGI app where Vercel can find it.

Storage: if TURSO_DATABASE_URL (and TURSO_AUTH_TOKEN) are set as Vercel
project environment variables, entries persist in that Turso (libSQL)
database and survive across invocations -- see README.md, "Deploying to
Vercel". Without them, this falls back to /tmp, the only writable directory
in a serverless function, which does NOT persist across invocations: added
thoughts will disappear on the next cold start.
"""
import os

from mindgalaxy.app import create_app

db_path = os.environ.get("MINDGALAXY_DB_PATH", "/tmp/mindgalaxy.db")
app = create_app(db_path=db_path)
