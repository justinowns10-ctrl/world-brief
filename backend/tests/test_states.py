"""Publication states (pending, complete, partial, failed) and the
model-call budget. These run the real LM Studio client code against a fake
server, so the budget is enforced where it is enforced in production."""
from __future__ import annotations

import json

import jsonschema
from fastapi.testclient import TestClient

from helpers import NOW, FakeLMStudio, make_config
from worldbrief import db
from worldbrief.api import create_app
from worldbrief.cli import main
from worldbrief.config import Feed
from worldbrief.pipeline import load_schema, run_pipeline

TOKEN = "test-token-0123456789abcdef"


def run(cfg, model, conn):
    return run_pipeline(cfg, model, conn, briefing_date="2026-11-23", now=NOW)


def test_complete(tmp_path):
    cfg = make_config(tmp_path)
    conn = db.connect(cfg.resolve(cfg.paths.database))
    fake = FakeLMStudio()
    briefing = run(cfg, fake.client(cfg), conn)
    assert briefing["publication"]["state"] == "complete" and briefing["publication"]["reasons"] == []
    assert briefing["publication"]["events"] == {"selected": 3, "processed": 3, "published": 3,
                                                 "skippedUnsupported": 0, "skippedErrors": 0, "unprocessed": 0}
    assert len(briefing["stories"]) == 3
    assert db.latest_run_status(conn)["state"] == "complete"
    assert db.list_briefings(conn)[0]["state"] == "complete"
    # 1 ranking call, then a draft and a check per story
    assert len(fake.requests) == 7


def test_budget_runs_out_mid_run_gives_a_partial_briefing(tmp_path):
    cfg = make_config(tmp_path)
    conn = db.connect(cfg.resolve(cfg.paths.database))
    fake = FakeLMStudio()
    briefing = run(cfg, fake.client(cfg, max_calls=3), conn)     # rank + one full story
    assert briefing is not None
    jsonschema.Draft202012Validator(load_schema()).validate(briefing)
    assert len(briefing["stories"]) == 1
    assert briefing["publication"]["state"] == "partial"
    assert any("model-call budget" in r and "2 of 3" in r for r in briefing["publication"]["reasons"])
    assert len(fake.requests) == 3                                # nothing was sent past the budget
    status = db.latest_run_status(conn)
    assert status["state"] == "partial" and status["briefingAvailable"] is True


def test_budget_runs_out_between_draft_and_check(tmp_path):
    """The budget ends after a story is drafted but before it is checked. Its
    claims are published only because they are word for word from the source,
    they are labelled unchecked, and the briefing says verification did not complete."""
    cfg = make_config(tmp_path)
    conn = db.connect(cfg.resolve(cfg.paths.database))
    briefing = run(cfg, FakeLMStudio().client(cfg, max_calls=4), conn)   # rank, story 1, draft of story 2
    assert briefing["publication"]["state"] == "partial"
    assert briefing["publication"]["events"] == {"selected": 3, "processed": 2, "published": 2,
                                                 "skippedUnsupported": 0, "skippedErrors": 0, "unprocessed": 1}
    assert any("Verification could not complete" in r for r in briefing["publication"]["reasons"])
    unchecked = briefing["stories"][1]
    assert unchecked["status"] == "preliminary"
    assert all(c["support"] == "unchecked" for c in unchecked["claims"])
    assert "VERIFICATION INCOMPLETE" in unchecked["uncertainty"]


def test_complete_and_partial_briefings_are_distinguishable_everywhere(tmp_path):
    """A run cut short must never look like a complete one: not in the briefing,
    not in the list, not in the run status."""
    cfg = make_config(tmp_path)
    conn = db.connect(cfg.resolve(cfg.paths.database))
    complete = run(cfg, FakeLMStudio().client(cfg), conn)
    complete_view = (complete["publication"]["state"], db.list_briefings(conn)[0]["state"],
                     db.latest_run_status(conn)["state"], complete["publication"]["events"]["unprocessed"])
    partial = run(cfg, FakeLMStudio().client(cfg, max_calls=3), conn)
    partial_view = (partial["publication"]["state"], db.list_briefings(conn)[0]["state"],
                    db.latest_run_status(conn)["state"], partial["publication"]["events"]["unprocessed"])
    assert complete_view == ("complete", "complete", "complete", 0)
    assert partial_view == ("partial", "partial", "partial", 2)
    assert complete["publication"]["events"]["published"] == 3 and partial["publication"]["events"]["published"] == 1


