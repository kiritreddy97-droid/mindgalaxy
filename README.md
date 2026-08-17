# MindGalaxy

**Turn your journal, notes, or ideas into a living, navigable 3D galaxy of your own thinking.**

Every entry you write becomes a star. Stars that mean similar things drift near each other. Related thoughts are connected by faint constellation lines. Themes you write about often cluster into named constellations. A theme you were once obsessed with and haven't touched in months fades into a dormant, ghostly cluster — a supernova remnant. And every so often, a thought comes along that connects to nothing else you've ever written: a shooting star, rendered in gold.

It's a small, local tool for noticing the shape of your own mind over time.

![MindGalaxy screenshot](docs/screenshot.png)

## Why this is different

This is **not** a wrapper around an LLM API. There's no API key, no network call, no per-entry cost, and your writing never leaves your machine. Every "smart" behavior — where a thought is positioned, which thoughts are related, what a theme should be called, whether a theme has gone quiet, which thoughts are genuinely novel — comes from small, fast, fully local, fully inspectable unsupervised machine learning:

```
your text
    │
    ▼
TF-IDF vectorization           (what words matter, weighted by how distinctive they are)
    │
    ▼
TruncatedSVD → 3D coordinates  (semantic space, compressed down to a place in the galaxy)
    │
    ▼
k-means clustering             (thoughts that use similar language become a "constellation")
    │
    ▼
cosine similarity              (novelty scores + the constellation graph)
```

It runs in well under a second for hundreds of entries, works completely offline once installed, and the whole pipeline is about 150 lines of readable code in `mindgalaxy/engine.py` — nothing is hidden behind an API boundary.

**A note on honesty**: bag-of-words methods cluster on shared *vocabulary*, not deep meaning. A project with distinctive, recurring words (character names, a hobby's jargon) separates out crisply. Everyday, wide-vocabulary journaling blends together more. That's a real, explainable property of the algorithm, not a bug being papered over — see [How it works](#how-it-works) below.

## Features

- **A 3D galaxy you can fly through** — drag to rotate, scroll to zoom, click any star to read the entry, hover to preview.
- **Auto-named constellations** — themes are discovered and labeled automatically from the words that make each one distinctive (not just frequent).
- **Dormancy detection** — a theme you wrote about steadily and then abandoned is flagged and rendered faded, like a fading star.
- **Shooting stars** — entries that are genuine outliers relative to everything else you've written are highlighted in gold.
- **Time-lapse replay** — watch your galaxy form, star by star, in the order you actually wrote it.
- **Search** — filter your galaxy by keyword; matching stars light up, everything else fades.
- **Two ways to view it**: a live local web server (`mindgalaxy serve`) that always reflects your current entries, or a single self-contained HTML file (`mindgalaxy export`) you can save, share, or email — no server required, works completely offline (three.js is vendored inline, not loaded from a CDN).
- **A real CLI and a real SQLite database** — your entries live in one portable `.db` file.

## Installation

Requires Python 3.10+.

```bash
git clone <this-repo>
cd mindgalaxy
pip install -r requirements.txt
```

## Quick start

```bash
# Add a few thoughts
mindgalaxy add "Started sketching out a new side project tonight."
mindgalaxy add "Ran five miles for the first time since spring."
mindgalaxy add "Called my sister, she's doing well in her new apartment."

# Or import a whole journal / notes file at once
# (splits on blank lines and markdown headings)
mindgalaxy import my_journal.md

# See a quick text summary
mindgalaxy stats

# Launch the live, interactive galaxy in your browser
mindgalaxy serve --open

# ...or export a single shareable HTML file, no server needed
mindgalaxy export my_galaxy.html --open
```

### Try the demo first

Don't want to write real entries yet? A ready-made demo galaxy is included — a fictional six-month journal spanning a novel-writing project that fades out, learning guitar, training for a half marathon, family calls, and a couple of genuinely odd 2am thoughts:

```bash
python3 scripts/build_demo.py
open demo_galaxy.html   # or just double-click it
```

## Every command

| Command | What it does |
|---|---|
| `mindgalaxy add "text"` | Add a single entry. |
| `mindgalaxy import file.md` | Import many entries from a markdown/text file (splits on blank lines and `#` headings). |
| `mindgalaxy stats` | Print a text summary: constellations, sizes, dormancy, shooting stars. |
| `mindgalaxy build -o galaxy.json` | Compute the galaxy and write the raw JSON. |
| `mindgalaxy export out.html [--open]` | Export a standalone, fully offline HTML snapshot. |
| `mindgalaxy serve [--open]` | Serve a live galaxy at `http://127.0.0.1:5000` that stays in sync with your database. |

All commands accept `--db path/to/file.db` (defaults to `~/.mindgalaxy/galaxy.db`).

## How it works

**Position.** Entries are vectorized with TF-IDF (term frequency, weighted down for words that appear in almost everything — "the", "today", "just"). That vector space is compressed to 3 dimensions with truncated SVD (the same technique behind classic Latent Semantic Analysis), and the result becomes the star's `(x, y, z)` position. Entries using similar language end up near each other.

**Constellations.** The same vectors are clustered with k-means. The number of clusters starts from a standard rule-of-thumb (`k ≈ √(n/2)`) and is nudged ±1 by silhouette score — deliberately conservative, because silhouette score alone tends to keep climbing as k approaches the entry count on short, wordy text, which would over-fragment the galaxy into dozens of tiny, meaningless clusters. Each cluster is named after the terms that are most *distinctive* to it (mean TF-IDF inside the cluster minus mean TF-IDF outside it) rather than simply its highest-weighted terms, which tend to surface generic words that score reasonably high everywhere.

**Dormancy.** For any constellation with a steady historical cadence, if the time since its last entry is much longer than its typical gap (and at least 30 days), it's marked dormant and rendered faded — a theme that used to be active and has gone quiet.

**Novelty / shooting stars.** For every entry, novelty is `1 − (similarity to its closest neighbor)`. Rather than an arbitrary fixed cutoff (which misfires badly on naturally low-similarity prose), an entry is flagged as a shooting star only if its novelty is a genuine statistical outlier *within that galaxy* — above the 90th percentile and at least one standard deviation above the median, capped at a small handful per galaxy.

**Brightness.** Recency is modeled as exponential decay with a 45-day half-life, so what you wrote about this week is vivid and what you wrote about last year is dim — without ever disappearing.

## Project layout

```
mindgalaxy/
├── mindgalaxy/
│   ├── engine.py       # the whole ML pipeline (TF-IDF → SVD → k-means → graph)
│   ├── storage.py       # SQLite-backed entry storage
│   ├── exporter.py      # renders the galaxy template (standalone or server mode)
│   ├── cli.py            # command-line interface
│   ├── app.py            # Flask app for `mindgalaxy serve`
│   └── vendor/three.min.js  # vendored so exports work fully offline
├── templates/galaxy.html # the entire interactive 3D UI (vanilla JS + three.js)
├── sample_data/           # a generated demo journal + its precomputed galaxy
├── scripts/build_demo.py  # builds demo_galaxy.html from sample_data
└── tests/                 # pytest suite: engine, storage, CLI, exporter, Flask app
```

## Running the tests

```bash
pip install pytest
pytest tests/ -v
```

## Privacy

Nothing here calls out to the network at runtime. Your entries live in a local SQLite file. Exported HTML snapshots are single files with the visualization library embedded inline — open one on a plane, no connection required.

## License

MIT — see [LICENSE](LICENSE).
