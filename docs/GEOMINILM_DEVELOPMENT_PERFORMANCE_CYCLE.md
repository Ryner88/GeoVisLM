# GeoMiniLM Development Performance Cycle

## Scope

- Branch: `geominilm-development-performance-cycle`
- Starting point: `c1a03ed`
- Previous production candidate: `428af8d`
- Failed production candidate: `9af23d8`
- Frozen 14-record regression split: off-limits for development selection and
  tuning
- Dashboard integration: blocked until a future formal production gate passes

This cycle used training-derived leave-one-out development evaluation. That
result is now historical: the repaired protocol uses workflow-only scoring,
grouped workflow-family holdouts, and treats template code plus retrieval data as
one versioned candidate. The repaired protocol is implemented, reviewed, and
recorded; future model selection must use this contract.

## Monday Development-Cycle Contract Target

Target: a reviewed development-cycle contract before model selection resumes.
The contract prohibits model, retrieval, template, prompt, threshold, and
category-floor tuning against `data/geominilm/validation_workflows.jsonl`.

Locked protocol for the next cycle:

- Primary score: workflow-only scoring.
- Development split: grouped workflow-family holdouts.
- Per-category floors: locked before candidate evaluation.
- All-record pass: every evaluated record must clear the record-level pass
  requirement.
- Semantic checks: predicted workflows must preserve requested operations,
  parameters, constraints, outputs, and review intent.
- Executability checks: steps must name runnable tools or known application
  operations, valid artifacts or states, and executable ordering.
- Route-aware confidence: retrieval and template routes require separate
  confidence checks; TF-IDF retrieval similarity cannot stand in for template
  output confidence.
- Sealed shadow set: authored and checksum-locked before the gate, hidden from
  development review, disjoint from training and regression records, evaluated
  once per locked candidate, then retired to regression evidence.

Review outcome on 2026-08-11: approved for development use. The frozen
14-record validation set remains off-limits for model, retrieval, template,
prompt, scoring-threshold, confidence-threshold, and category-floor tuning.
Dashboard integration remains blocked until a future locked candidate passes a
formal one-shot production gate on a new sealed shadow set.

## Grouped Workflow-Family Development Baseline

Command:

```bash
timeout 120 .venv/bin/python scripts/train_geominilm.py \
  --dataset data/geominilm/starter_workflows.jsonl \
  --extra-training-data data/geominilm/training_expansion_workflows.jsonl \
  --grouped-held-out-eval \
  --eval-dir outputs/eval/geominilm_grouped_development \
  --output-dir outputs/models/geominilm_grouped_development \
  --predictions-dir outputs/model_samples/geominilm_grouped_development
```

Initial repaired-protocol baseline before development-supported fixes:

- Records: `29`
- Workflow families: `5`
- Prediction routes: `workflow_template: 29`
- Grouped holdout score: `0.9134`
- Threshold failures: `2`
- Expected calibration error: `0.5577`
- Maximum calibration error: `0.5678`

Failure classification:

| Class | Finding | Development-supported action |
| --- | --- | --- |
| Retrieval | No direct retrieval-route failures; grouped folds excluded held-out workflow families and every prediction used the template route. Retrieval similarity was still recorded as template confidence. | Preserve family exclusion and record retrieval similarity separately from template confidence. |
| Template | `report-terrain-summary-010` over-expanded the Markdown report output with source raster paths. | Add a terrain-report template branch that writes only the requested report path. |
| Template | `train-gis-flood-zonal-summary-023` used broad raster/vector summary wording and combined tools where the development target expects rasterstats then GeoPandas output. | Narrow the flood zonal-summary template to rasterstats class counts and GeoJSON output. |
| Scoring | The two threshold failures were caused by partial ordered-step/output/tool overlap under workflow-only scoring, not by missing predictions or schema errors. | Fix template wording and output/tool fields rather than changing scorer weights or thresholds. |
| Confidence | Template predictions used TF-IDF retrieval similarity as confidence, producing severe under-confidence. | Add route-aware `workflow_template_route` confidence and keep `retrieval_similarity` as a separate diagnostic. |

Final grouped development result after development-supported changes:

