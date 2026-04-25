from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts._data_common import log, raw_dataset_dir, update_manifest, write_manual_instructions


if __name__ == "__main__":
    raw_dir = raw_dataset_dir("aras")
    write_manual_instructions(
        "ARAS",
        [
            "Visit https://www.cmpe.boun.edu.tr/aras/",
            "Download the ARAS data package into data_raw/aras/",
            "Re-run scripts/process_aras.py after the raw files are present.",
        ],
    )
    update_manifest(
        dataset_name="aras",
        source_url="https://www.cmpe.boun.edu.tr/aras/",
        local_path=str(raw_dir),
        license_if_known="Unknown",
        download_method="manual",
        status="manual",
        notes="Manual download is required.",
    )
    log("Recorded manual instructions for ARAS.")

