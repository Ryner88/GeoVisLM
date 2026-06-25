# GeoVisLM Priority Tasks

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `FIXED_TASKS.md`

## Priority Queue

### 1. `[TODO]` Add PostGIS Storage

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
