# GeoVisLM

GeoVisLM is an AI geospatial and scientific visualization lab that combines GIS analysis, ParaView-style scientific visualization, and a small domain-specific language model called GeoMiniLM.

## Goals

- Automate geospatial analysis workflows.
- Generate terrain, slope, hillshade, and risk maps.
- Produce scientific visualization scripts and renders.
- Build a small custom LLM for GIS and visualization workflows.
- Export portfolio-ready reports.

## Initial MVP

The first MVP focuses on terrain analysis:

1. Load a DEM raster.
2. Generate slope and hillshade outputs.
3. Classify terrain risk.
4. Export map images.
5. Generate an analysis report.

## Stack

- Python
- Rasterio
- GeoPandas
- GDAL
- QGIS / PyQGIS later
- ParaView later
- Hugging Face Transformers / Tokenizers
- FastAPI dashboard later

## Project Tracking

- [Priority Tasks](docs/planning/PRIORITY_TASKS.md)
- [Future Tasks](docs/planning/FUTURE_TASKS.md)
- [Fixed Tasks](docs/planning/FIXED_TASKS.md)

## UML Diagrams

- [UML Diagram Documentation](docs/UML_DIAGRAMS.md)
- PlantUML sources: `docs/diagrams/plantuml/`
- Exported images: `docs/diagrams/images/`

## QGIS Workflow

- [QGIS Terrain Workflow](docs/QGIS_WORKFLOW.md)

## Flood and Wildfire Risk Workflows

Filesystem-first flood and wildfire screening workflows can run without the
dashboard or PostGIS:

```bash
.venv/bin/python scripts/run_flood_risk.py \
  --dem data/sample/sample_dem.tif \
  --rivers path/to/rivers.geojson \
  --output-dir outputs/flood_risk

.venv/bin/python scripts/run_wildfire_risk.py \
  --dem data/sample/sample_dem.tif \
  --fuel path/to/fuel.geojson \
  --fuel-field fuel_class \
  --output-dir outputs/wildfire_risk
```

See [Flood and Wildfire Risk Workflows](docs/RISK_WORKFLOWS.md) for input
requirements, risk classes, outputs, and limitations.

## ParaView Terrain Visualization

GeoVisLM includes a first ParaView-compatible terrain rendering entry point at
`geovis_lm/viz/paraview_terrain.py`. It is intended to run with ParaView's
Python interpreter:

```bash
pvpython geovis_lm/viz/paraview_terrain.py data/sample/sample_dem.tif
```

Expected outputs are written under `outputs/renders/`:

- `terrain.png` screenshot render
- `terrain.pvsm` ParaView state file for interactive refinement

Current limitation: ParaView and `pvpython` are not installed by the project
requirements. The script must be run in an environment where ParaView includes
GDAL raster reader support for GeoTIFF DEM inputs.

## GeoMiniLM Dataset

Starter instruction data for the planned GeoMiniLM workflow model lives in
`data/geominilm/`.

- `data/geominilm/README.md` documents the JSONL schema and authoring rules.
- `data/geominilm/starter_workflows.jsonl` includes seed GIS, QGIS, ParaView,
  and reporting workflow examples.

## Report Generation

GeoVisLM can generate a Markdown terrain analysis report from completed terrain
workflow outputs:

```bash
python scripts/generate_report.py \
  --dem data/sample/sample_dem.tif \
  --maps-dir outputs/maps \
  --renders-dir outputs/renders \
  --output-md outputs/reports/terrain_analysis.md
```

PDF export is optional and requires `reportlab` in the active Python
environment:

```bash
python scripts/generate_report.py \
  --dem data/sample/sample_dem.tif \
  --maps-dir outputs/maps \
  --output-md outputs/reports/terrain_analysis.md \
  --output-pdf outputs/reports/terrain_analysis.pdf
```

## Dashboard

The FastAPI dashboard runs from the project virtual environment:

```bash
.venv/bin/python -m uvicorn geovis_lm.dashboard.app:app --reload
```

The dashboard supports a file-backed operational workflow with projects, runs,
validated input files, run lifecycle history, output browsing, report
generation, first-party login/signup, and optional bearer authentication for
API/service access. In local development, authentication is disabled unless
`GEOVIS_REQUIRE_AUTH=true` is set.

Create a project, create a run, upload a DEM, run terrain analysis, and
generate a report:

```bash
curl -X POST http://127.0.0.1:8000/api/projects \
  -H "content-type: application/json" \
  -d '{"name":"Sample Terrain"}'
curl -X POST http://127.0.0.1:8000/api/projects/<project_id>/runs \
  -H "content-type: application/json" \
  -d '{"name":"Sample DEM run","workflow_type":"terrain"}'
curl -X POST --data-binary @data/sample/sample_dem.tif \
  "http://127.0.0.1:8000/api/runs/<run_id>/upload-dem?filename=sample_dem.tif"
curl -X POST http://127.0.0.1:8000/api/runs/<run_id>/analyze
curl -X POST http://127.0.0.1:8000/api/runs/<run_id>/report
curl http://127.0.0.1:8000/api/runs/<run_id>/outputs
```

For validated multi-file uploads, send base64 file payloads to:

```bash
curl -X POST http://127.0.0.1:8000/api/projects/<project_id>/runs/<run_id>/files \
  -H "content-type: application/json" \
  -d '{"files":[{"filename":"sample_dem.tif","content_b64":"<base64 bytes>"}]}'
```

