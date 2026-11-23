"""Regression tests for the errors found in the first real briefing
(2026-11-23, benchmarks/2026-11-23-first-real-run).

Each test reproduces the shape of an observed error with wording written for
the test; no publisher's text is copied here.
"""
from __future__ import annotations

from helpers import NOW, Checker, FakeLMStudio, draft, make_config, passage
from worldbrief import db
from worldbrief.cluster import cluster_articles
from worldbrief.config import Feed
from worldbrief.geo import countries_in, decide_section, locate_event
from worldbrief.ingest import article_kind
from worldbrief.lm import StandInModel
from worldbrief.pipeline import run_pipeline
from worldbrief.rank import apply_editorial_rules, describe_clusters
from worldbrief.validate import claim_nature, locate, validate_event


def art(title, text="", source="s1", url=None, published="2026-11-23T06:00:00Z", ident=None):
    ident = ident or f"{source}-{abs(hash(title)) % 10**8}"
    return {"id": ident, "source_id": source, "title": title, "text": text, "kind": "news",
            "url": url or f"https://{source}.test/news/{ident}", "published_at": published}


# ================================================================= 1. classification

def test_observed_section_errors_are_corrected_by_place_names():
    cases = [
        # (headline, what the model said, what it must be)
        ("Report finds Gaza left a toxic wasteland by Israeli bombardment", "other_regions", "middle_east"),
        ("Dozens missing after fire at Indonesian sweet factory on Java", "other_regions", "south_southeast_asia"),
        ("Row over who represents the EU at Ukraine-Russia peace talks", "energy", "europe"),
        ("Australian law expert attacks defence bill in Canberra", "europe", "other_regions"),
        ("Kenya and DR Congo agree to restore ties", "europe", "africa"),
        ("At least 15 killed in Kyiv region as Russia steps up attacks", "middle_east", "europe"),
    ]
    for headline, model_said, expected in cases:
        section, how = decide_section([art(headline)], model_said)
        assert section == expected, (headline, section, how)


def test_topic_section_needs_support_in_the_headline():
    summit = [art("COP31 climate talks in Turkey collapse"), art("The worst COP ever? Climate talks end in chaos")]
    assert decide_section(summit, "energy")[0] == "energy"            # model's topic, headlines agree
    assert decide_section(summit, "middle_east")[0] == "middle_east"  # model chose the region; that stands
    assert decide_section([art("Row over who represents the EU at Ukraine peace talks")], "energy")[0] == "europe"
    assert decide_section([art("Chip export curbs hit AI firms")], "technology")[0] == "technology"
    assert decide_section([art("Scientists discover deep-sea species")], "science")[0] == "science"
    assert decide_section([art("Something happened somewhere")], "science")[0] == "other_regions"


def test_united_states_as_actor_does_not_pull_a_story_out_of_its_region():
    assert decide_section([art("US strikes Houthi targets in Yemen")], "other_regions")[0] == "middle_east"
    assert decide_section([art("US Army to detonate explosives in Iowa")], "other_regions")[0] == "other_regions"
    assert locate_event([art("US Army to detonate explosives in Iowa")])["us_only"] is True
    assert locate_event([art("US strikes Houthi targets in Yemen")])["us_only"] is False


def test_place_matching_details():
    assert "Turkey" in countries_in("Talks hosted by Turkey")
    assert "Turkey" not in countries_in("A recipe for roast turkey")
    assert countries_in("Ukraine’s capital and Russia's border")["Ukraine"] == 1
    assert "Democratic Republic of Congo" in countries_in("Fighting in DR Congo")
    assert "United States" in countries_in("The U.S. and the US")
    assert not countries_in("Businesses and focus groups")            # no accidental 'US' inside words


def test_united_states_only_story_is_capped_and_wrong_sections_fixed_in_ranking():
    clusters = [
        [art("US Army to detonate explosives in Iowa despite court order", source="a"),
         art("US army to blow up chemicals in Iowa", source="b")],
        [art("Report finds Gaza left a toxic wasteland by Israeli bombardment", source="a")],
    ]
    descriptions = describe_clusters(clusters, {})
    ranking = {0: {"section": "other_regions", "importance": 4, "countries": ["Canada"]},
               1: {"section": "other_regions", "importance": 5, "countries": []}}
    changes = apply_editorial_rules(descriptions, ranking, clusters)
    assert ranking[0]["importance"] == 2 and ranking[0]["countries"] == ["United States"]
    assert ranking[1]["section"] == "middle_east" and ranking[1]["importance"] == 5
    assert set(ranking[1]["countries"]) == {"Palestine", "Israel"}
    assert len(changes) == 2


