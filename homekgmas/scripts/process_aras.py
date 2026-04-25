from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.datahub.io import dataframe_to_parquet
from app.datahub.schemas import build_state_t
from scripts._data_common import discover_structured_files, log, processed_dataset_dir, raw_dataset_dir, read_any_table


if __name__ == "__main__":
    raw_dir = raw_dataset_dir("aras")
    processed_dir = processed_dataset_dir("aras")
    rows: list[dict[str, object]] = []
    for file_path in [path for path in discover_structured_files(raw_dir) if path.suffix.lower() in {".csv", ".txt", ".parquet"}]:
        try:
            df = read_any_table(file_path) if file_path.suffix.lower() != ".txt" else pd.read_csv(file_path, sep=r"\s+", engine="python")
        except Exception as exc:
            log(f"Skipping unreadable ARAS file {file_path}: {exc}")
            continue
        for row in df.to_dict(orient="records"):
            rows.append(
                build_state_t(
                    home_id=str(row.get("home_id") or row.get("house") or "aras_home"),
                    timestamp=row.get("timestamp"),
                    sensor_events=[row],
                    device_states={},
                    occupancy=row.get("occupancy"),
                    activity_hint=row.get("activity") or row.get("label"),
                    environment={},
                    source_dataset="aras",
                )
            )
    dataframe_to_parquet(pd.DataFrame(rows), processed_dir / "states.parquet")
    log(f"Processed ARAS data with {len(rows)} state rows.")

