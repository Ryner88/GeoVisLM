from __future__ import annotations

import json
from pathlib import Path

import pytest

from geovis_lm.eval.workflow_eval import EvaluationInputError, load_jsonl
from geovis_lm.model.dataset import (
    build_baseline_predictions,
    load_geominilm_dataset,
    preprocess_examples,
    summarize_examples,
    write_preprocessed_jsonl,
)


STARTER_DATASET = Path("data/geominilm/starter_workflows.jsonl")


def test_load_geominilm_dataset_validates_starter_records():
    examples = load_geominilm_dataset(STARTER_DATASET)
    summary = summarize_examples(examples)

    assert summary.total_records == 12
    assert set(summary.domain_counts) == {"gis", "qgis", "paraview", "reporting"}
    assert all(example.expected_workflow for example in examples)
    assert examples[0].id == "gis-terrain-analysis-001"


def test_preprocess_examples_builds_prompt_target_pairs(tmp_path):
    examples = load_geominilm_dataset(STARTER_DATASET)
    pairs = preprocess_examples(examples)
    output_path = write_preprocessed_jsonl(pairs, tmp_path / "training_pairs.jsonl")

    persisted = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    target = json.loads(persisted[0]["target"])

    assert len(persisted) == len(examples)
    assert "Generate a structured GeoVisLM workflow." in persisted[0]["prompt"]
    assert "expected_workflow" in target
    assert "explanation" in target


def test_build_baseline_predictions_are_evaluation_schema_valid(tmp_path):
    examples = load_geominilm_dataset(STARTER_DATASET)
    predictions = build_baseline_predictions(examples)

    path = write_jsonl(tmp_path / "geominilm_predictions_test.jsonl", predictions)
    loaded = load_jsonl(path, prediction=True)

    assert len(loaded) == len(examples)
    assert loaded[0]["predicted_workflow"] == examples[0].expected_workflow


def test_load_geominilm_dataset_reports_invalid_jsonl(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"id": "broken"}\n', encoding="utf-8")

    with pytest.raises(EvaluationInputError) as exc_info:
        load_geominilm_dataset(path)

    assert any("missing required fields" in error for error in exc_info.value.errors)


def write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    return path
