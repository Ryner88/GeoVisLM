# GeoVisLM Fixed Tasks

Completed tasks should be moved here from `PRIORITY_TASKS.md`.

Status labels:

- `[DONE]` completed and ready for recordkeeping

## Completed Work

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

### `[DONE]` Add PostGIS Storage

Implemented:

- Optional storage package under `geovis_lm/storage/`
- Database helper module at `geovis_lm/storage/db.py`
- PostGIS schema documentation at `docs/POSTGIS_SCHEMA.md`
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
