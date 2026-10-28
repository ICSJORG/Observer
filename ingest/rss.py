"""RSS/Atom ingestion from feeds.txt (CPJ atom feed + RSF per-country feeds).

* RSF per-country feeds: the country comes from the feed URL (reliable), not from text.
* CPJ's site-wide feed: the country is detected from the text (heuristic).
* Uses conditional GET (ETag / Last-Modified) so repeat runs only download changed feeds;
  state is kept in data/feed_state.json. Use --refetch to ignore it.
* Feeds only expose their latest items, so history builds up as you run this on a schedule.
  Feed items are articles (kind="article"), not verified incident records.
"""
import html
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import feedparser
import requests

import config
from classify import lookup_country
from db import make_record

log = logging.getLogger("rss")
STATE_FILE = config.DATA_DIR / "feed_state.json"
_TAG = re.compile(r"<[^>]+>")

# RSF groupings that are not a single country keep RSF's label and have no ISO code.
SLUG_LABELS = {
    "oecs": "OECS (Eastern Caribbean)",
    "northern-cyprus": "Northern Cyprus",
    "morocco-western-sahara": "Morocco / Western Sahara",
}


@dataclass
class Feed:
    url: str
    source: str
    country: str = None
    iso3: str = None


def load_feeds(path=None):
    feeds = []
    for line in Path(path or config.FEEDS_FILE).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        host = urlparse(line).netloc.lower().removeprefix("www.")
        source = "CPJ" if host.endswith("cpj.org") else "RSF" if host.endswith("rsf.org") else host
        country = iso3 = None
        m = re.search(r"/rss/[^/]+/([^/]+)/feed\.xml$", line) if source == "RSF" else None
        if m:
            slug = unquote(m.group(1))
            if slug in SLUG_LABELS:
                country = SLUG_LABELS[slug]
            else:
                country, iso3 = lookup_country(slug)
                country = country or slug.replace("-", " ").title()
        feeds.append(Feed(line, source, country, iso3))
    return feeds


def _load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _entry_dt(e):
    for key in ("published_parsed", "updated_parsed"):
        t = e.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def fetch(feeds, refetch=False, delay=0.5, timeout=30):
    """Fetch the given feeds politely; a failing feed is logged and skipped."""
    state = {} if refetch else _load_state()
    out, failed = [], 0
    for fd in feeds:
        headers = {"User-Agent": config.USER_AGENT,
                   "Accept": "application/atom+xml, application/rss+xml, application/xml;q=0.9, */*;q=0.8"}
        st = state.get(fd.url, {})
        if st.get("etag"):
            headers["If-None-Match"] = st["etag"]
        if st.get("modified"):
            headers["If-Modified-Since"] = st["modified"]
        try:
            r = requests.get(fd.url, headers=headers, timeout=timeout)
            if r.status_code == 304:
                continue
            r.raise_for_status()
            parsed = feedparser.parse(r.content)
            if parsed.bozo and not parsed.entries:
                raise ValueError(f"unparseable feed ({parsed.bozo_exception})")
            state[fd.url] = {"etag": r.headers.get("ETag"), "modified": r.headers.get("Last-Modified")}
            for e in parsed.entries:
                summary = " ".join(html.unescape(_TAG.sub(" ", e.get("summary", ""))).split())
                link = e.get("link", "")
                out.append(make_record(
                    source=fd.source, kind="article", event_date=_entry_dt(e),
                    title=html.unescape(e.get("title", "")), summary=summary, url=link,
                    country=fd.country, iso3=fd.iso3, detect=(fd.source != "RSF"),
                    # same article can legitimately appear in several RSF country feeds
                    source_id=f"{e.get('id') or link}#{fd.country or ''}",
                ))
        except Exception as exc:
            failed += 1
            log.warning("feed failed %s: %s", fd.url, exc)
        time.sleep(delay)
    STATE_FILE.write_text(json.dumps(state, indent=1))
    if failed:
        log.warning("%d of %d %s feeds failed", failed, len(feeds), feeds[0].source if feeds else "")
    return out