class WrongSections(FakeLMStudio):
    """A model that files everything under 'energy', as a stand-in for the real run's ranking errors."""

    def _handle(self, request):
        import json
        import re

        import httpx
        body = json.loads(request.content)
        if body["response_format"]["json_schema"]["name"] != "rank":
            return super()._handle(request)
        self.requests.append(body)
        ids = re.findall(r"^Event (\d+) ", body["messages"][1]["content"], re.M)
        reply = {"events": [{"cluster_id": int(i), "section": "energy", "importance": 4, "countries": ["Narnia"],
                             "reason": "x"} for i in ids]}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply)}}]})


def write_feed(tmp_path, name, items):
    body = "".join(
        f"<item><title>{t}</title><link>{u}</link><description>{d}</description>"
        f"<pubDate>Mon, 23 Nov 2026 0{6 + i % 3}:00:00 GMT</pubDate></item>" for i, (t, u, d) in enumerate(items))
    path = tmp_path / f"{name}.xml"
    path.write_text(f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{name}</title>'
                    f"<link>https://{name}.test</link><description>x</description>{body}</channel></rss>",
                    encoding="utf-8")
    return Feed(id=name, name=name.title(), url=str(path))


def test_briefing_sections_and_coverage_are_right_even_when_the_model_is_wrong(tmp_path):
    feeds = [
        write_feed(tmp_path, "one", [
            ("Report finds Gaza left a toxic wasteland", "https://one.test/world/gaza",
             "A report says bombardment left soil and water in Gaza contaminated."),
            ("Dozens missing after fire at Indonesian sweet factory", "https://one.test/world/fire",
             "A fire at a sweet factory on Java killed at least 24 people, officials said."),
        ]),
        write_feed(tmp_path, "two", [
            ("Kenya and DR Congo agree to restore ties", "https://two.test/news/ties",
             "The two leaders agreed to restore ties after months of tension."),
        ]),
    ]
    cfg = make_config(tmp_path, feeds=feeds)
    conn = db.connect(cfg.resolve(cfg.paths.database))
    briefing = run_pipeline(cfg, WrongSections().client(cfg), conn, briefing_date="2026-11-23", now=NOW)
    sections = {s["headline"][:6]: s["section"] for s in briefing["stories"]}
    assert sections == {"Report": "middle_east", "Dozens": "south_southeast_asia", "Kenya ": "africa"}
    assert all("Narnia" not in s["countries"] for s in briefing["stories"])
    missing = briefing["coverage"]["sectionsWithoutCoverage"]
    assert "middle_east" not in missing and "south_southeast_asia" not in missing and "europe" in missing


# ================================================================= 2. news vs opinion, analysis, speculation

def test_article_kinds():
    def kind(title, url):
        return article_kind({"title": title, "url": url})

    assert kind("A season of protest is a symptom of economic breakdown", "https://x.test/opinions/2026/11/23/a") == "opinion"
    assert kind("Why the far right is not retreating", "https://x.test/commentisfree/2026/nov/23/b") == "opinion"
    assert kind("Opinion: the treaty is a mistake", "https://x.test/world/c") == "opinion"
    assert kind("The Courier view on the budget: too little", "https://x.test/world/d") == "opinion"
    assert kind("What's next after the climate talks failed?", "https://x.test/news/videos/e") == "analysis"
    assert kind("Five takeaways from the failed climate talks", "https://x.test/news/articles/f") == "analysis"
    assert kind("Monday briefing: what the reset means", "https://x.test/world/2026/g") == "analysis"
    assert kind("Mothers struggle to survive amid war", "https://x.test/features/2026/h") == "analysis"
    assert kind("Minister says warship was sunk – Europe live", "https://x.test/world/live/2026/i") == "live"
    assert kind("Live: strikes kill 15 in capital region", "https://x.test/europe/j") == "live"
    assert kind("Home side lose after leading by two goals", "https://x.test/sports/2026/k") == "sport"
    assert kind("Parliament approves water treaty", "https://x.test/world/2026/l") == "news"
    assert kind("At least 15 killed as attacks intensify", "https://x.test/news/2026/m") == "news"


