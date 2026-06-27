# GeoVisLM Deployment Path

This document defines the operational deployment path for GeoVisLM, including
environment variables, persistent storage layout, service layout, and
health-check requirements.

Implementation status: initial container deployment is available through
`Dockerfile`, `docker-compose.yml`, `.env.example`, and the FastAPI health
endpoints. The Compose path includes a dedicated worker service that polls
durable queued jobs and shares persistent output storage with the dashboard.

## Deployment Goals

- Run the dashboard/API as a stable web service.
- Preserve uploaded inputs, generated outputs, reports, and logs across restarts.
- Store operational metadata in PostgreSQL/PostGIS.
- Support background analysis jobs without blocking web requests.
- Provide clear health checks for orchestration and monitoring.
- Keep local file-only development possible.

## Target Environments

Development:

- Local virtualenv
- Local filesystem storage
- Optional local PostgreSQL/PostGIS
- Auth bypass only when explicitly enabled

Staging:

- Containerized services
- PostgreSQL/PostGIS database
- Persistent volume or object storage
- Authentication enabled
- Small upload limits

Production:

- Containerized services
- Managed PostgreSQL/PostGIS or hardened self-hosted database
- Persistent object storage or durable mounted volume
- Background worker process
- Reverse proxy or platform ingress
- Monitoring, logs, backups, and alerting

## Service Layout

Minimum operational services:

- `web`: FastAPI dashboard/API served by Uvicorn or Gunicorn/Uvicorn workers
- `worker`: background job executor for analysis workflows
- `database`: PostgreSQL with PostGIS extension
- `storage`: persistent filesystem volume or object storage bucket

Optional future services:

- `scheduler`: cleanup and retry scheduler
- `cache`: Redis or equivalent for queues and short-lived state
- `qgis-worker`: worker image with QGIS/PyQGIS installed
- `paraview-worker`: worker image with ParaView/pvpython installed

Recommended process split:

```text
web      -> handles HTTP, auth, metadata reads, upload coordination
worker   -> handles GIS processing, report generation, validation, retries
database -> stores projects, runs, files, reports, events, permissions
storage  -> stores uploaded bytes and generated artifacts
```

## Environment Variables

Implemented settings:

- `GEOVIS_OUTPUT_ROOT`: root path for persistent local file storage
- `GEOVIS_DATABASE_URL`: optional PostgreSQL/PostGIS connection URL
- `GEOVIS_REQUIRE_AUTH`: requires `x-geovis-user` identity headers when true
- `GEOVIS_MAX_UPLOAD_FILE_MB`
- `GEOVIS_MAX_UPLOAD_BATCH_MB`
- `GEOVIS_MAX_BATCH_FILES`

Additional recommended production settings:

- `GEOVIS_ENV`: `development`, `staging`, or `production`
- `GEOVIS_SECRET_KEY`: secret used for sessions, tokens, or signing
- `GEOVIS_BASE_URL`: external base URL for generated links

Auth and permissions:

- `GEOVIS_AUTH_PROVIDER`
- `GEOVIS_ADMIN_EMAILS`

Runtime:

- `GEOVIS_LOG_LEVEL`
- `GEOVIS_WORKER_CONCURRENCY`
- `GEOVIS_JOB_TIMEOUT_SECONDS`
- `GEOVIS_CLEANUP_ENABLED`

Optional external tools:

- `GEOVIS_QGIS_ENABLED`
- `GEOVIS_QGIS_PYTHON_PATH`
- `GEOVIS_PARAVIEW_ENABLED`
- `GEOVIS_PVPYTHON_PATH`

Rules:

- `.env.example` may contain placeholder values only.
- Real secrets must come from deployment secret storage.
- Production must not enable `GEOVIS_DEV_AUTH_BYPASS`.
- Database URLs must be masked in logs.

## Persistent Storage Layout

For filesystem storage, use `GEOVIS_OUTPUT_ROOT`:

```text
<GEOVIS_OUTPUT_ROOT>/
  runs/
    <run_id>/
      inputs/
        raw/
        validated/
      maps/
      renders/
      reports/
      logs/
  projects/
    <project_id>/
      project.json
```

Rules:

- All user-controlled files must stay under `GEOVIS_STORAGE_ROOT`.
- Paths stored in the database should be relative when possible.
- Temporary files should stay under the run `temp/` directory.
- Cleanup jobs must not delete files referenced by active runs or reports.
- Object storage can mirror the same logical layout with key prefixes.

## Database Requirements

Database must provide:

- PostgreSQL
- PostGIS extension
- Migrations or schema initialization
- Backups
- Connection pooling or conservative connection limits

Operational tables should cover:

- Projects
- Runs
- Files
- Reports
- Visualizations
- Run events
- Project members
- Audit events

## Deployment Steps

Initial container deployment:

1. Copy `.env.example` to `.env`.
2. Run `docker compose up --build`.
3. Confirm the `dashboard`, `worker`, and `db` services are healthy.
4. Initialize PostGIS metadata tables with `python3 scripts/init_postgis.py` when database metadata is required.
5. Check `GET /healthz` and `GET /readyz`.
6. Create a project and terrain run.
7. Upload a small DEM/vector input pair and queue the run.
8. Confirm the worker service completes the run and generated outputs persist.

Repo-side validation that does not require Docker:

```bash
python3 scripts/validate_docker_deployment.py
```

Docker-capable host validation:

```bash
python3 scripts/validate_docker_deployment.py --compose-config
docker compose up --build
docker compose exec -T dashboard python scripts/compose_worker_smoke.py
```

Production deployment adds:

1. Auth provider configuration.
2. TLS and external domain.
3. Backup policy.
4. Log aggregation.
5. Monitoring and alerting.
6. Resource limits.
7. Upload limits.
8. Security review.

## Health Checks

Required endpoints:

- `GET /healthz`: process is alive
- `GET /readyz`: service is ready for traffic
- `GET /version`: build/version metadata

`/healthz` should check:

- Web process is running.
- Event loop can respond.

`/readyz` should check:

- Database connection works, when database is required.
- Storage root is writable.
- Required configuration is present.
- Worker queue is reachable, when queue is enabled.

Worker health checks:

- Worker process is running.
- Worker can read configuration.
- Worker can access storage root.
- Worker can connect to database.

Suggested health response:

```json
{
  "status": "ok",
  "service": "geovis-web",
  "environment": "staging",
  "database": "ok",
  "storage": "ok",
  "version": "0.1.0"
}
```

## Operational Logging

Log events:

- Service startup and shutdown
- Configuration validation
- Upload accepted/rejected
- File validation results
- Run lifecycle changes
- Job failures
- Permission denials
- Cleanup actions

Required log fields:

- `timestamp`
- `level`
- `service`
- `event_type`
- `project_id`, when available
- `run_id`, when available
- `file_id`, when available
- `message`

## Backup and Recovery

Backup targets:

- PostgreSQL/PostGIS database
- Persistent storage root or object storage bucket
- Environment/configuration records, excluding secret values

Recovery requirements:

- Restore database and files to a consistent point in time.
- Preserve project/run/file relationships.
- Validate that reports and output paths still resolve after restore.
- Document manual recovery procedure before production launch.

## Acceptance Criteria for Implementation

- Application can run with configured `GEOVIS_STORAGE_ROOT`.
- Application can run with configured `GEOVIS_DATABASE_URL`.
- Startup fails clearly when required production config is missing.
- `/healthz` responds without database dependency.
- `/readyz` checks database and storage dependencies.
- Uploaded files persist across service restarts.
- Generated outputs persist across service restarts.
- Web service and worker can run as separate processes.
- Deployment documentation lists all required environment variables.
- Staging deployment can complete a sample terrain workflow end to end.
