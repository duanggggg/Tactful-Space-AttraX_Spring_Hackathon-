from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts._data_common import download_file, extract_archive, log, raw_dataset_dir, update_manifest


DATASET_NAME = "home_assistant_datasets"
SOURCE_URL = "https://github.com/allenporter/home-assistant-datasets/archive/refs/heads/main.zip"


if __name__ == "__main__":
    raw_dir = raw_dataset_dir("home_assistant")
    archive_path = raw_dir / "home_assistant_datasets_main.zip"
    extract_dir = raw_dir / "repo"
    try:
        download_file(SOURCE_URL, archive_path)
        extract_archive(archive_path, extract_dir)
        update_manifest(
            dataset_name=DATASET_NAME,
            source_url=SOURCE_URL,
            local_path=str(extract_dir),
            license_if_known="Apache-2.0",
            download_method="github_zip",
            status="success",
            notes="Downloaded GitHub archive and extracted repo snapshot.",
        )
        log(f"Downloaded {DATASET_NAME} to {extract_dir}")
    except Exception as exc:
        update_manifest(
            dataset_name=DATASET_NAME,
            source_url=SOURCE_URL,
            local_path=str(raw_dir),
            license_if_known="Apache-2.0",
            download_method="github_zip",
            status="failed",
            notes=str(exc),
        )
        raise

