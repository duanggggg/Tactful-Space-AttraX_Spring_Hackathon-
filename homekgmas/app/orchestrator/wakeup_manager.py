"""Select which agents should participate in a task discussion."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.agents.agent_registry import AgentRegistry
from app.api.schemas import TaskRequest


def _flatten_text(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, dict):
        output: list[str] = []
        for key, nested in value.items():
            output.extend(_flatten_text(key))
            output.extend(_flatten_text(nested))
        return output
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        output: list[str] = []
        for item in value:
            output.extend(_flatten_text(item))
        return output
    return [str(value)]


@dataclass(frozen=True)
class WakeupScore:
    """One scored candidate from wakeup selection."""

    agent_name: str
    score: int
    matched_keywords: tuple[str, ...] = field(default_factory=tuple)
    matched_slots: tuple[str, ...] = field(default_factory=tuple)
    matched_domains: tuple[str, ...] = field(default_factory=tuple)
    matched_arguments: tuple[str, ...] = field(default_factory=tuple)
    dataset_match: bool = False


class WakeupManager:
    """Dataset-aware participant selection with conservative fallback logic."""

    def rank_agents(self, task: TaskRequest, registry: AgentRegistry) -> list[WakeupScore]:
        description = task.description.lower()
        parsed_slots = task.preferences.get("parsed_slots", {}) if isinstance(task.preferences, dict) else {}
        source_dataset = str(task.preferences.get("source_dataset", "")) if isinstance(task.preferences, dict) else ""
        trigger = task.constraints.get("trigger", {}) if isinstance(task.constraints, dict) else {}
        evidence_text = " ".join(
            part.lower()
            for part in [
                task.description,
                " ".join(_flatten_text(parsed_slots)),
                " ".join(_flatten_text(trigger)),
                source_dataset,
                task.source,
            ]
            if part
        )

        scored: list[WakeupScore] = []
        for agent in registry.list_agents():
            profile = registry.profile_for(agent.name)
            if profile is None:
                continue

            score = 0
            matched_keywords = tuple(sorted({keyword for keyword in profile.keyword_hints if keyword.lower() in description}))
            matched_slots = tuple(sorted({hint for hint in profile.slot_hints if hint.lower() in evidence_text}))
            matched_domains = tuple(sorted({domain for domain in profile.device_domains if domain.lower() in evidence_text}))
            matched_arguments = tuple(sorted({argument for argument in profile.argument_keys if argument.lower() in evidence_text}))
            dataset_match = bool(source_dataset and source_dataset in profile.source_datasets)
            if matched_keywords:
                score += 2 * len(matched_keywords)
            if matched_slots:
                score += 3 * len(matched_slots)
            if matched_domains:
                score += 3 * len(matched_domains)
            if matched_arguments:
                score += 1 * len(matched_arguments)
            if dataset_match:
                score += 1
            scored.append(
                WakeupScore(
                    agent_name=agent.name,
                    score=score,
                    matched_keywords=matched_keywords,
                    matched_slots=matched_slots,
                    matched_domains=matched_domains,
                    matched_arguments=matched_arguments,
                    dataset_match=dataset_match,
                )
            )

        return sorted(scored, key=lambda item: (item.score, item.agent_name), reverse=True)

    def score_map(self, task: TaskRequest, registry: AgentRegistry) -> dict[str, int]:
        """Return a compact agent-name to score mapping for downstream ranking."""

        return {item.agent_name: item.score for item in self.rank_agents(task, registry)}

    # 用户原话经过云端 LLM 直传时（source=xiaozhi）若全无关键词命中，
    # 默认叫醒"舒适三人组"，让多 agent 至少有一次讨论，而不是空回。
    _XIAOZHI_FALLBACK_AGENTS: tuple[str, ...] = ("lighting_agent", "music_agent", "cooling_agent")

    def select_agents(self, task: TaskRequest, registry: AgentRegistry) -> list:
        ranked = self.rank_agents(task, registry)
        if not ranked:
            return []

        selected_names: list[str] = []
        if str(task.source or "").lower() == "inferred":
            top = ranked[0]
            if top.score >= 1:
                selected_names = [top.agent_name]
        else:
            selected_names = [item.agent_name for item in ranked if item.score >= 2]
            if not selected_names:
                best_score = ranked[0].score
                if best_score >= 1:
                    selected_names = [item.agent_name for item in ranked if item.score == best_score][:2]

        # 兜底：xiaozhi 真人语音输入但所有 agent 都 0 分时，唤醒舒适三人组
        if not selected_names and str(task.source or "").lower() == "xiaozhi":
            available = {item.agent_name for item in ranked}
            selected_names = [name for name in self._XIAOZHI_FALLBACK_AGENTS if name in available]

        agent_lookup = {agent.name: agent for agent in registry.list_agents()}
        return [agent_lookup[name] for name in selected_names if name in agent_lookup]
