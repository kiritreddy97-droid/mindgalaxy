"""
MindGalaxy
==========

Turn a stream of text entries (journal notes, ideas, tweets, standup logs —
anything) into a living, navigable 3D galaxy of your own thinking.

Fully local. No API keys, no network calls, no external AI service.
Every "smart" behaviour here — semantic positioning, thematic clustering,
novelty detection, dormancy detection — is produced by classic, inspectable
unsupervised NLP (TF-IDF, truncated SVD, k-means, cosine similarity)
running entirely on your machine.
"""

from .engine import Entry, build_galaxy

__all__ = ["Entry", "build_galaxy"]
__version__ = "1.0.0"
