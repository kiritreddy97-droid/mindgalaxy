"""Build the demo galaxy from sample_data/journal_sample.json and export it
as a standalone HTML file at the project root (demo_galaxy.html)."""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mindgalaxy.engine import Entry, build_galaxy  # noqa: E402
from mindgalaxy.exporter import export_standalone  # noqa: E402

NOW = dt.datetime(2026, 8, 17, 9, 0, 0)


def main():
    raw = json.loads((ROOT / "sample_data" / "journal_sample.json").read_text())
    entries = [
        Entry(id=r["id"], text=r["text"], created_at=dt.datetime.fromisoformat(r["created_at"]))
        for r in raw
    ]
    galaxy = build_galaxy(entries, now=NOW)
    (ROOT / "sample_data" / "galaxy_demo.json").write_text(json.dumps(galaxy, indent=2))
    export_standalone(galaxy, ROOT / "demo_galaxy.html", title="Kirit's Mind Galaxy — Demo")
    print(f"Stars: {galaxy['count']}")
    print("Constellations:")
    for cid, info in galaxy["clusters"].items():
        print(f"  [{info['status']:7s}] {info['name']}  ({info['count']} stars)")
    shooting = [s for s in galaxy["stars"] if s["is_shooting_star"]]
    print(f"Shooting stars: {len(shooting)}")
    for s in shooting:
        print(f"  - {s['text'][:70]}...")
    print(f"\nExported -> {ROOT / 'demo_galaxy.html'}")


if __name__ == "__main__":
    main()
