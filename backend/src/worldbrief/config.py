"""Configuration: defaults plus an optional TOML file."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass
class Paths:
    database: str = "data/worldbrief.db"
    log_dir: str = "data/logs"
    export_dir: str = "data/briefings"


@dataclass
class Window:
    hours: int = 30


@dataclass
class LMStudio:
    base_url: str = "http://127.0.0.1:1234/v1"
    chat_model: str = ""
    embedding_model: str = ""
    temperature: float = 0.1
    request_timeout_s: float = 180.0
    retries: int = 2
    cooldown_s: float = 1.0
    max_prompt_chars: int = 14000
    max_output_tokens: int = 900
    model_ttl_s: int = 0


@dataclass
class Limits:
    max_articles: int = 300
    max_candidate_events: int = 40
    max_stories: int = 12
    max_stories_per_section: int = 3
    max_articles_per_event: int = 5
    max_chars_per_article: int = 1500
    max_llm_calls: int = 80
    max_run_minutes: float = 45.0


@dataclass
class Clustering:
    embedding_threshold: float = 0.78
    event_threshold: float = 0.22
    lexical_threshold: float = 0.30   # no longer used; accepted so existing config files still load


@dataclass
class Api:
    host: str = "127.0.0.1"
    port: int = 8000


@dataclass
class Feed:
    id: str
    name: str
    url: str
    country: str | None = None
    type: str | None = None
    homepage: str | None = None
    region_hint: str | None = None


@dataclass
class Config:
    paths: Paths = field(default_factory=Paths)
    window: Window = field(default_factory=Window)
    lmstudio: LMStudio = field(default_factory=LMStudio)
    limits: Limits = field(default_factory=Limits)
    clustering: Clustering = field(default_factory=Clustering)
    api: Api = field(default_factory=Api)
    feeds: list[Feed] = field(default_factory=list)
    base_dir: Path = field(default_factory=Path.cwd)

    def resolve(self, relative: str) -> Path:
        p = Path(relative)
        return p if p.is_absolute() else self.base_dir / p


def _fill(obj, data: dict, section: str):
    known = {f.name for f in fields(obj)}
    for key, value in data.items():
        if key not in known:
            raise ValueError(f"Unknown setting [{section}] {key}")
        setattr(obj, key, value)
    return obj


def load_config(path: str | Path | None) -> Config:
    cfg = Config()
    if path is None:
        return cfg
    path = Path(path)
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    cfg.base_dir = path.resolve().parent
    for section in ("paths", "window", "lmstudio", "limits", "clustering", "api"):
        if section in raw:
            _fill(getattr(cfg, section), raw[section], section)
    cfg.feeds = [Feed(**f) for f in raw.get("feeds", [])]
    ids = [f.id for f in cfg.feeds]
    if len(ids) != len(set(ids)):
        raise ValueError("Feed ids must be unique")
    return cfg
