"""Deterministic geography: which countries a set of reports is about, and
which briefing section that puts them in.

The first real run showed the model cannot be trusted with this: it filed
Gaza and Indonesia under "other regions". Place names are a lookup problem,
so they are looked up.

Matching is on whole words, case-sensitive, so "Turkey" matches and "turkey"
does not. Ambiguous names are left out on purpose (Georgia, Jordan as a first
name is accepted as the country because that is by far the commoner use in
world news). People are not in the table: a story is placed by where it
happens and whom it concerns, read from place names and nationalities.
"""
from __future__ import annotations

import re
from collections import Counter

# section -> "Country: alias, alias, ..." (the country name itself is always an alias)
_TABLE = {
    "europe": """
        European Union: EU, Brussels, European Commission, European Parliament, Eurozone
        United Kingdom: UK, Britain, British, England, Scotland, Wales, Northern Ireland, London, Westminster, Downing Street, Scottish, Welsh
        Ireland: Irish, Dublin
        France: French, Paris, Macron, Élysée
        Germany: German, Berlin, Bundestag
        Italy: Italian, Rome
        Spain: Spanish, Madrid, Catalonia, Catalan
        Portugal: Portuguese, Lisbon
        Netherlands: Dutch, Amsterdam, The Hague
        Belgium: Belgian
        Luxembourg
        Switzerland: Swiss, Geneva, Zurich
        Austria: Austrian, Vienna
        Poland: Polish, Warsaw
        Czech Republic: Czechia, Czech, Prague
        Slovakia: Slovak, Bratislava
        Hungary: Hungarian, Budapest
        Romania: Romanian, Bucharest
        Bulgaria: Bulgarian, Sofia
        Greece: Greek, Athens
        Cyprus: Cypriot, Nicosia
        Malta: Maltese
        Serbia: Serbian, Belgrade
        Croatia: Croatian, Zagreb
        Bosnia and Herzegovina: Bosnia, Bosnian, Sarajevo
        Kosovo: Kosovan, Pristina
        Montenegro: Montenegrin
        North Macedonia: Macedonian, Skopje
        Albania: Albanian, Tirana
        Slovenia: Slovenian, Ljubljana
        Sweden: Swedish, Stockholm
        Norway: Norwegian, Oslo
        Denmark: Danish, Copenhagen, Greenland
        Finland: Finnish, Helsinki
        Iceland: Icelandic, Reykjavik
        Estonia: Estonian, Tallinn
        Latvia: Latvian, Riga
        Lithuania: Lithuanian, Vilnius
        Ukraine: Ukrainian, Ukrainians, Kyiv, Kiev, Kharkiv, Odesa, Odessa, Donbas, Donetsk, Crimea, Zaporizhzhia, Kherson, Lviv, Zelensky, Zelenskyy
        Russia: Russian, Russians, Moscow, Kremlin, St Petersburg, Putin, Siberia
        Belarus: Belarusian, Minsk
        Moldova: Moldovan, Chisinau, Transnistria
        Armenia: Armenian, Yerevan
        Azerbaijan: Azerbaijani, Baku, Nagorno-Karabakh
        Vatican: Holy See, Pope
    """,
    "middle_east": """
        Israel: Israeli, Israelis, Jerusalem, Tel Aviv, Netanyahu, Knesset
        Palestine: Palestinian, Palestinians, Gaza, West Bank, Hamas, Ramallah, Rafah, Khan Younis
        Lebanon: Lebanese, Beirut, Hezbollah
        Syria: Syrian, Syrians, Damascus, Aleppo, Idlib
        Iraq: Iraqi, Iraqis, Baghdad, Mosul, Basra, Erbil
        Iran: Iranian, Iranians, Tehran
        Saudi Arabia: Saudi, Saudis, Riyadh, Jeddah
        Yemen: Yemeni, Yemenis, Sanaa, Houthi, Houthis, Aden
        Oman: Omani, Muscat
        United Arab Emirates: UAE, Emirati, Dubai, Abu Dhabi
        Qatar: Qatari, Doha
        Bahrain: Bahraini, Manama
        Kuwait: Kuwaiti
        Jordan: Jordanian, Amman
        Egypt: Egyptian, Egyptians, Cairo, Sinai, Suez
        Turkey: Türkiye, Turkish, Ankara, Istanbul, Antalya, Erdogan, Erdoğan
        Kurdistan: Kurdish, Kurds
    """,
    "east_asia": """
        China: Chinese, Beijing, Shanghai, Xinjiang, Tibet, Tibetan, Xi Jinping, Shenzhen
        Hong Kong
        Taiwan: Taiwanese, Taipei
        Japan: Japanese, Tokyo, Osaka, Okinawa
        South Korea: South Korean, Seoul
        North Korea: North Korean, Pyongyang
        Mongolia: Mongolian, Ulaanbaatar
    """,
    "south_southeast_asia": """
        India: Indian, Indians, New Delhi, Delhi, Mumbai, Kashmir, Modi, Bengaluru, Kolkata
        Pakistan: Pakistani, Islamabad, Karachi, Lahore
        Bangladesh: Bangladeshi, Dhaka
        Sri Lanka: Sri Lankan, Colombo
        Nepal: Nepali, Nepalese, Kathmandu
        Bhutan: Bhutanese
        Maldives: Maldivian
        Afghanistan: Afghan, Afghans, Kabul, Taliban
        Indonesia: Indonesian, Jakarta, Java, Sumatra, Bali, Banten
        Malaysia: Malaysian, Kuala Lumpur
        Singapore: Singaporean
        Thailand: Thai, Bangkok
        Vietnam: Vietnamese, Hanoi, Ho Chi Minh City
        Philippines: Philippine, Filipino, Filipinos, Manila
        Myanmar: Burma, Burmese, Yangon, Naypyidaw, Rohingya
        Cambodia: Cambodian, Phnom Penh
        Laos: Laotian, Vientiane
        Brunei
        Timor-Leste: East Timor
        ASEAN
    """,
    "africa": """
        Nigeria: Nigerian, Nigerians, Abuja, Lagos
        Ghana: Ghanaian, Accra
        Senegal: Senegalese, Dakar
        Mali: Malian, Bamako
        Burkina Faso: Burkinabe, Ouagadougou
        Niger: Nigerien, Niamey
        Chad: Chadian, N'Djamena
        Sudan: Sudanese, Khartoum, Darfur, El Fasher
        South Sudan: South Sudanese, Juba
        Ethiopia: Ethiopian, Addis Ababa, Tigray
        Eritrea: Eritrean, Asmara
        Somalia: Somali, Mogadishu, Somaliland
        Kenya: Kenyan, Kenyans, Nairobi
        Uganda: Ugandan, Kampala
        Tanzania: Tanzanian, Dar es Salaam, Zanzibar
        Rwanda: Rwandan, Kigali
        Burundi: Burundian
        Democratic Republic of Congo: DR Congo, DRC, Democratic Republic of the Congo, Congolese, Kinshasa, Goma
        Republic of Congo: Congo-Brazzaville, Brazzaville
        Cameroon: Cameroonian, Yaoundé
        Central African Republic: Bangui
        Gabon: Gabonese
        Angola: Angolan, Luanda
        Zambia: Zambian, Lusaka
        Zimbabwe: Zimbabwean, Harare
        Mozambique: Mozambican, Maputo
        Malawi: Malawian
        Botswana
        Namibia: Namibian
        South Africa: South African, Johannesburg, Pretoria, Cape Town
        Lesotho
        Eswatini
        Madagascar: Malagasy
        Ivory Coast: Côte d'Ivoire, Ivorian, Abidjan
        Guinea: Guinean, Conakry
        Sierra Leone: Freetown
        Liberia: Liberian, Monrovia
        Togo: Togolese
        Benin: Beninese
        Gambia: Gambian
        Mauritania: Mauritanian
        Libya: Libyan, Tripoli, Benghazi
        Tunisia: Tunisian, Tunis
        Algeria: Algerian, Algiers
        Morocco: Moroccan, Rabat, Casablanca, Western Sahara
        African Union: Sahel, ECOWAS
    """,
    "latin_america": """
        Mexico: Mexican, Mexicans, Mexico City
        Guatemala: Guatemalan
        Honduras: Honduran
        El Salvador: Salvadoran
        Nicaragua: Nicaraguan, Managua
        Costa Rica: Costa Rican
        Panama: Panamanian
        Cuba: Cuban, Havana
        Haiti: Haitian, Port-au-Prince
        Dominican Republic: Dominican
        Jamaica: Jamaican
        Puerto Rico: Puerto Rican
        Trinidad and Tobago
        Colombia: Colombian, Bogotá, Bogota
        Venezuela: Venezuelan, Caracas, Maduro
        Ecuador: Ecuadorian, Quito
        Peru: Peruvian, Lima
        Bolivia: Bolivian, La Paz
        Brazil: Brazilian, Brazilians, Brasília, Brasilia, São Paulo, Sao Paulo, Rio de Janeiro, Bolsonaro, Lula
        Paraguay: Paraguayan
        Uruguay: Uruguayan, Montevideo
        Argentina: Argentine, Argentinian, Buenos Aires, Milei
        Chile: Chilean, Santiago
        Guyana: Guyanese
        Suriname
    """,
    "other_regions": """
        United States: US, U.S., USA, American, Americans, Washington, White House, Pentagon, Congress, Trump, New York, California, Texas, Florida, Iowa, Los Angeles, Seattle, Chicago, ICE
        Canada: Canadian, Canadians, Ottawa, Toronto, Quebec
        Australia: Australian, Australians, Canberra, Sydney, Melbourne, NSW, Queensland, Albanese
        New Zealand: New Zealander, Wellington, Auckland
        Papua New Guinea: Port Moresby
        Fiji: Fijian
        Solomon Islands
        Vanuatu
        Samoa
        Tonga
        Kazakhstan: Kazakh, Astana, Almaty
        Uzbekistan: Uzbek, Tashkent
        Kyrgyzstan: Kyrgyz, Bishkek
        Tajikistan: Tajik, Dushanbe
        Turkmenistan: Turkmen
        Antarctica: Antarctic
        Arctic
    """,
}

