# GeoVisLM Project and Run Model

This document defines the operational project/run model for GeoVisLM. It is a
specification only; implementation can follow once the dashboard, storage, and
job execution layers are ready.

## Goals

- Give every uploaded file, analysis run, output, and report a stable owner and project context.
- Support repeatable terrain, GIS, QGIS, ParaView, and future risk-analysis workflows.
- Make long-running and failed jobs observable, retryable, and auditable.
- Keep filesystem outputs and database metadata aligned.

## Core Entities

### Project

A project groups related geospatial analysis work.

Required fields:

- `id`: stable UUID
- `name`: user-facing project name
- `slug`: URL-safe project identifier
- `owner_user_id`: user or service account that owns the project
- `status`: project lifecycle status
- `created_at`: creation timestamp
- `updated_at`: last metadata update timestamp

Recommended fields:

- `description`: short project summary
- `default_crs`: preferred CRS for project outputs
- `area_of_interest`: optional geometry reference or bounds
- `tags`: list of project labels
- `metadata`: JSON object for future extension
- `archived_at`: timestamp when archived

Project statuses:

- `active`: project accepts new runs
- `archived`: project is read-only for normal users
- `deleted`: project is hidden and pending cleanup

### Run

A run is one execution of an analysis workflow inside a project.

Required fields:

- `id`: stable UUID
- `project_id`: parent project UUID
- `workflow_type`: terrain, vector_overlay, qgis_processing, paraview_render, flood_risk, wildfire_risk, or similar
- `status`: run lifecycle status
- `created_by_user_id`: user or service account that started the run
- `created_at`: creation timestamp
- `updated_at`: last state change timestamp

Recommended fields:

- `name`: optional user-facing run name
- `input_file_ids`: ordered list of input file metadata IDs
- `output_file_ids`: ordered list of output file metadata IDs
- `report_ids`: generated report IDs
- `started_at`: timestamp when work begins
- `completed_at`: timestamp when work finishes successfully
- `failed_at`: timestamp when work fails
- `retry_of_run_id`: source run UUID when this is a retry
- `attempt_number`: integer retry attempt counter
- `error_code`: stable machine-readable error code
- `error_message`: readable failure message
- `logs_path`: filesystem path or object-storage URI for run logs
- `parameters`: JSON object containing workflow parameters
- `metadata`: JSON object for future extension

### File Metadata

File metadata describes uploaded inputs and generated outputs. Actual files
remain on disk or object storage; the database stores metadata and paths.

Required fields:

- `id`: stable UUID
- `project_id`: parent project UUID
- `run_id`: related run UUID, when applicable
- `role`: input, output, report, visualization, log, or temporary
- `file_type`: dem, raster, vector, csv, qgis_project, paraview_state, image, markdown, pdf, json, or unknown
- `path`: local filesystem path or object-storage URI
- `status`: file lifecycle status
- `created_at`: creation timestamp
- `updated_at`: last metadata update timestamp

Recommended fields:

- `original_filename`: source filename from upload
- `stored_filename`: normalized stored filename
- `content_type`: MIME type when known
- `extension`: file extension
- `size_bytes`: file size
- `checksum_sha256`: content hash for deduplication and integrity checks
- `crs`: CRS string when known
- `bounds`: geospatial bounds when known
- `band_count`: raster band count when known
- `feature_count`: vector feature count when known
- `driver`: GDAL/Fiona/Rasterio driver name when known
- `validation_errors`: list of file-level validation problems
- `metadata`: JSON object for future extension

File statuses:

- `pending`: file record exists but bytes are not fully available
- `uploaded`: uploaded bytes are available
- `validating`: file validation is running
- `valid`: file passed validation
- `invalid`: file failed validation
- `processing`: file is being used by a run
- `completed`: file output is ready
- `failed`: processing failed for this file
- `deleted`: file is hidden and pending cleanup

## Run Status Lifecycle

Standard run lifecycle:

```text
created -> queued -> running -> completed
```

Failure lifecycle:

```text
created -> queued -> running -> failed
```

Cancellation lifecycle:

```text
created -> queued -> canceled
created -> queued -> running -> canceling -> canceled
```

Retry lifecycle:

```text
failed -> retrying -> queued -> running -> completed
failed -> retrying -> queued -> running -> failed
```

Supported run statuses:

- `created`: run record exists
- `queued`: run is waiting for a worker
- `running`: worker is executing the workflow
- `completed`: workflow completed successfully
- `failed`: workflow failed and may be retryable
- `retrying`: retry request has been accepted
- `canceling`: cancellation request has been accepted
- `canceled`: workflow stopped before completion
- `archived`: run is retained for history but hidden from active views

