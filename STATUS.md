# GeoVisLM Project Status

Last reviewed: 2026-09-22

## Executive Summary

GeoVisLM's application and operational workflow are implemented and locally
healthy. Merged `main` at `57edeb9` passes the full `82`-test suite. Production
recovery is validated and its non-sensitive evidence is versioned in the
repository.

The GeoMiniLM recommendation feature is integrated into the dashboard behind
an explicit user-approval step. However, the current GeoMiniLM candidate is
not approved for production use: its latest sealed shadow-set gate failed.
Feature availability and model production approval are tracked separately.

## Current State

| Area | Status | Evidence / limitation |
| --- | --- | --- |
| Repository baseline | Healthy | Recovery PR #6 merged as `57edeb9`; month-end evidence follows in a focused PR |
| Automated tests | Passing | `82 passed in 16.11s` on merged `main`, 2026-09-22 |
| Terrain workflow | Implemented | DEM upload, slope, hillshade, risk classification, maps, and reports |
| Flood and wildfire workflows | Implemented | Filesystem workflows and versioned dashboard templates |
| Dashboard operations | Implemented | Projects, runs, uploads, queue/worker, outputs, previews, and reports |
| Authentication and collaboration | Implemented | First-party auth, project sharing, audit events, and report comments |
| Workflow templates | Implemented | Versioned terrain, flood-risk, and wildfire-risk templates tracked per run |
| GeoMiniLM dashboard feature | Implemented in repository; production deploy pending | Prime remains at `90c089b`, where recommendation routes return 404; deploy/revalidation tracked in issue #8 |
| GeoMiniLM production candidate | Blocked | Latest gate scored `0.4783`; required `0.7600`; 14/15 threshold failures |
| Prime deployment | Healthy but behind `main` | Live dashboard, worker, PostGIS, auth, sharing, comments, and upload/analysis/output passed on 2026-09-22; GeoMiniLM approval route is not deployed |
| Production recovery | Validated | PostGIS and 86 retained files restored in isolation; database, manifests, metadata links, and 36 API downloads verified |
| ParaView | Partial / environment-dependent | Entry point exists, but ParaView is not included in project requirements |

## Current Priority

`[NEXT]` Improve the new-analysis and batch-upload experience (GitHub issue
`#7`).

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

1. Encrypted off-host backup replication (`#5`, high-priority operations).
2. Deploy current `main` and revalidate the live approval boundary (`#8`,
   high-priority operations).
3. New analysis and batch-upload experience improvements (`#7`, next feature).
4. Project timeline and collaboration notifications (`#9`, backlog).
5. Demo video and portfolio package (`#10`, backlog).
6. A new GeoMiniLM development cycle followed by a newly sealed production
   gate; this is not yet scheduled as active work.

## Latest Production Recovery Drill

The 2026-09-22 Prime drill passed. The retained backup set is
`/root/geovis-backups/production-drill-20260922T175546Z`. Total backup time was
`0.563 s`; isolated restore time was `10.612 s`. Database fingerprints, all 86
file manifests, 156 metadata references, and 36 API artifact downloads matched.
Production data and runtime fingerprints were unchanged. See
`docs/operations/BACKUP_RESTORE.md` for retention and cleanup and
`docs/operations/evidence/production-drill-20260922/` for versioned evidence.

## Latest Live Deployment Validation

Prime was revalidated on 2026-09-22. Public dashboard availability, local
readiness, dashboard/worker/PostGIS health, first-party and bearer
authentication, project sharing, report comments, and a two-file
upload-to-worker-to-six-download workflow passed. Temporary validation records
were removed and logs contained no runtime errors.

Prime still runs `90c089b`; its recommendation endpoint returns 404. The
GeoMiniLM explicit-approval boundary is implemented on current `main` but must
be deployed and revalidated under issue `#8`. This deployment gap is distinct
from the failed model production gate: deploying the approval UI/API does not
approve the current model candidate.

## Verification Snapshot

Run on 2026-09-22:

```bash
timeout 300 .venv/bin/python -m pytest -q
```

Result: `82 passed in 16.11s` on merged revision `57edeb9`.
