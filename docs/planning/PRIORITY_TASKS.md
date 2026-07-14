# GeoVisLM Priority Tasks

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Current Priority Queue

### 0. `[TODO]` Retire former GeoVis deployment after observation period

Keep the former server intact as the immediate rollback target. Retirement
requires explicit approval. The observation period, production-account sign-in,
and a full isolated backup/restore drill are complete. Twenty uniquely tagged
public requests all appeared in Prime logs, but strict zero-traffic confirmation
still requires former-host access logs or authoritative Cloudflare origin
analytics. Do not combine retirement with the Prime cutover validation task.
