from __future__ import annotations

import json
from pathlib import Path

import pytest

from geovis_lm.eval.workflow_eval import (
    EvaluationInputError,
    evaluate_files,
    evaluate_records,
    load_jsonl,
    write_json_report,
    write_markdown_report,
)


def expected_record() -> dict:
    return {
        "id": "gis-test-001",
        "domain": "gis",
        "instruction": "Create a slope raster from a DEM.",
        "inputs": {"dem_path": "data/sample/sample_dem.tif", "output_path": "outputs/maps/slope.tif"},
        "expected_workflow": [
            {
                "step": 1,
                "action": "Load the DEM raster and preserve metadata.",
                "tool": "rasterio",
                "output": "DEM array plus raster metadata.",
            },
            {
                "step": 2,
                "action": "Calculate slope in degrees.",
                "tool": "numpy gradient operations",
                "output": "outputs/maps/slope.tif",
            },
        ],
        "explanation": "Slope requires DEM grid spacing and preserved metadata for aligned output.",
    }


def prediction_record(**overrides) -> dict:
    record = {
        "id": "gis-test-001",
        "domain": "gis",
        "instruction": "Create a slope raster from a DEM.",
        "inputs": {"dem_path": "data/sample/sample_dem.tif", "output_path": "outputs/maps/slope.tif"},
        "predicted_workflow": [
            {
                "step": 1,
                "action": "Load the DEM raster and preserve metadata.",
                "tool": "rasterio",
                "output": "DEM array plus raster metadata.",
            },
            {
                "step": 2,
                "action": "Calculate slope in degrees.",
                "tool": "numpy gradient operations",
                "output": "outputs/maps/slope.tif",
            },
        ],
        "explanation": "Slope requires DEM grid spacing and preserved metadata for aligned output.",
    }
    record.update(overrides)
    return record


def write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    return path


def test_evaluate_records_scores_valid_prediction_as_pass():
    report = evaluate_records([expected_record()], [prediction_record()])

    assert report.passed is True
    assert report.summary_score == 1.0
    assert report.records[0].findings == []


def test_load_jsonl_reports_malformed_records(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"id": "broken"\n', encoding="utf-8")

    with pytest.raises(EvaluationInputError) as exc_info:
        load_jsonl(path)

    assert "invalid JSON" in exc_info.value.errors[0]


def test_load_jsonl_reports_incomplete_prediction(tmp_path):
    path = write_jsonl(
        tmp_path / "incomplete.jsonl",
        [{"id": "gis-test-001", "domain": "gis", "instruction": "x", "inputs": {}}],
    )

    with pytest.raises(EvaluationInputError) as exc_info:
        load_jsonl(path, prediction=True)

    assert any("missing required fields" in error for error in exc_info.value.errors)
    assert any("missing workflow field" in error for error in exc_info.value.errors)


def test_evaluate_records_reports_missing_prediction():
    report = evaluate_records([expected_record()], [])

    assert report.passed is False
    assert report.missing_predictions == 1
    assert report.records[0].findings == ["missing_prediction"]


def test_evaluate_records_allows_partial_tool_match_above_threshold():
    partial_tool = prediction_record(
        predicted_workflow=[
            {
                "step": 1,
                "action": "Load the DEM raster and preserve metadata.",
                "tool": "Use rasterio",
                "output": "DEM array plus raster metadata.",
            },
            {
                "step": 2,
                "action": "Calculate slope in degrees.",
                "tool": "Use numpy gradient operations",
                "output": "outputs/maps/slope.tif",
            },
        ]
    )

    report = evaluate_records([expected_record()], [partial_tool])

    assert report.passed is True
    assert report.records[0].score >= 0.75
    assert "tool_choice_partial" in report.records[0].findings
    assert "tool_choice_mismatch" in report.records[0].findings


def test_evaluate_records_reports_mismatched_prediction():
    mismatched = prediction_record(
        inputs={"dem_path": "wrong.tif"},
        predicted_workflow=[
            {
                "step": 1,
                "action": "Open a spreadsheet.",
                "tool": "pandas",
                "output": "table rows",
            }
        ],
        explanation="Too short.",
    )

    report = evaluate_records([expected_record()], [mismatched])

    assert report.passed is False
    assert report.records[0].score < 0.75
    assert "workflow_step_count_mismatch" in report.records[0].findings
    assert "invalid_tools" in report.records[0].findings
    assert "output_path_mismatch" in report.records[0].findings


@pytest.mark.parametrize("threshold", [-1.0, 1.1, float("nan"), float("inf")])
def test_evaluate_records_rejects_invalid_pass_threshold(threshold):
    with pytest.raises(EvaluationInputError) as exc_info:
        evaluate_records([expected_record()], [prediction_record()], pass_threshold=threshold)

    assert exc_info.value.errors == ["pass threshold must be a finite number from 0 through 1"]


def test_evaluate_files_writes_json_and_markdown_reports(tmp_path):
    expected_path = write_jsonl(tmp_path / "expected.jsonl", [expected_record()])
    predictions_path = write_jsonl(tmp_path / "predictions.jsonl", [prediction_record()])

    report = evaluate_files(expected_path, predictions_path)
    json_path = write_json_report(report, tmp_path / "evaluation_report.json")
    markdown_path = write_markdown_report(report, tmp_path / "evaluation_report.md")

    assert json.loads(json_path.read_text(encoding="utf-8"))["passed"] is True
    assert "GeoMiniLM Workflow Evaluation" in markdown_path.read_text(encoding="utf-8")
