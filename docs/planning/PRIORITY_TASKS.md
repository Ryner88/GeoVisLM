# GeoVisLM Priority Tasks

Status labels:

* `[NEXT]` next task to start
* `[TODO]` not started
* `[TODO-BLOCKED]` not started until its explicit gate passes
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Current Priority Queue

### 1. `[NEXT]` Improve the New Analysis and Batch Upload Experience

Goal: make uploads and analysis setup clearer and more robust for larger
datasets and multi-file geospatial inputs.

Build:

* Support batch datasets and shapefile bundles.
* Improve validation feedback.
* Add upload progress.
* Define quotas.
* Document cleanup behavior for failed or abandoned uploads.

## Active Boundaries

* No task is currently `[IN-PROGRESS]`.
* The dashboard recommendation feature is implemented, but the current
  GeoMiniLM candidate is not production-approved.
* Do not tune against the frozen regression set or the retired 2026-08-28
  shadow set. A later formal decision requires a new sealed shadow set.
