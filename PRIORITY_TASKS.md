# GeoVisLM Priority Tasks

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `FIXED_TASKS.md`

## Priority Queue

### 1. `[TODO]` Add QGIS Processing Integration

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

### 2. `[TODO]` Add PostGIS Storage

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
