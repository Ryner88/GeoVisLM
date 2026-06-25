# GeoVisLM Test Coverage Plan

This document defines the operational test matrix for GeoVisLM. It covers upload
tests, API tests, failure tests, GIS/report tests, storage tests, and security
tests. It is a specification only; implementation can follow as features are
built.

## Goals

- Prevent regressions in geospatial processing workflows.
- Validate upload and batch behavior before operational rollout.
- Ensure failures are readable, retryable when appropriate, and isolated.
- Protect project permissions and filesystem boundaries.
- Keep tests useful in file-only local mode and database-backed deployments.

## Test Layers

- Unit tests: pure functions, validators, path utilities, schema helpers
- Integration tests: API routes, storage, file ingestion, report generation
- Workflow tests: full terrain/vector/report/dashboard flows
- Failure tests: invalid files, missing dependencies, bad permissions
- Smoke tests: startup, health checks, CLI help, sample workflow

## Upload Test Matrix

Supported file uploads:

| Case | Input | Expected |
| --- | --- | --- |
| GeoTIFF DEM | `.tif` sample DEM | accepted and metadata recorded |
| GeoJSON vector | `.geojson` sample overlay | accepted and metadata recorded |
| JSON GeoJSON | `.json` valid GeoJSON | accepted as vector |
| CSV table | `.csv` with header and rows | accepted as tabular data |
| Shapefile bundle | `.shp`, `.shx`, `.dbf`, `.prj` | accepted as one logical dataset |

Rejected file uploads:

| Case | Input | Expected |
| --- | --- | --- |
| Unsupported extension | `.exe` | rejected with `unsupported_file_type` |
| Oversized file | over configured file limit | rejected with `file_too_large` |
| Oversized batch | over configured batch limit | rejected with `batch_too_large` |
| Unsafe filename | `../sample.tif` | rejected with `unsafe_filename` |
| Missing Shapefile file | `.shp` without `.dbf` | rejected or marked invalid |
| Invalid raster | corrupt `.tif` | rejected with raster parse error |
| Invalid GeoJSON | malformed JSON | rejected with vector parse error |
| CSV without header | headerless `.csv` | rejected or warning per policy |

Batch upload tests:

- Multiple valid files complete successfully.
- One invalid optional file does not fail the full batch.
- One missing required file prevents dependent workflow execution.
- Per-file status transitions are recorded.
- Batch aggregate status becomes `completed_with_errors` when applicable.

## API Test Matrix

Project API:

- Create project.
- List projects for current user.
- Read project by ID.
- Update project metadata.
- Archive project.
- Reject project access for unauthorized user.

Run API:

- Create run under project.
- Read run details.
- List runs for project.
- Transition run to queued, running, completed.
- Transition run to failed with error fields.
- Retry failed run and link retry to original run.
- Cancel queued or running run.

File API:

- Upload file to project/run.
- Read file metadata.
- List files for project/run.
- Download authorized output.
- Reject unauthorized file access.

Dashboard/API smoke tests:

- `GET /healthz`
- `GET /readyz`
- `POST /api/runs`
- upload sample DEM
- analyze sample DEM
- generate Markdown report
- list run outputs

## Failure Test Matrix

Expected failure cases:

- Missing DEM path.
- Corrupt DEM file.
- Missing CRS.
- Invalid vector geometry.
- Missing Shapefile component.
- Unsupported file type.
- Path traversal filename.
- Upload exceeds limit.
- Report generation requested before analysis outputs exist.
- PDF requested without PDF dependency.
- QGIS workflow requested without PyQGIS.
- ParaView workflow requested without `pvpython`.
- PostGIS init requested without database URL.
- PostGIS connection fails.
- Worker job times out.
- Retry requested for non-retryable failure.

For each failure, assert:

- Stable `error_code`.
- Readable `error_message`.
- No unauthorized file writes.
- Run/file status is updated correctly.
- Logs include enough diagnostic context.
- Independent batch files can continue when allowed.

## GIS and Vector Test Matrix

Terrain processing:

- Load sample DEM.
- Generate slope raster.
- Generate hillshade raster.
- Generate terrain risk raster.
- Preserve raster shape.
- Preserve CRS/profile where applicable.
- Mask invalid/nodata cells.

