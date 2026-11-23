"""Small text helpers shared by the pipeline stages."""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_WORD = re.compile(r"[a-z0-9]+")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'“])")
_TRACKING = re.compile(r"^(utm_|at_|fbclid$|gclid$|ref$|cmp$|ocid$|xtor$)", re.I)

STOPWORDS = frozenset(
    "the a an and or but of to in on at for from by with as is are was were be been has have had it its this that "
    "these those he she they we you his her their our will would can could may might should not no after before over "
    "under into out about than then there here who what when where which while also more most new says said say".split()
)


def clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", raw))).strip()


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING.match(k)]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def normalize(s: str) -> str:
    """Lower-case, alphanumerics only, single spaces. Used for matching, never shown."""
    return " ".join(_WORD.findall(s.lower()))


def tokens(s: str) -> list[str]:
    return [t for t in _WORD.findall(s.lower()) if len(t) > 2 and t not in STOPWORDS]


def sentences(s: str) -> list[str]:
    return [p.strip() for p in _SENT.split(s) if p.strip()]


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
