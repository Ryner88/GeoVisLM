# GeoVisLM Future Tasks

These tasks are not current priority work. Move items into
`docs/planning/PRIORITY_TASKS.md` when they become active.

Status labels:

* `[NEXT]` next task to start
* `[TODO]` not started
* `[TODO-BLOCKED]` not started until its explicit gate passes
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Future Queue

### 4. `[TODO]` Add Production Backup, Restore, and Retention Validation

Goal: prove production data can be recovered before additional collaboration and
AI-assisted workflow activity accumulate more state.

Build when active:

* Test PostGIS backup creation.
* Test output-volume backup creation.
* Perform an isolated restore drill covering both PostGIS and retained output
  files.
* Define retention and cleanup rules.
* Document restore steps, expected timing, and verification checks.

Acceptance criteria:

* Backup creation succeeds for PostGIS and retained output files.
* An isolated restore environment successfully restores both data stores.
* Restored database records and retained output files are verified end to end.
* Retention and cleanup rules are documented.
* Prime production state is not modified during the restore drill.

### 5. `[TODO]` Improve the New Analysis and Batch Upload Experience

Goal: make uploads and analysis setup clearer and more robust for larger
datasets and multi-file geospatial inputs.

Build when active:

* Support batch datasets and shapefile bundles.
* Improve validation feedback.
* Add upload progress.
* Define quotas.
* Document cleanup behavior for failed or abandoned uploads.

### 6. `[TODO]` Add Project Timeline and Collaboration Notifications

Goal: make collaboration activity visible and actionable across projects.

Build when active:

* Add a unified history for uploads, runs, outputs, invitations, membership
  changes, and report comments.
* Notify users about invitations.
* Notify users about completed runs.
* Notify users about comment activity.

### 7. `[TODO]` Create GeoVisLM Demo Video and Portfolio Page

Goal: create a polished demo package after the workflow and AI-assisted
experience are stable.

Build when active:

* Add portfolio documentation under `docs/portfolio/`.
* Add `docs/portfolio/DEMO_SCRIPT.md` covering the complete terrain workflow.
* Add a screenshot checklist for dashboard, terrain/risk outputs, QGIS,
  ParaView, generated reports, collaboration, and AI-assisted recommendations.
* Add a project page covering the problem, architecture, technical stack,
  workflows, limitations, and next steps.
* Store demo assets under `docs/portfolio/assets/` and link the page from the
  README.

Acceptance criteria:

* Portfolio page explains the current GeoVisLM product accurately.
* Demo script walks through a complete validated workflow.
* Screenshot checklist and required assets exist.
* README links to the portfolio documentation.
* The project remains presentable without requiring live infrastructure.

Maintenance note: the pending Prime kernel reboot remains separate maintenance,
not a GeoVisLM feature priority.
