# GeoMiniLM Production Gate - 2026-08-11

## Candidate

- Candidate commit: `0bc44b0f563faaa1dcd7b45106c79777dbc9c35e`
- Branch: `main`
- Upstream sync before gate: `HEAD == origin/main == 0bc44b0f563faaa1dcd7b45106c79777dbc9c35e`
- Gate type: formal one-shot frozen production evaluation
- Frozen validation set: `data/geominilm/validation_workflows.jsonl`
- Frozen validation set SHA-256: `57db85e9ae38c2a8b9e36c254a39fccef26540780942ac232e942e27484845bf`
- Tuning after frozen-set read: none
- Deployment decision: blocked

Candidate `0bc44b0` was evaluated once against the frozen production
validation set on 2026-08-11. No model, retrieval, template, scorer, threshold,
confidence, or category-floor changes were made from the frozen-set outcome.

## Command

```bash
timeout 120 .venv/bin/python scripts/train_geominilm.py \
  --dataset data/geominilm/starter_workflows.jsonl \
  --extra-training-data data/geominilm/training_expansion_workflows.jsonl \
  --validation-set data/geominilm/validation_workflows.jsonl \
  --eval-dir outputs/eval/geominilm_validation \
  --output-dir outputs/models/geominilm_validation \
  --predictions-dir outputs/model_samples/geominilm_validation \
  --production-pass-threshold 0.75 \
  --minimum-threshold-margin 0.01 \
  --minimum-validation-records 12
```

Result:

- CLI status: completed
- Records: `29` training/development records
- Frozen validation records: `14`
- Threshold failures: `10`
- Records with findings: `14`

## Integrity

- Manifest check: pass
- Manifest mismatches: none
- Duplicate/leakage split validation: pass
- Duplicate/leakage issues: none
- Oracle sanity score: `1.0000`
- Honest baseline score: `0.3682`
- Candidate beats honest baseline: true

## Gate Results

- Primary metric: `trained_validation_score`
- Candidate score: `0.6475`
- Locked pass threshold: `0.7500`
- Minimum threshold margin: `0.0100`
- Required metric value: `0.7600`
- Delta versus honest baseline: `+0.2793`
- Delta versus reference heldout: `+0.1532`
- All records passed: false
- Category floor passed: false
- Confidence gate passed: false
- Dashboard integration allowed: false

Authorization checks:

| Check | Result |
| --- | --- |
| Beats honest baseline | pass |
| Passes required metric value | fail |
| Has expanded validation set | pass |
| All records passed | fail |
| Manifest check | pass |
| Split/leakage validation | pass |
| Category floor | fail |
| Confidence gate | fail |

## Category Results

| Category | Score | Failures |
| --- | ---: | ---: |
| `gis_hillshade_and_single_raster_products` | `0.6976` | `1/2` |
| `gis_risk_overlay_and_reclassification` | `0.5781` | `2/2` |
| `paraview_render_variants` | `0.7155` | `2/3` |
| `qgis_styling_and_layout_exports` | `0.6555` | `3/4` |
| `reporting_summaries` | `0.5817` | `2/3` |

All category scores remained below the locked `0.7500` category floor.

## Confidence

- Method: `prediction_confidence`
- Confidence records: `14/14`
- Expected calibration error: `0.6271`
- Maximum calibration error: `0.6271`
- Confidence gate limits: ECE `<= 0.2000`, MCE `<= 0.3500`
- Confidence gate: fail

All validation predictions landed in the `0.8000-1.0000` confidence bin with
average confidence `0.9129` and pass accuracy `0.2857`, indicating severe
over-confidence on the frozen production set.

## Failed Validation Records

| Record | Score | Primary findings |
| --- | ---: | --- |
| `validation-gis-flood-zonal-summary-008` | `0.5981` | tool/output mismatch, partial ordered steps |
| `validation-gis-reproject-cog-007` | `0.5938` | step-count mismatch, tool/output mismatch |
| `validation-gis-wildfire-vector-002` | `0.5581` | tool/output mismatch, partial ordered steps |
| `validation-paraview-clip-cross-section-012` | `0.7411` | tool/output mismatch, partial ordered steps |
| `validation-paraview-slope-colorbar-011` | `0.5899` | tool/output mismatch, partial ordered steps |
| `validation-qgis-atlas-export-009` | `0.6053` | tool/output mismatch, partial ordered steps |
| `validation-qgis-layer-transparency-003` | `0.6684` | tool/output mismatch, partial ordered steps |
| `validation-qgis-vector-labels-010` | `0.5506` | tool/output mismatch, partial ordered steps |
| `validation-report-eval-manifest-014` | `0.4439` | tool/output mismatch, partial ordered steps |
| `validation-report-qgis-export-review-013` | `0.5373` | tool/output mismatch, partial ordered steps |

These records are production-gate evidence only. They must not be used to tune
the next candidate directly.

## Artifact Hashes

The generated artifacts are under ignored `outputs/` paths; checksums are
recorded here for auditability.

| Artifact | SHA-256 |
| --- | --- |
| `outputs/eval/geominilm_validation/evaluation_manifest.json` | `ae5c4f99fbbb99cfbfae76134b5b8eb17e37ac90bc17f6b89d70c0eedf8c7ffc` |
| `outputs/eval/geominilm_validation/manifest_check.json` | `1feafee3bb9162637a7ed8e849f3e3c2e7a92a580ccbfaa5468f78203fcfbc85` |
| `outputs/eval/geominilm_validation/split_validation.json` | `c2b0cd5c9aed8b7c22cb2d201f8d5190bd4c5bc2b8fc1c82dfc0c3809795c971` |
| `outputs/eval/geominilm_validation/evaluation_report.json` | `8b3825530e3e459e4adababcd24c21ed265da525bdcf3fee87532b53939b1c1c` |
| `outputs/eval/geominilm_validation/experiment_comparison.json` | `8ef9d61885677f836f70ba53fff497ec53320a4c0505878a2f01a89371281fab` |
| `outputs/eval/geominilm_validation/confidence_calibration.json` | `39d572ddc41aa2472a5f838c45fa7f83a68e85a5880644ece95c0cd1041a5a34` |
| `outputs/eval/geominilm_validation/production_decision.json` | `db345bf5b95cff158e2ea334b958b6210d54aef663ea23a2e1b9161b696f7040` |
| `outputs/model_samples/geominilm_validation/validation_predictions.jsonl` | `2529b0b23dc6d1c63d23a299a6a3d32369f734a884085e26d7a07d5b646e7ba0` |
| `outputs/model_samples/geominilm_validation/honest_baseline_predictions.jsonl` | `76a5ae70e14d848cec2589c7730a3ec7f17855e798322825d82fe10fcb6bea69` |
| `outputs/models/geominilm_validation/validation_experiment_metadata.json` | `c440d07ee295842403f11fe1eaad9a44a925caa8a4a2a609d7e81325b4ff2c03` |

## Decision

Candidate `0bc44b0` is not deployment-eligible. Prime deployment and dashboard
GeoMiniLM recommendation integration remain blocked.

Next work should be a new development-only cycle that improves generalized
workflow coverage and calibration without reading or tuning against the frozen
validation records. The development plan should focus on:

- broader development-authored route coverage for raster reprojection/COG,
  wildfire overlays, QGIS atlas/labels/transparency, ParaView scalar/clip
  variants, and reporting review workflows;
- route-specific confidence calibration using development-only grouped
  holdouts;
- semantic/executability checks for tool, output, and step-order preservation;
- locked thresholds and category floors before any future sealed production
  gate.
