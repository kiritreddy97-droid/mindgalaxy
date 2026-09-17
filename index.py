"""
Vercel entrypoint.

Vercel's Python builder looks for a Flask `app` object in one of a fixed
set of files (app.py, index.py, server.py, main.py, ...) at the repo root.
mindgalaxy uses an application-factory pattern (mindgalaxy.app.create_app),
so this thin wrapper exposes the WSGI app where Vercel can find it, and
points the sqlite storage at /tmp, the only writable directory in a
serverless function. Note: data will not persist across invocations there.
"""
import os

from mindgalaxy.app import create_app

db_path = os.environ.get("MINDGALAXY_DB_PATH", "/tmp/mindgalaxy.db")
app = create_app(db_path=db_path)
