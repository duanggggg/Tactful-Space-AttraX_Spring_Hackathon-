from pathlib import Path
import sys

from huggingface_hub import snapshot_download

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts._data_common import download_file, extract_archive, log, raw_dataset_dir, update_manifest


DATASET_NAME = "edgewisepersona"
HF_SOURCE_URL = "https://huggingface.co/datasets/TCLResearchEurope/EdgeWisePersona"
GITHUB_SOURCE_URL = "https://github.com/TCLResearchEurope/EdgeWisePersona/archive/refs/heads/main.zip"


if __name__ == "__main__":
    raw_dir = raw_dataset_dir("edgewisepersona")
    try:
        local_path = snapshot_download(
            repo_id="TCLResearchEurope/EdgeWisePersona",
            repo_type="dataset",
            local_dir=str(raw_dir / "hf"),
            local_dir_use_symlinks=False,
        )
        update_manifest(
            dataset_name=DATASET_NAME,
            source_url=HF_SOURCE_URL,
            local_path=str(local_path),
            license_if_known="Unknown",
            download_method="huggingface_snapshot",
            status="success",
            notes="Downloaded Hugging Face dataset snapshot.",
        )
        log(f"Downloaded {DATASET_NAME} from Hugging Face to {local_path}")
    except Exception as exc:
        archive_path = raw_dir / "edgewisepersona_main.zip"
        extract_dir = raw_dir / "repo"
        try:
            download_file(GITHUB_SOURCE_URL, archive_path)
            extract_archive(archive_path, extract_dir)
            update_manifest(
                dataset_name=DATASET_NAME,
                source_url=GITHUB_SOURCE_URL,
                local_path=str(extract_dir),
                license_if_known="Unknown",
                download_method="github_zip",
                status="success",
                notes=f"Hugging Face snapshot failed; GitHub fallback succeeded. HF error: {exc}",
            )
            log(f"Downloaded {DATASET_NAME} fallback repo to {extract_dir}")
        except Exception as fallback_exc:
            update_manifest(
                dataset_name=DATASET_NAME,
                source_url=HF_SOURCE_URL,
                local_path=str(raw_dir),
                license_if_known="Unknown",
                download_method="huggingface_snapshot_or_github_zip",
                status="failed",
                notes=f"HF error: {exc}; GitHub fallback error: {fallback_exc}",
            )
            raise

