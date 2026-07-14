# Prime VPS deployment

GeoVis LM is deployed on Prime at `/opt/geovis_lm` with Docker Compose v2. The
dashboard is published only as `127.0.0.1:8000`; Caddy is the only public web
entry point. Do not remove the previous deployment or change Cloudflare/DNS
until the Prime public endpoint passes validation.

## Host and services

- Repository: `/opt/geovis_lm`, branch `main`
- Compose project: `geovis_lm`
- Services: `dashboard`, persistent `worker`, and PostGIS `db`
- Volumes: `geovis_lm_geovis_outputs` and `geovis_lm_geovis_postgis`
- Environment: `/opt/geovis_lm/.env`, mode `0600`, never committed
- Caddy configuration: `/etc/caddy/Caddyfile`
- Pre-import backups: `/root/geovis-backups/`
- Prime public IPv4: `192.3.31.132`
- Production hostname: `geovis.nextgenbytes.me`

The production environment requires `POSTGRES_PASSWORD`,
`GEOVIS_AUTH_TOKEN`, and `GEOVIS_SESSION_SECRET`. It also sets
`GEOVIS_REQUIRE_AUTH=true`, `GEOVIS_SESSION_COOKIE_SECURE=true`, upload limits,
and `GEOVIS_SIGNUP_ENABLED=false`. Secret values must not appear in logs,
documentation, or Git. Cloudflare Access credentials are not required by the
application and were not copied.

Production account signup, provisioning, role assignment, recovery, and access
reviews follow `docs/operations/ACCOUNT_POLICY.md`. In particular, keep public
signup disabled and use `scripts/manage_users.py` inside the dashboard
container for operator-controlled account changes.

## Supported Compose runner

Production deployments require Docker Compose v2 through `docker compose`.
Legacy `docker-compose` v1 is not supported and the deployment runbook refuses
to use it. This prevents the v1 `KeyError: ContainerConfig` recreate failure
and keeps database, dashboard, and worker lifecycle management on one supported
runner.

Before an upgrade, verify the runner and configuration:

```bash
docker compose version
docker compose config --quiet
```

`deploy_runbook.sh` starts the `db` service through Compose without forcing its
recreation, builds the shared app image, and force-recreates only `dashboard`
and `worker`. The external volume name remains
`geovis_lm_geovis_postgis`; never use `docker compose down --volumes` in deploy
or recovery commands.

## Initial deployment and validation

```bash
cd /opt/geovis_lm
docker compose config -q
python3 scripts/validate_docker_deployment.py --compose-config
docker compose build
docker compose up -d
docker compose ps
curl -fsS http://127.0.0.1:8000/healthz
curl -fsS http://127.0.0.1:8000/readyz
docker compose exec -T dashboard python -m compileall -q geovis_lm scripts
docker compose exec -T dashboard python -m pytest -q
docker compose exec -T dashboard python scripts/compose_worker_smoke.py --token "$GEOVIS_AUTH_TOKEN"
```

Load `.env` without printing it before the worker smoke command. A successful
smoke test queues a DEM/vector run, waits for the persistent worker to complete
it, and checks its raster, GeoJSON, PNG, and metadata artifacts.

For a release or runner upgrade, exercise the exact redeploy path twice:

```bash
sudo ./scripts/verify_compose_redeploy.sh
```

The verifier rejects any `ContainerConfig` traceback, requires all three
services to be running, checks local and public readiness/login, and compares
PostgreSQL's cluster identifier before and after each redeploy. An unchanged
identifier proves that the same PostGIS data directory remained mounted.

## Legacy Compose stale-container recovery

Compose v1 can leave renamed containers such as
`12a511c3e99e_geovis_lm_db_1`. Preserve `.env` and both named volumes before
recovery, then inspect the project state:

```bash
docker compose ps -a
docker ps -a --filter label=com.docker.compose.project=geovis_lm
docker volume inspect geovis_lm_geovis_postgis
```

If a stale renamed container conflicts with a Compose v2 service, record its
name and mounts, stop it, and remove only that container:

```bash
docker inspect <stale-container>
docker stop <stale-container>
docker rm <stale-container>
docker compose up -d --wait db
docker compose up -d --no-deps --force-recreate --wait dashboard worker
```

Do not remove `geovis_lm_geovis_postgis`, pass `--volumes`, or delete an active
database container until its mount has been confirmed. After recovery, run the
repeated-redeploy verifier and the worker persistence smoke test.

## Caddy and Cloudflare origin TLS

The site proxies `geovis.nextgenbytes.me` to `127.0.0.1:8000`. Cloudflare uses
Full (strict) mode and Caddy uses the matching Cloudflare Origin CA pair:

- Certificate: `/etc/caddy/certs/geovis-origin.pem`, mode `0640`, `root:caddy`
- Private key: `/etc/caddy/certs/geovis-origin-key.pem`, mode `0640`, `root:caddy`
- Certificate directory: `/etc/caddy/certs`, mode `0750`, `root:caddy`

Never copy either TLS file into Git or output its contents. The pre-Origin-CA
Caddy backup is
`/root/geovis-backups/Caddyfile.before-origin-ca.20260711T013456Z`.
Validate before every reload:

```bash
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl reload caddy
journalctl -u caddy --since "15 minutes ago" --no-pager
```

## Public validation record

