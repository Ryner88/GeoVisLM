# GeoMiniLM Evaluation

The workflow evaluator compares expected GeoMiniLM JSONL records with predicted
records by stable `id`. It is deterministic and intended to create a baseline
before model training begins.

## Prediction Format

Prediction records use the same top-level schema as the starter dataset. The
workflow field may be either `predicted_workflow` or `expected_workflow`:

```json
{
  "id": "gis-terrain-analysis-001",
  "domain": "gis",
  "instruction": "Run the MVP terrain analysis on a DEM.",
  "inputs": {},
  "predicted_workflow": [
    {
      "step": 1,
      "action": "Load the DEM raster.",
      "tool": "rasterio",
      "output": "DEM array plus raster metadata."
    }
  ],
  "explanation": "The workflow preserves raster metadata so outputs align."
}
```

## Scoring Rubric

Scores range from `0.0` to `1.0`. The default pass threshold is `0.75`.

- Instruction relevance: 10%
- Required input coverage: 20%
- Ordered workflow steps: 30%
- Tool choice: 15%
- Output paths or states: 15%
- Explanation quality: 10%

The report passes only when the summary score meets the threshold and every
expected record has a passing prediction.

## Usage

```bash
python scripts/evaluate_geominilm.py \
  --expected data/geominilm/starter_workflows.jsonl \
  --predictions outputs/model_samples/predictions.jsonl \
  --output-dir outputs/eval
```

The command writes:

- `outputs/eval/evaluation_report.json`
- `outputs/eval/evaluation_report.md`

Use `--fail-on-threshold` when a training or CI job should fail on a low score.

## Expanded Production Validation Gate

The production evaluation design was frozen on `2026-08-03` for the Thursday,
`2026-08-06` acceptance gate.

- Frozen manifest: `data/geominilm/evaluation_manifest.json`
- Training splits: `data/geominilm/starter_workflows.jsonl` and
  `data/geominilm/training_expansion_workflows.jsonl`
- Expanded validation split: `data/geominilm/validation_workflows.jsonl`
  (`14` records; GIS `4`, QGIS `4`, ParaView `3`, reporting `3`)
- Primary metric: `trained_validation_score`
- Locked pass threshold: `0.75`
- Dashboard threshold margin: `0.01`, so dashboard authorization requires a
  primary metric of at least `0.76`
- Minimum expanded validation size for dashboard authorization: `12` records
- Dashboard integration remains blocked unless `trained_validation_score` is
  greater than `honest_baseline_score` on the frozen expanded validation set
  and clears the locked threshold margin.

Run the production validation experiment with:

```bash
.venv/bin/python scripts/train_geominilm.py \
  --dataset data/geominilm/starter_workflows.jsonl \
  --extra-training-data data/geominilm/training_expansion_workflows.jsonl \
  --validation-set data/geominilm/validation_workflows.jsonl
```

Validation runs write the existing prediction, honest baseline, oracle sanity,
per-record, and per-category reports, plus:

- `outputs/eval/geominilm_validation/evaluation_manifest.json`
- `outputs/eval/geominilm_validation/manifest_check.json`
- `outputs/eval/geominilm_validation/split_validation.json`
- `outputs/eval/geominilm_validation/confidence_calibration.json`
- `outputs/eval/geominilm_validation/production_decision.json`

The split validation step checks exact duplicate records, duplicate ids,
near-duplicate train/validation leakage using a locked Jaccard threshold of
`0.85` with containment overlap for edited copies, and current
dataset/taxonomy checksums against the frozen manifest.
Calibration currently reports reliability bins and calibration error using the
workflow score as a confidence proxy until model-native confidence values exist.

## Development Model Selection

Do not use the frozen `14`-record validation split for iterative tuning. Further
model changes before the August 6 gate should be selected with training-derived
development runs only.

Use leave-one-out evaluation across the starter and training expansion splits:

```bash
.venv/bin/python scripts/train_geominilm.py \
  --dataset data/geominilm/starter_workflows.jsonl \
  --extra-training-data data/geominilm/training_expansion_workflows.jsonl \
  --held-out-eval \
  --eval-dir outputs/eval/geominilm_development
```

The August 4 training-derived development run produced:

- Development held-out score: `0.7627`
- Development records: `29`
- Baseline oracle sanity score: `1.0000`

The next read of `data/geominilm/validation_workflows.jsonl` should be the
formal August 6 production gate attempt, not another tuning loop.

Current expanded-set status from the `2026-08-04` performance run:

- Status: production evaluation framework implemented; expanded production
  acceptance gate not passed.
- Trained validation score: `0.7201`
- Honest baseline score: `0.5326`
- Delta vs honest baseline: `+0.1875`
- Required metric for dashboard authorization: `0.76`
- Failed validation examples: `9/14`
- Expected calibration error: `0.4368`
- Dashboard integration: blocked

## Baseline Validation

The deterministic baseline compares the starter workflow file against itself.
This is a harness sanity check before generated model predictions exist; it
should pass with a perfect score.

Validated on `2026-07-25`:

```bash
timeout 120 .venv/bin/python -m py_compile geovis_lm/eval/workflow_eval.py scripts/evaluate_geominilm.py
timeout 120 .venv/bin/python scripts/evaluate_geominilm.py --help
timeout 120 .venv/bin/python -m pytest tests/test_workflow_eval.py -vv
timeout 120 .venv/bin/python scripts/evaluate_geominilm.py \
  --expected data/geominilm/starter_workflows.jsonl \
  --predictions data/geominilm/starter_workflows.jsonl \
  --output-dir outputs/eval \
  --fail-on-threshold
```

Result:

- Workflow evaluation tests: `6 passed`
- Baseline evaluation: `PASS`
- Summary score: `1.000`
- Expected/evaluated records: `12/12`
- Missing predictions: `0`

## Known Limitations

- Text similarity is token-overlap based, not embedding based.
- Tool and output matching rewards exact or substring matches; semantically
  equivalent but differently phrased tools may score lower.
- The evaluator measures structured workflow quality, not whether outputs were
  executed or geospatially valid.
