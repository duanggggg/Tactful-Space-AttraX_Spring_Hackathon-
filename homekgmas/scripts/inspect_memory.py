from pathlib import Path
import sys
import json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import build_settings
from app.memory.triple_store import TripleStore


if __name__ == "__main__":
    settings = build_settings()
    store = TripleStore(settings.memory_dir)
    records = [record.model_dump(mode="json") for record in store.recent_records(limit=10)]
    print(json.dumps(records, indent=2))
