# MindGalaxy

**Turn your journal, notes, or ideas into a living, navigable 3D galaxy of your own thinking.**

Every entry you write becomes a star. Stars that mean similar things drift near each other. Related thoughts are connected by faint constellation lines. Themes you write about often cluster into named constellations. A theme you were once obsessed with and haven't touched in months fades into a dormant, ghostly cluster — a supernova remnant. And every so often, a thought comes along that connects to nothing else you've ever written: a shooting star, rendered in gold.

It's a small, local tool for noticing the shape of your own mind over time.

![MindGalaxy screenshot](docs/screenshot.png)

## Why this is different

The core is **not** a wrapper around an LLM API. Run locally, there's no API key, no network call, no per-entry cost, and your writing never leaves your machine. (The optional hosted site can add a free AI provider on top for richer gas clouds; see [The hosted site](#the-hosted-site-private-galaxies-and-ai-gas-clouds).) Every "smart" behavior — where a thought is positioned, which thoughts are related, what a theme should be called, whether a theme has gone quiet, which thoughts are genuinely novel — comes from small, fast, fully local, fully inspectable unsupervised machine learning:

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

## Gas clouds: knowledge around every star

Each star now glows with a **gas cloud** — one coloured nebula per facet of what the thought is about. Click a star and the camera flies to it, the nebulae get labelled, and the side panel lets you explore each facet:

| You write… | The gas cloud shows |
|---|---|
| "I love to cook", "I like to eat" | Cuisines (Italian, Indian, Mexican, East Asian, Middle Eastern) — each dish with its place of origin, ingredients, recipe steps and approximate nutrition |
| "I love milk", "I need to buy milk" | Types of milk, plant milks, things made from milk (paneer, yogurt, butter, ghee, mozzarella) and dishes with milk — with calories, protein, fat, calcium and recipes |
| "I feel like buying a car" | Cars by speed, mileage, seating and country of origin (0–60, top speed, mpg/range, seats, price) |
| "I need a watch", "lost track of time" | Luxury Swiss, automatic, quartz/digital and smartwatches (origin, movement, price, water resistance) |
| house, hospital, school, university, marriage, wife/husband, sexual health, pregnancy, birth, child, technology, phones, health, disease | Curated facets for each (types, origins, checklists, milestones, warning signs…) |
| "solve 2x + 3 = 11", "what is 15% of 240" | A worked, step-by-step solution (arithmetic, percentages, linear and quadratic equations) |
| anything else | A live Wikipedia lookup (overview + related ideas), fetched in the browser only when you open that star |

**Interconnections.** Thoughts whose topics are the same or related are joined by teal dashed lines — even when they share no words. "I love milk" links to "I like to cook" (*milk is a base for sauces, desserts, curries and chai*) and to "we are pregnant" (*calcium needs rise; avoid unpasteurized dairy*). The panel lists every interconnected thought with the reason.

The curated knowledge lives in `mindgalaxy/knowledge_base.py` as plain data — add a topic (keywords + facets + items) or a line to `RELATIONS` and it lights up automatically. Topic detection, the maths solver and the interconnection graph are in `mindgalaxy/knowledge.py`. Figures such as prices, specs and calories are typical approximate values, and the health topics are general information, not medical advice.

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
│   ├── knowledge.py     # topic detection, maths solver, topic interconnections
│   ├── knowledge_base.py # curated gas-cloud knowledge (19 topics)
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

## The hosted site: private galaxies and AI gas clouds

Deployed on Vercel, MindGalaxy is multi-user. Everyone signs up with a **username and a 4-digit passkey** and only ever sees their own galaxy.

A 4-digit passkey has only 10,000 possible values, so the protection is rate limiting, not the passkey itself: an account locks for 15 minutes after 5 wrong passkeys, a network may make at most 30 failed sign-ins an hour, and at most 5 sign-ups a day. Passkeys are stored as salted PBKDF2 hashes. Don't reuse a bank or phone PIN.

**Idle sign-out.** You stay signed in for as long as you're using the site. After 5 minutes with no mouse movement, taps, scrolling or typing, a pop-up counts down another 5 minutes; any activity cancels it, and when it reaches zero you're signed out. Activity in any open tab counts, and the server enforces the same limit on its own, so closing the tab doesn't leave you signed in. (`MINDGALAXY_IDLE_WARN_SECONDS` / `MINDGALAXY_IDLE_COUNTDOWN_SECONDS` change the timings.)

**History calendar.** The 📅 History button opens a month calendar of your thoughts. Days you wrote on glow brighter the more you wrote; pick one to list that day's thoughts and dim every other star in the galaxy.

**AI knowledge (free by default).** With a free AI provider configured (below), the knowledge layer (`mindgalaxy/ai.py`, `mindgalaxy/free_ai.py`) does the following:

