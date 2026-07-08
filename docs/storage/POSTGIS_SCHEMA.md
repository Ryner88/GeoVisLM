# GeoVisLM PostGIS Schema

GeoVisLM keeps generated files on the local filesystem and stores project
metadata, run metadata, file metadata, status events, output paths, reports, and
visualization references in PostgreSQL/PostGIS when database storage is
configured.

## Configuration

Set `GEOVIS_DATABASE_URL` to enable database storage:

```bash
GEOVIS_DATABASE_URL=postgresql://geovis:geovis@localhost:5432/geovis_lm
```

The project remains usable in file-only mode when this variable is absent.

## Tables

### `geovis_users`

Stores first-party login accounts.

- `id`: user UUID
- `email`: normalized unique email address
- `password_hash`: Argon2 password hash; plaintext passwords are never stored
- `display_name`: user-facing name
- `role`: default application role
- `active`: whether the account can authenticate
- `activation_token_hash`, `activated_at`: activation metadata
- `last_login_at`: most recent successful login timestamp, when recorded
- `metadata`: JSONB metadata
- `created_at`, `updated_at`: timestamps

### `geovis_projects`

Stores one project ownership boundary.

- `id`: project UUID
- `name`, `slug`: user-facing and URL-safe project identifiers
- `owner_user_id`: owning user or service account
- `status`: `active`, `archived`, or `deleted`
- `description`, `default_crs`, `area_of_interest`
- `metadata`: JSONB metadata
- `created_at`, `updated_at`, `archived_at`: timestamps

### `geovis_runs`

Stores one workflow run.

- `id`: run UUID
- `project_id`: parent project UUID
- `workflow_type`: terrain, vector, QGIS, ParaView, or future workflow type
- `status`: `created`, `uploaded`, `queued`, `running`, `completed`, `failed`, `canceling`, `canceled`, `retrying`, `reported`, or `archived`
- `created_by_user_id`: user or service account that created the run
- `input_filename`: original input filename
- `crs`: run CRS string when known
- `bounds`: optional PostGIS polygon bounds
- `started_at`, `completed_at`, `failed_at`: lifecycle timestamps
- `retry_of_run_id`, `attempt_number`, `retryable`: retry metadata
- `error_code`, `error_message`, `error_detail`: failure metadata
- `parameters`: workflow parameters
- `metadata`: JSONB metadata
- `created_at`, `updated_at`: timestamps

### `geovis_files`

Stores uploaded input and generated file metadata.

- `id`: file UUID
- `project_id`: parent project
- `run_id`: related run, when applicable
- `role`: input, output, report, visualization, log, or temporary
- `file_type`: dem, raster, vector, csv, shapefile_sidecar, markdown, image, or similar
- `original_filename`, `stored_filename`
- `path`: local filesystem path
- `status`: pending, uploaded, validating, valid, invalid, processing, completed, failed, or deleted
- `content_type`, `extension`, `size_bytes`, `checksum_sha256`
- `crs`: layer CRS string when known
- `bounds`: optional PostGIS geometry bounds
- `validation_errors`: JSONB validation error list
- `metadata`: JSONB metadata

### `geovis_run_status_events`

Stores run lifecycle history.

- `id`: event UUID
- `run_id`: parent run
- `status`: lifecycle status
- `message`: readable status message
- `metadata`: JSONB event metadata
- `created_at`: event timestamp

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
