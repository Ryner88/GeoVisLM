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
