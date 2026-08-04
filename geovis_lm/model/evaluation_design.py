from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from geovis_lm.eval.workflow_eval import EvaluationInputError, EvaluationReport
from geovis_lm.model.dataset import GeoMiniLMExample, load_geominilm_dataset


MANIFEST_VERSION = 1
DEFAULT_PRIMARY_METRIC = "trained_validation_score"
DEFAULT_PRODUCTION_PASS_THRESHOLD = 0.75
DEFAULT_NEAR_DUPLICATE_THRESHOLD = 0.85
DEFAULT_MINIMUM_VALIDATION_RECORDS = 12
DEFAULT_MINIMUM_THRESHOLD_MARGIN = 0.01


@dataclass(frozen=True)
class SplitSpec:
    name: str
    role: str
    path: Path


@dataclass(frozen=True)
class DuplicateIssue:
    kind: str
    left_split: str
    left_id: str
    right_split: str
    right_id: str
    similarity: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "left_split": self.left_split,
            "left_id": self.left_id,
            "right_split": self.right_split,
            "right_id": self.right_id,
            "similarity": round(self.similarity, 4),
        }


@dataclass(frozen=True)
class SplitValidationResult:
    split_manifest: dict[str, Any]
    issues: list[DuplicateIssue]
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "split_manifest": self.split_manifest,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def build_evaluation_manifest(
    split_specs: list[SplitSpec],
    *,
    taxonomy_path: Path,
    primary_metric: str = DEFAULT_PRIMARY_METRIC,
    pass_threshold: float = DEFAULT_PRODUCTION_PASS_THRESHOLD,
    near_duplicate_threshold: float = DEFAULT_NEAR_DUPLICATE_THRESHOLD,
    minimum_validation_records: int = DEFAULT_MINIMUM_VALIDATION_RECORDS,
    minimum_threshold_margin: float = DEFAULT_MINIMUM_THRESHOLD_MARGIN,
    created_at: str | None = None,
) -> dict[str, Any]:
    splits = []
    split_checksum_inputs = []
    for spec in split_specs:
        examples = load_geominilm_dataset(spec.path)
        content_checksum = file_sha256(spec.path)
        record_ids = [example.id for example in examples]
        domain_counts: dict[str, int] = {}
        for example in examples:
            domain_counts[example.domain] = domain_counts.get(example.domain, 0) + 1
        split_entry = {
            "name": spec.name,
            "role": spec.role,
            "path": str(spec.path),
            "sha256": content_checksum,
            "record_count": len(examples),
            "record_ids": record_ids,
            "domain_counts": dict(sorted(domain_counts.items())),
        }
        splits.append(split_entry)
        split_checksum_inputs.append(
            {
                "name": spec.name,
                "role": spec.role,
                "path": str(spec.path),
                "sha256": content_checksum,
                "record_ids": record_ids,
            }
        )

    taxonomy_checksum = file_sha256(taxonomy_path)
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "created_at": created_at or datetime.now(UTC).isoformat(),
        "status": "frozen",
        "primary_metric": primary_metric,
        "pass_threshold": pass_threshold,
        "minimum_validation_records": minimum_validation_records,
        "minimum_threshold_margin": minimum_threshold_margin,
        "dashboard_integration_rule": (
            "blocked unless trained_validation_score is greater than honest_baseline_score "
            "on the frozen expanded validation set and clears the locked threshold margin"
        ),
        "near_duplicate_threshold": near_duplicate_threshold,
        "taxonomy": {
            "path": str(taxonomy_path),
            "sha256": taxonomy_checksum,
        },
        "splits": splits,
        "split_checksum": sha256_json(split_checksum_inputs),
    }
    manifest["manifest_checksum"] = sha256_json({key: value for key, value in manifest.items() if key != "manifest_checksum"})
    return manifest


def validate_evaluation_splits(
    split_specs: list[SplitSpec],
    *,
    taxonomy_path: Path,
    near_duplicate_threshold: float = DEFAULT_NEAR_DUPLICATE_THRESHOLD,
) -> SplitValidationResult:
    examples_by_split = [(spec, load_geominilm_dataset(spec.path)) for spec in split_specs]
    issues: list[DuplicateIssue] = []
    flattened: list[tuple[str, str, GeoMiniLMExample]] = []
    seen_ids: dict[str, str] = {}
    seen_fingerprints: dict[str, tuple[str, str]] = {}

    for spec, examples in examples_by_split:
        for example in examples:
            if example.id in seen_ids:
                issues.append(DuplicateIssue("duplicate_id", seen_ids[example.id], example.id, spec.name, example.id, 1.0))
            else:
                seen_ids[example.id] = spec.name

            fingerprint = canonical_example_fingerprint(example)
            if fingerprint in seen_fingerprints:
                left_split, left_id = seen_fingerprints[fingerprint]
                issues.append(DuplicateIssue("exact_duplicate", left_split, left_id, spec.name, example.id, 1.0))
            else:
                seen_fingerprints[fingerprint] = (spec.name, example.id)
            flattened.append((spec.name, spec.role, example))

    for left_index, (left_split, left_role, left_example) in enumerate(flattened):
        left_tokens = duplicate_tokens(left_example)
        for right_split, right_role, right_example in flattened[left_index + 1 :]:
            if left_role == right_role:
                continue
            similarity = token_overlap_similarity(left_tokens, duplicate_tokens(right_example))
            if similarity >= near_duplicate_threshold:
                issues.append(
                    DuplicateIssue("near_duplicate_or_leakage", left_split, left_example.id, right_split, right_example.id, similarity)
                )

    manifest = build_evaluation_manifest(
        split_specs,
        taxonomy_path=taxonomy_path,
        near_duplicate_threshold=near_duplicate_threshold,
    )
    return SplitValidationResult(
        split_manifest=manifest,
        issues=issues,
        passed=not issues,
    )


