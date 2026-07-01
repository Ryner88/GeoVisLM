# GeoVisLM Priority Tasks

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Current Priority Queue

### 1. `[DONE]` Add Artifact Preview and Download UX

Goal: make generated DEM, vector, and render outputs usable from the dashboard.

Acceptance criteria:

- Run detail page lists slope, hillshade, risk, summary JSON, clipped vectors, and overlay render outputs.
- PNG renders can be previewed in browser.
- GeoTIFF, GeoJSON, and JSON outputs can be downloaded.
- Output file metadata shows type, size, checksum, and generated stage.
- Access control applies to every output download route.

### 2. `[TODO]` Add Browser End-to-End Workflow Test

Goal: validate the manual dashboard path, not just API workflows.

Acceptance criteria:

- Test logs in through `/login`.
- Test creates a project through the browser form.
- Test uploads DEM/vector inputs through dashboard pages.
- Test queues a run.
- Test confirms outputs appear after worker execution.
- Test verifies logout blocks dashboard access again.
