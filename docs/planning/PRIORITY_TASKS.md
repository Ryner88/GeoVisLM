# GeoVisLM Priority Tasks

Status labels:

* `[NEXT]` next task to start
* `[TODO]` not started
* `[TODO-BLOCKED]` not started until its explicit gate passes
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Current Priority Queue

### 0. `[DONE]` Run GeoMiniLM Candidate `0bc44b0` Production Gate

Goal: evaluate candidate `0bc44b0` exactly once against the frozen production
validation set and record the deployment decision without tuning against the
frozen outcomes.

Result:

* Formal one-shot gate recorded in
  `docs/GEOMINILM_PRODUCTION_ACCEPTANCE_2026-08-11.md`.
* Manifest integrity and duplicate/leakage checks passed.
* Candidate score was `0.6475` versus required value `0.7600`.
* All-record, category-floor, threshold, and confidence gates failed.
* Deployment and dashboard integration remain blocked.
* Frozen validation outcomes must not be used for direct tuning.

### 1. `[DONE]` Review GeoMiniLM Development-Cycle Contract

Goal: lock the repaired GeoMiniLM development protocol before any new model
selection work begins. The August 8 production candidate failed, and the
14-record validation set is now a frozen regression benchmark, not a tuning set
or active production-evaluation target.

Build:

* Review and approve workflow-only primary scoring.
* Use grouped workflow-family holdouts for development model selection.
* Lock per-category score floors before evaluating any future candidate.
* Require every evaluated record to pass.
* Require semantic and executability checks for predicted workflows.
* Require route-aware confidence checks for retrieval and template predictions.
* Define sealed shadow-set authoring, custody, one-shot use, and retirement
  rules.
* Explicitly prohibit model or template tuning against
  `data/geominilm/validation_workflows.jsonl`.

Acceptance criteria:

* Development-cycle contract is reviewed and recorded.
* Workflow-only score, per-category floors, all-record pass requirement,
  semantic checks, executability checks, route-aware confidence requirements,
  and sealed shadow-set rules are locked before model selection resumes.
* The frozen 14-record validation set is used only for regression reporting and
  protocol migration diagnostics.
* No model, retrieval, template, or threshold tuning uses the frozen regression
  set.

Result:

* Reviewed and recorded in `docs/GEOMINILM_DEVELOPMENT_PERFORMANCE_CYCLE.md`
  on 2026-08-11.
* Grouped workflow-family development baseline ran on the 29 development
  records only.
* Development-supported fixes were limited to template routes and route-aware
  template confidence; the frozen 14-record validation set was not used for
  tuning.

### 2. `[TODO-BLOCKED]` Integrate GeoMiniLM Recommendations into the Dashboard

Goal: generate suggested workflows from uploaded data and present them for user
approval before execution.

Blocked until:

* The development-cycle contract is reviewed.
* A new training/development-only performance cycle produces a locked candidate
  under the repaired protocol.
* A future formal production gate passes on a new sealed shadow set.

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
