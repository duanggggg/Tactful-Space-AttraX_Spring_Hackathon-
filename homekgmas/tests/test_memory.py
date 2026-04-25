from app.agents.agent_registry import AgentRegistry
from app.api.schemas import TaskRequest
from app.core.config import build_settings
from app.core.utils import utc_timestamp
from app.environment.simulator import HomeSimulator
from app.evaluation.benchmark_runner import BenchmarkRunner
from app.evaluation.baselines import build_framework_baseline_specs
from app.evaluation.memory_benchmark import MemoryBenchmarkRunner
from app.memory.coordinator import MemoryCoordinator
from app.memory.graph_retriever import GraphRetriever
from app.memory.memory_schema import MemoryQuery, MemoryRecord, Triple
from app.memory.triple_store import TripleStore
from app.memory.workspace_store import WorkspaceMemoryStore
from app.orchestrator.central_node import CentralNode


def test_triple_store_saves_and_queries(tmp_path):
    store = TripleStore(tmp_path / "memory")
    record = MemoryRecord(
        record_id="record-1",
        task_id="task-1",
        created_at=utc_timestamp(),
        task_summary="Cool the living room",
        involved_agents=["cooling_agent"],
        tags=["cooling_agent"],
        triples=[Triple(subject="task-1", predicate="involved_agent", object="cooling_agent")],
    )

    store.save_record(record)
    matches = store.query_records(MemoryQuery(agent_name="cooling_agent", keywords=["living"], limit=3))

    assert len(matches) == 1
    assert matches[0].task_id == "task-1"


def test_graph_retriever_scores_agent_relevant_history(tmp_path):
    store = TripleStore(tmp_path / "memory")
    cooling_record = MemoryRecord(
        record_id="record-cooling",
        task_id="task-cooling",
        created_at=utc_timestamp(),
        task_summary="Cool the living room for a calm evening",
        involved_agents=["cooling_agent"],
        tags=["cooling_agent", "calm"],
        final_actions=[{"device_id": "living_room_ac_1", "attribute": "target_temperature", "value": 25}],
        discussion_state={"rolling_summary": ["Cooling proposal revised for calm comfort"]},
        triples=[Triple(subject="task-cooling", predicate="involved_agent", object="cooling_agent")],
    )
    lighting_record = MemoryRecord(
        record_id="record-lighting",
        task_id="task-lighting",
        created_at=utc_timestamp(),
        task_summary="Bright kitchen work scene",
        involved_agents=["lighting_agent"],
        tags=["lighting_agent", "bright"],
        triples=[Triple(subject="task-lighting", predicate="involved_agent", object="lighting_agent")],
    )

    store.save_record(cooling_record)
    store.save_record(lighting_record)

    retrieved = GraphRetriever(store).retrieve_for_agent(
        "cooling_agent",
        "Need a calm cool living room scene",
        limit=2,
    )

    assert retrieved
    assert retrieved[0].task_id == "task-cooling"


def test_graph_retriever_builds_compact_graph_context(tmp_path):
    store = TripleStore(tmp_path / "memory")
    record = MemoryRecord(
        record_id="record-cooling",
        task_id="task-cooling",
        created_at=utc_timestamp(),
        task_summary="Cool the living room for a calm evening",
        involved_agents=["cooling_agent"],
        tags=["cooling_agent", "calm", "evening"],
        final_actions=[{"device_id": "living_room_ac_1", "attribute": "target_temperature", "value": 25}],
        triples=[
            Triple(subject="task-cooling", predicate="intent", object="cooling"),
            Triple(subject="task-cooling", predicate="target_room", object="living_room"),
            Triple(subject="task-cooling", predicate="time_of_day", object="evening"),
            Triple(subject="task-cooling", predicate="final_action", object="living_room_ac_1.target_temperature=25"),
        ],
    )
    store.save_record(record)

    context = GraphRetriever(store).retrieve_context(
        "cooling_agent",
        "Need a calm cool living room scene",
        sensor_context={"time_of_day": "evening"},
    )

    assert context.facts
    assert any("living_room" in fact for fact in context.facts)
    assert any("effective action" in item.lower() for item in context.reusable_strategies)
    assert context.render_for_prompt()


def test_workspace_memory_store_bootstraps_and_persists_entries(tmp_path):
    settings = build_settings({"output_dir": tmp_path / "outputs"})
    workspace_store = WorkspaceMemoryStore(settings.agent_workspace_dir)
    registry = AgentRegistry.from_config(settings.agents_config_path, workspace_store=workspace_store)

    record = MemoryRecord(
        record_id="record-1",
        task_id="task-1",
        created_at=utc_timestamp(),
        task_summary="Create a calm evening with music",
        involved_agents=["music_agent"],
        proposals=[
            {
                "agent_name": "music_agent",
                "rationale": ["Mood support matters.", "Volume should stay gentle."],
                "concerns": ["Respect quiet-hours policies."],
                "actions": [{"device_id": "music_player", "attribute": "volume", "value": 18}],
            }
        ],
        tags=["music_agent", "calm"],
    )

    workspace_store.persist_record(record)
    context = workspace_store.retrieve_for_agent("music_agent", "Need a calm music scene")

    assert registry.get("music_agent").workspace_profile.soul
    assert (settings.agent_workspace_dir / "music_agent" / "SOUL.md").exists()
    assert context.short_term
    assert context.long_term


