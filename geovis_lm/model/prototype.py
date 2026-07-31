from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from typing import Any

from geovis_lm.eval.workflow_eval import EvaluationReport
from geovis_lm.model.dataset import GeoMiniLMExample, TrainingPair, build_prompt, preprocess_examples


CHECKPOINT_VERSION = 1


@dataclass(frozen=True)
class TrainingResult:
    checkpoint_path: Path
    metadata: dict[str, Any]


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


def compare_reports(trained: EvaluationReport, baseline: EvaluationReport) -> dict[str, Any]:
    trained_records = {record.record_id: record for record in trained.records}
    baseline_records = {record.record_id: record for record in baseline.records}
    record_deltas = []
    for record_id in sorted(trained_records):
        trained_score = trained_records[record_id].score
        baseline_score = baseline_records[record_id].score
        record_deltas.append(
            {
                "id": record_id,
                "trained_score": round(trained_score, 4),
                "baseline_score": round(baseline_score, 4),
                "delta": round(trained_score - baseline_score, 4),
            }
        )
    return {
        "trained_summary_score": round(trained.summary_score, 4),
        "baseline_summary_score": round(baseline.summary_score, 4),
        "summary_delta": round(trained.summary_score - baseline.summary_score, 4),
        "trained_passed": trained.passed,
        "baseline_passed": baseline.passed,
        "record_deltas": record_deltas,
    }


def write_comparison_report(comparison: dict[str, Any], json_path: Path, markdown_path: Path) -> tuple[Path, Path]:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# GeoMiniLM Baseline Comparison",
        "",
        f"- Trained summary score: {comparison['trained_summary_score']:.3f}",
        f"- Dry-run baseline score: {comparison['baseline_summary_score']:.3f}",
        f"- Summary delta: {comparison['summary_delta']:.3f}",
        f"- Trained result: {'PASS' if comparison['trained_passed'] else 'FAIL'}",
        f"- Baseline result: {'PASS' if comparison['baseline_passed'] else 'FAIL'}",
        "",
        "| ID | Trained | Baseline | Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for record in comparison["record_deltas"]:
        lines.append(
            f"| {record['id']} | {record['trained_score']:.3f} | "
            f"{record['baseline_score']:.3f} | {record['delta']:.3f} |"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


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
