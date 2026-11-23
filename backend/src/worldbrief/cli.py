"""Command line entry point:  python -m worldbrief <command>"""
from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import sys
from pathlib import Path

from . import db
from .config import load_config

TOKEN_ENV = "WORLDBRIEF_API_TOKEN"


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers = [logging.StreamHandler(), logging.FileHandler(log_dir / "worldbrief.log", encoding="utf-8")]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def cmd_run(args) -> int:
    from .lm import LMStudioClient, StandInModel
    from .pipeline import run_pipeline

    cfg = load_config(args.config)
    setup_logging(cfg.resolve(cfg.paths.log_dir))
    if not cfg.feeds:
        print("No feeds configured. Copy config.example.toml to config.toml first.", file=sys.stderr)
        return 2
    model = StandInModel() if args.stand_in else LMStudioClient(cfg.lmstudio, cfg.limits.max_llm_calls)
    conn = db.connect(cfg.resolve(cfg.paths.database))
    briefing = run_pipeline(cfg, model, conn, briefing_date=args.date)
    if briefing is None:
        print("Nothing published. See the log for the reason.")
        return 1
    print(f"Published {briefing['id']}: {len(briefing['stories'])} stories.")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from .api import create_app

    cfg = load_config(args.config)
    token = os.environ.get(TOKEN_ENV, "")
    if len(token) < 16:
        print(f"Set {TOKEN_ENV} to a token of at least 16 characters (run: python -m worldbrief token).", file=sys.stderr)
        return 2
    host = args.host or cfg.api.host
    port = args.port or cfg.api.port
    app = create_app(str(cfg.resolve(cfg.paths.database)), token)
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


def cmd_load_demo(args) -> int:
    cfg = load_config(args.config)
    conn = db.connect(cfg.resolve(cfg.paths.database))
    for path in args.files:
        briefing = json.loads(Path(path).read_text(encoding="utf-8"))
        db.save_briefing(conn, briefing)
        print("loaded", briefing["id"])
    return 0


def cmd_check_lm(args) -> int:
    from .lm import LMStudioClient

    cfg = load_config(args.config)
    cfg.lmstudio.chat_model = cfg.lmstudio.chat_model or "unset"
    try:
        models = LMStudioClient(cfg.lmstudio, 1).list_models()
    except Exception as exc:
        print(f"Could not reach LM Studio at {cfg.lmstudio.base_url}: {exc}", file=sys.stderr)
        return 1
    print(f"LM Studio is reachable at {cfg.lmstudio.base_url}. Models it reports:")
    for m in models:
        print("  ", m)
    return 0


def cmd_status(args) -> int:
    cfg = load_config(args.config)
    conn = db.connect(cfg.resolve(cfg.paths.database))
    run = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    if run is None:
        print("No runs yet.")
        return 0
    print(f"Run {run['id']} for {run['briefing_id']}: {run['status']} ({run['started_at']} to {run['finished_at']})")
    print("Stats:", run["stats"])
    for e in conn.execute("SELECT * FROM run_events WHERE run_id=? ORDER BY id", (run["id"],)):
        print(f"  {e['at']} {e['level']:5} {e['stage']:9} {e['message']}")
    removed = conn.execute(
        "SELECT story_headline, claim_text, verdict, reason FROM claim_audit WHERE run_id=? AND published=0", (run["id"],)
    ).fetchall()
    if removed:
        print("Claims removed before publication:")
        for r in removed:
            print(f"  [{r['verdict']}] {r['claim_text']}  ({r['reason']})")
    return 0


def cmd_token(args) -> int:
    print(secrets.token_urlsafe(32))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="worldbrief")
    parser.add_argument("--config", default="config.toml" if Path("config.toml").exists() else None)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run", help="fetch feeds and publish today's briefing")
    p.add_argument("--stand-in", action="store_true", help="use the rule-based stand-in instead of LM Studio (testing only)")
    p.add_argument("--date", help="briefing date, YYYY-MM-DD (default: today, UTC)")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("serve", help="start the API")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("load-demo", help="store demonstration briefings so the API has something to serve")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=cmd_load_demo)

    sub.add_parser("check-lm", help="check that LM Studio is reachable and list its models").set_defaults(func=cmd_check_lm)
    sub.add_parser("status", help="show the last run, its log and removed claims").set_defaults(func=cmd_status)
    sub.add_parser("token", help="print a new random API token").set_defaults(func=cmd_token)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
