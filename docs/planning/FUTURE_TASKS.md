# GeoVisLM Future Tasks

These tasks are not current priority work. Move items into `docs/planning/PRIORITY_TASKS.md` when they become active.

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Future Queue

### `[TODO]` Investigate NumPy 2.5 MaskedArray Deprecation Warnings

Goal: keep the test suite warning-clean and avoid future NumPy compatibility breaks.

Acceptance criteria:

* Identify whether warnings originate from GeoVisLM code or third-party geospatial dependencies.
* If from GeoVisLM code, update array handling to use `np.reshape(..., copy=False)` or another supported path.
* If from dependencies, document the upstream source and pin or upgrade strategy.
* Test suite runs without unexpected NumPy deprecation warnings, or warnings are intentionally filtered with justification.

Notes:

* Current warnings are dependency/runtime deprecation warnings from NumPy under `.venv/lib/python3.12/site-packages/numpy/ma/core.py`, triggered by `tests/test_dashboard_operational.py`.
* These warnings did not fail the suite during the priority queue completion validation.

### `[TODO]` Train First GeoMiniLM Prototype

Goal: train or fine-tune a small prototype language model on GeoMiniLM workflow examples to generate structured GIS and visualization workflows.

Build when active:

* Add training package under:

  * `geovis_lm/model/`
* Add training script, for example:

  * `scripts/train_geominilm.py`
* Use the dataset under:

  * `data/geominilm/starter_workflows.jsonl`
* Add preprocessing utilities to convert JSONL examples into prompt/completion or instruction/response format.
* Start with a small local-friendly model or adapter-based fine-tuning path.
* Save model artifacts under:

  * `outputs/models/geominilm/`
* Add generated sample outputs under:

  * `outputs/model_samples/`
* Document hardware assumptions and limitations.

Suggested CLI:

```bash
python scripts/train_geominilm.py \
  --dataset data/geominilm/starter_workflows.jsonl \
  --output-dir outputs/models/geominilm
```

Acceptance criteria:

* Dataset loader reads all GeoMiniLM JSONL examples.
* Training script has a working `--help`.
* Prototype training path is documented.
* Model output directory is created.
* At least one sample inference can generate a structured workflow response.
* If full training is not possible locally, a dry-run or preprocessing validation path exists.

Validation:

```bash
python3 -m py_compile geovis_lm/model/dataset.py
python3 scripts/train_geominilm.py --help
python3 scripts/train_geominilm.py --dataset data/geominilm/starter_workflows.jsonl --dry-run
```

---

### `[TODO]` Add Model Evaluation Suite

Goal: compare GeoMiniLM-generated workflow outputs against expected workflow JSON records so model quality can be measured.

Build when active:

* Add evaluation package under:

  * `geovis_lm/eval/`
* Add evaluator module, for example:

  * `geovis_lm/eval/workflow_eval.py`
* Add evaluation script:

  * `scripts/evaluate_geominilm.py`
* Compare model outputs against expected workflow fields:

  * instruction relevance
  * required input usage
  * ordered workflow structure
  * tool correctness
  * output path correctness
  * explanation quality
* Support JSON/Markdown evaluation reports.
* Store evaluation results under:

  * `outputs/eval/`
* Add scoring rubric documentation.

Suggested CLI:

```bash
python scripts/evaluate_geominilm.py \
  --expected data/geominilm/starter_workflows.jsonl \
  --predictions outputs/model_samples/predictions.jsonl \
  --output outputs/eval/geominilm_eval.md
```

Acceptance criteria:

* Evaluation script reads expected and predicted JSONL files.
* Missing required fields are detected.
* Workflow step mismatches are reported.
* Summary score or pass/fail rubric is generated.
* Evaluation report is written to disk.
* README or eval documentation explains the scoring approach.

Validation:

```bash
python3 -m py_compile geovis_lm/eval/workflow_eval.py
python3 scripts/evaluate_geominilm.py --help
```

---

### `[TODO]` Add Demo Video and Portfolio Page

Goal: create a polished demo package that shows GeoVisLM as a portfolio-ready AI geospatial visualization project.

Build when active:

* Add portfolio documentation under:

  * `docs/portfolio/`
* Add demo script outline:

  * `docs/portfolio/DEMO_SCRIPT.md`
* Add screenshot checklist:

  * terrain analysis outputs
  * QGIS map view
  * ParaView render
  * generated report
  * dashboard, when available
* Add project page content:

  * problem statement
  * project goals
  * architecture
  * workflow screenshots
  * technical stack
  * current limitations
  * next steps
* Add README section linking to the portfolio page.
* Store demo assets under:

  * `docs/portfolio/assets/`

Suggested files:

```text
docs/portfolio/PROJECT_PAGE.md
docs/portfolio/DEMO_SCRIPT.md
docs/portfolio/SCREENSHOT_CHECKLIST.md
docs/portfolio/assets/
```

Acceptance criteria:

* Portfolio page explains what GeoVisLM does.
* Demo script walks through the full terrain workflow.
* Screenshot checklist exists.
* README links to the portfolio documentation.
* Project is presentable without requiring live infrastructure.

Validation:

```bash
test -f docs/portfolio/PROJECT_PAGE.md
test -f docs/portfolio/DEMO_SCRIPT.md
test -f docs/portfolio/SCREENSHOT_CHECKLIST.md
```

---

### `[BLOCKED]` Install/check system GDAL tools when sudo access is available

Goal: install and verify system GDAL command-line tools once interactive sudo access is available.

Blocked reason: this requires interactive sudo access in the target environment.

Build when unblocked:

* Install GDAL command-line tools through the system package manager.
* Verify:

  * `gdalinfo`
  * `ogrinfo`
* Document installed versions.
* Confirm GDAL can inspect:

  * sample DEM GeoTIFF
  * sample vector file, if available
* Add setup notes to README or environment docs.

Suggested commands:

```bash
sudo apt update
sudo apt install -y gdal-bin

gdalinfo --version
ogrinfo --version
gdalinfo data/sample/sample_dem.tif
```

Acceptance criteria:

* `gdalinfo --version` works.
* `ogrinfo --version` works.
* `gdalinfo data/sample/sample_dem.tif` can inspect the sample DEM.
* Setup documentation records the requirement and verification commands.

Validation:

```bash
gdalinfo --version
ogrinfo --version
gdalinfo data/sample/sample_dem.tif
```

## Dashboard and Workflow Enhancements

### `[TODO]` Add Project Sharing and Report Comments

Goal: allow users to invite colleagues to view specific analysis projects and leave comments on Markdown reports.

Build:

- Project-level sharing permissions
- Invite by email
- Read-only collaborator access
- Markdown report comment threads
- Comment author, timestamp, and resolved status
- Activity history for shared projects

Acceptance criteria:

- User can invite a colleague to a specific analysis project.
- Invited collaborator can view only shared projects.
- Collaborator can leave comments on Markdown reports.
- Comments are saved with author and timestamp.
- Project owner can resolve or delete comments.

Dependencies:

- Authentication
- User accounts
- Project permissions
- Markdown report generator

Why future: this is a collaboration feature and should wait until core analysis/reporting works.
