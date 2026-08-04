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
    build_production_decision,
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
        target = json.loads(nearest["target"])
        return {
            "id": example.id,
            "domain": example.domain,
            "instruction": example.instruction,
            "inputs": example.inputs,
            "predicted_workflow": target["expected_workflow"],
            "explanation": target["explanation"],
            "source_checkpoint_record_id": nearest["id"],
        }

    def predict_many(self, examples: list[GeoMiniLMExample]) -> list[dict[str, Any]]:
        return [self.predict(example) for example in examples]

    def metadata(self, examples: list[GeoMiniLMExample]) -> dict[str, Any]:
        return {
            "algorithm": "tfidf_nearest_neighbor",
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
    heldout_report = evaluate_records(expected_records, predictions)
    baseline_report = evaluate_records(expected_records, _oracle_baseline_predictions(examples))
    comparison = compare_reports(heldout_report, baseline_report, trained_label="heldout")
    comparison["fold_count"] = len(folds)
    comparison["failed_examples"] = [
        {
            "id": record.record_id,
            "score": round(record.score, 4),
            "findings": record.findings,
            "source_checkpoint_record_id": _prediction_source(predictions, record.record_id),
        }
        for record in heldout_report.records
        if not record.passed or record.findings
    ]
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
    trained_report = evaluate_records(expected_records, predictions, pass_threshold=pass_threshold)

    honest_baseline_predictions = build_domain_exemplar_baseline_predictions(training_examples, validation_examples)
    honest_baseline_report = evaluate_records(expected_records, honest_baseline_predictions, pass_threshold=pass_threshold)
    oracle_sanity_report = evaluate_records(
        expected_records,
        _oracle_baseline_predictions(validation_examples),
        pass_threshold=pass_threshold,
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
    comparison["production_decision"] = build_production_decision(comparison)
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
    finding_examples = []
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
            finding_examples.append(item)
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
        "finding_examples": finding_examples,
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
        }
        for example in examples
    ]


def _prediction_source(predictions: list[dict[str, Any]], record_id: str) -> str | None:
    for prediction in predictions:
        if prediction["id"] == record_id:
            return prediction.get("source_checkpoint_record_id")
    return None


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
