# homekgmas

`homekgmas` is a local-first smart-home multi-agent research prototype. It combines a runnable orchestration service, a dynamic home simulator, local structured memory, and a data/evaluation pipeline for studying coordinated agent behavior.

The repository is no longer just a scaffold. The current codebase can already run an end-to-end task loop:

1. Accept a user or scheduled task.
2. Read simulated sensor, outdoor, and device state.
3. Build a structured discussion topic.
4. Wake the most relevant domain agents.
5. Retrieve local memory for each participating agent.
6. Generate proposals.
7. Detect conflicts and run one revision round when needed.
8. Build a coordinated execution plan.
9. Execute selected actions in the simulator.
10. Persist outcomes as JSON records, workspace notes, and triples.

## What The Project Contains

The repository has two closely related parts.

- A runtime smart-home orchestration system built around `CentralNode`, domain agents, local memory, and a simulator-backed environment.
- A research pipeline for dataset construction, offline evaluation, benchmarking, and memory ablations.

The default runtime mode is `fusion`, which uses dataset-derived agent catalogs and action spaces. The codebase also contains a `web` mode for normalized web-origin control data.

## Current Runtime Architecture

The main runtime path lives under `app/`:

- `app/main.py`: FastAPI application factory and dependency wiring.
- `app/orchestrator/`: task handling, wakeup selection, discussion, consensus, and planning.
- `app/agents/`: domain agents, personas, action catalogs, and registry bootstrap.
- `app/environment/`: embedded simulator, remote simulator client, and state models.
- `app/memory/`: triple-store memory, workspace memory, graph retrieval, and dialogue compression.
- `app/discussion/`: proposal protocol, conflict detection, and action resolution.
- `app/planning/`: action, plan, validation, and simple scheduling models.

At runtime, the orchestrator uses:

- a `CentralNode` as the coordination hub
- local file-based memory, not a database
- a simulator as the system of record for current home state
- typed proposal and plan objects throughout the loop

## Supported Agent Domains

The original demo scenario centers on cooling, lighting, and music. The current runtime has expanded beyond that and now supports these agent domains:

- `cooling_agent`
- `lighting_agent`
- `music_agent`
- `fan_agent`
- `cover_agent`
- `lock_agent`
- `switch_agent`
- `appliance_agent`

Each agent has:

- a persona and workspace profile
- an allowed device/action scope
- rule-based proposal logic
- optional structured LLM generation when `HOMEKG_LLM_ENABLED=true`

## Local-First Design Rules

These principles are reflected in the actual implementation:

- No database, Redis, Neo4j, Celery, Kubernetes, or microservices.
- Memory stays on disk as JSON records, JSONL workspace notes, and triples.
- The simulator can run embedded in-process or as a separate local service.
- Agent/action catalogs are modular so future backends can be swapped in.
- Conflict handling and dialogue compression are part of the default flow, not optional extras.

## Quickstart

Create a virtual environment and install dependencies:

Use Python 3.10+ if possible. Python 3.9 can work, but it relies on `eval_type_backport` for modern type-annotation parsing in Pydantic.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Start the orchestration API:

```bash
python scripts/run_server.py
```

Useful endpoints:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`
- `POST http://127.0.0.1:8000/api/v1/tasks/demo`
- `GET http://127.0.0.1:8000/api/v1/tasks/context/current`

Run tests:

```bash
pytest
```

## Configuration

Default runtime config lives in `configs/system.yaml`. Environment overrides are loaded from `.env` and shell variables.

Common variables:

- `HOMEKG_OUTPUT_DIR`
- `HOMEKG_LLM_ENABLED`
- `OPENAI_API_KEY`
- `OPENAI_API_BASE`
- `OPENAI_MODEL`
- `OPENAI_TIMEOUT_SECONDS`
- `HOMEKG_SIMULATOR_MODE`
- `HOMEKG_SIMULATOR_API_BASE`
- `HOMEKG_PRIMARY_MEMORY_BACKEND`
- `HOMEKG_AGENT_MODE`

