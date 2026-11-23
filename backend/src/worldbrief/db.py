"""SQLite storage: source records, run history, claim audit, published briefings."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, country TEXT, type TEXT, homepage TEXT
);
CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    url TEXT NOT NULL,
    canonical_url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    published_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    briefing_id TEXT, started_at TEXT NOT NULL, finished_at TEXT,
    status TEXT NOT NULL, stats TEXT
);
CREATE TABLE IF NOT EXISTS run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL, at TEXT NOT NULL, stage TEXT NOT NULL,
    level TEXT NOT NULL, message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS claim_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL, story_headline TEXT, claim_text TEXT NOT NULL,
    verdict TEXT NOT NULL, published INTEGER NOT NULL, reason TEXT
);
CREATE TABLE IF NOT EXISTS briefings (
    id TEXT PRIMARY KEY, generated_at TEXT NOT NULL, title TEXT NOT NULL,
    story_count INTEGER NOT NULL, is_demo INTEGER NOT NULL, json TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def upsert_source(conn, feed) -> None:
    conn.execute(
        "INSERT INTO sources(id,name,country,type,homepage) VALUES(?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name,country=excluded.country,"
        "type=excluded.type,homepage=excluded.homepage",
        (feed.id, feed.name, feed.country, feed.type, feed.homepage),
    )


def insert_article(conn, a: dict) -> bool:
    cur = conn.execute(
        "INSERT OR IGNORE INTO articles(id,source_id,url,canonical_url,title,text,published_at,fetched_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (a["id"], a["source_id"], a["url"], a["canonical_url"], a["title"], a["text"], a["published_at"], now_iso()),
    )
    return cur.rowcount == 1


def articles_since(conn, since_iso: str, limit: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM articles WHERE published_at >= ? ORDER BY published_at DESC LIMIT ?", (since_iso, limit)
    ).fetchall()
    return [dict(r) for r in rows]


def sources_by_id(conn) -> dict[str, dict]:
    return {r["id"]: dict(r) for r in conn.execute("SELECT * FROM sources")}


def start_run(conn, briefing_id: str) -> int:
    cur = conn.execute(
        "INSERT INTO runs(briefing_id,started_at,status) VALUES(?,?,?)", (briefing_id, now_iso(), "running")
    )
    conn.commit()
    return cur.lastrowid


def finish_run(conn, run_id: int, status: str, stats: dict) -> None:
    conn.execute(
        "UPDATE runs SET finished_at=?, status=?, stats=? WHERE id=?", (now_iso(), status, json.dumps(stats), run_id)
    )
    conn.commit()


def log_event(conn, run_id: int, stage: str, level: str, message: str) -> None:
    conn.execute(
        "INSERT INTO run_events(run_id,at,stage,level,message) VALUES(?,?,?,?,?)",
        (run_id, now_iso(), stage, level, message[:2000]),
    )
    conn.commit()


def audit_claim(conn, run_id: int, headline: str, text: str, verdict: str, published: bool, reason: str | None) -> None:
    conn.execute(
        "INSERT INTO claim_audit(run_id,story_headline,claim_text,verdict,published,reason) VALUES(?,?,?,?,?,?)",
        (run_id, headline, text, verdict, int(published), reason),
    )


def save_briefing(conn, briefing: dict) -> None:
    conn.execute(
        "INSERT INTO briefings(id,generated_at,title,story_count,is_demo,json) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET generated_at=excluded.generated_at,title=excluded.title,"
        "story_count=excluded.story_count,is_demo=excluded.is_demo,json=excluded.json",
        (
            briefing["id"], briefing["generatedAt"], briefing["title"], len(briefing["stories"]),
            int(bool(briefing.get("isDemo", False))), json.dumps(briefing, ensure_ascii=False),
        ),
    )
    conn.commit()


def list_briefings(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT id, generated_at, title, story_count, is_demo FROM briefings ORDER BY id DESC"
    ).fetchall()
    return [
        {"id": r["id"], "date": r["id"], "generatedAt": r["generated_at"], "title": r["title"],
         "storyCount": r["story_count"], "isDemo": bool(r["is_demo"])}
        for r in rows
    ]


def get_briefing(conn, briefing_id: str) -> dict | None:
    row = conn.execute("SELECT json FROM briefings WHERE id=?", (briefing_id,)).fetchone()
    return json.loads(row["json"]) if row else None
