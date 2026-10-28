"""ACLED connector. ACLED is conflict data, not a press-freedom dataset, so events are
filtered to those whose notes mention journalists/media workers (a heuristic; review results).

Auth: myACLED account via OAuth. Check https://acleddata.com/api-documentation if auth changes.
Respect ACLED's terms of use and attribution requirements when publishing.
"""
import re

import pycountry
import requests

import config
from db import make_record

MEDIA_RX = re.compile(r"\b(journalists?|reporters?|media (?:worker|crew|outlet|office)s?|cameraman|photojournalist|correspondent|newsroom|broadcaster)\b", re.I)


def _token():
    if not (config.ACLED_USERNAME and config.ACLED_PASSWORD):
        raise RuntimeError("Set ACLED_USERNAME and ACLED_PASSWORD environment variables.")
    r = requests.post(config.ACLED_TOKEN_URL, timeout=30, headers={"User-Agent": config.USER_AGENT},
                      data={"username": config.ACLED_USERNAME, "password": config.ACLED_PASSWORD,
                            "grant_type": "password", "client_id": "acled"})
    r.raise_for_status()
    return r.json()["access_token"]


def _iso3(numeric):
    try:
        return pycountry.countries.get(numeric=f"{int(numeric):03d}").alpha_3
    except (AttributeError, TypeError, ValueError):
        return None


def fetch(since="2018-01-01", until="2100-01-01", max_pages=50, page_size=5000):
    headers = {"Authorization": f"Bearer {_token()}", "User-Agent": config.USER_AGENT}
    out = []
    for page in range(1, max_pages + 1):
        r = requests.get(config.ACLED_READ_URL, headers=headers, timeout=120, params={
            "_format": "json", "event_date": f"{since}|{until}", "event_date_where": "BETWEEN",
            "limit": page_size, "page": page,
        })
        r.raise_for_status()
        rows = r.json().get("data", [])
        if not rows:
            break
        for e in rows:
            notes = e.get("notes", "")
            if not MEDIA_RX.search(notes):
                continue
            out.append(make_record(
                source="ACLED", kind="incident", event_date=e.get("event_date"),
                title=f"{e.get('sub_event_type') or e.get('event_type')} — {e.get('location', '')}",
                summary=notes, url="https://acleddata.com/", country=e.get("country"),
                iso3=_iso3(e.get("iso")),
                type_text=f"{e.get('event_type', '')} {e.get('sub_event_type', '')}",
                lat=e.get("latitude"), lon=e.get("longitude"), victims=e.get("fatalities"),
                source_id=e.get("event_id_cnty"),
            ))
    return out
