# GeoMiniLM Production Acceptance Gate - 2026-08-08

## Locked Candidate

- Candidate commit: `9af23d8b7d86c242d9cf1be8a672e04b207a4e40`
- Review date: `2026-08-08`
- Branch evaluated: `geominilm-production-performance`
- Constraint: no model or dataset changes during the gate.
- Frozen validation set: `data/geominilm/validation_workflows.jsonl`
- Frozen validation record count: `14`
- Attempt count: one attempt for this candidate/gate.

## One-Shot Evaluation Command

```bash
.venv/bin/python scripts/train_geominilm.py \
  --dataset data/geominilm/starter_workflows.jsonl \
  --extra-training-data data/geominilm/training_expansion_workflows.jsonl \
  --validation-set data/geominilm/validation_workflows.jsonl \
  --production-pass-threshold 0.75 \
  --minimum-threshold-margin 0.01 \
  --minimum-validation-records 12
```

The frozen validation set was evaluated once for candidate `9af23d8` in this
gate. No retuning or second frozen-set attempt was performed for this candidate
or gate.

## Gate Decision

Status: **FAIL**

Dashboard integration remains blocked. The next GeoMiniLM performance cycle is
training/development-only; the frozen production validation set must not be used
for iterative tuning.

Locked pass rule:

- Required primary metric: `trained_validation_score >= 0.7600`
- Must beat honest baseline: yes
- Integrity checks must pass: yes

Observed result:

- Primary metric: `0.7201`
- Required metric: `0.7600`
- Remaining gap: `0.0399`
- Honest baseline score: `0.5326`
- Delta vs honest baseline: `+0.1875`
- Beats honest baseline: `true`
- Integrity checks pass: `true`
- Dashboard integration allowed: `false`

Candidate `9af23d8` beats the honest baseline and passes integrity checks, but
fails the locked score threshold.

## Overall Scores

- Trained validation score: `0.7201`
- Honest baseline score: `0.5326`
- Oracle sanity score: `1.0000`
- Reference development held-out score: `0.4943`
- Delta vs honest baseline: `+0.1875`
- Failed validation examples: `9/14`

## Per-Category Scores

| Category | Trained | Honest Baseline | Failed |
| --- | ---: | ---: | ---: |
| `gis_hillshade_and_single_raster_products` | `0.7480` | `0.4459` | `1/2` |
| `gis_risk_overlay_and_reclassification` | `0.6607` | `0.4434` | `2/2` |
| `paraview_render_variants` | `0.7749` | `0.5166` | `1/3` |
| `qgis_styling_and_layout_exports` | `0.7328` | `0.5691` | `3/4` |
| `reporting_summaries` | `0.6694` | `0.6172` | `2/3` |

## Calibration

- Method: workflow score as confidence proxy
- Expected calibration error: `0.4368`
- Maximum calibration error: `0.5089`

| Bin | Range | Count | Avg Confidence | Accuracy | Gap |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | `0.0000-0.2000` | `0` | `0.0000` | `0.0000` | `0.0000` |
| 2 | `0.2000-0.4000` | `0` | `0.0000` | `0.0000` | `0.0000` |
| 3 | `0.4000-0.6000` | `0` | `0.0000` | `0.0000` | `0.0000` |
| 4 | `0.6000-0.8000` | `11` | `0.6907` | `0.1818` | `0.5089` |
| 5 | `0.8000-1.0000` | `3` | `0.8276` | `1.0000` | `0.1724` |

## Integrity Checks

Manifest check:

- Passed: `true`
- Mismatches: `[]`
- Frozen manifest checksum field: `414d0eb5d9ba468c5eb9153d313365f241c6346032119301727ab8fd0aceb238`
- Frozen split checksum field: `37c70721b8a9dc352cf56e0073c8434aaf38bdfb82dac3d79c137bc626887d61`

Split validation:

- Passed: `true`
- Duplicate id issues: `0`
- Exact duplicate issues: `0`
- Near-duplicate/leakage issues: `0`
- Issues: `[]`

Current file checksums:

| File | SHA-256 |
| --- | --- |
| `data/geominilm/evaluation_manifest.json` | `8083a58d3633d779414de180f6d6aab4280369a606dfd64a5e31284ad2df71fb` |
| `data/geominilm/starter_workflows.jsonl` | `a4903f291bcb67460731b18a8433c26b63f54b84ae2a00baaa10acbbd43499e0` |
| `data/geominilm/training_expansion_workflows.jsonl` | `e15068d596f98bd9308a6a9f42096de6cc34707c3dd593dbe7cc8a32e4afe376` |
| `data/geominilm/validation_workflows.jsonl` | `57db85e9ae38c2a8b9e36c254a39fccef26540780942ac232e942e27484845bf` |
| `data/geominilm/failure_taxonomy.json` | `74f5c87c7d35c692f4bdbb106c731d9485c43629a6f25e8ff7b30fab0605796b` |

Generated gate artifact checksums:

| File | SHA-256 |
| --- | --- |
| `outputs/eval/geominilm_validation/experiment_comparison.json` | `30170d13fb9e80c24afd9eab723e676a46a67916ffd25923ddb7e3f66a68da90` |
| `outputs/eval/geominilm_validation/confidence_calibration.json` | `ebfbab73e6902c8a46f70740f11755394f36b2268f0954588196b460207c279f` |
| `outputs/eval/geominilm_validation/manifest_check.json` | `1feafee3bb9162637a7ed8e849f3e3c2e7a92a580ccbfaa5468f78203fcfbc85` |
| `outputs/eval/geominilm_validation/split_validation.json` | `ed94c14d5694f48305115068512e4624a0dceab0708788e7de87bf3fdd6d21c6` |
| `outputs/eval/geominilm_validation/production_decision.json` | `17aa51759296d3f7aeecc50bf32a2d2943332aa095ebdc21b755c7b0adc7eb72` |

## Engineering Verification

Full test suite:

```bash
timeout 120 .venv/bin/python -m pytest
```

Result: `77 passed in 6.46s`

Engineering checks passed. The model acceptance gate failed.
