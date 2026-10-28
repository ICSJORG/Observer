"""Adapters for two downloadable datasets of killed journalists:

* CPJ  "Journalists and Media Workers Killed" CSV export (cpj.org/data)
* UNESCO Observatory of Killed Journalists CSV (UNESCO datahub)

Both are structured incident records (kind="incident", type="Killing"), so country and
type are taken from the data rather than guessed. Records carry a name+year match_key so
the dashboard can count a killing once when both sources list it.
"""
import ast
import json

from classify import country_name, iso2_to_iso3, lookup_country
from db import make_record

CPJ_REQUIRED = {"Name", "Date", "Country", "Type of Death", "cpj.org URL"}
UNESCO_REQUIRED = {"Title En", "Date", "Calc country code", "Enquiry status"}


def is_cpj(columns):
    return CPJ_REQUIRED <= set(columns)


def is_unesco(columns):
    return UNESCO_REQUIRED <= set(columns)


def _s(v):
    return (v or "").strip()


def _clean(d):
    return {k: v for k, v in d.items() if v not in (None, "", "[]", False)}


def _join(*parts, sep="; "):
    return sep.join(p for p in parts if p)


def cpj_records(df):
    out = []
    for r in df.to_dict("records"):
        name, status = _s(r["Name"]), _s(r.get("Status"))
        raw_country = _s(r["Country"])
        country, iso3 = lookup_country(raw_country)
        country = country or raw_country or None
        role, org = _s(r.get("Journalist or Media Worker")), _s(r.get("Organization"))
        circ, perp = _s(r.get("Type of Death")), _s(r.get("Suspected Source of Fire"))
        confirmed = _s(r.get("Confirmed as work-related")).lower() == "yes"
        suspected = _s(r.get("Suspected as work-related")).lower() == "yes"
        flags = {k: _s(r.get(col)).lower() == "yes" for k, col in
                 (("taken_captive", "Taken Captive"), ("threatened", "Threatened"), ("tortured", "Tortured"))}
        out.append(make_record(
            source="CPJ", kind="incident", event_date=r["Date"], title=name,
            summary=_join(_join(role, org, sep=", "), f"Type of death: {circ}" if circ else "",
                          f"Suspected source of fire: {perp}" if perp else ""),
            url=_s(r["cpj.org URL"]), country=country, iso3=iso3, detect=False,
            type_label="Killing" if status.lower() == "killed" else None, type_text=status,
            source_id=_s(r["cpj.org URL"]), match_name=name,
            victim=name, role=role, organization=org, case_status=_s(r.get("Impunity")),
            perpetrator=perp, circumstance=circ,
            work_related="Confirmed" if confirmed else "Suspected" if suspected else None,
            details=_clean(flags),
        ))
    return out


def _unesco_url(s):
    s = _s(s)
    if s.startswith("http"):
        return s
    try:
        d = ast.literal_eval(s)
        return d.get("url") if isinstance(d, dict) else None
    except (ValueError, SyntaxError):
        return None


def unesco_records(df):
    out = []
    for r in df.to_dict("records"):
        name = _s(r["Title En"])
        iso3 = iso2_to_iso3(r.get("Calc country code"))   # None for the few rows without a valid code
        local, media, coverage = _s(r.get("Local")), _s(r.get("Media")), _s(r.get("Area coverage"))
        conflict = _s(r.get("Conflict Zone")).lower() == "true"
        out.append(make_record(
            source="UNESCO", kind="incident", event_date=r["Date"], title=name,
            summary=_join(f"{local} journalist" if local else "", media, "Conflict zone" if conflict else "",
                          f"Coverage: {coverage.replace(';', ', ')}" if coverage else ""),
            url=_unesco_url(r.get("description_en")),
            country=country_name(iso3) if iso3 else None, iso3=iso3, detect=False,
            type_label="Killing", source_id=_s(r.get("ID")), match_name=name,
            victim=name, gender=_s(r.get("Gender")), media_type=media,
            case_status=_s(r.get("Enquiry status")),
            details=_clean({
                "unesco_id": _s(r.get("ID")), "nationality": _s(r.get("Nationality")),
                "local_or_foreign": local, "conflict_zone": conflict, "area_coverage": coverage,
                "regional_group": _s(r.get("Regional Group")), "age": _s(r.get("Age")),
                "date_resolution": _s(r.get("Date resolution")),
            }),
        ))
    return out
