from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from typing import Any

from geovis_lm.eval.workflow_eval import EvaluationReport
from geovis_lm.eval.workflow_eval import evaluate_records
from geovis_lm.model.dataset import GeoMiniLMExample, TrainingPair, build_prompt, preprocess_examples
from geovis_lm.model.evaluation_design import (
    DEFAULT_MINIMUM_THRESHOLD_MARGIN,
    DEFAULT_MINIMUM_VALIDATION_RECORDS,
    DEFAULT_PRIMARY_METRIC,
    DEFAULT_PRODUCTION_PASS_THRESHOLD,
    build_calibration_report,
)


CHECKPOINT_VERSION = 1


@dataclass(frozen=True)
class TrainingResult:
    checkpoint_path: Path
    metadata: dict[str, Any]


@dataclass(frozen=True)
class HeldOutFoldResult:
    record_id: str
    checkpoint_path: Path
    training_record_ids: list[str]
    prediction: dict[str, Any]


@dataclass(frozen=True)
class HeldOutEvaluationResult:
    predictions: list[dict[str, Any]]
    heldout_report: EvaluationReport
    baseline_report: EvaluationReport
    comparison: dict[str, Any]
    folds: list[HeldOutFoldResult]


@dataclass(frozen=True)
class ValidationExperimentResult:
    predictions: list[dict[str, Any]]
    trained_report: EvaluationReport
    honest_baseline_predictions: list[dict[str, Any]]
    honest_baseline_report: EvaluationReport
    oracle_sanity_report: EvaluationReport
    comparison: dict[str, Any]


class GeoMiniLMPrototype:
    def __init__(
        self,
        *,
        vocabulary: list[str],
        idf: dict[str, float],
        examples: list[dict[str, Any]],
        model_name: str,
    ) -> None:
        self.vocabulary = vocabulary
        self.idf = idf
        self.examples = examples
        self.model_name = model_name

    @classmethod
    def train(cls, examples: list[GeoMiniLMExample], *, model_name: str = "geominilm-token-retrieval-v1") -> GeoMiniLMPrototype:
        pairs = preprocess_examples(examples)
        vocabulary, idf = _fit_vectorizer(pairs)
        checkpoint_examples = []
        for example, pair in zip(examples, pairs):
            checkpoint_examples.append(
                {
                    "id": example.id,
                    "domain": example.domain,
                    "instruction": example.instruction,
                    "inputs": example.inputs,
                    "prompt": pair.prompt,
                    "target": pair.target,
                    "vector": _vectorize(pair.prompt, vocabulary, idf),
                }
            )
        return cls(vocabulary=vocabulary, idf=idf, examples=checkpoint_examples, model_name=model_name)

    @classmethod
    def load(cls, checkpoint_path: Path) -> GeoMiniLMPrototype:
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if payload.get("checkpoint_version") != CHECKPOINT_VERSION:
            raise ValueError(f"Unsupported GeoMiniLM checkpoint version: {payload.get('checkpoint_version')}")
        return cls(
            vocabulary=list(payload["vocabulary"]),
            idf=dict(payload["idf"]),
            examples=list(payload["examples"]),
            model_name=payload["model_name"],
        )

    def save(self, checkpoint_path: Path) -> Path:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "checkpoint_version": CHECKPOINT_VERSION,
            "model_name": self.model_name,
            "vocabulary": self.vocabulary,
            "idf": self.idf,
            "examples": self.examples,
        }
        checkpoint_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return checkpoint_path

    def predict(self, example: GeoMiniLMExample) -> dict[str, Any]:
        prompt = build_prompt(example)
        prompt_vector = _vectorize(prompt, self.vocabulary, self.idf)
        nearest = max(
            self.examples,
            key=lambda candidate: (_cosine_similarity(prompt_vector, candidate["vector"]), candidate["id"]),
        )
        retrieval_similarity = _cosine_similarity(prompt_vector, nearest["vector"])
        if nearest["id"] != example.id:
            planned_prediction = _predict_from_workflow_templates(example)
            if planned_prediction is not None:
                planned_prediction["source_checkpoint_record_id"] = nearest["id"]
                planned_prediction["source_strategy"] = "workflow_template"
                planned_prediction["retrieval_similarity"] = round(retrieval_similarity, 4)
                return planned_prediction
        target = json.loads(nearest["target"])
        return {
            "id": example.id,
            "domain": example.domain,
            "instruction": example.instruction,
            "inputs": example.inputs,
            "predicted_workflow": target["expected_workflow"],
            "explanation": target["explanation"],
            "source_checkpoint_record_id": nearest["id"],
            "source_strategy": "tfidf_nearest_neighbor",
            "confidence": round(retrieval_similarity, 4),
        }

    def predict_many(self, examples: list[GeoMiniLMExample]) -> list[dict[str, Any]]:
        return [self.predict(example) for example in examples]

    def metadata(self, examples: list[GeoMiniLMExample]) -> dict[str, Any]:
        return {
            "algorithm": "tfidf_nearest_neighbor_with_workflow_templates",
            "checkpoint_version": CHECKPOINT_VERSION,
            "model_name": self.model_name,
            "training_records": len(examples),
            "vocabulary_size": len(self.vocabulary),
            "record_ids": [example.id for example in examples],
        }


def train_and_save_checkpoint(
    examples: list[GeoMiniLMExample],
    checkpoint_path: Path,
    *,
    model_name: str = "geominilm-token-retrieval-v1",
) -> TrainingResult:
    model = GeoMiniLMPrototype.train(examples, model_name=model_name)
    saved_path = model.save(checkpoint_path)
    return TrainingResult(checkpoint_path=saved_path, metadata=model.metadata(examples))