- **Explore any subject, level by level.** Write "I like to eat noodles" and the star's gas cloud opens on the countries with a real noodle tradition. Pick Japan and it shows the kinds of noodle used there (wheat, thick wheat, buckwheat…), then dish styles (soup like ramen, stir-fried like yakisoba…), then the dishes themselves with their origin, key facts, ingredients and a home recipe. The same works for cement, diseases, cars or anything else. Every level is cached and shared (keyed by subject, never by user or note), so the second person to explore noodles costs nothing.
- **Lines only between thoughts that are truly related.** Each new thought is classified, then compared with your earlier ones, and linked only when there's a direct, specific connection, with the reason shown. Symptom, disease and hospital stars get *only* these links: a symptom connects to a disease only if it's a recognised sign of it, and a hospital connects to a disease only if it's renowned for treating that disease. That's then checked against the hospital's Wikipedia article (or a live web search when Claude is the provider).
- **Hospital bursts.** Select a disease or hospital star with a verified link and gas bursts out of the hospital star, with the specialist department beside it and a card linking to the hospital's official website (from Wikidata) or find-a-doctor page. MindGalaxy never names individual doctors, and never shows a URL the AI wrote itself.
- Medical gas clouds always say they're general information, not a diagnosis.

Free providers are tried in order, and when one is rate-limited or out of quota the next one answers:

| Provider | Env var | Free allowance (at the time of writing) |
|---|---|---|
| [Google Gemini](https://aistudio.google.com/app/apikey) | `GEMINI_API_KEY` | ~1,500 requests/day on Flash models. Free-tier prompts may be used by Google to improve its products. |
| [Groq](https://console.groq.com/keys) | `GROQ_API_KEY` | ~1,000 requests/day |
| [Cerebras](https://cloud.cerebras.ai/) | `CEREBRAS_API_KEY` | free tier, very fast |
| [Mistral](https://console.mistral.ai/api-keys) | `MISTRAL_API_KEY` | large monthly allowance; free-mode prompts may be used for training unless you opt out |
| [OpenRouter](https://openrouter.ai/keys) | `OPENROUTER_API_KEY` | ~50 requests/day on `:free` models |
| [NVIDIA NIM](https://build.nvidia.com/) | `NVIDIA_API_KEY` | free with the developer program |
| Any OpenAI-compatible endpoint | `FREE_AI_BASE_URL`, `FREE_AI_API_KEY`, `FREE_AI_MODEL` | |

Models can be overridden with `GEMINI_MODEL`, `GROQ_MODEL`, etc. None need a credit card; see [awesome-free-llm-apis](https://github.com/mnfst/awesome-free-llm-apis) for more. Claude is an optional, paid last resort: install with `pip install mindgalaxy[claude]` (or add `anthropic` to `requirements.txt`) and set `ANTHROPIC_API_KEY`. Each account gets 80 new AI lookups a day (`MINDGALAXY_AI_DAILY_LIMIT`). With no provider configured, everything still works using the offline curated knowledge.

## The galaxy ecosystem

Every signed-in user's galaxy floats in a shared universe around yours, labelled with their username; zoom out to see them. Only a galaxy's owner can open it. Click a galaxy (or search in **✉ Galaxies**) to:

- **Befriend** it. When they accept, a string joins your soul to theirs and you can chat (text, emoji, anything).
- **Become life partners** (both accept): you can each read all of the other's thoughts.
- **Form a family** of up to 9 galaxies: members see only thoughts their owner switches to *Share with family*, and the AI keeps 18+ and violent thoughts from ever being shared there.
- **Become enemies** (both accept): a black hole appears on the string between you. Each side can report the other once a day; after 5 reports the black hole swallows that galaxy (everyone involved sees it happen). The pair is cut apart forever: their chat and media are destroyed and neither can ever send the other a request again.
- **Leave** partnership, family or enmity only when both agree. **Block** always works one-sided and instantly: it ends any status and hides chat, requests and shared thoughts between the two, and deletes nothing.

**Media in chat is view-once and end-to-end encrypted.** Photos show for 10 seconds; audio and video play once. Each browser keeps a private key (ECDH P-256, never exported) and media is encrypted with AES-GCM before it leaves the sender's device. The server stores only ciphertext and deletes it the moment it's opened, or after 7 days unopened. Limits: 4 MB per file; media can only be opened on the device the recipient last used the site on; and nothing can stop someone photographing their screen.

## Deploying to Vercel

`index.py` is the Vercel entrypoint. In your Vercel project → **Settings → Environment Variables**, add:

| Variable | Required | What it's for |
|---|---|---|
| `SECRET_KEY` | yes | Signs login sessions. Any long random string, e.g. `python -c "import secrets; print(secrets.token_hex(32))"`. Without it the site shows a "not configured" page rather than running insecurely. |
| `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN` | yes, in practice | A free [Turso](https://turso.tech) database, so accounts and thoughts survive. Without them storage falls back to `/tmp`, which is wiped on every cold start. |
| `GROQ_API_KEY`, `GEMINI_API_KEY` (and/or the other free providers) | recommended | Turn on the AI features above, at no cost. Groq is tried first (fastest), then Gemini. |

Then redeploy. New tables and columns are created in Turso automatically on first use; thoughts saved before accounts existed aren't shown to any account.

## Privacy

The local CLI and `mindgalaxy serve` never call out to the network, except for the Wikipedia lookup when you open a star that matches no curated topic (a few keywords, never the full text). Your entries live in a local SQLite file, and exported HTML snapshots work fully offline.

On the hosted site, thoughts are stored in the site's Turso database. With an AI provider configured, each new thought is sent to that provider to classify it and find related thoughts; exploring a gas cloud sends only its subject (such as "noodles"), never the note. Free tiers may use what's sent to improve their models.

## License

MIT — see [LICENSE](LICENSE).
