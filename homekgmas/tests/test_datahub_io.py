from pathlib import Path
import json

from app.datahub import io


def test_normalize_manifest_local_path_uses_project_relative_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(io, "PROJECT_ROOT", tmp_path)

    inside_project = tmp_path / "data_raw" / "smartsense" / "repo"

    assert io.normalize_manifest_local_path(inside_project) == "data_raw/smartsense/repo"
    assert io.normalize_manifest_local_path("data_raw/casas/zenodo") == "data_raw/casas/zenodo"


def test_resolve_manifest_local_path_handles_legacy_project_root(monkeypatch, tmp_path):
    project_root = tmp_path / "homekgmas"
    monkeypatch.setattr(io, "PROJECT_ROOT", project_root)

    old_path = Path("/Users/fengdefan/Documents/GitHub/pipekgbot/data_raw/smartsense/repo")

    assert io.resolve_manifest_local_path(old_path) == project_root / "data_raw" / "smartsense" / "repo"


def test_upsert_manifest_entry_stores_relative_paths_and_loads_current_root(monkeypatch, tmp_path):
    metadata_dir = tmp_path / "metadata"
    manifest_path = metadata_dir / "datasets_manifest.json"

    monkeypatch.setattr(io, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(io, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(io, "ensure_data_layout", lambda: metadata_dir.mkdir(parents=True, exist_ok=True))

    io.upsert_manifest_entry(
        {
            "dataset_name": "smartsense",
            "source_url": "https://example.com/smartsense.zip",
            "local_path": str(tmp_path / "data_raw" / "smartsense" / "repo"),
            "license_if_known": "Unknown",
            "download_method": "github_zip",
            "status": "success",
            "notes": "Downloaded.",
            "updated_at": "2026-04-15T00:00:00+00:00",
        }
    )

    raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert raw_manifest[0]["local_path"] == "data_raw/smartsense/repo"

    resolved_manifest = io.load_manifest(resolve_local_paths=True)
    assert resolved_manifest[0]["local_path"] == str(tmp_path / "data_raw" / "smartsense" / "repo")