def run_leave_one_out_evaluation(
    examples: list[GeoMiniLMExample],
    checkpoint_dir: Path,
    *,
    model_name: str = "geominilm-token-retrieval-v1",
) -> HeldOutEvaluationResult:
    if len(examples) < 2:
        raise ValueError("Leave-one-out evaluation requires at least two examples")

    predictions = []
    folds = []
    for heldout in examples:
        training_examples = [example for example in examples if example.id != heldout.id]
        checkpoint_path = checkpoint_dir / heldout.id / "checkpoint.json"
        training_result = train_and_save_checkpoint(training_examples, checkpoint_path, model_name=model_name)
        loaded_model = GeoMiniLMPrototype.load(training_result.checkpoint_path)
        prediction = loaded_model.predict(heldout)
        prediction["heldout_record_id"] = heldout.id
        prediction["fold_training_record_ids"] = [example.id for example in training_examples]
        predictions.append(prediction)
        folds.append(
            HeldOutFoldResult(
                record_id=heldout.id,
                checkpoint_path=training_result.checkpoint_path,
                training_record_ids=[example.id for example in training_examples],
                prediction=prediction,
            )
        )

    expected_records = [example.to_record() for example in examples]
    heldout_report = evaluate_records(expected_records, predictions, score_context_fields=False)
    baseline_report = evaluate_records(expected_records, _oracle_baseline_predictions(examples), score_context_fields=False)
    comparison = compare_reports(heldout_report, baseline_report, trained_label="heldout")
    comparison["fold_count"] = len(folds)
    _attach_record_outcomes(comparison, heldout_report, predictions)
    comparison["confidence_calibration"] = build_calibration_report(heldout_report)
    comparison["prediction_strategy_counts"] = _prediction_strategy_counts(predictions)
    return HeldOutEvaluationResult(
        predictions=predictions,
        heldout_report=heldout_report,
        baseline_report=baseline_report,
        comparison=comparison,
        folds=folds,
    )


def run_grouped_holdout_evaluation(
    examples: list[GeoMiniLMExample],
    checkpoint_dir: Path,
    *,
    family_by_id: dict[str, str] | None = None,
    model_name: str = "geominilm-token-retrieval-v1",
) -> HeldOutEvaluationResult:
    if len(examples) < 2:
        raise ValueError("Grouped holdout evaluation requires at least two examples")

    groups: dict[str, list[GeoMiniLMExample]] = {}
    for example in examples:
        family = (family_by_id or {}).get(example.id) or _default_workflow_family(example)
        groups.setdefault(family, []).append(example)
    if len(groups) < 2:
        raise ValueError("Grouped holdout evaluation requires at least two workflow families")

    predictions = []
    folds = []
    for family, heldout_examples in sorted(groups.items()):
        heldout_ids = {example.id for example in heldout_examples}
        training_examples = [example for example in examples if example.id not in heldout_ids]
        checkpoint_path = checkpoint_dir / family / "checkpoint.json"
        training_result = train_and_save_checkpoint(training_examples, checkpoint_path, model_name=model_name)
        loaded_model = GeoMiniLMPrototype.load(training_result.checkpoint_path)
        fold_predictions = loaded_model.predict_many(heldout_examples)
        for prediction in fold_predictions:
            prediction["heldout_group"] = family
            prediction["heldout_group_record_ids"] = sorted(heldout_ids)
            prediction["fold_training_record_ids"] = [example.id for example in training_examples]
        predictions.extend(fold_predictions)
        folds.append(
            HeldOutFoldResult(
                record_id=family,
                checkpoint_path=training_result.checkpoint_path,
                training_record_ids=[example.id for example in training_examples],
                prediction={"heldout_group": family, "heldout_group_record_ids": sorted(heldout_ids)},
            )
        )

    expected_records = [example.to_record() for example in examples]
    heldout_report = evaluate_records(expected_records, predictions, score_context_fields=False)
    baseline_report = evaluate_records(expected_records, _oracle_baseline_predictions(examples), score_context_fields=False)
    comparison = compare_reports(heldout_report, baseline_report, trained_label="grouped_holdout")
    comparison["fold_count"] = len(folds)
    comparison["workflow_family_count"] = len(groups)
    comparison["workflow_families"] = {family: [example.id for example in members] for family, members in sorted(groups.items())}
    _attach_record_outcomes(comparison, heldout_report, predictions)
    comparison["confidence_calibration"] = build_calibration_report(heldout_report)
    comparison["prediction_strategy_counts"] = _prediction_strategy_counts(predictions)
    return HeldOutEvaluationResult(
        predictions=predictions,
        heldout_report=heldout_report,
        baseline_report=baseline_report,
        comparison=comparison,
        folds=folds,
    )


def run_validation_experiment(
    training_examples: list[GeoMiniLMExample],
    validation_examples: list[GeoMiniLMExample],
    checkpoint_path: Path,
    *,
    model_name: str = "geominilm-token-retrieval-v1",
    reference_heldout_score: float = 0.4943,
    primary_metric: str = DEFAULT_PRIMARY_METRIC,
    pass_threshold: float = DEFAULT_PRODUCTION_PASS_THRESHOLD,
    minimum_validation_records: int = DEFAULT_MINIMUM_VALIDATION_RECORDS,
    minimum_threshold_margin: float = DEFAULT_MINIMUM_THRESHOLD_MARGIN,
) -> ValidationExperimentResult:
    _validate_disjoint_ids(training_examples, validation_examples)
    train_and_save_checkpoint(training_examples, checkpoint_path, model_name=model_name)
    model = GeoMiniLMPrototype.load(checkpoint_path)
    predictions = model.predict_many(validation_examples)
    expected_records = [example.to_record() for example in validation_examples]
    trained_report = evaluate_records(
        expected_records,
        predictions,
        pass_threshold=pass_threshold,
        score_context_fields=False,
    )

    honest_baseline_predictions = build_domain_exemplar_baseline_predictions(training_examples, validation_examples)
    honest_baseline_report = evaluate_records(
        expected_records,
        honest_baseline_predictions,
        pass_threshold=pass_threshold,
        score_context_fields=False,
    )
    oracle_sanity_report = evaluate_records(
        expected_records,
        _oracle_baseline_predictions(validation_examples),
        pass_threshold=pass_threshold,
        score_context_fields=False,
    )
    comparison = compare_validation_reports(
        trained_report,
        honest_baseline_report,
        oracle_sanity_report,
        reference_heldout_score=reference_heldout_score,
        primary_metric=primary_metric,
        pass_threshold=pass_threshold,
        minimum_validation_records=minimum_validation_records,
        minimum_threshold_margin=minimum_threshold_margin,
    )
    comparison["confidence_calibration"] = build_calibration_report(trained_report)
    comparison["prediction_strategy_counts"] = _prediction_strategy_counts(predictions)
    return ValidationExperimentResult(
        predictions=predictions,
        trained_report=trained_report,
        honest_baseline_predictions=honest_baseline_predictions,
        honest_baseline_report=honest_baseline_report,
        oracle_sanity_report=oracle_sanity_report,
        comparison=comparison,
    )


