# GeoMiniLM Development Performance Cycle

## Scope

- Branch: `geominilm-development-performance-cycle`
- Starting point: `c1a03ed`
- Immutable production candidate: `428af8d`
- Frozen production validation split: off-limits for development selection
- Dashboard integration: blocked until a future formal production gate passes

This cycle uses training-derived leave-one-out development evaluation only.

## Preserved Development Baseline

- Protocol: leave-one-out over `data/geominilm/starter_workflows.jsonl` plus `data/geominilm/training_expansion_workflows.jsonl`
- Records: `29`
- Baseline held-out score: `0.7627`
- Baseline expected calibration error: `0.2495`
- Baseline failed held-out examples: `11`

## Current Development Result

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

Targeted development checks that do not read the frozen validation split:

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
