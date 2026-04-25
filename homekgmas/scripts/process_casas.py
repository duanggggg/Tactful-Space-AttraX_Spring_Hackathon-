"""Process CASAS smart-home event streams into event and windowed parquet tables."""

import csv
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.datahub.io import dataframe_to_parquet
from scripts._data_common import log, processed_dataset_dir, raw_dataset_dir, update_manifest


DATASET_NAME = "casas_zenodo"
EVENT_SCHEMA = pa.schema(
    [
        pa.field("home_id", pa.large_string()),
        pa.field("timestamp", pa.large_string()),
        pa.field("sensor_id", pa.large_string()),
        pa.field("sensor_value", pa.large_string()),
        pa.field("sensor_type", pa.large_string()),
        pa.field("room_hint", pa.large_string()),
        pa.field("event_type", pa.large_string()),
        pa.field("activity_hint", pa.large_string()),
    ]
)
WINDOW_SCHEMA = pa.schema(
    [
        pa.field("home_id", pa.large_string()),
        pa.field("timestamp", pa.large_string()),
        pa.field("event_count", pa.int64()),
        pa.field("motion_count", pa.int64()),
        pa.field("door_count", pa.int64()),
        pa.field("top_rooms", pa.large_string()),
        pa.field("top_activity_hints", pa.large_string()),
        pa.field("occupancy", pa.bool_()),
        pa.field("activity_hint", pa.large_string()),
    ]
)


def _room_hint_from_sensor(series: pd.Series) -> pd.Series:
    """Collapse raw sensor labels into a coarse room hint."""

    normalized = (
        series.astype(str)
        .str.replace(r"([a-z])([A-Z])", r"\1_\2", regex=True)
        .str.replace(r"[^A-Za-z0-9_]+", "_", regex=True)
        .str.lower()
    )
    return normalized.str.split("_").str[0].fillna("")



def _read_casas_csv(path: Path) -> pd.DataFrame:
    """Read one CASAS CSV while tolerating variable-width activity columns."""

    rows: list[list[Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row or len(row) < 4:
                continue
            if len(row) == 4:
                row.append(None)
            elif len(row) > 5:
                row = row[:4] + [",".join(row[4:])]
            rows.append(row[:5])
    return pd.DataFrame(rows, columns=["date", "time", "sensor_id", "sensor_value", "activity_hint"])



def _build_events_df(file_path: Path) -> pd.DataFrame:
    """Normalize one raw CASAS file into the shared event schema."""

    df = _read_casas_csv(file_path)
    if df.empty:
        return pd.DataFrame(columns=EVENT_SCHEMA.names)
    df["timestamp"] = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str), errors="coerce")
    df = df.dropna(subset=["timestamp"]).copy()
    if df.empty:
        return pd.DataFrame(columns=EVENT_SCHEMA.names)
    df["home_id"] = file_path.stem
    df["sensor_id"] = df["sensor_id"].astype(str)
    df["sensor_value"] = df["sensor_value"].astype(str)
    df["sensor_type"] = df["sensor_id"].str[:1]
    df["room_hint"] = _room_hint_from_sensor(df["sensor_id"])
    df["event_type"] = df["sensor_value"].str.lower()
    df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return df[
        [
            "home_id",
            "timestamp",
            "sensor_id",
            "sensor_value",
            "sensor_type",
            "room_hint",
            "event_type",
            "activity_hint",
        ]
    ].drop_duplicates()



def _window_features(events_df: pd.DataFrame, window: str) -> pd.DataFrame:
    """Aggregate event windows into occupancy and activity summaries."""

    if events_df.empty:
        return pd.DataFrame(columns=WINDOW_SCHEMA.names)
    df = events_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    if df.empty:
        return pd.DataFrame(columns=WINDOW_SCHEMA.names)
    df["window_start"] = df["timestamp"].dt.floor(window)
    rows: list[dict[str, object]] = []
    for (home_id, window_start), group in df.groupby(["home_id", "window_start"], sort=True):
        room_counts = Counter(room for room in group["room_hint"] if isinstance(room, str) and room)
        activity_counts = Counter(
            item for item in group["activity_hint"] if isinstance(item, str) and item.strip()
        )
        rows.append(
            {
                "home_id": home_id,
                "timestamp": window_start.isoformat(),
                "event_count": int(len(group.index)),
                "motion_count": int((group["sensor_id"].astype(str).str.startswith("M")).sum()),
                "door_count": int((group["sensor_id"].astype(str).str.startswith("D")).sum()),
                "top_rooms": dict(room_counts.most_common(5)),
                "top_activity_hints": dict(activity_counts.most_common(3)),
                "occupancy": bool(len(group.index) > 0),
                "activity_hint": next(iter(activity_counts), None) or next(iter(room_counts), None),
            }
        )
    return pd.DataFrame(rows, columns=WINDOW_SCHEMA.names)



def _normalize_text_value(value: Any) -> str | None:
    """Normalize nullable string-like values before Arrow conversion."""

    if value is None or pd.isna(value):
        return None
    if isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    elif isinstance(value, list):
        value = json.dumps(value, ensure_ascii=False)
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None
    return text



