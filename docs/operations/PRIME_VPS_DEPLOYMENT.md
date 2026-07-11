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
- Token-backed public session login, authenticated dashboard access, and logout
  passed. Prime had zero first-party user account records, so production-account
  email/password login remains a required policy/provisioning check.
- Public terrain run `6f71590b507f442e82b5d648bf78741f` completed through
  the persistent worker with six registered artifacts; previews and downloads
  passed. The completed run and all artifacts survived a Compose restart.
- The default Python urllib user agent received Cloudflare 403; the same public
  workflow passed with a normal identified client user agent.
- Dashboard, worker, PostGIS, Caddy, firewall, and port checks passed with no
  runtime failures in the validation log window.

Do not retire the former deployment until a production account is provisioned
and tested, an observation period completes, and retirement is explicitly
approved.

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
