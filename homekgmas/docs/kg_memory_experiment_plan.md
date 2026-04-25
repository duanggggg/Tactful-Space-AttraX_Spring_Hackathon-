# KG Memory Experiment Plan

## Goal

Establish whether graph-derived memory records provide a lower-cost and more effective agent initialization path than plain text workspace memory.

## Evaluation Contract

- Primary paper claim:
  - compare framework families, not different local model sizes
- Main framework comparison:
  - `rule_only`: handwritten control without learned memory
  - `llm_direct`: one model directly maps task plus sensors to actions
  - `agentic_no_memory`: multi-agent discussion without retrieved memory
  - `agentic_text_memory`: multi-agent discussion with text snippets
  - `agentic_kg_memory`: multi-agent discussion with graph facts
  - `agentic_hybrid_memory`: multi-agent discussion with graph facts plus text snippets
- Secondary ablation inside the agentic framework:
  - `none`: no retrieved memory
  - `workspace_text`: short-term and long-term text snippets only
  - `kg_facts`: compact graph-derived facts only
  - `hybrid`: graph facts plus text snippets
- Control the prompt budget:
  - compare memory backends under the same maximum prompt character budget
  - log retrieval latency separately from generation latency
  - for LLM-based frameworks, fix the same underlying model across all framework variants

## Open Datasets

### Dataset Group A: Smart-home ambient sensing

- CASAS Aruba:
  - use for room occupancy, activity transitions, and routine reconstruction
  - map event streams into tasks such as lighting, cooling, and quiet-hours decisions
- CASAS Kyoto or similar CASAS homes:
  - use as an additional house split for cross-home robustness
- ARAS:
  - use for multi-resident interaction and conflict-heavy cases

### Dataset Group B: Local sensor robustness

- OPPORTUNITY or PAMAP2:
  - use as auxiliary wearable or multimodal datasets to stress-test sensor fusion and missing-sensor recovery
  - not the main task dataset, but useful for validating sensor grounding and temporal robustness

## Task Construction

- Build task prompts from sensor windows:
  - thermal discomfort
  - low ambient light
  - calm evening scenes
  - quiet-hours music suppression
  - reading or focus scenes
- For each task window, store:
  - raw sensor slice
  - derived task description
  - target devices
  - expected policy constraints
  - expected action template

## Framework Baselines

- `rule_only`
  - current repo keyword or rule controller
  - no retrieved memory
  - no explicit discussion loop
- `llm_direct`
  - one LLM consumes current task, current sensors, and policy constraints
  - directly predicts final actions
  - no explicit agent specialization
- `agentic_no_memory`
  - current multi-agent discussion pipeline
  - no retrieved long-term memory
- `agentic_text_memory`
  - current multi-agent discussion pipeline
  - initialize agents from workspace text memory only
- `agentic_kg_memory`
  - current multi-agent discussion pipeline
  - initialize agents from graph-derived facts only
- `agentic_hybrid_memory`
  - current multi-agent discussion pipeline
  - initialize agents from both graph facts and text memory

## Model Control

- Do not treat model identity as the main experimental variable.
- For `llm_direct`, `agentic_no_memory`, `agentic_text_memory`, `agentic_kg_memory`, and `agentic_hybrid_memory`:
  - keep the same underlying model fixed
  - keep decoding settings fixed
  - keep prompt budget fixed where possible
- If multiple models are ever tried, present them only as a robustness appendix, not as the headline comparison.

## Local Sensor Acquisition And Validation

### Acquisition

- Keep the current simulator as the default reproducible source.
- Add a local adapter layer that can ingest:
  - Home Assistant REST snapshots
  - exported CSV or JSON event logs
  - manual spot-check measurements from a thermometer, lux meter, and sound meter

### Validation

- Validate simulator-to-local alignment on:
  - temperature
  - humidity
  - illuminance proxy
  - occupancy state
  - quiet-hours status
- For each locally captured session:
  - log synchronized timestamps
  - compare local sensor values with simulator-derived state
  - flag drift, missing data, and impossible transitions

## Metrics

### Memory Efficiency

- retrieval latency in milliseconds
- prompt characters or tokens used for initialization
- retrieved fact count
- retrieved snippet count

### Decision Quality

- action precision against annotated target actions
- action recall against annotated target actions
- exact-plan match
- task success judged by annotated goal satisfaction
- device-policy violation rate
- conflict rate
- rounds-to-consensus
- execution success rate

### Robustness

- performance under missing sensor channels
- performance under noisy occupancy signals
- cross-home generalization
- quiet-hours compliance

## Recommended Implementation Order

1. Finish graph-derived prompt context and memory benchmark logging.
2. Add framework-level runners for `rule_only` and `llm_direct`.
3. Build a task-construction pipeline from simulator state and one open dataset.
4. Add local sensor adapter and validation reports.
5. Run the framework comparison with the same model held fixed across all LLM-based variants.
