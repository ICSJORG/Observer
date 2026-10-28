import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import create_engine, inspect, text

import config
from classify import classify_type, country_name, detect_country

BASE_COLUMNS = {
    "id": "TEXT PRIMARY KEY", "source": "TEXT NOT NULL", "kind": "TEXT", "event_date": "TEXT",
    "year": "INTEGER", "month": "TEXT", "country": "TEXT", "iso3": "TEXT", "type": "TEXT",
    "title": "TEXT", "summary": "TEXT", "url": "TEXT", "lat": "REAL", "lon": "REAL",
    "victims": "INTEGER", "fetched_at": "TEXT",
}
EXTRA_COLUMNS = {
    "victim": "TEXT", "role": "TEXT", "organization": "TEXT", "gender": "TEXT", "media_type": "TEXT",
    "case_status": "TEXT", "perpetrator": "TEXT", "circumstance": "TEXT", "work_related": "TEXT",
    "match_key": "TEXT", "details": "TEXT",
}
ALL_COLUMNS = {**BASE_COLUMNS, **EXTRA_COLUMNS}
COLUMNS = list(ALL_COLUMNS)

_engine = None


def engine():
    global _engine
    if _engine is None:
        _engine = create_engine(config.DATABASE_URL, future=True)
        with _engine.begin() as cx:
            cx.execute(text("CREATE TABLE IF NOT EXISTS incidents (%s)" %
                            ", ".join(f"{c} {t}" for c, t in BASE_COLUMNS.items())))
            have = {c["name"] for c in inspect(cx).get_columns("incidents")}
            for col, typ in EXTRA_COLUMNS.items():
                if col not in have:
                    cx.execute(text(f"ALTER TABLE incidents ADD COLUMN {col} {typ}"))
            cx.execute(text("CREATE INDEX IF NOT EXISTS ix_inc_year ON incidents(year)"))
            cx.execute(text("CREATE INDEX IF NOT EXISTS ix_inc_country ON incidents(iso3)"))
            cx.execute(text("CREATE INDEX IF NOT EXISTS ix_inc_match ON incidents(match_key)"))
    return _engine


_GENERIC_NAMES = {"unidentified", "unknown", "unnamed", "anonymous"}


def name_key(name):
    """Order-insensitive, accent-insensitive name key used to link the same person across sources."""
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    toks = re.sub(r"[^a-z\s]", " ", s).split()
    if len(toks) < 2 or _GENERIC_NAMES & set(toks):
        return None
    return " ".join(sorted(toks))


def _num(v):
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def make_record(source, kind, event_date, title="", summary="", url="", country=None, iso3=None,
                type_text="", type_label=None, lat=None, lon=None, victims=None, source_id=None,
                detect=True, match_name=None, details=None, **extra):
    """Build a normalised record.

    kind: 'incident' (a record of an event) or 'article' (a news item).
    type_label: use a known attack type verbatim instead of keyword classification.
    detect: if no ISO code is supplied, try to find a country in the text. Structured
            sources pass detect=False so a country is never guessed.
    match_name: victim name used to build a cross-source match key (name + year).
    extra: victim, role, organization, gender, media_type, case_status, perpetrator,
           circumstance, work_related.
    """
    unknown = set(extra) - set(EXTRA_COLUMNS)
    if unknown:
        raise TypeError(f"unexpected fields: {sorted(unknown)}")
    d = pd.to_datetime(event_date, errors="coerce", utc=True)
    if pd.isna(d):
        return None
    if not iso3 and detect:
        country, iso3 = detect_country(country, title, summary)
    elif iso3 and not country:
        country = country_name(iso3)
    key = f"{source}|{source_id or url or (title + str(d.date()))}"
    nk = name_key(match_name) if match_name else None
    rec = dict.fromkeys(COLUMNS)
    rec.update({
        "id": hashlib.sha1(key.encode("utf-8")).hexdigest(),
        "source": source, "kind": kind,
        "event_date": d.strftime("%Y-%m-%d"), "year": int(d.year), "month": d.strftime("%Y-%m"),
        "country": country, "iso3": iso3,
        "type": type_label or classify_type(type_text, title, summary),
        "title": (title or "").strip()[:500], "summary": (summary or "").strip()[:3000],
        "url": url or None, "lat": _num(lat), "lon": _num(lon),
        "victims": int(v) if (v := _num(victims)) is not None else None,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "match_key": f"{nk}|{d.year}" if nk else None,
        "details": json.dumps(details, ensure_ascii=False) if details else None,
    })
    rec.update({k: (v or None) for k, v in extra.items()})
    return rec


def insert_records(records):
    """Upsert (new rows inserted, existing rows refreshed). Returns number of new rows."""
    records = [r for r in records if r]
    if not records:
        return 0
    sets = ", ".join(f"{c}=excluded.{c}" for c in COLUMNS if c != "id")
    sql = text(f"INSERT INTO incidents ({', '.join(COLUMNS)}) VALUES ({', '.join(':' + c for c in COLUMNS)}) "
               f"ON CONFLICT (id) DO UPDATE SET {sets}")
    with engine().begin() as cx:
        before = cx.execute(text("SELECT COUNT(*) FROM incidents")).scalar()
        cx.execute(sql, records)
        after = cx.execute(text("SELECT COUNT(*) FROM incidents")).scalar()
    return after - before


def load_all() -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM incidents", engine())
    if not df.empty:
        df["event_date"] = pd.to_datetime(df["event_date"])
    return df
