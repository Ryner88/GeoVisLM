# GeoMiniLM Production Gate - 2026-08-28

## Decision

Result: **FAIL**.

Dashboard integration remains blocked. The shadow set is now retired as
regression evidence and must not be used for model, retrieval, template,
prompt, threshold, confidence, or category-floor tuning.

## Candidate

The locked development candidate remains `75818a88fa0e0589d363ca54c53d443b2b2bd64d`.
The repository was clean before the shadow-set work. At preflight,
`main`, `origin/main`, and `HEAD` pointed to
`07cb50cc9c572c4297a58490b2781a0a2f672797`; that commit only adds the
candidate-lock evidence document on top of `75818a88`.

No candidate code, scorer code, model logic, retrieval logic, template logic, or
threshold logic was changed for this gate.

The locked development evidence still stands:

- Grouped-development score: `0.9354`
- Grouped-development failures: `0/29`
- Dashboard integration before this gate: blocked

## Shadow Set

New sealed shadow set:

- Path: `data/geominilm/shadow_workflows_20260828.jsonl`
- Records: `15`
- Domains: GIS, QGIS, ParaView, reporting
- Shadow taxonomy: `data/geominilm/shadow_failure_taxonomy_20260828.json`
- Frozen manifest: `data/geominilm/shadow_evaluation_manifest_20260828.json`

The shadow manifest locked these gate values before evaluation:

- Primary metric: `trained_validation_score`
- Record pass threshold: `0.7500`
- Minimum threshold margin: `0.0100`
- Required metric value: `0.7600`
- Minimum validation records: `12`
- Near-duplicate threshold: `0.8500`
- Category pass threshold: `0.7500`
- Maximum expected calibration error: `0.2000`
- Maximum calibration error: `0.3500`

## Split Validation

Training, frozen regression, and shadow records were checked together before the
gate:

- Starter training records: `12`
- Training-expansion records: `17`
- Frozen regression records: `14`
- Shadow records: `15`
- Duplicate IDs: `0`
- Exact duplicates: `0`
- Near-duplicate or leakage issues at `0.8500`: `0`
- Split validation: pass

The gate command also wrote `outputs/eval/geominilm_shadow_20260828/split_validation.json`
for the training/shadow split used by the formal run. That split validation
passed with `0` issues.

## Command

The shadow set was evaluated once:

```bash
timeout 120 .venv/bin/python scripts/train_geominilm.py \
  --dataset data/geominilm/starter_workflows.jsonl \
  --extra-training-data data/geominilm/training_expansion_workflows.jsonl \
  --validation-set data/geominilm/shadow_workflows_20260828.jsonl \
  --failure-taxonomy data/geominilm/shadow_failure_taxonomy_20260828.json \
  --evaluation-manifest data/geominilm/shadow_evaluation_manifest_20260828.json \
  --production-pass-threshold 0.75 \
  --minimum-threshold-margin 0.01 \
  --minimum-validation-records 12 \
  --eval-dir outputs/eval/geominilm_shadow_20260828 \
  --output-dir outputs/models/geominilm_shadow_20260828 \
  --predictions-dir outputs/model_samples/geominilm_shadow_20260828
```

## Score

- Trained shadow score: `0.4783`
- Honest baseline score: `0.3368`
- Oracle sanity score: `1.0000`
- Delta vs honest baseline: `+0.1415`
- Threshold failures: `14/15`
- Records with evaluator findings: `15/15`
- Prediction strategies: `workflow_template: 14`, `tfidf_nearest_neighbor: 1`

The candidate beat the honest baseline, but it did not meet the required metric,
the all-record pass rule, category floors, or confidence limits.

## Category Floors

| Category | Shadow Records | Trained Score | Honest Baseline | Failures |
| --- | ---: | ---: | ---: | ---: |
| `gis_hillshade_and_single_raster_products` | `2` | `0.4289` | `0.2631` | `2/2` |
| `gis_risk_overlay_and_reclassification` | `3` | `0.3883` | `0.2756` | `3/3` |
| `qgis_styling_and_layout_exports` | `4` | `0.5127` | `0.3372` | `4/4` |
| `paraview_render_variants` | `3` | `0.4102` | `0.2698` | `3/3` |
| `reporting_summaries` | `3` | `0.6234` | `0.5134` | `2/3` |

