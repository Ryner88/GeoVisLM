# GeoVisLM Fixed Tasks

Completed tasks should be moved here from `docs/planning/PRIORITY_TASKS.md`.

Status labels:

- `[DONE]` completed and ready for recordkeeping

## Completed Work

### `[DONE]` Add Held-Out GeoMiniLM Evaluation

Implemented:

- Added leave-one-out GeoMiniLM evaluation with `--held-out-eval`.
- Trained each fold checkpoint without the evaluated example.
- Reloaded each fold checkpoint for inference before generating predictions.
- Reported held-out score, dry-run baseline score, delta, and per-example
  failures.
- Wrote held-out predictions, fold checkpoints, evaluation reports, and
  baseline comparison artifacts under the existing output locations.
- Added focused tests proving held-out examples are excluded from fold training
  and that failed examples are surfaced.

Verified:

- `python3 -m py_compile geovis_lm/model/prototype.py scripts/train_geominilm.py`
- `python3 scripts/train_geominilm.py --dataset data/geominilm/starter_workflows.jsonl --held-out-eval`
- `timeout 120 .venv/bin/python -m pytest tests/test_geominilm_prototype.py tests/test_train_geominilm_cli.py -vv` (`7 passed`)
- `timeout 300 .venv/bin/python -m pytest -q` (`64 passed`)

Findings:

- Training-set score: `1.0000`
- Held-out score: `0.4943`
- Failed examples: `12/12`
- Conclusion: the nearest-neighbor prototype memorizes the starter dataset and
  does not yet generalize.
- The `1.0000` dry-run baseline derives predictions from expected outputs, so
  it is an oracle/sanity baseline, not an honest generalization benchmark.

### `[DONE]` Train First GeoMiniLM Prototype

Implemented:

- Added a deterministic local GeoMiniLM prototype that trains on the 12
  validated starter workflows using a TF-IDF nearest-neighbor checkpoint.
- Saved reproducible checkpoint and metadata artifacts under
  `outputs/models/geominilm/`.
- Loaded the checkpoint for inference and generated schema-valid predictions
  under `outputs/model_samples/`.
- Evaluated trained predictions with the existing GeoMiniLM evaluation suite.
- Compared trained results against the dry-run baseline.
- Added focused tests for checkpoint save/load, inference, schema validation,
  CLI training, and baseline comparison.

Verified:

- `python3 -m py_compile geovis_lm/model/dataset.py geovis_lm/model/prototype.py scripts/train_geominilm.py`
- `python3 scripts/train_geominilm.py --dataset data/geominilm/starter_workflows.jsonl --dry-run`
- `python3 scripts/train_geominilm.py --dataset data/geominilm/starter_workflows.jsonl`
- `timeout 300 .venv/bin/python -m pytest -q` (`62 passed`)

Notes:

- The `1.000` trained result is an end-to-end validation over the same 12
  workflows used for training, not evidence of generalization.
- Held-out or leave-one-out evaluation is tracked as a separate follow-up in
  `docs/planning/PRIORITY_TASKS.md`.

### `[DONE]` Add Model Evaluation Suite

Implemented:

- Added `geovis_lm/eval/workflow_eval.py` for deterministic GeoMiniLM workflow prediction scoring.
- Added `scripts/evaluate_geominilm.py` to validate expected and predicted JSONL files and write JSON/Markdown reports.
- Added `outputs/eval/` as the generated report location.
- Documented the scoring rubric, pass threshold, CLI usage, and known limitations in `docs/GEOMINILM_EVALUATION.md`.
- Added unit tests for valid, malformed, incomplete, and mismatched prediction records.

Verified:

- `python3 -m py_compile geovis_lm/eval/workflow_eval.py`
- `python3 scripts/evaluate_geominilm.py --help`
- `timeout 120 .venv/bin/python -m pytest tests/test_workflow_eval.py -vv`
- `timeout 120 .venv/bin/python scripts/evaluate_geominilm.py --expected data/geominilm/starter_workflows.jsonl --predictions data/geominilm/starter_workflows.jsonl --output-dir outputs/eval`

Final local verification on `2026-07-25`:

- `timeout 120 .venv/bin/python -m py_compile geovis_lm/eval/workflow_eval.py scripts/evaluate_geominilm.py`
- `timeout 120 .venv/bin/python scripts/evaluate_geominilm.py --help`
- `timeout 120 .venv/bin/python -m pytest tests/test_workflow_eval.py -vv` (`6 passed`)
- `timeout 120 .venv/bin/python scripts/evaluate_geominilm.py --expected data/geominilm/starter_workflows.jsonl --predictions data/geominilm/starter_workflows.jsonl --output-dir outputs/eval --fail-on-threshold` (`PASS`, summary score `1.000`, `12/12` records)

### `[DONE]` Clean Up Local Validation Warnings

Implemented in commit `4f457c2`:

- Removed local validation warning noise without hiding unrelated future warnings.
- Preserved the narrow rasterio/NumPy dependency-boundary warning handling.
- Kept the patch unchanged when Docker Desktop failed during image unpack,
  because the failure was traced to host infrastructure, not application code.