COUNTRY_SECTION: dict[str, str] = {}
ALIASES: dict[str, str] = {}              # alias -> country
COUNTRY_ALIASES: dict[str, list[str]] = {}

for _section, _block in _TABLE.items():
    for _line in _block.strip().splitlines():
        _country, _, _rest = _line.strip().partition(":")
        _country = _country.strip()
        _names = [_country] + [a.strip() for a in _rest.split(",") if a.strip()]
        COUNTRY_SECTION[_country] = _section
        COUNTRY_ALIASES[_country] = _names
        for _name in _names:
            ALIASES.setdefault(_name, _country)

# Longest aliases first so "South Korea" wins over "Korea"-like fragments and "New Zealand" over "Zealand".
_PATTERN = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(a) for a in sorted(ALIASES, key=len, reverse=True)) + r")(?:['’]s)?(?![\w-])"
)

TITLE_WEIGHT = 3


def countries_in(text: str) -> Counter:
    """Country -> number of mentions (any alias)."""
    return Counter(ALIASES[m.group(1)] for m in _PATTERN.finditer(text or ""))


def locate_event(articles: list[dict]) -> dict:
    """Where a group of reports is set.

    Returns {'countries': [most-mentioned first], 'section': region or None,
             'scores': {country: score}, 'us_only': bool}.
    Headline mentions count three times a body mention. The section is the
    region with the highest total. "Other regions" (which holds the United
    States) yields to another region that has at least half its score, because
    the US is so often an actor in a story set elsewhere.
    """
    scores: Counter = Counter()
    for a in articles:
        for country, n in countries_in(a.get("title", "")).items():
            scores[country] += n * TITLE_WEIGHT
        for country, n in countries_in(a.get("text", "")).items():
            scores[country] += n
    if not scores:
        return {"countries": [], "section": None, "scores": {}, "us_only": False}
    by_section: Counter = Counter()
    for country, score in scores.items():
        by_section[COUNTRY_SECTION[country]] += score
    ranked = by_section.most_common()
    section = ranked[0][0]
    if section == "other_regions" and len(ranked) > 1 and ranked[1][1] * 2 >= ranked[0][1]:
        section = ranked[1][0]
    ordered = [c for c, _ in scores.most_common()]
    in_section = [c for c in ordered if COUNTRY_SECTION[c] == section]
    countries = (in_section + [c for c in ordered if c not in in_section])[:4]
    return {"countries": countries, "section": section, "scores": dict(scores),
            "us_only": set(scores) == {"United States"}}


