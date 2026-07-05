# GeoVisLM Priority Tasks

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Current Priority Queue

### 1. `[TODO]` Add First-Party Login and Signup for GeoVis LM

Goal: add real application-level authentication so users can sign up, log in, log out, and access only their own dashboard runs, uploads, and outputs. Cloudflare Access should remain useful as an outer staging gate, but GeoVis LM should no longer rely only on that or a shared token.

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

### 2. `[TODO]` Add Flood Risk Workflow

Goal: combine DEM-derived terrain outputs, river proximity, slope, and optional building footprint overlays into a basic flood-risk analysis workflow.

Acceptance criteria:

- Workflow loads a DEM and at least one river or stream vector layer.
- River buffers are generated.
- DEM/slope-derived terrain risk is combined with river proximity.
- Flood-risk output is written to a run-scoped output folder.
- Output classes are documented.
- Workflow works without dashboard or PostGIS.
- README or workflow documentation explains input requirements and limitations.

### 3. `[TODO]` Add Wildfire Risk Workflow

Goal: combine slope, vegetation/fuel data, optional wind or sensor inputs, and proximity layers into a basic wildfire-risk analysis workflow.

Acceptance criteria:

- Workflow loads DEM and vegetation/fuel input.
- Slope is generated or reused from terrain workflow logic.
- Vegetation/fuel classes are normalized into stable risk inputs.
- Wildfire-risk output is written to disk.
- Output classes are documented.
- Workflow works without dashboard or PostGIS.
- README or workflow documentation explains input requirements and limitations.
