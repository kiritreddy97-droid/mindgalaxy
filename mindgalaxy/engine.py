"""
mindgalaxy.engine
==================

The semantic core of MindGalaxy. Given a list of text entries, this module
computes an entire "galaxy": a 3D position for every entry (its star), a
thematic cluster ("constellation") with an auto-generated name, a novelty
score that flags genuinely new lines of thinking ("shooting stars"), a
recency-based brightness so recent thoughts glow and old ones dim, a
nearest-neighbour graph of "constellation lines" connecting related
thoughts, and a dormancy flag for themes that used to be active and have
gone quiet ("supernova remnants").

Everything is classic, local, fully-inspectable unsupervised NLP:

    text  --TF-IDF-->  sparse vectors
          --TruncatedSVD-->  3D coordinates
          --KMeans (auto-k via silhouette)-->  thematic clusters
          --cosine similarity-->  novelty + constellation graph

No external AI API, no network call, no API key. It runs entirely offline.
"""
from __future__ import annotations

import datetime as _dt
import warnings
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import TruncatedSVD
from sklearn.exceptions import ConvergenceWarning
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_similarity

# On small or repetitive inputs, k-means is sometimes asked for more
# clusters than there are genuinely distinct points -- harmless here (it
# just settles for fewer clusters than requested), so the warning is
# suppressed to keep this a quiet library rather than a noisy one.
warnings.filterwarnings("ignore", category=ConvergenceWarning)

# Tokenizing "don't", "I've", "it's" etc. splits off fragments like "don",
# "ve", "isn" that sklearn's stock English stop list doesn't cover (it only
# covers the standalone contraction word, not the split pieces). Left in,
# these swamp cluster names with junk like "Don · Lighthouse · Know".
_CONTRACTION_FRAGMENTS = {
    "don", "doesn", "didn", "isn", "wasn", "weren", "aren", "won", "wouldn",
    "couldn", "shouldn", "hasn", "haven", "hadn", "ain", "ve", "ll", "re",
    "im", "ive", "youre", "theyre", "dont", "didnt", "doesnt", "cant",
}
STOP_WORDS = frozenset(ENGLISH_STOP_WORDS) | _CONTRACTION_FRAGMENTS


@dataclass
class Entry:
    """A single unit of thought: one journal entry, note, or line of text."""

    id: int
    text: str
    created_at: _dt.datetime


def _choose_k(vectors: np.ndarray) -> int:
    """
    Pick the number of thematic clusters.

    Silhouette score alone is unreliable here: on short, vocabulary-diverse
    text, it tends to climb monotonically as k approaches n (each cluster
    shrinks toward a single, trivially "tight" point), which would pick the
    largest k allowed rather than the most natural one. Instead we start
    from a standard rule-of-thumb cluster count (k ~ sqrt(n / 2), a common
    heuristic for k-means when no better signal is available) and use
    silhouette only to nudge that estimate up or down by one -- enough to
    adapt to the data without runaway over-fragmentation.
    """
    n = vectors.shape[0]
    if n < 6:
        return 1
    base = max(2, min(8, int(round((n / 2) ** 0.5))))
    candidates = sorted({k for k in (base - 1, base, base + 1) if 2 <= k < n})
    best_k, best_score = base, -1.0
    for k in candidates:
        try:
            km = KMeans(n_clusters=k, n_init=10, random_state=42).fit(vectors)
            if len(set(km.labels_)) < 2:
                continue
            score = silhouette_score(vectors, km.labels_)
        except Exception:
            continue
        if score > best_score:
            best_k, best_score = k, score
    return best_k


def _cluster_names(vectorizer: TfidfVectorizer, dense_tfidf: np.ndarray,
                    labels: np.ndarray, top_n: int = 3) -> dict[int, str]:
    """
    Name each cluster after the terms that are most *distinctive* to it --
    scored by (mean tf-idf inside the cluster) minus (mean tf-idf outside
    it) -- rather than simply the highest-weighted terms in the cluster
    centroid, which tend to surface generic words ("way", "good", "new")
    that score reasonably high everywhere.
    """
    terms = np.array(vectorizer.get_feature_names_out())
    names: dict[int, str] = {}
    for c in sorted(set(labels.tolist())):
        mask = labels == c
        if mask.sum() == 0:
            continue
        in_mean = dense_tfidf[mask].mean(axis=0)
        out_mask = ~mask
        out_mean = dense_tfidf[out_mask].mean(axis=0) if out_mask.any() else np.zeros_like(in_mean)
        distinctiveness = in_mean - out_mean
        top_idx = distinctiveness.argsort()[::-1][:top_n]
        top_terms = [terms[i] for i in top_idx if terms[i].strip() and distinctiveness[i] > 0]
        names[int(c)] = " · ".join(w.title() for w in top_terms]) or f"Theme {c}"
    return names


