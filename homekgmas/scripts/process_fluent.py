from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.datahub.io import dataframe_to_parquet
from app.datahub.schemas import build_task_t
from scripts._data_common import discover_structured_files, log, processed_dataset_dir, raw_dataset_dir, read_any_table


if __name__ == "__main__":
    raw_dir = raw_dataset_dir("fluent")
    processed_dir = processed_dataset_dir("fluent")
    commands: list[dict[str, object]] = []
    for file_path in [path for path in discover_structured_files(raw_dir) if path.suffix.lower() in {".csv", ".json", ".jsonl", ".parquet"}]:
        try:
            df = read_any_table(file_path)
        except Exception as exc:
            log(f"Skipping unreadable Fluent file {file_path}: {exc}")
            continue
        for row in df.to_dict(orient="records"):
            text = str(row.get("transcription") or row.get("text") or row.get("sentence") or "").strip()
            if not text:
                continue
            task = build_task_t(
                timestamp=row.get("timestamp"),
                task_source="voice",
                raw_text=text,
                parsed_slots={"intent": row.get("intent"), "slots": row.get("slots")},
                trigger={"type": "voice", "detail": row.get("speaker_id")},
                target_devices_hint=[],
                source_dataset="fluent",
            )
            commands.append(
                {
                    "wav_path": row.get("path") or row.get("wav_path"),
                    "transcription": text,
                    "task": task,
                }
            )
    dataframe_to_parquet(pd.DataFrame(commands), processed_dir / "commands.parquet")
    log(f"Processed Fluent data with {len(commands)} command rows.")

