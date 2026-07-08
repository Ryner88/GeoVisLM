# GeoVisLM Priority Tasks

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Current Priority Queue

### 1. `[TODO]` Harden Legacy Compose Container Recreate Failures

Goal: make the VPS deployment path resilient when legacy `docker-compose` 1.29.2 raises `KeyError: ContainerConfig` while recreating `dashboard`, `worker`, or `db` containers.

Observed failure:

```text
ERROR: for geovis_lm_dashboard_1  "ContainerConfig"
ERROR: for dashboard  "ContainerConfig"
KeyError: "ContainerConfig"
```

Current mitigation:

- `deploy_runbook.sh` avoids recreating PostGIS through legacy Compose.
- The runbook starts or reuses `geovis_lm_db_1` directly with Docker and the persistent `geovis_lm_geovis_postgis` volume.
- Dashboard and worker are recreated with `docker-compose up -d --no-deps --no-build --force-recreate dashboard worker` after building the shared app image.

Remaining work:

- Add a regression check or smoke procedure that verifies redeploy does not trigger the Compose v1 `ContainerConfig` traceback.
- Document the manual recovery steps for stale Compose-renamed containers such as `12a511c3e99e_geovis_lm_db_1`.
- Confirm the runbook preserves PostGIS volumes and keeps `dashboard`, `worker`, and `db` healthy after repeated deploys.

Acceptance criteria:

- Running `sudo ./deploy_runbook.sh --skip-pull --cache` on the VPS completes without `ContainerConfig` errors.
- Repeated deploys leave `geovis_lm_db_1`, `geovis_lm_dashboard_1`, and `geovis_lm_worker_1` running or healthy.
- Public login still renders the first-party auth UI and `/readyz` returns ready after redeploy.

### 2. `[TODO]` Migrate VPS Deployment from Legacy `docker-compose` v1 to Compose v2

Goal: remove the legacy Compose 1.29.2 deployment risk that can raise `KeyError: ContainerConfig` during container recreation.

Why priority: the current VPS runbook has a direct-Docker mitigation for PostGIS and recreates only app services, but the cleaner long-term fix is to install and standardize on Docker Compose v2 or another supported deploy runner.

Observed failure:

```text
ERROR: for geovis_lm_dashboard_1  "ContainerConfig"
ERROR: for dashboard  "ContainerConfig"
KeyError: "ContainerConfig"
```

Remaining work:

- Install or enable Docker Compose v2 on the VPS.
- Update deployment scripts and docs to prefer `docker compose` when available.
- Remove or simplify direct-Docker workarounds once Compose v2 is verified.
- Add a rollback note for preserving the `geovis_lm_geovis_postgis` volume.

Acceptance criteria:

- `docker compose version` works on the VPS.
- Repeated deploys can recreate dashboard and worker without the `ContainerConfig` traceback.
- PostGIS data survives deploys and container recreation.
- Deployment documentation clearly states whether Compose v1 fallback is still supported.
