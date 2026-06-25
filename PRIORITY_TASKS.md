# GeoVisLM Priority Tasks

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `FIXED_TASKS.md`

## Priority Queue

### 1. `[TODO]` Add Batch Upload to New Analysis Page

Goal: allow users to upload and process multiple geospatial files in one analysis workflow instead of submitting files one by one.

Build:

- Multi-file upload field on the New Analysis page
- Batch queue for uploaded files
- Per-file processing status
- Validation for GeoTIFF, GeoJSON, Shapefile bundles, and CSV
- Error handling so one failed file does not stop the full batch
- Grouped outputs under one analysis run

Acceptance criteria:

- User can upload multiple geospatial files at once.
- Each uploaded file shows pending, processing, completed, or failed status.
- Successful files generate outputs under the same analysis run.
- Failed files show readable error messages.
- Dashboard displays the batch as one grouped run.

Why priority: batch upload improves the core analysis workflow and makes the dashboard feel useful.

---

### 2. `[TODO]` Create GIS and ParaView Templates Library

Goal: allow users to save reusable combinations of GIS processing steps and ParaView visualization settings.

Build:

- Template model or JSON storage format
- Template list page
- Template detail view
- Save current workflow as template
- Apply template to a new dataset
- Import/export template JSON

Acceptance criteria:

- User can save a named workflow template.
- Template stores GIS steps and ParaView settings.
- User can apply a saved template to a compatible new dataset.
- Template output is reproducible.
- Template data is documented.

Why priority: templates turn GeoVisLM from a one-off analyzer into a reusable analysis platform.

---

### 3. `[TODO]` Create Project Timeline View

Goal: create a dashboard timeline that maps task status and expected completion dates for ongoing geospatial analysis work.

Build:

- Timeline page or dashboard panel
- Task/project status model
- Expected completion date field
- Timeline grouping by project
- Filters for open, in-progress, blocked, completed, and overdue work

Acceptance criteria:

- User can see ongoing geospatial tasks in timeline order.
- Each timeline item shows project, status, expected completion date, and linked analysis run.
- Blocked and overdue items are visually identifiable.
- Timeline links back to the related project or analysis page.

Why priority: timeline view improves project management once multiple analysis runs exist.
