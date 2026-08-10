# GeoMiniLM Dataset Format

This folder contains starter instruction data for GeoMiniLM, the small
geospatial and scientific visualization model planned for GeoVisLM.

## Files

- `starter_workflows.jsonl`: seed examples for GIS, QGIS, and ParaView workflow generation.
- `training_expansion_workflows.jsonl`: additional stratified training and
  development examples authored after the held-out failure analysis. These are
  training-only records.
- `validation_workflows.jsonl`: frozen independently authored 14-record
  regression benchmark. Do not copy these records into training data or use
  them for model, template, retrieval, prompt, threshold, or floor tuning.
- `evaluation_manifest.json`: versioned frozen split contract with dataset,
  taxonomy, and split checksums for the historical production validation gate
  and current regression benchmark.
- `failure_taxonomy.json`: categorizes the first held-out failures by
  operation, parameters, output structure, and coverage records.

## JSONL Schema

Each line is one JSON object with this shape:

```json
{
  "id": "stable-example-id",
  "domain": "gis | qgis | paraview | reporting",
  "instruction": "User-facing request the model should answer.",
  "inputs": {
    "key": "Relevant paths, layers, parameters, or constraints."
  },
  "expected_workflow": [
    {
      "step": 1,
      "action": "Short imperative action.",
      "tool": "Preferred tool, library, or application.",
      "output": "Expected artifact or state."
    }
  ],
  "explanation": "Why the workflow is correct and how outputs should be used."
}
```

## Authoring Rules

- Keep `id` stable; downstream train/eval splits may reference it.
- Use `domain` to group examples by execution surface.
- Keep `instruction` close to a realistic user request.
- Put concrete files, layers, thresholds, CRS values, and output paths in `inputs`.
- Write `expected_workflow` as ordered, executable steps.
- Use `explanation` to capture reasoning, caveats, or validation checks.

## Current Coverage

The starter dataset includes:

- Terrain analysis from DEM inputs
- QGIS styling and export workflows
- ParaView DEM rendering workflows
- Early reporting and multimodal workflow examples

This is seed data only. Production training should add more varied geography,
file formats, failure cases, and evaluation labels.

The training expansion currently adds `17` training-only records covering COG
reprojection, wildfire and flood risk summaries, QGIS atlas and labeling
exports, ParaView colorbar and clipping variants, and reporting review tasks.

## Evaluation Splits

- Keep validation ids disjoint from starter and expansion training ids.
- Update `evaluation_manifest.json` only when intentionally recording a new
  benchmark contract; regression runs verify its checksums before reporting.
- The current frozen regression split has `14` records stratified across GIS,
  QGIS, ParaView, and reporting workflows.
- Use the 14-record split only for regression reporting and protocol migration
  diagnostics. Future production acceptance requires a new sealed shadow set.
- Treat the `1.0000` expected-output baseline as an oracle sanity check only.
  It confirms the evaluation pipeline can score perfect predictions, but it is
  not an honest generalization benchmark.
- Compare development experiments with grouped workflow-family holdouts over
  training/development records, workflow-only scoring, locked category floors,
  all-record pass status, semantic and executability checks, and route-aware
  confidence requirements.
