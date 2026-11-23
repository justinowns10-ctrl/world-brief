"""Stage 5: ask the model for a source-grounded draft of one event.

The model never writes URLs or source names. It refers to passages by the
short labels it is shown (A1, A2, ...); code maps those back to stored records.
"""
from __future__ import annotations

from .ingest import full_text

SUMMARY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["headline", "event_date", "claims", "why_it_matters", "context", "uncertainty"],
    "properties": {
        "headline": {"type": "string"},
        "event_date": {"type": ["string", "null"]},
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "article_ids", "quote"],
                "properties": {
                    "text": {"type": "string"},
                    "article_ids": {"type": "array", "items": {"type": "string"}},
                    "quote": {"type": "string"},
                },
            },
        },
        "why_it_matters": {"type": ["string", "null"]},
        "context": {"type": ["string", "null"]},
        "uncertainty": {"type": ["string", "null"]},
    },
}

SUMMARY_SYSTEM = (
    "You write one entry of an international news briefing from the numbered source passages you are given. "
    "Rules:\n"
    "1. Use only what the passages say. Do not add facts, figures, names or dates from memory.\n"
    "2. Write 2 to 4 claims. Each claim is one short factual sentence in neutral language.\n"
    "3. For each claim, list the passage labels (for example A1) that state it, and copy one sentence or phrase "
    "word for word from one of those passages as the quote.\n"
    "4. Attribute contested statements to who made them (for example: officials said).\n"
    "5. event_date is the day the event happened in YYYY-MM-DD form only if a passage states it; otherwise null. "
    "Do not use the publication date as the event date.\n"
    "6. why_it_matters is one sentence of analysis. context is one sentence of background, or null. "
    "uncertainty states what the passages leave unknown or disagree on, or null.\n"
    "7. headline is a plain factual headline of at most 12 words.\n"
    "Reply with JSON only."
)


def choose_passages(articles: list[dict], max_articles: int, max_chars: int) -> list[dict]:
    """Prefers one article per outlet and original reporting over copies."""
    ordered = sorted(articles, key=lambda a: (a.get("role") == "syndicated", a["published_at"]))
    picked, seen = [], set()
    for a in ordered:
        if a["source_id"] not in seen:
            picked.append(a)
            seen.add(a["source_id"])
    for a in ordered:
        if a not in picked:
            picked.append(a)
    passages = []
    for i, a in enumerate(picked[:max_articles], start=1):
        passages.append({
            "ref": f"A{i}",
            "article": a,
            "title": a["title"],
            "text": full_text(a)[:max_chars],
        })
    return passages


def build_prompt(passages: list[dict], source_names: dict[str, str]) -> str:
    blocks = []
    for p in passages:
        a = p["article"]
        blocks.append(
            f"[{p['ref']}] {source_names.get(a['source_id'], a['source_id'])}, published {a['published_at']}\n{p['text']}"
        )
    return "Source passages:\n\n" + "\n\n".join(blocks)


def draft_event(passages: list[dict], source_names: dict[str, str], model) -> dict:
    meta = {"passages": [{"ref": p["ref"], "title": p["title"], "text": p["text"]} for p in passages]}
    return model.chat_json("summarize", SUMMARY_SYSTEM, build_prompt(passages, source_names), SUMMARY_SCHEMA, meta=meta)
