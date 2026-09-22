# GeoVisLM Project Status

Last reviewed: 2026-09-22

## Executive Summary

GeoVisLM's application and operational workflow are implemented and locally
healthy. Before this status-documentation update, `main` matched
`origin/main`; the full test suite passes with `82 passed`.

The GeoMiniLM recommendation feature is integrated into the dashboard behind
an explicit user-approval step. However, the current GeoMiniLM candidate is
not approved for production use: its latest sealed shadow-set gate failed.
Feature availability and model production approval are tracked separately.

## Current State

| Area | Status | Evidence / limitation |
| --- | --- | --- |
| Repository baseline | Healthy | `main` was synchronized with `origin/main` at `fee7bef` before this documentation update |
| Automated tests | Passing | `82 passed in 18.11s` on 2026-09-22 |
| Terrain workflow | Implemented | DEM upload, slope, hillshade, risk classification, maps, and reports |
| Flood and wildfire workflows | Implemented | Filesystem workflows and versioned dashboard templates |
| Dashboard operations | Implemented | Projects, runs, uploads, queue/worker, outputs, previews, and reports |
| Authentication and collaboration | Implemented | First-party auth, project sharing, audit events, and report comments |
| Workflow templates | Implemented | Versioned terrain, flood-risk, and wildfire-risk templates tracked per run |
| GeoMiniLM dashboard feature | Implemented with approval gate | Recommendations can be generated and must be explicitly approved before execution |
| GeoMiniLM production candidate | Blocked | Latest gate scored `0.4783`; required `0.7600`; 14/15 threshold failures |
| Prime deployment | Previously validated | Last documented production sign-off and collaboration deployment checks passed; live state was not revalidated in this status review |
| ParaView | Partial / environment-dependent | Entry point exists, but ParaView is not included in project requirements |

## Current Priority

`[NEXT]` Add production backup, restore, and retention validation.

This work must prove that both PostGIS data and retained output files can be
backed up and restored in isolation without modifying production state.

## GeoMiniLM Boundary

The August 28 one-shot shadow-set result is the current production decision:

- Candidate score: `0.4783`
- Required score: `0.7600`
- Threshold failures: `14/15`
- Expected calibration error: `0.8302`
- Decision: failed; candidate must not be promoted as production-approved

The retired shadow set and frozen regression set must not be used for tuning.
A future candidate requires a new development-only cycle and a different
sealed shadow set for its next formal production decision.

## Near-Term Backlog

1. Production backup, restore, and retention validation.
2. New analysis and batch-upload experience improvements.
3. Project timeline and collaboration notifications.
4. Demo video and portfolio page.
5. A new GeoMiniLM development cycle followed by a newly sealed production
   gate; this is not yet scheduled as active work.

## Verification Snapshot

Run on 2026-09-22:

```bash
timeout 300 .venv/bin/python -m pytest -q
```

Result: `82 passed in 18.11s`.
