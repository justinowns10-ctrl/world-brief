"""Runs the stages in order and publishes one briefing.

Publication states
------------------
pending   a run is in progress (or none has started). Nothing new is served yet.
complete  a briefing was published and nothing was cut short.
partial   a briefing was published, but something limited it: a feed could not
          be read, a story was lost to an inference error, or the run hit its
          model-call budget or time limit. The briefing lists the reasons.
failed    nothing was published. Any earlier briefing for that date is untouched.

Failure handling: every feed, every event and every model call is isolated.
A failure is logged to the run history and the run carries on with what it has.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from importlib import resources
from pathlib import Path

import jsonschema

from . import PIPELINE_VERSION, REGION_SECTIONS, db
from .cluster import cluster_articles
from .config import Config
from .ingest import fetch_feed, independent_source_count, mark_duplicates, parse_feed_detailed
from .lm import BudgetExceeded, LMError
from .rank import describe_clusters, rank_events, select_events
from .summarize import choose_passages, draft_event
from .text import clean_text
from .validate import safe_text, supported_event_date, validate_event

log = logging.getLogger("worldbrief.pipeline")

MAX_ARTICLES_LISTED = 8


def load_schema() -> dict:
    return json.loads(resources.files("worldbrief").joinpath("briefing.schema.json").read_text(encoding="utf-8"))


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ingest_feeds(cfg: Config, conn, note) -> dict:
    stats = {"feeds_ok": 0, "feeds_failed": 0, "articles_new": 0, "feeds": {}}
    for feed in cfg.feeds:
        try:
            db.upsert_source(conn, feed)
            records, info = parse_feed_detailed(feed, fetch_feed(feed))
            if not records:
                why = f"malformed ({info['parse_error']})" if info["malformed"] else "not a feed, empty, or undated"
                raise ValueError(f"no usable entries: {why}")
            new = sum(db.insert_article(conn, r) for r in records)
            conn.commit()
            stats["feeds_ok"] += 1
            stats["articles_new"] += new
            stats["feeds"][feed.id] = {"ok": True, "usable": len(records), "new": new, "malformed": info["malformed"]}
            damaged = " (malformed XML, recovered what was readable)" if info["malformed"] else ""
            note("ingest", "info", f"{feed.id}: {len(records)} entries, {new} new{damaged}")
        except Exception as exc:
            conn.rollback()
            stats["feeds_failed"] += 1
            stats["feeds"][feed.id] = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
            note("ingest", "error", f"{feed.id}: failed, skipped: {exc}")
    return stats


def story_id(briefing_id: str, articles: list[dict]) -> str:
    """Identifies a story by its event, not by its position in the briefing.
    The anchor is the earliest report of the event, so regenerating a briefing
    (different order, more articles) keeps the id, and saved-story references
    on the phone keep pointing at the same event."""
    anchor = min(articles, key=lambda a: (a["published_at"], a["id"]))
    return f"{briefing_id}-{anchor['id']}"


def build_story(story_id: str, articles: list[dict], passages: list[dict], draft: dict, checked: dict,
                rank: dict) -> dict:
    listed = [p["article"] for p in passages]
    for a in sorted(articles, key=lambda a: a["published_at"]):
        if a not in listed and not a.get("withheld") and len(listed) < MAX_ARTICLES_LISTED:
            listed.append(a)
    source_text = " ".join(f"{p['title']}. {p['text']}" for p in passages)
    independent = independent_source_count(listed)
    claims = []
    for n, c in enumerate(checked["claims"], start=1):
        claims.append({
            "id": f"c{n}", "text": c["text"], "support": c["support"], "note": c["note"],
            "evidence": [{"articleId": e["passage"]["article"]["id"], "quote": e["quote"]} for e in c["evidence"]],
        })
    partial = sum(1 for c in claims if c["support"] == "partial")
    unchecked = sum(1 for c in claims if c["support"] == "unchecked")
    dropped = sum(1 for a in checked["audit"] if not a["published"])
    withheld_text = sum(len(p.get("removed") or []) for p in passages)

    notes = []
    drafted_uncertainty = safe_text(draft.get("uncertainty"), source_text)
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
    if withheld_text:
        notes.append("Part of a source's text was withheld from processing because it read as instructions to software.")
    if unchecked:
        notes.append(f"VERIFICATION INCOMPLETE: the consistency check did not run. {unchecked} statement(s) are "
                     "shown only because they are word for word from the cited source; they were not checked further.")

    if checked["conflict"]:
        status = "disputed"
    elif independent >= 2 and partial == 0 and unchecked == 0 and checked["checked_by_model"]:
        status = "verified"
    else:
        status = "preliminary"

    times = sorted(a["published_at"] for a in listed)
    return {
        "id": story_id,
        "section": rank["section"],
        "headline": checked["headline"],
        "countries": rank.get("countries", []),
        "eventDate": supported_event_date(draft.get("event_date"), passages),
        "firstReportedAt": times[0],
        "lastReportedAt": times[-1],
        "status": status,
        "importance": rank["importance"],
        "topStory": False,
        "summary": " ".join(c["text"] for c in claims),
        "claims": claims,
        "whyItMatters": checked["why_it_matters"],
        "context": checked["context"],
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
    """Produces and stores one briefing. Returns it, or None if the run failed
    to publish anything. The outcome is recorded in the `runs` table either way."""
    now = now or datetime.now(timezone.utc)
    briefing_id = briefing_date or now.date().isoformat()
    deadline = time.monotonic() + cfg.limits.max_run_minutes * 60
    started = time.monotonic()
    run_id = db.start_run(conn, briefing_id)          # state: pending
    stats: dict = {"model": model.name}
    reasons: list[str] = []                            # why the briefing is partial, if it is
    coverage_notes: list[str] = []

    def note(stage: str, level: str, message: str) -> None:
        (log.warning if level == "error" else log.info)("[%s] %s", stage, message)
        db.log_event(conn, run_id, stage, level, message)

    def fail(reason: str) -> None:
        note("publish", "error", f"run failed: {reason}")
        stats.update(failure=reason, reasons=reasons, model_calls=model.calls,
                     seconds=round(time.monotonic() - started, 1))
        db.finish_run(conn, run_id, "failed", stats)

    try:
        if fetch:
            stats.update(ingest_feeds(cfg, conn, note))
            if stats["feeds_failed"]:
                reasons.append(f"{stats['feeds_failed']} of {len(cfg.feeds)} feeds could not be read.")
        window_start = now - timedelta(hours=cfg.window.hours)
        articles = [a for a in db.articles_since(conn, iso(window_start), cfg.limits.max_articles)
                    if a["published_at"] <= iso(now)]
        stats["articles_considered"] = len(articles)
        if not articles:
            fail("no articles in the time window")
            return None

        mark_duplicates(articles)
        clusters, method = cluster_articles(articles, model, cfg.clustering.embedding_threshold,
                                            cfg.clustering.lexical_threshold)
        stats.update(clusters=len(clusters), clustering=method)
        note("cluster", "info", f"{len(articles)} articles grouped into {len(clusters)} events ({method})")

        feeds_by_id = {f.id: f for f in cfg.feeds}
        descriptions = describe_clusters(clusters, feeds_by_id)
        ranking, rank_budget_hit = rank_events(descriptions, model, cfg.limits.max_candidate_events)
        chosen = select_events(descriptions, ranking, cfg.limits.max_stories, cfg.limits.max_stories_per_section)
        by_rule = sum(1 for cid in chosen if ranking[cid].get("by_rule"))
        note("rank", "info", f"{len(chosen)} events selected" + (f", {by_rule} ranked by rule" if by_rule else ""))
        if by_rule:
            coverage_notes.append(f"{by_rule} of {len(chosen)} selected events were ranked by a fixed rule "
                                  "because the model's ranking was unavailable.")

        sources = db.sources_by_id(conn)
        source_names = {sid: s["name"] for sid, s in sources.items()}
        stories: list[dict] = []
        stats.update(claims_published=0, claims_removed=0, events_failed=0, events_unsupported=0,
                     events_processed=0, instruction_like_text_withheld=0)
        stopped: str | None = None
        for position, cid in enumerate(chosen):
            if time.monotonic() > deadline:
                stopped = "time limit"
                break
            try:
                passages = choose_passages(clusters[cid], cfg.limits.max_articles_per_event,
                                           cfg.limits.max_chars_per_article)
                withheld = sum(len(p["removed"]) for p in passages) + sum(1 for a in clusters[cid] if a.get("withheld"))
                if withheld:
                    stats["instruction_like_text_withheld"] += withheld
                    note("summarize", "error", f"event {cid}: withheld {withheld} piece(s) of instruction-like source text")
                if not passages:
                    stats["events_unsupported"] += 1
                    note("summarize", "error", f"event {cid} dropped: no usable source text")
                    continue
                draft = draft_event(passages, source_names, model)
                stats["events_processed"] += 1
                checked = validate_event(draft, passages, model)
                headline = checked["headline"]
                for a in checked["audit"]:
                    db.audit_claim(conn, run_id, headline, a["text"], a["verdict"], a["published"], a["reason"])
                conn.commit()
                removed = sum(1 for a in checked["audit"] if not a["published"])
                stats["claims_removed"] += removed
                if not checked["claims"]:
                    stats["events_unsupported"] += 1
                    note("validate", "error", f"dropped '{headline}': no claim survived checking")
                    continue
                stories.append(build_story(story_id(briefing_id, clusters[cid]), clusters[cid], passages, draft,
                                           checked, ranking[cid]))
                stats["claims_published"] += len(checked["claims"])
                note("validate", "info", f"'{headline}': {len(checked['claims'])} claims kept, {removed} removed")
            except BudgetExceeded:
                stopped = "model-call budget"
                break
            except LMError as exc:
                stats["events_failed"] += 1
                note("summarize", "error", f"event {cid} skipped: {exc}")
            except Exception as exc:  # a defect in one event must not lose the briefing
                stats["events_failed"] += 1
                log.exception("event %s failed", cid)
                note("summarize", "error", f"event {cid} skipped after an unexpected error: {exc!r}")

        left = 0
        if stopped:
            left = len(chosen) - position
            reasons.append(f"The run reached its {stopped} with {left} of {len(chosen)} selected events unprocessed.")
            note("summarize", "error", f"{stopped} reached; {left} events unprocessed")
        elif rank_budget_hit:
            reasons.append("The model-call budget ran out during ranking.")
        if any(c["support"] == "unchecked" for st in stories for c in st["claims"]):
            reasons.append("Verification could not complete for at least one story; unchecked statements are labelled.")
        events = {"selected": len(chosen), "processed": stats["events_processed"], "published": len(stories),
                  "skippedUnsupported": stats["events_unsupported"], "skippedErrors": stats["events_failed"],
                  "unprocessed": left}
        stats["events"] = events
        if stats["events_failed"]:
            reasons.append(f"{stats['events_failed']} event(s) were lost to inference or processing errors.")

        if not stories:
            fail(f"no story could be published ({stopped} reached before any finished)" if stopped
                 else "no story passed checking")
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
        state = "partial" if reasons else "complete"
        briefing = {
            "schemaVersion": 1,
            "id": briefing_id,
            "date": briefing_id,
            "generatedAt": iso(now),
            "title": "World Brief",
            "overview": f"{len(stories)} developments drawn from {len(used_sources)} sources. Leading: "
                        + "; ".join(s["headline"] for s in top[:3]) + ".",
            "isDemo": False,
            "publication": {"state": state, "reasons": reasons, "events": events},
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
        by_status = {k: sum(1 for s in stories if s["status"] == k) for k in ("verified", "preliminary", "disputed")}
        stats.update(stories=len(stories), stories_by_status=by_status, reasons=reasons, model_calls=model.calls,
                     seconds=round(time.monotonic() - started, 1))
        note("publish", "info", f"published {briefing_id} ({state}): {len(stories)} stories, {model.calls} model calls")
        db.finish_run(conn, run_id, state, stats)
        return briefing
    except Exception as exc:
        log.exception("run failed")
        db.log_event(conn, run_id, "run", "error", f"run failed: {exc!r}")
        stats.update(failure=f"unexpected error: {exc!r}"[:300], reasons=reasons)
        db.finish_run(conn, run_id, "failed", stats)
        raise
