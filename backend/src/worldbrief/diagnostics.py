"""Measurement for real runs: what model ran, how long calls took, how much
memory was used, and what validation did with the output. Used by
`worldbrief run --report`. Nothing here changes what the pipeline produces.
"""
from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

import httpx

from . import PIPELINE_VERSION


def lmstudio_model_info(base_url: str, model_id: str) -> dict:
    """Asks LM Studio's native REST API what it knows about the model:
    quantization, architecture, context length, load settings. Tries the v1
    API, then the older v0 API. Returns the raw record so nothing is lost if
    field names differ between LM Studio versions."""
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    tried = []
    for path in ("/api/v1/models", "/api/v0/models"):
        try:
            response = httpx.get(root + path, timeout=10)
            response.raise_for_status()
            body = response.json()
            entries = body.get("models") or body.get("data") or []
            for entry in entries:
                if model_id in (entry.get("key"), entry.get("id")) or any(
                        model_id == inst.get("id") for inst in entry.get("loaded_instances") or []):
                    return {"endpoint": path, "found": True, "record": entry}
            tried.append(f"{path}: reachable, model '{model_id}' not listed "
                         f"({len(entries)} models: {[e.get('key') or e.get('id') for e in entries][:12]})")
        except Exception as exc:
            tried.append(f"{path}: {type(exc).__name__}: {str(exc)[:120]}")
    return {"found": False, "tried": tried}


