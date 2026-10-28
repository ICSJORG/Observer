"""Importer for files in data/imports/.

* CPJ killed-journalists export and UNESCO observatory CSV are recognised by their headers
  (any file name) and handled by ingest/killed_journalists.py.
* Any other CSV/JSON (Mapping Media Freedom, Council of Europe Platform, ...) goes through the
  generic importer: name the file after the source (MMF.csv, COE.csv); column names are matched
  case-insensitively against CANDIDATES below, so extend them if your export differs.
"""
import pandas as pd

import config
from db import make_record
from ingest import killed_journalists as kj

CANDIDATES = {
    "date": ["date", "event_date", "incident_date", "date of incident", "date_of_incident", "published"],
    "year": ["year"],
    "country": ["country", "country_name", "state", "location country"],
    "iso3": ["iso3", "iso_a3", "country_code"],
    "type": ["type", "type_of_incident", "incident_type", "type of attack", "category", "type of death", "alert_type"],
    "title": ["title", "headline", "name", "journalist", "victim"],
    "summary": ["summary", "description", "details", "notes", "text"],
    "url": ["url", "link", "source_url"],
    "lat": ["lat", "latitude"],
    "lon": ["lon", "lng", "longitude"],
    "victims": ["victims", "number_of_victims", "fatalities"],
    "id": ["id", "incident_id", "case_id", "event_id"],
}


def _pick(cols_lower, key):
    for cand in CANDIDATES[key]:
        if cand in cols_lower:
            return cols_lower[cand]
    return None


def _read(path):
    if path.suffix == ".json":
        return pd.read_json(path, dtype=False).astype(object)
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def _generic(path, df):
    source = path.stem.split("__")[0].upper()
    cols = {c.lower().strip(): c for c in df.columns}
    m = {k: _pick(cols, k) for k in CANDIDATES}
    if not m["date"] and not m["year"]:
        raise ValueError(f"{path.name}: no date or year column found (columns: {list(df.columns)})")
    out = []
    for _, r in df.iterrows():
        def get(k):
            v = r[m[k]] if m[k] else None
            return None if v is None or v == "" else v
        when = get("date") or (f"{get('year')}-01-01" if get("year") else None)
        out.append(make_record(
            source=source, kind="incident", event_date=when,
            title=get("title") or "", summary=get("summary") or "", url=get("url") or "",
            country=get("country"), iso3=get("iso3"), type_text=get("type") or "",
            lat=get("lat"), lon=get("lon"), victims=get("victims"), source_id=get("id"),
        ))
    return source, out


def load_file(path):
    df = _read(path)
    if kj.is_cpj(df.columns):
        return "CPJ", kj.cpj_records(df)
    if kj.is_unesco(df.columns):
        return "UNESCO", kj.unesco_records(df)
    return _generic(path, df)


def fetch_all():
    results = []
    for path in sorted(list(config.IMPORT_DIR.glob("*.csv")) + list(config.IMPORT_DIR.glob("*.json"))):
        try:
            results.append(load_file(path))
        except Exception as exc:
            print(f"  skipped {path.name}: {exc}")
    return results
