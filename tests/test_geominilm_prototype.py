from __future__ import annotations

import json
from pathlib import Path

from geovis_lm.eval.workflow_eval import evaluate_records, load_jsonl
from geovis_lm.model.dataset import build_baseline_predictions, load_geominilm_dataset
from geovis_lm.model.prototype import GeoMiniLMPrototype, compare_reports, train_and_save_checkpoint


STARTER_DATASET = Path("data/geominilm/starter_workflows.jsonl")


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


def write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    return path
