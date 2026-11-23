"""Stage 6: check every drafted claim against the passages it cites.

A claim is published only if all of these hold:
  1. it cites at least one passage that was actually given to the model;
  2. a passage in a cited article matches it (the published quote is always
     text taken from the stored source record, never the model's wording);
  3. a second model pass, shown only the cited passages, does not judge it
     unsupported or contradicted.
Numbers and names that do not appear in the cited passages downgrade a claim
to "partial". None of this proves a claim is true. It shows the claim is what
the cited sources say, which is the most a pipeline without its own reporting
can establish.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta

from .lm import LMError
from .text import STOPWORDS, clean_text, normalize, sentences, tokens

log = logging.getLogger("worldbrief.validate")

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_NAME = re.compile(r"\b[A-Z][a-zA-Z]{2,}\b")
_RANK = {"supported": 0, "partial": 1, "unsupported": 2, "contradicted": 2}

VERIFY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["claims", "sources_conflict", "conflict_note"],
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["index", "verdict", "reason"],
                "properties": {
                    "index": {"type": "integer"},
                    "verdict": {"type": "string", "enum": ["supported", "partial", "unsupported", "contradicted"]},
                    "reason": {"type": "string"},
                },
            },
        },
        "sources_conflict": {"type": "boolean"},
        "conflict_note": {"type": ["string", "null"]},
    },
}

VERIFY_SYSTEM = (
    "You are a fact-checking step. You are given source passages and numbered statements. Each statement names the "
    "passages it relies on. Judge each statement using ONLY those passages, not your own knowledge:\n"
    "- supported: the passages state it.\n"
    "- partial: the passages state only part of it, or it is stronger or more certain than the passages.\n"
    "- unsupported: the passages do not state it.\n"
    "- contradicted: a passage says otherwise.\n"
    "Give a short reason for each. Then set sources_conflict to true if the passages disagree with each other on a "
    "material fact, and describe the disagreement in conflict_note; otherwise false and null. Reply with JSON only."
)


def numbers_in(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in _NUMBER.findall(text)}


def names_in(text: str) -> set[str]:
    out = set()
    for sentence in sentences(text) or [text]:
        for i, match in enumerate(_NAME.finditer(sentence)):
            word = match.group(0)
            if match.start() == 0 or word.lower() in STOPWORDS:
                continue
            out.add(word.lower())
    return out


def locate(needle: str, haystack: str, threshold: float) -> str | None:
    """Finds the source text that corresponds to `needle`. Returns text from the
    source itself, or None."""
    if not needle or not haystack:
        return None
    n = normalize(needle)
    if len(n.split()) >= 4 and n in normalize(haystack):
        for sentence in sentences(haystack):
            if n in normalize(sentence):
                return sentence[:400]
        return needle.strip()[:400]
    wanted = set(tokens(needle))
    if len(wanted) < 3:
        return None
    best, best_score = None, 0.0
    for sentence in sentences(haystack):
        score = len(wanted & set(tokens(sentence))) / len(wanted)
        if score > best_score:
            best, best_score = sentence, score
    return best[:400] if best is not None and best_score >= threshold else None


def unseen_numbers(text: str | None, source_text: str) -> set[str]:
    return numbers_in(text or "") - numbers_in(source_text)


def valid_event_date(value: str | None, earliest: date, latest: date) -> str | None:
    if not value:
        return None
    try:
        d = date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None
    return d.isoformat() if earliest - timedelta(days=60) <= d <= latest + timedelta(days=1) else None


def validate_event(draft: dict, passages: list[dict], model) -> dict:
    """Returns {'claims': [...publishable...], 'audit': [...every claim...],
    'conflict': bool, 'conflict_note': str|None, 'checked_by_model': bool}."""
    by_ref = {p["ref"]: p for p in passages}
    audit: list[dict] = []
    candidates: list[dict] = []

    for raw in draft.get("claims", []):
        text = clean_text(raw.get("text"))
        if not text:
            continue
        refs = [r.strip().strip("[]").upper() for r in raw.get("article_ids", []) if isinstance(r, str)]
        cited = [by_ref[r] for r in dict.fromkeys(refs) if r in by_ref]
        unknown = [r for r in refs if r not in by_ref]
        if not cited:
            audit.append({"text": text, "verdict": "unsupported", "published": False,
                          "reason": f"cites no passage that was provided ({', '.join(unknown) or 'none'})"})
            continue
        evidence = []
        for p in cited:
            quote = locate(raw.get("quote", ""), p["text"], 0.7) or locate(text, p["text"], 0.6)
            if quote:
                evidence.append({"passage": p, "quote": quote})
        if not evidence:
            audit.append({"text": text, "verdict": "unsupported", "published": False,
                          "reason": "no text in the cited passages matches the claim or its quote"})
            continue
        cited_text = " ".join(p["text"] for p in cited)
        notes = []
        missing_numbers = numbers_in(text) - numbers_in(cited_text)
        if missing_numbers:
            notes.append("figure not found in cited passages: " + ", ".join(sorted(missing_numbers)))
        cited_norm = f" {normalize(cited_text)} "
        missing_names = sorted(n for n in names_in(text) if f" {n} " not in cited_norm)
        if missing_names:
            notes.append("name not found in cited passages: " + ", ".join(missing_names))
        candidates.append({
            "text": text, "cited": [e["passage"] for e in evidence], "evidence": evidence,
            "verdict": "partial" if notes else "supported", "notes": notes,
        })

    conflict, conflict_note, checked = False, None, False
    if candidates:
        used = []
        for c in candidates:
            for p in c["cited"]:
                if p not in used:
                    used.append(p)
        prompt = "Source passages:\n\n" + "\n\n".join(f"[{p['ref']}] {p['text']}" for p in used)
        prompt += "\n\nStatements:\n" + "\n".join(
            f"{i}. {c['text']} (relies on: {', '.join(p['ref'] for p in c['cited'])})" for i, c in enumerate(candidates)
        )
        try:
            reply = model.chat_json(
                "verify", VERIFY_SYSTEM, prompt, VERIFY_SCHEMA,
                meta={"claims": [c["text"] for c in candidates]},
            )
            checked = True
            seen = set()
            for item in reply["claims"]:
                i = item["index"]
                if not 0 <= i < len(candidates) or i in seen:
                    continue
                seen.add(i)
                c = candidates[i]
                if _RANK[item["verdict"]] > _RANK[c["verdict"]]:
                    c["verdict"] = item["verdict"]
                if item["verdict"] != "supported" and item.get("reason"):
                    c["notes"].append(clean_text(item["reason"])[:240])
            for i, c in enumerate(candidates):
                if i not in seen and c["verdict"] == "supported":
                    c["verdict"] = "partial"
                    c["notes"].append("the consistency check returned no verdict for this claim")
            conflict = bool(reply.get("sources_conflict"))
            conflict_note = clean_text(reply.get("conflict_note")) or None
        except LMError as exc:
            log.warning("claim check did not run: %s", exc)
            for c in candidates:
                if c["verdict"] == "supported":
                    c["verdict"] = "partial"
                c["notes"].append("the automatic consistency check did not run")

    published = []
    for c in candidates:
        ok = c["verdict"] in ("supported", "partial")
        audit.append({"text": c["text"], "verdict": c["verdict"], "published": ok, "reason": "; ".join(c["notes"]) or None})
        if c["verdict"] == "contradicted":
            conflict = True
        if ok:
            published.append({
                "text": c["text"], "support": c["verdict"],
                "note": "; ".join(c["notes"]) or None, "evidence": c["evidence"],
            })
    return {"claims": published, "audit": audit, "conflict": conflict,
            "conflict_note": conflict_note if conflict else None, "checked_by_model": checked}
