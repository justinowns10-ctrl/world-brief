"""Stage 1 and 2: fetch feeds, normalize entries, mark duplicates and wire copy."""
from __future__ import annotations

import calendar
import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import httpx

from .config import Feed
from .text import canonical_url, clean_text, jaccard, normalize, tokens

log = logging.getLogger("worldbrief.ingest")

USER_AGENT = "WorldBrief/0.1 (personal news reader)"
MAX_FEED_BYTES = 5_000_000
_WIRE = re.compile(r"\((Reuters|AP|AFP|dpa|EFE|Xinhua|ANSA|PTI)\)|\b(Reuters|Associated Press|Agence France-Presse)\b")


def fetch_feed(feed: Feed, timeout_s: float = 20.0) -> bytes:
    """Returns raw feed bytes. Anything that is not http(s) is read as a local file path (used by tests)."""
    url = feed.url
    if not url.startswith(("http://", "https://")):
        return Path(url).read_bytes()
    with httpx.Client(timeout=timeout_s, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        response = client.get(url)
        response.raise_for_status()
        if len(response.content) > MAX_FEED_BYTES:
            raise ValueError(f"feed is larger than {MAX_FEED_BYTES} bytes")
        return response.content


def _entry_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
    return None


def parse_feed(feed: Feed, raw: bytes) -> list[dict]:
    return parse_feed_detailed(feed, raw)[0]


def parse_feed_detailed(feed: Feed, raw: bytes) -> tuple[list[dict], dict]:
    """Turns one feed into normalized article records, plus facts about the feed
    itself. Entries without a link, title or date are skipped: an undated report
    cannot be placed in a daily window. Malformed XML is tolerated: whatever
    entries the parser can recover are used, and the damage is reported."""
    parsed = feedparser.parse(raw)
    info = {
        "bytes": len(raw),
        "entries": len(parsed.entries),
        "malformed": bool(parsed.get("bozo")),
        "parse_error": str(parsed.get("bozo_exception"))[:200] if parsed.get("bozo") else None,
        "format": parsed.get("version") or None,
    }
    out = []
    for entry in parsed.entries:
        try:
            url = (entry.get("link") or "").strip()
            title = clean_text(entry.get("title"))
            when = _entry_time(entry)
            if not url.startswith(("http://", "https://")) or not title or when is None:
                continue
            body = clean_text(entry.get("summary") or entry.get("description"))
            canon = canonical_url(url)
            out.append({
                "id": hashlib.sha1(canon.encode()).hexdigest()[:12],
                "source_id": feed.id,
                "url": url,
                "canonical_url": canon,
                "title": title,
                "text": body,
                "published_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
            })
        except Exception as exc:  # one bad entry must not lose the feed
            log.warning("feed %s: skipped an entry: %s", feed.id, exc)
    info["usable"] = len(out)
    info["skipped"] = info["entries"] - len(out)
    info["newest"] = max((a["published_at"] for a in out), default=None)
    info["oldest"] = min((a["published_at"] for a in out), default=None)
    info["median_text_chars"] = sorted(len(a["text"]) for a in out)[len(out) // 2] if out else 0
    return out, info


def probe_feed(feed: Feed, timeout_s: float = 20.0) -> dict:
    """Fetches and parses one feed and reports what happened. Never raises."""
    result = {"id": feed.id, "url": feed.url, "ok": False}
    try:
        raw = fetch_feed(feed, timeout_s)
    except httpx.HTTPStatusError as exc:
        result["error"] = f"HTTP {exc.response.status_code}"
        return result
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        return result
    try:
        _, info = parse_feed_detailed(feed, raw)
    except Exception as exc:
        result["error"] = f"could not be parsed: {type(exc).__name__}: {str(exc)[:160]}"
        return result
    result.update(info)
    if info["usable"] == 0:
        result["error"] = ("no usable entries" + (f" (malformed: {info['parse_error']})" if info["malformed"] else
                                                   " (not a feed, empty, or entries lack link/title/date)"))
    else:
        result["ok"] = True
    return result


def full_text(article: dict) -> str:
    title, body = article["title"], article["text"]
    if not body:
        return title
    return f"{title}. {body}" if not title.endswith((".", "!", "?")) else f"{title} {body}"


def mark_duplicates(articles: list[dict]) -> None:
    """Sets article['role'] and article['dup_of'] in place.

    - same normalized title, or near-identical text, from a different outlet -> 'syndicated' copy
    - text credits a wire agency -> 'wire', with article['wire'] naming the agency
    Copies stay in the set (they are real links) but do not count as independent sources.
    """
    ordered = sorted(articles, key=lambda a: a["published_at"])
    seen_titles: dict[str, dict] = {}
    kept: list[tuple[set, dict]] = []
    for a in ordered:
        a["role"], a["dup_of"], a["wire"] = "original", None, None
        match = _WIRE.search(full_text(a))
        if match:
            a["role"] = "wire"
            a["wire"] = (match.group(1) or match.group(2)).lower()
        key = normalize(a["title"])
        shingles = set(tokens(full_text(a)))
        original = seen_titles.get(key)
        if original is None:
            for other_shingles, other in kept:
                if len(shingles) >= 8 and jaccard(shingles, other_shingles) >= 0.8:
                    original = other
                    break
        if original is not None:
            a["dup_of"] = original["id"]
            if a["role"] != "wire":
                a["role"] = "syndicated"
            if original.get("wire") and not a["wire"]:
                a["wire"] = original["wire"]
        else:
            seen_titles[key] = a
            kept.append((shingles, a))


def independent_source_count(articles: list[dict]) -> int:
    """Outlets that reported in their own words. All copies of one wire report count once."""
    keys = set()
    for a in articles:
        if a.get("wire"):
            keys.add("wire:" + a["wire"])
        elif a.get("role") == "syndicated":
            continue
        else:
            keys.add("src:" + a["source_id"])
    return len(keys)