## Retry and Failure Rules

- A failed run is retryable only when `retryable` is true.
- Retry creates a new run record with `retry_of_run_id` pointing to the failed run.
- Retry must preserve original inputs unless the user explicitly changes them.
- Retry increments `attempt_number`.
- Non-retryable failures should expose a clear `error_code` and `error_message`.
- One failed file in a batch should not automatically fail the full run unless that file is required.
- Batch runs should expose both aggregate run status and per-file status.

Suggested failure fields:

- `error_code`: machine-readable code, for example `invalid_file_type` or `raster_read_failed`
- `error_message`: readable summary
- `error_detail`: longer diagnostic text
- `failed_file_id`: file metadata ID when failure is file-specific
- `retryable`: boolean

## Ownership and Access Rules

Initial ownership rules:

- Every project has exactly one owner.
- Every run belongs to exactly one project.
- Every file belongs to exactly one project.
- A run can only use files from its own project unless explicit sharing is added later.
- Project owners can create, view, retry, cancel, archive, and delete runs.
- Read-only collaborators can view project runs and outputs but cannot modify them.
- Future comment/sharing features should attach permissions at the project level.

Service accounts:

- Background workers may update run and file status.
- Workers must not change project ownership.
- Workers should write append-only logs or status events.

## Example JSON Shape

```json
{
  "project": {
    "id": "f67a6d54-36d9-4a9a-8f73-6a501ae7f9a8",
    "name": "Sample Terrain Analysis",
    "slug": "sample-terrain-analysis",
    "owner_user_id": "user_123",
    "status": "active",
    "default_crs": "EPSG:4326",
    "created_at": "2026-06-25T16:00:00Z",
    "updated_at": "2026-06-25T16:00:00Z"
  },
  "run": {
    "id": "9bfb9a29-ecf9-4272-94a1-f21213e0280d",
    "project_id": "f67a6d54-36d9-4a9a-8f73-6a501ae7f9a8",
    "workflow_type": "terrain",
    "status": "completed",
    "created_by_user_id": "user_123",
    "input_file_ids": ["file_dem_001"],
    "output_file_ids": ["file_slope_001", "file_hillshade_001", "file_risk_001"],
    "parameters": {
      "risk_thresholds": {
        "low_max_degrees": 10,
        "medium_max_degrees": 25
      }
    },
    "created_at": "2026-06-25T16:05:00Z",
    "started_at": "2026-06-25T16:05:05Z",
    "completed_at": "2026-06-25T16:05:30Z",
    "updated_at": "2026-06-25T16:05:30Z"
  },
  "files": [
    {
      "id": "file_dem_001",
      "project_id": "f67a6d54-36d9-4a9a-8f73-6a501ae7f9a8",
      "run_id": "9bfb9a29-ecf9-4272-94a1-f21213e0280d",
      "role": "input",
      "file_type": "dem",
      "original_filename": "sample_dem.tif",
      "path": "outputs/runs/9bfb9a29/inputs/sample_dem.tif",
      "status": "valid",
      "crs": "EPSG:4326",
      "size_bytes": 1048576,
      "created_at": "2026-06-25T16:05:01Z",
      "updated_at": "2026-06-25T16:05:04Z"
    }
  ]
}
```

## Example Database Shape

Suggested tables:

- `geovis_projects`
- `geovis_runs`
- `geovis_files`
- `geovis_run_events`
- `geovis_project_members`

Minimum relationships:

- `geovis_runs.project_id -> geovis_projects.id`
- `geovis_files.project_id -> geovis_projects.id`
- `geovis_files.run_id -> geovis_runs.id`
- `geovis_run_events.run_id -> geovis_runs.id`
- `geovis_project_members.project_id -> geovis_projects.id`

`geovis_run_events` should store append-only state transitions:

- `id`
- `run_id`
- `from_status`
- `to_status`
- `message`
- `created_by`
- `created_at`

## Acceptance Criteria for Implementation

- A project record can be created, read, updated, archived, and listed.
- A run record can be created under a project.
- A run can move through `created`, `queued`, `running`, `completed`, and `failed`.
- File metadata can be stored for inputs and outputs.
- Each file records role, type, path, status, size, and validation state.
- Batch runs can track per-file status without losing aggregate run status.
- Failed runs record `error_code`, `error_message`, and `retryable`.
- Retry creates a new run linked to the failed run.
- Ownership rules prevent a run from accessing files outside its project.
- File-only mode remains possible for local development.
- Dashboard run views can be backed by the same model without special cases.
