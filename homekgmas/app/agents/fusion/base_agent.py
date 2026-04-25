"""Base class for all home-domain agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
from typing import Any

from app.agents.capability import Capability
from app.agents.catalog import AgentActionProfile
from app.agents.persona import AgentPersona
from app.agents.fusion.workspace import AgentWorkspaceProfile
from app.core.logger import get_logger
from app.discussion.protocol import AgentProposal, RevisionRequest
from app.llm.client import ChatModelClient
from app.memory.memory_schema import GraphMemoryContext, MemoryRecord
from app.memory.workspace_store import WorkspaceMemoryContext
from app.orchestrator.topic_builder import DiscussionTopic
from app.planning.action import PlannedAction


class BaseAgent(ABC):
    """Abstract base class for all domain agents."""

    def __init__(
        self,
        name: str,
        persona: AgentPersona,
        capabilities: list[Capability],
        workspace_profile: AgentWorkspaceProfile,
        action_profile: AgentActionProfile | None = None,
        llm_client: ChatModelClient | None = None,
    ) -> None:
        self.name = name
        self.persona = persona
        self.capabilities = capabilities
        self.workspace_profile = workspace_profile
        self.action_profile = action_profile
        self.llm_client = llm_client
        self.memory_records: list[MemoryRecord] = []
        self.graph_memory_context = GraphMemoryContext()
        self.workspace_memory_context = WorkspaceMemoryContext()
        self.logger = get_logger(f"app.agents.{name}")

    def initialize(
        self,
        memory_records: list[MemoryRecord],
        graph_memory_context: GraphMemoryContext | None = None,
        workspace_memory_context: WorkspaceMemoryContext | None = None,
    ) -> None:
        """Load task-relevant local memory before proposing actions."""

        self.memory_records = memory_records
        self.graph_memory_context = graph_memory_context or GraphMemoryContext()
        self.workspace_memory_context = workspace_memory_context or WorkspaceMemoryContext()

    def memory_summary(self) -> str:
        """Return a concise memory summary string."""

        if self.graph_memory_context.has_content():
            return self.graph_memory_context.summary()
        if self.memory_records:
            return f"Loaded {len(self.memory_records)} relevant memory record(s)."
        if self.workspace_memory_context.has_content():
            return self.workspace_memory_summary()
        return "No matching local memory yet."

    def workspace_memory_summary(self) -> str:
        """Return a concise workspace-memory summary string."""

        return self.workspace_memory_context.summary()

    def graph_memory_summary(self) -> str:
        """Return a concise graph-memory summary string."""

        return self.graph_memory_context.summary()

    def render_memory_context(self, *, max_chars: int = 900) -> str:
        """Render the memory payload that should reach the model."""

        if self.graph_memory_context.has_content():
            return self.graph_memory_context.render_for_prompt(max_chars=max_chars)
        if self.workspace_memory_context.has_content():
            return self.workspace_memory_context.render_for_prompt(max_chars=max_chars)
        if not self.memory_records:
            return ""

        lines: list[str] = []
        for record in self.memory_records[:3]:
            lines.append(f"- Past task: {record.task_summary}")
            for action in record.final_actions[:2]:
                lines.append(
                    "- Past action: "
                    f"{action.get('device_id')}.{action.get('attribute')}={action.get('value')}"
                )
        packed: list[str] = []
        total = 0
        for line in lines:
            line_cost = len(line) + (1 if packed else 0)
            if packed and total + line_cost > max_chars:
                break
            packed.append(line)
            total += line_cost
        return "\n".join(packed)

    def soul_summary(self) -> str:
        """Return the workspace soul summary for prompts and debugging."""

        return self.workspace_profile.soul_summary()

    def skill_summary(self) -> str:
        """Return the workspace skill summary for prompts and debugging."""

        return self.workspace_profile.skills_summary()

    def allowed_action_targets(self) -> dict[str, set[str]]:
        """Return allowed device and attribute pairs for this domain agent."""

        return {}

    def effective_action_targets(self) -> dict[str, set[str]]:
        """Return the merged static and dataset-driven action targets."""

        merged: dict[str, set[str]] = {
            device_id: set(attributes)
            for device_id, attributes in self.allowed_action_targets().items()
        }
        if self.action_profile is None:
            return merged
        for device_id, attributes in self.action_profile.action_targets().items():
            merged.setdefault(device_id, set()).update(attributes)
        return merged

    def prompt_action_catalog(self) -> dict[str, Any]:
        """Return a prompt-visible summary of this agent's action space."""

        if self.action_profile is None:
            return {
                "mode": "generic",
                "device_domains": [],
                "service_names": [],
                "argument_keys": [],
                "keyword_hints": [],
                "slot_hints": [],
                "allowed_devices": {
                    device_id: sorted(attributes)
                    for device_id, attributes in self.effective_action_targets().items()
                },
                "examples": [],
            }
        payload = self.action_profile.prompt_payload()
        payload["allowed_devices"] = {
            device_id: sorted(attributes)
            for device_id, attributes in self.effective_action_targets().items()
        }
        return payload

    def build_validation_feedback(self, actions: list[PlannedAction]) -> dict[str, Any]:
        """Summarize whether the current actions fit the declared action space."""

        allowed_targets = self.effective_action_targets()
        if not actions:
            return {
                "status": "empty",
                "notes": ["No actions proposed yet. Prefer zero actions over uncertain off-domain actions."],
            }

        invalid: list[str] = []
        for action in actions:
            if action.device_id not in allowed_targets:
                invalid.append(f"{action.device_id} is not owned by {self.name}.")
                continue
            if action.attribute not in allowed_targets.get(action.device_id, set()):
                invalid.append(f"{action.device_id}.{action.attribute} is outside the allowed action space.")
        if invalid:
            return {"status": "needs_correction", "notes": invalid[:4]}
        return {
            "status": "valid",
            "notes": ["All proposed actions matched the current device and attribute guardrails."],
        }

    def normalize_action_value(self, attribute: str, value: Any) -> Any:
        """Normalize common model-produced values before validation."""

        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered == "true":
                return True
            if lowered == "false":
                return False
        return value

    def normalize_action_priority(self, value: Any) -> str:
        """Convert model priority values into the internal literal set."""

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"low", "medium", "high"}:
                return normalized
            if normalized in {"1", "p1"}:
                return "high"
            if normalized in {"2", "p2"}:
                return "medium"
            if normalized in {"3", "p3"}:
                return "low"
        if isinstance(value, (int, float)):
            if int(value) <= 1:
                return "high"
            if int(value) == 2:
                return "medium"
            return "low"
        return "medium"

    def _build_llm_proposal(
        self,
        payload: dict[str, Any],
        *,
        round_index: int,
        fallback_summary: str,
        fallback_rationale: str,
    ) -> AgentProposal:
        """Validate and normalize a structured model response."""

        actions: list[PlannedAction] = []
        allowed_targets = self.effective_action_targets()
        validation_feedback: list[str] = []

        for raw_action in payload.get("actions", []):
            if not isinstance(raw_action, dict):
                continue

            device_id = str(raw_action.get("device_id", "")).strip()
            attribute = str(raw_action.get("attribute", "")).strip()
            if not device_id or not attribute:
                validation_feedback.append("Skipped one incomplete action because device_id or attribute was missing.")
                continue
            if allowed_targets and device_id not in allowed_targets:
                validation_feedback.append(f"Skipped {device_id}.{attribute} because the device is outside {self.name}'s scope.")
                continue
            if allowed_targets and attribute not in allowed_targets.get(device_id, set()):
                validation_feedback.append(f"Skipped {device_id}.{attribute} because the attribute is not allowed.")
                continue

            action_data = {
                "device_id": device_id,
                "attribute": attribute,
                "value": self.normalize_action_value(attribute, raw_action.get("value")),
                "reason": str(raw_action.get("reason") or f"{self.name} model suggestion"),
                "requested_by": self.name,
                "priority": self.normalize_action_priority(raw_action.get("priority")),
            }
            try:
                actions.append(PlannedAction.model_validate(action_data))
            except Exception as exc:
                self.logger.warning("Skipping invalid LLM action for %s: %s", self.name, exc)
                validation_feedback.append(f"Skipped {device_id}.{attribute} because validation failed.")

        concerns = [
            str(concern).strip()
            for concern in (
                payload.get("concerns", [])
                if isinstance(payload.get("concerns", []), list)
                else [payload.get("concerns")]
            )
            if str(concern).strip()
        ]
        return AgentProposal(
            agent_name=self.name,
            summary=str(payload.get("summary") or fallback_summary),
            rationale=payload.get("rationale_points", payload.get("rationale") or fallback_rationale),
            round_index=round_index,
            actions=actions,
            concerns=concerns,
            validation_feedback=validation_feedback or self.build_validation_feedback(actions)["notes"],
        )

    def request_llm_proposal(
        self,
        *,
        topic: DiscussionTopic,
        round_index: int,
        domain_instructions: str,
        fallback_summary: str,
        fallback_rationale: str,
        prior_proposal: AgentProposal | None = None,
        revision_request: RevisionRequest | None = None,
    ) -> AgentProposal | None:
        """Request a structured proposal from the configured model."""

        if self.llm_client is None:
            return None

        request_payload: dict[str, Any] = {
            "task": topic.model_dump(mode="json"),
            "agent": {
                "name": self.name,
                "persona": self.persona.model_dump(mode="json"),
                "capabilities": [capability.model_dump(mode="json") for capability in self.capabilities],
                "soul": self.soul_summary(),
                "skills": self.workspace_profile.skills,
                "memory_summary": self.memory_summary(),
                "graph_memory_summary": self.graph_memory_summary(),
                "workspace_memory_summary": self.workspace_memory_summary(),
                "memory_context": self.render_memory_context(),
            },
            "action_catalog": self.prompt_action_catalog(),
            "allowed_action_targets": {
                device_id: sorted(attributes)
                for device_id, attributes in self.effective_action_targets().items()
            },
            "action_feedback": {
                "status": "ready",
                "notes": [
                    "Only propose actions that fit the declared device and attribute space.",
                    "Prefer the smallest action set that satisfies the task.",
                ],
            },
            "round_index": round_index,
        }
        if prior_proposal is not None:
            request_payload["prior_proposal"] = prior_proposal.model_dump(mode="json")
            request_payload["action_feedback"] = self.build_validation_feedback(prior_proposal.actions)
        if revision_request is not None:
            request_payload["revision_request"] = revision_request.model_dump(mode="json")

        system_prompt = (
            f"你是智能家居领域智能体「{self.name}」。\n"
            f"角色定位：{self.soul_summary()}\n"
            f"核心技能：{self.skill_summary() or '按照配置的领域职责工作。'}\n"
            f"{domain_instructions}\n"
            "【输出语言：必须全部使用简体中文】summary / rationale / concerns 字段都用中文，"
            "禁止英文叙述（device_id 等英文标识符可以保留）。\n"
            "返回一个 JSON 对象，包含字段：summary, rationale, concerns, actions。\n"
            "- summary：一句话中文，描述本次决策。\n"
            "- rationale：1-3 条中文短句，说明判断依据，引用环境数据时给出具体数值。\n"
            "- concerns：中文短句数组，列出顾虑或冲突点；没有就给空数组。\n"
            "- actions：对象数组，字段 device_id / attribute / value / reason / priority；reason 用中文。\n"
            "只能使用 allowed_action_targets 列出的设备和属性。\n"
            "结合 action_catalog 与 action_feedback 留在允许的动作空间内。\n"
            "任务明确时，倾向给出最少而精准的动作，而不是大而全的场景包。\n"
            "不要写 requested_by 字段，由应用层注入。\n"
            "如果当前没有适合做的动作，actions 返回空数组即可。"
        )

        try:
            payload = self.llm_client.generate_json(
                system_prompt=system_prompt,
                user_prompt=json.dumps(request_payload, ensure_ascii=True, indent=2),
            )
            self.logger.info("Using LLM-backed proposal generation for round %s.", round_index)
            return self._build_llm_proposal(
                payload,
                round_index=round_index,
                fallback_summary=fallback_summary,
                fallback_rationale=fallback_rationale,
            )
        except Exception as exc:
            self.logger.warning("Falling back to rule-based reasoning after LLM error: %s", exc)
            return None

    @abstractmethod
    def propose(self, topic: DiscussionTopic) -> AgentProposal:
        """Produce a structured proposal for the given discussion topic."""

    def revise(
        self,
        topic: DiscussionTopic,
        prior_proposal: AgentProposal,
        revision_request: RevisionRequest,
    ) -> AgentProposal:
        """Revise a prior proposal when discussion feedback indicates conflicts."""

        return prior_proposal.model_copy(deep=True)