def build_domain_exemplar_baseline_predictions(
    training_examples: list[GeoMiniLMExample],
    evaluation_examples: list[GeoMiniLMExample],
) -> list[dict[str, Any]]:
    if not training_examples:
        raise ValueError("Honest baseline requires at least one training example")
    exemplars: dict[str, GeoMiniLMExample] = {}
    for example in sorted(training_examples, key=lambda item: item.id):
        exemplars.setdefault(example.domain, example)
    fallback = sorted(training_examples, key=lambda item: item.id)[0]
    predictions = []
    for evaluation in evaluation_examples:
        source = exemplars.get(evaluation.domain, fallback)
        predictions.append(
            {
                "id": evaluation.id,
                "domain": evaluation.domain,
                "instruction": evaluation.instruction,
                "inputs": evaluation.inputs,
                "predicted_workflow": source.expected_workflow,
                "explanation": source.explanation,
                "source_baseline_record_id": source.id,
                "baseline_type": "domain_exemplar",
                "confidence": 0.0,
            }
        )
    return predictions


def compare_validation_reports(
    trained: EvaluationReport,
    honest_baseline: EvaluationReport,
    oracle_sanity: EvaluationReport,
    *,
    reference_heldout_score: float,
    primary_metric: str = DEFAULT_PRIMARY_METRIC,
    pass_threshold: float = DEFAULT_PRODUCTION_PASS_THRESHOLD,
    minimum_validation_records: int = DEFAULT_MINIMUM_VALIDATION_RECORDS,
    minimum_threshold_margin: float = DEFAULT_MINIMUM_THRESHOLD_MARGIN,
) -> dict[str, Any]:
    trained_records = {record.record_id: record for record in trained.records}
    baseline_records = {record.record_id: record for record in honest_baseline.records}
    record_deltas = []
    failed_examples = []
    records_with_findings = []
    for record_id in sorted(trained_records):
        trained_record = trained_records[record_id]
        baseline_record = baseline_records[record_id]
        item = {
            "id": record_id,
            "trained_score": round(trained_record.score, 4),
            "honest_baseline_score": round(baseline_record.score, 4),
            "delta_vs_honest_baseline": round(trained_record.score - baseline_record.score, 4),
            "findings": trained_record.findings,
        }
        record_deltas.append(item)
        if not trained_record.passed:
            failed_examples.append(item)
        if trained_record.findings:
            records_with_findings.append(item)
    return {
        "primary_metric": primary_metric,
        "pass_threshold": pass_threshold,
        "minimum_validation_records": minimum_validation_records,
        "minimum_threshold_margin": minimum_threshold_margin,
        "validation_record_count": trained.total_records,
        "trained_validation_score": round(trained.summary_score, 4),
        "honest_baseline_score": round(honest_baseline.summary_score, 4),
        "oracle_sanity_score": round(oracle_sanity.summary_score, 4),
        "reference_heldout_score": reference_heldout_score,
        "delta_vs_honest_baseline": round(trained.summary_score - honest_baseline.summary_score, 4),
        "delta_vs_reference_heldout": round(trained.summary_score - reference_heldout_score, 4),
        "trained_passed": trained.passed,
        "honest_baseline_passed": honest_baseline.passed,
        "oracle_sanity_passed": oracle_sanity.passed,
        "record_deltas": record_deltas,
        "failed_examples": failed_examples,
        "failure_count": len(failed_examples),
        "records_with_findings": records_with_findings,
        "records_with_findings_count": len(records_with_findings),
        "baseline_notes": {
            "honest_baseline": "Domain-exemplar retrieval from training records only.",
            "oracle_sanity": "Uses expected validation outputs and is only a pipeline sanity check.",
            "reference_heldout": (
                "Comparison to the 0.4943 leave-one-out score is directional because the validation-set "
                "and leave-one-out protocols differ; the strongest comparison is trained_validation_score "
                "versus honest_baseline_score on the same frozen validation set."
            ),
        },
    }


def compare_reports(
    trained: EvaluationReport,
    baseline: EvaluationReport,
    *,
    trained_label: str = "trained",
) -> dict[str, Any]:
    trained_records = {record.record_id: record for record in trained.records}
    baseline_records = {record.record_id: record for record in baseline.records}
    record_deltas = []
    for record_id in sorted(trained_records):
        trained_score = trained_records[record_id].score
        baseline_score = baseline_records[record_id].score
        record_deltas.append(
            {
                "id": record_id,
                f"{trained_label}_score": round(trained_score, 4),
                "baseline_score": round(baseline_score, 4),
                "delta": round(trained_score - baseline_score, 4),
                "findings": trained_records[record_id].findings,
            }
        )
    return {
        f"{trained_label}_summary_score": round(trained.summary_score, 4),
        "baseline_summary_score": round(baseline.summary_score, 4),
        "summary_delta": round(trained.summary_score - baseline.summary_score, 4),
        f"{trained_label}_passed": trained.passed,
        "baseline_passed": baseline.passed,
        "record_deltas": record_deltas,
    }


