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
