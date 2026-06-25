# GeoVisLM Priority Tasks

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Operational Readiness Queue

These items are required before GeoVisLM should be treated as operational software instead of a local/demo workflow. Current dashboard support is useful for demos, but the production path still needs durable projects, validated ingestion, persisted state, workers, security, deployment, and tests.

### 1. `[TODO]` Build Real Project and Run Model

Goal: replace ad-hoc run folders and JSON metadata with a persistent project/run model that can track ownership, lifecycle state, inputs, outputs, failures, and retries.

Build:

- Persistent project records
- Persistent analysis run records
- Project ownership fields
- File metadata records linked to projects and runs
- Stable status lifecycle such as created, queued, running, completed, failed, cancelled, retrying, and reported
- Retry and failure state fields
- Run timestamps for created, queued, started, completed, failed, cancelled, and retried states

Acceptance criteria:

- A project can own multiple runs.
- Each run has a durable record outside generated output files.
- Each uploaded/generated file is represented by metadata.
- Failed runs keep error type, error message, and retry eligibility.
- Run state transitions are explicit and documented.

Why priority: the dashboard cannot be operational without reliable, queryable project and run state.

---

### 2. `[TODO]` Implement Reliable File Ingestion

Goal: make upload handling safe and reliable for real geospatial workloads, including multiple files, large files, validation, Shapefile bundles, quotas, and cleanup.

Build:

- Multi-file upload support
- Large-file handling with streaming limits and predictable failure behavior
- Shapefile bundle handling for `.shp`, `.shx`, `.dbf`, `.prj`, and optional sidecar files
- File validation for GeoTIFF, GeoJSON, JSON, CSV, and Shapefile inputs
- MIME/type and extension checks
- Per-project and per-run storage quotas
- Cleanup policy for abandoned, failed, and expired uploads
- Human-readable validation errors per file

Acceptance criteria:

- User can upload multiple geospatial files in one run.
- Shapefile inputs are rejected unless required bundle components are present.
- Large uploads fail cleanly when they exceed configured limits.
- Invalid files do not enter the analysis pipeline.
- Cleanup rules are documented and test-covered.

Why priority: ingestion is the entry point for every real analysis and must be safe before background execution or deployment.

---

### 3. `[TODO]` Build Operational Dashboard Workflow

Goal: turn the current API/demo page into a real dashboard workflow for creating analyses, reviewing history, browsing outputs, and inspecting run logs/errors.

Build:

- Real New Analysis page
- Project selector or project creation flow
- Run history page
- Output browser grouped by project/run/file type
- Logs and errors per run
- Progress states for queued, running, completed, failed, cancelled, and retrying runs
- Links from outputs back to source inputs and run metadata

Acceptance criteria:

- User can create a new analysis from the dashboard without curl commands.
- User can view run history across projects.
- User can open outputs for a completed run.
- User can inspect logs/errors for failed runs.
- Dashboard status matches persisted run state.

Why priority: operational use requires visibility and control, not just API endpoints.

---

### 4. `[TODO]` Wire PostGIS and Database Migrations Into Dashboard

Goal: connect the dashboard to a real database while preserving documented file-only fallback behavior for local demos.

Build:

- Database connection configuration
- Migration system
- Project/run/file metadata tables
- Optional PostGIS extension setup
- PostGIS-backed storage for vector metadata and spatial extents
- Dashboard reads/writes through the database model
- File-only fallback rules for demo/local mode

Acceptance criteria:

- App can start with database mode enabled using environment configuration.
- Migrations create all required operational tables.
- Dashboard run creation persists to the database.
- Vector metadata can be stored with spatial context when PostGIS is available.
- File-only mode remains documented for lightweight local use.

Why priority: JSON files are acceptable for demos, but production needs migrations and durable database-backed state.

---

### 5. `[TODO]` Add Background Job Execution

Goal: move long-running geospatial analysis out of request handlers into a queue-backed worker system with cancellation and retry support.

Build:

- Background worker process
- Queue system or task table
- Job records linked to analysis runs
- Long-running terrain/vector/report execution support
- Progress updates
- Cancellation support
- Retry support with retry limits
- Failure capture and log preservation

