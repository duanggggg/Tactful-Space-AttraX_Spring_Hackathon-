from pathlib import Path
import json
import sys
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts._data_common import download_file, extract_archive, log, raw_dataset_dir, update_manifest, write_manual_instructions


DATASET_NAME = "casas_zenodo"
RECORD_URL = "https://zenodo.org/api/records/15708568"
PAGE_URL = "https://zenodo.org/records/15708568"


def resolve_download_url() -> tuple[str, str]:
    with urlopen(RECORD_URL) as response:
        payload = json.load(response)
    files = payload.get("files", [])
    preferred_names = ["labeled_data.zip", "data.zip"]
    for preferred in preferred_names:
        for file_item in files:
            if file_item.get("key") == preferred:
                return file_item["links"]["self"], preferred
    if files:
        first = files[0]
        return first["links"]["self"], first["key"]
    raise ValueError("Zenodo record did not expose any downloadable file.")


if __name__ == "__main__":
    raw_dir = raw_dataset_dir("casas")
    extract_dir = raw_dir / "zenodo"
    try:
        download_url, filename = resolve_download_url()
        archive_path = raw_dir / filename
        download_file(download_url, archive_path)
        extract_archive(archive_path, extract_dir)
        update_manifest(
            dataset_name=DATASET_NAME,
            source_url=PAGE_URL,
            local_path=str(extract_dir),
            license_if_known="CC-BY-4.0",
            download_method="zenodo_api",
            status="success",
            notes=f"Downloaded {filename} via the Zenodo API.",
        )
        log(f"Downloaded {DATASET_NAME} artifact {filename} to {extract_dir}")
    except Exception as exc:
        write_manual_instructions(
            "CASAS",
            [
                f"Visit {PAGE_URL}",
                "Download either labeled_data.zip or data.zip into data_raw/casas/",
                "Re-run scripts/process_casas.py after the archive is present.",
            ],
        )
        update_manifest(
            dataset_name=DATASET_NAME,
            source_url=PAGE_URL,
            local_path=str(raw_dir),
            license_if_known="CC-BY-4.0",
            download_method="zenodo_api_or_manual",
            status="manual",
            notes=f"Automatic download failed: {exc}",
        )
        log(f"Automatic CASAS download failed: {exc}")

