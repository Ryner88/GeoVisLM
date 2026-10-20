# Data Privacy Plan

Status: planning. Apply these requirements before adding external data
retrieval, run-specific chat, hosted models, or saved-area monitoring.

## Data inventory

| Data | Sensitivity and handling |
| --- | --- |
| Public DEMs, roads, building footprints, weather, gauges, and fire detections | Public source data still needs provenance, license, and update timestamps. Do not infer that a public layer makes a user's analysis area public. |
| User uploads, project locations, saved areas, reports, and map selections | Treat as user-controlled project data. Scope reads and exports to existing project permissions; minimize precision in operational logs. |
| Chat questions, model prompts, and generated answers | May reveal locations, assets, and intent. Keep attached to the correct project/run; disclose any external model processing before enabling it. |
| Credentials and provider tokens | Operational secrets. Never place in project data, reports, prompts, evidence records, or browser storage. |

## Data-flow rules

- Retrieve only the geographic extent and variables needed for a validated
  analysis. Bound extents and resolution before requesting data.
- Keep public provider requests separate from user identity. Do not send
  account names, private uploads, full reports, or chat transcripts to data
  providers unless that transfer is explicitly part of an approved feature.
- For hosted model calls, define which run evidence and user text may leave the
  application, provider retention and training settings, region, and deletion
  behavior before activation. Prefer the minimum evidence excerpt needed to
  answer the question.
- Keep immutable provenance for reproducibility, but avoid storing raw
  credential-bearing URLs or unnecessary personal data in evidence manifests.
- Apply project authorization to derived layers and exposure reports as well
  as raw uploads. Counts for small areas may reveal sensitive asset locations;
  review map detail and export permissions before sharing.
- Define retention and deletion for uploads, temporary downloads, cached
  provider data, prompts, reports, alerts, and logs before each feature ships.
  Ensure failed or cancelled jobs do not leave unowned temporary data.
- Log access and deletion events without logging payloads or secrets. Limit
  operator access to what recovery and support require.

## Phase gates

Phase 1 may use public 3DEP and OSM inputs with project-scoped outputs. The
later population slice must preserve Census vintage and estimation limits
without exposing individual-level claims. Run-specific chat needs project/run
authorization and a documented prompt-retention rule. Saved-area monitoring
needs user controls for schedule, notification destination, and deletion.
Hosted model providers require a separate data-flow review before any user
content is sent to them.