Verified:

- `timeout 300 .venv/bin/python -m pytest -q -W default` (`48 passed`)
- `timeout 240 .venv/bin/python -W default scripts/local_operational_smoke.py`
- `python3 scripts/validate_docker_deployment.py`
- Docker Compose runtime smoke passed on `2026-07-25` after Docker Desktop host
  disk space was recovered:
  - `docker compose --env-file /tmp/geovis-compose-test.env config`
  - `docker compose --env-file /tmp/geovis-compose-test.env up --build -d`
  - `docker compose --env-file /tmp/geovis-compose-test.env exec -T dashboard python scripts/init_postgis.py --dry-run`
  - `docker compose --env-file /tmp/geovis-compose-test.env exec -T dashboard python scripts/compose_worker_smoke.py --token local-compose-token`

Notes:

- Docker Desktop originally failed with corrupted/incomplete layer symptoms and
  later `input/output error`/`EOF` during final image unpack while the Windows
  host drive was full.
- The same Compose path passed after freeing space and restarting Docker
  Desktop, confirming the blocker was image-store infrastructure rather than an
  application regression.

### `[DONE]` Trace NumPy 2.5 Raster Read Warnings

Implemented:

- Reproduced the NumPy `2.5.0` deprecation warnings in the dashboard operational suite.
- Traced the source to rasterio `1.5.0` raster read calls, not GeoVisLM's own NumPy array transformations.
- Added a shared `read_masked_band()` helper for GeoVisLM raster reads.
- Applied a narrow, message-specific `DeprecationWarning` filter only around rasterio `read()` and `read_masks()` calls.
- Updated DEM loading and overlay preview rendering to use the shared helper.
- Added regression coverage that promotes `DeprecationWarning` to errors around `load_dem()`.

Decision:

- Keep `numpy==2.5.0`.
- Keep `rasterio==1.5.0`; `pip index versions rasterio` reports it as the latest available release in this environment.
- Do not add a global pytest warning filter. The filter belongs at the known dependency boundary so unrelated NumPy deprecations remain visible.

Verified:

- `timeout 120 .venv/bin/python -m pytest tests/test_dashboard_operational.py::test_load_dem_avoids_numpy_masked_shape_deprecation -W error::DeprecationWarning -vv`
- `timeout 300 .venv/bin/python -m pytest -W always -vv`

Notes:

- Failure trace before the fix pointed from `geovis_lm/gis/terrain.py` into `rasterio/_io.pyx`, then NumPy's `numpy/ma/core.py:3505`.
- Both `src.read(1, masked=False)` and `src.read_masks(1)` trigger the same rasterio/NumPy warning under NumPy `2.5.0`, so replacing GeoVisLM masked-array construction alone was not sufficient.

### `[DONE]` Retire Former GeoVis Deployment

Retired the former GeoVis runtime on the old VPS on `2026-07-14` UTC after the
Prime observation, production-account, public-path, redeploy-persistence, and
backup/restore checks completed.

Implemented:

- Removed the former GeoVis containers from the old VPS.
- Removed the old GeoVis Caddy route so the former host no longer serves the
  production hostname.
- Preserved the former PostGIS and output volumes for rollback during the
  remaining retention period.
- Left unrelated services hosted on the old VPS active and unchanged.

Verified:

- Prime remains the active public GeoVis deployment.
- The former runtime and proxy route are no longer active.
- Rollback data remains available without keeping the retired application
  exposed or running.

### `[DONE]` Finalize Prime Account Policy and Production Sign-Off

Formal production sign-off was recorded on `2026-07-13` UTC after the Prime
service remained ready through the observation period that began with public
validation on `2026-07-11` UTC.

Implemented:

- Closed-by-default production signup policy with no standing invite code.
- Offline account provisioning, password reset, activation, and deactivation
  through `scripts/manage_users.py` without opening public signup.
- Least-privilege role guidance, recovery verification, session-secret rotation,
  audit-note requirements, and quarterly access reviews.
- Immediate rejection of an existing first-party session after its account is deactivated.

Verified:

- First-party production owner login/logout, invalid-password rejection, and
  Secure/HttpOnly session handling had already passed through Cloudflare.
- Public readiness reports storage, database mode, and required authentication ready.
- Dashboard, worker, and PostGIS services are healthy after Compose recreation.
- The available 48-hour service log window contains no traceback or runtime error.
- The reconciled account-policy and Compose v2 image passes all 39 tests.
- Two live redeploys preserved the PostGIS cluster and left all services healthy.
- A fresh public worker run completed with six outputs.
- PostGIS, output-volume, and restricted configuration backups were created,
  restored into isolated targets, and verified by object/content comparison.
- Cloudflare served the public domain and all 20 tagged public probes appeared
  in Prime logs.

The former deployment was subsequently retired as recorded above.

### `[DONE]` Harden Container Recreates and Complete Compose v2 Migration

Removed the legacy Compose recreate failure path and completed the production
migration to Docker Compose v2 on the Prime VPS.

Implemented:

