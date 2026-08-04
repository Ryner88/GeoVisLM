# GeoMiniLM Dataset Format

This folder contains starter instruction data for GeoMiniLM, the small
geospatial and scientific visualization model planned for GeoVisLM.

## Files

- `starter_workflows.jsonl`: seed examples for GIS, QGIS, and ParaView workflow generation.
- `training_expansion_workflows.jsonl`: additional stratified training examples
  authored after the held-out failure analysis. These are training-only records.
- `validation_workflows.jsonl`: frozen independently authored expanded
  validation examples. Do not copy these records into training data.
- `evaluation_manifest.json`: versioned frozen split contract with dataset,
  taxonomy, and split checksums for the production validation gate.
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

## Evaluation Splits

- Keep validation ids disjoint from starter and expansion training ids.
- Update `evaluation_manifest.json` only when intentionally freezing a new
  evaluation design; production runs verify its checksums before reporting.
- The current expanded validation split has `14` records stratified across GIS,
  QGIS, ParaView, and reporting workflows.
- Treat the `1.0000` expected-output baseline as an oracle sanity check only.
  It confirms the evaluation pipeline can score perfect predictions, but it is
  not an honest generalization benchmark.
- Compare improvement experiments against the current held-out reference score
  of `0.4943` and report per-category failures.
