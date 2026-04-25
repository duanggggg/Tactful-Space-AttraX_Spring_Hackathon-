# Repository Agent Guide

This repository is a local-first smart-home multi-agent research prototype. The codebase serves two purposes at the same time:

- a runnable orchestration system for simulated smart-home control
- a research platform for datasets, evaluation, and memory/backend experiments

When editing the repository, keep both roles aligned.

## Current Project Reality

The source of truth is the code, not older planning text.

The current implementation already includes:

- one `CentralNode` orchestration hub
- local simulator-backed sensing and execution
- local structured memory persisted as JSON records, JSONL workspace notes, and triples
- built-in dialogue compression
- multiple agent domains, not only the original three-agent demo

The original core scenario is still centered on:

- `CoolingAgent`
- `LightingAgent`
- `MusicAgent`

But the current runtime also supports:

- `FanAgent`
- `CoverAgent`
- `LockAgent`
- `SwitchAgent`
- `ApplianceAgent`

Do not rewrite the repository as if it only supports three agents unless the user explicitly asks to remove the expanded domains.

## Core Goal

Build and maintain a smart-home intelligent butler that can:

1. accept user, scheduled, inferred, or automation-like tasks
2. read simulator state
3. build a structured discussion topic
4. wake relevant domain agents
5. retrieve local memory per agent
6. generate proposals
7. detect conflicts and compress discussion state
8. resolve proposals into a coordinated execution plan
9. execute actions in the simulator
10. persist structured outcomes for later retrieval and evaluation

## Architectural Guardrails

- Keep the system local-first.
- Keep memory file-based.
- Keep runtime modules typed, documented, and runnable.
- Preserve modular boundaries between orchestration, agents, environment, memory, discussion, and evaluation.
- Preserve explicit support for conflicting proposals and coordinated resolution.
- Keep simulator-backed execution as the default assumption.
- Keep runtime output inspectable on disk under `outputs/`.

## Infrastructure Constraints

- Do not add a database for the core MVP path.
- Do not add Redis, Neo4j, PostgreSQL, Celery, Kubernetes, or microservices.
- Do not replace local memory with external infrastructure.
- Do not make the system depend on cloud-only runtime services for its main loop.

Optional LLM usage is acceptable, but the system must remain able to run in rule-based local mode.

## Runtime Shape To Preserve

The main runtime path is:

- `app/main.py` wires settings, simulator, registry, memory, and `CentralNode`
- `app/orchestrator/central_node.py` runs the full task loop
- `app/orchestrator/wakeup_manager.py` selects participants
- `app/orchestrator/discussion_manager.py` runs proposal and revision rounds
- `app/discussion/conflict_detector.py` detects policy and action conflicts
- `app/discussion/action_resolver.py` builds the coordinated action set
- `app/environment/` provides embedded and remote simulator backends
- `app/memory/` persists and retrieves local memory artifacts

When changing these areas, preserve the end-to-end loop unless the task explicitly asks for a redesign.

## Research Surface To Preserve

This repository also includes:

- dataset warehouse building
- unified task/sample normalization
- offline evaluation
- runtime benchmarking
- memory backend comparisons

Changes to runtime request/response shapes, task schemas, agent names, action schemas, or output paths can affect evaluation scripts and generated datasets. Treat those interfaces carefully.

## Change Priorities

Prefer changes that:

- improve correctness of agent selection, proposal quality, conflict resolution, or execution safety
- improve local memory quality without adding infrastructure complexity
- keep simulator behavior and runtime outputs debuggable
- maintain compatibility with evaluation and dataset tooling
- reduce drift between docs and actual code

Avoid changes that:

- introduce aspirational abstractions with no current runtime value
- hide behavior behind opaque infrastructure
- break the local development loop
- erase research artifacts or compatibility layers without explicit approval

## Documentation Rule

Keep `README.md`, `AGENTS.md`, and code comments aligned with the current implementation.

In particular:

- do not describe the repository as a mere scaffold when a feature already runs end to end
- do not claim the runtime only supports three agents when the registry and catalogs support more
- do not document heavyweight infrastructure that does not exist
- be explicit about which parts are production-ready versus intentionally lightweight