def test_story_ids_survive_regeneration_in_a_different_order(tmp_path):
    """A saved story is a stored story id. After the briefing is regenerated
    with the events ranked in the opposite order, each id must still name the
    same event."""
    import re

    def ranked(order):
        class Ranking(FakeLMStudio):
            def _handle(self, request):
                import json as _json
                import httpx
                body = _json.loads(request.content)
                if body["response_format"]["json_schema"]["name"] != "rank":
                    return super()._handle(request)
                self.requests.append(body)
                ids = [int(i) for i in re.findall(r"^Event (\d+) ", body["messages"][1]["content"], re.M)]
                scores = {cid: (5 - n if order == "forward" else 3 + n) for n, cid in enumerate(sorted(ids))}
                reply = {"events": [{"cluster_id": c, "section": "europe", "importance": scores[c], "countries": [],
                                     "reason": "x"} for c in ids]}
                return httpx.Response(200, json={"choices": [{"message": {"content": _json.dumps(reply)}}]})
        return Ranking()

    cfg = make_config(tmp_path)
    conn = db.connect(cfg.resolve(cfg.paths.database))
    first = run(cfg, ranked("forward").client(cfg), conn)
    saved = {s["id"]: s["articles"][0]["url"] for s in first["stories"]}        # what a bookmark points at
    second = run(cfg, ranked("reverse").client(cfg), conn)
    assert [s["id"] for s in second["stories"]] == [s["id"] for s in reversed(first["stories"])]   # order changed
    assert {s["id"]: s["articles"][0]["url"] for s in second["stories"]} == saved                  # identity did not
    assert not any(re.fullmatch(r"\d{4}-\d{2}-\d{2}-\d{2}", s["id"]) for s in second["stories"]) # not positional


def test_budget_runs_out_before_any_story_is_a_failed_run(tmp_path):
    cfg = make_config(tmp_path)
    conn = db.connect(cfg.resolve(cfg.paths.database))
    assert run(cfg, FakeLMStudio().client(cfg, max_calls=1), conn) is None     # ranking used the only call
    status = db.latest_run_status(conn)
    assert status["state"] == "failed"
    assert "model-call budget" in status["reasons"][0]
    assert db.list_briefings(conn) == []


def test_zero_budget_ranks_by_rule_then_fails(tmp_path):
    cfg = make_config(tmp_path)
    conn = db.connect(cfg.resolve(cfg.paths.database))
    fake = FakeLMStudio()
    assert run(cfg, fake.client(cfg, max_calls=0), conn) is None
    assert fake.requests == []
    assert db.latest_run_status(conn)["state"] == "failed"


def test_failed_run_leaves_the_earlier_briefing_in_place(tmp_path):
    cfg = make_config(tmp_path)
    conn = db.connect(cfg.resolve(cfg.paths.database))
    first = run(cfg, FakeLMStudio().client(cfg), conn)
    assert run(cfg, FakeLMStudio().client(cfg, max_calls=1), conn) is None
    status = db.latest_run_status(conn)
    assert status["state"] == "failed" and status["briefingAvailable"] is True
    assert db.get_briefing(conn, "2026-11-23") == first


def test_inference_errors_on_every_story_fail_the_run(tmp_path):
    cfg = make_config(tmp_path)
    cfg.lmstudio.retries = 0
    conn = db.connect(cfg.resolve(cfg.paths.database))
    assert run(cfg, FakeLMStudio(fail_tasks={"summarize"}).client(cfg), conn) is None
    assert db.latest_run_status(conn)["state"] == "failed"


