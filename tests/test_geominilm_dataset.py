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
TRAINING_EXPANSION = Path("data/geominilm/training_expansion_workflows.jsonl")
VALIDATION_DATASET = Path("data/geominilm/validation_workflows.jsonl")
FAILURE_TAXONOMY = Path("data/geominilm/failure_taxonomy.json")


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


def test_validation_and_training_expansion_are_disjoint_and_valid():
    starter = load_geominilm_dataset(STARTER_DATASET)
    expansion = load_geominilm_dataset(TRAINING_EXPANSION)
    validation = load_geominilm_dataset(VALIDATION_DATASET)

    training_ids = {example.id for example in starter + expansion}
    validation_ids = {example.id for example in validation}

    assert len(expansion) == 8
    assert len(validation) == 6
    assert training_ids.isdisjoint(validation_ids)
    assert {example.domain for example in validation} == {"gis", "qgis", "paraview", "reporting"}


def test_failure_taxonomy_covers_validation_and_expansion_ids():
    taxonomy = json.loads(FAILURE_TAXONOMY.read_text(encoding="utf-8"))
    expansion_ids = {example.id for example in load_geominilm_dataset(TRAINING_EXPANSION)}
    validation_ids = {example.id for example in load_geominilm_dataset(VALIDATION_DATASET)}
    categorized_expansion_ids = set()
    categorized_validation_ids = set()

    for category in taxonomy["categories"].values():
        categorized_expansion_ids.update(category["training_expansion_ids"])
        categorized_validation_ids.update(category["validation_ids"])

    assert expansion_ids == categorized_expansion_ids
    assert validation_ids == categorized_validation_ids
    assert taxonomy["baseline_reference"]["heldout_score"] == 0.4943


def write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    return path
