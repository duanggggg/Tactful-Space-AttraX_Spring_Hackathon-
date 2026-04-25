"""Simple JSON/JSONL helpers for local file-based persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FileStore:
    """Small helper that persists structured data on disk."""

    def ensure_dir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def read_json(self, path: Path, default: Any | None = None) -> Any:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def read_jsonl(self, path: Path) -> list[Any]:
        if not path.exists():
            return []
        records: list[Any] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
        return records

    def read_text(self, path: Path, default: str = "") -> str:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return handle.read()

    def write_json(self, path: Path, payload: Any) -> None:
        self.ensure_dir(path.parent)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=True)

    def write_text(self, path: Path, payload: str) -> None:
        self.ensure_dir(path.parent)
        with path.open("w", encoding="utf-8") as handle:
            handle.write(payload)

    def append_jsonl(self, path: Path, payload: Any) -> None:
        self.ensure_dir(path.parent)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True))
            handle.write("\n")
