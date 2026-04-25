from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts._data_common import log, raw_dataset_dir, update_manifest, write_manual_instructions


if __name__ == "__main__":
    raw_dir = raw_dataset_dir("fluent")
    write_manual_instructions(
        "Fluent Speech Commands",
        [
            "Visit https://fluent.ai/fluent-speech-commands-a-dataset-for-spoken-language-understanding-research/",
            "Follow the dataset access instructions and place the extracted files under data_raw/fluent/",
            "Re-run scripts/process_fluent.py after the text metadata is available.",
        ],
    )
    update_manifest(
        dataset_name="fluent_speech_commands",
        source_url="https://fluent.ai/fluent-speech-commands-a-dataset-for-spoken-language-understanding-research/",
        local_path=str(raw_dir),
        license_if_known="Unknown",
        download_method="manual",
        status="manual",
        notes="Manual download is required.",
    )
    log("Recorded manual instructions for Fluent Speech Commands.")

