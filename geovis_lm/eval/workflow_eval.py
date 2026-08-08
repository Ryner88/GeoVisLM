from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import re
from typing import Any


REQUIRED_RECORD_FIELDS = {"id", "domain", "instruction", "inputs", "explanation"}
EXPECTED_WORKFLOW_FIELD = "expected_workflow"
PREDICTED_WORKFLOW_FIELDS = ("predicted_workflow", "expected_workflow")
REQUIRED_STEP_FIELDS = {"step", "action", "tool", "output"}
SUPPORTED_DOMAINS = {"gis", "qgis", "paraview", "reporting"}
DEFAULT_PASS_THRESHOLD = 0.75


class EvaluationInputError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class RecordScore:
    record_id: str
    domain: str | None
    score: float
    passed: bool
    components: dict[str, float]
    confidence: float | None = None
    findings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvaluationReport:
    total_records: int
    evaluated_records: int
    missing_predictions: int
    summary_score: float
    passed: bool
    pass_threshold: float
    records: list[RecordScore]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "evaluated_records": self.evaluated_records,
            "missing_predictions": self.missing_predictions,
            "summary_score": round(self.summary_score, 4),
            "passed": self.passed,
            "pass_threshold": self.pass_threshold,
            "records": [
                {
                    "id": record.record_id,
                    "domain": record.domain,
                    "score": round(record.score, 4),
                    "passed": record.passed,
                    "components": {key: round(value, 4) for key, value in record.components.items()},
                    "confidence": round(record.confidence, 4) if record.confidence is not None else None,
                    "findings": record.findings,
                }
                for record in self.records
            ],
        }


