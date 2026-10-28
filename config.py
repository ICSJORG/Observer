"""Central configuration. Override with environment variables."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
IMPORT_DIR = DATA_DIR / "imports"      # drop CSV exports here (see README)
DATA_DIR.mkdir(exist_ok=True)
IMPORT_DIR.mkdir(exist_ok=True)

# SQLite by default. For PostgreSQL:
#   export DATABASE_URL="postgresql+psycopg2://user:pass@localhost:5432/pfmonitor"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'incidents.db'}")

# Please put a real contact address here: polite crawling matters.
USER_AGENT = os.getenv(
    "PFM_USER_AGENT", "PressFreedomMonitor/0.1 (academic research; contact: you@example.org)"
)

# One feed URL per line (CPJ atom feed + RSF per-country feeds). Add more freely.
# RSF country feeds take their country from the URL, so no text guessing is needed.
FEEDS_FILE = BASE_DIR / "feeds.txt"

# ACLED (OAuth; free "myACLED" account required). Never hard-code credentials.
ACLED_USERNAME = os.getenv("ACLED_USERNAME", "")
ACLED_PASSWORD = os.getenv("ACLED_PASSWORD", "")
ACLED_TOKEN_URL = "https://acleddata.com/oauth/token"
ACLED_READ_URL = "https://acleddata.com/api/acled/read"

# Country polygons for the choropleth (ISO-3 ids). Fetched once at runtime.
WORLD_GEOJSON_URL = (
    "https://raw.githubusercontent.com/python-visualization/folium/main/examples/data/world-countries.json"
)
