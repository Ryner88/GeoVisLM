from __future__ import annotations

import json
from pathlib import Path

import pytest

from geovis_lm.eval.workflow_eval import evaluate_records, load_jsonl
from geovis_lm.model.dataset import build_baseline_predictions, load_geominilm_dataset
from geovis_lm.model.prototype import (
    GeoMiniLMPrototype,
    compare_reports,
    run_leave_one_out_evaluation,
    run_validation_experiment,
    run_grouped_holdout_evaluation,
    train_and_save_checkpoint,
)


STARTER_DATASET = Path("data/geominilm/starter_workflows.jsonl")
TRAINING_EXPANSION = Path("data/geominilm/training_expansion_workflows.jsonl")
VALIDATION_DATASET = Path("data/geominilm/validation_workflows.jsonl")


def test_prototype_trains_saves_loads_and_predicts_schema_valid_records(tmp_path):
    examples = load_geominilm_dataset(STARTER_DATASET)
    checkpoint_path = tmp_path / "checkpoint.json"

    result = train_and_save_checkpoint(examples, checkpoint_path)
    loaded_model = GeoMiniLMPrototype.load(result.checkpoint_path)
    predictions = loaded_model.predict_many(examples)
    predictions_path = write_jsonl(tmp_path / "predictions.jsonl", predictions)

    loaded_predictions = load_jsonl(predictions_path, prediction=True)
    report = evaluate_records([example.to_record() for example in examples], loaded_predictions)

    assert checkpoint_path.exists()
    assert result.metadata["training_records"] == 12
    assert result.metadata["vocabulary_size"] > 0
    assert report.passed is True
    assert report.summary_score == 1.0
    assert predictions[0]["source_checkpoint_record_id"] == examples[0].id


def test_compare_reports_records_trained_vs_dry_run_baseline():
    examples = load_geominilm_dataset(STARTER_DATASET)
    model = GeoMiniLMPrototype.train(examples)
    expected = [example.to_record() for example in examples]

    trained_report = evaluate_records(expected, model.predict_many(examples))
    baseline_report = evaluate_records(expected, build_baseline_predictions(examples))
    comparison = compare_reports(trained_report, baseline_report)

    assert comparison["trained_passed"] is True
    assert comparison["baseline_passed"] is True
    assert comparison["summary_delta"] == 0.0
    assert len(comparison["record_deltas"]) == len(examples)


def test_leave_one_out_evaluation_excludes_heldout_examples_from_training(tmp_path):
    examples = load_geominilm_dataset(STARTER_DATASET)
    result = run_leave_one_out_evaluation(examples, tmp_path / "folds")

    assert len(result.folds) == len(examples)
    assert result.baseline_report.summary_score == 1.0
    assert result.heldout_report.summary_score < result.baseline_report.summary_score
    assert result.comparison["heldout_summary_score"] == round(result.heldout_report.summary_score, 4)
    assert result.comparison["baseline_summary_score"] == 1.0
    assert result.comparison["summary_delta"] < 0.0
    assert result.comparison["failure_count"] == 0
    assert result.comparison["records_with_findings_count"] == len(examples)
    assert result.comparison["confidence_calibration"]["record_count"] == len(examples)
    assert "expected_calibration_error" in result.comparison["confidence_calibration"]
    assert result.comparison["failed_examples"] == []
    assert result.comparison["records_with_findings"]
    for fold in result.folds:
        assert fold.record_id not in fold.training_record_ids
        assert fold.prediction["source_checkpoint_record_id"] != fold.record_id
        assert fold.checkpoint_path.exists()


def test_training_derived_development_evaluation_clears_model_selection_floor(tmp_path):
    development_examples = load_geominilm_dataset(STARTER_DATASET) + load_geominilm_dataset(TRAINING_EXPANSION)
    result = run_leave_one_out_evaluation(development_examples, tmp_path / "development_folds")

    assert len(result.folds) == 29
    assert result.comparison["heldout_summary_score"] >= 0.75
    assert result.baseline_report.summary_score == 1.0
    for fold in result.folds:
        assert fold.record_id not in fold.training_record_ids


