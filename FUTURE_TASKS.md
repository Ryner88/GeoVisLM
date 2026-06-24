# GeoVisLM Future Tasks

These tasks are not current priority work. Move items into `PRIORITY_TASKS.md` when they become active.

Status labels:

- `[TODO]` not started
- `[IN-PROGRESS]` actively being worked
- `[BLOCKED]` cannot move without another fix or decision
- `[DONE]` completed and ready to move into `FIXED_TASKS.md`

## Future Queue

### `[TODO]` Add Web Dashboard

Build a FastAPI dashboard for uploading DEM files, running analysis jobs, and viewing outputs.

### `[TODO]` Add Report Generator

Generate Markdown and PDF reports from completed GIS/visualization runs.

### `[TODO]` Add Vector Layer Support

Support GeoJSON/Shapefile overlays such as rivers, roads, buildings, and administrative boundaries.

### `[TODO]` Add Flood Risk Workflow

Combine DEM, slope, river buffers, and building footprints into a flood-risk analysis.

### `[TODO]` Add Wildfire Risk Workflow

Combine slope, vegetation, wind/sensor data, and proximity layers into a wildfire-risk analysis.

### `[TODO]` Add QGIS Processing Integration

Use PyQGIS or QGIS Processing algorithms for slope, hillshade, buffers, clipping, and map rendering.

### `[TODO]` Add PostGIS Storage

Store uploaded layers, metadata, runs, and outputs in PostgreSQL/PostGIS.

### `[TODO]` Train First GeoMiniLM Prototype

Train or fine-tune a small language model on GIS and ParaView workflow examples.

### `[TODO]` Add Model Evaluation Suite

Compare GeoMiniLM output against expected workflow JSON.

### `[TODO]` Add Demo Video and Portfolio Page

Create a short demo video, screenshots, and a polished project page.

### `[TODO]` Install/check system GDAL tools when sudo access is available

Install and verify `gdalinfo` and `ogrinfo` once interactive sudo access is available.