- `deploy_main.sh` defaults to the currently checked-out branch, with `main` as
  the detached-HEAD fallback, instead of requiring the removed `appAuth` branch.
- `deploy_runbook.sh` requires Docker Compose v2 and rejects legacy
  `docker-compose` v1 instead of retaining its `ContainerConfig` failure path.
- PostGIS is managed through Compose v2 with its existing
  `geovis_lm_geovis_postgis` volume; the direct-`docker run` workaround was
  removed.
- Deploys start and wait for PostGIS, then force-recreate only `dashboard` and
  `worker`, waiting for both health checks.
- `scripts/verify_compose_redeploy.sh` exercises repeated redeploys, rejects any
  `ContainerConfig` traceback, checks all services and public endpoints, and
  compares the PostgreSQL cluster identifier to prove volume persistence.
- The Prime runbook documents Compose v2 as the only supported runner, manual
  stale-container recovery, and rollback rules that preserve named volumes.

Verified:

- Both deployment scripts pass Bash syntax validation.
- The repository passes `git diff --check`.
- `docker compose config --quiet` and
  `python3 scripts/validate_docker_deployment.py --compose-config` succeed.
- On `2026-07-14`, two consecutive live Compose v2 redeploys completed without
  `ContainerConfig`; dashboard, worker, and PostGIS were healthy after each.
- Local and public readiness and public login checks passed after both redeploys.
- The PostgreSQL cluster identifier was unchanged across both redeploys.
- The deployment-security tests pass (`7 passed`) and the full containerized
  suite passes (`37 passed`).
- The authenticated public worker smoke run completed with six registered
  outputs after the repeated redeploys.

### `[DONE]` Deployment Security Hardening

Finished the deployment security hardening work and validated it against the live VPS deployment.

Implemented:

- Compose now requires `GEOVIS_AUTH_TOKEN` when auth is enabled.
- Compose now requires a GeoVis-specific `POSTGRES_PASSWORD` for the `geovis` database role.
- HTTPS session cookies default to secure mode with `GEOVIS_SESSION_COOKIE_SECURE=true`.
- Docker deployment validation checks for required auth and database secret wiring.
- Docker validation subprocess execution is constrained to trusted Docker executable paths.
- VPS deployment helpers generate missing `GEOVIS_AUTH_TOKEN` and `POSTGRES_PASSWORD` values instead of relying on defaults.

Verified:

- Public `/readyz` reports `auth_required=true` and `auth_configured=true`.
- Public login renders the first-party auth UI.
- The PostGIS `geovis` role password was rotated to the current `.env` secret.
- Dashboard and worker containers were restarted after secret rotation.
- The legacy Compose v1 recreate risk was subsequently eliminated by the
  Compose v2 migration recorded above.

### `[DONE]` Add First-Party Login and Signup for GeoVis LM

Implemented first-party authentication for the FastAPI dashboard while keeping bearer-token API authentication available for service clients.

Implemented:

- File-backed first-party users with normalized email addresses, Argon2 password hashes, display names, roles, active flags, and activation metadata.
- A `geovis_users` PostGIS schema table for database-backed deployments.
- `/signup`, `/login`, `/logout`, `/api/auth/signup`, `/api/auth/login`, and `/api/auth/me`.
- Signed HTTP-only session cookies using `GEOVIS_SESSION_SECRET` with `GEOVIS_SECRET_KEY` and `GEOVIS_AUTH_TOKEN` fallback compatibility.
- `GEOVIS_SIGNUP_ENABLED` and `GEOVIS_SIGNUP_INVITE_CODE` controls.
- Tests for signup, invite-code gating, login, logout, protected routes, and per-user project isolation.
- README and deployment/storage docs updates for auth settings and session-secret rotation guidance.

Verified:

- A user can sign up when signup is enabled.
- Signup can be restricted by invite code.
- A user can log in and log out successfully.
- Dashboard and API routes are protected for unauthenticated users.
- Runs, uploads, and outputs are associated with the logged-in user.
- Users cannot access another user’s outputs or runs.
- Passwords are securely hashed and not exposed.

### `[DONE]` Add Flood Risk Workflow

Implemented:

- Filesystem-first flood-risk workflow combining DEM-derived low elevation, flat terrain, and river-buffer proximity into `flood_risk.tif`.
- River buffers generated as `river_buffers.geojson`.
- JSON summary with output classes, model weights, inputs, outputs, and limitations.
- Dashboard adapter support for `workflow_type=flood_risk` while keeping the workflow runnable from `scripts/run_flood_risk.py`.
- Input requirements, output classes, and limitations in `docs/RISK_WORKFLOWS.md`.

Verified:

- Workflow loads a DEM and river or stream vector layer.
- River buffers are generated.
- DEM/slope-derived terrain risk is combined with river proximity.
- Flood-risk output is written to a run-scoped output folder.
- Workflow works without dashboard or PostGIS.

### `[DONE]` Add Wildfire Risk Workflow

Implemented:

- Filesystem-first wildfire-risk workflow combining DEM-derived slope, normalized vegetation/fuel inputs, and optional proximity vectors into `wildfire_risk.tif`.
- Numeric and common text fuel classes normalized into stable low, moderate, and high risk inputs.
- Fuel rasters reprojected to the DEM grid.
- JSON summary with output classes, normalized fuel metadata, inputs, outputs, and limitations.
- Dashboard adapter support for `workflow_type=wildfire_risk` while keeping the workflow runnable from `scripts/run_wildfire_risk.py`.
- Input requirements, output classes, and limitations in `docs/RISK_WORKFLOWS.md`.

Verified:

- Workflow loads DEM and vegetation/fuel input.
- Slope is generated or reused from terrain workflow logic.
- Vegetation/fuel classes are normalized into stable risk inputs.
- Wildfire-risk output is written to disk.
- Workflow works without dashboard or PostGIS.

### `[DONE]` Initial GeoVisLM Project Scaffold

Completed in commit:

`5d80b8d Initial GeoVisLM project scaffold`

Implemented:

- Repo scaffold and package structure
- Python virtual environment with GIS and early LLM stack
- `requirements.txt`
- README and `.gitignore`
- Terrain pipeline in `geovis_lm/gis/terrain.py`
- CLI in `scripts/run_terrain_analysis.py`
- Sample DEM at `data/sample/sample_dem.tif`

Verified:

- GeoVisLM GIS stack imports successfully
- GeoVisLM LLM stack imports successfully
- `pip check` reports no broken requirements
- Terrain pipeline generated:
  - `outputs/maps/slope_degrees.tif`
  - `outputs/maps/hillshade.tif`
  - `outputs/maps/terrain_risk.tif`
- CLI help displays successfully
- Git status is clean

Notes:

- System `gdalinfo` and `ogrinfo` are not installed yet because `sudo apt update` requires an interactive password.
- This is not blocking the MVP because Rasterio/GeoPandas pipeline validation succeeded.

### `[DONE]` Add UML Diagrams and Exported Images

Implemented:

- System architecture PlantUML diagram
- Component diagram
- Terrain pipeline sequence diagram
- GeoMiniLM workflow diagram
- Exported PNG images under `docs/diagrams/images/`
- UML documentation in `docs/UML_DIAGRAMS.md`
- README link to `docs/UML_DIAGRAMS.md`

Verified:

- `.puml` files exist under `docs/diagrams/plantuml/`
- exported images exist under `docs/diagrams/images/`
- `docs/UML_DIAGRAMS.md` references every diagram
- README links to the UML documentation

### `[DONE]` Add QGIS Workflow Documentation

Implemented:

- QGIS import steps
- Recommended layer order
- Slope layer styling guide
- Hillshade layer styling guide
- Terrain risk layer styling guide
- Map export instructions
- Screenshot/export placeholder locations under `docs/qgis/`
- README link to `docs/QGIS_WORKFLOW.md`

Verified:

- Documentation explains how to open `slope_degrees.tif`, `hillshade.tif`, and `terrain_risk.tif` in QGIS.
- Documentation explains layer order and styling.
- README links to the QGIS workflow document.

### `[DONE]` Add ParaView Terrain Visualization Script

Implemented:

- ParaView-compatible terrain rendering script at `geovis_lm/viz/paraview_terrain.py`
- Documented DEM input expectation and render outputs
- Default outputs under `outputs/renders/`
- `pvpython` execution path with lazy ParaView imports
- README usage notes and current ParaView/GDAL reader limitation

Verified:

- Script compiles with the project Python interpreter.
- README documents how ParaView will be used.

Notes:

- ParaView is not installed through `requirements.txt`; run the script with a local ParaView `pvpython` install.
- GeoTIFF input support depends on ParaView being built with GDAL raster reader support.

### `[DONE]` Create GeoMiniLM Dataset Format

Implemented:

- Dataset folder under `data/geominilm/`
- JSONL schema and authoring rules in `data/geominilm/README.md`
- Starter workflow dataset in `data/geominilm/starter_workflows.jsonl`
- GIS terrain analysis examples
- QGIS styling and export examples
- ParaView rendering and GUI refinement examples
- Reporting and dataset-authoring examples
- README link to the GeoMiniLM dataset folder

Verified:

- Starter dataset has 12 JSONL examples.
- Every example includes `instruction`, `inputs`, `expected_workflow`, and `explanation`.
- Every workflow step includes `step`, `action`, `tool`, and `output`.

### `[DONE]` Add Report Generator

Implemented:

- Report package under `geovis_lm/reports/`
- Terrain report generator at `geovis_lm/reports/terrain_report.py`
- CLI entry point at `scripts/generate_report.py`
- Markdown reports with input data, generated outputs, terrain summary, visualization outputs, reproducibility commands, limitations, and next steps
- Optional PDF report generation through `reportlab`
- Automatic creation of `outputs/reports/`
- README usage instructions

Verified:

- `python3 -m py_compile geovis_lm/reports/terrain_report.py`
- `python3 scripts/generate_report.py --help`
- Markdown report generation from sample terrain outputs
- PDF report request exits with a clear missing-`reportlab` message in this environment