def same_place_names(text: str) -> set[str]:
    """Lower-case words of every alias of every country the text mentions.
    Used so "Democratic Republic of Congo" is not treated as a new name when
    the source says "DR Congo"."""
    words: set[str] = set()
    for country in countries_in(text):
        for alias in COUNTRY_ALIASES[country]:
            words.update(w.lower() for w in re.findall(r"[A-Za-z]+", alias))
    return words


# ---------------------------------------------------------------- topics

# Ordinary words are matched in any case; acronyms only in capitals ("COP", not "cop").
_TOPIC_WORDS = {
    "science": r"scientists?|researchers?|study finds|discover(?:y|ed|s)|telescope|space(?:craft)?|asteroid|genome|"
               r"species|fossils?\b(?! fuel)|physic(?:s|ists)|mathematic(?:s|ians?)|math|vaccine trial|archaeolog\w+",
    "technology": r"artificial intelligence|superintelligence|chips?|semiconductors?|cyber\w*|software|hack(?:ed|ers?)?|"
                  r"data breach|robots?|quantum|tech (?:giants?|firms?|stocks?)|social media|smartphones?|algorithm\w*|datacent(?:er|re)s?",
    "energy": r"oil|gas|pipelines?|nuclear (?:plant|power|reactor)s?|power grid|energy grid|electricity|blackouts?|"
              r"renewables?|solar|wind farms?|coal|energy|climate (?:talks|summit|deal|conference)|emissions|fossil fuels?",
    "economics": r"tariffs?|trade (?:deal|war|talks|pact)|inflation|central bank|interest rates?|recession|"
                 r"debt|currency|stock markets?|markets|budget|economy|economic|exports?|imports?|bailout|shares",
    "humanitarian": r"famine|refugees?|displaced|displacement|humanitarian|aid (?:convoy|agenc\w+|workers?|deliver\w+)|"
                    r"cholera|outbreak|hunger|malnutrition|starvation|drought|widow(?:s|ed)?",
}
_TOPIC_ACRONYMS = {
    "science": r"NASA|ESA|CERN",
    "technology": r"AI",
    "energy": r"OPEC\+?|LNG|COP\d*|IAEA",
    "economics": r"IMF|GDP|WTO|World Bank",
    "humanitarian": r"UNHCR|WFP|UNICEF|UNRWA|OCHA",
}
_EDGE = (r"(?<![\w-])(?:", r")(?![\w-])")
TOPIC_PATTERNS = {
    topic: (re.compile(_EDGE[0] + _TOPIC_WORDS[topic] + _EDGE[1], re.I),
            re.compile(_EDGE[0] + _TOPIC_ACRONYMS[topic] + _EDGE[1]))
    for topic in _TOPIC_WORDS
}


