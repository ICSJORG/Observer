<img width="2048" height="2048" alt="logoclean" src="https://github.com/user-attachments/assets/a4e8eda6-d85a-4577-baeb-1435a7d18fa7" />

# Observer

Ingests press-freedom sources into one normalised database (SQLite or PostgreSQL) and serves a
searchable, filterable Streamlit dashboard: trends, a killed-journalists analysis tab, and a folium map.

## Run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python ingest_all.py            # feeds.txt (CPJ + RSF) and every file in data/imports/
streamlit run app.py
```
PostgreSQL: `pip install psycopg2-binary`, then `export DATABASE_URL="postgresql+psycopg2://user:pass@host/db"`.
Existing databases are migrated automatically (new columns are added on first run). Re-running is safe:
rows are upserted, so refreshed dataset exports update existing records.

## Sources
| Source | How | Result |
|---|---|---|
| CPJ site feed | `feeds.txt` (`https://cpj.org/feed/atom/`) | articles; country detected from text (heuristic) |
| RSF, 176 country feeds | `feeds.txt` | articles; **country taken from the feed URL** |
| CPJ killed journalists & media workers | `data/imports/cpj-people-list-*.csv` (recognised by its headers) | incidents: type=Killing, circumstance, suspected source of fire, impunity, role, organisation, work-related status, captive/threatened/tortured flags |
| UNESCO Observatory of Killed Journalists | `data/imports/fej001.csv` (recognised by its headers) | incidents: type=Killing, gender, media type, enquiry status, local/foreign, conflict zone, DG statement link |
| Mapping Media Freedom, Council of Europe | CSV/JSON export in `data/imports/` named `MMF.csv`, `COE.csv` | generic importer; extend `CANDIDATES` in `ingest/csv_import.py` if headers differ |
| ACLED | `python ingest_all.py --acled --since 2020-01-01` (needs `ACLED_USERNAME`/`ACLED_PASSWORD`) | events whose notes mention journalists/media workers (heuristic) |

Feed fetching uses conditional GET (state in `data/feed_state.json`; `--refetch` ignores it) and a 0.5 s
delay between requests. Feeds only expose their latest items, so run `ingest_all.py` on a schedule
(cron/launchd) to build history. To update a dataset, drop the new export into `data/imports/` and re-run.

## Data decisions you should know about
- **CPJ and UNESCO overlap** (about 960 killings appear in both, matched on normalised name + year). The
  dashboard merges them by default ("Count each killing once"); untick to see every source row. Matching is
  exact, so spelling variants and "Unidentified" victims are not merged.
- **Country labels without an ISO code** keep the source's label and are not mapped: CPJ's
  "Israel and the Occupied Palestinian Territory" (221 records) and "Yugoslavia", and RSF's OECS, Northern
  Cyprus and Morocco / Western Sahara feeds. To map CPJ's combined label, add it to `ALIASES` in `classify.py`
  (that is an editorial choice, so it is not done for you).
- **UNESCO coordinates** in the CSV are country-level points, so they are not stored as event locations.
  Four UNESCO rows have no valid country code and stay unattributed.
- Impunity (CPJ) and enquiry status (UNESCO) use different vocabularies and are shown as published.
- The same RSF article can appear in several country feeds and is stored once per country.
- Type/country for RSS text is keyword-based; spot-check before publishing. Check each source's licence
  and attribute it in publications.

## Layout
`config.py` settings · `feeds.txt` feed list · `db.py` schema, upsert, cross-source match key ·
`classify.py` type + country logic · `ingest/` (`rss.py`, `killed_journalists.py`, `csv_import.py`, `acled.py`) ·
`ingest_all.py` CLI · `app.py` dashboard.
