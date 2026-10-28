"""Heuristic classification (attack type) and country resolution.

Attack-type and free-text country detection are keyword heuristics, good for triage and
exploration. Structured sources (CPJ/UNESCO datasets, RSF per-country feeds) bypass them.
"""
import re
from functools import lru_cache

import pycountry

TYPE_RULES = [
    ("Killing", r"\b(kill(?:ed|ing|s)?|murder(?:ed|s)?|shot dead|assassinat\w+|slain|gunned down)\b"),
    ("Imprisonment / detention", r"\b(jail(?:ed|s)?|imprison\w*|detain\w*|arrest\w*|sentenc\w+|prison|in custody|abduct\w+|kidnap\w*|disappear\w*)\b"),
    ("Surveillance / digital", r"\b(spyware|pegasus|surveillance|hack(?:ed|ing)?|cyber\s?attack\w*|ddos|phishing|wiretap\w*)\b"),
    ("Physical attack", r"\b(assault\w*|beaten|beat up|attack(?:ed|s)?|injur\w+|wounded|stabb\w+|violence)\b"),
    ("Threat / harassment", r"\b(threat\w*|intimidat\w+|harass\w*|doxx\w*|stalk\w*|smear\w*|online abuse|death threat\w*)\b"),
    ("Legal harassment", r"\b(lawsuit|sue[sd]?|defamation|slapp|charged|indict\w+|libel|criminal case|fined?)\b"),
    ("Censorship / access", r"\b(censor\w*|block(?:ed|s|ing)?|banned?|shut\s?down|shutdown|suspend\w*|revok\w+|accreditation|expel\w*|deport\w*|raid\w*)\b"),
]
_COMPILED_TYPES = [(t, re.compile(p, re.I)) for t, p in TYPE_RULES]

DISPLAY_OVERRIDES = {
    "RUS": "Russia", "IRN": "Iran", "SYR": "Syria", "KOR": "South Korea", "PRK": "North Korea",
    "VEN": "Venezuela", "BOL": "Bolivia", "TZA": "Tanzania", "VNM": "Vietnam", "PSE": "Palestine",
    "GBR": "United Kingdom", "MDA": "Moldova", "TUR": "Türkiye", "LAO": "Laos", "COD": "DR Congo",
    "COG": "Republic of the Congo", "TWN": "Taiwan", "USA": "United States", "CZE": "Czechia",
    "XKX": "Kosovo", "BRN": "Brunei", "FSM": "Micronesia",
}
ALIASES = {
    "russia": "RUS", "turkey": "TUR", "türkiye": "TUR", "turkiye": "TUR", "iran": "IRN", "syria": "SYR",
    "south korea": "KOR", "north korea": "PRK", "venezuela": "VEN", "bolivia": "BOL", "tanzania": "TZA",
    "vietnam": "VNM", "palestine": "PSE", "gaza": "PSE", "west bank": "PSE", "uk": "GBR", "britain": "GBR",
    "united kingdom": "GBR", "usa": "USA", "united states": "USA", "moldova": "MDA", "laos": "LAO",
    "dr congo": "COD", "democratic republic of the congo": "COD", "democratic republic of congo": "COD",
    "democratic republic congo": "COD", "drc": "COD", "republic of congo": "COG", "congo brazzaville": "COG",
    "taiwan": "TWN", "czechia": "CZE", "czech republic": "CZE", "north macedonia": "MKD",
    "ivory coast": "CIV", "cote d'ivoire": "CIV", "côte d'ivoire": "CIV", "bosnia": "BIH",
    "bosnia herzegovina": "BIH", "east timor": "TLS", "kosovo": "XKX", "uae": "ARE",
}


def classify_type(*texts: str) -> str:
    blob = " ".join(t for t in texts if t)
    for label, rx in _COMPILED_TYPES:
        if rx.search(blob):
            return label
    return "Other"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().replace("-", " ").replace("_", " ")).strip()


@lru_cache(maxsize=1)
def _country_index():
    names = {}
    for c in pycountry.countries:
        for attr in ("name", "common_name", "official_name"):
            n = getattr(c, attr, None)
            if n:
                names[_norm(n)] = c.alpha_3
    names.update({_norm(k): v for k, v in ALIASES.items()})
    alts = sorted(names, key=len, reverse=True)
    pattern = "|".join(re.escape(n).replace(r"\ ", r"[\s-]+") for n in alts)
    return names, re.compile(rf"(?<!\w)({pattern})(?!\w)", re.I)


def country_name(iso3: str) -> str:
    if iso3 in DISPLAY_OVERRIDES:
        return DISPLAY_OVERRIDES[iso3]
    c = pycountry.countries.get(alpha_3=iso3)
    return (getattr(c, "common_name", None) or c.name) if c else iso3


def lookup_country(name: str):
    """Exact (normalised) match of a country name/alias -> (display_name, iso3), else (None, None)."""
    if not name:
        return None, None
    iso3 = _country_index()[0].get(_norm(name))
    return (country_name(iso3), iso3) if iso3 else (None, None)


def iso2_to_iso3(code: str):
    code = (code or "").strip().upper()
    if code == "XK":
        return "XKX"
    c = pycountry.countries.get(alpha_2=code) if len(code) == 2 else None
    return c.alpha_3 if c else None


def detect_country(*texts: str):
    """Earliest country mention in free text -> (display_name, iso3), or (None, None)."""
    names, rx = _country_index()
    for t in texts:
        if not t:
            continue
        m = rx.search(t)
        if m:
            iso3 = names[_norm(m.group(1))]
            return country_name(iso3), iso3
    return None, None
