from pathlib import Path

from app.core.config import build_settings
from app.main import create_app


def build_test_settings(tmp_path: Path):
    return build_settings({"output_dir": tmp_path / "outputs", "llm_enabled": False})


def build_test_app(tmp_path: Path):
    settings = build_test_settings(tmp_path)
    return create_app(settings), settings
