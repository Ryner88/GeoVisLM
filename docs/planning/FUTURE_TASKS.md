# GeoVisLM Future Tasks

These tasks are not current priority work. Move items into
`docs/planning/PRIORITY_TASKS.md` when they become active.

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Future Queue

### `[TODO]` Add Demo Video and Portfolio Page

Goal: create a polished demo package that shows GeoVisLM as a portfolio-ready
AI geospatial visualization project.

Why later: dependency health, measurable model quality, the first model
prototype, production diagnostics, and secure collaboration provide more direct
engineering and user value. Prepare the portfolio package after those priority
milestones produce stable material to demonstrate.

Build when active:

* Add portfolio documentation under `docs/portfolio/`.
* Add `docs/portfolio/DEMO_SCRIPT.md` covering the complete terrain workflow.
* Add a screenshot checklist for dashboard, terrain/risk outputs, QGIS,
  ParaView, and generated reports.
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

Validation:

```bash
test -f docs/portfolio/PROJECT_PAGE.md
test -f docs/portfolio/DEMO_SCRIPT.md
test -f docs/portfolio/SCREENSHOT_CHECKLIST.md
```
