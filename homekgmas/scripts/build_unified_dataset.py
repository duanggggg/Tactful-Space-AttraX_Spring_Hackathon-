"""Entry-point script for building the smart-home warehouse and final episodes dataset."""

from pathlib import Path
import argparse
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

print("[warehouse-entry] importing warehouse modules...", flush=True)
from app.datahub.io import DATA_PROCESSED_DIR, DATA_RAW_DIR, DATA_STAGING_DIR, ensure_data_layout
from app.datahub.warehouse_builder import build_warehouse
from scripts._data_common import log, write_metadata_defaults
print("[warehouse-entry] imports ready", flush=True)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for warehouse generation."""

    parser = argparse.ArgumentParser(description="Build staging, canonical, and episode datasets for smart-home training.")
    parser.add_argument("--raw-root", default=str(DATA_RAW_DIR), help="Raw data root.")
    parser.add_argument("--staging-root", default=str(DATA_STAGING_DIR), help="Staging parquet output root.")
    parser.add_argument("--processed-root", default=str(DATA_PROCESSED_DIR), help="Processed parquet output root.")
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable tqdm progress bars and fall back to plain warehouse logs.",
    )
    parser.add_argument(
        "--start-from",
        default="manifest",
        choices=["manifest", "home_assistant", "smartsense", "casas", "edgewisepersona", "zh_commands", "canonical", "reports"],
        help="Resume from this warehouse stage. Earlier stages are loaded from checkpoints when available.",
    )
    parser.add_argument(
        "--stop-after",
        default=None,
        choices=["manifest", "home_assistant", "smartsense", "casas", "edgewisepersona", "zh_commands", "canonical", "reports"],
        help="Stop after completing this stage and writing checkpoints.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    ensure_data_layout()
    write_metadata_defaults()
    print(
        "[warehouse-entry] "
        f"raw_root={args.raw_root} "
        f"staging_root={args.staging_root} "
        f"processed_root={args.processed_root} "
        f"start_from={args.start_from} "
        f"stop_after={args.stop_after} "
        f"show_progress={not args.no_progress}",
        flush=True,
    )
    log("Starting warehouse build entrypoint.")
    bundle = build_warehouse(
        raw_root=Path(args.raw_root),
        staging_root=Path(args.staging_root),
        processed_root=Path(args.processed_root),
        show_progress=not args.no_progress,
        start_from=args.start_from,
        stop_after=args.stop_after,
    )
    log(
        "Warehouse build complete: "
        f"staging_tables={len(bundle.staging)}, "
        f"canonical_tables={len(bundle.canonical)}, "
        f"bridge_tables={len(bundle.bridges)}, "
        f"episodes={len(bundle.episodes)}"
    )
