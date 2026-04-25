"""Build structured memory records from orchestration results."""

from __future__ import annotations

from app.core.utils import dedupe_preserve_order, slugify, utc_timestamp
from app.discussion.protocol import DiscussionRoundResult
from app.memory.memory_schema import MemoryRecord, Triple
from app.planning.plan import ExecutionPlan, ExecutionResult


class MemorySummarizer:
    """Converts a finished task into local records and triples."""

    def summarize(
        self,
        task_id: str,
        task_description: str,
        sensor_context: dict,
        outdoor_context: dict,
        device_context: dict,
        discussion_result: DiscussionRoundResult,
        plan: ExecutionPlan,
        execution_result: ExecutionResult,
    ) -> MemoryRecord:
        record_id = f"{task_id}-{slugify(task_description)[:24]}"
        involved_agents = [proposal.agent_name for proposal in discussion_result.proposals]
        conflict_records = discussion_result.conflict_history or discussion_result.conflicts
        triples = [Triple(subject=task_id, predicate="type", object="Task")]
        triples.extend(self._build_task_context_triples(task_id, task_description, sensor_context, outdoor_context))
        triples.extend(
            Triple(subject=task_id, predicate="involved_agent", object=agent_name)
            for agent_name in involved_agents
        )
        triples.extend(
            Triple(subject=task_id, predicate="selected_agent_count", object=str(len(involved_agents)))
            for _ in [0]
        )
        triples.extend(
            Triple(
                subject=task_id,
                predicate="final_action",
                object=f"{action.device_id}.{action.attribute}={action.value}",
                metadata={"requested_by": action.requested_by},
            )
            for action in plan.selected_actions
        )
        triples.extend(
            Triple(subject=task_id, predicate="affected_device", object=action.device_id)
            for action in plan.selected_actions
        )
        triples.extend(
            Triple(
                subject=task_id,
                predicate="conflict",
                object=conflict.title,
                metadata={"severity": conflict.severity},
            )
            for conflict in conflict_records
        )
        triples.extend(
            Triple(subject=task_id, predicate="resolution", object=item)
            for item in discussion_result.compressed_state.accepted_decisions
        )
        triples.append(
            Triple(
                subject=task_id,
                predicate="outcome_quality",
                object="success" if execution_result.success else "failed",
            )
        )

        tags = dedupe_preserve_order(
            involved_agents
            + self._infer_intents(task_description)
            + [str(sensor_context.get("time_of_day", ""))]
            + [str(outdoor_context.get("weather", ""))],
            limit=12,
        )

        return MemoryRecord(
            record_id=record_id,
            task_id=task_id,
            created_at=utc_timestamp(),
            task_summary=task_description,
            sensor_context=sensor_context,
            outdoor_context=outdoor_context,
            device_context=device_context,
            involved_agents=involved_agents,
            proposals=[proposal.model_dump(mode="json") for proposal in discussion_result.proposals],
            conflicts=[conflict.model_dump(mode="json") for conflict in conflict_records],
            final_actions=[action.model_dump(mode="json") for action in plan.selected_actions],
            outcome=execution_result.model_dump(mode="json"),
            tags=tags,
            discussion_state=discussion_result.compressed_state.model_dump(mode="json"),
            rounds_completed=discussion_result.rounds_completed,
            triples=triples,
        )

    def _build_task_context_triples(
        self,
        task_id: str,
        task_description: str,
        sensor_context: dict,
        outdoor_context: dict,
    ) -> list[Triple]:
        triples: list[Triple] = []
        for intent in self._infer_intents(task_description):
            triples.append(Triple(subject=task_id, predicate="intent", object=intent))
        for room in self._infer_rooms(task_description, sensor_context):
            triples.append(Triple(subject=task_id, predicate="target_room", object=room))

        time_of_day = str(sensor_context.get("time_of_day", "")).strip().lower()
        if time_of_day:
            triples.append(Triple(subject=task_id, predicate="time_of_day", object=time_of_day))

        quiet_hours = bool(sensor_context.get("quiet_hours"))
        triples.append(
            Triple(
                subject=task_id,
                predicate="policy",
                object="quiet_hours" if quiet_hours else "none",
            )
        )

        weather = str(outdoor_context.get("weather", "")).strip().lower()
        if weather:
            triples.append(Triple(subject=task_id, predicate="weather", object=weather))
        return triples

    def _infer_intents(self, task_description: str) -> list[str]:
        lowered = task_description.lower()
        intents: list[str] = []
        if "cool" in lowered or "temperature" in lowered:
            intents.append("cooling")
        if any(keyword in lowered for keyword in ("light", "bright", "dim")):
            intents.append("lighting")
        if any(keyword in lowered for keyword in ("music", "playlist", "volume", "audio")):
            intents.append("music")
        if any(keyword in lowered for keyword in ("calm", "soft", "gentle", "relax")):
            intents.append("calm_scene")
        if any(keyword in lowered for keyword in ("focus", "read", "work")):
            intents.append("focus_scene")
        return intents

    def _infer_rooms(self, task_description: str, sensor_context: dict) -> list[str]:
        lowered = task_description.lower()
        rooms = [room for room in ("living_room", "bedroom", "kitchen") if room.replace("_", " ") in lowered]
        if rooms:
            return rooms

        occupancy = sensor_context.get("occupancy", {})
        if isinstance(occupancy, dict):
            occupied = [room for room, active in occupancy.items() if active]
            if occupied:
                return occupied
        return []
