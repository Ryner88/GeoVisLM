# GeoVisLM Priority Tasks

Status labels:

* `[NEXT]` next task to start
* `[TODO]` not started
* `[TODO-BLOCKED]` not started until its explicit gate passes
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Current Priority Queue

### 1. `[NEXT]` Verify Current Production Deployment and Operations

Confirm on the live host that Prime runs current `main` and inspect the backup
timer's actual state and recent runs. The October 18 B2-only restore passed,
but its source commit was `90c089b`; it cannot prove deployment of the newer
repository changes. The runbook says scheduling must stay disabled until live
acceptance passes. Do not infer timer state from documentation.

Finish [issue #5](https://github.com/Ryner88/GeoVisLM/issues/5) acceptance by
checking operator alert receipt and retention deletion, then verify continuing
scheduled-backup success if the timer is enabled. Exercise upload quotas and
recovery under load for the completed issue #7 implementation. Record the
results here and in `STATUS.md` only after observing them.

### 2. `[TODO]` Establish the Data-Source and Licensing Register

Use `docs/DATA_SOURCES.md` to pin provider, product, version, geographic
coverage, access requirements, license, attribution, and quality limitations.
Confirm the exact terms for the first selected files before ingestion or
publication.

### 3. `[TODO]` Select First U.S. Exposure Inputs

Select a bare-earth USGS 3DEP DEM and a dated Geofabrik OSM buildings-and-roads
extract for a bounded test geography. Record download URLs, versions, metadata,
and checksums. Microsoft U.S. footprints are supplemental after local quality
and overlap review. OpenTopography is optional and is not a Phase 1 blocker.

### 4. `[TODO]` Establish Provider Security and Data Provenance

Apply `docs/SECRETS_AND_PROVIDER_SECURITY.md` and `docs/DATA_PRIVACY.md` to
approved source hosts, request bounds, credential storage, source records,
project access, retention, and outbound data flows. Later-provider credentials
are not required to prepare the first U.S. milestone.

### 5. `[TODO-BLOCKED]` Implement Phase 1 Evidence and Exposure Calculations

When Phase 1 is authorized, implement the versioned evidence schema, spatial
building/road exposure rules, and deterministic verification of report claims
using the selected inputs. This remains proposed AI work, not an active issue.

## Active Boundaries

* Production backup, isolated restore, evidence retention, and cleanup are
  `[DONE]`; see `docs/planning/FIXED_TASKS.md` and
  `docs/operations/evidence/production-drill-20260922/`.
* Issues #7, #8, and #9 are closed. Their completed work is existing
  infrastructure, not an open development dependency.
* The dashboard recommendation feature is implemented, but the current
  GeoMiniLM candidate is not production-approved.
* Phases 1–9 are `Proposed / Not Started` in `AI_ROADMAP.md`. Create issues or
  milestones when implementation is ready to begin.
* Do not tune against the frozen regression set or the retired 2026-08-28
  shadow set. A later formal decision requires a new sealed shadow set.
