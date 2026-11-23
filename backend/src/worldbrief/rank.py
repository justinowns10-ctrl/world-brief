"""Stage 4: decide which events matter and where they belong."""
from __future__ import annotations

import logging
from collections import Counter

from . import REGION_SECTIONS, SECTIONS
from .ingest import independent_source_count
from .lm import BudgetExceeded, LMError

log = logging.getLogger("worldbrief.rank")

RANK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["events"],
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["cluster_id", "section", "importance", "countries", "reason"],
                "properties": {
                    "cluster_id": {"type": "integer"},
                    "section": {"type": "string", "enum": SECTIONS},
                    "importance": {"type": "integer", "minimum": 1, "maximum": 5},
                    "countries": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
            },
        }
    },
}

RANK_SYSTEM = (
    "You are the ranking step of an international news briefing. For each numbered event, choose one section and "
    "rate its importance from 1 (minor) to 5 (major). Judge by humanitarian, geopolitical, economic and scientific "
    "consequences and long-term significance, not by how much attention it gets in United States media. "
    "Place an event in a regional section by where it happens; use a topic section only when the story is mainly "
    "about science, technology, energy, international economics or humanitarian response. Events in North America, "
    "Oceania or Central Asia go in other_regions. List the countries involved. Use only the information given. "
    "Reply with JSON only."
)


def describe_clusters(clusters: list[list[dict]], feeds_by_id: dict) -> list[dict]:
    out = []
    for cid, articles in enumerate(clusters):
        hints = Counter(
            feeds_by_id[a["source_id"]].region_hint
            for a in articles
            if a["source_id"] in feeds_by_id and feeds_by_id[a["source_id"]].region_hint
        )
        independent = independent_source_count(articles)
        newest = max(a["published_at"] for a in articles)
        out.append({
            "cluster_id": cid,
            "headlines": [a["title"] for a in articles[:3]],
            "sources": sorted({a["source_id"] for a in articles}),
            "independent_sources": independent,
            "articles": len(articles),
            "newest": newest,
            "hint": hints.most_common(1)[0][0] if hints else None,
            "prescore": independent * 2 + len(articles) * 0.5,
        })
    return out


def rank_events(descriptions: list[dict], model, max_candidates: int, batch_size: int = 20) -> dict[int, dict]:
    """Returns {cluster_id: {section, importance, countries}}. A failed batch falls
    back to a rule so ranking never stops the run."""
    candidates = sorted(descriptions, key=lambda d: (d["prescore"], d["newest"]), reverse=True)[:max_candidates]
    results: dict[int, dict] = {}
    for start in range(0, len(candidates), batch_size):
        batch = candidates[start:start + batch_size]
        lines = []
        for d in batch:
            lines.append(
                f"Event {d['cluster_id']} ({d['independent_sources']} independent source(s): {', '.join(d['sources'])})\n"
                + "\n".join(f"  - {h}" for h in d["headlines"])
            )
        valid_ids = {d["cluster_id"] for d in batch}
        try:
            reply = model.chat_json("rank", RANK_SYSTEM, "\n\n".join(lines), RANK_SCHEMA, meta=batch)
            for event in reply["events"]:
                if event["cluster_id"] in valid_ids:
                    results[event["cluster_id"]] = {
                        "section": event["section"], "importance": event["importance"],
                        "countries": [c for c in event["countries"] if isinstance(c, str)][:6],
                    }
        except BudgetExceeded:
            log.warning("ranking: model call budget used up; remaining events ranked by rule")
        except LMError as exc:
            log.warning("ranking batch failed, ranked by rule instead: %s", exc)
        for d in batch:
            results.setdefault(d["cluster_id"], {
                "section": d["hint"] or "other_regions",
                "importance": min(5, 1 + d["independent_sources"]),
                "countries": [],
                "by_rule": True,
            })
    return results


def select_events(descriptions: list[dict], ranking: dict[int, dict], max_stories: int, per_section: int) -> list[int]:
    """Picks cluster ids for the briefing.

    Regions are not forced to be equal, but a region with any event of
    importance 2 or more gets at least one slot before the rest is filled by
    importance. This stops well-covered regions crowding out the others.
    """
    by_id = {d["cluster_id"]: d for d in descriptions}
    ordered = sorted(
        ranking, key=lambda cid: (ranking[cid]["importance"], by_id[cid]["prescore"], by_id[cid]["newest"]), reverse=True
    )
    chosen: list[int] = []
    counts: Counter = Counter()
    for section in REGION_SECTIONS:
        if section == "other_regions":
            continue
        for cid in ordered:
            if ranking[cid]["section"] == section and ranking[cid]["importance"] >= 2:
                chosen.append(cid)
                counts[section] += 1
                break
    for cid in ordered:
        if len(chosen) >= max_stories:
            break
        section = ranking[cid]["section"]
        if cid in chosen or counts[section] >= per_section:
            continue
        chosen.append(cid)
        counts[section] += 1
    chosen = chosen[:max_stories]
    return sorted(chosen, key=lambda cid: ordered.index(cid))