def _table_from_schema(df: pd.DataFrame, schema: pa.Schema) -> pa.Table:
    """Build an Arrow table from an explicit schema instead of inferred dtypes."""

    prepared = df.copy()
    for field in schema:
        if field.name not in prepared.columns:
            prepared[field.name] = None
    prepared = prepared[schema.names]

    arrays: list[pa.Array] = []
    for field in schema:
        series = prepared[field.name]
        if pa.types.is_string(field.type) or pa.types.is_large_string(field.type):
            values = [_normalize_text_value(value) for value in series.tolist()]
            arrays.append(pa.array(values, type=field.type))
        elif pa.types.is_integer(field.type):
            values = pd.to_numeric(series, errors="coerce").fillna(0).astype("int64").tolist()
            arrays.append(pa.array(values, type=field.type))
        elif pa.types.is_boolean(field.type):
            values = series.fillna(False).astype(bool).tolist()
            arrays.append(pa.array(values, type=field.type))
        else:
            arrays.append(pa.array(series.tolist(), type=field.type))
    return pa.Table.from_arrays(arrays, schema=schema)



def _append_parquet(
    writer: pq.ParquetWriter | None,
    df: pd.DataFrame,
    path: Path,
    schema: pa.Schema,
) -> pq.ParquetWriter | None:
    """Append one dataframe chunk to a parquet writer with an explicit schema."""

    if df.empty:
        return writer
    table = _table_from_schema(df, schema)
    if writer is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        writer = pq.ParquetWriter(path, schema)
    writer.write_table(table)
    return writer



def _tmp_path(path: Path) -> Path:
    """Return the temporary output path used during CASAS export."""

    return path.with_suffix(path.suffix + ".tmp")


if __name__ == "__main__":
    raw_dir = raw_dataset_dir("casas")
    candidate_files = sorted(path for path in raw_dir.rglob("*.csv"))
    processed_dir = processed_dataset_dir("casas")

    events_path = processed_dir / "events.parquet"
    window_1_path = processed_dir / "window_features_1min.parquet"
    window_5_path = processed_dir / "window_features_5min.parquet"
    window_15_path = processed_dir / "window_features_15min.parquet"
    for path in [events_path, window_1_path, window_5_path, window_15_path]:
        tmp_path = _tmp_path(path)
        if path.exists():
            path.unlink()
        if tmp_path.exists():
            tmp_path.unlink()

    events_writer: pq.ParquetWriter | None = None
    window_1_writer: pq.ParquetWriter | None = None
    window_5_writer: pq.ParquetWriter | None = None
    window_15_writer: pq.ParquetWriter | None = None
    total_events = 0

    try:
        for index, file_path in enumerate(candidate_files, start=1):
            events_df = _build_events_df(file_path)
            total_events += int(len(events_df.index))
            events_writer = _append_parquet(events_writer, events_df, _tmp_path(events_path), EVENT_SCHEMA)
            window_1_writer = _append_parquet(
                window_1_writer,
                _window_features(events_df, "1min"),
                _tmp_path(window_1_path),
                WINDOW_SCHEMA,
            )
            window_5_writer = _append_parquet(
                window_5_writer,
                _window_features(events_df, "5min"),
                _tmp_path(window_5_path),
                WINDOW_SCHEMA,
            )
            window_15_writer = _append_parquet(
                window_15_writer,
                _window_features(events_df, "15min"),
                _tmp_path(window_15_path),
                WINDOW_SCHEMA,
            )
            if index % 10 == 0 or index == len(candidate_files):
                log(
                    f"Processed CASAS file {index}/{len(candidate_files)}: "
                    f"{file_path.name} ({len(events_df.index)} rows)"
                )
    finally:
        for writer in [events_writer, window_1_writer, window_5_writer, window_15_writer]:
            if writer is not None:
                writer.close()

    if events_writer is None:
        dataframe_to_parquet(pd.DataFrame(columns=EVENT_SCHEMA.names), events_path)
    else:
        _tmp_path(events_path).replace(events_path)
    if window_1_writer is None:
        dataframe_to_parquet(pd.DataFrame(columns=WINDOW_SCHEMA.names), window_1_path)
    else:
        _tmp_path(window_1_path).replace(window_1_path)
    if window_5_writer is None:
        dataframe_to_parquet(pd.DataFrame(columns=WINDOW_SCHEMA.names), window_5_path)
    else:
        _tmp_path(window_5_path).replace(window_5_path)
    if window_15_writer is None:
        dataframe_to_parquet(pd.DataFrame(columns=WINDOW_SCHEMA.names), window_15_path)
    else:
        _tmp_path(window_15_path).replace(window_15_path)

    update_manifest(
        dataset_name=DATASET_NAME,
        source_url="https://zenodo.org/records/15708568",
        local_path=str(raw_dir),
        license_if_known="CC-BY-4.0",
        download_method="zenodo_api",
        status="success",
        notes=f"Processed {total_events} CASAS event rows into windowed parquet exports.",
    )
    log(f"Processed CASAS dataset with {total_events} event rows.")