def test_grouped_holdout_evaluation_excludes_workflow_families_from_retrieval_checkpoint(tmp_path):
    development_examples = load_geominilm_dataset(STARTER_DATASET) + load_geominilm_dataset(TRAINING_EXPANSION)
    family_by_id = {
        "gis-terrain-analysis-001": "terrain",
        "gis-slope-only-002": "terrain",
        "train-gis-hillshade-custom-013": "terrain",
        "paraview-render-dem-007": "render",
        "train-paraview-contour-overlay-018": "render",
    }
    selected = [example for example in development_examples if example.id in family_by_id]

    result = run_grouped_holdout_evaluation(selected, tmp_path / "grouped_folds", family_by_id=family_by_id)

    assert result.comparison["workflow_family_count"] == 2
    assert result.comparison["fold_count"] == 2
    assert result.comparison["prediction_strategy_counts"] == {"workflow_template": 5}
    assert result.comparison["failure_count"] <= result.comparison["records_with_findings_count"]
    for prediction in result.predictions:
        assert prediction["confidence_source"] == "workflow_template_route"
        assert "retrieval_similarity" in prediction
        assert prediction["confidence"] != prediction["retrieval_similarity"]
        assert prediction["id"] not in prediction["fold_training_record_ids"]
        for grouped_id in prediction["heldout_group_record_ids"]:
            assert grouped_id not in prediction["fold_training_record_ids"]


def test_validation_experiment_uses_disjoint_frozen_validation_set(tmp_path):
    training_examples = load_geominilm_dataset(STARTER_DATASET) + load_geominilm_dataset(TRAINING_EXPANSION)
    validation_examples = load_geominilm_dataset(VALIDATION_DATASET)

    result = run_validation_experiment(training_examples, validation_examples, tmp_path / "validation_checkpoint.json")

    assert result.oracle_sanity_report.summary_score == 1.0
    assert result.comparison["reference_heldout_score"] == 0.4943
    assert result.comparison["trained_validation_score"] >= result.comparison["honest_baseline_score"]
    assert result.comparison["delta_vs_reference_heldout"] > 0.0
    assert result.comparison["validation_record_count"] == 14
    assert result.comparison["trained_validation_score"] == 0.6475
    assert result.comparison["failure_count"] == 10
    assert result.comparison["records_with_findings_count"] == 14
    assert result.comparison["confidence_calibration"]["method"] == "prediction_confidence"
    assert result.comparison["prediction_strategy_counts"] == {"workflow_template": 14}
    assert "production_decision" not in result.comparison
    assert all(prediction["id"] != prediction["source_checkpoint_record_id"] for prediction in result.predictions)


def test_validation_experiment_rejects_training_validation_leakage(tmp_path):
    training_examples = load_geominilm_dataset(STARTER_DATASET)
    validation_examples = [training_examples[0]]

    with pytest.raises(ValueError) as exc_info:
        run_validation_experiment(training_examples, validation_examples, tmp_path / "validation_checkpoint.json")

    assert training_examples[0].id in str(exc_info.value)


def test_validation_experiment_is_deterministic_and_improves_multiple_categories(tmp_path):
    training_examples = load_geominilm_dataset(STARTER_DATASET) + load_geominilm_dataset(TRAINING_EXPANSION)
    validation_examples = load_geominilm_dataset(VALIDATION_DATASET)

    first = run_validation_experiment(training_examples, validation_examples, tmp_path / "first.json")
    second = run_validation_experiment(training_examples, validation_examples, tmp_path / "second.json")
    first.comparison.pop("category_results", None)
    second.comparison.pop("category_results", None)

    assert first.comparison == second.comparison
    improved_categories = {
        record["id"]
        for record in first.comparison["record_deltas"]
        if record["trained_score"] > record["honest_baseline_score"]
    }
    assert len(improved_categories) >= 4


def write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    return path