def _cluster_status(entries: list[Entry], labels: np.ndarray, now: _dt.datetime) -> dict[int, str]:
    """
    Detect dormant themes: clusters that had a steady cadence of entries and
    have since gone quiet for much longer than their historical gap. These
    render as faded "supernova remnants" in the galaxy.
    """
    status: dict[int, str] = {}
    for c in sorted(set(labels.tolist())):
        idxs = [i for i, lab in enumerate(labels) if lab == c]
        if len(idxs) < 3:
            status[int(c)] = "active"
            continue
        dates = sorted(entries[i].created_at for i in idxs)
        gaps = [
            (dates[i + 1] - dates[i]).total_seconds() / 86400.0
            for i in range(len(dates) - 1)
        ]
        avg_gap = sum(gaps) / len(gaps) if gaps else 0.0
        last_age = (now - dates[-1]).total_seconds() / 86400.0
        if avg_gap > 0 and last_age > max(2 * avg_gap, 30):
            status[int(c)] = "dormant"
        else:
            status[int(c)] = "active"
    return status


def _fit_tfidf(texts: list[str]) -> tuple[TfidfVectorizer, Any]:
    """
    Fit a TF-IDF vectorizer, preferring settings tuned for normal journal
    text (unigrams, terms shared by >= 2 entries, common words dropped) but
    falling back to maximally permissive settings if that pruning happens to
    wipe out the entire vocabulary. That can genuinely happen on small or
    highly repetitive inputs -- e.g. a handful of near-identical entries
    where every word is either "too common" or "too rare" by the stricter
    thresholds -- and it's a real corpus, not an error, so we degrade
    gracefully instead of crashing.
    """
    n = len(texts)
    min_df = 2 if n >= 12 else 1
    max_df = 0.9 if n >= 5 else 1.0
    try:
        vectorizer = TfidfVectorizer(
            max_df=max_df, min_df=min_df, stop_words=list(STOP_WORDS),
            ngram_range=(1, 1), sublinear_tf=True,
        )
        tfidf = vectorizer.fit_transform(texts)
        if tfidf.shape[1] == 0:
            raise ValueError("empty vocabulary after pruning")
    except ValueError:
        vectorizer = TfidfVectorizer(
            max_df=1.0, min_df=1, stop_words=list(STOP_WORDS),
            ngram_range=(1, 1), sublinear_tf=True,
        )
        tfidf = vectorizer.fit_transform(texts)
    return vectorizer, tfidf


def _simple_top_words(text: str, top_n: int = 3) -> list[str]:
    """A dependency-free fallback for naming a "galaxy" of just one star,
    where fitting a whole TF-IDF model would be overkill."""
    import re

    words = [w for w in re.findall(r"[A-Za-z']{3,}", text.lower()) if w not in STOP_WORDS]
    seen: list[str] = []
    for w in words:
        if w not in seen:
            seen.append(w)
        if len(seen) >= top_n:
            break
    return seen


