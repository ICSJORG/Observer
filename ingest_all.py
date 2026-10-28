"""Run all connectors; one failing source never stops the others.

  python ingest_all.py                     # RSS feeds (feeds.txt) + files in data/imports/
  python ingest_all.py --only CPJ          # just CPJ (its feed and its dataset CSV)
  python ingest_all.py --refetch           # ignore ETag/Last-Modified cache
  python ingest_all.py --acled --since 2020-01-01
"""
import argparse
import logging
from collections import defaultdict

import db
from ingest import acled, csv_import, rss

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingest")


def run(label, fn):
    try:
        n = db.insert_records(fn())
        log.info("%-12s +%d new records", label, n)
    except Exception as exc:
        log.error("%-12s FAILED: %s", label, exc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="Only this source label (CPJ, RSF, UNESCO, MMF, ...)")
    ap.add_argument("--acled", action="store_true", help="Also pull ACLED (needs credentials)")
    ap.add_argument("--since", default="2018-01-01", help="ACLED start date")
    ap.add_argument("--refetch", action="store_true", help="Ignore cached ETag/Last-Modified for feeds")
    a = ap.parse_args()
    want = lambda s: not a.only or a.only.upper() == s.upper()

    by_source = defaultdict(list)
    for fd in rss.load_feeds():
        by_source[fd.source].append(fd)
    for source, feeds in by_source.items():
        if want(source):
            run(f"{source} RSS", lambda f=feeds: rss.fetch(f, refetch=a.refetch))

    try:
        for source, recs in csv_import.fetch_all():
            if want(source):
                run(f"{source} file", lambda r=recs: r)
    except Exception as exc:
        log.error("file import FAILED: %s", exc)
    if a.acled and want("ACLED"):
        run("ACLED", lambda: acled.fetch(since=a.since))


if __name__ == "__main__":
    main()
