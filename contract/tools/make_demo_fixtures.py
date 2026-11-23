"""Builds the demonstration briefings used as test fixtures and as the Android
app's bundled demo data. Everything here is invented and labelled as such:
fictional outlets, example.com links, isDemo = true.

Run from the repo root:  python contract/tools/make_demo_fixtures.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "contract" / "examples"
ANDROID_ASSETS = ROOT / "android" / "app" / "src" / "main" / "assets" / "demo"

SOURCES = {
    "meridian": ("Meridian Wire (demo)", "International", "wire"),
    "northlight": ("Northlight Broadcasting (demo)", "Norway", "broadcaster"),
    "ledger": ("The Coast Ledger (demo)", "Nigeria", "newspaper"),
    "andes": ("Andes Daily (demo)", "Peru", "newspaper"),
    "straits": ("Straits Dispatch (demo)", "Singapore", "newspaper"),
    "levant": ("Levant Report (demo)", "Jordan", "broadcaster"),
    "relief": ("Relief Monitor (demo)", "International", "ngo"),
}

# (section, headline, countries, status, importance, top, event_day_offset,
#  [(claim, [source keys], support, note)], why, context, uncertainty)
DAY1 = [
    ("europe", "Baltic states agree shared monitoring of undersea cables", ["Estonia", "Latvia", "Lithuania"],
     "verified", 4, True, 0,
     [("Three Baltic governments signed an agreement to share monitoring data on undersea cables.", ["meridian", "northlight"], "supported", None),
      ("The arrangement takes effect in January.", ["northlight"], "supported", None)],
     "Undersea cables carry most of the region's data and power links, so shared monitoring shortens the time to spot damage.",
     "Several cables in the area were damaged over the past two years.", None),
    ("europe", "Rail strike halts cross-border freight for a second day", ["Austria", "Italy"],
     "preliminary", 2, False, 0,
     [("A rail strike stopped cross-border freight trains for a second day.", ["meridian"], "supported", None),
      ("Union and operator are due to meet tomorrow.", ["meridian"], "partial", "The cited report gives the meeting as planned, not confirmed.")],
     "The route is a main freight corridor across the Alps.", None,
     "Based on a single independent source. One statement could only be partly confirmed."),
    ("middle_east", "Ceasefire talks resume with mediators reporting narrow gaps", ["Jordan"],
     "disputed", 5, True, 0,
     [("Mediators said negotiating teams returned to talks on Sunday.", ["levant", "meridian"], "supported", None),
      ("One delegation described the remaining differences as narrow.", ["levant"], "supported", None)],
     "A deal would reopen aid routes that have been closed for weeks.", None,
     "Sources conflict on whether a draft text exists: one delegation says yes, the other denies it."),
    ("east_asia", "Typhoon forces evacuation of coastal towns", ["Japan"],
     "verified", 4, True, -1,
     [("Authorities ordered the evacuation of several coastal towns ahead of a typhoon.", ["meridian", "straits"], "supported", None),
      ("Rail and ferry services were suspended.", ["straits"], "supported", None)],
     "Early evacuation orders are the main tool for limiting casualties in typhoon season.", None, None),
    ("south_southeast_asia", "Regional bloc agrees common rules for cross-border power trading", ["Singapore", "Malaysia", "Thailand"],
     "verified", 3, False, 0,
     [("Energy ministers approved common rules for trading electricity across borders.", ["straits", "meridian"], "supported", None)],
     "Shared rules let countries with surplus hydropower or solar sell it to neighbours.", None, None),
    ("africa", "West African port reopens after dredging closure", ["Nigeria"],
     "preliminary", 3, False, -1,
     [("The port resumed full operations after a dredging closure.", ["ledger"], "supported", None)],
     "The port handles a large share of the region's container traffic.", None,
     "Based on a single independent source."),
    ("africa", "Regional court rules on disputed border region", ["Kenya", "Somalia"],
     "verified", 4, True, 0,
     [("A regional court issued a ruling on a disputed border area.", ["ledger", "meridian"], "supported", None),
      ("Both governments said they would study the judgment.", ["meridian"], "supported", None)],
     "The ruling affects fishing rights and offshore exploration licences.", "The dispute has been before courts for a decade.", None),
    ("latin_america", "Andean drought prompts hydropower rationing", ["Peru", "Ecuador"],
     "verified", 3, False, 0,
     [("Two Andean countries announced scheduled power cuts as reservoirs fell.", ["andes", "meridian"], "supported", None)],
     "Both countries rely on hydropower for most of their electricity.", None, None),
    ("science", "Deep-sea survey catalogues previously unrecorded species", [],
     "preliminary", 2, False, -3,
     [("A research expedition reported dozens of species not previously recorded.", ["northlight"], "supported", None)],
     "Baseline surveys shape decisions on seabed mining permits.", None,
     "Based on a single independent source. The findings have not been peer reviewed."),
    ("energy", "Grid operators test first long-distance hydrogen pipeline segment", ["Norway", "Germany"],
     "verified", 3, False, 0,
     [("Operators began pressure tests on a hydrogen pipeline segment.", ["northlight", "meridian"], "supported", None)],
     "It is a test of whether existing gas corridors can be converted.", None, None),
    ("economics", "Central banks coordinate currency swap lines", [],
     "verified", 3, False, 0,
     [("Several central banks announced expanded currency swap lines.", ["meridian", "straits"], "supported", None)],
     "Swap lines reduce the risk of dollar shortages in smaller economies.", None, None),
    ("humanitarian", "Aid agencies warn of funding gap for flood response", ["Bangladesh"],
     "preliminary", 4, False, 0,
     [("Aid agencies said the flood response appeal is less than half funded.", ["relief"], "supported", None)],
     "Funding shortfalls decide how many people receive shelter before winter.", None,
     "Based on a single independent source, which is itself party to the appeal."),
]

DAY2 = [
    ("europe", "Alpine tunnel reopens after safety upgrade", ["Switzerland"], "verified", 2, False, 0,
     [("A major Alpine road tunnel reopened after a safety upgrade.", ["meridian", "northlight"], "supported", None)],
     "The closure had diverted freight onto longer routes.", None, None),
    ("east_asia", "Regional summit ends without joint statement", ["South Korea"], "verified", 4, True, 0,
     [("A regional summit closed without a joint statement.", ["straits", "meridian"], "supported", None)],
     "A missing statement usually signals disagreement on security language.", None, None),
    ("africa", "Vaccination campaign reaches remote districts", ["Ethiopia"], "preliminary", 3, True, -2,
     [("Health officials said a vaccination campaign reached remote districts.", ["ledger"], "supported", None)],
     "Coverage in remote areas determines whether outbreaks can be contained.", None,
     "Based on a single independent source."),
    ("latin_america", "Port workers and government reach pay settlement", ["Chile"], "verified", 3, False, 0,
     [("Port unions and the government announced a pay settlement.", ["andes", "meridian"], "supported", None)],
     "The dispute had slowed copper exports.", None, None),
    ("technology", "Regulators publish shared rules for satellite debris", [], "verified", 3, False, 0,
     [("Space regulators published shared guidelines on satellite debris.", ["meridian", "northlight"], "supported", None)],
     "Crowded orbits raise collision risk for communications satellites.", None, None),
]


def build(date: str, stories_def: list, overview: str) -> dict:
    y, m, d = (int(x) for x in date.split("-"))
    used_sources: list[str] = []
    stories = []
    for i, s in enumerate(stories_def, start=1):
        section, headline, countries, status, importance, top, offset, claims_def, why, context, uncertainty = s
        sid = f"{date}-{i:02d}"
        keys: list[str] = []
        for _, srcs, _, _ in claims_def:
            for k in srcs:
                if k not in keys:
                    keys.append(k)
        articles = []
        for j, k in enumerate(keys, start=1):
            if k not in used_sources:
                used_sources.append(k)
            articles.append({
                "id": f"{sid}-a{j}",
                "sourceId": k,
                "title": headline if j == 1 else f"{headline} ({SOURCES[k][0].split(' (')[0]})",
                "url": f"https://example.com/demo/{date}/{i:02d}/{k}",
                "publishedAt": f"{date}T{5 + j:02d}:{(i * 7) % 60:02d}:00Z",
                "role": "wire" if k == "meridian" else "original",
            })
        art_by_key = {k: a for k, a in zip(keys, articles)}
        claims = []
        for c, (text, srcs, support, note) in enumerate(claims_def, start=1):
            claims.append({
                "id": f"c{c}",
                "text": text,
                "support": support,
                "note": note,
                "evidence": [{"articleId": art_by_key[k]["id"], "quote": f"Demo passage: {text}"} for k in srcs],
            })
        times = sorted(a["publishedAt"] for a in articles)
        stories.append({
            "id": sid,
            "section": section,
            "headline": headline,
            "countries": countries,
            "eventDate": f"{y:04d}-{m:02d}-{d + offset:02d}",
            "firstReportedAt": times[0],
            "lastReportedAt": times[-1],
            "status": status,
            "importance": importance,
            "topStory": top,
            "summary": " ".join(c["text"] for c in claims),
            "claims": claims,
            "whyItMatters": why,
            "context": context,
            "uncertainty": uncertainty,
            "independentSourceCount": len(keys),
            "articles": articles,
        })
    present = {s["section"] for s in stories}
    regions = ["europe", "middle_east", "east_asia", "south_southeast_asia", "africa", "latin_america"]
    return {
        "schemaVersion": 1,
        "id": date,
        "date": date,
        "generatedAt": f"{date}T13:00:00Z",
        "title": "World Brief",
        "overview": overview,
        "isDemo": True,
        "generator": {"pipelineVersion": "demo", "model": None},
        "coverage": {
            "windowStart": f"{y:04d}-{m:02d}-{d - 1:02d}T13:00:00Z",
            "windowEnd": f"{date}T13:00:00Z",
            "articlesConsidered": sum(len(s["articles"]) for s in stories),
            "sourcesConsidered": len(used_sources),
            "sectionsWithoutCoverage": [r for r in regions if r not in present],
            "notes": ["Demonstration data. Not real news."],
        },
        "sources": [
            {"id": k, "name": SOURCES[k][0], "country": SOURCES[k][1], "type": SOURCES[k][2],
             "homepage": f"https://example.com/demo/source/{k}"}
            for k in used_sources
        ],
        "stories": stories,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ANDROID_ASSETS.mkdir(parents=True, exist_ok=True)
    briefings = [
        build("2026-11-23", DAY1, "Demonstration edition: twelve sample developments across six regions and five topics."),
        build("2026-11-22", DAY2, "Demonstration edition: five sample developments."),
    ]
    for b in briefings:
        path = OUT / f"briefing-{b['id']}.json"
        path.write_text(json.dumps(b, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        shutil.copyfile(path, ANDROID_ASSETS / path.name)
        print("wrote", path.relative_to(ROOT), len(b["stories"]), "stories")


if __name__ == "__main__":
    main()