def topic_support(articles: list[dict]) -> dict[str, int]:
    """Topic -> number of headlines that use that topic's vocabulary."""
    return {topic: sum(1 for a in articles
                       if words.search(a.get("title", "")) or acronyms.search(a.get("title", "")))
            for topic, (words, acronyms) in TOPIC_PATTERNS.items()}


def decide_section(articles: list[dict], model_section: str | None) -> tuple[str, str]:
    """Returns (section, how it was decided).

    The model may only choose between "file under its region" and "file under
    a topic". Which region is looked up from place names. A topic the model
    proposes is accepted only if the headlines use that topic's vocabulary.
    """
    place = locate_event(articles)
    region = place["section"]
    topics = topic_support(articles)
    if model_section in topics:
        if topics[model_section] > 0:
            return model_section, "topic proposed by the model and supported by headline wording"
        if region:
            return region, f"model proposed '{model_section}' without support in the headlines; placed by geography"
    if region:
        # A development that most headlines describe in one topic's terms and that spans
        # regions (a climate summit, a trade deal between continents) belongs to the topic.
        spanned = {COUNTRY_SECTION[c] for c in place["scores"]}
        best_topic = max(topics, key=topics.get)
        if len(spanned) >= 2 and topics[best_topic] * 2 >= len(articles) and topics[best_topic] > 0:
            return best_topic, "spans regions and the headlines describe it as this topic"
        if model_section and model_section != region:
            return region, f"placed by geography (the model said '{model_section}')"
        return region, "placed by geography"
    best_topic = max(topics, key=topics.get)
    if topics[best_topic] > 0:
        return best_topic, "no place named; placed by headline wording"
    return "other_regions", "no place or topic could be determined"