def test_ranking_failure_alone_does_not_make_the_briefing_partial_but_is_disclosed(tmp_path):
    cfg = make_config(tmp_path)
    cfg.lmstudio.retries = 0
    conn = db.connect(cfg.resolve(cfg.paths.database))
    briefing = run(cfg, FakeLMStudio(fail_tasks={"rank"}).client(cfg), conn)
    assert briefing is not None
    assert any("ranked by a fixed rule" in n for n in briefing["coverage"]["notes"])


def test_no_articles_is_a_failed_run(tmp_path):
    cfg = make_config(tmp_path, feeds=[Feed(id="gone", name="Gone", url=str(tmp_path / "missing.xml"))])
    conn = db.connect(cfg.resolve(cfg.paths.database))
    assert run(cfg, FakeLMStudio().client(cfg), conn) is None
    status = db.latest_run_status(conn)
    assert status["state"] == "failed" and "no articles" in status["reasons"][0]


def test_pending_and_interrupted_runs(tmp_path):
    cfg = make_config(tmp_path)
    conn = db.connect(cfg.resolve(cfg.paths.database))
    assert db.latest_run_status(conn)["state"] == "pending"          # nothing has run yet
    db.start_run(conn, "2026-11-23")
    assert db.latest_run_status(conn)["state"] == "pending"          # a run is in progress
    # The process dies here. The next run finds the stale row and records it as failed.
    briefing = run(cfg, FakeLMStudio().client(cfg), conn)
    assert briefing is not None
    rows = [dict(r) for r in conn.execute("SELECT status, stats FROM runs ORDER BY id")]
    assert [r["status"] for r in rows] == ["failed", "complete"]
    assert "interrupted" in json.loads(rows[0]["stats"])["failure"]


def test_status_endpoint_reports_each_state(tmp_path):
    cfg = make_config(tmp_path)
    path = str(cfg.resolve(cfg.paths.database))
    conn = db.connect(path)
    client = TestClient(create_app(path, TOKEN))
    auth = {"Authorization": f"Bearer {TOKEN}"}
    assert client.get("/v1/status").status_code == 401
    assert client.get("/v1/status", headers=auth).json()["state"] == "pending"
    run(cfg, FakeLMStudio().client(cfg, max_calls=3), conn)
    body = client.get("/v1/status", headers=auth).json()
    assert body["state"] == "partial" and body["date"] == "2026-11-23" and body["reasons"]
    assert client.get("/v1/briefings", headers=auth).json()["briefings"][0]["state"] == "partial"
    run(cfg, FakeLMStudio().client(cfg, max_calls=1), conn)
    assert client.get("/v1/status", headers=auth).json()["state"] == "failed"
    run(cfg, FakeLMStudio().client(cfg), conn)
    assert client.get("/v1/status", headers=auth).json()["state"] == "complete"


def test_database_from_before_states_is_upgraded(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE briefings (id TEXT PRIMARY KEY, generated_at TEXT NOT NULL, title TEXT NOT NULL, "
                "story_count INTEGER NOT NULL, is_demo INTEGER NOT NULL, json TEXT NOT NULL)")
    old.execute("INSERT INTO briefings VALUES ('2026-11-01','2026-11-01T13:00:00Z','World Brief',0,0,'{}')")
    old.commit()
    old.close()
    conn = db.connect(path)
    assert db.list_briefings(conn)[0]["state"] == "complete"


def test_run_report_is_written_even_for_a_stand_in_run(tmp_path, monkeypatch):
    from helpers import FIXTURES
    config = tmp_path / "config.toml"
    config.write_text(
        f'[[feeds]]\nid = "alpha"\nname = "Alpha"\nurl = {json.dumps(str(FIXTURES / "feed_alpha.xml"))}\n'
        '[window]\nhours = 1000000\n', encoding="utf-8")
    report = tmp_path / "reports" / "run.json"
    assert main(["--config", str(config), "run", "--stand-in", "--date", "2026-11-23", "--report", str(report)]) == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["model"]["is_real_model"] is False
    assert data["run"]["state"] == "complete"
    assert data["validation"]["claims_published"] >= 1
    assert "gpu" in data["resources"] and data["resources"]["samples"] >= 2
    summary = report.with_suffix(".md").read_text(encoding="utf-8")
    assert "not a language model" in summary and "Output validation" in summary
