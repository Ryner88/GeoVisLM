[STAGED] Prime VPS migration/import completed pending public origin cutover
- Inspected Prime resources, packages, services, firewall, and ports before changes.
- Installed Docker Engine, Docker Compose v2, and Caddy; left Nginx disabled/absent.
- Synchronized clean `main` checkout at `/opt/geovis_lm` and generated root-only deployment secrets.
- Deployed healthy dashboard, persistent worker, and PostGIS services with localhost-only dashboard binding.
- Passed compilation, 35 tests, deployment/Compose validation, worker smoke, and restart persistence checks.
- Configured and validated Caddy plus UFW rules for SSH, HTTP, and HTTPS without exposing port 8000.
- Public Cloudflare HTTPS remains blocked pending origin/DNS and trusted origin TLS cutover; the old deployment must remain available.

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
