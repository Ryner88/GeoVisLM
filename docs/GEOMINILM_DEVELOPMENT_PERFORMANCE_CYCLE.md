# GeoMiniLM Development Performance Cycle

## Scope

- Branch: `geominilm-development-performance-cycle`
- Starting point: `c1a03ed`
- Previous production candidate: `428af8d`
- Failed production candidate: `9af23d8`
- Frozen production validation split: off-limits for development selection
- Dashboard integration: blocked until a future formal production gate passes

This cycle used training-derived leave-one-out development evaluation. That
result is now historical: the repaired protocol uses workflow-only scoring,
grouped workflow-family holdouts, and treats template code plus retrieval data as
one versioned candidate. The repaired protocol is implemented and verified,
pending protocol review before the next performance cycle.

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
