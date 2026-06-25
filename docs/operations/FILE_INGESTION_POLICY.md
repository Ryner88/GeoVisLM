# GeoVisLM File Ingestion Policy

This document defines the operational policy for accepting, validating,
processing, and cleaning up uploaded geospatial files. It is a specification
only; implementation can follow after the project/run model is implemented.

## Goals

- Accept common geospatial input formats safely and predictably.
- Validate files before analysis runs consume them.
- Support batch upload without one bad file stopping the whole batch.
- Keep upload storage bounded with clear cleanup rules.
- Preserve enough metadata to reproduce and audit analysis workflows.

## Supported File Types

Initial supported inputs:

- GeoTIFF raster: `.tif`, `.tiff`
- GeoJSON vector: `.geojson`
- JSON vector, when valid GeoJSON: `.json`
- ESRI Shapefile bundle: `.shp`, `.shx`, `.dbf`, `.prj`, plus optional sidecar files
- CSV tabular data: `.csv`

Future supported inputs:

- ParaView/VTK data: `.vtk`, `.vtu`, `.vtp`, `.vti`
- QGIS project files: `.qgz`
- Cloud-optimized GeoTIFF: `.tif`, `.tiff` with COG validation
- GeoPackage: `.gpkg`

Unsupported by default:

- Executables or scripts
- Compressed archives until archive scanning is implemented
- Files with unknown extensions
- Files with mismatched MIME type and extension
- Files without readable metadata

## Shapefile Bundle Rules

A Shapefile upload is treated as one logical dataset made of multiple files.

Required files:

- `.shp`: geometry
- `.shx`: geometry index
- `.dbf`: attribute table

Strongly recommended files:

- `.prj`: CRS metadata

Optional sidecar files:

- `.cpg`: character encoding
- `.qix`: spatial index
- `.sbn`, `.sbx`: spatial index
- `.xml`: metadata

Rules:

- All bundle files must share the same base filename.
- Bundle files must be attached to the same upload batch.
- A Shapefile bundle is not valid until required files are present.
- Missing `.prj` should produce a warning and require manual CRS selection before analysis.
- Extra files with the same base name can be stored as sidecars when extension is allowed.
- Mixed-base Shapefile uploads should be split into separate logical datasets.

Example valid bundle:

```text
rivers.shp
rivers.shx
rivers.dbf
rivers.prj
rivers.cpg
```

## Upload Limits

Initial limits:

- Maximum single file size: 250 MB
- Maximum batch size: 1 GB total
- Maximum files per batch: 50
- Maximum filename length: 180 characters
- Maximum extracted or normalized path length: 512 characters

Operational limits should be configurable through environment variables:

- `GEOVIS_MAX_UPLOAD_FILE_MB`
- `GEOVIS_MAX_UPLOAD_BATCH_MB`
- `GEOVIS_MAX_BATCH_FILES`

Rejected uploads should return a readable error that includes the violated
limit and the affected filename.

## Filename and Path Rules

- Store original filename for display and audit.
- Generate a safe stored filename for filesystem use.
- Strip directory components from uploaded filenames.
- Reject absolute paths.
- Reject `..` path traversal segments.
- Normalize whitespace and unsafe characters.
- Preserve file extension after validation.
- Store files under the owning project/run directory only.

Suggested storage shape:

```text
outputs/runs/<run_id>/inputs/
outputs/runs/<run_id>/inputs/raw/
outputs/runs/<run_id>/inputs/validated/
outputs/runs/<run_id>/maps/
outputs/runs/<run_id>/reports/
outputs/runs/<run_id>/logs/
```

## Validation Rules

All files:

- Extension is allowed.
- File size is within configured limits.
- Filename is safe after normalization.
- File can be opened by the expected parser.
- Content type and extension are not obviously inconsistent.
- SHA-256 checksum is recorded.
- File metadata record is created before processing.

Raster files:

- Rasterio can open the file.
- Raster has at least one band.
- Raster has width and height greater than zero.
- CRS is present or flagged for manual CRS assignment.
- Bounds can be read.
- Nodata value is recorded when available.
- Data type is recorded.

Vector files:

- GeoPandas/Fiona can open the file.
- Layer has at least one feature.
- Geometry column exists.
- Geometry validity is checked.
- CRS is present or flagged for manual CRS assignment.
- Bounds can be read.
- Feature count is recorded.

CSV files:

- File can be decoded as UTF-8 or a detected supported encoding.
- Header row is present.
- Row count is greater than zero.
- Columns are recorded.
- If geospatial columns are present, latitude/longitude or geometry columns are identified.
- CSV is not treated as spatial until coordinate fields or geometry are validated.

Shapefile bundles:

- Required bundle files are present.
- Bundle base filename is consistent.
- Fiona/GeoPandas can open the `.shp`.
- `.prj` CRS is present or warning is recorded.
- Sidecar files are recorded in metadata.

## Batch Upload Behavior

Batch status is aggregate; file status is per-file.

Batch statuses:

- `created`
- `uploading`
- `validating`
- `partially_valid`
- `valid`
- `processing`
- `completed`
- `completed_with_errors`
- `failed`

Per-file statuses:

- `pending`
- `uploaded`
- `validating`
- `valid`
- `warning`
- `invalid`
- `processing`
- `completed`
- `failed`

Rules:

- One invalid optional file does not fail the whole batch.
- One invalid required file prevents workflows that depend on it.
- Batch should surface both total status and per-file status.
- Processing can continue for valid independent files.
- Errors must be stored per file with readable messages.

## Error Handling

Each failed file should record:

- `error_code`
- `error_message`
- `error_detail`, when available
- `retryable`
- `validation_stage`

Suggested error codes:

- `unsupported_file_type`
- `file_too_large`
- `batch_too_large`
- `unsafe_filename`
- `missing_shapefile_component`
- `missing_crs`
- `invalid_geometry`
- `raster_open_failed`
- `vector_open_failed`
- `csv_parse_failed`
- `checksum_failed`

## Cleanup Policy

Temporary upload files:

- Delete incomplete uploads after 24 hours.
- Delete failed validation temp files after 7 days unless debugging is enabled.
- Keep validation metadata even when temp bytes are deleted.

Completed run files:

- Keep input and output files while project is active.
- Archive files when project is archived.
- Delete files only after project deletion grace period.

Suggested retention:

- Active project files: retain indefinitely
- Archived project files: retain until manually deleted or retention policy expires
- Deleted project files: purge after 30 days
- Run logs: retain 90 days by default
- Temporary chunks: purge after 24 hours

Cleanup must never remove:

- Files referenced by active runs
- Files referenced by generated reports
- Files needed by a retryable failed run unless user confirms deletion

## Acceptance Criteria for Implementation

- Upload endpoint rejects unsupported extensions with clear messages.
- Upload endpoint enforces single-file and batch-size limits.
- Shapefile bundles are grouped and validated as one logical dataset.
- Missing Shapefile required files produce readable per-file or per-bundle errors.
- Raster, vector, and CSV validators record useful metadata.
- Batch upload can complete with mixed success and failure.
- Failed files do not stop independent valid files from processing.
- Cleanup process can identify temporary, failed, archived, and deleted files.
- File metadata remains available after temporary bytes are cleaned up.
- File-only local mode follows the same path and metadata rules.
