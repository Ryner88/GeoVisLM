# GeoVisLM Priority Tasks

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Current Priority Queue

### 1. `[IN-PROGRESS]` Add Project Sharing and Report Comments

Goal: let owners invite collaborators to individual projects and discuss
generated reports without weakening current tenant isolation.

Why now: first-party accounts, roles, project ownership, and production account
policy are complete. Collaboration is the next high-value product capability,
but it must build on explicit project-level authorization and auditability.

Build:

* Project membership with owner-managed invitations and read-only collaborator
  access.
* Markdown report comment threads with author, timestamp, edit history, and
  resolved state.
* Activity/audit events for invitations, membership changes, comments, and
  moderation.
* Operator-safe handling for invitations when public signup remains disabled.

Current slice:

* Project memberships and invitations are implemented and committed:
  existing-account invitations, owner-controlled revocation, read-only
  collaborator access, enumeration-resistant authorization failures, and
  project membership audit events.
* Report comments are implemented: Markdown comments attached to generated
  reports, author/timestamp metadata, immutable edit history, sanitized HTML
  rendering, owner moderation, concealed inaccessible resources, and audit
  events for create/edit/resolve/reopen/delete.
* Keep this task `[IN-PROGRESS]` until the final cross-tenant regression,
  merge, Prime deployment, and production smoke/readiness slice passes.

Acceptance criteria:

* Owners can invite an existing account to one project and revoke access.
* Collaborators can view only explicitly shared projects and cannot mutate
  owner-only resources.
* Authorized users can add comments; owners can resolve or delete them.
* Cross-project and cross-user access attempts remain denied without leaking
  resource existence.
* Authorization, invitation, comment, audit, and regression tests pass.