- Records: `29`
- Workflow families: `5`
- Prediction routes: `workflow_template: 29`
- Grouped holdout score: `0.9287`
- Threshold failures: `0`
- Records with findings: `29`
- Expected calibration error: `0.1010`
- Maximum calibration error: `0.1010`

## 2026-08-17 Reproducible Development Baseline

Preflight:

- Branch at start: `main...origin/main`, clean.
- Commit at start: `a8b43a15f607ec7dbc5e454f7740826daa225346`.
- Frozen regression set exclusion: no command in this run passed
  `--validation-set` or read `data/geominilm/validation_workflows.jsonl`.
  Generated grouped metadata and predictions contained no frozen validation ids.
- Seed: not applicable; the TF-IDF grouped holdout and template route are
  deterministic and expose no random seed parameter.

Baseline reproduction command:

```bash
timeout 120 .venv/bin/python scripts/train_geominilm.py \
  --dataset data/geominilm/starter_workflows.jsonl \
  --extra-training-data data/geominilm/training_expansion_workflows.jsonl \
  --grouped-held-out-eval \
  --eval-dir outputs/eval/geominilm_grouped_development_20260817 \
  --output-dir outputs/models/geominilm_grouped_development_20260817 \
  --predictions-dir outputs/model_samples/geominilm_grouped_development_20260817
```

Reproduced baseline:

- Records: `29`
- Workflow families: `5`
- Route counts: `workflow_template: 29`
- Score: `0.9287`
- Pass threshold: `0.7500`
- Threshold failures: `0`
- Records with findings: `29`
- ECE / max calibration error: `0.1010` / `0.1010`
- Confidence range: `0.8100-0.9200`
- Retrieval similarity diagnostic range: `0.2633-0.5577`

Grouped category floors:

| Family | Records | Average | Minimum | Failures |
| --- | ---: | ---: | ---: | ---: |
| `reporting_summaries` | `4` | `0.8482` | `0.7616` | `0` |
| `qgis_styling_and_layout_exports` | `8` | `0.9123` | `0.7689` | `0` |
| `paraview_render_variants` | `6` | `0.9463` | `0.8803` | `0` |
| `gis_risk_overlay_and_reclassification` | `7` | `0.9561` | `0.9257` | `0` |
| `gis_hillshade_and_single_raster_products` | `4` | `0.9680` | `0.9632` | `0` |

Baseline artifact hashes:

| Artifact | SHA-256 |
| --- | --- |
| `data/geominilm/starter_workflows.jsonl` | `a4903f291bcb67460731b18a8433c26b63f54b84ae2a00baaa10acbbd43499e0` |
| `data/geominilm/training_expansion_workflows.jsonl` | `e15068d596f98bd9308a6a9f42096de6cc34707c3dd593dbe7cc8a32e4afe376` |
| `data/geominilm/failure_taxonomy.json` | `74f5c87c7d35c692f4bdbb106c731d9485c43629a6f25e8ff7b30fab0605796b` |
| `outputs/eval/geominilm_grouped_development_20260817/evaluation_report.json` | `60ad951503628887b861334332b5bdb3d6c550d6265639bfb8e3d3afa25e841c` |
| `outputs/eval/geominilm_grouped_development_20260817/baseline_comparison.json` | `da4e4b197e1a7f268b47802a938042e91a5ada3e3c6ab186235a4af97025ac1a` |
| `outputs/eval/geominilm_grouped_development_20260817/confidence_calibration.json` | `771e02e749327b3b19023bc20cd3ba85573c20fc665502af28b33b1ea3ca152c` |
| `outputs/model_samples/geominilm_grouped_development_20260817/grouped_heldout_predictions.jsonl` | `2cbe3c4698534438e04a95e577eec97e51e732b2bc1a540f503b4c0d10f52558` |
| `outputs/models/geominilm_grouped_development_20260817/grouped_heldout_metadata.json` | `913b4b82f81f28ef4c89a44de9222d8f601934223e5e35f0c655386b43f7a39b` |

Ranked weakness diagnosis from passed-but-low-margin records:

