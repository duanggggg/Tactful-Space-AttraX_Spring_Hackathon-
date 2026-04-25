from pathlib import Path
import sys

from huggingface_hub import snapshot_download

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts._data_common import log, raw_dataset_dir, update_manifest


DATASETS = [
    ("zh_smart_home_control", "Charles95/smart_home_control"),
    ("zh_home_assistant_requests", "jc132/Home-Assistant-Requests-Zh"),
]


if __name__ == "__main__":
    raw_dir = raw_dataset_dir("zh_commands")
    for dataset_name, repo_id in DATASETS:
        target_dir = raw_dir / dataset_name
        try:
            local_path = snapshot_download(
                repo_id=repo_id,
                repo_type="dataset",
                local_dir=str(target_dir),
                local_dir_use_symlinks=False,
            )
            update_manifest(
                dataset_name=dataset_name,
                source_url=f"https://huggingface.co/datasets/{repo_id}",
                local_path=str(local_path),
                license_if_known="Unknown",
                download_method="huggingface_snapshot",
                status="success",
                notes="Downloaded Hugging Face dataset snapshot.",
            )
            log(f"Downloaded {repo_id} to {local_path}")
        except Exception as exc:
            update_manifest(
                dataset_name=dataset_name,
                source_url=f"https://huggingface.co/datasets/{repo_id}",
                local_path=str(target_dir),
                license_if_known="Unknown",
                download_method="huggingface_snapshot",
                status="failed",
                notes=str(exc),
            )
            raise

