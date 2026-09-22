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
| Prime deployment | Healthy | Backup/restore drill on 2026-09-22 ended with dashboard, worker, and PostGIS healthy and `/readyz` ready |
| Production recovery | Validated | PostGIS and 86 retained files restored in isolation; database, manifests, metadata links, and 36 API downloads verified |
| ParaView | Partial / environment-dependent | Entry point exists, but ParaView is not included in project requirements |

## Current Priority

`[NEXT]` Improve the new-analysis and batch-upload experience.

This work should improve multi-file datasets and shapefile bundles, validation
feedback, upload progress, quotas, and abandoned-upload cleanup behavior.

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

1. New analysis and batch-upload experience improvements.
2. Project timeline and collaboration notifications.
3. Demo video and portfolio page.
4. A new GeoMiniLM development cycle followed by a newly sealed production
   gate; this is not yet scheduled as active work.

## Latest Production Recovery Drill

The 2026-09-22 Prime drill passed. The retained backup set is
`/root/geovis-backups/production-drill-20260922T175546Z`. Total backup time was
`0.563 s`; isolated restore time was `10.612 s`. Database fingerprints, all 86
file manifests, 156 metadata references, and 36 API artifact downloads matched.
Production data and runtime fingerprints were unchanged. See
`docs/operations/BACKUP_RESTORE.md` for evidence, retention rules, and cleanup.

## Verification Snapshot

Run on 2026-09-22:

```bash
timeout 300 .venv/bin/python -m pytest -q
```

Result: `82 passed in 18.11s`.
