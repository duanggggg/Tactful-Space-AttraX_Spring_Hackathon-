from app.discussion.action_resolver import ActionResolver
from app.discussion.conflict_detector import ConflictDetector
from app.discussion.protocol import AgentProposal, DiscussionTurn
from app.memory.dialogue_compressor import DialogueCompressor
from app.planning.action import PlannedAction


def test_conflict_detection_and_compression():
    proposals = [
        AgentProposal(
            agent_name="agent_a",
            summary="Agent A proposes brighter light",
            rationale="test",
            actions=[
                PlannedAction(
                    device_id="living_room_main",
                    attribute="brightness",
                    value=70,
                    reason="test",
                    requested_by="agent_a",
                )
            ],
        ),
        AgentProposal(
            agent_name="agent_b",
            summary="Agent B proposes dimmer light",
            rationale="test",
            actions=[
                PlannedAction(
                    device_id="living_room_main",
                    attribute="brightness",
                    value=30,
                    reason="test",
                    requested_by="agent_b",
                )
            ],
        ),
    ]
    detector = ConflictDetector()
    conflicts = detector.detect(proposals, task_description="Create a calm evening scene")
    assert conflicts
    assert any(conflict.resolution_hint for conflict in conflicts)

    accepted, rejected, rationale = ActionResolver().resolve(proposals, conflicts)
    assert accepted
    assert rejected
    assert rationale
    assert rejected[0].decision_reason

    turns = [
        DiscussionTurn(round_index=1, speaker="agent_a", summary="First stance", proposal_action_count=1),
        DiscussionTurn(round_index=2, speaker="agent_b", summary="Second stance", proposal_action_count=1, turn_type="revision"),
    ]
    compressed = DialogueCompressor(window_size=1).compress(turns, conflicts=conflicts)
    assert compressed.open_conflicts
    assert compressed.accepted_decisions
    assert len(compressed.rolling_summary) <= 2


def test_action_resolver_limits_inferred_actions_to_primary_agent_budget():
    proposals = [
        AgentProposal(
            agent_name="music_agent",
            summary="Media action",
            rationale="test",
            actions=[
                PlannedAction(
                    device_id="music_player",
                    attribute="input_source",
                    value="television",
                    reason="Recent activity suggests TV control",
                    requested_by="music_agent",
                    priority="high",
                ),
                PlannedAction(
                    device_id="music_player",
                    attribute="volume",
                    value=20,
                    reason="Keep media audible",
                    requested_by="music_agent",
                    priority="medium",
                ),
            ],
        ),
        AgentProposal(
            agent_name="cooling_agent",
            summary="Cooling action",
            rationale="test",
            actions=[
                PlannedAction(
                    device_id="living_room_ac_1",
                    attribute="power",
                    value=True,
                    reason="Room is warm",
                    requested_by="cooling_agent",
                    priority="high",
                ),
                PlannedAction(
                    device_id="living_room_ac_1",
                    attribute="target_temperature",
                    value=24,
                    reason="Comfort target",
                    requested_by="cooling_agent",
                    priority="medium",
                ),
            ],
        ),
    ]

    accepted, rejected, rationale = ActionResolver().resolve(
        proposals,
        conflicts=[],
        task_source="inferred",
        task_description="Decide the next smart-home action based on recent television activity",
        task_preferences={},
    )

    assert len(accepted) == 1
    assert all(action.requested_by == "music_agent" for action in accepted)
    assert rejected
    assert rationale


def test_action_resolver_rejects_out_of_scope_agent_operations():
    proposals = [
        AgentProposal(
            agent_name="music_agent",
            summary="Invalid media action",
            rationale="test",
            actions=[
                PlannedAction(
                    device_id="living_room_ac_1",
                    attribute="power",
                    value=True,
                    reason="invalid",
                    requested_by="music_agent",
                )
            ],
        )
    ]

    accepted, rejected, rationale = ActionResolver().resolve(
        proposals,
        conflicts=[],
        task_source="user_nl",
        task_description="Turn on music",
        task_preferences={"parsed_slots": {"device": "speaker"}},
    )

    assert not accepted
    assert rejected
    assert any("out-of-scope" in item.lower() or "not allowed" in item.lower() for item in rationale)


def test_action_resolver_prefers_custom_like_action_for_inferred_tasks():
    proposals = [
        AgentProposal(
            agent_name="cooling_agent",
            summary="Cooling action",
            rationale="test",
            actions=[
                PlannedAction(
                    device_id="living_room_ac_1",
                    attribute="power",
                    value=True,
                    reason="turn on climate",
                    requested_by="cooling_agent",
                    priority="high",
                ),
                PlannedAction(
                    device_id="living_room_ac_1",
                    attribute="fan_speed",
                    value="medium",
                    reason="match inferred SmartSense control style",
                    requested_by="cooling_agent",
                    priority="medium",
                ),
            ],
        )
    ]

    accepted, rejected, _ = ActionResolver().resolve(
        proposals,
        conflicts=[],
        task_source="inferred",
        task_description="Decide the next smart-home action from recent AC history",
        task_preferences={},
    )

    assert len(accepted) == 1
    assert accepted[0].attribute == "fan_speed"
    assert rejected


def test_action_resolver_uses_wakeup_scores_to_choose_primary_inferred_agent():
    proposals = [
        AgentProposal(
            agent_name="cooling_agent",
            summary="Cooling action",
            rationale="test",
            actions=[
                PlannedAction(
                    device_id="living_room_ac_1",
                    attribute="fan_speed",
                    value="medium",
                    reason="cooling guess",
                    requested_by="cooling_agent",
                    priority="medium",
                ),
            ],
        ),
        AgentProposal(
            agent_name="music_agent",
            summary="Music action",
            rationale="test",
            actions=[
                PlannedAction(
                    device_id="music_player",
                    attribute="input_source",
                    value="television",
                    reason="media guess",
                    requested_by="music_agent",
                    priority="medium",
                ),
            ],
        ),
    ]

    accepted, rejected, _ = ActionResolver().resolve(
        proposals,
        conflicts=[],
        task_source="inferred",
        task_description="Decide the next smart-home action from recent television activity",
        task_preferences={},
        wakeup_scores={"cooling_agent": 1, "music_agent": 8},
    )

    assert len(accepted) == 1
    assert accepted[0].requested_by == "music_agent"
    assert rejected
