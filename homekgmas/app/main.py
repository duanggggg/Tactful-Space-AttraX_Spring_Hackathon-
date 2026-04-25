"""FastAPI entry point for the homekgmas multi-agent runtime."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.agent_registry import AgentRegistry
from app.api.routes_environment import build_environment_router
from app.api.routes_task import build_task_router
from app.core.config import AppSettings, get_settings
from app.core.logger import setup_logging
from app.environment.simulator import HomeSimulator
from app.llm.client import OpenAIChatCompletionsClient
from app.memory.coordinator import MemoryCoordinator
from app.memory.graph_retriever import GraphRetriever
from app.memory.triple_store import TripleStore
from app.memory.workspace_store import WorkspaceMemoryStore
from app.orchestrator.central_node import CentralNode
from app.planning.scheduler import InMemoryScheduler


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Application factory."""

    settings = settings or get_settings()
    settings.ensure_directories()
    setup_logging(settings.log_dir)

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
    scheduler = InMemoryScheduler()
    central_node = CentralNode.build_default(
        simulator=simulator,
        agent_registry=registry,
        triple_store=triple_store,
        memory_coordinator=memory_coordinator,
        compression_window=settings.compression_window,
    )

    app = FastAPI(title=settings.project_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )
    app.state.settings = settings
    app.state.central_node = central_node
    app.state.scheduler = scheduler
    app.include_router(build_task_router(central_node, scheduler), prefix=settings.api_prefix)
    app.include_router(build_environment_router(simulator), prefix=settings.api_prefix)

    @app.get("/")
    def index() -> dict[str, object]:
        return {
            "project": settings.project_name,
            "status": "ok",
            "message": "homekgmas API is running",
            "routes": {
                "health": "/health",
                "docs": "/docs",
                "openapi": "/openapi.json",
                "demo_task": f"{settings.api_prefix}/tasks/demo",
                "current_context": f"{settings.api_prefix}/tasks/context/current",
                "scheduled_tasks": f"{settings.api_prefix}/tasks/scheduled",
                "run_due_tasks": f"{settings.api_prefix}/tasks/scheduled/run-due",
            },
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "project": settings.project_name}

    return app


app = create_app()