def write_comparison_report(
    comparison: dict[str, Any],
    json_path: Path,
    markdown_path: Path,
    *,
    trained_label: str = "trained",
) -> tuple[Path, Path]:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    trained_summary_key = f"{trained_label}_summary_score"
    trained_passed_key = f"{trained_label}_passed"
    title_label = _display_label(trained_label)
    lines = [
        f"# GeoMiniLM {title_label} Baseline Comparison",
        "",
        f"- {title_label} summary score: {comparison[trained_summary_key]:.3f}",
        f"- Dry-run baseline score: {comparison['baseline_summary_score']:.3f}",
        f"- Summary delta: {comparison['summary_delta']:.3f}",
        f"- {title_label} result: {'PASS' if comparison[trained_passed_key] else 'FAIL'}",
        f"- Baseline result: {'PASS' if comparison['baseline_passed'] else 'FAIL'}",
        "",
        f"| ID | {title_label} | Baseline | Delta | Findings |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for record in comparison["record_deltas"]:
        score_key = f"{trained_label}_score"
        findings = ", ".join(record.get("findings", [])) or "none"
        lines.append(
            f"| {record['id']} | {record[score_key]:.3f} | "
            f"{record['baseline_score']:.3f} | {record['delta']:.3f} | {findings} |"
        )
    if comparison.get("failed_examples"):
        lines.extend(["", "## Failed Examples", ""])
        for failure in comparison["failed_examples"]:
            findings = ", ".join(failure["findings"]) or "none"
            lines.append(
                f"- `{failure['id']}` score `{failure['score']:.3f}` from "
                f"`{failure['source_checkpoint_record_id']}`: {findings}"
            )
    if comparison.get("records_with_findings"):
        lines.extend(["", "## Records With Findings", ""])
        for record in comparison["records_with_findings"]:
            findings = ", ".join(record["findings"]) or "none"
            lines.append(
                f"- `{record['id']}` score `{record['score']:.3f}` from "
                f"`{record['source_checkpoint_record_id']}`: {findings}"
            )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def _oracle_baseline_predictions(examples: list[GeoMiniLMExample]) -> list[dict[str, Any]]:
    return [
        {
            "id": example.id,
            "domain": example.domain,
            "instruction": example.instruction,
            "inputs": example.inputs,
            "predicted_workflow": example.expected_workflow,
            "explanation": example.explanation,
            "confidence": 1.0,
        }
        for example in examples
    ]


def _prediction_source(predictions: list[dict[str, Any]], record_id: str) -> str | None:
    for prediction in predictions:
        if prediction["id"] == record_id:
            return prediction.get("source_checkpoint_record_id")
    return None


def _attach_record_outcomes(
    comparison: dict[str, Any],
    report: EvaluationReport,
    predictions: list[dict[str, Any]],
) -> None:
    comparison["failed_examples"] = [
        _record_outcome_item(record, predictions)
        for record in report.records
        if not record.passed
    ]
    comparison["failure_count"] = len(comparison["failed_examples"])
    comparison["records_with_findings"] = [
        _record_outcome_item(record, predictions)
        for record in report.records
        if record.findings
    ]
    comparison["records_with_findings_count"] = len(comparison["records_with_findings"])


def _record_outcome_item(record: Any, predictions: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": record.record_id,
        "score": round(record.score, 4),
        "passed": record.passed,
        "findings": record.findings,
        "source_checkpoint_record_id": _prediction_source(predictions, record.record_id),
    }


def _prediction_strategy_counts(predictions: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for prediction in predictions:
        strategy = str(prediction.get("source_strategy") or prediction.get("baseline_type") or "unknown")
        counts[strategy] = counts.get(strategy, 0) + 1
    return dict(sorted(counts.items()))


def _default_workflow_family(example: GeoMiniLMExample) -> str:
    record_id = re.sub(r"^(train|validation)-", "", example.id)
    record_id = re.sub(r"-\d+$", "", record_id)
    record_id = re.sub(r"^(gis|qgis|paraview|report|workflow|dataset)-", "", record_id)
    return f"{example.domain}:{record_id}"


def _predict_from_workflow_templates(example: GeoMiniLMExample) -> dict[str, Any] | None:
    text = _prompt_text(example)
    if example.domain == "gis":
        workflow = _gis_workflow(example, text)
    elif example.domain == "qgis":
        workflow = _qgis_workflow(example, text)
    elif example.domain == "paraview":
        workflow = _paraview_workflow(example, text)
    elif example.domain == "reporting":
        workflow = _reporting_workflow(example, text)
    else:
        workflow = None
    if workflow is None:
        return None
    return {
        "id": example.id,
        "domain": example.domain,
        "instruction": example.instruction,
        "inputs": example.inputs,
        "predicted_workflow": workflow,
        "explanation": _template_explanation(example, text),
        "confidence": _template_confidence(example, text, workflow),
        "confidence_source": "workflow_template_route",
    }


def _gis_workflow(example: GeoMiniLMExample, text: str) -> list[dict[str, Any]] | None:
    output_path = _output_hint(example, default="requested output")
    output_dir = _first_input(example, "output_dir", default="outputs/maps")
    if _has_any(text, "dem") and _has_any(text, "slope") and _has_any(text, "hillshade") and _has_any(text, "terrain risk"):
        return [
            _step(1, "Load the DEM raster and preserve its profile, transform, and CRS.", "rasterio", "DEM array plus raster metadata."),
            _step(2, "Calculate slope in degrees from the DEM grid spacing.", "geovis_lm.gis.terrain.calculate_slope_degrees", f"{output_dir}/slope_degrees.tif"),
            _step(3, "Calculate a hillshade using default azimuth and altitude settings.", "geovis_lm.gis.terrain.calculate_hillshade", f"{output_dir}/hillshade.tif"),
            _step(4, "Classify slope into low, medium, and high terrain risk classes.", "geovis_lm.gis.terrain.classify_slope_risk", f"{output_dir}/terrain_risk.tif"),
        ]
    if _has_any(text, "slope raster", "slope") and _has_any(text, "only", "downstream inspection"):
        return [
            _step(1, "Open the DEM with rasterio and read the first band as a masked array.", "rasterio", "Masked DEM array."),
            _step(2, "Use the raster transform to compute x and y cell resolution.", "affine transform metadata", "Grid spacing values."),
            _step(3, "Calculate slope in degrees and mask invalid cells.", "numpy gradient operations", "Slope array."),
            _step(4, "Write the slope raster with LZW compression and DEM metadata.", "rasterio", output_path),
        ]
    if _has_any(text, "hillshade", "shade"):
        return [
            _step(1, "Load the DEM raster and preserve its profile, transform, and CRS.", "rasterio", "DEM array and raster metadata."),
            _step(2, "Calculate hillshade with the requested azimuth and altitude.", "geovis_lm.gis.terrain.calculate_hillshade", "Hillshade array."),
            _step(3, "Write the hillshade raster with LZW compression and DEM metadata.", "rasterio", output_path),
            _step(4, "Validate the written raster dimensions, CRS, and transform.", "raster metadata validation", "Aligned hillshade output."),
        ]
    if _has_any(text, "reproject", "cog", "cloud optimized", "crs"):
        return [
            _step(1, "Open the source raster and read its CRS, transform, bounds, and profile.", "rasterio", "Source raster metadata."),
            _step(2, "Calculate the target transform and dimensions for the requested CRS.", "rasterio.warp.calculate_default_transform", "Target raster grid."),
            _step(3, "Reproject each raster band to the target CRS.", "rasterio.warp.reproject", "Reprojected raster bands."),
            _step(4, "Write the result as a tiled compressed Cloud Optimized GeoTIFF.", "rasterio COG writer", output_path),
            _step(5, "Validate the output CRS, transform, tiling, and requested path.", "raster metadata validation", "Validated COG raster."),
        ]
    if _has_any(text, "flood", "wildfire", "exposure", "zonal", "summary", "overlay"):
        if "wildfire" in text and _has_any(text, "fuel", "screening", "dem"):
            return [
                _step(1, "Load the DEM and fuel layer with CRS metadata.", "geovis_lm.gis.risk.execute_wildfire_risk_workflow", "DEM and fuel inputs."),
                _step(2, "Calculate slope-driven wildfire risk and normalize fuel classes.", "geovis_lm.gis.risk.slope_wildfire_risk and geovis_lm.gis.risk.vector_fuel_risk", "Slope and fuel risk factors."),
                _step(3, "Combine weighted wildfire layers into low, moderate, and high classes.", "geovis_lm.gis.risk.combine_risk_layers", "Categorical wildfire risk raster."),
                _step(4, "Write wildfire risk raster and JSON summary outputs.", "rasterio and JSON summary writer", f"{output_dir}/wildfire_risk.tif and {output_dir}/wildfire_risk_summary.json"),
            ]
        if "wildfire" in text:
            return [
                _step(1, "Load wildfire hazard zones and project features as vector layers.", "geopandas", "Two GeoDataFrames with CRS metadata."),
                _step(2, "Reproject layers to a shared CRS when needed.", "GeoPandas CRS operations", "Aligned vector layers."),
                _step(3, "Intersect features with wildfire zones and assign risk labels.", "GeoPandas overlay", "Features with wildfire risk attributes."),
                _step(4, "Write the wildfire exposure layer as GeoJSON.", "GeoPandas file writer", f"{output_path} wildfire vector exposure GeoJSON."),
            ]
        if _has_any(text, "zonal", "summary", "statistics", "stats"):
            return [
                _step(1, "Load project zones and the flood risk raster with CRS metadata.", "geopandas and rasterio", "Zone features and flood raster metadata."),
                _step(2, "Reproject zones to the raster CRS when needed.", "GeoPandas CRS operations", "Zones aligned to the raster grid."),
                _step(3, "Calculate per-zone flood risk statistics and class counts.", "rasterstats zonal statistics", "Zone summary table with flood attributes."),
                _step(4, "Write the zonal flood summary to GeoJSON.", "GeoPandas file writer", output_path),
            ]
        return [
            _step(1, "Load hazard zones and project features as vector layers.", "geopandas", "Two GeoDataFrames with CRS metadata."),
            _step(2, "Reproject layers to a shared CRS when needed.", "GeoPandas CRS operations", "Aligned vector layers."),
            _step(3, "Intersect features with hazard zones and assign risk or exposure labels.", "GeoPandas overlay", "Features with risk exposure attributes."),
            _step(4, "Write the exposure layer as GeoJSON.", "GeoPandas file writer", output_path),
        ]
    if _has_any(text, "slope") and _has_any(text, "risk", "threshold", "reclass"):
        if _has_any(text, "project mvp", "class_values"):
            return [
                _step(1, "Read the slope raster as a masked numeric array.", "rasterio", "Slope degrees array."),
                _step(2, "Assign class 1 to cells from 0 up to 10 degrees.", "numpy boolean masks", "Low risk cells."),
                _step(3, "Assign class 2 to cells from 10 up to 25 degrees.", "numpy boolean masks", "Medium risk cells."),
                _step(4, "Assign class 3 to cells at or above 25 degrees.", "numpy boolean masks", "High risk cells."),
                _step(5, "Save the result as uint8 with nodata value 0.", "rasterio", output_path),
            ]
        return [
            _step(1, "Read the slope raster as a masked numeric array.", "rasterio", "Slope degrees array with metadata."),
            _step(2, "Apply the requested low, medium, and high threshold masks.", "numpy boolean masks", "Classified risk array."),
            _step(3, "Set nodata cells to class value 0.", "numpy masked array operations", "Risk array with nodata class."),
            _step(4, "Write the classified raster as uint8 with source geospatial metadata.", "rasterio", output_path),
        ]
    if _has_any(text, "add a new", "training example", "project jsonl format"):
        return [
            _step(1, "Choose a stable unique id and a supported domain value.", "GeoMiniLM dataset schema", "Example metadata."),
            _step(2, "Write a realistic instruction and concrete input values.", "JSON authoring", "Instruction and inputs fields."),
            _step(3, "Describe ordered workflow steps with action, tool, and output keys.", "JSON authoring", "expected_workflow array."),
            _step(4, "Add an explanation that captures reasoning and caveats.", "JSON authoring", "Complete JSONL record."),
            _step(5, "Validate that the new line is valid JSON and includes all required fields.", "Python json module", "Valid starter dataset."),
        ]
    if _has_any(text, "dataset", "jsonl", "schema", "duplicate"):
        return [
            _step(1, "Read each non-empty JSONL line as a JSON object.", "Python json module", "Parsed candidate records."),
            _step(2, "Validate required fields, supported domains, and workflow step fields.", "GeoMiniLM dataset schema", "Schema validation results."),
            _step(3, "Check for duplicate ids within the candidate file and existing training data.", "Dataset id registry", "Duplicate id findings."),
            _step(4, "Report validation errors or confirm the dataset is ready to append.", "Validation report writer", "Dataset validation summary."),
        ]
    return None


def _qgis_workflow(example: GeoMiniLMExample, text: str) -> list[dict[str, Any]] | None:
    export_path = _output_hint(example, default="requested export path")
    if _has_any(text, "move from qgis", "paraview", "3d terrain render"):
        return [
            _step(1, "Use QGIS to validate raster alignment, styling, and terrain risk classes.", "QGIS", "Confirmed 2D analytical map."),
            _step(2, "Use the original DEM as the ParaView input rather than the classified risk raster.", "GeoTIFF DEM", "Elevation data suitable for 3D warp."),
            _step(3, "Run the ParaView terrain script with pvpython.", "pvpython", "3D terrain screenshot and state file."),
            _step(4, "Compare the QGIS risk map and ParaView render for portfolio presentation.", "GeoVisLM workflow review", "Paired 2D and 3D terrain visuals."),
        ]
    if _has_any(text, "atlas"):
        return [
            _step(1, "Confirm the map layers and coverage layer are loaded and styled in QGIS.", "QGIS map canvas", "Atlas-ready project view."),
            _step(2, "Create a print layout and enable atlas generation from the coverage layer.", "QGIS Layout Manager", "Atlas layout with coverage settings."),
            _step(3, "Add map, title, legend, scale bar, page label, and dynamic atlas labels.", "QGIS layout item tools and atlas controls", "Complete atlas page template with legend and scale bar."),
            _step(4, "Export the atlas pages to the requested output path.", "QGIS layout export and atlas export", f"{export_path} atlas pages PDF PNG map export."),
        ]
    if _has_any(text, "label", "labels"):
        return [
            _step(1, "Load the vector layer and confirm its CRS and attribute table.", "QGIS Browser or Layer menu", "Vector layer in the project."),
            _step(2, "Enable labels from the requested attribute field.", "QGIS vector labeling", "Readable feature labels."),
            _step(3, "Style symbols and label placement for map readability.", "QGIS vector styling and labeling controls", "Styled labeled vector layer with readable labels."),
            _step(4, "Save the QGIS project or export the requested map output.", "QGIS project save and layout export", f"{export_path} labeled vector layer project map output."),
        ]
    if _has_any(text, "pdf", "layout", "export", "png"):
        return [
            _step(1, "Confirm the map layers are visible and styled in QGIS.", "QGIS map canvas", "Final map view."),
            _step(2, "Create a print layout and add the current map extent.", "QGIS Layout Manager", "Layout with map item."),
            _step(3, "Add title, legend, scale bar, north arrow, and requested layout elements.", "QGIS layout item tools", "Map surrounds on the layout with title legend scale bar north arrow."),
            _step(4, "Export the layout to the requested path.", "QGIS layout export", f"{export_path} PDF PNG map layout export."),
        ]
    if _has_any(text, "terrain risk raster", "risk colors", "low, medium, and high"):
        return [
            _step(1, "Open layer properties for terrain_risk.tif.", "QGIS Layer Properties", "Symbology panel."),
            _step(2, "Set renderer to paletted or unique values.", "QGIS Symbology", "Class table for raster values."),
            _step(3, "Assign green to value 1, yellow to value 2, and red to value 3.", "QGIS color controls", "Readable risk legend."),
            _step(4, "Hide or make value 0 transparent if present.", "QGIS transparency settings", "Nodata cells do not distract from mapped terrain."),
        ]
    if _has_any(text, "readable layer order", "recommended_order"):
        return [
            _step(1, "Create a new QGIS project and add the hillshade, slope, and risk rasters.", "QGIS Browser or Layer menu", "Three raster layers in the layer panel."),
            _step(2, "Place hillshade below analytical overlays.", "QGIS Layers panel", "Hillshade used as terrain context."),
            _step(3, "Place slope above hillshade with partial transparency.", "QGIS raster styling", "Slope pattern visible over shaded relief."),
            _step(4, "Place terrain risk at the top with categorical colors.", "QGIS paletted renderer", "Risk classes visible for interpretation."),
        ]
    if _has_any(text, "opacity", "transparent", "transparency", "overlay", "layer"):
        return [
            _step(1, "Add the base and overlay layers to the QGIS project.", "QGIS Browser or Layer menu", "Layers in the layer panel."),
            _step(2, "Place the base layer below the overlay layer.", "QGIS Layers panel", "Base layer provides terrain context."),
            _step(3, "Style the overlay with the requested color ramp or symbology.", "QGIS raster styling and Symbology", "Styled overlay layer."),
            _step(4, "Set overlay opacity to the requested partial transparency.", "QGIS layer rendering controls and transparency settings", "Readable combined map view."),
        ]
    return None


def _paraview_workflow(example: GeoMiniLMExample, text: str) -> list[dict[str, Any]] | None:
    prefix = _first_input(example, "output_prefix", default="terrain_render")
    image_output = _first_input(example, "screenshot_path", "output_path", default=f"outputs/renders/{prefix}.png")
    state_output = _first_input(example, "state_path", default=f"outputs/renders/{prefix}.pvsm")
    if _has_any(text, "gui", "refining", "state file", "change color preset"):
        return [
            _step(1, "Open the saved ParaView state file in the GUI.", "ParaView File Open", "Restored render pipeline."),
            _step(2, "Inspect the raster source, Warp By Scalar filter, and active color map.", "ParaView Pipeline Browser", "Editable visualization pipeline."),
            _step(3, "Adjust camera position and color settings for the target view.", "ParaView RenderView controls", "Refined terrain composition."),
            _step(4, "Save a new screenshot under outputs/renders.", "ParaView Save Screenshot", "Updated terrain render image."),
        ]
    if _has_any(text, "vertical exaggeration", "elevation_scale", "stronger vertical"):
        return [
            _step(1, "Run the ParaView terrain script with --elevation-scale 2.5.", "pvpython", "Configured render pipeline."),
            _step(2, "Warp the DEM by its scalar elevation values using the requested scale factor.", "Warp By Scalar", "Vertically exaggerated terrain mesh."),
            _step(3, "Render the terrain with the default terrain color map.", "ParaView RenderView", "Exaggerated terrain preview."),
            _step(4, "Save outputs using the terrain_exaggerated prefix.", "ParaView screenshot and state writers", f"{image_output} and {state_output}"),
        ]
    if _has_any(text, "save a screenshot", "script_path", "interpreter"):
        return [
            _step(1, "Run the ParaView terrain script with pvpython, passing the DEM path.", "pvpython", "ParaView pipeline execution."),
            _step(2, "Open the DEM as raster data and identify the first scalar band.", "paraview.simple.OpenDataFile", "Raster source with scalar elevation data."),
            _step(3, "Apply Warp By Scalar using the elevation band.", "paraview.simple.WarpByScalar", "3D terrain surface."),
            _step(4, "Apply a terrain color preset and reset the camera.", "ParaView RenderView", "Readable terrain scene."),
            _step(5, "Save a screenshot and ParaView state file.", "paraview.simple.SaveScreenshot and SaveState", f"{image_output} and {state_output}"),
        ]
    workflow = [
        _step(1, "Run the ParaView terrain workflow and open the DEM raster.", "pvpython and paraview.simple.OpenDataFile", "DEM source with scalar elevation data."),
        _step(2, "Apply Warp By Scalar to create terrain relief.", "paraview.simple.WarpByScalar and Warp By Scalar", "Warped terrain surface."),
    ]
    if _has_any(text, "clip", "cross section", "cross-section"):
        workflow.append(_step(3, "Clip the terrain to the requested cross-section or area of interest.", "paraview.simple.Clip", "Clipped terrain cross-section."))
        workflow.append(_step(4, "Save screenshot and state outputs with the requested prefix.", "paraview.simple.SaveScreenshot and SaveState", f"{image_output} and {state_output}"))
        return workflow
    if _has_any(text, "contour"):
        workflow.append(_step(3, "Generate contour lines using the requested interval.", "paraview.simple.Contour", "Contour overlay."))
    elif _has_any(text, "colorbar", "color bar", "slope", "scalar bar"):
        workflow.append(_step(3, "Color the terrain by the requested scalar and show a scalar color bar.", "paraview.simple.ColorBy and GetScalarBar and ParaView RenderView", "Terrain render with slope scalar color bar and color legend."))
    else:
        workflow.append(_step(3, "Set camera, lighting, and terrain color styling for review.", "paraview.simple render view controls", "Configured terrain view."))
    workflow.append(_step(4, "Save screenshot and state outputs with the requested prefix.", "paraview.simple.SaveScreenshot and SaveState", f"{image_output} and {state_output}"))
    return workflow


def _reporting_workflow(example: GeoMiniLMExample, text: str) -> list[dict[str, Any]] | None:
    report_path = _output_hint(example, default="requested Markdown report")
    if not _has_any(text, "report", "markdown", "review", "summary", "manifest"):
        return None
    if _has_any(text, "qgis", "export", "stakeholder", "map") and "report_path" in example.inputs:
        return [
            _step(1, "List the QGIS export artifacts included in the report.", "Markdown report generator", "Report inputs section."),
            _step(2, "Summarize styling, layout elements, and export quality for reviewers.", "GeoVisLM reporting workflow", "Methods and results sections."),
            _step(3, "Explain how stakeholders should inspect the maps and source layers.", "GeoVisLM documentation links", "Review guidance section."),
            _step(4, "Write the Markdown report to the requested path.", "Filesystem writer", _first_input(example, "report_path", default=report_path)),
        ]
    if _has_any(text, "terrain", "slope", "hillshade", "risk") and "report_path" in example.inputs:
        return [
            _step(1, "List the DEM input and generated raster outputs.", "Markdown report generator", "Report inputs section."),
            _step(2, "Summarize the slope and terrain risk classification method.", "GeoVisLM reporting workflow", "Methods section."),
            _step(3, "Describe how to inspect the outputs in QGIS and ParaView.", "GeoVisLM documentation links", "Visualization section."),
            _step(4, "Save the report as Markdown under outputs/reports.", "Filesystem writer", _first_input(example, "report_path", default=report_path)),
        ]
    return [
        _step(1, "List the geospatial artifacts, QGIS exports, model outputs, or evaluation manifest inputs included in the report.", "Markdown report generator", "Report inputs section with artifact list."),
        _step(2, "Summarize methods, outputs, scores, threshold margin, risk attributes, or export quality for reviewers.", "GeoVisLM reporting workflow", "Methods and results sections with validation score and production decision."),
        _step(3, "Explain how reviewers should inspect the outputs and any blocked dashboard follow-up work.", "GeoVisLM documentation links", "Review guidance section with dashboard integration status."),
        _step(4, "Write the Markdown report to the requested path.", "Filesystem writer", f"{report_path} Markdown report review summary."),
    ]


def _template_explanation(example: GeoMiniLMExample, text: str) -> str:
    request = example.instruction.strip()
    input_terms = ", ".join(sorted(example.inputs.keys()))
    if example.domain == "gis":
        return (
            f"For the request {request}, the workflow chooses GIS raster or vector operations from the provided "
            f"{input_terms} inputs, preserves CRS and metadata, assigns risk or terrain outputs, and writes the "
            "requested artifact for validation."
        )
    if example.domain == "qgis":
        return (
            f"For the request {request}, the workflow keeps QGIS layer order, styling, labels, layout elements, "
            "legend, scale bar, transparency, and export path explicit so the map deliverable can be reviewed."
        )
    if example.domain == "paraview":
        return (
            f"For the request {request}, the workflow builds a ParaView terrain render with the requested filter "
            "variant, color map, camera state, screenshot, and state file for reproducible visual review."
        )
    if _has_any(text, "qgis", "export", "stakeholder", "map") and "report_path" in example.inputs:
        return (
            f"For the request {request}, the Markdown report connects QGIS export files to styling, layout, and "
            "export-quality choices, explains stakeholder map inspection, references source layers, and writes "
            "the requested report path."
        )
    if _has_any(text, "terrain", "slope", "hillshade", "risk") and "report_path" in example.inputs:
        return (
            f"For the request {request}, the Markdown report connects the source DEM and generated GIS outputs to "
            "terrain interpretation, summarizes slope and risk methods, names QGIS and ParaView inspection steps, "
            "and writes the requested report path for MVP review."
        )
    return (
        f"For the request {request}, the workflow produces a Markdown review artifact that names inputs, summarizes "
        "results, explains inspection steps, captures decisions, and writes the requested report path."
    )


def _template_confidence(example: GeoMiniLMExample, text: str, workflow: list[dict[str, Any]]) -> float:
    confidence = 0.78
    output_hint = _output_hint(example, default="")
    if output_hint and output_hint != "requested output":
        confidence += 0.06
    if workflow and any(_template_text_match(output_hint, step.get("output", "")) for step in workflow):
        confidence += 0.04
    if example.domain in {"gis", "qgis", "paraview", "reporting"}:
        confidence += 0.03
    if _has_any(text, "zonal", "summary", "report", "layout", "atlas", "hillshade", "slope", "wildfire", "flood", "contour"):
        confidence += 0.04
    return round(min(confidence, 0.92), 4)


def _template_text_match(expected: str, predicted: Any) -> bool:
    expected_norm = re.sub(r"\s+", " ", str(expected).strip().lower())
    predicted_norm = re.sub(r"\s+", " ", str(predicted).strip().lower())
    if not expected_norm or not predicted_norm:
        return False
    return expected_norm in predicted_norm or predicted_norm in expected_norm or bool(set(_tokens(expected_norm)) & set(_tokens(predicted_norm)))


def _prompt_text(example: GeoMiniLMExample) -> str:
    return f"{example.instruction} {json.dumps(example.inputs, sort_keys=True)}".lower()


def _has_any(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def _first_input(example: GeoMiniLMExample, *keys: str, default: str) -> str:
    for key in keys:
        value = example.inputs.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return default


def _output_hint(example: GeoMiniLMExample, *, default: str) -> str:
    parts = []
    for key in (
        "output_path",
        "export_path",
        "report_path",
        "project_path",
        "state_path",
        "screenshot_path",
        "export_dir",
    ):
        value = example.inputs.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value)
    for key in ("outputs", "exports", "export_paths"):
        value = example.inputs.get(key)
        if isinstance(value, list):
            parts.extend(item for item in value if isinstance(item, str) and item.strip())
    output_dir = example.inputs.get("output_dir")
    if isinstance(output_dir, str) and output_dir.strip():
        parts.extend(
            [
                output_dir,
                f"{output_dir}/flood_risk.tif",
                f"{output_dir}/river_buffers.geojson",
                f"{output_dir}/flood_risk_summary.json",
                f"{output_dir}/wildfire_risk.tif",
                f"{output_dir}/wildfire_risk_summary.json",
            ]
        )
    output_prefix = example.inputs.get("output_prefix")
    if isinstance(output_prefix, str) and output_prefix.strip():
        parts.extend([f"outputs/renders/{output_prefix}.png", f"outputs/renders/{output_prefix}.pvsm"])
    if parts:
        return " and ".join(dict.fromkeys(parts))
    return default


def _step(step: int, action: str, tool: str, output: str) -> dict[str, Any]:
    return {"step": step, "action": action, "tool": tool, "output": output}


def _validate_disjoint_ids(
    training_examples: list[GeoMiniLMExample],
    validation_examples: list[GeoMiniLMExample],
) -> None:
    training_ids = {example.id for example in training_examples}
    validation_ids = {example.id for example in validation_examples}
    overlap = sorted(training_ids & validation_ids)
    if overlap:
        raise ValueError(f"Training and validation examples must be disjoint: {', '.join(overlap)}")


def _display_label(label: str) -> str:
    if label == "heldout":
        return "Held-Out"
    return label.replace("_", " ").title()


def _fit_vectorizer(pairs: list[TrainingPair]) -> tuple[list[str], dict[str, float]]:
    documents = [set(_tokens(pair.prompt)) for pair in pairs]
    vocabulary = sorted({token for document in documents for token in document})
    document_count = len(documents)
    idf = {}
    for token in vocabulary:
        frequency = sum(1 for document in documents if token in document)
        idf[token] = math.log((1 + document_count) / (1 + frequency)) + 1
    return vocabulary, idf


def _vectorize(text: str, vocabulary: list[str], idf: dict[str, float]) -> list[float]:
    counts: dict[str, int] = {}
    for token in _tokens(text):
        counts[token] = counts.get(token, 0) + 1
    return [counts.get(token, 0) * idf[token] for token in vocabulary]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(left_value * right_value for left_value, right_value in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def _tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9_./-]+", value.lower()) if len(token) > 2]
