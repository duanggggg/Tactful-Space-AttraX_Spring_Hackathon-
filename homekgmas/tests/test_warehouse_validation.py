from pathlib import Path

import pytest

from app.datahub.validation import validate_warehouse_outputs


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_validate_warehouse_outputs_reports_missing_files_for_empty_root(tmp_path):
    processed_root = tmp_path / "data_processed"
    reports_root = tmp_path / "reports"
    processed_root.mkdir(parents=True, exist_ok=True)
    reports_root.mkdir(parents=True, exist_ok=True)

    payload = validate_warehouse_outputs(
        processed_root=processed_root,
        reports_root=reports_root,
        sample_size=4,
    )

    assert payload["passed"] is False
    assert any(check["name"] == "file_exists:episodes" and not check["passed"] for check in payload["checks"])


@pytest.mark.skipif(
    not (PROJECT_ROOT / "data_processed/episodes.parquet").exists(),
    reason="Built warehouse outputs are not available in the local workspace.",
)
def test_validate_built_warehouse_outputs_passes_on_current_dataset():
    payload = validate_warehouse_outputs(
        processed_root=PROJECT_ROOT / "data_processed",
        reports_root=PROJECT_ROOT / "reports",
        sample_size=32,
    )

    assert payload["passed"] is True
    assert payload["summary"]["row_counts"]["episodes"] > 0
    assert payload["summary"]["action_service_coverage"] >= 0.95
