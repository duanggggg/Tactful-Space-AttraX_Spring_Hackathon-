"""Simple graph-like memory retrieval over local records."""

from __future__ import annotations

import json

from app.core.utils import dedupe_preserve_order, sentence_case
from app.memory.memory_schema import GraphMemoryContext, MemoryRecord
from app.memory.triple_store import TripleStore


class GraphRetriever:
    """Retrieves relevant local memories for a specific agent and task."""

    def __init__(self, triple_store: TripleStore) -> None:
        self.triple_store = triple_store

    def _score_record(self, agent_name: str, keywords: list[str], record: MemoryRecord) -> int:
        score = 0
        if agent_name in record.involved_agents:
            score += 4

        haystack_parts = [
            record.task_summary,
            json.dumps(record.tags),
            json.dumps(record.final_actions),
            json.dumps(record.conflicts),
            json.dumps(record.discussion_state),
        ]
        haystack = " ".join(haystack_parts).lower()

        for keyword in keywords:
            if keyword in haystack:
                score += 2
            if keyword in record.task_summary.lower():
                score += 1

        if not keywords and agent_name in record.involved_agents:
            score += 1

        return score

    def retrieve_for_agent(
        self,
        agent_name: str,
        task_text: str,
        limit: int = 3,
    ) -> list[MemoryRecord]:
        keywords = [token for token in task_text.lower().split() if len(token) > 3][:6]
        candidates = self.triple_store.recent_records(limit=max(limit * 6, 12))
        scored_records = []

        for record in candidates:
            score = self._score_record(agent_name, keywords, record)
            if score > 0:
                scored_records.append((score, record.created_at, record))

        scored_records.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [record for _, _, record in scored_records[:limit]]

    def retrieve_context(
        self,
        agent_name: str,
        task_text: str,
        *,
        sensor_context: dict | None = None,
        record_limit: int = 3,
        max_facts: int = 8,
    ) -> GraphMemoryContext:
        """Convert nearby graph memories into compact prompt facts."""

        sensor_context = sensor_context or {}
        records = self.retrieve_for_agent(agent_name, task_text, limit=record_limit)
        facts: list[str] = []
        strategies: list[str] = []
        warnings: list[str] = []

        for record in records:
            facts.extend(self._extract_facts(record, sensor_context))
            strategies.extend(self._extract_strategies(record, agent_name))
            warnings.extend(self._extract_warnings(record, sensor_context))

        return GraphMemoryContext(
            facts=dedupe_preserve_order(facts, limit=max_facts),
            reusable_strategies=dedupe_preserve_order(strategies, limit=max_facts),
            warnings=dedupe_preserve_order(warnings, limit=max_facts),
            source_record_ids=[record.record_id for record in records],
            retrieval_metadata={
                "record_limit": record_limit,
                "selected_record_count": len(records),
                "task_keyword_count": len([token for token in task_text.lower().split() if len(token) > 3][:6]),
            },
        )

    def _extract_facts(self, record: MemoryRecord, sensor_context: dict) -> list[str]:
        facts: list[str] = [f"Related task: {sentence_case(record.task_summary)}"]
        for triple in record.triples:
            if triple.predicate == "target_room":
                facts.append(f"Target room in similar history: {triple.object}.")
            elif triple.predicate == "time_of_day":
                facts.append(f"Similar history was resolved during the {triple.object}.")
            elif triple.predicate == "intent":
                facts.append(f"Recurring intent tag: {triple.object}.")
            elif triple.predicate == "policy" and str(triple.object).lower() != "none":
                facts.append(f"Policy seen in similar history: {triple.object}.")

        current_time_of_day = str(sensor_context.get("time_of_day", "")).strip().lower()
        if current_time_of_day and current_time_of_day in json.dumps(record.model_dump(mode="json")).lower():
            facts.append(f"Current task matches past {current_time_of_day} context.")
        return facts

    def _extract_strategies(self, record: MemoryRecord, agent_name: str) -> list[str]:
        strategies: list[str] = []
        for triple in record.triples:
            if triple.predicate == "final_action":
                requested_by = str(triple.metadata.get("requested_by", "")).strip()
                if not requested_by or requested_by == agent_name:
                    strategies.append(f"Previously effective action: {triple.object}.")
            elif triple.predicate == "resolution":
                strategies.append(f"Conflict resolution pattern: {triple.object}.")

        if not strategies and record.final_actions:
            action = record.final_actions[0]
            strategies.append(
                "Previously effective action: "
                f"{action.get('device_id')}.{action.get('attribute')}={action.get('value')}."
            )
        return strategies

    def _extract_warnings(self, record: MemoryRecord, sensor_context: dict) -> list[str]:
        warnings: list[str] = []
        for triple in record.triples:
            if triple.predicate == "conflict":
                warnings.append(f"Past conflict to avoid: {triple.object}.")
            elif triple.predicate == "policy" and str(triple.object).lower() == "quiet_hours":
                warnings.append("Quiet-hours policy appeared in related history.")

        if sensor_context.get("quiet_hours"):
            warnings.append("Current environment is in quiet hours.")
        return warnings
