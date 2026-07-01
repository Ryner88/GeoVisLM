# GeoVisLM Priority Tasks

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Current Priority Queue

### 1. `[TODO]` Add Flood Risk Workflow

Goal: combine DEM-derived terrain outputs, river proximity, slope, and optional building footprint overlays into a basic flood-risk analysis workflow.

Acceptance criteria:

- Workflow loads a DEM and at least one river or stream vector layer.
- River buffers are generated.
- DEM/slope-derived terrain risk is combined with river proximity.
- Flood-risk output is written to a run-scoped output folder.
- Output classes are documented.
- Workflow works without dashboard or PostGIS.
- README or workflow documentation explains input requirements and limitations.

### 2. `[TODO]` Add Wildfire Risk Workflow

Goal: combine slope, vegetation/fuel data, optional wind or sensor inputs, and proximity layers into a basic wildfire-risk analysis workflow.

Acceptance criteria:

- Workflow loads DEM and vegetation/fuel input.
- Slope is generated or reused from terrain workflow logic.
- Vegetation/fuel classes are normalized into stable risk inputs.
- Wildfire-risk output is written to disk.
- Output classes are documented.
- Workflow works without dashboard or PostGIS.
- README or workflow documentation explains input requirements and limitations.
