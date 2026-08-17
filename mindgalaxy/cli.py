"""
mindgalaxy.cli
================

Command-line interface for MindGalaxy.

    mindgalaxy add "Text of a thought or journal entry"
    mindgalaxy import notes.md
    mindgalaxy build
    mindgalaxy serve
    mindgalaxy export snapshot.html
    mindgalaxy stats
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import webbrowser
from pathlib import Path

from .engine import build_galaxy
from .exporter import export_standalone
from .storage import DEFAULT_DB_PATH, Storage


def _split_markdown(text: str) -> list[str]:
    """Split a markdown/plain-text file into individual entries.

    Splits on blank lines and on '# heading' boundaries, so a single
    freeform journal file becomes many separate stars.
    """
    text = text.replace("\r\n", "\n")
    # Break before headings so each heading starts a new chunk. (A callback
    # replacement is used, not a r"...\x00..." template string, because the
    # re module's template mini-language treats "\x00" as an invalid escape
    # rather than a literal NUL character.)
    text = re.sub(r"\n(#{1,6}\s)", lambda m: "\n\x00" + m.group(1), text)
    chunks = [c.strip() for c in text.split("\x00")]
    entries: list[str] = []
    for chunk in chunks:
        for para in re.split(r"\n\s*\n", chunk):
            para = para.strip()
            if len(para) >= 8:
                entries.append(para)
    return entries


def cmd_add(args: argparse.Namespace) -> None:
    with Storage(args.db) as store:
        entry_id = store.add(" ".join(args.text))
        print(f"✦ Added star #{entry_id} to your galaxy ({store.count()} total).")


def cmd_import(args: argparse.Namespace) -> None:
    path = Path(args.file)
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)
    texts = _split_markdown(path.read_text(encoding="utf-8"))
    with Storage(args.db) as store:
        ids = store.add_many(texts)
        print(f"✦ Imported {len(ids)} new stars from {path.name} ({store.count()} total).")


def cmd_stats(args: argparse.Namespace) -> None:
    with Storage(args.db) as store:
        entries = store.all_entries()
    galaxy = build_galaxy(entries)
    print(f"Stars:       {galaxy['count']}")
    print(f"Constellations:")
    for cid, info in galaxy["clusters"].items():
        badge = "●" if info["status"] == "active" else "○ (dormant)"
        print(f"  {badge} {info['name']}  —  {info['count']} stars")
    shooting = [s for s in galaxy["stars"] if s["is_shooting_star"]]
    if shooting:
        print(f"Shooting stars (novel, unconnected thoughts): {len(shooting)}")


def cmd_build(args: argparse.Namespace) -> None:
    with Storage(args.db) as store:
        entries = store.all_entries()
    galaxy = build_galaxy(entries)
    out = Path(args.output)
    out.write_text(json.dumps(galaxy, indent=2), encoding="utf-8")
    print(f"✦ Built galaxy.json with {galaxy['count']} stars -> {out}")


def cmd_export(args: argparse.Namespace) -> None:
    with Storage(args.db) as store:
        entries = store.all_entries()
    if not entries:
        print("No entries yet — add some with `mindgalaxy add \"...\"` first.", file=sys.stderr)
        sys.exit(1)
    galaxy = build_galaxy(entries)
    out = export_standalone(galaxy, args.output, title=args.title)
    print(f"✦ Exported standalone galaxy -> {out}")
    if args.open:
        webbrowser.open(out.resolve().as_uri())


def cmd_serve(args: argparse.Namespace) -> None:
    from .app import create_app

    app = create_app(db_path=args.db)
    url = f"http://{args.host}:{args.port}"
    print(f"✦ MindGalaxy is live at {url}  (Ctrl+C to stop)")
    if args.open:
        webbrowser.open(url)
    app.run(host=args.host, port=args.port, debug=False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mindgalaxy",
        description="Turn your notes and journal entries into a navigable 3D galaxy of your own thinking.",
    )
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to the SQLite database file.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add a single entry (a thought/star) to your galaxy.")
    p_add.add_argument("text", nargs="+", help="The text of the entry.")
    p_add.set_defaults(func=cmd_add)

    p_import = sub.add_parser("import", help="Import many entries from a markdown/text file.")
    p_import.add_argument("file", help="Path to a .md or .txt file; blank lines and headings split entries.")
    p_import.set_defaults(func=cmd_import)

    p_stats = sub.add_parser("stats", help="Print a summary of your galaxy.")
    p_stats.set_defaults(func=cmd_stats)

    p_build = sub.add_parser("build", help="Compute the galaxy and write it to a JSON file.")
    p_build.add_argument("-o", "--output", default="galaxy.json", help="Output JSON path.")
    p_build.set_defaults(func=cmd_build)

    p_export = sub.add_parser("export", help="Export a standalone, shareable HTML snapshot.")
    p_export.add_argument("output", help="Output HTML path.")
    p_export.add_argument("--title", default="My Mind Galaxy", help="Title shown in the page.")
    p_export.add_argument("--open", action="store_true", help="Open the exported file in a browser.")
    p_export.set_defaults(func=cmd_export)

    p_serve = sub.add_parser("serve", help="Serve a live, always-up-to-date galaxy in your browser.")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", default=5000, type=int)
    p_serve.add_argument("--open", action="store_true", help="Open the app in a browser on start.")
    p_serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