Validated on `2026-07-11` UTC through Cloudflare, Ray ID
`a19411fd08dd4bc3-BUF`:

- Public and forced-origin `GET /healthz` and `GET /readyz` succeeded.
- `GET /readyz` returned HTTP 200 with ready status. `HEAD /readyz` returns 405
  because that endpoint implements GET only; this is not a readiness failure.
- `GET /login` returned the login HTML with inline HTTPS-safe assets, correct
  redirects, and a Secure session cookie during token-backed session testing.
- Signup remained disabled (`GET /signup` returned 404).
- Token-backed public session login, authenticated dashboard access, Secure
  session-cookie handling, and logout passed.
- A provisioned first-party owner account passed email/password login through
  Cloudflare, authenticated dashboard access, Secure and HttpOnly session-cookie
  checks, logout, and post-logout access denial. A known-invalid password was
  rejected with HTTP 401. No credentials were recorded.
- Targeted browser-session and deployment-security regressions passed (2 tests),
  and bearer-token session authentication continued to pass after first-party
  account provisioning.
- Public terrain run `6f71590b507f442e82b5d648bf78741f` completed through
  the persistent worker with six registered artifacts; previews and downloads
  passed. The completed run and all artifacts survived a Compose restart.
- The default Python urllib user agent received Cloudflare 403; the same public
  workflow passed with a normal identified client user agent.
- Dashboard, worker, PostGIS, Caddy, firewall, and port checks passed with no
  runtime failures in the validation log window.

Do not retire the former deployment until the observation period completes,
backups are confirmed, and retirement is explicitly approved.

## Production sign-off

Production was formally signed off on `2026-07-13` UTC after the observation
period that began with the `2026-07-11` public validation. At sign-off:

- Public `/readyz` returned ready with storage, database mode, and required
  authentication configured.
- Dashboard, worker, and PostGIS reported healthy after a Compose recreation;
  PostGIS remained healthy across the observation period.
- The available 48-hour service log window showed successful startup and
  readiness checks with no traceback or runtime error.
- The closed-signup provisioning and recovery policy was documented, and 30
  focused authentication and deployment-security tests passed.

This sign-off approves Prime as the production service. It does not approve
retirement of the former deployment; that still requires confirmed backups and
explicit retirement approval.

### 2026-07-14 sign-off revalidation

The account-policy branch was reconciled with the completed Compose v2
migration and exercised on Prime before merge:

- The reconciled container image passed all 39 tests.
- Two consecutive Compose v2 redeploys completed with dashboard, worker, and
  PostGIS healthy; PostgreSQL's cluster identifier remained unchanged.
- A new authenticated public worker run
  (`adad9c4350cf4957a90eea7b75555921`) completed with six registered outputs.
- A restricted backup set was created at
  `/root/geovis-backups/signoff-20260714T163330Z`. PostGIS restored into an
  isolated database with matching tables, extensions, and 8,500 spatial
  reference rows. The output archive restored into an isolated volume with an
  identical 57-file, 605,042-byte content digest. `.env`, Caddy configuration,
  and the origin certificate pair restored byte-for-byte into an isolated
  directory; backup checksums passed.
- Cloudflare returned the public readiness response, direct-origin readiness
  at `192.3.31.132` matched it, and all 20 uniquely tagged public probes were
  present in the Prime dashboard logs.

The public-path sample shows production requests reaching Prime and found no
sample routed elsewhere. A strict assertion that the former VPS receives zero
background traffic still requires either former-host access logs or
authoritative Cloudflare origin analytics; neither is available on Prime. Keep
former-host retirement as a separate explicitly approved operation.

## Routine operations

```bash
cd /opt/geovis_lm
docker compose ps
docker compose logs --since=30m dashboard worker db
docker compose restart
systemctl status caddy docker
ufw status verbose
```

For an upgrade, confirm a clean Git tree, back up `.env`, Caddy, and both
volumes, fetch `origin`, fast-forward `main`, then run `docker compose build`
and `docker compose up -d`. Repeat all validators and smoke/persistence checks
before changing traffic.

## Backups

Stop writes or use database-consistent tooling. Back up PostGIS with
`pg_dump`, archive the output volume from a temporary container, and copy the
root-only `.env` and Caddyfile into restricted storage. Record the deployed Git
commit. Test restoration periodically; a volume listing alone is not a backup.

The `2026-07-14` restore drill used a custom-format `pg_dump`, a compressed
archive of `geovis_lm_geovis_outputs`, and restricted copies of `.env`, Caddy,
and the origin certificate pair. Restores must target scratch databases,
volumes, and directories first. Compare database objects, output content
digests, and configuration bytes before accepting a backup set. Remove only the
scratch targets after validation; never overwrite the production volumes as
part of a drill.

## Rollback

For traffic rollback, restore the previous Cloudflare/DNS origin without
deleting Prime, then verify the former endpoint. To roll Prime back locally:

```bash
cd /opt/geovis_lm
docker compose down
git switch main
git reset --keep <previous-validated-commit>
docker compose build
docker compose up -d
docker compose ps
```

`docker compose down` must not use `--volumes`; both named volumes and `.env`
must remain. Restore `/etc/caddy/Caddyfile` from `/root/geovis-backups/`, run
`caddy validate`, and reload Caddy if proxy rollback is required. If data must
be rolled back, restore PostGIS and artifacts from the matching tested backup
instead of deleting volumes.
