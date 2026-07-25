# GeoVisLM Priority Tasks

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Current Priority Queue

### 1. `[TODO]` Investigate NumPy 2.5 MaskedArray Deprecation Warnings

Goal: keep the production test suite warning-clean and prevent a future NumPy
upgrade from turning current geospatial warnings into failures.

Why now: all 39 tests pass, but 19 NumPy 2.5 deprecation warnings recur in the
dashboard and risk-workflow tests. Dependency compatibility is the most
immediate maintenance risk in the otherwise healthy production baseline.

Acceptance criteria:

* Identify whether each warning originates in GeoVisLM code or a third-party
  geospatial dependency.
* Update GeoVisLM array handling when applicable.
* For dependency warnings, document the upstream source and a pin/upgrade plan.
* The suite runs without unexpected NumPy warnings, or narrowly scoped filters
  include a documented justification and removal condition.

Validation:

```bash
docker compose exec -T dashboard python -m pytest -q
```

### 2. `[TODO]` Train First GeoMiniLM Prototype

Goal: train or adapter-tune a small prototype that generates structured GIS and
visualization workflows from GeoMiniLM examples.

Why now: the operational GIS platform is stable, but the repository still lacks
the model prototype central to the GeoVisLM product direction. Start after the
evaluation schema and baseline are usable.

Build:

* Add dataset/preprocessing and training modules under `geovis_lm/model/`.
* Add `scripts/train_geominilm.py` using
  `data/geominilm/starter_workflows.jsonl`.
* Support a local-friendly model or adapter path, documented hardware limits,
  and a no-download dry run.
* Store models under `outputs/models/geominilm/` and predictions under
  `outputs/model_samples/`.
* Evaluate at least one generated prediction with the priority-2 evaluator.

Acceptance criteria:

* The loader reads and validates every starter JSONL example.
* Training CLI help and preprocessing dry run succeed.
* Model artifacts and reproducible configuration metadata are written.
* At least one inference produces a schema-valid structured workflow.
* An evaluation report records prototype quality and limitations.

Validation:

```bash
python3 -m py_compile geovis_lm/model/dataset.py
python3 scripts/train_geominilm.py --help
python3 scripts/train_geominilm.py --dataset data/geominilm/starter_workflows.jsonl --dry-run
```

### 3. `[TODO]` Install and Verify Host GDAL Tools

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

### 4. `[TODO]` Add Project Sharing and Report Comments

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
