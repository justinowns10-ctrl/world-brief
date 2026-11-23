"""Backend tests. Feeds are local files with invented content; the language
model is replaced by a rule-based stand-in or a scripted misbehaving model.
These tests show the pipeline's plumbing and safeguards work. They say nothing
about the quality of a real model's summaries."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from worldbrief import db
from worldbrief.api import create_app
from worldbrief.config import Config, Feed
from worldbrief.ingest import independent_source_count, mark_duplicates, parse_feed
from worldbrief.lm import LMError, StandInModel, parse_json_reply
from worldbrief.pipeline import load_schema, run_pipeline
from worldbrief.text import canonical_url
from worldbrief.validate import validate_event

FIXTURES = Path(__file__).parent / "fixtures"
REPO = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 23, 12, 0, 0, tzinfo=timezone.utc)
TOKEN = "test-token-0123456789abcdef"


def make_config(tmp_path: Path, extra_feeds: list[Feed] | None = None) -> Config:
    cfg = Config()
    cfg.base_dir = tmp_path
    cfg.feeds = [
        Feed(id="alpha", name="Alpha Test Feed", url=str(FIXTURES / "feed_alpha.xml"), region_hint="europe"),
        Feed(id="beta", name="Beta Test Feed", url=str(FIXTURES / "feed_beta.xml"), region_hint="africa"),
    ] + (extra_feeds or [])
    return cfg


def test_schema_copies_match():
    assert (REPO / "contract" / "briefing.schema.json").read_text(encoding="utf-8") == \
        (REPO / "backend" / "src" / "worldbrief" / "briefing.schema.json").read_text(encoding="utf-8")


def test_example_briefings_are_valid():
    validator = jsonschema.Draft202012Validator(load_schema())
    examples = sorted((REPO / "contract" / "examples").glob("*.json"))
    assert examples
    for path in examples:
        briefing = json.loads(path.read_text(encoding="utf-8"))
        validator.validate(briefing)
        for story in briefing["stories"]:
            ids = {a["id"] for a in story["articles"]}
            for claim in story["claims"]:
                assert all(e["articleId"] in ids for e in claim["evidence"])


def test_android_demo_assets_match_contract_examples():
    assets = REPO / "android" / "app" / "src" / "main" / "assets" / "demo"
    for path in (REPO / "contract" / "examples").glob("*.json"):
        assert (assets / path.name).read_text(encoding="utf-8") == path.read_text(encoding="utf-8")


def test_canonical_url_drops_tracking():
    assert canonical_url("https://Alpha.test/floods/?utm_source=rss&id=7#top") == "https://alpha.test/floods?id=7"


def test_parse_skips_undated_and_marks_copies():
    feed_a = Feed(id="alpha", name="A", url="x")
    feed_b = Feed(id="beta", name="B", url="x")
    articles = parse_feed(feed_a, (FIXTURES / "feed_alpha.xml").read_bytes()) + \
        parse_feed(feed_b, (FIXTURES / "feed_beta.xml").read_bytes())
    titles = [a["title"] for a in articles]
    assert "Entry with no date is skipped" not in titles
    mark_duplicates(articles)
    treaty = [a for a in articles if "treaty" in a["title"]]
    assert sorted(a["role"] for a in treaty) == ["original", "syndicated"]
    assert independent_source_count(treaty) == 1
    floods = [a for a in articles if "lood" in a["title"]]
    assert independent_source_count(floods) == 2


def test_parse_json_reply_tolerates_wrapping():
    assert parse_json_reply('<think>hmm</think>```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(ValueError):
        parse_json_reply("no json here")


def test_pipeline_end_to_end_and_api(tmp_path):
    cfg = make_config(tmp_path, [Feed(id="broken", name="Broken", url=str(tmp_path / "missing.xml"))])
    conn = db.connect(cfg.resolve(cfg.paths.database))
    briefing = run_pipeline(cfg, StandInModel(), conn, briefing_date="2026-11-23", now=NOW)
    assert briefing is not None
    jsonschema.Draft202012Validator(load_schema()).validate(briefing)

    # the broken feed was logged, not fatal
    events = [e["message"] for e in conn.execute("SELECT message FROM run_events WHERE level='error'")]
    assert any("broken" in m for m in events)
    assert briefing["publication"]["state"] == "partial"
    assert any("could not be read" in r for r in briefing["publication"]["reasons"])

    headlines = " | ".join(s["headline"] for s in briefing["stories"])
    assert "Old story" not in headlines
    assert len(briefing["stories"]) == 3            # flood, treaty, seabed

    known_urls = {r["url"] for r in conn.execute("SELECT url FROM articles")}
    for story in briefing["stories"]:
        ids = {a["id"] for a in story["articles"]}
        assert all(a["url"] in known_urls for a in story["articles"])
        assert story["firstReportedAt"] <= story["lastReportedAt"]
        for claim in story["claims"]:
            assert claim["evidence"] and all(e["articleId"] in ids for e in claim["evidence"])

    flood = next(s for s in briefing["stories"] if "lood" in s["headline"])
    treaty = next(s for s in briefing["stories"] if "treaty" in s["headline"])
    assert flood["independentSourceCount"] == 2
    assert treaty["independentSourceCount"] == 1     # same text from two outlets counts once
    assert treaty["status"] == "preliminary"
    assert "single independent source" in treaty["uncertainty"]

    # second run on the same data replaces the briefing instead of duplicating it
    run_pipeline(cfg, StandInModel(), conn, briefing_date="2026-11-23", now=NOW)
    assert len(db.list_briefings(conn)) == 1

    client = TestClient(create_app(str(cfg.resolve(cfg.paths.database)), TOKEN))
    assert client.get("/v1/health").json()["status"] == "ok"
    assert client.get("/v1/briefings").status_code == 401
    assert client.get("/v1/briefings", headers={"Authorization": "Bearer wrong"}).status_code == 401
    auth = {"Authorization": f"Bearer {TOKEN}"}
    listed = client.get("/v1/briefings", headers=auth).json()["briefings"]
    assert [b["id"] for b in listed] == ["2026-11-23"]
    assert client.get("/v1/briefings/2026-11-23", headers=auth).json()["id"] == "2026-11-23"
    assert client.get("/v1/briefings/latest", headers=auth).json()["id"] == "2026-11-23"
    assert client.get("/v1/briefings/1999-01-01", headers=auth).status_code == 404


PASSAGES = [
    {"ref": "A1", "title": "Harbour city floods", "article": {"id": "art1"},
     "text": "The river burst its banks on Sunday and flooded the harbour city of Testport. "
             "Officials said 1,200 people left their homes."},
    {"ref": "A2", "title": "Testport flooded", "article": {"id": "art2"},
     "text": "Flood water covered much of Testport after the river overflowed. Officials said 1,200 people were evacuated."},
]


class ScriptedModel:
    """Returns whatever the test tells it to for the verify step."""
    name = "scripted"

    def __init__(self, verdicts=None, fail=False):
        self.calls, self.verdicts, self.fail = 0, verdicts or {}, fail

    def embed(self, texts):
        return None

    def chat_json(self, task, system, user, schema, meta=None):
        self.calls += 1
        if self.fail:
            raise LMError("model unavailable")
        return {"claims": [{"index": i, "verdict": self.verdicts.get(i, "supported"), "reason": "scripted"}
                           for i in range(len(meta["claims"]))],
                "sources_conflict": False, "conflict_note": None}


def draft(*claims):
    return {"claims": [{"text": t, "article_ids": ids, "quote": q} for t, ids, q in claims]}


def test_validation_removes_fabricated_and_unsupported_claims():
    d = draft(
        ("Officials said 1,200 people left their homes in Testport.", ["A1"], "Officials said 1,200 people left their homes."),
        ("The mayor of Testport resigned over the response.", ["A9"], "The mayor resigned."),            # unknown passage
        ("Insurers estimated losses at 40 million dollars.", ["A2"], "Losses were put at 40 million."),  # not in source
        ("Officials said 5,000 people were evacuated from Testport.", ["A2"], "Officials said 1,200 people were evacuated."),
        ("Flood water covered much of Testport.", ["A2"], "Flood water covered much of Testport after the river overflowed."),
    )
    result = validate_event(d, PASSAGES, ScriptedModel(verdicts={2: "unsupported"}))
    published = {c["text"]: c for c in result["claims"]}
    audit = {a["text"]: a for a in result["audit"]}

    assert "The mayor of Testport resigned over the response." not in published
    assert "Insurers estimated losses at 40 million dollars." not in published
    assert audit["The mayor of Testport resigned over the response."]["verdict"] == "unsupported"

    wrong_number = published["Officials said 5,000 people were evacuated from Testport."]
    assert wrong_number["support"] == "partial" and "5000" in wrong_number["note"]

    good = published["Officials said 1,200 people left their homes in Testport."]
    assert good["support"] == "supported"
    assert good["evidence"][0]["quote"] in PASSAGES[0]["text"]     # quote is source text, not model text

    assert "Flood water covered much of Testport." not in published  # the scripted checker rejected index 2
    assert audit["Flood water covered much of Testport."]["verdict"] == "unsupported"


def test_verbatim_claim_is_labelled_unchecked_when_checker_is_unavailable():
    d = draft(("Officials said 1,200 people left their homes.", ["A1"], "Officials said 1,200 people left their homes."))
    result = validate_event(d, PASSAGES, ScriptedModel(fail=True))
    assert result["checked_by_model"] is False
    assert result["claims"][0]["support"] == "unchecked"       # word for word, so publishable but labelled


def test_contradicted_claim_is_removed_and_marks_conflict():
    d = draft(("Officials said 1,200 people left their homes.", ["A1"], "Officials said 1,200 people left their homes."))
    result = validate_event(d, PASSAGES, ScriptedModel(verdicts={0: "contradicted"}))
    assert result["claims"] == [] and result["conflict"] is True


class FailingSummaries(StandInModel):
    """Fails on one event to prove a single failure does not stop the run."""

    def chat_json(self, task, system, user, schema, meta=None):
        if task == "summarize" and "treaty" in meta["passages"][0]["title"]:
            raise LMError("simulated inference failure")
        return super().chat_json(task, system, user, schema, meta)


def test_one_failed_event_does_not_stop_the_briefing(tmp_path):
    cfg = make_config(tmp_path)
    conn = db.connect(cfg.resolve(cfg.paths.database))
    briefing = run_pipeline(cfg, FailingSummaries(), conn, briefing_date="2026-11-23", now=NOW)
    assert briefing is not None and len(briefing["stories"]) == 2
    assert all("treaty" not in s["headline"] for s in briefing["stories"])


def test_time_limit_before_any_story_is_a_failed_run(tmp_path):
    cfg = make_config(tmp_path)
    cfg.limits.max_run_minutes = 0
    conn = db.connect(cfg.resolve(cfg.paths.database))
    assert run_pipeline(cfg, StandInModel(), conn, briefing_date="2026-11-23", now=NOW) is None
    assert db.latest_run_status(conn)["state"] == "failed"
    assert db.list_briefings(conn) == []


def test_lmstudio_client_retries_invalid_json_and_respects_budget():
    import httpx

    from worldbrief.config import LMStudio
    from worldbrief.lm import BudgetExceeded, LMStudioClient

    replies = iter(["not json", '```json\n{"ok": true}\n```'])
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"choices": [{"message": {"content": next(replies)}}]})

    cfg = LMStudio(chat_model="test-model", cooldown_s=0, retries=1, max_prompt_chars=200)
    client = LMStudioClient(cfg, max_calls=2, transport=httpx.MockTransport(handler))
    schema = {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}
    assert client.chat_json("probe", "system", "u" * 1000, schema) == {"ok": True}
    assert client.calls == 2
    assert seen[0]["model"] == "test-model" and seen[0]["response_format"]["type"] == "json_schema"
    assert len(seen[0]["messages"][1]["content"]) <= 200          # prompt cap applied
    with pytest.raises(BudgetExceeded):
        client.chat_json("probe", "system", "user", schema)