class ResourceSampler:
    """Samples GPU memory and load with nvidia-smi, and system memory with
    psutil when it is installed, every `interval` seconds on a background
    thread. Reports peaks. Missing tools are reported, not fatal."""

    QUERY = "memory.used,memory.total,utilization.gpu,temperature.gpu,name"

    def __init__(self, interval: float = 2.0):
        self.interval = interval
        self.samples = 0
        self.gpu = {"available": shutil.which("nvidia-smi") is not None}
        self.system: dict = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        try:
            import psutil  # optional
            self._psutil = psutil
        except ImportError:
            self._psutil = None
            self.system = {"available": False, "note": "install psutil to record system memory (pip install psutil)"}

    def _sample(self) -> None:
        if self.gpu["available"]:
            try:
                out = subprocess.run(
                    ["nvidia-smi", f"--query-gpu={self.QUERY}", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=10, check=True,
                ).stdout.strip().splitlines()[0]
                used, total, load, temp, name = [x.strip() for x in out.split(",", 4)]
                g = self.gpu
                g["name"] = name
                g["memory_total_mib"] = int(total)
                g["memory_used_mib_start"] = g.get("memory_used_mib_start", int(used))
                g["memory_used_mib_peak"] = max(g.get("memory_used_mib_peak", 0), int(used))
                g["utilization_pct_peak"] = max(g.get("utilization_pct_peak", 0), int(load))
                g["temperature_c_peak"] = max(g.get("temperature_c_peak", 0), int(temp))
            except Exception as exc:
                self.gpu["error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
        if self._psutil is not None:
            vm = self._psutil.virtual_memory()
            s = self.system
            s["available"] = True
            s["memory_total_mib"] = vm.total // 2**20
            s["memory_used_mib_start"] = s.get("memory_used_mib_start", vm.used // 2**20)
            s["memory_used_mib_peak"] = max(s.get("memory_used_mib_peak", 0), vm.used // 2**20)
            s["cpu_pct_peak"] = max(s.get("cpu_pct_peak", 0.0), self._psutil.cpu_percent(interval=None))
        self.samples += 1

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._sample()
            self._stop.wait(self.interval)

    def start(self) -> "ResourceSampler":
        self._sample()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=15)
        self._sample()
        if not self.gpu["available"]:
            self.gpu["note"] = "nvidia-smi was not found on PATH; GPU memory was not recorded"
        return {"interval_s": self.interval, "samples": self.samples, "gpu": self.gpu, "system": self.system}


def summarize_calls(call_log: list[dict]) -> dict:
    by_task: dict[str, dict] = {}
    for c in call_log:
        t = by_task.setdefault(c["task"], {"calls": 0, "failed": 0, "seconds_total": 0.0, "seconds_max": 0.0,
                                           "prompt_tokens": 0, "completion_tokens": 0})
        t["calls"] += 1
        t["failed"] += 0 if c["ok"] else 1
        t["seconds_total"] = round(t["seconds_total"] + c["seconds"], 3)
        t["seconds_max"] = max(t["seconds_max"], c["seconds"])
        t["prompt_tokens"] += c.get("prompt_tokens") or 0
        t["completion_tokens"] += c.get("completion_tokens") or 0
    for t in by_task.values():
        t["seconds_mean"] = round(t["seconds_total"] / t["calls"], 3)
        if t["completion_tokens"] and t["seconds_total"]:
            t["completion_tokens_per_second"] = round(t["completion_tokens"] / t["seconds_total"], 1)
    return by_task


def build_report(cfg, model, conn, briefing, resources: dict, wall_seconds: float) -> dict:
    run = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    audit = [dict(r) for r in conn.execute(
        "SELECT story_headline, claim_text, verdict, published, reason FROM claim_audit WHERE run_id=?", (run["id"],))]
    events = [dict(r) for r in conn.execute(
        "SELECT at, stage, level, message FROM run_events WHERE run_id=? ORDER BY id", (run["id"],))]
    call_log = getattr(model, "call_log", [])
    verdicts: dict[str, int] = {}
    for a in audit:
        verdicts[a["verdict"]] = verdicts.get(a["verdict"], 0) + 1
    stand_in = getattr(model, "is_stand_in", False)
    return {
        "report_version": 1,
        "pipeline_version": PIPELINE_VERSION,
        "environment": {
            "os": platform.platform(), "machine": platform.machine(), "python": sys.version.split()[0],
        },
        "model": {
            "id": model.name,
            "is_real_model": not stand_in,
            "lmstudio": None if stand_in else lmstudio_model_info(cfg.lmstudio.base_url, cfg.lmstudio.chat_model),
            "embedding_model": cfg.lmstudio.embedding_model or None,
        },
        "runtime_settings": {"lmstudio": asdict(cfg.lmstudio), "limits": asdict(cfg.limits),
                             "clustering": asdict(cfg.clustering), "window_hours": cfg.window.hours},
        "run": {
            "briefing_id": run["briefing_id"], "state": {"running": "pending"}.get(run["status"], run["status"]),
            "started_at": run["started_at"], "finished_at": run["finished_at"],
            "wall_seconds": round(wall_seconds, 1), "stats": json.loads(run["stats"] or "{}"),
        },
        "inference": {
            "calls": len(call_log), "seconds_total": round(sum(c["seconds"] for c in call_log), 1),
            "by_task": summarize_calls(call_log), "call_log": call_log,
        },
        "resources": resources,
        "validation": {
            "claims_checked": len(audit),
            "claims_published": sum(1 for a in audit if a["published"]),
            "claims_removed": sum(1 for a in audit if not a["published"]),
            "verdicts": verdicts,
            "removed": [a for a in audit if not a["published"]],
            "partly_confirmed": [a for a in audit if a["published"] and a["verdict"] == "partial"],
            "stories_by_status": json.loads(run["stats"] or "{}").get("stories_by_status"),
        },
        "publication": (briefing or {}).get("publication"),
        "log": events,
    }


def write_report(report: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md = path.with_suffix(".md")
    r, m, inf, res, val = report["run"], report["model"], report["inference"], report["resources"], report["validation"]
    lm = (m.get("lmstudio") or {})
    rec = lm.get("record") or {}
    quant = rec.get("quantization")
    if isinstance(quant, dict):
        quant = quant.get("name") or json.dumps(quant)
    lines = [
        f"# Real-run report: {r['briefing_id']}", "",
        f"- State: **{r['state']}**" + (f" ({'; '.join(report['publication']['reasons'])})"
                                         if report.get("publication") and report["publication"].get("reasons") else ""),
        f"- Environment: {report['environment']['os']}, Python {report['environment']['python']}",
        f"- Model: `{m['id']}`" + ("" if m["is_real_model"] else " (**not a language model**)"),
        f"- Quantization: {quant or 'not reported by LM Studio'}",
        f"- Architecture / format: {rec.get('arch') or rec.get('architecture') or '?'} / "
        f"{rec.get('compatibility_type') or rec.get('format') or '?'}",
        f"- Context: max {rec.get('max_context_length', '?')}, loaded "
        f"{rec.get('loaded_context_length') or [i.get('config', {}).get('context_length') for i in rec.get('loaded_instances') or []] or '?'}",
        f"- Wall time: {r['wall_seconds']} s; inference {inf['seconds_total']} s over {inf['calls']} calls", "",
        "| Task | Calls | Failed | Mean s | Max s | Prompt tok | Output tok | Output tok/s |", "|---|---|---|---|---|---|---|---|",
    ]
    for task, t in inf["by_task"].items():
        lines.append(f"| {task} | {t['calls']} | {t['failed']} | {t['seconds_mean']} | {t['seconds_max']} | "
                     f"{t['prompt_tokens']} | {t['completion_tokens']} | {t.get('completion_tokens_per_second', '')} |")
    g, s = res.get("gpu", {}), res.get("system", {})
    lines += ["", "## Peak resource use", "",
              (f"- GPU {g.get('name', '')}: {g.get('memory_used_mib_peak')} of {g.get('memory_total_mib')} MiB "
               f"(started at {g.get('memory_used_mib_start')}), load peak {g.get('utilization_pct_peak')} %, "
               f"{g.get('temperature_c_peak')} C" if g.get("memory_used_mib_peak") is not None
               else f"- GPU: not recorded ({g.get('note') or g.get('error')})"),
              (f"- System memory: {s.get('memory_used_mib_peak')} of {s.get('memory_total_mib')} MiB "
               f"(started at {s.get('memory_used_mib_start')}), CPU peak {s.get('cpu_pct_peak')} %"
               if s.get("available") else f"- System memory: not recorded ({s.get('note')})"),
              f"- {res.get('samples')} samples, every {res.get('interval_s')} s. "
              "These are whole-machine figures and include anything else that was running.",
              "", "## Output validation", "",
              f"- Claims drafted and checked: {val['claims_checked']}",
              f"- Published: {val['claims_published']} ({len(val['partly_confirmed'])} only partly confirmed)",
              f"- Removed: {val['claims_removed']}",
              f"- Verdicts: {val['verdicts']}",
              f"- Stories by status: {val['stories_by_status']}", ""]
    if val["removed"]:
        lines += ["### Removed claims", ""] + [f"- [{a['verdict']}] {a['claim_text']} ({a['reason']})" for a in val["removed"]] + [""]
    if val["partly_confirmed"]:
        lines += ["### Partly confirmed claims", ""] + [f"- {a['claim_text']} ({a['reason']})" for a in val["partly_confirmed"]] + [""]
    lines += ["## Run log", ""] + [f"- {e['at']} {e['level']} {e['stage']}: {e['message']}" for e in report["log"]]
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_measurements(report, path.with_name("MEASUREMENTS.md"))
    return md


def write_measurements(report: dict, path: Path) -> Path:
    """A numbers-only summary of a run: no headlines, claims or source text, so
    it can be kept in version control when the run's content cannot."""
    r, inf, res, val = report["run"], report["inference"], report["resources"], report["validation"]
    st = r["stats"]
    rec = ((report["model"].get("lmstudio") or {}).get("record")) or {}
    quant = rec.get("quantization")
    if isinstance(quant, dict):
        quant = f"{quant.get('name')}, {quant.get('bits_per_weight')} bits per weight"
    loaded = [i.get("config", {}) for i in rec.get("loaded_instances") or []]
    load = (f"context {loaded[0].get('context_length')} of {rec.get('max_context_length')}, "
            f"parallel slots {loaded[0].get('parallel')}, flash attention {loaded[0].get('flash_attention')}"
            if loaded else "not reported")
    lm = report["runtime_settings"]["lmstudio"]
    g, sysm = res.get("gpu", {}), res.get("system", {})
    rows = [
        ("Host", f"{report['environment']['os']}, Python {report['environment']['python']}"),
        ("Pipeline version", report["pipeline_version"]),
        ("Model", f"`{report['model']['id']}` ({rec.get('params_string', '?')}, {quant or 'quantization not reported'}, "
                  f"{rec.get('format', '?')})" + ("" if report["model"]["is_real_model"] else " NOT A LANGUAGE MODEL")),
        ("Load settings", load),
        ("Backend settings", f"temperature {lm['temperature']}, max output tokens {lm['max_output_tokens']}, "
                             f"prompt cap {lm['max_prompt_chars']} characters, one request at a time"),
        ("Embedding model", report["model"]["embedding_model"] or "none"),
        ("Feeds", f"{st.get('feeds_ok')} read, {st.get('feeds_failed')} failed, {st.get('articles_new')} new articles, "
                  f"{st.get('articles_considered')} in the window"),
        ("Article kinds", str(st.get("article_kinds"))),
        ("Events", f"{st.get('clusters')} clusters ({st.get('clustering')}); {st.get('events')}"),
        ("Wall time", f"{r['wall_seconds']} s"),
        ("Inference", f"{inf['calls']} calls, {inf['seconds_total']} s"),
        ("GPU", f"{g.get('name')}: peak {g.get('memory_used_mib_peak')} of {g.get('memory_total_mib')} MiB "
                f"(start {g.get('memory_used_mib_start')}), load peak {g.get('utilization_pct_peak')} %, "
                f"{g.get('temperature_c_peak')} C" if g.get("memory_used_mib_peak") is not None else "not recorded"),
        ("System memory", f"peak {sysm.get('memory_used_mib_peak')} of {sysm.get('memory_total_mib')} MiB "
                          f"(start {sysm.get('memory_used_mib_start')}), CPU peak {sysm.get('cpu_pct_peak')} %"
                          if sysm.get("available") else "not recorded"),
        ("Claims", f"{val['claims_checked']} drafted, {val['claims_published']} published "
                   f"({len(val['partly_confirmed'])} partly confirmed), {val['claims_removed']} removed; "
                   f"verdicts {val['verdicts']}"),
        ("Stories", f"{st.get('stories')}: {val['stories_by_status']}"),
        ("State", r["state"] + (": " + "; ".join(report["publication"]["reasons"])
                                if report.get("publication") and report["publication"].get("reasons") else "")),
    ]
    lines = [f"# Measurements: run for {r['briefing_id']}, started {r['started_at']}", "",
             "Numbers only. The briefing, claims, run log and source records are kept beside this file on the "
             "machine that ran it and are not in Git.", "", "| | |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    lines += ["", "| Task | Calls | Failed | Mean s | Max s | Prompt tokens | Output tokens | Output tokens/s |",
              "|---|---|---|---|---|---|---|---|"]
    for task, t in inf["by_task"].items():
        lines.append(f"| {task} | {t['calls']} | {t['failed']} | {t['seconds_mean']} | {t['seconds_max']} | "
                     f"{t['prompt_tokens']} | {t['completion_tokens']} | {t.get('completion_tokens_per_second', '')} |")
    lines += ["", "Resource figures are for the whole machine and include anything else that was running.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