def load_jsonl(path: Path, *, prediction: bool = False) -> list[dict[str, Any]]:
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    if not path.exists():
        raise EvaluationInputError([f"{path}: file does not exist"])

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}:{line_number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(record, dict):
            errors.append(f"{path}:{line_number}: record must be a JSON object")
            continue

        record_errors = validate_record(record, prediction=prediction)
        errors.extend(f"{path}:{line_number}: {error}" for error in record_errors)

        record_id = record.get("id")
        if isinstance(record_id, str):
            if record_id in seen_ids:
                errors.append(f"{path}:{line_number}: duplicate id: {record_id}")
            seen_ids.add(record_id)
        records.append(record)

    if errors:
        raise EvaluationInputError(errors)
    return records


def validate_record(record: dict[str, Any], *, prediction: bool = False) -> list[str]:
    errors: list[str] = []
    missing = sorted(field for field in REQUIRED_RECORD_FIELDS if field not in record)
    if missing:
        errors.append(f"missing required fields: {', '.join(missing)}")

    workflow_key = _workflow_key(record, prediction=prediction)
    if workflow_key is None:
        accepted = ", ".join(PREDICTED_WORKFLOW_FIELDS) if prediction else EXPECTED_WORKFLOW_FIELD
        errors.append(f"missing workflow field: {accepted}")
    else:
        errors.extend(_validate_workflow(record.get(workflow_key), workflow_key))

    if "id" in record and not _nonempty_string(record["id"]):
        errors.append("id must be a non-empty string")
    if record.get("domain") not in SUPPORTED_DOMAINS:
        errors.append(f"domain must be one of: {', '.join(sorted(SUPPORTED_DOMAINS))}")
    if "instruction" in record and not _nonempty_string(record["instruction"]):
        errors.append("instruction must be a non-empty string")
    if "inputs" in record and not isinstance(record["inputs"], dict):
        errors.append("inputs must be an object")
    if "explanation" in record and not _nonempty_string(record["explanation"]):
        errors.append("explanation must be a non-empty string")
    return errors


def evaluate_files(
    expected_path: Path,
    predictions_path: Path,
    *,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
) -> EvaluationReport:
    expected = load_jsonl(expected_path, prediction=False)
    predictions = load_jsonl(predictions_path, prediction=True)
    return evaluate_records(expected, predictions, pass_threshold=pass_threshold)


def evaluate_records(
    expected_records: list[dict[str, Any]],
    prediction_records: list[dict[str, Any]],
    *,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
    score_context_fields: bool = True,
) -> EvaluationReport:
    _validate_pass_threshold(pass_threshold)
    predictions_by_id = {record["id"]: record for record in prediction_records}
    scores: list[RecordScore] = []

    for expected in expected_records:
        prediction = predictions_by_id.get(expected["id"])
        if prediction is None:
            scores.append(
                RecordScore(
                    record_id=expected["id"],
                    domain=expected.get("domain"),
                    score=0.0,
                    passed=False,
                    components=_empty_components(),
                    findings=["missing_prediction"],
                )
            )
            continue
        scores.append(score_record(expected, prediction, pass_threshold=pass_threshold, score_context_fields=score_context_fields))

    summary_score = sum(record.score for record in scores) / len(scores) if scores else 0.0
    return EvaluationReport(
        total_records=len(expected_records),
        evaluated_records=sum(1 for record in scores if "missing_prediction" not in record.findings),
        missing_predictions=sum(1 for record in scores if "missing_prediction" in record.findings),
        summary_score=summary_score,
        passed=summary_score >= pass_threshold and all(record.passed for record in scores),
        pass_threshold=pass_threshold,
        records=scores,
    )


def score_record(
    expected: dict[str, Any],
    prediction: dict[str, Any],
    *,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
    score_context_fields: bool = True,
) -> RecordScore:
    expected_steps = expected[EXPECTED_WORKFLOW_FIELD]
    prediction_steps = prediction[_workflow_key(prediction, prediction=True)]

    components = {
        "ordered_steps": _ordered_step_score(expected_steps, prediction_steps),
        "tool_choice": _step_field_score(expected_steps, prediction_steps, "tool"),
        "output_paths": _step_field_score(expected_steps, prediction_steps, "output"),
        "explanation_quality": _explanation_score(expected.get("explanation", ""), prediction.get("explanation", "")),
    }
    if score_context_fields:
        components = {
            "instruction_relevance": _text_overlap(expected["instruction"], prediction.get("instruction", "")),
            "required_inputs": _input_score(expected.get("inputs", {}), prediction.get("inputs", {})),
            **components,
        }
        weights = {
            "instruction_relevance": 0.10,
            "required_inputs": 0.20,
            "ordered_steps": 0.30,
            "tool_choice": 0.15,
            "output_paths": 0.15,
            "explanation_quality": 0.10,
        }
    else:
        weights = {
            "ordered_steps": 0.50,
            "tool_choice": 0.25,
            "output_paths": 0.20,
            "explanation_quality": 0.05,
        }
    score = sum(components[name] * weight for name, weight in weights.items())
    findings = _record_findings(expected, prediction, components)
    confidence = _prediction_confidence(prediction)
    return RecordScore(
        record_id=expected["id"],
        domain=expected.get("domain"),
        score=score,
        passed=score >= pass_threshold and not any(finding.startswith("invalid_") for finding in findings),
        components=components,
        confidence=confidence,
        findings=findings,
    )


def write_json_report(report: EvaluationReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_markdown_report(report: EvaluationReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# GeoMiniLM Workflow Evaluation",
        "",
        f"- Result: {'PASS' if report.passed else 'FAIL'}",
        f"- Summary score: {report.summary_score:.3f}",
        f"- Pass threshold: {report.pass_threshold:.3f}",
        f"- Expected records: {report.total_records}",
        f"- Evaluated records: {report.evaluated_records}",
        f"- Missing predictions: {report.missing_predictions}",
        "",
        "| ID | Domain | Score | Result | Findings |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for record in report.records:
        findings = ", ".join(record.findings) if record.findings else "none"
        lines.append(
            f"| {record.record_id} | {record.domain or ''} | {record.score:.3f} | "
            f"{'PASS' if record.passed else 'FAIL'} | {findings} |"
        )
    lines.extend(
        [
            "",
            "## Rubric",
            "",
            "- Instruction relevance: 10%",
            "- Required input coverage: 20%",
            "- Ordered workflow steps: 30%",
            "- Tool choice: 15%",
            "- Output paths or states: 15%",
            "- Explanation quality: 10%",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _workflow_key(record: dict[str, Any], *, prediction: bool) -> str | None:
    fields = PREDICTED_WORKFLOW_FIELDS if prediction else (EXPECTED_WORKFLOW_FIELD,)
    return next((field for field in fields if field in record), None)


def _validate_workflow(value: Any, field_name: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, list) or not value:
        return [f"{field_name} must be a non-empty array"]
    expected_step_number = 1
    for index, step in enumerate(value, start=1):
        if not isinstance(step, dict):
            errors.append(f"{field_name}[{index}] must be an object")
            continue
        missing = sorted(REQUIRED_STEP_FIELDS - step.keys())
        if missing:
            errors.append(f"{field_name}[{index}] missing fields: {', '.join(missing)}")
        if step.get("step") != expected_step_number:
            errors.append(f"{field_name}[{index}] step must be {expected_step_number}")
        for text_field in ("action", "tool", "output"):
            if text_field in step and not _nonempty_string(step[text_field]):
                errors.append(f"{field_name}[{index}].{text_field} must be a non-empty string")
        expected_step_number += 1
    return errors


def _record_findings(
    expected: dict[str, Any],
    prediction: dict[str, Any],
    components: dict[str, float],
) -> list[str]:
    findings: list[str] = []
    if expected.get("domain") != prediction.get("domain"):
        findings.append("domain_mismatch")
    for component, score in components.items():
        if score < 1.0:
            findings.append(f"{component}_partial")
    expected_steps = expected[EXPECTED_WORKFLOW_FIELD]
    prediction_steps = prediction[_workflow_key(prediction, prediction=True)]
    if len(expected_steps) != len(prediction_steps):
        findings.append("workflow_step_count_mismatch")
    tool_score = _step_field_score(expected_steps, prediction_steps, "tool")
    if tool_score == 0.0:
        findings.append("invalid_tools")
    elif tool_score < 1.0:
        findings.append("tool_choice_mismatch")
    if _step_field_score(expected_steps, prediction_steps, "output") < 1.0:
        findings.append("output_path_mismatch")
    return findings


def _validate_pass_threshold(pass_threshold: float) -> None:
    if not isinstance(pass_threshold, (int, float)) or not math.isfinite(pass_threshold):
        raise EvaluationInputError(["pass threshold must be a finite number from 0 through 1"])
    if pass_threshold < 0.0 or pass_threshold > 1.0:
        raise EvaluationInputError(["pass threshold must be a finite number from 0 through 1"])


def _input_score(expected_inputs: dict[str, Any], predicted_inputs: Any) -> float:
    if not expected_inputs:
        return 1.0
    if not isinstance(predicted_inputs, dict):
        return 0.0
    matches = sum(1 for key, value in expected_inputs.items() if predicted_inputs.get(key) == value)
    return matches / len(expected_inputs)


def _ordered_step_score(expected_steps: list[dict[str, Any]], prediction_steps: list[dict[str, Any]]) -> float:
    if not expected_steps or not prediction_steps:
        return 0.0
    max_steps = max(len(expected_steps), len(prediction_steps))
    matches = 0.0
    for expected, predicted in zip(expected_steps, prediction_steps):
        step_match = 1.0 if expected.get("step") == predicted.get("step") else 0.0
        action_match = _text_overlap(expected.get("action", ""), predicted.get("action", ""))
        matches += (step_match + action_match) / 2
    return matches / max_steps


def _step_field_score(
    expected_steps: list[dict[str, Any]],
    prediction_steps: list[dict[str, Any]],
    field_name: str,
) -> float:
    if not expected_steps:
        return 1.0
    if not prediction_steps:
        return 0.0
    matches = 0.0
    for expected, predicted in zip(expected_steps, prediction_steps):
        matches += _field_match(expected.get(field_name, ""), predicted.get(field_name, ""))
    return matches / max(len(expected_steps), len(prediction_steps))


def _field_match(expected: str, predicted: str) -> float:
    expected_norm = _normalize(expected)
    predicted_norm = _normalize(predicted)
    if not expected_norm or not predicted_norm:
        return 0.0
    if expected_norm == predicted_norm:
        return 1.0
    if expected_norm in predicted_norm or predicted_norm in expected_norm:
        return 0.75
    return _text_overlap(expected_norm, predicted_norm)


def _explanation_score(expected: str, predicted: str) -> float:
    if len(_tokens(predicted)) < 8:
        return 0.0
    return _text_overlap(expected, predicted)


def _text_overlap(expected: str, predicted: str) -> float:
    expected_tokens = set(_tokens(expected))
    predicted_tokens = set(_tokens(predicted))
    if not expected_tokens or not predicted_tokens:
        return 0.0
    return len(expected_tokens & predicted_tokens) / len(expected_tokens)


def _tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9_./-]+", value.lower()) if len(token) > 2]


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _empty_components() -> dict[str, float]:
    return {
        "instruction_relevance": 0.0,
        "required_inputs": 0.0,
        "ordered_steps": 0.0,
        "tool_choice": 0.0,
        "output_paths": 0.0,
        "explanation_quality": 0.0,
    }


def _prediction_confidence(prediction: dict[str, Any]) -> float | None:
    confidence = prediction.get("confidence")
    if not isinstance(confidence, (int, float)) or not math.isfinite(confidence):
        return None
    return max(0.0, min(1.0, float(confidence)))
