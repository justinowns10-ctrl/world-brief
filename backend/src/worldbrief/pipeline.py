"""Runs the stages in order and publishes one briefing.

Failure handling: every feed, every event and every model call is isolated.
A failure is logged to the run history and the run carries on with what it has.
When the time limit or the model-call budget is reached, the stories finished
so far are published and the briefing says so.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from importlib import resources
from pathlib import Path

import jsonschema

from . import PIPELINE_VERSION, REGION_SECTIONS, db
from .cluster import cluster_articles
from .config import Config
from .ingest import fetch_feed, independent_source_count, mark_duplicates, parse_feed
from .lm import BudgetExceeded, LMError
from .rank import describe_clusters, rank_events, select_events
from .summarize import choose_passages, draft_event
from .text import clean_text
from .validate import unseen_numbers, valid_event_date, validate_event

log = logging.getLogger("worldbrief.pipeline")

MAX_ARTICLES_LISTED = 8


def load_schema() -> dict:
    return json.loads(resources.files("worldbrief").joinpath("briefing.schema.json").read_text(encoding="utf-8"))


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ingest_feeds(cfg: Config, conn, note) -> dict:
    stats = {"feeds_ok": 0, "feeds_failed": 0, "articles_new": 0}
    for feed in cfg.feeds:
        try:
            db.upsert_source(conn, feed)
            records = parse_feed(feed, fetch_feed(feed))
            new = sum(db.insert_article(conn, r) for r in records)
            conn.commit()
            stats["feeds_ok"] += 1
            stats["articles_new"] += new
            note("ingest", "info", f"{feed.id}: {len(records)} entries, {new} new")
        except Exception as exc:
            conn.rollback()
            stats["feeds_failed"] += 1
            note("ingest", "error", f"{feed.id}: failed, skipped: {exc}")
    return stats


def build_story(story_id: str, articles: list[dict], passages: list[dict], draft: dict, checked: dict,
                rank: dict, window_start: date, today: date) -> dict:
    listed = [p["article"] for p in passages]
    for a in sorted(articles, key=lambda a: a["published_at"]):
        if a not in listed and len(listed) < MAX_ARTICLES_LISTED:
            listed.append(a)
    source_text = " ".join(p["text"] for p in passages)
    independent = independent_source_count(articles)
    claims = []
    for n, c in enumerate(checked["claims"], start=1):
        claims.append({
            "id": f"c{n}", "text": c["text"], "support": c["support"], "note": c["note"],
            "evidence": [{"articleId": e["passage"]["article"]["id"], "quote": e["quote"]} for e in c["evidence"]],
        })
    partial = sum(1 for c in claims if c["support"] == "partial")
    dropped = sum(1 for a in checked["audit"] if not a["published"])

    def analysis(value):
        text = clean_text(value)
        if not text or unseen_numbers(text, source_text):
            return None
        return text

    notes = []
    drafted_uncertainty = analysis(draft.get("uncertainty"))
    if drafted_uncertainty:
        notes.append(drafted_uncertainty)
    if checked["conflict"]:
        notes.append("Sources conflict: " + (checked["conflict_note"] or "the cited reports disagree on a material point."))
    if independent <= 1:
        notes.append("Based on a single independent source.")
    if partial:
        notes.append(f"{partial} statement(s) could only be partly confirmed against the cited passages.")
    if dropped:
        notes.append(f"{dropped} drafted statement(s) were removed because the cited passages did not support them.")
    if not checked["checked_by_model"]:
        notes.append("The automatic consistency check did not run for this story.")

    if checked["conflict"]:
        status = "disputed"
    elif independent >= 2 and partial == 0 and checked["checked_by_model"]:
        status = "verified"
    else:
        status = "preliminary"

    times = sorted(a["published_at"] for a in listed)
    return {
        "id": story_id,
        "section": rank["section"],
        "headline": clean_text(draft.get("headline"))[:160] or passages[0]["title"],
        "countries": rank.get("countries", []),
        "eventDate": valid_event_date(draft.get("event_date"), window_start, today),
        "firstReportedAt": times[0],
        "lastReportedAt": times[-1],
        "status": status,
        "importance": rank["importance"],
        "topStory": False,
        "summary": " ".join(c["text"] for c in claims),
        "claims": claims,
        "whyItMatters": analysis(draft.get("why_it_matters")),
        "context": analysis(draft.get("context")),
        "uncertainty": " ".join(notes) or None,
        "independentSourceCount": independent,
        "articles": [
            {"id": a["id"], "sourceId": a["source_id"], "title": a["title"], "url": a["url"],
             "publishedAt": a["published_at"], "role": a.get("role", "original")}
            for a in listed
        ],
    }


def run_pipeline(cfg: Config, model, conn, briefing_date: str | None = None, now: datetime | None = None,
                 fetch: bool = True) -> dict | None:
    """Produces and stores one briefing. Returns it, or None if nothing could be published."""
    now = now or datetime.now(timezone.utc)
    briefing_id = briefing_date or now.date().isoformat()
    deadline = time.monotonic() + cfg.limits.max_run_minutes * 60
    started = time.monotonic()
    run_id = db.start_run(conn, briefing_id)
    stats: dict = {"model": model.name}
    coverage_notes: list[str] = []

    def note(stage: str, level: str, message: str) -> None:
        (log.warning if level == "error" else log.info)("[%s] %s", stage, message)
        db.log_event(conn, run_id, stage, level, message)

    try:
        if fetch:
            stats.update(ingest_feeds(cfg, conn, note))
            if stats["feeds_failed"]:
                coverage_notes.append(f"{stats['feeds_failed']} of {len(cfg.feeds)} feeds could not be read.")
        window_start = now - timedelta(hours=cfg.window.hours)
        articles = [a for a in db.articles_since(conn, iso(window_start), cfg.limits.max_articles)
                    if a["published_at"] <= iso(now)]
        stats["articles_considered"] = len(articles)
        if not articles:
            note("ingest", "error", "no articles in the time window; nothing to publish")
            db.finish_run(conn, run_id, "empty", stats)
            return None

        mark_duplicates(articles)
        clusters, method = cluster_articles(articles, model, cfg.clustering.embedding_threshold,
                                            cfg.clustering.lexical_threshold)
        stats.update(clusters=len(clusters), clustering=method)
        note("cluster", "info", f"{len(articles)} articles grouped into {len(clusters)} events ({method})")

        feeds_by_id = {f.id: f for f in cfg.feeds}
        descriptions = describe_clusters(clusters, feeds_by_id)
        ranking = rank_events(descriptions, model, cfg.limits.max_candidate_events)
        chosen = select_events(descriptions, ranking, cfg.limits.max_stories, cfg.limits.max_stories_per_section)
        by_rule = sum(1 for cid in chosen if ranking[cid].get("by_rule"))
        note("rank", "info", f"{len(chosen)} events selected" + (f", {by_rule} ranked by rule" if by_rule else ""))

        sources = db.sources_by_id(conn)
        source_names = {sid: s["name"] for sid, s in sources.items()}
        stories: list[dict] = []
        stats.update(claims_published=0, claims_removed=0, events_failed=0)
        for cid in chosen:
            if time.monotonic() > deadline:
                note("summarize", "error", "time limit reached; publishing the stories finished so far")
                coverage_notes.append("The run reached its time limit, so this briefing is shorter than planned.")
                break
            try:
                passages = choose_passages(clusters[cid], cfg.limits.max_articles_per_event,
                                           cfg.limits.max_chars_per_article)
                draft = draft_event(passages, source_names, model)
                checked = validate_event(draft, passages, model)
                headline = clean_text(draft.get("headline")) or passages[0]["title"]
                for a in checked["audit"]:
                    db.audit_claim(conn, run_id, headline, a["text"], a["verdict"], a["published"], a["reason"])
                conn.commit()
                removed = sum(1 for a in checked["audit"] if not a["published"])
                stats["claims_removed"] += removed
                if not checked["claims"]:
                    note("validate", "error", f"dropped '{headline}': no claim survived checking")
                    stats["events_failed"] += 1
                    continue
                stories.append(build_story(f"{briefing_id}-{len(stories) + 1:02d}", clusters[cid], passages, draft,
                                           checked, ranking[cid], window_start.date(), now.date()))
                stats["claims_published"] += len(checked["claims"])
                note("validate", "info", f"'{headline}': {len(checked['claims'])} claims kept, {removed} removed")
            except BudgetExceeded:
                note("summarize", "error", "model call budget used up; publishing the stories finished so far")
                coverage_notes.append("The run used its model-call budget, so this briefing is shorter than planned.")
                break
            except LMError as exc:
                stats["events_failed"] += 1
                note("summarize", "error", f"event {cid} skipped: {exc}")
            except Exception as exc:  # a defect in one event must not lose the briefing
                stats["events_failed"] += 1
                log.exception("event %s failed", cid)
                note("summarize", "error", f"event {cid} skipped after an unexpected error: {exc!r}")

        if not stories:
            note("publish", "error", "no story passed checking; nothing published")
            db.finish_run(conn, run_id, "empty", stats)
            return None

        top = [s for s in stories if s["importance"] >= 4][:4] or stories[:3]
        for s in top:
            s["topStory"] = True
        used_sources = sorted({a["sourceId"] for s in stories for a in s["articles"]})
        present = {s["section"] for s in stories}
        coverage_notes.append("Summaries are based on the excerpts publishers put in their feeds, not full articles.")
        if getattr(model, "is_stand_in", False):
            coverage_notes.append("Produced with the rule-based stand-in, not a language model. For testing only.")
        if method == "lexical":
            coverage_notes.append("Events were grouped by word overlap; no embedding model was configured.")
        briefing = {
            "schemaVersion": 1,
            "id": briefing_id,
            "date": briefing_id,
            "generatedAt": iso(now),
            "title": "World Brief",
            "overview": f"{len(stories)} developments drawn from {len(used_sources)} sources. Leading: "
                        + "; ".join(s["headline"] for s in top[:3]) + ".",
            "isDemo": False,
            "generator": {"pipelineVersion": PIPELINE_VERSION, "model": model.name},
            "coverage": {
                "windowStart": iso(window_start),
                "windowEnd": iso(now),
                "articlesConsidered": len(articles),
                "sourcesConsidered": len({a["source_id"] for a in articles}),
                "sectionsWithoutCoverage": [r for r in REGION_SECTIONS if r != "other_regions" and r not in present],
                "notes": coverage_notes,
            },
            "sources": [
                {"id": sid, "name": sources[sid]["name"], "country": sources[sid]["country"],
                 "type": sources[sid]["type"], "homepage": sources[sid]["homepage"]}
                if sid in sources else {"id": sid, "name": sid, "country": None, "type": None, "homepage": None}
                for sid in used_sources
            ],
            "stories": stories,
        }
        jsonschema.Draft202012Validator(load_schema()).validate(briefing)
        db.save_briefing(conn, briefing)
        export_dir = cfg.resolve(cfg.paths.export_dir)
        export_dir.mkdir(parents=True, exist_ok=True)
        Path(export_dir, f"briefing-{briefing_id}.json").write_text(
            json.dumps(briefing, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        stats.update(stories=len(stories), model_calls=model.calls, seconds=round(time.monotonic() - started, 1))
        note("publish", "info", f"published {briefing_id}: {len(stories)} stories, {model.calls} model calls")
        db.finish_run(conn, run_id, "published", stats)
        return briefing
    except Exception as exc:
        log.exception("run failed")
        db.log_event(conn, run_id, "run", "error", f"run failed: {exc!r}")
        db.finish_run(conn, run_id, "failed", stats)
        raise
