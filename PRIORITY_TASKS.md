# GeoVisLM Priority Tasks

Status labels:

- `[TODO]` not started
- `[IN-PROGRESS]` actively being worked
- `[BLOCKED]` cannot move without another fix or decision
- `[DONE]` completed and ready to move into `FIXED_TASKS.md`

## Priority Queue

### 1. `[TODO]` Add Report Generator

Generate Markdown and PDF reports from completed GIS/visualization runs.

Why priority: reports make existing terrain analysis outputs presentable and close the MVP loop from data processing to deliverable.

---

### 2. `[TODO]` Add Web Dashboard

Build a FastAPI dashboard for uploading DEM files, running analysis jobs, and viewing outputs.

Why priority: a dashboard turns the CLI pipeline into a usable workflow and creates the foundation for demos.

---

### 3. `[TODO]` Add Vector Layer Support

Support GeoJSON/Shapefile overlays such as rivers, roads, buildings, and administrative boundaries.

Why priority: vector overlays unlock realistic GIS analysis beyond single-raster terrain outputs.

---

### 4. `[TODO]` Add QGIS Processing Integration

Use PyQGIS or QGIS Processing algorithms for slope, hillshade, buffers, clipping, and map rendering.

Why priority: QGIS integration improves analytical credibility and prepares the project for richer geoprocessing workflows.

---

### 5. `[TODO]` Add PostGIS Storage

Store uploaded layers, metadata, runs, and outputs in PostgreSQL/PostGIS.

Why priority: persistent geospatial storage becomes important once uploads, vector layers, and dashboard workflows exist.