Notes:

- Markdown generation does not require QGIS, ParaView, or GDAL command-line tools.
- PDF generation requires optional `reportlab`; the CLI exits with a clear message when it is missing.

### `[DONE]` Add Web Dashboard

Implemented:

- Dashboard package under `geovis_lm/dashboard/`
- FastAPI app at `geovis_lm/dashboard/app.py`
- Run creation endpoint
- Raw-byte DEM upload endpoint
- Sample DEM helper endpoint for local demos
- Terrain analysis endpoint that writes run-scoped map outputs
- Report generation endpoint using the terrain report generator
- Output listing endpoint
- Static serving for generated files under `/outputs`
- Run folders under `outputs/runs/<run_id>/`
- README usage instructions

Verified:

- `python3 -m py_compile geovis_lm/dashboard/app.py`
- FastAPI and Uvicorn are available in `.venv`
- Direct dashboard workflow creates a run, attaches the sample DEM, runs terrain analysis, generates a report, and lists outputs.
- Uvicorn starts successfully at `http://127.0.0.1:8000`.

Notes:

- The dashboard does not require ParaView or QGIS for the basic terrain workflow.
- `python-multipart` is not installed, so DEM uploads use raw request bytes instead of multipart form uploads.

### `[DONE]` Add Vector Layer Support

Implemented:

- Vector utilities in `geovis_lm/gis/vector.py`
- GeoJSON, JSON, and Shapefile extension support
- Vector loading through GeoPandas
- Geometry and CRS validation
- CRS detection
- Reprojection to raster CRS
- Raster-bounds clipping
- GeoJSON export
- CLI entry point at `scripts/process_vector_overlay.py`
- Sample GeoJSON overlay at `data/sample/sample_overlay.geojson`
- README workflow documentation

Verified:

- `python3 -m py_compile geovis_lm/gis/vector.py`
- `python3 scripts/process_vector_overlay.py --help`
- Sample GeoJSON overlay can be loaded, validated, clipped to the sample DEM, and exported to GeoJSON.

Notes:

- Shapefile support depends on the project GeoPandas/Fiona stack, which is available in `.venv`.

### `[DONE]` Add QGIS Processing Integration

Implemented:

- Optional QGIS package under `geovis_lm/qgis/`
- QGIS processing workflow script at `geovis_lm/qgis/processing_workflow.py`
- Lazy PyQGIS import with a clear missing-dependency message
- Planned slope and hillshade outputs under `outputs/qgis/`
- `--plan-only` mode for environments without QGIS
- README setup limitation and usage examples

Verified:

- `python3 -m py_compile geovis_lm/qgis/processing_workflow.py`
- `python3 geovis_lm/qgis/processing_workflow.py --help`
- `python3 geovis_lm/qgis/processing_workflow.py --dem data/sample/sample_dem.tif --output-dir outputs/qgis --plan-only`
- Missing PyQGIS exits with a clear message.

Notes:

- QGIS must be installed separately for real Processing execution.

### `[DONE]` Operational Dashboard Foundation

Implemented:

- File-backed project and run model with owner metadata, run lifecycle history, retry metadata, failure fields, and run-scoped output directories.
- Operational dashboard/API workflow for project creation, run creation, run history, output browsing, status history, failure inspection, analysis, retries, cancellation, and report generation.
- Validated batch file ingestion for GeoTIFF, GeoJSON/JSON, CSV, and Shapefile bundle components.
- Upload safety controls for extension allowlists, filename normalization, path traversal rejection, base64 payload validation, SHA-256 checksums, per-file validation status, and configurable upload limits.
- Authentication and authorization controls using `GEOVIS_REQUIRE_AUTH`, `x-geovis-user`, and project ownership/role checks.
- Background execution entry point through `POST /api/runs/<run_id>/queue`, with queued/running/completed/failed lifecycle state persisted to run metadata.
- Health and readiness endpoints at `/healthz` and `/readyz`.
- Optional PostGIS schema support for projects, runs, files, run status events, outputs, reports, and visualizations.
- Production deployment scaffold with `.env.example`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, persistent output/PostGIS volumes, and container health checks.
- CI test workflow at `.github/workflows/tests.yml`.
- Operational pytest suite in `tests/test_dashboard_operational.py`.
- README, deployment, and storage schema documentation updates.

Verified:

- `python3 -m py_compile geovis_lm/dashboard/app.py geovis_lm/dashboard/operations.py geovis_lm/storage/db.py`
- `timeout 120 .venv/bin/python -m pytest -q tests/test_dashboard_operational.py`

Notes:

- File-only mode remains the default local/demo path.
- Database-backed metadata is schema-ready, but the dashboard still uses file-backed metadata unless a future integration layer routes writes through PostGIS.
- Background execution currently uses FastAPI background tasks; a dedicated worker service remains the recommended next scaling step for long production GIS workloads.

### `[DONE]` Create GIS and ParaView Templates Library

Implemented:

- Template-ready project/run metadata structure with workflow type, parameters, inputs, outputs, reports, and retry lineage.
- JSON-compatible workflow parameters persisted per run.
- Import/export-friendly file metadata and report records.

