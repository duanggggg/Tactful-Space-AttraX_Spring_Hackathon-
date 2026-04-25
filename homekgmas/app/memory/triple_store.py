"""Local file-based triple and memory record persistence."""

from __future__ import annotations

import heapq
import json
from pathlib import Path

from app.memory.memory_schema import MemoryQuery, MemoryRecord
from app.storage.file_store import FileStore


class TripleStore:
    """Persist memory records and triples to local files."""

    def __init__(self, memory_dir: Path) -> None:
        self.memory_dir = memory_dir
        self.records_dir = self.memory_dir / "records"
        self.triples_path = self.memory_dir / "triples.jsonl"
        self.file_store = FileStore()
        self.file_store.ensure_dir(self.records_dir)

    def save_record(self, record: MemoryRecord) -> Path:
        record_path = self.records_dir / f"{record.record_id}.json"
        self.file_store.write_json(record_path, record.model_dump(mode="json"))
        for triple in record.triples:
            self.file_store.append_jsonl(self.triples_path, triple.model_dump(mode="json"))
        return record_path

    def _record_mtime_ns(self, path: Path) -> int:
        try:
            return path.stat().st_mtime_ns
        except OSError:
            return 0

    def _ordered_record_paths(self, *, limit_hint: int | None = None) -> list[Path]:
        paths = [path for path in self.records_dir.glob("*.json") if path.is_file()]
        if limit_hint is not None and limit_hint > 0:
            return heapq.nlargest(limit_hint, paths, key=self._record_mtime_ns)
        return sorted(paths, key=self._record_mtime_ns, reverse=True)

    def query_records(self, query: MemoryQuery) -> list[MemoryRecord]:
        records: list[MemoryRecord] = []
        candidate_paths = self._ordered_record_paths(
            limit_hint=query.limit if not query.agent_name and not query.keywords else None
        )
        for path in candidate_paths:
            payload = self.file_store.read_json(path, default={})
            if not payload:
                continue
            record = MemoryRecord(**payload)
            if query.agent_name and query.agent_name not in record.involved_agents:
                continue

            haystack = json.dumps(record.model_dump(mode="json")).lower()
            if query.keywords and not any(keyword.lower() in haystack for keyword in query.keywords):
                continue

            records.append(record)
            if len(records) >= query.limit:
                break
        return records

    def recent_records(self, limit: int = 5) -> list[MemoryRecord]:
        return self.query_records(MemoryQuery(limit=limit))
