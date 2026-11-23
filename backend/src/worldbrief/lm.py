"""Language-model access.

The pipeline talks to a small interface (`LanguageModel`), not to LM Studio
directly, so the model server can be swapped without touching the stages.

Workload bounds enforced here:
- one request at a time (calls are synchronous; nothing is sent in parallel)
- a per-call timeout, a prompt-size cap and an output-token cap
- a per-run call budget
- a pause between calls
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Protocol

import httpx
import jsonschema

from .config import LMStudio

log = logging.getLogger("worldbrief.lm")


class LMError(RuntimeError):
    """A model call failed after retries."""


class BudgetExceeded(LMError):
    """The run has used its allowed number of model calls."""


class LanguageModel(Protocol):
    name: str
    calls: int

    def chat_json(self, task: str, system: str, user: str, schema: dict, meta: Any = None) -> dict: ...

    def embed(self, texts: list[str]) -> list[list[float]] | None: ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def parse_json_reply(content: str) -> dict:
    """Parses model output, tolerating reasoning tags and code fences."""
    text = _THINK.sub("", content or "").strip()
    text = _FENCE.sub("", text).strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError("no JSON object in reply")
        text = text[start:end + 1]
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("reply is not a JSON object")
    return value


class LMStudioClient:
    """Client for LM Studio's OpenAI-compatible server."""

    def __init__(self, cfg: LMStudio, max_calls: int, transport: httpx.BaseTransport | None = None):
        if not cfg.chat_model:
            raise LMError("lmstudio.chat_model is not set in the config file")
        self.cfg = cfg
        self.name = cfg.chat_model
        self.max_calls = max_calls
        self.calls = 0
        self.total_seconds = 0.0
        self._client = httpx.Client(base_url=cfg.base_url.rstrip("/"), timeout=cfg.request_timeout_s, transport=transport)

    def list_models(self) -> list[str]:
        response = self._client.get("/models", timeout=10)
        response.raise_for_status()
        return [m.get("id", "?") for m in response.json().get("data", [])]

    def chat_json(self, task: str, system: str, user: str, schema: dict, meta: Any = None) -> dict:
        cfg = self.cfg
        room = cfg.max_prompt_chars - len(system)
        if len(user) > room:
            log.warning("%s: prompt truncated from %d to %d characters", task, len(user), room)
            user = user[:max(room, 0)]
        payload = {
            "model": cfg.chat_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_output_tokens,
            "stream": False,
            "response_format": {"type": "json_schema", "json_schema": {"name": task, "strict": True, "schema": schema}},
        }
        if cfg.model_ttl_s > 0:
            payload["ttl"] = cfg.model_ttl_s
        last: Exception | None = None
        for attempt in range(cfg.retries + 1):
            if self.calls >= self.max_calls:
                raise BudgetExceeded(f"model call budget of {self.max_calls} used up")
            self.calls += 1
            started = time.monotonic()
            try:
                response = self._client.post("/chat/completions", json=payload)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                value = parse_json_reply(content)
                jsonschema.validate(value, schema)
                return value
            except (httpx.HTTPError, KeyError, IndexError, ValueError, jsonschema.ValidationError) as exc:
                last = exc
                log.warning("%s: attempt %d failed: %s", task, attempt + 1, str(exc)[:200])
                time.sleep(min(2.0 * (attempt + 1), 10.0))
            finally:
                self.total_seconds += time.monotonic() - started
                if cfg.cooldown_s > 0:
                    time.sleep(cfg.cooldown_s)
        raise LMError(f"{task}: failed after {cfg.retries + 1} attempts: {last}")

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        if not self.cfg.embedding_model:
            return None
        vectors: list[list[float]] = []
        for i in range(0, len(texts), 32):
            batch = [t[:800] for t in texts[i:i + 32]]
            response = self._client.post("/embeddings", json={"model": self.cfg.embedding_model, "input": batch})
            response.raise_for_status()
            data = sorted(response.json()["data"], key=lambda d: d["index"])
            vectors.extend(d["embedding"] for d in data)
        return vectors


class StandInModel:
    """A rule-based stand-in used by tests and `--stand-in` runs.

    It is NOT a language model. It copies sentences out of the sources so the
    rest of the pipeline (validation, storage, API, app) can be exercised
    without LM Studio. Its output says nothing about real model quality.
    """

    name = "stand-in (no language model)"
    is_stand_in = True

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        return None

    def chat_json(self, task, system, user, schema, meta=None):
        self.calls += 1
        if task == "rank":
            return {"events": [
                {"cluster_id": c["cluster_id"], "section": c.get("hint") or "other_regions",
                 "importance": min(5, 1 + c["independent_sources"]), "countries": [], "reason": "stand-in"}
                for c in meta
            ]}
        if task == "summarize":
            from .text import sentences
            claims = []
            for passage in meta["passages"][:3]:
                first = sentences(passage["text"])[:1]
                if first:
                    claims.append({"text": first[0], "article_ids": [passage["ref"]], "quote": first[0]})
            return {"headline": meta["passages"][0]["title"], "event_date": None, "claims": claims,
                    "why_it_matters": None, "context": None, "uncertainty": None}
        if task == "verify":
            return {"claims": [{"index": i, "verdict": "supported", "reason": "copied from source"}
                               for i in range(len(meta["claims"]))],
                    "sources_conflict": False, "conflict_note": None}
        raise LMError(f"stand-in has no behaviour for task {task}")
