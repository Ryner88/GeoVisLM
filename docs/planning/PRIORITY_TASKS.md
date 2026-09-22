# GeoVisLM Priority Tasks

Status labels:

* `[NEXT]` next task to start
* `[TODO]` not started
* `[TODO-BLOCKED]` not started until its explicit gate passes
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Current Priority Queue

### 1. `[NEXT]` Add Production Backup, Restore, and Retention Validation

Goal: prove production data can be recovered before additional collaboration
and AI-assisted workflow activity accumulate more state.

Build:

* Test PostGIS backup creation.
* Test output-volume backup creation.
* Perform an isolated restore drill covering both PostGIS and retained output
  files.
* Define retention and cleanup rules.
* Document restore steps, expected timing, and verification checks.

Acceptance criteria:

* Backup creation succeeds for PostGIS and retained output files.
* An isolated restore environment successfully restores both data stores.
* Restored database records and retained output files are verified end to end.
* Retention and cleanup rules are documented.
* Prime production state is not modified during the restore drill.

## Active Boundaries

* No task is currently `[IN-PROGRESS]`.
* The dashboard recommendation feature is implemented, but the current
  GeoMiniLM candidate is not production-approved.
* Do not tune against the frozen regression set or the retired 2026-08-28
  shadow set. A later formal decision requires a new sealed shadow set.
