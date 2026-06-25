# GeoVisLM Priority Tasks

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `FIXED_TASKS.md`

## Priority Queue

### 1. `[TODO]` Add Web Dashboard

Goal: build a FastAPI dashboard for uploading DEM files, running terrain analysis jobs, and viewing generated outputs.

Build:

* Add dashboard package under `geovis_lm/dashboard/`.
* Add FastAPI app, for example:

  * `geovis_lm/dashboard/app.py`
* Add upload endpoint for DEM files.
* Add run endpoint to execute terrain analysis.
* Add output listing endpoint.
* Add report generation endpoint once the report generator exists.
* Add static file serving for generated maps, renders, and reports.
* Add simple HTML templates or JSON-first API responses.
* Add run output folders, for example:

  * `outputs/runs/<run_id>/maps/`
  * `outputs/runs/<run_id>/renders/`
  * `outputs/runs/<run_id>/reports/`
* Add README usage instructions.

Suggested endpoints:

```text
GET  /
POST /api/runs
POST /api/runs/{run_id}/upload-dem
POST /api/runs/{run_id}/analyze
POST /api/runs/{run_id}/report
GET  /api/runs/{run_id}
GET  /api/runs/{run_id}/outputs
```

Acceptance criteria:

* User can start the dashboard locally with Uvicorn.
* User can upload a DEM file.
* User can run terrain analysis from the dashboard/API.
* User can view generated output paths.
* User can generate or link to a report.
* Dashboard does not require ParaView or QGIS for the basic terrain workflow.
* README documents how to start and use the dashboard.

Validation:

```bash
python3 -m py_compile geovis_lm/dashboard/app.py
uvicorn geovis_lm.dashboard.app:app --reload
```

Why priority: a dashboard turns the CLI pipeline into a usable workflow and creates the foundation for demos.

---

### 2. `[TODO]` Add Vector Layer Support

Goal: support GeoJSON and Shapefile overlays such as rivers, roads, buildings, and administrative boundaries.

Build:

* Add vector package under `geovis_lm/gis/vector.py`.
* Add functions to:

  * load vector layers with GeoPandas
  * validate geometry
  * detect CRS
  * reproject to match a raster CRS
  * clip vector layers to DEM bounds
  * export processed vectors to GeoJSON
* Support at least:

  * `.geojson`
  * `.json`
  * `.shp`
* Add optional vector overlay metadata to reports.
* Prepare dashboard upload support for vector files.
* Document sample vector workflow.

Suggested functions:

```python
load_vector(path)
validate_vector(gdf)
reproject_vector(gdf, target_crs)
clip_vector_to_raster_bounds(gdf, raster_path)
write_vector_geojson(gdf, output_path)
```

Acceptance criteria:

* GeoJSON vector layer can be loaded and validated.
* Shapefile vector layer can be loaded if dependencies are available.
* Vector CRS can be matched to DEM/raster CRS.
* Vector layer can be clipped to DEM bounds.
* Processed vector layer can be exported to GeoJSON.
* README documents the supported vector formats and workflow.

Validation:

```bash
python3 -m py_compile geovis_lm/gis/vector.py
python3 scripts/process_vector_overlay.py --help
```

Why priority: vector overlays unlock realistic GIS analysis beyond single-raster terrain outputs.

---

### 3. `[TODO]` Add QGIS Processing Integration

Goal: use PyQGIS or QGIS Processing algorithms for slope, hillshade, buffers, clipping, and map rendering.

Build:

* Add QGIS integration package under `geovis_lm/qgis/`.
* Add a QGIS processing script, for example:

  * `geovis_lm/qgis/processing_workflow.py`
* Keep QGIS integration optional.
* Detect missing QGIS/PyQGIS dependencies and fail with a clear message.
* Add workflows for:

  * slope generation
  * hillshade generation
  * raster clipping
  * vector buffering
  * vector clipping
  * map rendering/export if available
* Document that QGIS must be installed separately.
* Add README usage examples.

Suggested command:

```bash
python geovis_lm/qgis/processing_workflow.py \
  --dem data/sample/sample_dem.tif \
  --output-dir outputs/qgis
```

Acceptance criteria:

* QGIS integration does not break normal Python workflows when QGIS is unavailable.
* Script provides clear error output when PyQGIS is missing.
* At least one QGIS Processing workflow is documented.
* QGIS-generated outputs are written to a predictable output folder.
* README documents setup limitations and usage.

Validation:

```bash
python3 -m py_compile geovis_lm/qgis/processing_workflow.py
python3 geovis_lm/qgis/processing_workflow.py --help
```

Why priority: QGIS integration improves analytical credibility and prepares the project for richer geoprocessing workflows.

---

### 4. `[TODO]` Add PostGIS Storage

Goal: store uploaded layers, metadata, runs, and outputs in PostgreSQL/PostGIS for persistent dashboard workflows.

Build:

* Add database package under `geovis_lm/storage/`.
* Add schema documentation under `docs/POSTGIS_SCHEMA.md`.
* Add database models or SQL migrations for:

  * runs
  * uploaded layers
  * raster outputs
  * vector outputs
  * generated reports
  * visualization outputs
* Store metadata such as:

  * input filename
  * CRS
  * bounds
  * output paths
  * run status
  * timestamps
* Keep local filesystem output storage for files.
* Store file metadata and paths in PostGIS/PostgreSQL.
* Add `.env.example` database settings.
* Add README setup instructions.

Suggested tables:

```text
geovis_runs
geovis_layers
geovis_outputs
geovis_reports
```

Suggested statuses:

```text
created
uploaded
running
completed
failed
archived
```

Acceptance criteria:

* PostGIS schema is documented.
* Database connection settings are configurable.
* A run record can be created.
* Uploaded layer metadata can be stored.
* Output metadata can be stored after terrain analysis.
* Dashboard can later read run/output metadata from the database.
* Project still works in file-only mode if PostGIS is not configured.

Validation:

```bash
python3 -m py_compile geovis_lm/storage/db.py
python3 scripts/init_postgis.py --help
```

Why priority: persistent geospatial storage becomes important once uploads, vector layers, and dashboard workflows exist.
