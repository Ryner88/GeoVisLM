# GeoVisLM Priority Tasks

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Current Priority Queue

### 1. `[TODO]` Add Held-Out GeoMiniLM Evaluation

Goal: measure GeoMiniLM prototype generalization with held-out or leave-one-out
workflow evaluation instead of scoring only on the 12 training records.

Why now: the first prototype validates the end-to-end train/checkpoint/infer
contract, but the saturated `1.000` training-set score does not prove
generalization.

Acceptance criteria:

* Add a held-out split or leave-one-out evaluation mode for GeoMiniLM examples.
* Generate predictions for records excluded from each training fold.
* Compare held-out scores against the dry-run and training-set baselines.
* Document limitations from the tiny starter dataset.

Validation:

```bash
python3 scripts/train_geominilm.py --dataset data/geominilm/starter_workflows.jsonl
```

### 2. `[TODO]` Install and Verify Host GDAL Tools

Goal: make `gdalinfo` and `ogrinfo` available for host-level production
diagnostics in addition to the working containerized GIS stack.

Why now: Prime host access is available, so the former sudo blocker is removed.
The commands are currently absent from the host, which slows incident diagnosis
and independent inspection of retained or restored geospatial files.

Acceptance criteria:

* Install the supported `gdal-bin` package without changing container runtime
  dependencies.
* Record `gdalinfo` and `ogrinfo` versions.
* Inspect the sample DEM and an available sample vector dataset.
* Document host-versus-container GDAL usage and upgrade expectations.
* Re-run deployment and GIS workflow tests after installation.

Validation:

```bash
gdalinfo --version
ogrinfo --version
gdalinfo data/sample/sample_dem.tif
```

### 3. `[TODO]` Add Project Sharing and Report Comments

Goal: let owners invite collaborators to individual projects and discuss
generated reports without weakening current tenant isolation.

Why now: first-party accounts, roles, project ownership, and production account
policy are complete. Collaboration is the next high-value product capability,
but it must build on explicit project-level authorization and auditability.

Build:

* Project membership with owner-managed invitations and read-only collaborator
  access.
* Markdown report comment threads with author, timestamp, edit history, and
  resolved state.
* Activity/audit events for invitations, membership changes, comments, and
  moderation.
* Operator-safe handling for invitations when public signup remains disabled.

Acceptance criteria:

* Owners can invite an existing account to one project and revoke access.
* Collaborators can view only explicitly shared projects and cannot mutate
  owner-only resources.
* Authorized users can add comments; owners can resolve or delete them.
* Cross-project and cross-user access attempts remain denied without leaking
  resource existence.
* Authorization, invitation, comment, audit, and regression tests pass.