def test_opinion_column_is_never_a_source_of_claims(tmp_path):
    feeds = [write_feed(tmp_path, "mixed", [
        ("Protests are a symptom of economic breakdown", "https://mixed.test/opinions/2026/11/23/protests",
         "European governments beholden to corporate interests no longer care for their nations."),
        ("Why is the national bank under attack?", "https://mixed.test/news/2026/11/23/why-bank",
         "An explainer on the pressure facing the bank."),
        ("Parliament of Kenya approves water treaty", "https://mixed.test/news/2026/11/23/treaty",
         "Lawmakers in Kenya approved a water treaty by 140 votes to 60."),
    ])]
    cfg = make_config(tmp_path, feeds=feeds)
    conn = db.connect(cfg.resolve(cfg.paths.database))
    fake = FakeLMStudio()
    briefing = run_pipeline(cfg, fake.client(cfg), conn, briefing_date="2026-11-23", now=NOW)
    assert [s["headline"] for s in briefing["stories"]] == ["Parliament of Kenya approves water treaty"]
    everything_sent = " ".join(fake.prompts("rank") + fake.prompts("summarize") + fake.prompts("verify"))
    assert "beholden" not in everything_sent and "symptom of economic breakdown" not in everything_sent
    assert "under attack" not in " ".join(fake.prompts("summarize"))
    assert any("1 opinion" in n for n in briefing["coverage"]["notes"])
    run = conn.execute("SELECT stats FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    assert '"opinion": 1' in run["stats"] and '"analysis": 1' in run["stats"]


def test_a_briefing_made_only_of_commentary_fails_instead_of_publishing(tmp_path):
    feeds = [write_feed(tmp_path, "columns", [
        ("Protests are a symptom of breakdown", "https://columns.test/opinions/a", "A judgement."),
        ("Why is the bank under attack?", "https://columns.test/news/b", "An explainer."),
    ])]
    cfg = make_config(tmp_path, feeds=feeds)
    conn = db.connect(cfg.resolve(cfg.paths.database))
    assert run_pipeline(cfg, StandInModel(), conn, briefing_date="2026-11-23", now=NOW) is None
    assert "no news reports" in db.latest_run_status(conn)["reasons"][0]


def test_dropped_attribution_is_flagged():
    """Observed: 'a report finds X' and 'a sign, says the correspondent, that Y'
    were published as plain X and Y."""
    source = "The assault has contaminated soil and water across the territory, the report by two charities finds."
    plain = "The assault has contaminated soil and water across the territory."
    attributed = "A report by two charities finds the assault has contaminated soil and water across the territory."
    flagged = validate_event(draft((plain, ["A1"], source)), [passage("A1", source)], Checker())["claims"][0]
    assert flagged["support"] == "partial" and "attributes this to someone" in flagged["note"]
    kept = validate_event(draft((attributed, ["A1"], source)), [passage("A1", source)], Checker())["claims"][0]
    assert kept["support"] == "supported" and kept["nature"] == "statement"

    source2 = "The envoy is being sidelined, a sign, says the correspondent, that the bloc still lacks a common policy."
    plain2 = "The envoy is being sidelined, a sign that the bloc still lacks a common policy."
    assert validate_event(draft((plain2, ["A1"], source2)), [passage("A1", source2)], Checker())["claims"][0]["support"] == "partial"


def test_unattributed_judgement_is_flagged():
    source = "The bill is lazy and irresponsible lawmaking."
    result = validate_event(draft((source, ["A1"], source)), [passage("A1", source)], Checker())["claims"][0]
    assert result["support"] == "partial" and "judgement" in result["note"]
    quoted = "A law professor described the bill as lazy and irresponsible lawmaking."
    source2 = "The bill is lazy and irresponsible lawmaking, a law professor said."
    result = validate_event(draft((quoted, ["A1"], source2)), [passage("A1", source2)], Checker())["claims"][0]
    assert result["support"] == "supported"


def test_claim_nature():
    assert claim_nature("At least 15 people were killed in the region.") == "event"
    assert claim_nature("Officials said 15 people were killed.") == "statement"
    assert claim_nature("The army plans to detonate the chemicals next week.") == "forecast"
    assert claim_nature("The central bank could raise rates.") == "forecast"


def test_forecasts_are_called_out_in_the_story(tmp_path):
    feeds = [write_feed(tmp_path, "plan", [
        ("Army of Kenya plans to clear old munitions", "https://plan.test/news/munitions",
         "The army plans to detonate several tonnes of old munitions next week."),
    ])]
    cfg = make_config(tmp_path, feeds=feeds)
    conn = db.connect(cfg.resolve(cfg.paths.database))
    briefing = run_pipeline(cfg, FakeLMStudio().client(cfg), conn, briefing_date="2026-11-23", now=NOW)
    story = briefing["stories"][0]
    assert any(c["nature"] == "forecast" for c in story["claims"])
    assert "expected or possible" in story["uncertainty"]


# ================================================================= 3. clustering

def test_one_event_reported_differently_by_several_outlets_is_one_story():
    summit = [
        art("COP31 climate talks in Turkey collapse", "The summit in Antalya ended without agreement.", "a"),
        art("Longest-ever UN climate talks end with no deal", "COP31 ran two days over schedule in Antalya.", "b"),
        art("Climate summit fails as deal on fossil fuels is rejected", "Delegates at COP31 rejected the final text.", "c"),
    ]
    attack = [
        art("Russian warship hit by drone at Benghazi naval base", "Libyan officials reported the strike.", "a"),
        art("Russian warship sinks in Benghazi after suspected drone attack", "The vessel sank at the Libyan port.", "b"),
        art("Ukraine says it was behind attack on Russian ships off Libya", "Kyiv claimed the Benghazi strike.", "c"),
        art("Zelensky says Ukraine sank Russian warship off Libya", "The president confirmed the operation.", "d"),
    ]
    other = [
        art("South Korea education minister resigns over exam scandal", "The minister quit on Sunday.", "a"),
        art("Brazil storm displaces thousands", "A storm hit a town in the south.", "b"),
        art("Russian strike kills two in Kyiv", "A residential block was hit overnight.", "b"),
    ]
    articles = summit + attack + other
    clusters, method = cluster_articles(articles, StandInModel(), 0.78, 0.22)
    groups = [{a["id"] for a in c} for c in clusters]
    assert {a["id"] for a in summit} in groups
    assert {a["id"] for a in attack} in groups
    assert len(clusters) == 5                                   # the three unrelated reports stay separate
    assert method == "names and word overlap"


def test_different_events_in_the_same_country_are_not_merged():
    articles = [
        art("Russian strike kills two in Kyiv", "A residential block was hit overnight.", "a"),
        art("Ukraine parliament passes budget for next year", "Lawmakers in Kyiv approved the spending plan.", "b"),
        art("Ukraine wins place at football finals", "The national side qualified on Sunday.", "c"),
    ]
    clusters, _ = cluster_articles(articles, StandInModel(), 0.78, 0.22)
    assert len(clusters) == 3


def test_clustering_does_not_depend_on_article_order():
    articles = [
        art("COP31 climate talks in Turkey collapse", "The summit in Antalya ended without agreement.", "a", ident="x1"),
        art("Longest-ever UN climate talks end with no deal", "COP31 ran two days over in Antalya.", "b", ident="x2"),
        art("Brazil storm displaces thousands", "A storm hit a town in the south.", "c", ident="x3"),
        art("Climate summit fails as fossil fuel deal is rejected", "Delegates at COP31 rejected the text.", "d", ident="x4"),
    ]
    forward, _ = cluster_articles(articles, StandInModel(), 0.78, 0.22)
    backward, _ = cluster_articles(list(reversed(articles)), StandInModel(), 0.78, 0.22)
    as_sets = lambda cs: sorted(sorted(a["id"] for a in c) for c in cs)
    assert as_sets(forward) == as_sets(backward) == [["x1", "x2", "x4"], ["x3"]]


# ================================================================= 4. verification rules that misfired

def test_reordered_names_without_a_role_swap_are_no_longer_removed():
    """Observed: two true claims were removed because names appeared in a different order."""
    source = "At least 15 killed in the Kyiv region as Russia intensifies attacks."
    claim = "Russia intensified attacks on the Kyiv region."
    result = validate_event(draft((claim, ["A1"], source)), [passage("A1", source)], Checker())
    assert [c["text"] for c in result["claims"]] == [claim]

    source = "The assault by Israel has contaminated the entire strip, the report by Oxfam finds."
    claim = "Oxfam reports that the assault by Israel has contaminated the entire strip."
    result = validate_event(draft((claim, ["A1"], source)), [passage("A1", source)], Checker())
    assert [c["text"] for c in result["claims"]] == [claim]


def test_a_real_role_swap_is_still_removed():
    source = "Examplia sent troops across the border into Samplestan on Sunday."
    claim = "Samplestan sent troops across the border into Examplia on Sunday."
    result = validate_event(draft((claim, ["A1"], source)), [passage("A1", source)], Checker())
    assert result["claims"] == []


def test_another_name_for_the_same_country_is_not_a_new_name():
    source = "Kenya and DR Congo agree to restore ties after tensions over conflict."
    claim = "Kenya and the Democratic Republic of Congo agreed to restore ties."
    kept = validate_event(draft((claim, ["A1"], source)), [passage("A1", source)], Checker())["claims"][0]
    assert kept["support"] == "supported"
    # A first name and title the source never gave is still flagged.
    source = "Strikes came days after Putin promised a painful response."
    claim = "Russian President Vladimir Putin promised a painful response."
    flagged = validate_event(draft((claim, ["A1"], source)), [passage("A1", source)], Checker())["claims"][0]
    assert flagged["support"] == "partial" and "vladimir" in flagged["note"]


def test_attributed_claim_is_not_penalised_for_the_sources_claiming():
    source = ("The bill is lazy and irresponsible lawmaking, one of the country's leading scholars has warned, "
              "claiming its provisions could raise serious legal issues.")
    claim = "A leading scholar warned the bill is lazy and irresponsible lawmaking."
    kept = validate_event(draft((claim, ["A1"], source)), [passage("A1", source)], Checker())["claims"][0]
    assert kept["support"] == "supported"


def test_quote_comes_from_the_right_part_of_a_run_on_passage():
    """Observed: a standfirst run into the body with no full stop was treated as
    one sentence, so the published quote was its first 400 characters."""
    run_on = ("Findings warn of widespread contamination posing grave threats to public health for generations to come "
              "The destruction has left a devastating environmental legacy with poisoned water and contaminated soil "
              "threatening the systems that the population depends on for survival according to a report by two "
              "charities with heavy metals and explosive residues and asbestos from destroyed buildings and sewage "
              "making the air and soil and water dangerous for residents for decades to come and officials said "
              "the clean-up would take many years and cost far more than the territory can afford on its own.")
    quote = locate("Heavy metals, explosive residues and asbestos have made the air and soil dangerous.", run_on, 0.6)
    assert quote is not None and "asbestos" in quote and len(quote.split()) <= 45


# ================================================================= 5. errors seen in the second real run

def test_a_denial_worded_differently_is_not_a_dropped_negation():
    """Observed: 'failed to reach a pact' was removed because its source said 'ended without a pact'."""
    source = "The summit ended without a climate pact after two extra days of talks."
    claim = "Negotiators failed to reach a climate pact at the summit."
    result = validate_event(draft((claim, ["A1"], source)), [passage("A1", source)], Checker())
    assert [c["text"] for c in result["claims"]] == [claim]
    # A claim with no negation at all is still removed.
    claim = "Negotiators reached a climate pact at the summit."
    assert validate_event(draft((claim, ["A1"], source)), [passage("A1", source)], Checker())["claims"] == []


def test_distances_and_different_quantities_are_not_conflicting_figures():
    """Observed: '24 killed' was called in conflict with '50km west of the capital' and with '30 missing'."""
    passages = [passage("A1", "At least 24 people were killed in the factory fire."),
                passage("A2", "The fire broke out at a factory about 50km west of the capital, and about 30 people are still missing.")]
    claim = "At least 24 people were killed in the factory fire."
    kept = validate_event(draft((claim, ["A1"], claim)), passages, Checker())
    assert kept["claims"][0]["support"] == "supported" and kept["conflict"] is False
    # A real disagreement about the same quantity is still caught.
    passages.append(passage("A3", "At least three people were killed in the factory fire, officials said."))
    passages.append(passage("A4", "At least 3 people were killed in the factory fire."))
    disputed = validate_event(draft((claim, ["A1"], claim)), passages, Checker())
    assert disputed["conflict"] is True and "3" in disputed["conflict_note"]


def test_headline_attribution_such_as_experts_find_counts():
    source = "The bombardment has created a toxic wasteland, experts find."
    claim = "The bombardment has created a toxic wasteland."
    flagged = validate_event(draft((claim, ["A1"], source)), [passage("A1", source)], Checker())["claims"][0]
    assert flagged["support"] == "partial" and "attributes" in flagged["note"]


def test_global_summit_is_filed_under_its_topic_not_its_host_or_loudest_participant():
    cluster = [
        art("COP31 ends without climate pact as UN chief warns of no ambiguity in the science",
            "EU member states objected; Russia and the United States resisted.", "a"),
        art("Pacific island nations despair at summit failure", "Delegates in Antalya, Turkey, left without a deal.", "b"),
        art("Longest-ever UN climate talks end with no deal", "France and Germany blamed producers.", "c"),
        art("Fossil fuel wording sinks final text", "Australia will host next year.", "d"),
    ]
    assert decide_section(cluster, "europe")[0] == "energy"