Acceptance criteria:

- Starting analysis enqueues a job instead of blocking the HTTP request.
- Worker updates run/job progress as work executes.
- User can cancel queued or running work when supported.
- Failed jobs can be retried when retry rules allow it.
- Job failures preserve logs and readable errors.

Why priority: GIS and visualization workflows can run longer than a normal web request and need operational execution control.

---

### 6. `[TODO]` Add Security and Permission Controls

Goal: protect projects, uploads, outputs, and paths before the app is exposed beyond local development.

Build:

- Authentication
- User/project permissions
- Upload size limits
- Allowed file-type policy
- Path traversal protection on all input/output routes
- Input sanitization
- Safe output serving rules
- Rate or request limits for upload-heavy endpoints

Acceptance criteria:

- Users must authenticate before creating projects/runs.
- Users cannot access projects, inputs, outputs, or logs they do not own.
- Upload limits are configurable and enforced.
- Path traversal attempts are rejected and test-covered.
- Unsafe filenames and unsupported files are rejected before storage.

Why priority: file upload and output browsing are high-risk surfaces if the app leaves localhost.

---

### 7. `[TODO]` Add Production Deployment Path

Goal: provide a repeatable production deployment configuration with persistent storage, environment configuration, and monitoring/logging hooks.

Build:

- Dockerfile
- Docker Compose or equivalent production server config
- Persistent volume/storage configuration for uploads and outputs
- Environment variable configuration
- Database service configuration
- Worker service configuration
- Runtime logging configuration
- Basic monitoring/health endpoints

Acceptance criteria:

- App can be built and run from Docker.
- Dashboard, worker, database, and persistent storage are configured together.
- Environment variables control paths, limits, database connection, and mode.
- Generated outputs survive container restarts when persistent volumes are used.
- Health checks report whether the API, database, storage, and worker path are usable.

Why priority: operational use needs repeatable deployment, persistent storage, and observable runtime behavior.

---

### 8. `[TODO]` Expand Operational Test Coverage

Goal: add tests that cover the real operational paths: GIS/report/storage units, API behavior, uploads, and failure cases.

Build:

- Unit tests for GIS workflows
- Unit tests for report generation
- Unit tests for storage/path helpers
- API tests for project/run lifecycle
- File upload tests for valid and invalid inputs
- Shapefile bundle tests
- Failure-case tests for bad DEMs, missing files, worker failures, quota failures, and path traversal attempts
- Database migration/model tests when database mode is enabled

Acceptance criteria:

- Tests cover successful and failed analysis runs.
- Upload validation behavior is test-covered.
- Path traversal and unsafe filename cases are test-covered.
- Database-backed run lifecycle is test-covered.
- CI runs the operational test suite.

Why priority: operational code needs regression coverage before deployment or real-user testing.

---

## Secondary Feature Priorities

These are useful platform features, but they should come after the operational readiness queue above.

### 9. `[TODO]` Create GIS and ParaView Templates Library

Goal: allow users to save reusable combinations of GIS processing steps and ParaView visualization settings.

Build:

- Template model or JSON storage format
- Template list page
- Template detail view
- Save current workflow as template
- Apply template to a new dataset
- Import/export template JSON

Acceptance criteria:

- User can save a named workflow template.
- Template stores GIS steps and ParaView settings.
- User can apply a saved template to a compatible new dataset.
- Template output is reproducible.
- Template data is documented.

Why priority: templates turn GeoVisLM from a one-off analyzer into a reusable analysis platform, but they depend on stable run/project models.

---

### 10. `[TODO]` Create Project Timeline View

Goal: create a dashboard timeline that maps task status and expected completion dates for ongoing geospatial analysis work.

Build:

- Timeline page or dashboard panel
- Task/project status model
- Expected completion date field
- Timeline grouping by project
- Filters for open, in-progress, blocked, completed, and overdue work

Acceptance criteria:

- User can see ongoing geospatial tasks in timeline order.
- Each timeline item shows project, status, expected completion date, and linked analysis run.
- Blocked and overdue items are visually identifiable.
- Timeline links back to the related project or analysis page.

Why priority: timeline view improves project management once multiple analysis runs exist.