Vector processing:

- Load sample GeoJSON.
- Validate geometry and CRS.
- Reproject vector to raster CRS.
- Clip vector to raster bounds.
- Export clipped GeoJSON.
- Reject unsupported vector extension.
- Reject invalid geometry.
- Reject missing CRS when workflow requires CRS.

QGIS optional integration:

- CLI `--help` works without PyQGIS.
- `--plan-only` works without PyQGIS.
- Missing PyQGIS returns clear message.
- Real QGIS Processing execution can be tested in a QGIS-enabled environment.

ParaView optional integration:

- Script compiles without ParaView.
- Missing ParaView modules return clear message.
- Real render can be tested in a ParaView-enabled environment.

## Report Test Matrix

Markdown report:

- Generates from sample terrain outputs.
- Creates output directory automatically.
- Includes DEM, slope, hillshade, and terrain risk references.
- Includes optional QGIS and ParaView references when provided.
- Includes reproducibility commands.
- Works without QGIS, ParaView, or GDAL CLI tools.

PDF report:

- Missing PDF dependency returns clear message.
- PDF is generated when dependency is installed.
- PDF output path is created in reports directory.

Report failure cases:

- Missing terrain outputs are marked missing or rejected based on command mode.
- Invalid output path returns readable error.
- Unauthorized report access is rejected.

## Storage Test Matrix

File-only mode:

- Project/run metadata can be represented locally.
- Uploaded files are stored under run directory.
- Generated outputs are stored under run directory.
- Cleanup identifies temporary and failed files.

PostGIS mode:

- Schema SQL renders.
- Dry-run works without database.
- Missing database URL returns clear message.
- Database connection failure returns clear message.
- Run record can be inserted.
- File metadata can be inserted.
- Output metadata can be inserted.
- Report metadata can be inserted.

## Security Test Matrix

Authentication:

- Anonymous project creation is rejected in production mode.
- Anonymous upload is rejected in production mode.
- Dev auth bypass works only when explicitly enabled.

Authorization:

- Viewer cannot upload files.
- Viewer cannot create runs.
- Editor cannot delete project.
- Owner can manage project members.
- Service account can update run status but cannot manage members.

Path traversal:

- `../evil.tif` is rejected.
- Absolute upload path is rejected.
- Symlink escaping storage root is rejected.
- Null byte filename is rejected.
- Raw file path download is rejected.

Upload safety:

- Executable upload is rejected.
- Script upload is rejected.
- Unsupported archive is rejected.
- Oversized upload is rejected before processing.
- Invalid files are not processed by analysis workflows.

## CLI Test Matrix

Every CLI should support `--help`:

- `scripts/run_terrain_analysis.py --help`
- `scripts/generate_report.py --help`
- `scripts/process_vector_overlay.py --help`
- `scripts/init_postgis.py --help`
- `geovis_lm/qgis/processing_workflow.py --help`
- `geovis_lm/viz/paraview_terrain.py --help`

Sample workflow commands:

- Terrain analysis on sample DEM.
- Markdown report generation from sample outputs.
- Vector overlay clipping from sample GeoJSON.
- PostGIS dry-run.
- QGIS plan-only.

## Minimum CI Gate

Required for each pull request:

- Python compile check for all project modules and scripts.
- CLI help smoke tests.
- Unit tests for pure Python helpers.
- Sample terrain workflow test.
- Markdown report generation test.
- Vector overlay sample test in environment with GeoPandas.
- Security path normalization tests once implemented.

Suggested command:

```bash
python3 -m compileall geovis_lm scripts
python3 scripts/generate_report.py --help
python3 scripts/init_postgis.py --dry-run
```

## Acceptance Criteria for Implementation

- Test suite covers successful upload, validation, analysis, report, and output listing paths.
- Test suite covers at least one failure case per major subsystem.
- Test suite verifies path traversal protection.
- Test suite verifies permission checks for owner, editor, viewer, commenter, and service roles.
- GIS tests run against sample DEM and sample GeoJSON.
- Optional dependency tests distinguish unavailable dependency from code failure.
- CI can run a minimal test gate without QGIS, ParaView, or PostGIS installed.
- Extended CI can run QGIS, ParaView, and PostGIS tests in specialized environments.
