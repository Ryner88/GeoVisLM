# GeoVisLM AI Development Roadmap

## Status: Proposed / Not Started

Phases 1–9 are proposed development initiatives, not existing GitHub issues or
committed dates. Phase 0 is a set of live verification checks before new AI
implementation. Create issues or milestones for the AI phases only when work
is ready to begin. Keep repository completion and operational verification
separate.

## Phase 0 — Verify the production foundation

Check the live system and record dated evidence:

- Confirm Prime runs the intended current `main` commit. The October 18 B2
  recovery drill passed, but its backup source was `90c089b`, so it cannot
  prove that later changes were deployed.
- Inspect the backup timer state and recent service runs on Prime. The runbook
  requires scheduling to remain disabled until all live acceptance tests pass;
  repository documents do not establish that the timer has been enabled.
- Complete issue #5's remaining alert-receipt and retention-deletion checks.
  Once scheduling is enabled, verify continuing backup success and failure
  notification.
- Exercise upload quotas, batch recovery, and cleanup under realistic load.

Existing repository work: issues [#7](https://github.com/Ryner88/GeoVisLM/issues/7),
[#8](https://github.com/Ryner88/GeoVisLM/issues/8), and
[#9](https://github.com/Ryner88/GeoVisLM/issues/9) are closed; upload recovery
merged as [PR #16](https://github.com/Ryner88/GeoVisLM/pull/16), and timeline
and notifications as [PR #17](https://github.com/Ryner88/GeoVisLM/pull/17).
Backup PR #12 was reverted by #13; the current implementation was reapplied
and fixed through PRs #14 and #15. [Issue #5](https://github.com/Ryner88/GeoVisLM/issues/5)
remains open for operational acceptance. None of these closed issues is an
open AI development blocker.

## Phase 1 — Evidence-grounded analysis and exposure

- Freeze independent validation geographies before development and keep them
  out of tuning.
- Define a versioned evidence schema with inputs, provenance, data versions,
  coordinate reference systems, processing steps, and uncertainty.
- Calculate exposed buildings and road segments against risk rasters using
  explicit spatial rules and reproducible counts and lengths.
- Generate reports from evidence references and reject unsupported numerical
  claims.
- Check DEM quality and state limitations in the report.

First deliverable: given a risk raster, produce building and road exposure
metrics and a human-readable report whose quantitative claims are verified
deterministically against recorded evidence.

## Phase 2 — Natural-language GIS workflows and text chat

- Convert user requests into validated GIS workflows; resolve ambiguous
  locations and enforce geographic and resource limits.
- Retrieve DEM data and derive drainage networks where appropriate.
- Answer text follow-up questions using the completed run's recorded evidence.
- Add Census population exposure estimates with source and vintage recorded.

## Phase 3 — Link run-specific chat to the map

- Let answers point to the relevant map layers, features, and evidence records.
- Keep the selected run and map extent explicit so references cannot drift to
  another analysis.
- Make map interactions accessible and preserve the evidence behind each
  highlighted finding.

The text question-answering capability is defined in Phase 2. This phase adds
the map connection.

## Phase 4 — Scientific validation and calibration

- Compare flood outputs with independent flood observations and wildfire
  outputs with suitable historical fire data.
- Calibrate hazard thresholds only on development data.
- Evaluate against frozen geographic and temporal holdouts.
- Report precision, recall, spatial overlap, and uncertainty separately from
  workflow-execution correctness.

## Phase 5 — Live environmental data and scenarios

- Incorporate NASA FIRMS active-fire detections, NOAA weather information, and
  USGS river-gauge data with timestamps and provenance.
- Support scenario questions about changing river levels and wind conditions,
  with assumptions clearly recorded.

## Phase 6 — Imagery-derived evidence

- Evaluate satellite imagery as a source of regional land-cover, vegetation,
  burn-scar, or surface-condition evidence for flood and wildfire workflows.
- Record imagery source, acquisition time, resolution, cloud quality, model or
  algorithm version, and uncertainty.
- Match the claimed feature scale to source resolution. Sentinel-2's 10 m
  bands cannot resolve individual buildings; building-level extraction
  requires suitable higher-resolution imagery or authoritative footprint data.
- Before imagery-derived features affect flood or wildfire results, rerun the
  Phase 4 validation against its frozen holdouts and report the change in
  performance and uncertainty. Do not use the new evidence in decision reports
  until that revalidation passes.

## Phase 7 — Saved-area monitoring and notifications

- Add saved areas, scheduled analyses, change detection, and operator or user
  notifications using the existing collaboration-notification foundation.
- Record source timestamps, analysis versions, alert thresholds, delivery
  outcomes, and missed-run handling.

## Phase 8 — GeoMiniLM training and model infrastructure

- Investigate why the keyword-template router handles all evaluated
  predictions.
- Generate validated GIS workflow training examples and fine-tune a small
  open-weight model.
- Support local Ollama and hosted model providers.
- Compare the learned model with the keyword-template baseline. Require sealed
  evaluation and explicit approval before production promotion. The current
  GeoMiniLM candidate has not passed that gate.

## Phase 9 — AI cartography and scientific visualization

- Recommend color ramps, legends, and classification schemes.
- Generate map captions and accessibility descriptions.
- Use vision-assisted review to detect unreadable or misleading maps.
- Generate and safely validate ParaView Python scripts for reproducible 3D
  terrain visualizations.

## Cross-cutting definition of done

| Requirement | Applies to each relevant phase |
| --- | --- |
| Evidence | Record input versions, provenance, spatial reference, processing version, and reproducible outputs. |
| Claims | Check quantitative statements against computed evidence; show uncertainty and limitations. |
| Validation | Keep development data apart from frozen geographic and temporal holdouts; rerun validation when workflow inputs or hazard logic change. |
| Safety | Validate generated workflows and scripts, enforce resource limits, and preserve human approval for consequential actions. |
| Operations | Verify live deployment, scheduling, alerts, and recovery on the host before reporting them as working. |
| Accessibility | Provide readable maps, legends, captions, and nonvisual descriptions. |

## Numbering and planning rule

The former discussion labels Phase 2.5 and Phase 4.5 are Phases 3 and 6 here.
Scientific validation moves from 3 to 4; live data and scenarios move from 4
to 5. Monitoring is its own Phase 7. Model training moves to 8, and cartography
to 9. This preserves stable integer references for future tasks and issues.
Phase 1 is the first AI development priority after Phase 0 checks are
recorded. Later sequencing is proposed and may change based on validation.
