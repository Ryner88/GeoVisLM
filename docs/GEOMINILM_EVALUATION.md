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
