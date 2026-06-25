# GeoMiniLM Dataset Format

This folder contains starter instruction data for GeoMiniLM, the small
geospatial and scientific visualization model planned for GeoVisLM.

## Files

- `starter_workflows.jsonl`: seed examples for GIS, QGIS, and ParaView workflow generation.

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