def validate_manifest_file(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = build_evaluation_manifest(
        [
            SplitSpec(split["name"], split["role"], Path(split["path"]))
            for split in manifest["splits"]
        ],
        taxonomy_path=Path(manifest["taxonomy"]["path"]),
        primary_metric=manifest["primary_metric"],
        pass_threshold=manifest["pass_threshold"],
        near_duplicate_threshold=manifest["near_duplicate_threshold"],
        minimum_validation_records=manifest.get("minimum_validation_records", DEFAULT_MINIMUM_VALIDATION_RECORDS),
        minimum_threshold_margin=manifest.get("minimum_threshold_margin", DEFAULT_MINIMUM_THRESHOLD_MARGIN),
        created_at=manifest["created_at"],
    )
    mismatches = []
    if manifest.get("split_checksum") != expected["split_checksum"]:
        mismatches.append("split_checksum")
    if manifest.get("manifest_checksum") != expected["manifest_checksum"]:
        mismatches.append("manifest_checksum")
    for actual, regenerated in zip(manifest["splits"], expected["splits"]):
        if actual.get("sha256") != regenerated["sha256"]:
            mismatches.append(f"{actual['name']}.sha256")
        if actual.get("record_ids") != regenerated["record_ids"]:
            mismatches.append(f"{actual['name']}.record_ids")
    if manifest["taxonomy"].get("sha256") != expected["taxonomy"]["sha256"]:
        mismatches.append("taxonomy.sha256")
    return {
        "passed": not mismatches,
        "mismatches": mismatches,
        "expected": expected,
    }


def build_calibration_report(
    report: EvaluationReport,
    *,
    bins: int = 5,
) -> dict[str, Any]:
    if bins < 1:
        raise EvaluationInputError(["calibration bins must be at least 1"])
    records = []
    for record in report.records:
        confidence = max(0.0, min(1.0, record.score))
        records.append(
            {
                "id": record.record_id,
                "confidence": confidence,
                "accuracy": 1.0 if record.passed else 0.0,
                "score": record.score,
            }
        )
    reliability_bins = []
    expected_calibration_error = 0.0
    maximum_calibration_error = 0.0
    total = len(records)
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        if index == bins - 1:
            bucket = [record for record in records if lower <= record["confidence"] <= upper]
        else:
            bucket = [record for record in records if lower <= record["confidence"] < upper]
        avg_confidence = sum(record["confidence"] for record in bucket) / len(bucket) if bucket else 0.0
        accuracy = sum(record["accuracy"] for record in bucket) / len(bucket) if bucket else 0.0
        gap = abs(avg_confidence - accuracy)
        expected_calibration_error += (len(bucket) / total) * gap if total else 0.0
        maximum_calibration_error = max(maximum_calibration_error, gap)
        reliability_bins.append(
            {
                "bin": index + 1,
                "lower": round(lower, 4),
                "upper": round(upper, 4),
                "count": len(bucket),
                "avg_confidence": round(avg_confidence, 4),
                "accuracy": round(accuracy, 4),
                "gap": round(gap, 4),
            }
        )
    return {
        "method": "workflow_score_as_confidence_proxy",
        "record_count": total,
        "bins": reliability_bins,
        "reliability_bins": reliability_bins,
        "expected_calibration_error": round(expected_calibration_error, 4),
        "maximum_calibration_error": round(maximum_calibration_error, 4),
    }


def build_production_decision(comparison: dict[str, Any]) -> dict[str, Any]:
    metric = comparison["trained_validation_score"]
    baseline = comparison["honest_baseline_score"]
    minimum_validation_records = comparison["minimum_validation_records"]
    minimum_threshold_margin = comparison["minimum_threshold_margin"]
    required_metric_value = comparison["pass_threshold"] + minimum_threshold_margin
    passed_threshold = metric >= required_metric_value
    beats_honest_baseline = metric > baseline
    has_expanded_validation_set = comparison["validation_record_count"] >= minimum_validation_records
    return {
        "primary_metric": comparison["primary_metric"],
        "pass_threshold": comparison["pass_threshold"],
        "minimum_threshold_margin": minimum_threshold_margin,
        "required_metric_value": round(required_metric_value, 4),
        "primary_metric_value": metric,
        "honest_baseline_score": baseline,
        "beats_honest_baseline": beats_honest_baseline,
        "passes_threshold": passed_threshold,
        "validation_record_count": comparison["validation_record_count"],
        "minimum_validation_records": minimum_validation_records,
        "has_expanded_validation_set": has_expanded_validation_set,
        "dashboard_integration_allowed": beats_honest_baseline and passed_threshold and has_expanded_validation_set,
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_example_fingerprint(example: GeoMiniLMExample) -> str:
    payload = {
        "domain": example.domain,
        "instruction": normalize_duplicate_text(example.instruction),
        "inputs": example.inputs,
        "expected_workflow": example.expected_workflow,
        "explanation": normalize_duplicate_text(example.explanation),
    }
    return sha256_json(payload)


def duplicate_tokens(example: GeoMiniLMExample) -> set[str]:
    text = " ".join(
        [
            example.domain,
            example.instruction,
            json.dumps(example.inputs, sort_keys=True),
            json.dumps(example.expected_workflow, sort_keys=True),
            example.explanation,
        ]
    )
    return set(re.findall(r"[a-z0-9_./-]+", text.lower()))


def normalize_duplicate_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9_./-]+", value.lower()))


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def containment_similarity(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def token_overlap_similarity(left: set[str], right: set[str]) -> float:
    return max(jaccard_similarity(left, right), containment_similarity(left, right))