def build_galaxy(
    entries: list[Entry],
    now: Optional[_dt.datetime] = None,
    half_life_days: float = 45.0,
) -> dict[str, Any]:
    """
    Run the full MindGalaxy pipeline over a list of Entry objects and return
    a JSON-serializable dict: `{stars, edges, clusters, generated_at, count}`.
    """
    now = now or _dt.datetime.utcnow()
    n = len(entries)
    if n == 0:
        return {"stars": [], "edges": [], "clusters": {}, "generated_at": now.isoformat(), "count": 0}

    if n == 1:
        # A single star has nothing to be positioned relative to, clustered
        # with, or compared against -- skip the whole ML pipeline.
        entry = entries[0]
        name = " · ".join(w.title() for w in _simple_top_words(entry.text)) or "First Light"
        ages_days = max(0.0, (now - entry.created_at).total_seconds() / 86400.0)
        brightness = 0.35 + 0.65 * np.exp(-np.log(2) * ages_days / half_life_days)
        star = {
            "id": entry.id, "text": entry.text, "created_at": entry.created_at.isoformat(),
            "x": 0.0, "y": 0.0, "z": 0.0, "cluster": 0, "cluster_name": name,
            "cluster_status": "active", "novelty": 0.0, "brightness": float(brightness),
            "magnitude": 1.0, "is_shooting_star": False,
        }
        return {
            "stars": [star], "edges": [],
            "clusters": {"0": {"name": name, "count": 1, "status": "active"}},
            "generated_at": now.isoformat(), "count": 1,
        }

    texts = [e.text for e in entries]

    # Unigrams only: bigrams and one-off words are so sparse on short,
    # naturally-varied prose that they add noise rather than signal and
    # fragment what should be single themes into many tiny ones.
    vectorizer, tfidf = _fit_tfidf(texts)
    dense = tfidf.toarray()

    # TruncatedSVD needs at least 2 features; pad a *copy* with an inert
    # zero column on the rare inputs whose vocabulary collapses to just one
    # surviving term. Clustering and cluster naming keep using the
    # unpadded `dense`, since its columns must stay aligned with
    # `vectorizer`'s vocabulary (the padded column doesn't correspond to
    # any real term).
    svd_input = dense if dense.shape[1] >= 2 else np.hstack(
        [dense, np.zeros((dense.shape[0], 2 - dense.shape[1]))]
    )

    # --- position: project semantic space down to 3D -----------------
    n_components = max(1, min(3, min(svd_input.shape) - 1))
    svd = TruncatedSVD(n_components=n_components, random_state=42)
    coords = svd.fit_transform(svd_input)
    if coords.shape[1] < 3:
        coords = np.hstack([coords, np.zeros((coords.shape[0], 3 - coords.shape[1]))])
    coords = coords - coords.mean(axis=0)
    scale = np.abs(coords).max() or 1.0
    coords = coords / scale * 40.0

    # --- theme: cluster into constellations ---------------------------
    if n >= 6:
        k = max(1, min(_choose_k(dense), n - 1))
        labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit(dense).labels_ if k > 1 else np.zeros(n, dtype=int)
    else:
        labels = np.zeros(n, dtype=int)

    cluster_names = _cluster_names(vectorizer, dense, labels)
    cluster_status = _cluster_status(entries, labels, now)

    # --- relationships: cosine similarity graph ------------------------
    sims = np.clip(cosine_similarity(tfidf), -1.0, 1.0)
    np.fill_diagonal(sims, 0.0)
    novelty = (1.0 - sims.max(axis=1)) if n > 1 else np.zeros(n)

    # "Shooting stars" are entries that stand out as unusually disconnected
    # from everything else -- not just "the top X%" of an arbitrary scale,
    # but genuine statistical outliers relative to *this* galaxy's own
    # similarity distribution (journal prose is naturally low-similarity,
    # so an absolute cutoff would misfire; percentile + spread does not).
    shooting = np.zeros(n, dtype=bool)
    if n >= 8:
        med, std = float(np.median(novelty)), float(np.std(novelty))
        cutoff = max(np.percentile(novelty, 90), med + 1.0 * std)
        candidate_idx = np.where(novelty >= cutoff)[0]
        max_shooting = max(1, min(6, round(0.08 * n)))
        candidate_idx = candidate_idx[np.argsort(novelty[candidate_idx])[::-1]][:max_shooting]
        shooting[candidate_idx] = True

    edges: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    k_neighbors = 2 if n > 6 else 1
    for i in range(n):
        order = np.argsort(sims[i])[::-1][:k_neighbors]
        for j in order:
            j = int(j)
            if i == j or sims[i, j] <= 0.05:
                continue
            key = (min(i, j), max(i, j))
            if key in seen:
                continue
            seen.add(key)
            edges.append({
                "source": i,
                "target": j,
                "weight": float(sims[i, j]),
                "type": "constellation" if labels[i] == labels[j] else "bridge",
            })

    # --- time: recency-based brightness --------------------------------
    ages_days = np.clip(
        np.array([(now - e.created_at).total_seconds() / 86400.0 for e in entries]), 0, None
    )
    brightness = 0.35 + 0.65 * np.exp(-np.log(2) * ages_days / half_life_days)

    connectivity = np.zeros(n)
    for e in edges:
        connectivity[e["source"]] += 1
        connectivity[e["target"]] += 1
    magnitude = 1.0 + np.log1p(connectivity)

    stars = []
    for i, entry in enumerate(entries):
        c = int(labels[i])
        stars.append({
            "id": entry.id,
            "text": entry.text,
            "created_at": entry.created_at.isoformat(),
            "x": float(coords[i, 0]),
            "y": float(coords[i, 1]),
            "z": float(coords[i, 2]),
            "cluster": c,
            "cluster_name": cluster_names.get(c, f"Theme {c}"),
            "cluster_status": cluster_status.get(c, "active"),
            "novelty": float(novelty[i]),
            "brightness": float(brightness[i]),
            "magnitude": float(magnitude[i]),
            "is_shooting_star": bool(shooting[i]),
        })

    clusters_out = {
        str(c): {
            "name": cluster_names.get(c, f"Theme {c}"),
            "count": int((labels == c).sum()),
            "status": cluster_status.get(c, "active"),
        }
        for c in sorted(set(labels.tolist()))
    }

    return {
        "stars": stars,
        "edges": edges,
        "clusters": clusters_out,
        "generated_at": now.isoformat(),
        "count": n,
    }