def test_memory_coordinator_supports_kg_facts_backend(tmp_path):
    settings = build_settings({"output_dir": tmp_path / "outputs", "primary_memory_backend": "kg_facts"})
    triple_store = TripleStore(settings.memory_dir)
    workspace_store = WorkspaceMemoryStore(settings.agent_workspace_dir)
    AgentRegistry.from_config(settings.agents_config_path, workspace_store=workspace_store)

    triple_store.save_record(
        MemoryRecord(
            record_id="record-1",
            task_id="task-1",
            created_at=utc_timestamp(),
            task_summary="Create a cool calm evening with soft light and music",
            involved_agents=["cooling_agent"],
            tags=["cooling_agent", "calm", "evening"],
            triples=[
                Triple(subject="task-1", predicate="intent", object="cooling"),
                Triple(subject="task-1", predicate="time_of_day", object="evening"),
                Triple(subject="task-1", predicate="final_action", object="living_room_ac_1.target_temperature=25"),
            ],
        )
    )
    coordinator = MemoryCoordinator(
        graph_retriever=GraphRetriever(triple_store),
        workspace_store=workspace_store,
        primary_backend=settings.primary_memory_backend,
    )

    bundle = coordinator.retrieve_for_agent_with_context(
        "cooling_agent",
        "Need a calm cool living room scene",
        sensor_context={"time_of_day": "evening"},
    )

    assert bundle.active_backend == "kg_facts"
    assert bundle.graph_context.facts
    assert bundle.prompt_char_count() > 0


def test_memory_coordinator_none_backend_skips_graph_retrieval(tmp_path):
    class FailingGraphRetriever:
        def retrieve_for_agent(self, agent_name: str, task_text: str):
            raise AssertionError("graph retrieval should not run for backend=none")

        def retrieve_context(self, agent_name: str, task_text: str, *, sensor_context=None):
            raise AssertionError("graph context retrieval should not run for backend=none")

    settings = build_settings({"output_dir": tmp_path / "outputs", "primary_memory_backend": "none"})
    workspace_store = WorkspaceMemoryStore(settings.agent_workspace_dir)
    coordinator = MemoryCoordinator(
        graph_retriever=FailingGraphRetriever(),
        workspace_store=workspace_store,
        primary_backend="none",
    )

    bundle = coordinator.retrieve_for_agent_with_context(
        "cooling_agent",
        "Need a calm cool living room scene",
        sensor_context={"time_of_day": "evening"},
    )

    assert bundle.active_backend == "none"
    assert not bundle.graph_records
    assert not bundle.graph_context.has_content()


def test_benchmark_runner_returns_summary(tmp_path):
    settings = build_settings({"output_dir": tmp_path / "outputs"})
    triple_store = TripleStore(settings.memory_dir)
    workspace_store = WorkspaceMemoryStore(settings.agent_workspace_dir)
    simulator = HomeSimulator.from_settings(settings)
    registry = AgentRegistry.from_config(
        settings.agents_config_path,
        workspace_store=workspace_store,
    )
    retriever = GraphRetriever(triple_store)
    memory_coordinator = MemoryCoordinator(
        graph_retriever=retriever,
        workspace_store=workspace_store,
        primary_backend=settings.primary_memory_backend,
    )
    central_node = CentralNode.build_default(
        simulator=simulator,
        agent_registry=registry,
        triple_store=triple_store,
        memory_coordinator=memory_coordinator,
        compression_window=settings.compression_window,
    )

    report = BenchmarkRunner(central_node, simulator).run(
        [
            TaskRequest(description="Create a cool calm evening with soft light and music"),
            TaskRequest(description="Prepare a bright focused lighting scene for reading"),
        ]
    )

    assert report.summary.task_count == 2
    assert len(report.records) == 2
    assert 0.0 <= report.summary.mas_success_rate <= 1.0


def test_framework_baseline_specs_cover_rule_and_agentic_kg():
    specs = build_framework_baseline_specs()
    spec_ids = {spec.framework_id for spec in specs}

    assert "rule_only" in spec_ids
    assert "llm_direct" in spec_ids
    assert "agentic_kg_memory" in spec_ids


def test_memory_benchmark_runner_compares_backends(tmp_path):
    central_nodes = {}
    for backend in ("none", "workspace_text", "kg_facts"):
        settings = build_settings({"output_dir": tmp_path / backend, "primary_memory_backend": backend})
        triple_store = TripleStore(settings.memory_dir)
        workspace_store = WorkspaceMemoryStore(settings.agent_workspace_dir)
        simulator = HomeSimulator.from_settings(settings)
        registry = AgentRegistry.from_config(
            settings.agents_config_path,
            workspace_store=workspace_store,
        )
        coordinator = MemoryCoordinator(
            graph_retriever=GraphRetriever(triple_store),
            workspace_store=workspace_store,
            primary_backend=backend,
        )
        central_nodes[backend] = CentralNode.build_default(
            simulator=simulator,
            agent_registry=registry,
            triple_store=triple_store,
            memory_coordinator=coordinator,
            compression_window=settings.compression_window,
        )

    report = MemoryBenchmarkRunner(central_nodes).run(
        [TaskRequest(description="Create a cool calm evening with soft light and music")]
    )

    assert len(report.records) == 3
    assert {summary.backend for summary in report.summaries} == {"none", "workspace_text", "kg_facts"}
