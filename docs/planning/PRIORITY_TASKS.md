# GeoVisLM Priority Tasks

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Current Priority Queue

### 1. `[IN-PROGRESS]` Deployment Security Hardening

Goal: finish deployment security hardening after server-side validation.

Current status:

- Implemented on branch `securityfixes`.
- Commit: `151d54a Fix deployment security findings`.
- App-level validation passed locally.
- Server validation is pending because `securityfixes` is not available on `/opt/geovis_lm` yet.

Remaining work:

- Push or otherwise make `securityfixes` available on the VPS.
- Fetch and check out the branch under `/opt/geovis_lm`.
- Set required deployment secrets:
  - `GEOVIS_AUTH_TOKEN`
  - `POSTGRES_PASSWORD`
- Run Docker Compose validation on the server.
- Move this item to `docs/planning/FIXED_TASKS.md` after server validation passes.

Acceptance criteria:

- Docker Compose validation passes on the VPS with required secrets set.
- The deployed stack no longer relies on known default auth or database credentials.
- Session cookies are configured securely for HTTPS deployment.
- The Docker validation subprocess hardening remains in place.

### 2. `[DONE]` Add First-Party Login and Signup for GeoVis LM

Goal: add real application-level authentication so users can sign up, log in, log out, and access only their own dashboard runs, uploads, and outputs. Cloudflare Access should remain useful as an outer staging gate, but GeoVis LM should no longer rely only on that or a shared token.

Implemented first-party authentication for the FastAPI dashboard while keeping bearer-token API authentication available for service clients.

Scope:

- Add a users table with email, password hash, display name, role, and activation fields.
- Use a standard password hashing library and never store plaintext passwords.
- Add secure session-based authentication with HTTP-only cookies and a configurable session secret.
- Add signup, login, logout, and protected route handling.
- Add optional invite-code-based signup controls for staging.
- Associate runs, uploads, and outputs with the authenticated user.
- Add tests for signup, login, logout, unauthorized access, and per-user isolation.
- Update deployment docs and environment examples with auth settings.

Acceptance criteria:

- A new user can sign up when signup is enabled.
- Signup can be restricted by invite code.
- A user can log in and log out successfully.
- Dashboard and API routes are protected for unauthenticated users.
- Runs, uploads, and outputs are associated with the logged-in user.
- Users cannot access another user’s outputs or runs.
- Passwords are securely hashed and not exposed.
- Environment documentation lists the auth-related settings and secret rotation guidance.

Implementation notes:

- Added file-backed first-party users with normalized email addresses, Argon2 password hashes, display names, roles, active flags, and activation metadata.
- Added a `geovis_users` PostGIS schema table for database-backed deployments.
- Added `/signup`, `/login`, `/logout`, `/api/auth/signup`, `/api/auth/login`, and `/api/auth/me`.
- Added signed HTTP-only session cookies using `GEOVIS_SESSION_SECRET` with `GEOVIS_SECRET_KEY`/`GEOVIS_AUTH_TOKEN` fallback compatibility.
- Added `GEOVIS_SIGNUP_ENABLED` and `GEOVIS_SIGNUP_INVITE_CODE` controls.
- Added tests for signup, invite-code gating, login, logout, protected routes, and per-user project isolation.
- Updated README and deployment/storage docs with auth settings and session-secret rotation guidance.

### 3. `[DONE]` Add Flood Risk Workflow

Goal: combine DEM-derived terrain outputs, river proximity, slope, and optional building footprint overlays into a basic flood-risk analysis workflow.

Acceptance criteria:

- Workflow loads a DEM and at least one river or stream vector layer.
- River buffers are generated.
- DEM/slope-derived terrain risk is combined with river proximity.
- Flood-risk output is written to a run-scoped output folder.
- Output classes are documented.
- Workflow works without dashboard or PostGIS.
- README or workflow documentation explains input requirements and limitations.

Implementation notes:

- Added a filesystem-first flood-risk workflow that combines DEM-derived low elevation, flat terrain, and river-buffer proximity into `flood_risk.tif`.
- River buffers are generated as `river_buffers.geojson`.
- Added a JSON summary with output classes, model weights, inputs, outputs, and limitations.
- Added dashboard adapter support for `workflow_type=flood_risk` while keeping the workflow runnable from `scripts/run_flood_risk.py`.
- Documented input requirements, output classes, and limitations in `docs/RISK_WORKFLOWS.md`.

### 4. `[DONE]` Add Wildfire Risk Workflow

Goal: combine slope, vegetation/fuel data, optional wind or sensor inputs, and proximity layers into a basic wildfire-risk analysis workflow.

Acceptance criteria:

- Workflow loads DEM and vegetation/fuel input.
- Slope is generated or reused from terrain workflow logic.
- Vegetation/fuel classes are normalized into stable risk inputs.
- Wildfire-risk output is written to disk.
- Output classes are documented.
- Workflow works without dashboard or PostGIS.
- README or workflow documentation explains input requirements and limitations.

Implementation notes:

- Added a filesystem-first wildfire-risk workflow that combines DEM-derived slope, normalized vegetation/fuel inputs, and optional proximity vectors into `wildfire_risk.tif`.
- Fuel vectors normalize numeric or common text fuel classes into stable low, moderate, and high risk inputs; fuel rasters are reprojected to the DEM grid.
- Added a JSON summary with output classes, normalized fuel metadata, inputs, outputs, and limitations.
- Added dashboard adapter support for `workflow_type=wildfire_risk` while keeping the workflow runnable from `scripts/run_wildfire_risk.py`.
- Documented input requirements, output classes, and limitations in `docs/RISK_WORKFLOWS.md`.
