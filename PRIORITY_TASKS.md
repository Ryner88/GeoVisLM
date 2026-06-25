# GeoVisLM Priority Tasks

Status labels:

- `[TODO]` not started
- `[IN-PROGRESS]` actively being worked
- `[BLOCKED]` cannot move without another fix or decision
- `[DONE]` completed and ready to move into `FIXED_TASKS.md`

## Priority Queue

### 1. `[TODO]` Create GeoMiniLM Dataset Format

Goal: define the dataset format for the custom geospatial/scientific visualization LLM.

Build:

- dataset folder structure
- starter JSONL format
- prompt-to-workflow examples
- QGIS workflow examples
- ParaView workflow examples

Acceptance criteria:

- At least 10 starter examples exist.
- Each example has an instruction, inputs, expected workflow, and explanation.
- Format is documented.

Why priority: the custom LLM needs structured data before training.