| Rank | Evidence | Class | Risk |
| ---: | --- | --- | --- |
| `1` | `report-terrain-summary-010` scored `0.7616`, only `0.0116` above threshold, with ordered-step, output-path, and explanation partials. | Template output | Reporting templates remain brittle when concise terrain reports and broader QGIS/report language overlap. |
| `2` | `train-qgis-slope-transparency-016` scored `0.7689` before the change, with tool and output mismatches from generic base/overlay wording. | Template output | QGIS family generalization can pass while losing named layer semantics. |
| `3` | `train-report-evaluation-manifest-029` scored `0.8030`; `train-report-combined-risk-019` scored `0.8504`. | Template routing / output | Reporting fallback is broad and may over-include artifacts or review language. |
| `4` | `qgis-map-export-006` scored `0.8086` with output-path partials despite a correct PNG path. | Scoring / template output | Layout export scoring penalizes broad output descriptors appended to exact paths. |
| `5` | All records used `workflow_template`; retrieval similarity ranged only `0.2633-0.5577`. | Retrieval | Grouped development evidence is mostly template evidence; retrieval behavior remains weakly exercised for held-out families. |
| `6` | Lowest-margin records had route confidence up to `0.9200` despite scores as low as `0.7616`; pass/fail ECE was `0.1010`. | Confidence | Pass-calibration looks acceptable because all records pass, but confidence is over-strong relative to score margin on low-margin templates. |

Evidence-backed change selected:

- Implemented one narrow QGIS template branch for requests that explicitly ask
  for slope over hillshade with opacity/transparency.
- Rationale: the branch addresses the second-lowest baseline example without
  touching reporting, scoring, thresholds, retrieval, or frozen regression data.
- Regression coverage:
  `tests/test_geominilm_prototype.py::test_qgis_slope_transparency_template_preserves_hillshade_overlay_details`.

After-change grouped holdout command:

```bash
timeout 120 .venv/bin/python scripts/train_geominilm.py \
  --dataset data/geominilm/starter_workflows.jsonl \
  --extra-training-data data/geominilm/training_expansion_workflows.jsonl \
  --grouped-held-out-eval \
  --eval-dir outputs/eval/geominilm_grouped_development_20260817_after_qgis_transparency \
  --output-dir outputs/models/geominilm_grouped_development_20260817_after_qgis_transparency \
  --predictions-dir outputs/model_samples/geominilm_grouped_development_20260817_after_qgis_transparency
```

After-change result:

- Score: `0.9354`
- Threshold failures: `0`
- Records with findings: `29`
- Route counts: `workflow_template: 29`
- ECE / max calibration error: `0.1010` / `0.1010`
- Changed record: `train-qgis-slope-transparency-016`, `0.7689` to `0.9633`;
  all other record scores were unchanged.

After-change category floors:

| Family | Records | Average | Minimum | Failures |
| --- | ---: | ---: | ---: | ---: |
| `reporting_summaries` | `4` | `0.8482` | `0.7616` | `0` |
| `qgis_styling_and_layout_exports` | `8` | `0.9366` | `0.8086` | `0` |
| `paraview_render_variants` | `6` | `0.9463` | `0.8803` | `0` |
| `gis_risk_overlay_and_reclassification` | `7` | `0.9561` | `0.9257` | `0` |
| `gis_hillshade_and_single_raster_products` | `4` | `0.9680` | `0.9632` | `0` |

After-change artifact hashes:

| Artifact | SHA-256 |
| --- | --- |
| `outputs/eval/geominilm_grouped_development_20260817_after_qgis_transparency/evaluation_report.json` | `62c98d737aa678549fb30aee0ed6c5805decbe5605bc2fbaa3c13ab231de524d` |
| `outputs/eval/geominilm_grouped_development_20260817_after_qgis_transparency/baseline_comparison.json` | `9232bc0e0bbba37150fc7fa87f725789be816f1e35cea7558bec1abfcbd7ce2d` |
| `outputs/eval/geominilm_grouped_development_20260817_after_qgis_transparency/confidence_calibration.json` | `771e02e749327b3b19023bc20cd3ba85573c20fc665502af28b33b1ea3ca152c` |
| `outputs/model_samples/geominilm_grouped_development_20260817_after_qgis_transparency/grouped_heldout_predictions.jsonl` | `67f74b3d7010ed8aadcbffb6a43f1d413744bd2f620d7d59c995112ffb8b2e96` |
| `outputs/models/geominilm_grouped_development_20260817_after_qgis_transparency/grouped_heldout_metadata.json` | `21973127f8b86cf0e39eddd1cab93981f4706cfae014364abaa06052436c289f` |

