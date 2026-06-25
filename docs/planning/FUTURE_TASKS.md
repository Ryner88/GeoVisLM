# GeoVisLM Future Tasks

These tasks are not current priority work. Move items into `docs/planning/PRIORITY_TASKS.md` when they become active.

Status labels:

* `[TODO]` not started
* `[IN-PROGRESS]` actively being worked
* `[BLOCKED]` cannot move without another fix or decision
* `[DONE]` completed and ready to move into `docs/planning/FIXED_TASKS.md`

## Future Queue

### `[TODO]` Add Flood Risk Workflow

Goal: combine DEM-derived terrain outputs, river proximity, slope, and building footprint overlays into a basic flood-risk analysis workflow.

Build when active:

* Add flood workflow module, for example:

  * `geovis_lm/workflows/flood_risk.py`
* Accept inputs:

  * DEM raster
  * river/stream vector layer
  * optional building footprint vector layer
  * optional administrative boundary or area-of-interest layer
* Generate derived outputs:

  * slope raster
  * river buffer layer
  * low-elevation mask or relative elevation classification
  * flood-risk raster or vector layer
* Classify flood risk into stable classes:

  * low
  * medium
  * high
* Export outputs under a predictable run folder:

  * `outputs/runs/<run_id>/flood/`
* Add report support for flood-risk outputs.
* Add GeoMiniLM starter examples for flood-risk workflows.

Suggested CLI:

```bash
python scripts/run_flood_risk.py \
  --dem data/sample/sample_dem.tif \
  --rivers data/sample/rivers.geojson \
  --buildings data/sample/buildings.geojson \
  --output-dir outputs/runs/sample_flood/flood
```

Acceptance criteria:

* Workflow loads a DEM and at least one river vector layer.
* River buffers are generated.
* DEM/slope-derived terrain risk is combined with river proximity.
* Flood-risk output is written to disk.
* Output classes are documented.
* Workflow works without dashboard or PostGIS.
* README or workflow documentation explains input requirements and limitations.

Validation:

```bash
python3 -m py_compile geovis_lm/workflows/flood_risk.py
python3 scripts/run_flood_risk.py --help
```

---

### `[TODO]` Add Wildfire Risk Workflow

Goal: combine slope, vegetation/fuel data, wind or sensor inputs, and proximity layers into a basic wildfire-risk analysis workflow.

Build when active:

* Add wildfire workflow module, for example:

  * `geovis_lm/workflows/wildfire_risk.py`
* Accept inputs:

  * DEM raster
  * vegetation/fuel raster or vector layer
  * optional wind/sensor data file
  * optional roads/buildings/settlements vector layer
* Generate derived outputs:

  * slope raster
  * vegetation/fuel classification
  * proximity-to-assets layer
  * wildfire-risk raster or vector layer
* Classify wildfire risk into stable classes:

  * low
  * medium
  * high
  * extreme, if justified by input data
* Export outputs under:

  * `outputs/runs/<run_id>/wildfire/`
* Add report support for wildfire-risk outputs.
* Add GeoMiniLM starter examples for wildfire workflows.

Suggested CLI:

```bash
python scripts/run_wildfire_risk.py \
  --dem data/sample/sample_dem.tif \
  --vegetation data/sample/vegetation.geojson \
  --assets data/sample/buildings.geojson \
  --output-dir outputs/runs/sample_wildfire/wildfire
```

Acceptance criteria:

* Workflow loads DEM and vegetation/fuel input.
* Slope is incorporated into risk scoring.
* Proximity layers can be incorporated when available.
* Wildfire-risk output is written to disk.
* Classification logic is documented.
* Workflow works without dashboard, QGIS, or PostGIS.
* README or workflow documentation explains limitations.

Validation:

```bash
python3 -m py_compile geovis_lm/workflows/wildfire_risk.py
python3 scripts/run_wildfire_risk.py --help
```

---

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