## Calibration

- Method: `prediction_confidence`
- Confidence records: `15/15`
- Expected calibration error: `0.8302`
- Maximum calibration error: `0.8436`
- Confidence gate: fail

## Decision Checks

| Check | Result |
| --- | --- |
| Beats honest baseline | pass |
| Passes score threshold plus margin | fail |
| Has required validation size | pass |
| All records passed | fail |
| Manifest check | pass |
| Split validation | pass |
| Category floor | fail |
| Confidence gate | fail |

Dashboard integration allowed: `false`.

## Artifact Hashes

| Artifact | SHA-256 |
| --- | --- |
| `data/geominilm/starter_workflows.jsonl` | `a4903f291bcb67460731b18a8433c26b63f54b84ae2a00baaa10acbbd43499e0` |
| `data/geominilm/training_expansion_workflows.jsonl` | `e15068d596f98bd9308a6a9f42096de6cc34707c3dd593dbe7cc8a32e4afe376` |
| `data/geominilm/validation_workflows.jsonl` | `57db85e9ae38c2a8b9e36c254a39fccef26540780942ac232e942e27484845bf` |
| `data/geominilm/shadow_workflows_20260828.jsonl` | `bea00f1c9eaf7cf24d2cd10ca3dcd9645cbb207da74fdbaf134da605f1993c6f` |
| `data/geominilm/shadow_failure_taxonomy_20260828.json` | `3cb7892940ba8b38b7f0a1aa46c086e465ba91f3a3da6e6b97a587d0c83053f6` |
| `data/geominilm/shadow_evaluation_manifest_20260828.json` | `32c320e1760e7906cce8c8292c8309a2a2cf20286431f90eea0f0a64b9256c76` |
| `outputs/eval/geominilm_shadow_20260828/evaluation_report.json` | `31a11b4e3c8b2187d58938db34f55b8082acd70a74e3ec1c7aabc62c38d1b360` |
| `outputs/eval/geominilm_shadow_20260828/experiment_comparison.json` | `27f7199556e0a7e1b2375e486ee3846a2a8357e75812b536674fa785bb6a1716` |
| `outputs/eval/geominilm_shadow_20260828/production_decision.json` | `e449f12cdeea705b5a77912c96655a73bef8e6232cc4d31cb9977a2651f667d4` |
| `outputs/eval/geominilm_shadow_20260828/confidence_calibration.json` | `b4b24efe00d2a2e1e178b114d26395b1935e0eeaff9769d981bbb455613744e6` |
| `outputs/eval/geominilm_shadow_20260828/manifest_check.json` | `502d8470b85dc8c33a1888c8016803cf9b1e438ebac96765fcd4cd7975be1e06` |
| `outputs/eval/geominilm_shadow_20260828/split_validation.json` | `7b5fc6e8898f8a9e59db16bc2f15e30e9881f17fe2832d659668b9814bf86367` |
| `outputs/model_samples/geominilm_shadow_20260828/validation_predictions.jsonl` | `d701913bc2557e8208d83f3663391f93b8cf7623b9d47e77535ae67c6dc2312b` |
| `outputs/model_samples/geominilm_shadow_20260828/honest_baseline_predictions.jsonl` | `b73baa6633a8c69102e98fe6e474820726dffe578130e4bdf97db7af79a613a4` |
| `outputs/models/geominilm_shadow_20260828/validation_experiment_metadata.json` | `424fe16e2d8d2d29fdacb7ce2778af9be190363997aed4e5192f2b889e785745` |
| `outputs/models/geominilm_shadow_20260828/validation_checkpoint.json` | `39ed89621846d80e4237f86f8bf35fcd48dccf3f80af145ad11a28127f167645` |

## Follow-Up Boundary

Do not tune against `data/geominilm/shadow_workflows_20260828.jsonl` or its
answers. Future development work needs a new development-only cycle. Any later
production decision needs a different sealed shadow set, locked before the next
formal gate.