Verification:

```bash
timeout 120 .venv/bin/python -m pytest \
  tests/test_geominilm_prototype.py::test_qgis_slope_transparency_template_preserves_hillshade_overlay_details \
  tests/test_geominilm_prototype.py::test_grouped_holdout_evaluation_excludes_workflow_families_from_retrieval_checkpoint \
  -vv
```

Result: `2 passed`

```bash
timeout 120 .venv/bin/python -m py_compile geovis_lm/model/prototype.py scripts/train_geominilm.py
```

Result: passed

## Preserved Development Baseline

- Protocol: leave-one-out over `data/geominilm/starter_workflows.jsonl` plus `data/geominilm/training_expansion_workflows.jsonl`
- Records: `29`
- Baseline held-out score: `0.7627`
- Baseline expected calibration error: `0.2495`
- Baseline failed held-out examples: `11`

## Current Development Result

Historical leave-one-out result under the legacy development protocol:

Command:

```bash
.venv/bin/python scripts/train_geominilm.py \
  --dataset data/geominilm/starter_workflows.jsonl \
  --extra-training-data data/geominilm/training_expansion_workflows.jsonl \
  --held-out-eval \
  --eval-dir outputs/eval/geominilm_development \
  --output-dir outputs/models/geominilm_development \
  --predictions-dir outputs/model_samples/geominilm_development
```

Result:

- Held-out score: `0.8977`
- Delta vs preserved baseline: `+0.1350`
- Expected calibration error: `0.1023`
- Maximum calibration error: `0.2203`
- Failed held-out examples: `0`

Reliability bins:

| Bin | Range | Count | Avg Confidence | Accuracy | Gap |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | `0.0000-0.2000` | `0` | `0.0000` | `0.0000` | `0.0000` |
| 2 | `0.2000-0.4000` | `0` | `0.0000` | `0.0000` | `0.0000` |
| 3 | `0.4000-0.6000` | `0` | `0.0000` | `0.0000` | `0.0000` |
| 4 | `0.6000-0.8000` | `3` | `0.7797` | `1.0000` | `0.2203` |
| 5 | `0.8000-1.0000` | `26` | `0.9113` | `1.0000` | `0.0887` |

## Verification

Targeted development checks that do not read the frozen regression split:

```bash
timeout 120 .venv/bin/python -m pytest \
  tests/test_geominilm_prototype.py::test_leave_one_out_evaluation_excludes_heldout_examples_from_training \
  tests/test_geominilm_prototype.py::test_training_derived_development_evaluation_clears_model_selection_floor \
  tests/test_train_geominilm_cli.py::test_train_geominilm_held_out_eval_writes_excluded_fold_reports \
  -vv
```

Result: `3 passed`

```bash
timeout 120 .venv/bin/python -m py_compile geovis_lm/model/prototype.py scripts/train_geominilm.py
```

Result: passed

Full regression suite:

```bash
timeout 120 .venv/bin/python -m pytest
```

Result: `77 passed in 14.97s`

## Candidate Gate Outcome

- Locked candidate evaluated: `9af23d8`
- Lock basis: training-derived development result plus passing full regression suite
- Production status: `9af23d8` was not accepted; dashboard integration remains blocked
- Legacy candidate rescore under repaired workflow-only scoring: `0.6377`
- Comparable honest baseline under repaired workflow-only scoring: `0.3682`
- Repaired-protocol failures on the historical frozen set: `11/14`
- Future production use: requires protocol review, a new training/development-only
  performance cycle, locked workflow-only thresholds/category floors, and a
  newly scheduled formal one-shot gate on a new sealed shadow set before any
  production acceptance decision
