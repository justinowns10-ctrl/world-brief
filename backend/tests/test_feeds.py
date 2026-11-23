"""Feed handling against a real local HTTP server: unavailable, slow,
malformed, empty and non-feed responses. No outside network is used."""
from __future__ import annotations

import json

from helpers import FIXTURES, NOW, FakeLMStudio, LocalServer, make_config
from worldbrief import db
from worldbrief.cli import main
from worldbrief.config import Feed
from worldbrief.ingest import parse_feed_detailed, probe_feed
from worldbrief.pipeline import run_pipeline

GOOD = (FIXTURES / "feed_alpha.xml").read_bytes()
TRUNCATED = GOOD[: GOOD.index(b"<item><title>Parliament")] + b"<item><title>Cut off mid-ite"
HTML = b"<!DOCTYPE html><html><head><title>Subscribe</title></head><body><h1>Please log in</h1></body></html>"
ATOM = b"""<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Atom Test</title>
<entry><title>Atom entry about a summit</title><link href="https://atom.test/summit"/>
<updated>2026-11-23T08:00:00Z</updated><summary>Leaders met for a summit in Testport.</summary></entry></feed>"""
NO_DATES = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>
<item><title>No date one</title><link>https://nodate.test/1</link><description>Body.</description></item></channel></rss>"""

ROUTES = {
    "/good.xml": (200, GOOD), "/truncated.xml": (200, TRUNCATED), "/page.html": (200, HTML),
    "/empty.xml": (200, b""), "/garbage.xml": (200, bytes(range(256)) * 20), "/atom.xml": (200, ATOM),
    "/nodates.xml": (200, NO_DATES), "/gone.xml": (404, b"gone"), "/error.xml": (500, b"boom"),
    "/slow.xml": ("sleep", 3),
}


def feed(server, name):
    return Feed(id=name.split(".")[0], name=name, url=f"{server.url}/{name}")


def test_probe_reports_each_kind_of_failure():
    with LocalServer(ROUTES) as server:
        good = probe_feed(feed(server, "good.xml"))
        assert good["ok"] and good["usable"] == 3 and good["skipped"] == 1 and not good["malformed"]
        assert good["newest"] == "2026-11-23T07:30:00Z"

        truncated = probe_feed(feed(server, "truncated.xml"))
        assert truncated["ok"] and truncated["malformed"] and truncated["usable"] == 1     # recovered what was intact

        atom = probe_feed(feed(server, "atom.xml"))
        assert atom["ok"] and atom["usable"] == 1 and atom["format"].startswith("atom")

        assert "HTTP 404" == probe_feed(feed(server, "gone.xml"))["error"]
        assert "HTTP 500" == probe_feed(feed(server, "error.xml"))["error"]
        for name in ("page.html", "empty.xml", "garbage.xml", "nodates.xml"):
            result = probe_feed(feed(server, name))
            assert not result["ok"] and "no usable entries" in result["error"], name

        slow = probe_feed(feed(server, "slow.xml"), timeout_s=0.5)
        assert not slow["ok"] and "Timeout" in slow["error"]

    refused = probe_feed(Feed(id="refused", name="r", url=server.url + "/good.xml"), timeout_s=2)   # server is closed now
    assert not refused["ok"] and "Connect" in refused["error"]


def test_pipeline_survives_bad_feeds_and_says_so(tmp_path):
    with LocalServer(ROUTES) as server:
        names = ["good.xml", "truncated.xml", "page.html", "empty.xml", "garbage.xml", "gone.xml", "error.xml"]
        cfg = make_config(tmp_path, feeds=[feed(server, n) for n in names])
        conn = db.connect(cfg.resolve(cfg.paths.database))
        briefing = run_pipeline(cfg, FakeLMStudio().client(cfg), conn, briefing_date="2026-11-23", now=NOW)
    assert briefing is not None and briefing["stories"]
    assert briefing["publication"]["state"] == "partial"
    assert "5 of 7 feeds could not be read." in briefing["publication"]["reasons"]
    errors = [e["message"] for e in conn.execute("SELECT message FROM run_events WHERE stage='ingest' AND level='error'")]
    assert len(errors) == 5
    assert any("malformed XML" in e["message"] for e in conn.execute("SELECT message FROM run_events WHERE level='info'"))


def test_undated_and_linkless_entries_are_counted_as_skipped():
    records, info = parse_feed_detailed(Feed(id="n", name="n", url="x"), NO_DATES)
    assert records == [] and info["entries"] == 1 and info["skipped"] == 1


def test_check_feeds_command_writes_a_report(tmp_path, capsys):
    with LocalServer(ROUTES) as server:
        config = tmp_path / "config.toml"
        config.write_text("".join(
            f'[[feeds]]\nid = "{n.split(".")[0]}"\nname = "{n}"\nurl = "{server.url}/{n}"\n'
            for n in ["good.xml", "gone.xml", "page.html"]), encoding="utf-8")
        report = tmp_path / "feeds.json"
        code = main(["--config", str(config), "check-feeds", "--report", str(report)])
    assert code == 1                                                    # at least one feed failed
    out = capsys.readouterr().out
    assert "good" in out and "OK: 3 usable of 4 entries" in out and "FAILED: HTTP 404" in out
    data = json.loads(report.read_text(encoding="utf-8"))
    assert [f["ok"] for f in data["feeds"]] == [True, False, False]
