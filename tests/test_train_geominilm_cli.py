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
