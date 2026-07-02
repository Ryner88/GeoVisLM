[DONE] Private VPS staging deployment
- Cloned GeoVis LM to /opt/geovis_lm
- Installed Docker/Compose on the VPS
- Started dashboard, worker, and db services via Docker Compose
- Bound dashboard to localhost (127.0.0.1:8000)
- Routed Cloudflare hostname through Caddy on 80/443
- Enabled staging auth token (stored in /opt/geovis_lm/.env)
- Verified validator and worker smoke test pass

Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
