import json
import subprocess
import sys
from pathlib import Path

import pytest

from mindgalaxy.cli import _split_markdown
from mindgalaxy.engine import Entry, build_galaxy
from mindgalaxy.exporter import export_standalone, render_html


def run_cli(args, db_path):
    return subprocess.run(
        [sys.executable, "-m", "mindgalaxy.cli", "--db", str(db_path), *args],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent.parent),
    )


def test_split_markdown_splits_on_blank_lines_and_headings():
    text = "# Heading One\nFirst paragraph here, long enough.\n\nSecond paragraph, also long enough.\n# Heading Two\nThird paragraph, long enough too."
    chunks = _split_markdown(text)
    assert len(chunks) == 3
    assert any("Heading One" in c for c in chunks)
    assert any("Second paragraph" in c for c in chunks)


def test_split_markdown_ignores_tiny_fragments():
    text = "hi\n\nThis one is long enough to count as a real entry."
    chunks = _split_markdown(text)
    assert len(chunks) == 1


def test_cli_add_and_stats(tmp_path):
    db_path = tmp_path / "cli.db"
    result = run_cli(["add", "My first thought about the garden"], db_path)
    assert result.returncode == 0, result.stderr
    assert "Added star #1" in result.stdout

    result = run_cli(["add", "A second, unrelated thought about spaceships"], db_path)
    assert result.returncode == 0
    assert "2 total" in result.stdout

    result = run_cli(["stats"], db_path)
    assert result.returncode == 0
    assert "Stars:       2" in result.stdout


def test_cli_import_from_markdown(tmp_path):
    db_path = tmp_path / "cli.db"
    md_file = tmp_path / "notes.md"
    md_file.write_text(
        "# Monday\nWent for a long run in the rain and enjoyed it a lot.\n\n"
        "# Tuesday\nPracticed guitar for half an hour after dinner today.\n"
    )
    result = run_cli(["import", str(md_file)], db_path)
    assert result.returncode == 0, result.stderr
    assert "Imported 2 new stars" in result.stdout


def test_cli_build_writes_json(tmp_path):
    db_path = tmp_path / "cli.db"
    run_cli(["add", "Thought one about hiking trails"], db_path)
    run_cli(["add", "Thought two about hiking trails again"], db_path)
    out_path = tmp_path / "galaxy.json"
    result = run_cli(["build", "-o", str(out_path)], db_path)
    assert result.returncode == 0, result.stderr
    data = json.loads(out_path.read_text())
    assert data["count"] == 2


def test_cli_export_creates_standalone_html(tmp_path):
    db_path = tmp_path / "cli.db"
    run_cli(["add", "A thought worth remembering about the mountains"], db_path)
    out_path = tmp_path / "snapshot.html"
    result = run_cli(["export", str(out_path)], db_path)
    assert result.returncode == 0, result.stderr
    html = out_path.read_text()
    assert "<html" in html.lower()
    assert "THREE" in html  # vendored three.js is inlined
    assert '"standalone"' in html


def test_export_on_empty_db_fails_gracefully(tmp_path):
    db_path = tmp_path / "empty.db"
    out_path = tmp_path / "snapshot.html"
    result = run_cli(["export", str(out_path)], db_path)
    assert result.returncode != 0
    assert not out_path.exists()


def test_render_html_server_mode_has_no_embedded_data():
    html = render_html({}, mode="server")
    assert '__MODE__' not in html
    assert '__GALAXY_DATA__' not in html
    assert '"server"' in html


def test_export_standalone_embeds_real_data(tmp_path):
    entries = [Entry(id=1, text="A thought about rivers and stones", created_at=__import__("datetime").datetime(2026, 1, 1))]
    galaxy = build_galaxy(entries)
    out = export_standalone(galaxy, tmp_path / "out.html", title="Test Galaxy")
    html = out.read_text()
    assert "Test Galaxy" in html
    assert "rivers and stones" in html
