# GeoVisLM Priority Tasks

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Operational Readiness Queue

These items are required before GeoVisLM should be treated as operational software instead of a local/demo workflow. Current dashboard support is useful for demos, but the production path still needs durable projects, validated ingestion, persisted state, workers, security, deployment, and tests.

### Shared Operational Requirements

The following requirements apply across the priority queue and should not be repeated in every task:

- **Ownership:** projects, runs, uploaded files, generated outputs, logs, and errors must be associated with an owning user or service account.
- **Run lifecycle:** every analysis run should move through an explicit lifecycle such as created, queued, running, completed, failed, cancelled, retrying, and reported, or a documented equivalent.
- **Durable metadata:** project, run, input file, output file, status, timestamp, retry, and failure metadata should be stored outside generated output folders.
- **Errors and logs:** failed operations should preserve readable user-facing errors and operator-facing diagnostic details.
- **Configurable limits:** paths, storage limits, upload limits, database settings, and execution settings should come from configuration instead of hard-coded values.
- **Security:** upload, output, log, and project routes must enforce authentication, authorization, path safety, and input validation before production exposure.
- **Test coverage:** each operational feature should include success, failure, and edge-case tests, including invalid inputs and unsafe path attempts where relevant.

### Roadmap Format

Each task separates requirements from implementation notes. Requirements describe the behavior GeoVisLM needs. Implementation notes describe current likely approaches and can change if the project adopts different tooling.

---

### 1. `[TODO]` Build Real Project and Run Model

Goal: replace ad-hoc run folders and JSON metadata with durable project/run state.

Planning/spec status: complete in `docs/operations/RUN_MODEL.md`; implementation remains TODO.

Requirements:

- Persist projects, analysis runs, file references, status history, retries, and failures.
- Support multiple runs per project.
- Make run history queryable by the dashboard and API.
- Keep generated outputs linked to their source inputs and run metadata.

Implementation notes:

- Start with a minimal model for projects, runs, files, and status events.
- Keep lifecycle names aligned with the shared run lifecycle section.

Acceptance criteria:

- A project can own multiple durable runs.
- A run can be inspected after app restart without relying only on generated files.
- Failed runs keep enough metadata to explain and retry the failure when allowed.
- Status transitions are documented.

Why priority: the dashboard cannot be operational without reliable, queryable project and run state.

---

### 2. `[TODO]` Implement Reliable File Ingestion

Goal: make upload handling safe and reliable for real geospatial workloads.

Planning/spec status: complete in `docs/operations/FILE_INGESTION_POLICY.md`; implementation remains TODO.

Requirements:

- Support multi-file uploads.
- Validate file type, structure, size, and bundle completeness before analysis.
- Enforce storage quotas and upload limits.
- Provide cleanup rules for abandoned, failed, and expired uploads.
- Return readable validation errors per file.

Implementation notes:

- Initial supported formats can include GeoTIFF, GeoJSON, JSON, CSV, and Shapefile inputs.
- Shapefile bundle validation should account for required components such as `.shp`, `.shx`, `.dbf`, and `.prj`, plus optional sidecar files.
- MIME type and extension checks should be one layer of validation, not the only validation.
- Large-file handling can use streaming limits or another bounded upload approach.

Acceptance criteria:

- User can upload multiple geospatial files in one run.
- Invalid or incomplete files do not enter the analysis pipeline.
- Uploads fail cleanly when they exceed configured limits.
- Cleanup behavior is documented and test-covered.

Why priority: ingestion is the entry point for every real analysis and must be safe before background execution or deployment.

---

### 3. `[TODO]` Build Operational Dashboard Workflow

Goal: turn the current API/demo page into a real dashboard workflow for creating analyses, reviewing history, browsing outputs, and inspecting run state.

Requirements:

- Provide a New Analysis page.
- Show project/run history.
- Expose an output browser grouped by project and run.
- Show progress, logs, and errors per run.
- Link outputs back to the related inputs and run metadata.

Implementation notes:

- The first version can be server-rendered or API-backed; the roadmap should not depend on a specific frontend stack yet.

Acceptance criteria:

- User can create a new analysis from the dashboard without curl commands.
- User can view run history across projects.
- User can open outputs for a completed run.
- User can inspect failure details for failed runs.
- Dashboard status matches persisted run state.

Why priority: operational use requires visibility and control, not just API endpoints.

---

### 4. `[TODO]` Wire Database and Spatial Storage Into Dashboard

Goal: connect the dashboard to durable database-backed state while preserving documented local/demo fallback behavior.

Requirements:

- Add database connection configuration.
- Add a migration path for operational tables.
- Store project, run, file, and status metadata durably.
- Support spatial metadata for geospatial inputs and outputs when a spatial database is available.
- Document fallback behavior when database-backed mode is disabled.

Implementation notes:

- PostGIS is the preferred spatial database target for current planning.
- File-only mode can remain as a lightweight local demo path if clearly separated from operational mode.

Acceptance criteria:

- App can start in database-backed mode using configuration.
- Migrations create the required operational tables.
- Dashboard run creation persists to the database.
- Spatial metadata can be stored when spatial database support is enabled.
- File-only mode is documented as non-operational/demo behavior.

Why priority: JSON files are acceptable for demos, but production needs migrations and durable database-backed state.

---

### 5. `[TODO]` Add Background Job Execution

