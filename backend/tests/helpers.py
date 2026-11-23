"""Shared test helpers: a fake LM Studio server and a local HTTP server."""
from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

from worldbrief.config import Config, Feed
from worldbrief.lm import LMStudioClient

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 23, 12, 0, 0, tzinfo=timezone.utc)

_BLOCK = re.compile(r"^\[(A\d+)\] [^\n]*\n(.*?)(?=\n\n\[A\d+\]|\Z)", re.M | re.S)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


def make_config(tmp_path: Path, feeds: list[Feed] | None = None) -> Config:
    cfg = Config()
    cfg.base_dir = tmp_path
    cfg.lmstudio.chat_model = "fake-model-q4"
    cfg.lmstudio.cooldown_s = 0
    cfg.feeds = feeds if feeds is not None else [
        Feed(id="alpha", name="Alpha Test Feed", url=str(FIXTURES / "feed_alpha.xml"), region_hint="europe"),
        Feed(id="beta", name="Beta Test Feed", url=str(FIXTURES / "feed_beta.xml"), region_hint="africa"),
    ]
    return cfg


class FakeLMStudio:
    """Stands in for LM Studio's HTTP server so the real client code runs.

    By default it behaves like a careful model: it copies the first sentence of
    each passage. `summarize` and `verify` can be replaced to make it misbehave.
    Every request body is kept in `requests`.
    """

    def __init__(self, summarize=None, verify=None, fail_tasks=()):
        self.requests: list[dict] = []
        self.summarize, self.verify, self.fail_tasks = summarize, verify, set(fail_tasks)

    def client(self, cfg: Config, max_calls: int | None = None) -> LMStudioClient:
        return LMStudioClient(cfg.lmstudio, cfg.limits.max_llm_calls if max_calls is None else max_calls,
                              transport=httpx.MockTransport(self._handle))

    def prompts(self, task: str) -> list[str]:
        return [r["messages"][1]["content"] for r in self.requests
                if r["response_format"]["json_schema"]["name"] == task]

    def _handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        task = body["response_format"]["json_schema"]["name"]
        user = body["messages"][1]["content"]
        if task in self.fail_tasks:
            return httpx.Response(500, json={"error": "simulated server error"})
        if task == "rank":
            reply = {"events": [{"cluster_id": int(i), "section": "europe", "importance": 3, "countries": [],
                                 "reason": "fake"} for i in re.findall(r"^Event (\d+) ", user, re.M)]}
        elif task == "summarize":
            blocks = _BLOCK.findall(user)
            reply = self.summarize(blocks) if self.summarize else default_summary(blocks)
        elif task == "verify":
            statements = re.findall(r"^(\d+)\. (.*) \(relies on: [^)]*\)$", user, re.M)
            reply = self.verify(statements) if self.verify else {
                "claims": [{"index": int(i), "verdict": "supported", "reason": "matches"} for i, _ in statements],
                "sources_conflict": False, "conflict_note": None}
        else:
            return httpx.Response(400, json={"error": f"unknown task {task}"})
        return httpx.Response(200, json={
            "choices": [{"message": {"content": json.dumps(reply)}}],
            "usage": {"prompt_tokens": len(user) // 4, "completion_tokens": len(json.dumps(reply)) // 4},
        })


def default_summary(blocks: list[tuple[str, str]]) -> dict:
    claims = []
    for ref, text in blocks[:2]:
        first = _SENTENCE.split(text.strip())[0]
        claims.append({"text": first, "article_ids": [ref], "quote": first})
    return {"headline": _SENTENCE.split(blocks[0][1].strip())[0].rstrip("."), "event_date": None, "claims": claims,
            "why_it_matters": None, "context": None, "uncertainty": None}


class LocalServer:
    """Serves canned responses on 127.0.0.1 for feed and API-shape tests.
    routes: {path: (status, body_bytes)} or {path: ("sleep", seconds)}."""

    def __init__(self, routes: dict):
        routes = dict(routes)

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                status, body = routes.get(self.path, (404, b"not found"))
                if status == "sleep":
                    time.sleep(body)
                    status, body = 200, b""
                self.send_response(status)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()


def passage(ref: str, text: str, published_at: str = "2026-11-23T06:00:00Z", title: str = "Report") -> dict:
    return {"ref": ref, "title": title, "text": text, "removed": [],
            "article": {"id": f"art-{ref}", "published_at": published_at}}


class Checker:
    """A scripted checking model. verdicts: {claim index: verdict}; default 'supported'."""
    name = "scripted checker"

    def __init__(self, verdicts=None, conflict=None):
        self.calls, self.verdicts, self.conflict = 0, verdicts or {}, conflict

    def embed(self, texts):
        return None

    def chat_json(self, task, system, user, schema, meta=None):
        self.calls += 1
        return {"claims": [{"index": i, "verdict": self.verdicts.get(i, "supported"), "reason": "scripted"}
                           for i in range(len(meta["claims"]))],
                "sources_conflict": bool(self.conflict), "conflict_note": self.conflict}


def draft(*claims) -> dict:
    return {"claims": [{"text": t, "article_ids": ids, "quote": q} for t, ids, q in claims]}