For a local demo without uploading bytes manually, create a run and call:

```bash
curl -X POST http://127.0.0.1:8000/api/runs/<run_id>/use-sample-dem
```

Completed run pages at `/runs/<run_id>` group generated artifacts into raster,
vector, render/preview, and metadata sections. Each row shows the output type,
MIME type, byte size, SHA-256 checksum, generated stage, safe run-relative
filename, and a download action. PNG render outputs also include an inline
browser preview.

Artifact access is run-scoped and uses registered output ids from the run
metadata:

```bash
curl http://127.0.0.1:8000/api/runs/<run_id>/outputs
curl -OJ http://127.0.0.1:8000/api/runs/<run_id>/outputs/slope/download
curl -OJ http://127.0.0.1:8000/api/runs/<run_id>/outputs/vector_overlay_1/download
curl -OJ http://127.0.0.1:8000/api/runs/<run_id>/outputs/terrain_summary_json/download
curl http://127.0.0.1:8000/api/runs/<run_id>/outputs/terrain_overlay_png/preview
```

Supported generated downloads include GeoTIFF, GeoJSON, PNG, and JSON outputs.
Preview is intentionally limited to registered PNG outputs.

Operational settings are environment-driven:

- `GEOVIS_OUTPUT_ROOT`: storage root for projects, runs, uploads, and outputs
- `GEOVIS_REQUIRE_AUTH`: require a browser session or bearer token on operational routes
- `GEOVIS_SESSION_SECRET`: secret used to sign first-party dashboard sessions
- `GEOVIS_SIGNUP_ENABLED`: enable first-party signup when set to `true`
- `GEOVIS_SIGNUP_INVITE_CODE`: optional invite code required during signup
- `GEOVIS_AUTH_TOKEN`: optional bearer token for API/service authentication
- `GEOVIS_MAX_UPLOAD_FILE_MB`: maximum single upload size
- `GEOVIS_MAX_UPLOAD_BATCH_MB`: maximum batch upload size
- `GEOVIS_MAX_BATCH_FILES`: maximum files per upload batch
- `GEOVIS_DATABASE_URL`: optional PostGIS connection string

When authentication is required, browser users can create an account at
`/signup` if signup is enabled, sign in at `/login`, and sign out with
`POST /logout`. JSON clients can use `/api/auth/signup`, `/api/auth/login`, and
`/api/auth/me`; successful signup and login responses set the HTTP-only
`geovis_session` cookie. Bearer-token API calls remain available when
`GEOVIS_AUTH_TOKEN` is configured and include `Authorization: Bearer <token>`
with `x-geovis-user`.

Run a local HTTP smoke test that starts Uvicorn on an available port and drives
the full project, upload, analysis, report, and output workflow:

```bash
.venv/bin/python scripts/local_operational_smoke.py
```

Queued work can be executed once by the file-backed worker command:

```bash
.venv/bin/python scripts/run_worker_once.py --json
```

For continuous local processing, run:

```bash
.venv/bin/python scripts/run_worker_once.py --loop
```

## Vector Overlays

GeoVisLM supports basic vector overlay processing for GeoJSON, JSON, and
Shapefile inputs through GeoPandas:

```bash
.venv/bin/python scripts/process_vector_overlay.py \
  --vector data/sample/sample_overlay.geojson \
  --raster data/sample/sample_dem.tif \
  --output data/processed/sample_overlay_clipped.geojson
```

The workflow validates geometry and CRS metadata, reprojects vectors to match
the raster CRS, clips features to the raster bounds, and exports GeoJSON.

## QGIS Processing

QGIS integration is optional because PyQGIS is installed with QGIS, not the
project virtual environment. The script can show planned outputs without QGIS:

```bash
python3 geovis_lm/qgis/processing_workflow.py \
  --dem data/sample/sample_dem.tif \
  --output-dir outputs/qgis \
  --plan-only
```

Run the workflow with a Python environment configured for QGIS Processing:

```bash
python geovis_lm/qgis/processing_workflow.py \
  --dem data/sample/sample_dem.tif \
  --output-dir outputs/qgis
```

## PostGIS Storage

PostGIS storage is optional. GeoVisLM keeps generated files on disk and can
store project, run, file, status event, output, report, and visualization
metadata in PostgreSQL when `GEOVIS_DATABASE_URL` is configured.

```bash
cp .env.example .env
python3 scripts/init_postgis.py --dry-run
python3 scripts/init_postgis.py --print-sql
```

See `docs/storage/POSTGIS_SCHEMA.md` for the table layout and setup notes.

## Deployment

A repeatable container path is available for operational smoke testing:

```bash
cp .env.example .env
docker compose up --build
```

The Compose stack runs the dashboard, a persistent worker service, PostGIS,
persistent output storage, and health checks. The dashboard exposes
`GET /healthz` and `GET /readyz`.

Validate the deployment scaffold without requiring Docker:

```bash
python3 scripts/validate_docker_deployment.py
```

On a Docker-capable host, also validate Compose syntax:

```bash
python3 scripts/validate_docker_deployment.py --compose-config
```

After the stack is running, validate that the worker service processes a queued
DEM/vector run without manually invoking the worker:

```bash
docker compose exec -T dashboard python scripts/compose_worker_smoke.py
```
