from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from geovis_lm.model.dataset import GeoMiniLMExample
from geovis_lm.model.prototype import GeoMiniLMPrototype


DEFAULT_CHECKPOINT = Path("outputs/models/geominilm/checkpoint.json")


def _workflow_type(instruction: str, predicted_workflow: list[dict[str, Any]]) -> str:
    text = instruction.lower()
    actions = " ".join(str(step.get("action", "")) for step in predicted_workflow).lower()
    combined = f"{text} {actions}"
    if "wildfire" in combined or "fire risk" in combined:
        return "wildfire_risk"
    if "flood" in combined or "inundation" in combined:
        return "flood_risk"
    return "terrain"


@lru_cache(maxsize=4)
def load_recommendation_model(checkpoint_path: str) -> GeoMiniLMPrototype:
    return GeoMiniLMPrototype.load(Path(checkpoint_path))


def recommend_workflow(
    *,
    run_id: str,
    workflow_type: str,
    parameters: dict[str, Any],
    inputs: list[dict[str, Any]],
    checkpoint_path: Path = DEFAULT_CHECKPOINT,
) -> dict[str, Any]:
    filenames = [item.get("stored_filename") or item.get("original_filename") for item in inputs]
    filenames = [name for name in filenames if name]
    instruction = (
        f"Recommend a {workflow_type} geospatial workflow for the uploaded dataset. "
        f"Input files: {', '.join(filenames) or 'no files uploaded yet'}."
    )
    example = GeoMiniLMExample(
        id=f"dashboard-{run_id}",
        domain="gis",
        instruction=instruction,
        inputs={"files": filenames, "parameters": parameters},
        expected_workflow=[],
        explanation="",
    )
    prediction = load_recommendation_model(str(checkpoint_path)).predict(example)
    predicted_workflow = prediction.get("predicted_workflow", [])
    suggested_workflow_type = _workflow_type(instruction, predicted_workflow)
    return {
        "id": prediction["id"],
        "model_name": load_recommendation_model(str(checkpoint_path)).model_name,
        "workflow_type": suggested_workflow_type,
        "parameters": dict(parameters),
        "predicted_workflow": predicted_workflow,
        "explanation": prediction.get("explanation", ""),
        "confidence": prediction.get("confidence", prediction.get("retrieval_similarity", 0.0)),
        "confidence_source": prediction.get("confidence_source", "retrieval_similarity"),
        "source_checkpoint_record_id": prediction.get("source_checkpoint_record_id"),
        "input_filenames": filenames,
        "status": "pending_approval",
    }