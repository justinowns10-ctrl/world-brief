"""Stage 3: group articles about the same event. Done in code, not by the chat model."""
from __future__ import annotations

import logging
import math
from collections import Counter

import numpy as np

from .ingest import full_text
from .text import tokens

log = logging.getLogger("worldbrief.cluster")


def lexical_vectors(texts: list[str]) -> np.ndarray:
    """TF-IDF vectors, unit length. Fallback when no embedding model is configured."""
    docs = [Counter(tokens(t)) for t in texts]
    df = Counter()
    for d in docs:
        df.update(d.keys())
    vocab = {term: i for i, term in enumerate(df)}
    matrix = np.zeros((len(texts), max(len(vocab), 1)), dtype=np.float32)
    n = len(texts)
    for row, d in enumerate(docs):
        for term, count in d.items():
            matrix[row, vocab[term]] = (1 + math.log(count)) * math.log((1 + n) / (1 + df[term]) + 1)
    return _unit(matrix)


def _unit(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def cluster_articles(articles: list[dict], model, embedding_threshold: float, lexical_threshold: float) -> tuple[list[list[dict]], str]:
    """Returns (clusters, method). Greedy: each article joins the closest existing
    cluster above the threshold, otherwise starts a new one."""
    if not articles:
        return [], "none"
    texts = [full_text(a) for a in articles]
    vectors, method, threshold = None, "lexical", lexical_threshold
    try:
        embedded = model.embed(texts)
        if embedded is not None and len(embedded) == len(texts):
            vectors, method, threshold = _unit(np.asarray(embedded, dtype=np.float32)), "embedding", embedding_threshold
    except Exception as exc:
        log.warning("embedding failed, using word statistics instead: %s", exc)
    if vectors is None:
        vectors = lexical_vectors(texts)

    order = sorted(range(len(articles)), key=lambda i: articles[i]["published_at"])
    centroids: list[np.ndarray] = []
    members: list[list[int]] = []
    for i in order:
        v = vectors[i]
        best, best_sim = -1, threshold
        for c, centroid in enumerate(centroids):
            sim = float(v @ centroid) / (float(np.linalg.norm(centroid)) or 1.0)
            if sim >= best_sim:
                best, best_sim = c, sim
        if best == -1:
            centroids.append(v.copy())
            members.append([i])
        else:
            members[best].append(i)
            centroids[best] = centroids[best] + v
    return [[articles[i] for i in group] for group in members], method
