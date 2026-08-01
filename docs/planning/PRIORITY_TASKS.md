# GeoVisLM Priority Tasks

Status labels:

* `[NEXT]` next task to start
* `[TODO]` not started
* `[TODO-BLOCKED]` not started until its explicit gate passes
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Current Priority Queue

### 1. `[NEXT]` Expand GeoMiniLM Production Evaluation

Goal: expand GeoMiniLM evaluation beyond the six-example frozen validation set
so model quality, confidence, and category coverage are credible enough to guide
product integration decisions.

Build:

* Increase the frozen validation set beyond six examples.
* Add more workflow categories.
* Record dataset version and checksum.
* Retain the honest same-set baseline.
* Add automated duplicate and training/validation leakage tests.
* Report confidence calibration and per-category results.
* Compare GeoMiniLM against the honest baseline on the expanded frozen set.

Acceptance criteria:

* Expanded, stratified validation set is frozen before tuning.
* Dataset version and checksum are recorded.
* Honest same-set baseline is retained.
* Automated duplicate and training/validation leakage tests pass.
* Confidence calibration and per-category results are reported.
* GeoMiniLM beats the honest baseline on the expanded frozen set.
* Full regression suite passes with reproducible results.

### 2. `[TODO-BLOCKED]` Integrate GeoMiniLM Recommendations into the Dashboard

Goal: generate suggested workflows from uploaded data and present them for user
approval before execution.

Blocked until:

* `Expand GeoMiniLM Production Evaluation` passes its acceptance gate.

Build when unblocked:

* Generate suggested workflows from uploaded datasets.
* Show confidence, parameters, and explanation.
* Require explicit user approval before executing a recommendation.

### 3. `[TODO]` Add GIS and ParaView Workflow Template Library

Goal: provide reusable, versioned workflow templates for common GIS and
visualization analyses.

Build:

* Add versioned analysis templates.
* Start with terrain, flood-risk, and wildfire-risk workflows.
* Track the template and template version that produced each run.
