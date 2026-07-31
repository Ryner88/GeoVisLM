from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from geovis_lm.eval.workflow_eval import EXPECTED_WORKFLOW_FIELD, load_jsonl


@dataclass(frozen=True)
class GeoMiniLMExample:
    id: str
    domain: str
    instruction: str
    inputs: dict[str, Any]
    expected_workflow: list[dict[str, Any]]
    explanation: str

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> GeoMiniLMExample:
        return cls(
            id=record["id"],
            domain=record["domain"],
            instruction=record["instruction"],
            inputs=dict(record["inputs"]),
            expected_workflow=list(record[EXPECTED_WORKFLOW_FIELD]),
            explanation=record["explanation"],
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "domain": self.domain,
            "instruction": self.instruction,
            "inputs": self.inputs,
            EXPECTED_WORKFLOW_FIELD: self.expected_workflow,
            "explanation": self.explanation,
        }

    def to_training_pair(self) -> TrainingPair:
        target = {
            EXPECTED_WORKFLOW_FIELD: self.expected_workflow,
            "explanation": self.explanation,
        }
        return TrainingPair(
            id=self.id,
            domain=self.domain,
            prompt=build_prompt(self),
            target=json.dumps(target, ensure_ascii=False, sort_keys=True),
        )


@dataclass(frozen=True)
class TrainingPair:
    id: str
    domain: str
    prompt: str
    target: str

    def to_record(self) -> dict[str, str]:
        return {
            "id": self.id,
            "domain": self.domain,
            "prompt": self.prompt,
            "target": self.target,
        }


@dataclass(frozen=True)
class DatasetSummary:
    total_records: int
    domain_counts: dict[str, int]
    min_steps: int
    max_steps: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_records": self.total_records,
            "domain_counts": dict(sorted(self.domain_counts.items())),
            "min_steps": self.min_steps,
            "max_steps": self.max_steps,
        }


def load_geominilm_dataset(path: Path) -> list[GeoMiniLMExample]:
    records = load_jsonl(path, prediction=False)
    return [GeoMiniLMExample.from_record(record) for record in records]


def build_prompt(example: GeoMiniLMExample) -> str:
    inputs = json.dumps(example.inputs, ensure_ascii=False, sort_keys=True)
    return "\n".join(
        [
            "Generate a structured GeoVisLM workflow.",
            f"Domain: {example.domain}",
            f"Instruction: {example.instruction}",
            f"Inputs: {inputs}",
            "Return JSON with expected_workflow and explanation.",
        ]
    )


def preprocess_examples(examples: list[GeoMiniLMExample]) -> list[TrainingPair]:
    return [example.to_training_pair() for example in examples]


def summarize_examples(examples: list[GeoMiniLMExample]) -> DatasetSummary:
    domain_counts: dict[str, int] = {}
    step_counts = [len(example.expected_workflow) for example in examples]
    for example in examples:
        domain_counts[example.domain] = domain_counts.get(example.domain, 0) + 1
    return DatasetSummary(
        total_records=len(examples),
        domain_counts=domain_counts,
        min_steps=min(step_counts) if step_counts else 0,
        max_steps=max(step_counts) if step_counts else 0,
    )


def build_baseline_predictions(examples: list[GeoMiniLMExample]) -> list[dict[str, Any]]:
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


def write_preprocessed_jsonl(pairs: list[TrainingPair], path: Path) -> Path:
    return write_jsonl_records([pair.to_record() for pair in pairs], path)


def write_jsonl_records(records: list[dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path
