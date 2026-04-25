"""Run one local agent discussion round."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from app.discussion.action_resolver import ActionResolver
from app.discussion.conflict_detector import ConflictDetector
from app.discussion.protocol import DiscussionRoundResult, DiscussionTurn, RevisionRequest
from app.memory.coordinator import AgentMemoryBundle
from app.memory.dialogue_compressor import DialogueCompressor
from app.orchestrator.topic_builder import DiscussionTopic


class DiscussionManager:
    """Coordinates an initial proposal pass and one revision pass."""

    def __init__(
        self,
        compressor: DialogueCompressor,
        conflict_detector: ConflictDetector,
        action_resolver: ActionResolver,
        max_rounds: int = 2,
    ) -> None:
        self.compressor = compressor
        self.conflict_detector = conflict_detector
        self.action_resolver = action_resolver
        self.max_rounds = max_rounds

    def _detect_conflicts(self, topic: DiscussionTopic, proposals) -> list:
        return self.conflict_detector.detect(
            proposals,
            quiet_hours=topic.sensor_snapshot.quiet_hours,
            task_description=topic.description,
            time_of_day=topic.sensor_snapshot.time_of_day,
        )

    def run(
        self,
        topic: DiscussionTopic,
        agents: list,
        memory_by_agent: dict[str, AgentMemoryBundle],
        wakeup_scores: dict[str, int] | None = None,
    ) -> DiscussionRoundResult:
        turns = []
        proposal_history = []

        # initialize 必须串行（agent 的 memory 设置不是线程安全/不在意但 cheap）
        for agent in agents:
            bundle = memory_by_agent.get(agent.name, AgentMemoryBundle())
            agent.initialize(
                bundle.graph_records,
                graph_memory_context=bundle.graph_context,
                workspace_memory_context=bundle.workspace_context,
            )

        # 同一轮内的 LLM-backed propose 并行——大头在这里
        max_workers = max(1, len(agents))
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="agent-propose") as pool:
            current_proposals = list(pool.map(lambda a: a.propose(topic), agents))

        proposal_history.extend(current_proposals)
        for agent, proposal in zip(agents, current_proposals):
            turns.append(
                DiscussionTurn(
                    round_index=1,
                    speaker=agent.name,
                    summary=proposal.summary,
                    turn_type="proposal",
                    proposal_action_count=len(proposal.actions),
                )
            )

        conflicts = self._detect_conflicts(topic, current_proposals)
        conflict_history = list(conflicts)
        rounds_completed = 1

        if conflicts and self.max_rounds > 1:
            accepted, rejected, _ = self.action_resolver.resolve(
                current_proposals,
                conflicts,
                quiet_hours=topic.sensor_snapshot.quiet_hours,
                task_source=topic.source,
                task_description=topic.description,
                task_preferences=topic.preferences,
                wakeup_scores=wakeup_scores,
            )
            revision_request = RevisionRequest(
                round_index=2,
                conflicts=conflicts,
                accepted_actions=accepted,
                rejected_actions=rejected,
                notes=[conflict.resolution_hint for conflict in conflicts if conflict.resolution_hint],
            )
            prior_by_name = {p.agent_name: p for p in current_proposals}

            def _revise_one(agent):
                prior = prior_by_name[agent.name]
                return agent.revise(topic, prior, revision_request)

            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="agent-revise") as pool:
                revised_proposals = list(pool.map(_revise_one, agents))

            proposal_history.extend(revised_proposals)
            for agent, revised in zip(agents, revised_proposals):
                turns.append(
                    DiscussionTurn(
                        round_index=2,
                        speaker=agent.name,
                        summary=revised.summary,
                        turn_type="revision",
                        proposal_action_count=len(revised.actions),
                    )
                )

            current_proposals = revised_proposals
            conflicts = self._detect_conflicts(topic, current_proposals)
            conflict_history.extend(conflicts)
            rounds_completed = 2

        compressed_state = self.compressor.compress(turns=turns, conflicts=conflicts)
        return DiscussionRoundResult(
            proposals=current_proposals,
            proposal_history=proposal_history,
            turns=turns,
            conflicts=conflicts,
            conflict_history=conflict_history,
            rounds_completed=rounds_completed,
            compressed_state=compressed_state,
        )
