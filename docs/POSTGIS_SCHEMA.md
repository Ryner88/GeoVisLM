# GeoVisLM PostGIS Schema

GeoVisLM keeps generated files on the local filesystem and stores run metadata,
layer metadata, output paths, reports, and visualization references in
PostgreSQL/PostGIS when database storage is configured.

## Configuration

Set `GEOVIS_DATABASE_URL` to enable database storage:

```bash
GEOVIS_DATABASE_URL=postgresql://geovis:geovis@localhost:5432/geovis_lm
```

The project remains usable in file-only mode when this variable is absent.

## Tables

### `geovis_runs`

Stores one workflow run.

- `id`: run UUID
- `status`: `created`, `uploaded`, `running`, `completed`, `failed`, `archived`
- `input_filename`: original input filename
- `crs`: run CRS string when known
- `bounds`: optional PostGIS polygon bounds
- `metadata`: JSONB metadata
- `created_at`, `updated_at`: timestamps

### `geovis_layers`

Stores uploaded layer metadata.

- `id`: layer UUID
- `run_id`: parent run
- `layer_type`: raster, vector, dem, rivers, buildings, or similar
- `filename`: original filename
- `path`: local filesystem path
- `crs`: layer CRS string when known
- `bounds`: optional PostGIS polygon bounds
- `metadata`: JSONB metadata

### `geovis_outputs`

Stores generated raster/vector output metadata.

- `id`: output UUID
- `run_id`: parent run
- `output_type`: slope, hillshade, terrain_risk, flood_risk, or similar
- `path`: local filesystem path
- `crs`: output CRS string when known
- `bounds`: optional PostGIS polygon bounds
- `metadata`: JSONB metadata

### `geovis_reports`

Stores report artifacts.

- `id`: report UUID
- `run_id`: parent run
- `report_type`: terrain, flood, wildfire, or similar
- `path`: local filesystem path
- `format`: markdown, pdf, or similar
- `metadata`: JSONB metadata

### `geovis_visualizations`

Stores visualization artifacts.

- `id`: visualization UUID
- `run_id`: parent run
- `visualization_type`: qgis_export, paraview_render, or similar
- `path`: local filesystem path
- `state_path`: optional ParaView state file path
- `metadata`: JSONB metadata

## Initialization

Print the schema without connecting:

```bash
python3 scripts/init_postgis.py --print-sql
```

Check local configuration without connecting:

```bash
python3 scripts/init_postgis.py --dry-run
```

Initialize a configured database:

```bash
python3 scripts/init_postgis.py
```
