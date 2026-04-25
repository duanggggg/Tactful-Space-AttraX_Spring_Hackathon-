from app.agents.cooling_agent import CoolingAgent
from app.agents.lighting_agent import LightingAgent
from app.agents.music_agent import MusicAgent
from app.discussion.protocol import AgentProposal
from app.environment.home_state import DeviceState, SensorSnapshot
from app.orchestrator.topic_builder import DiscussionTopic


def test_agents_generate_structured_proposals():
    topic = DiscussionTopic(
        task_id="task-test",
        description="Create a cool calm evening with soft light and music",
        source="user",
        sensor_snapshot=SensorSnapshot(),
        device_state=DeviceState(),
    )

    cooling = CoolingAgent()
    lighting = LightingAgent()
    music = MusicAgent()

    cooling_proposal = cooling.propose(topic)
    lighting_proposal = lighting.propose(topic)
    music_proposal = music.propose(topic)

    assert cooling_proposal.agent_name == "cooling_agent"
    assert lighting_proposal.agent_name == "lighting_agent"
    assert music_proposal.agent_name == "music_agent"
    assert cooling_proposal.actions
    assert lighting_proposal.actions
    assert music_proposal.actions


class StubChatClient:
    def __init__(self, payload):
        self.payload = payload

    def generate_json(self, *, system_prompt: str, user_prompt: str):
        return self.payload


def test_agent_can_use_llm_structured_proposal():
    topic = DiscussionTopic(
        task_id="task-test",
        description="Prepare a calm evening with dim light",
        source="user",
        sensor_snapshot=SensorSnapshot(),
        device_state=DeviceState(),
    )

    lighting = LightingAgent(
        llm_client=StubChatClient(
            {
                "summary": "LLM lighting plan prepared.",
                "rationale": "The model selected a soft brightness level for evening comfort.",
                "concerns": ["Brightness should stay moderate."],
                "actions": [
                    {
                        "device_id": "living_room_main",
                        "attribute": "power",
                        "value": True,
                        "reason": "Need light for the requested scene.",
                        "priority": "1",
                    },
                    {
                        "device_id": "living_room_main",
                        "attribute": "brightness",
                        "value": 42,
                        "reason": "A soft scene fits the request.",
                        "priority": "medium",
                    },
                ],
            }
        )
    )

    proposal = lighting.propose(topic)

    assert proposal.summary == "LLM lighting plan prepared."
    assert proposal.rationale
    assert isinstance(proposal.rationale, list)
    assert proposal.actions[0].priority == "high"
    assert proposal.actions[1].value == 42
    assert all(action.requested_by == "lighting_agent" for action in proposal.actions)


def test_proposal_normalizes_string_concerns_without_character_splitting():
    proposal = AgentProposal(
        agent_name="cooling_agent",
        summary="Cooling ready",
        rationale="Temperature is high; comfort matters",
        concerns="High cooling may conflict with energy-saving goals",
    )

    assert proposal.concerns == ["High cooling may conflict with energy-saving goals."]
    assert proposal.rationale == ["Temperature is high.", "Comfort matters."]