Verified:

- Run creation accepts workflow parameters through `POST /api/projects/<project_id>/runs`.
- Parameters persist in run metadata and are copied into retry runs.

Notes:

- A dedicated template UI and named template registry can now be built on top of the persisted project/run model.

### `[DONE]` Validate Full Docker Compose Runtime

Completed the previously blocked Docker Compose runtime validation.

Implemented:

- Started Docker Desktop from the WSL environment and validated the Docker Engine through the Docker Desktop CLI.
- Created a local gitignored `.env` from `.env.example` for Compose runtime validation.
- Updated the Docker image to install `psycopg[binary]` so PostGIS schema helpers can connect from the dashboard container.
- Updated `scripts/validate_docker_deployment.py` to fall back to Docker Desktop's Windows CLI path when the WSL `docker` shim is unavailable.

Verified:

- `docker compose config` passes through Docker Desktop's CLI.
- `docker compose up --build -d` builds and starts the dashboard and PostGIS services.
- `docker compose ps` reports both dashboard and database containers healthy.
- `/healthz` returns `{"status":"ok"}`.
- `/readyz` returns ready status with storage, database mode, and auth configured.
- `python scripts/init_postgis.py --dry-run` passes inside the dashboard container.
- `python scripts/init_postgis.py` initializes the container PostGIS schema.
- A live Compose API workflow created a project, uploaded `data/sample/sample_dem.tif`, queued a terrain run, processed it with `scripts/run_worker_once.py --json`, generated a report, and listed outputs/jobs.
- The dashboard container was restarted and the same reported run, completed job, and 8 input/output files were still visible through the API.

Result:

- Docker Compose runtime validation is no longer blocked in this environment.
- Runtime validation summary was written to the mounted output volume at `/app/outputs/docker_runtime_validation.json` inside the dashboard container.

### `[DONE]` Add Real DEM Analysis Execution Adapter

Implemented a dedicated DEM terrain analysis adapter behind the dashboard and worker execution path.

Implemented:

- Added `geovis_lm/dashboard/analysis_adapter.py` with a `dem_terrain` execution adapter.
- Moved DEM terrain execution behind a structured adapter result and structured execution error contract.
- Adapter validates DEM input existence and supported GeoTIFF extensions before execution.
- Adapter writes `slope_degrees.tif`, `hillshade.tif`, `terrain_risk.tif`, and `terrain_summary.json`.
- Dashboard analysis now persists `execution_adapter`, `execution_metadata`, output paths, CRS, and structured error details.
- Worker execution continues to process queued runs through the same dashboard analysis workflow.

Verified:

- Direct dashboard analysis still completes for `data/sample/sample_dem.tif`.
- Queued worker analysis still completes through `scripts/run_worker_once.py`.
- Dashboard output listing includes the DEM outputs, summary JSON, uploaded DEM, and generated report.
- Unsupported non-DEM input fails with `unsupported_input` and `retryable=false`.
- Adapter execution failures capture stage, error type, input path, and stage logs.
- `python3 -m py_compile geovis_lm/dashboard/app.py geovis_lm/dashboard/analysis_adapter.py tests/test_dashboard_operational.py`
- `timeout 120 .venv/bin/python -m pytest -q`

Result:

- `11 passed, 3 warnings`.

### `[DONE]` Extend Analysis Adapter to Vector Overlays and Renders

Extended the DEM adapter to support vector overlay processing and render outputs.

Implemented:

- Adapter detects valid vector inputs attached to a run.
- GeoJSON/vector inputs are validated, reprojected to the DEM CRS, and clipped to DEM bounds.
- Clipped vector outputs are written as run-scoped GeoJSON files.
- Optional `terrain_overlay.png` render output combines the DEM preview and clipped vector boundaries.
- `render_overlay=false` disables render generation while preserving vector overlay processing.
- Adapter metadata records source CRS, target CRS, feature counts, clipped feature counts, render status, and stage logs.
- Dashboard output listing includes raster, vector, render, summary, and report artifacts.

Verified:

- DEM-only adapter execution still passes.
- DEM + `data/sample/sample_overlay.geojson` generates `sample_overlay_clipped.geojson`.
- DEM + vector execution generates `terrain_overlay.png` when render output is enabled.
- Render-disabled execution skips `terrain_overlay.png` while still writing clipped vector output.
- Unsupported vector input fails with `unsupported_vector_input` and `retryable=false`.

### `[DONE]` Add Browser Dashboard Login Session Flow

Implemented browser-native authentication for the server-rendered dashboard while preserving API bearer-token auth.

Implemented:

- Added `/login` page for entering the configured dashboard token.
- Added signed `geovis_session` cookie support using the configured auth token.
- Added `/logout` to clear the browser session.
- Dashboard page requests redirect unauthenticated browser users to `/login`.
- API routes continue returning JSON `401` responses when bearer auth is missing or invalid.
- Existing project ownership and role checks now work with either bearer-token principals or browser-session principals.

Verified:

