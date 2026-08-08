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

Compatibility and oracle sanity checks can still score the full record:

- Instruction relevance: 10%
- Required input coverage: 20%
- Ordered workflow steps: 30%
- Tool choice: 15%
- Output paths or states: 15%
- Explanation quality: 10%

Model selection and validation-set comparisons now use workflow-only scoring so
predictions are not rewarded for copying the expected record's original
`instruction` and `inputs` fields:

- Ordered workflow steps: 50%
- Tool choice: 25%
- Output paths or states: 20%
- Explanation quality: 5%

The report passes only when the summary score meets the threshold and every
expected record has a passing prediction.

Comparison artifacts separate threshold failures from diagnostic findings:

- `failed_examples`: records whose score is below the configured threshold.
- `failure_count`: count of threshold failures; this is the failure count used by
  category summaries and gate logic.
- `records_with_findings`: records with any evaluator finding, including partial
  component matches on otherwise passing records.
- `records_with_findings_count`: count of diagnostic finding records.

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
Calibration reports reliability bins from the prediction confidence field. For
the current prototype this confidence is the TF-IDF retrieval similarity, not the
evaluator score.

For predictions routed through `workflow_template`, TF-IDF similarity is only a
retrieval/routing confidence. It is not a validated confidence estimate for the
template output itself. Future calibration work should either calibrate by
prediction route or add a separate template-output confidence signal.

## Development Model Selection

Do not use the frozen `14`-record validation split for iterative tuning. That
set is now a regression benchmark because its detailed outcomes have been
reviewed repeatedly. Future production acceptance requires a new sealed shadow
set.

Use grouped workflow-family holdout evaluation across the starter and training
expansion splits:

```bash
.venv/bin/python scripts/train_geominilm.py \
  --dataset data/geominilm/starter_workflows.jsonl \
  --extra-training-data data/geominilm/training_expansion_workflows.jsonl \
  --grouped-held-out-eval \
  --eval-dir outputs/eval/geominilm_grouped_heldout
```

The grouped protocol holds out entire workflow families, not just individual
records. The versioned candidate includes both retrieval data and the handwritten
template code path, because either component can encode development examples.
Grouped data holdouts do not, by themselves, remove code-level leakage when
template predicates were authored with knowledge of the held-out family. Template
development therefore needs a separate sealed, pre-authored challenge set.

The older leave-one-out command remains available as a diagnostic only:

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

Candidate `9af23d8` was evaluated exactly once against
`data/geominilm/validation_workflows.jsonl` during the `2026-08-08` formal
production gate. That candidate failed. The next performance cycle must remain
training/development-only, not another tuning loop against the frozen validation
split.

The repaired scoring protocol reports the same candidate lower because copied
request context no longer contributes to the primary score:

- Workflow-only trained validation score: `0.6377`
- Workflow-only honest baseline score: `0.3682`
- Failed validation examples: `11/14`
- Records with evaluator findings: `14/14`
- Prediction source strategies: `workflow_template` for `14/14`

Interpret this as a protocol-migration rescore, not a new production acceptance
attempt. The historical `0.7201` reports remain legacy-scoring gate results. Do
not reuse the `0.7600` authorization threshold blindly: the metric changed, so
the next threshold and per-category floors must be locked under workflow-only
scoring before evaluating a new sealed shadow set.

Dashboard authorization is now computed only after manifest validation,
split/leakage validation, all-record pass status, per-category floors, and
confidence checks are attached to the production decision.

Current expanded-set status from the `2026-08-08` production gate:

- Status: production evaluation framework implemented; expanded production
  acceptance gate not passed.
- Trained validation score: `0.7201`
- Honest baseline score: `0.5326`
- Delta vs honest baseline: `+0.1875`
- Required metric for dashboard authorization: `0.76`
- Remaining gap: `0.0399`
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