Primary memory backend options:

- `triple_graph`
- `workspace_dual`
- `workspace_text`
- `kg_facts`
- `hybrid`
- `none`

Agent mode options:

- `fusion`
- `web`
- `generic`

## Dynamic Simulator

The simulator models:

- drifting outdoor weather, temperature, humidity, light, and wind
- indoor temperature, humidity, ambient light, and occupancy
- device state changes caused by accepted actions
- quiet-hours and time-of-day derived policy context

Run the standalone simulator service:

```bash
python scripts/run_simulator_server.py
```

The simulator service is served on `http://127.0.0.1:8011/` with:

- `GET /api/state`
- `POST /api/tick`
- `POST /api/reset`
- `POST /api/actions`

By default, the main app uses the embedded simulator. To read from the standalone simulator service instead:

```bash
export HOMEKG_SIMULATOR_MODE=remote
export HOMEKG_SIMULATOR_API_BASE=http://127.0.0.1:8011
python scripts/run_server.py
```

## Memory System

The runtime persists and compares multiple local memory forms:

- `TripleStore`: task records plus triple-like facts on disk
- `WorkspaceMemoryStore`: agent-local short-term and long-term notes
- `GraphRetriever`: lightweight graph-style fact extraction from recent records
- `DialogueCompressor`: structured compression of proposal history and open conflicts

Generated runtime artifacts are typically written under `outputs/`, including:

- `outputs/memory/records/*.json`
- `outputs/memory/triples.jsonl`
- `outputs/agent_workspaces/fusion/*/memory/short_term.jsonl`
- `outputs/agent_workspaces/fusion/*/memory/long_term.jsonl`
- `outputs/logs/`
- `outputs/reports/`

## Research And Evaluation Tooling

Beyond the runtime system, the repository includes a larger smart-home data pipeline.

### Dataset Warehouse

The warehouse pipeline normalizes multiple source datasets into a canonical episode format.

Key layers:

- `data_staging/`: source-aligned staging tables
- `data_processed/`: canonical dimensions, facts, bridges, and episodes
- `metadata/`: manifests and normalization metadata
- `reports/`: profiling and validation summaries

Main build command:

```bash
python scripts/build_unified_dataset.py
```

Important outputs:

- `metadata/source_manifest.parquet`
- `data_staging/*.parquet`
- `data_processed/dim_*.parquet`
- `data_processed/fact_*.parquet`
- `data_processed/bridge_*.parquet`
- `data_processed/synthetic_discussion.parquet`
- `data_processed/episodes.parquet`

### Offline Evaluation

The runtime can be evaluated against warehouse episodes and labeled actions.

Example commands:

```bash
python scripts/run_dataset_evaluation.py
python scripts/run_benchmark.py
python scripts/run_memory_benchmark.py
```

These scripts produce reports such as:

- `outputs/reports/benchmark_report.json`
- `outputs/reports/memory_benchmark_report.json`
- per-run dataset evaluation folders under `outputs/dataset_eval*/`

### API Dataset Collection

You can also collect datasets from live API runs:

```bash
HOMEKG_LLM_ENABLED=false python scripts/run_server.py
python scripts/run_simulator_server.py
python scripts/collect_api_dataset.py
```

This collects generated questions plus corresponding task results from:

- `GET http://127.0.0.1:8011/api/state`
- `POST http://127.0.0.1:8000/api/v1/tasks/demo`

## Development Notes

The codebase is typed, modular, and test-backed. A few components are still intentionally lightweight:

- `ExecutionPlanner` is currently a thin pass-through hook.
- Discussion currently supports an initial proposal pass plus one revision round.
- Retrieval is local and heuristic-first rather than heavyweight semantic search.
- The scheduler is in-memory and not yet persisted to disk.

Those limits are deliberate. The project is optimizing for a clean, inspectable local MVP and a research-friendly architecture rather than infrastructure complexity.