- Unauthenticated browser navigation to `/` redirects to `/login?next=/`.
- Invalid login redirects back to `/login?error=1`.
- Valid login grants browser access to the dashboard.
- Browser session can create a project through the server-rendered form path.
- Logout clears dashboard access.
- API bearer-token auth continues to work unchanged.
- `python3 -m py_compile geovis_lm/dashboard/app.py geovis_lm/dashboard/operations.py geovis_lm/dashboard/analysis_adapter.py tests/test_dashboard_operational.py`
- `timeout 120 .venv/bin/python -m pytest -q`

Result:

- `15 passed, 7 warnings`.

### `[DONE]` Fix Dashboard Project and Run Visibility Consistency

Fixed dashboard recent-run visibility so it matches the current authenticated principal's visible projects.

Implemented:

- Added shared visible-run filtering based on the current user's visible project IDs.
- Updated the dashboard index page to show only runs whose parent project is visible.
- Updated `GET /api/runs` without a project filter to use the same visibility rule.
- Recent Runs now includes the parent project link/name for each visible run.
- Orphaned runs and cross-user runs no longer appear on the dashboard index for unrelated users.

Verified:

- Same-user projects and runs appear together on `/`.
- Cross-user projects and runs are hidden from `/` and `GET /api/runs`.
- Orphaned runs with missing parent projects are hidden from `/` and `GET /api/runs`.

### `[DONE]` Add Persistent Docker Worker Service

Added a first-class Docker Compose worker service for continuous queued job processing.

Implemented:

- Added `run_worker_loop` to poll and claim durable queued jobs continuously.
- Extended `scripts/run_worker_once.py` with `--loop`, `--poll-interval`, and `--max-iterations`.
- Added a `worker` service to `docker-compose.yml` using the dashboard image and shared output volume.
- Worker service depends on healthy dashboard and PostGIS services.
- Added a worker health check that exercises one non-destructive poll iteration.
- Added `scripts/compose_worker_smoke.py` to prove dashboard + worker process a queued DEM/vector run without manually invoking the worker.
- Updated deployment validation and docs to include the worker service.

Verified:

- Compose starts dashboard, worker, and PostGIS services.
- Worker claims queued jobs from durable metadata.
- Worker processes DEM/vector runs end-to-end and writes raster, vector, render, and metadata artifacts.
- Completed job/run visibility survives dashboard service restarts through mounted output storage.
- Worker restart does not duplicate completed jobs because only `queued` jobs are claimed.
- Failed worker execution preserves structured run/job error metadata through the existing worker failure path.
- `python3 -m py_compile geovis_lm/dashboard/worker.py scripts/run_worker_once.py scripts/compose_worker_smoke.py scripts/validate_docker_deployment.py`
- `timeout 120 .venv/bin/python -m pytest -q`
- `python3 scripts/validate_docker_deployment.py`
- `python3 scripts/validate_docker_deployment.py --compose-config`
- `docker compose up --build -d`
- `docker compose exec -T dashboard python scripts/compose_worker_smoke.py`

Result:

- `17 passed, 7 warnings`.
- Compose worker smoke completed one queued DEM/vector run with one completed job and 12 output files.
- After dashboard and worker restart, the same run remained completed with one completed job and 12 output files.

### `[DONE]` Create Project Timeline View

Implemented:

- Run status history with timestamped lifecycle events.
- Dashboard project pages that list project runs.
- Run detail pages that display current status, errors, outputs, and status history.
- API support for listing runs by project and across projects.

Verified:

- Operational tests assert status history for completed analysis runs.
- Failed runs preserve failure state and retry metadata.

### `[DONE]` Operational Queue, Worker, Smoke Test, and Auth Hardening

Completed the next operational dashboard cycle.

Included:

- End-to-end local HTTP smoke test at `scripts/local_operational_smoke.py`.
- Durable file-backed job records under `GEOVIS_OUTPUT_ROOT/jobs/`.
- Queue endpoint now creates a durable queued job instead of relying only on FastAPI background tasks.
- Worker module at `geovis_lm/dashboard/worker.py` and CLI entry point at `scripts/run_worker_once.py`.
- Worker execution claims queued jobs, runs terrain analysis, writes job logs, and updates job/run status.
- Retryable failed runs now create a retry run and queue a durable worker job.
- Dashboard project page now shows run status, owner, timestamps, input count, and output count.
- Dashboard run page now shows input metadata, jobs, outputs, lifecycle history, errors, and conditional queue/cancel/retry actions.
- Operational auth now requires `GEOVIS_AUTH_TOKEN` when `GEOVIS_REQUIRE_AUTH=true`; raw user headers are no longer trusted without a valid bearer token.
- Project, run, and job listing APIs are scoped to visible projects.
- Docker scaffold validation script at `scripts/validate_docker_deployment.py`.
- CI now runs pytest, the local operational smoke test, and deployment scaffold validation.
- README and deployment docs now cover token auth, worker execution, smoke testing, and Docker validation.

Verification:

- `python3 -m py_compile geovis_lm/dashboard/app.py geovis_lm/dashboard/operations.py geovis_lm/dashboard/worker.py scripts/run_worker_once.py scripts/local_operational_smoke.py scripts/validate_docker_deployment.py scripts/init_postgis.py`
- `timeout 120 .venv/bin/python -m pytest -q`
- `timeout 90 .venv/bin/python scripts/local_operational_smoke.py`
- `python3 scripts/validate_docker_deployment.py`

Notes:

- Result: `8 passed, 2 warnings`.
- Live Uvicorn smoke test passed.
- Full Docker Compose runtime validation was completed in the follow-up Docker runtime validation task.

### `[DONE]` Add PostGIS Storage

Implemented:

- Optional storage package under `geovis_lm/storage/`
- Database helper module at `geovis_lm/storage/db.py`
- PostGIS schema documentation at `docs/storage/POSTGIS_SCHEMA.md`
- Schema SQL for runs, uploaded layers, outputs, reports, and visualizations
- Configurable `GEOVIS_DATABASE_URL`
- `.env.example` database settings
- Initialization CLI at `scripts/init_postgis.py`
- Dry-run and print-SQL modes that work without a configured database
- README setup instructions

Verified:

- `python3 -m py_compile geovis_lm/storage/db.py`
- `python3 scripts/init_postgis.py --help`
- `python3 scripts/init_postgis.py --dry-run`
- `python3 scripts/init_postgis.py --print-sql`

Notes:

- The project still works in file-only mode when PostGIS is not configured.
- A real PostGIS connection requires installing the optional `psycopg` package.

### `[DONE]` GeoVis LM Priority Queue Completed

Completed and pushed to `main` at commit `2066852`.

Completed items:

1. `[DONE]` Add Persistent Docker Worker Service
2. `[DONE]` Add Artifact Preview and Download UX
3. `[DONE]` Add Browser End-to-End Workflow Test

Validation:

- Artifact branch merge validation: `20 passed, 11 warnings`
- Browser E2E merge validation: `21 passed, 13 warnings`
- `git diff --check` passed
- `git push` succeeded

Notes:

- `python3 -m pytest -q` was unavailable because system Python lacked pytest.
- Validation was correctly run with `.venv/bin/python -m pytest -q`.
- `py_compile` required `globstar` because `**` did not expand in the shell by default.
- Remaining warnings are dependency/runtime deprecation warnings from NumPy under `.venv/lib/python3.12/site-packages/numpy/ma/core.py`, triggered by `tests/test_dashboard_operational.py`.
- These warnings did not fail the suite.

### `[DONE]` Add Artifact Preview and Download UX

Implemented:

- Run detail output sections for raster, vector, render/preview, and metadata artifacts.
- Registered-output artifact metadata with output type, MIME type, byte size, SHA-256 checksum, generated stage, and run-relative display filename.
- Authenticated download routes for registered GeoTIFF, GeoJSON, PNG, JSON, and Markdown outputs.
- Authenticated inline preview route for registered PNG render outputs.
- Path containment and output-id validation so artifact routes only serve files registered on the owning run.
- README dashboard documentation for previewing and downloading generated artifacts.

Verified:

- `timeout 300 .venv/bin/python -m pytest -vv`
- `timeout 120 .venv/bin/python scripts/local_operational_smoke.py`
- `docker compose up --build -d`
- `docker compose exec -T dashboard python scripts/compose_worker_smoke.py`

Notes:

- Result: `20 passed, 11 warnings`.
- Local HTTP smoke passed.
- Docker Compose dashboard and worker processed a queued vector+DEM run and exposed registered artifacts through metadata, preview, and download routes.
- Browser end-to-end workflow testing was completed as a separate follow-up priority task.

### `[DONE]` Add Browser End-to-End Workflow Test

Implemented:

- Dashboard run-page upload form for validated input uploads through browser pages.
- Dashboard form handler that reuses the existing project/run authorization and base64 ingestion path.
- Browser workflow test covering login, project creation, run creation, DEM/vector upload, queueing, worker completion, output visibility, and logout access blocking.

Verified:

- `timeout 180 .venv/bin/python -m pytest tests/test_dashboard_operational.py::test_browser_end_to_end_workflow_from_login_to_outputs -vv`

Notes:

- Focused E2E result: `1 passed, 2 warnings`.

### `[DONE]` Add Operational Planning Specs

Implemented:

- Project/run model specification at `docs/operations/RUN_MODEL.md`
- File ingestion policy at `docs/operations/FILE_INGESTION_POLICY.md`
- Security and permissions policy at `docs/operations/SECURITY_AND_PERMISSIONS.md`
- Deployment path at `docs/operations/DEPLOYMENT_PATH.md`
- Operational test coverage plan at `docs/operations/TEST_COVERAGE_PLAN.md`
- Documentation index links in `docs/README.md`

Verified:

- Operational specs define the planning portion for project/run model, file ingestion, security, deployment, and testing.
- `docs/planning/PRIORITY_TASKS.md` now marks those specs complete while leaving implementation tasks as `[TODO]`.

Notes:

- This completed item covers documentation/specification only.
- Operational implementation remains pending in the priority queue.
