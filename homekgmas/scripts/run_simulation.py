from pathlib import Path
import sys
import json

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.agent_registry import AgentRegistry
from app.api.schemas import TaskRequest
from app.core.config import build_settings
from app.environment.simulator import HomeSimulator
from app.llm.client import OpenAIChatCompletionsClient
from app.memory.coordinator import MemoryCoordinator
from app.memory.graph_retriever import GraphRetriever
from app.memory.triple_store import TripleStore
from app.memory.workspace_store import WorkspaceMemoryStore
from app.orchestrator.central_node import CentralNode


if __name__ == "__main__":
    settings = build_settings()
    llm_client = OpenAIChatCompletionsClient.from_settings(settings)
    triple_store = TripleStore(settings.memory_dir)
    workspace_store = WorkspaceMemoryStore(settings.agent_workspace_dir)
    simulator = HomeSimulator.from_settings(settings)
    registry = AgentRegistry.from_config(
        settings.agents_config_path,
        workspace_store=workspace_store,
        llm_client=llm_client,
        agent_mode=settings.agent_mode,
        agent_catalog_path=settings.agent_catalog_path,
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
    result = central_node.handle_task(
        TaskRequest(description="Create a cool, calm evening scene with soft light and gentle music")
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2))
