from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_train_geominilm_help_succeeds():
    result = subprocess.run(
        [sys.executable, "scripts/train_geominilm.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--dry-run" in result.stdout


def test_train_geominilm_dry_run_writes_artifacts(tmp_path):
    output_dir = tmp_path / "model"
    predictions_dir = tmp_path / "predictions"
    eval_dir = tmp_path / "eval"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/train_geominilm.py",
            "--dataset",
            "data/geominilm/starter_workflows.jsonl",
            "--output-dir",
            str(output_dir),
            "--predictions-dir",
            str(predictions_dir),
            "--eval-dir",
            str(eval_dir),
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    report = json.loads((eval_dir / "evaluation_report.json").read_text(encoding="utf-8"))

    assert metadata["dry_run"] is True
    assert metadata["summary"]["total_records"] == 12
    assert (output_dir / "training_pairs.jsonl").exists()
    assert (predictions_dir / "dry_run_predictions.jsonl").exists()
    assert report["passed"] is True
    assert "GeoMiniLM dry run complete" in result.stdout


def test_train_geominilm_training_writes_checkpoint_predictions_and_comparison(tmp_path):
    output_dir = tmp_path / "model"
    predictions_dir = tmp_path / "predictions"
    eval_dir = tmp_path / "eval"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/train_geominilm.py",
            "--dataset",
            "data/geominilm/starter_workflows.jsonl",
            "--output-dir",
            str(output_dir),
            "--predictions-dir",
            str(predictions_dir),
            "--eval-dir",
            str(eval_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    metadata = json.loads((output_dir / "metadata.json").read_text(encoding="utf-8"))
    report = json.loads((eval_dir / "evaluation_report.json").read_text(encoding="utf-8"))
    comparison = json.loads((eval_dir / "baseline_comparison.json").read_text(encoding="utf-8"))

    assert metadata["dry_run"] is False
    assert metadata["training_status"] == "complete"
    assert metadata["training"]["training_records"] == 12
    assert (output_dir / "checkpoint.json").exists()
    assert (predictions_dir / "trained_predictions.jsonl").exists()
    assert report["passed"] is True
    assert comparison["summary_delta"] == 0.0
    assert "GeoMiniLM training complete" in result.stdout


def test_train_geominilm_held_out_eval_writes_excluded_fold_reports(tmp_path):
    output_dir = tmp_path / "model"
    predictions_dir = tmp_path / "predictions"
    eval_dir = tmp_path / "eval"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/train_geominilm.py",
            "--dataset",
            "data/geominilm/starter_workflows.jsonl",
            "--output-dir",
            str(output_dir),
            "--predictions-dir",
            str(predictions_dir),
            "--eval-dir",
            str(eval_dir),
            "--held-out-eval",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    metadata = json.loads((output_dir / "heldout_metadata.json").read_text(encoding="utf-8"))
    comparison = json.loads((eval_dir / "baseline_comparison.json").read_text(encoding="utf-8"))
    calibration = json.loads((eval_dir / "confidence_calibration.json").read_text(encoding="utf-8"))
    predictions = [
        json.loads(line)
        for line in (predictions_dir / "heldout_predictions.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert metadata["training_status"] == "held_out_complete"
    assert metadata["training"]["fold_count"] == 12
    assert comparison["heldout_summary_score"] < comparison["baseline_summary_score"]
    assert comparison["confidence_calibration"] == calibration
    assert calibration["method"] == "workflow_score_as_confidence_proxy"
    assert "expected_calibration_error" in calibration
    assert comparison["failed_examples"]
    assert (eval_dir / "evaluation_report.md").exists()
    for prediction in predictions:
        assert prediction["id"] not in prediction["fold_training_record_ids"]
        assert prediction["source_checkpoint_record_id"] != prediction["id"]
    assert "GeoMiniLM held-out evaluation complete" in result.stdout


def test_train_geominilm_validation_experiment_writes_honest_baseline_reports(tmp_path):
    output_dir = tmp_path / "model"
    predictions_dir = tmp_path / "predictions"
    eval_dir = tmp_path / "eval"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/train_geominilm.py",
            "--dataset",
            "data/geominilm/starter_workflows.jsonl",
            "--extra-training-data",
            "data/geominilm/training_expansion_workflows.jsonl",
            "--validation-set",
            "data/geominilm/validation_workflows.jsonl",
            "--output-dir",
            str(output_dir),
            "--predictions-dir",
            str(predictions_dir),
            "--eval-dir",
            str(eval_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    metadata = json.loads((output_dir / "validation_experiment_metadata.json").read_text(encoding="utf-8"))
    comparison = json.loads((eval_dir / "experiment_comparison.json").read_text(encoding="utf-8"))
    split_validation = json.loads((eval_dir / "split_validation.json").read_text(encoding="utf-8"))
    manifest_check = json.loads((eval_dir / "manifest_check.json").read_text(encoding="utf-8"))
    calibration = json.loads((eval_dir / "confidence_calibration.json").read_text(encoding="utf-8"))
    production_decision = json.loads((eval_dir / "production_decision.json").read_text(encoding="utf-8"))

    assert metadata["training_status"] == "validation_experiment_complete"
    assert metadata["training"]["training_records"] == 29
    assert metadata["training"]["validation_records"] == 14
    assert comparison["primary_metric"] == "trained_validation_score"
    assert comparison["pass_threshold"] == 0.75
    assert comparison["minimum_validation_records"] == 12
    assert comparison["minimum_threshold_margin"] == 0.01
    assert comparison["validation_record_count"] == 14
    assert comparison["oracle_sanity_score"] == 1.0
    assert comparison["reference_heldout_score"] == 0.4943
    assert comparison["confidence_calibration"] == calibration
    assert comparison["production_decision"] == production_decision
    assert "category_results" in comparison
    assert comparison["category_results"]["qgis_styling_and_layout_exports"]["total_count"] == 4
    improved_categories = [
        category
        for category in comparison["category_results"].values()
        if category["trained_score"] > category["honest_baseline_score"]
    ]
    assert len(improved_categories) >= 3
    assert "oracle/sanity" not in comparison["baseline_notes"]["honest_baseline"]
    assert "directional" in comparison["baseline_notes"]["reference_heldout"]
    assert split_validation["passed"] is True
    assert split_validation["issues"] == []
    assert manifest_check["passed"] is True
    assert calibration["method"] == "workflow_score_as_confidence_proxy"
    assert "expected_calibration_error" in calibration
    assert "reliability_bins" in calibration
    assert production_decision["dashboard_integration_allowed"] == (
        comparison["trained_validation_score"] > comparison["honest_baseline_score"]
        and comparison["trained_validation_score"] >= production_decision["required_metric_value"]
        and comparison["validation_record_count"] >= comparison["minimum_validation_records"]
    )
    assert (predictions_dir / "honest_baseline_predictions.jsonl").exists()
    assert (eval_dir / "evaluation_manifest.json").exists()
    assert (eval_dir / "experiment_comparison.md").exists()
    assert "GeoMiniLM validation experiment complete" in result.stdout