Goal: move long-running geospatial analysis out of request handlers into controlled asynchronous execution.

Requirements:

- Submit analysis work without blocking the HTTP request.
- Track queued, running, completed, failed, cancelled, and retrying work.
- Preserve progress, logs, and errors for each job/run.
- Support cancellation and retry where the underlying workflow allows it.

Implementation notes:

- The execution backend can be a worker process, task table, queue service, or another bounded job runner.
- Retry limits and cancellation semantics should be explicit because not every GIS operation can be safely interrupted.

Acceptance criteria:

- Starting analysis creates tracked background work.
- Progress updates are visible through persisted run/job state.
- Failed jobs can be retried when retry rules allow it.
- Job failures preserve logs and readable errors.

Why priority: GIS and visualization workflows can run longer than a normal web request and need operational execution control.

---

### 6. `[TODO]` Add Security and Permission Controls

Goal: protect projects, uploads, outputs, and paths before the app is exposed beyond local development.

Planning/spec status: complete in `docs/operations/SECURITY_AND_PERMISSIONS.md`; implementation remains TODO.

Requirements:

- Add authentication.
- Enforce user/project permissions.
- Validate uploads and sanitize inputs.
- Prevent path traversal on input, output, and log routes.
- Apply configurable upload and request limits.
- Serve generated outputs through safe access rules.

Implementation notes:

- The auth mechanism can remain undecided until deployment shape is clearer.
- Security checks should be centralized so CLI/demo paths and dashboard paths do not drift.

Acceptance criteria:

- Users must authenticate before creating projects/runs in operational mode.
- Users cannot access projects, inputs, outputs, or logs they do not own.
- Upload limits are configurable and enforced.
- Unsafe filenames, unsupported files, and path traversal attempts are rejected and test-covered.

Why priority: file upload and output browsing are high-risk surfaces if the app leaves localhost.

---

### 7. `[TODO]` Add Production Deployment Path

Goal: provide a repeatable production deployment configuration with persistent storage, environment configuration, and observability hooks.

Planning/spec status: complete in `docs/operations/DEPLOYMENT_PATH.md`; implementation remains TODO.

Requirements:

- Define a reproducible app runtime.
- Configure persistent storage for uploads and generated outputs.
- Configure database-backed state when operational mode is enabled.
- Configure worker execution when background jobs are enabled.
- Provide environment-based configuration.
- Provide health checks and runtime logging.

Implementation notes:

- Docker and Docker Compose are good initial candidates, but equivalent production packaging is acceptable if documented.
- Health checks should verify API, database, storage, and worker readiness where those components are enabled.

Acceptance criteria:

- App can be built and started through the documented deployment path.
- Persistent storage survives app restarts.
- Runtime settings come from environment/configuration.
- Health checks report whether enabled operational dependencies are usable.

Why priority: operational use needs repeatable deployment, persistent storage, and observable runtime behavior.

---

### 8. `[TODO]` Expand Operational Test Coverage

Goal: add tests that cover operational paths across GIS workflows, reports, storage, API behavior, uploads, security, and failures.

Planning/spec status: complete in `docs/operations/TEST_COVERAGE_PLAN.md`; implementation remains TODO.

Requirements:

- Cover successful and failed analysis runs.
- Cover upload validation for valid, invalid, incomplete, and oversized inputs.
- Cover storage/path helpers and unsafe path attempts.
- Cover API project/run lifecycle behavior.
- Cover database-backed behavior when database mode is enabled.
- Run the operational suite in CI.

Implementation notes:

- Include targeted tests for GIS/report/storage units before broader end-to-end tests.
- Use small fixtures so CI remains fast and deterministic.

Acceptance criteria:

- Tests cover the main success path and representative failure paths.
- Upload validation and path safety are test-covered.
- Database-backed run lifecycle is test-covered when database mode exists.
- CI runs the operational test suite.

Why priority: operational code needs regression coverage before deployment or real-user testing.

---

## Secondary Feature Priorities

These are useful platform features, but they should come after the operational readiness queue above.

### 9. `[TODO]` Create GIS and ParaView Templates Library

Goal: allow users to save reusable combinations of GIS processing steps and visualization settings.

Requirements:

- Save named workflow templates.
- Store processing steps and visualization settings.
- Apply compatible templates to new datasets.
- Import and export template definitions.

Implementation notes:

- JSON is a reasonable first interchange format, but the stored representation can change once the project/run model is stable.

Acceptance criteria:

- User can save and apply a named workflow template.
- Template output is reproducible for compatible inputs.
- Template data is documented.

Why priority: templates turn GeoVisLM from a one-off analyzer into a reusable analysis platform, but they depend on stable run/project models.

---

### 10. `[TODO]` Create Project Timeline View

Goal: create a dashboard timeline that maps task status and expected completion dates for ongoing geospatial analysis work.

Requirements:

- Show timeline items by project.
- Track status and expected completion date.
- Filter open, in-progress, blocked, completed, and overdue work.
- Link timeline items back to the related project or analysis run.

Implementation notes:

- Timeline data should come from the same durable project/run model instead of a separate planning-only store.

Acceptance criteria:

- User can see ongoing geospatial tasks in timeline order.
- Blocked and overdue items are visually identifiable.
- Timeline links back to related project/run details.

Why priority: timeline view improves project management once multiple analysis runs exist.
