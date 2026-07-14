# GeoVisLM Priority Tasks

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Current Priority Queue

### 0. `[IN-PROGRESS]` Finalize Prime account policy and production sign-off

Prime, Cloudflare Full (strict) Origin CA TLS, public readiness, first-party
owner login/logout, invalid-password rejection, Secure/HttpOnly cookies,
token-backed authentication, public worker workflow, artifact access, and
restart persistence are validated. Decide the production signup policy,
invite-code requirement, admin provisioning procedure, and recovery flow using
the first-party authentication code already present on `main`; do not enable
open signup by default. The production owner credential was not recorded.

Acceptance criteria:

- [x] A first-party production account can log in and log out through Cloudflare.
- Signup/invite/admin/recovery policy is documented and tested.
- Public production validation is formally signed off after an observation period.

### 0a. `[TODO]` Retire former GeoVis deployment after observation period

Keep the former server intact as the immediate rollback target. Retirement
requires a completed observation period, successful production-account sign-in,
confirmed backups, and explicit approval. Do not combine retirement with the
Prime cutover validation task.
