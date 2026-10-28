"""Central configuration. Override with environment variables."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
IMPORT_DIR = DATA_DIR / "imports"
DATA_DIR.mkdir(exist_ok=True)
IMPORT_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'incidents.db'}")

USER_AGENT = os.getenv(
    "PFM_USER_AGENT", "Observer/1.0"
)

FEEDS_FILE = BASE_DIR / "feeds.txt"

WORLD_GEOJSON_URL = (
    "https://raw.githubusercontent.com/python-visualization/folium/main/examples/data/world-countries.json"
)
