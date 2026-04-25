from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.datahub.io import ensure_data_layout
from scripts._data_common import log, write_metadata_defaults


if __name__ == "__main__":
    ensure_data_layout()
    write_metadata_defaults()
    log("Initialized data warehouse directories and metadata defaults.")

