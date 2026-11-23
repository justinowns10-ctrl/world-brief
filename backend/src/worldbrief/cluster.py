"""Stage 3: group articles about the same event. Done in code, not by the chat model.

The first real run used plain word overlap and split one summit into two
stories and one naval attack into seven. Two changes fix most of that:

* Names carry the signal. Words in the headline count three times; proper
  nouns, acronyms and the countries a report mentions are added as their own,
  heavily weighted features. "COP31", "Benghazi" and "Kallas" identify an
  event far better than "talks" or "attack".
* Average-link clustering. A report joins a group only if it resembles the
  group's members on average, which stops chains of loosely related reports
  from forming one story, and the result does not depend on arrival order.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter

import numpy as np

from .geo import countries_in
from .ingest import full_text
from .text import STOPWORDS, tokens

log = logging.getLogger("worldbrief.cluster")

_NAME = re.compile(r"\b(?:[A-Z][a-zA-Z]+|[A-Z]{2,}\d*|\d+[A-Za-z]+)\b")
BODY_CHARS = 600


def event_features(article: dict) -> Counter:
    title, body = article["title"], article["text"][:BODY_CHARS]
    features: Counter = Counter()
    for t in tokens(title):
        features[t] += 3
    for t in tokens(body):
        features[t] += 1
    for name in _NAME.findall(title):
        if name.lower() not in STOPWORDS:
            features["#" + name.lower()] += 3
    for name in _NAME.findall(body):
        if name.lower() not in STOPWORDS:
            features["#" + name.lower()] += 1
    for country in countries_in(f"{title} {body}"):
        features["@" + country] += 2
    return features


def feature_vectors(articles: list[dict]) -> np.ndarray:
    """TF-IDF over event features, unit length."""
    docs = [event_features(a) for a in articles]
    df: Counter = Counter()
    for d in docs:
        df.update(d.keys())
    vocab = {term: i for i, term in enumerate(df)}
    n = len(articles)
    matrix = np.zeros((n, max(len(vocab), 1)), dtype=np.float32)
    for row, d in enumerate(docs):
        for term, count in d.items():
            matrix[row, vocab[term]] = (1 + math.log(count)) * math.log((1 + n) / (1 + df[term]) + 1)
    return _unit(matrix)


def _unit(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def average_link(vectors: np.ndarray, threshold: float) -> list[list[int]]:
    """Agglomerative clustering: repeatedly merge the two groups whose members
    are most alike on average, until no pair reaches the threshold."""
    n = len(vectors)
    sim = (vectors @ vectors.T).astype(np.float64)
    np.fill_diagonal(sim, -1.0)
    members: dict[int, list[int]] = {i: [i] for i in range(n)}
    active = np.ones(n, dtype=bool)
    while True:
        masked = np.where(np.outer(active, active), sim, -1.0)
        flat = int(np.argmax(masked))
        a, b = divmod(flat, n)
        if masked[a, b] < threshold:
            break
        na, nb = len(members[a]), len(members[b])
        merged = (na * sim[a] + nb * sim[b]) / (na + nb)     # average linkage update
        sim[a, :] = merged
        sim[:, a] = merged
        sim[a, a] = -1.0
        active[b] = False
        members[a].extend(members.pop(b))
    return [sorted(group) for group in members.values()]


_EVENT_CODE = re.compile(r"\b[A-Z]{1,5}-?\d{1,4}\b")       # COP31, G20, MH370: names of specific events or things


def event_codes(article: dict) -> set[str]:
    return set(_EVENT_CODE.findall(f"{article['title']} {article['text'][:BODY_CHARS]}"))


def merge_on_event_codes(groups: list[list[int]], articles: list[dict]) -> list[list[int]]:
    """Joins groups whose reports name the same coded event in a headline or
    opening. A summit is one development however differently outlets word it:
    'COP31 talks collapse' and 'Climate summit fails' (which names COP31 in
    its first line) belong together."""
    codes = [set().union(*(event_codes(articles[i]) for i in group)) for group in groups]
    merged = True
    while merged:
        merged = False
        for a in range(len(groups)):
            for b in range(a + 1, len(groups)):
                if codes[a] & codes[b]:
                    groups[a] = sorted(groups[a] + groups[b])
                    codes[a] |= codes[b]
                    del groups[b], codes[b]
                    merged = True
                    break
            if merged:
                break
    return groups


def cluster_articles(articles: list[dict], model, embedding_threshold: float, event_threshold: float) -> tuple[list[list[dict]], str]:
    """Returns (clusters, method). Each cluster is ordered by publication time."""
    if not articles:
        return [], "none"
    vectors, method, threshold = None, "names and word overlap", event_threshold
    try:
        embedded = model.embed([full_text(a) for a in articles])
        if embedded is not None and len(embedded) == len(articles):
            vectors, method, threshold = _unit(np.asarray(embedded, dtype=np.float32)), "embedding", embedding_threshold
    except Exception as exc:
        log.warning("embedding failed, using names and word overlap instead: %s", exc)
    if vectors is None:
        vectors = feature_vectors(articles)
    groups = merge_on_event_codes(average_link(vectors, threshold), articles)
    clusters = [sorted((articles[i] for i in group), key=lambda a: (a["published_at"], a["id"])) for group in groups]
    clusters.sort(key=lambda c: (c[0]["published_at"], c[0]["id"]))
    return clusters, method
