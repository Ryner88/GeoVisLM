[DONE] Prime VPS migration/import and staging validation
- Inspected Prime resources, packages, services, firewall, and ports before changes.
- Installed Docker Engine, Docker Compose v2, and Caddy; left Nginx disabled/absent.
- Synchronized clean `main` checkout at `/opt/geovis_lm` and generated root-only deployment secrets.
- Deployed healthy dashboard, persistent worker, and PostGIS services with localhost-only dashboard binding.
- Passed compilation, 35 tests, deployment/Compose validation, worker smoke, and restart persistence checks.
- Configured and validated Caddy plus UFW rules for SSH, HTTP, and HTTPS without exposing port 8000.
- Cloudflare public readiness and the complete queued-analysis workflow pass; the old deployment remains available pending explicit retirement approval.

[DONE] Prime Cloudflare Origin CA TLS
- Configured Full (strict) origin TLS for `geovis.nextgenbytes.me` with root-owned Caddy-readable certificate files outside Git.
- Public and direct-origin GET readiness return HTTP 200; HEAD readiness returns the expected method-not-allowed response.
- Validated public token session login/logout, queued worker processing, six artifacts, downloads/previews, and restart persistence.
- Full production sign-off remains pending first-party account provisioning/login validation because Prime currently has no account records.

[DONE] Private VPS staging deployment
- Cloned GeoVis LM to /opt/geovis_lm
- Installed Docker/Compose on the VPS
- Started dashboard, worker, and db services via Docker Compose
- Bound dashboard to localhost (127.0.0.1:8000)
- Routed Cloudflare hostname through Caddy on 80/443
- Enabled staging auth token (stored in /opt/geovis_lm/.env)
- Verified validator and worker smoke test pass

Timestamp: 2026-07-02T19:50:26Z

[COMPLETE] Private VPS staging verified
- External DNS resolves to Cloudflare and Caddy routes to dashboard
- Cloudflare Access login present (heuristic detected)
- Direct VPS IP and port 8000 are not publicly reachable

Completed at: 2026-07-02T19:52:12Z
