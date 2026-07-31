from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from geovis_lm.eval.workflow_eval import (  # noqa: E402
    EvaluationInputError,
    evaluate_records,
    write_json_report,
    write_markdown_report,
)
from geovis_lm.model.dataset import (  # noqa: E402
    build_baseline_predictions,
    load_geominilm_dataset,
    preprocess_examples,
    summarize_examples,
    write_jsonl_records,
    write_preprocessed_jsonl,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare and dry-run the GeoMiniLM prototype training flow.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/geominilm/starter_workflows.jsonl"),
        help="GeoMiniLM workflow JSONL dataset.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/models/geominilm"),
        help="Directory for preprocessed data and prototype metadata.",
    )
    parser.add_argument(
        "--predictions-dir",
        type=Path,
        default=Path("outputs/model_samples"),
        help="Directory for dry-run sample predictions.",
    )
    parser.add_argument(
        "--eval-dir",
        type=Path,
        default=Path("outputs/eval/geominilm_dry_run"),
        help="Directory for dry-run evaluation reports.",
    )
    parser.add_argument(
        "--model-name",
        default="geominilm-local-baseline",
        help="Prototype model or adapter name recorded in dry-run metadata.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and preprocess without downloading or training a model.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.dry_run:
        raise SystemExit("Only --dry-run is implemented for the local GeoMiniLM prototype.")

    try:
        artifacts = run_dry_run(args)
    except EvaluationInputError as exc:
        for error in exc.errors:
            print(error, file=sys.stderr)
        raise SystemExit(2) from exc

    print("GeoMiniLM dry run complete")
    print(f"Records: {artifacts['summary']['total_records']}")
    print(f"Preprocessed data: {artifacts['preprocessed_path']}")
    print(f"Metadata: {artifacts['metadata_path']}")
    print(f"Predictions: {artifacts['predictions_path']}")
    print(f"Evaluation: {artifacts['evaluation_json_path']}")


def run_dry_run(args: argparse.Namespace) -> dict[str, object]:
    examples = load_geominilm_dataset(args.dataset)
    pairs = preprocess_examples(examples)
    summary = summarize_examples(examples)

    preprocessed_path = write_preprocessed_jsonl(pairs, args.output_dir / "training_pairs.jsonl")
    metadata_path = write_metadata(
        args.output_dir / "metadata.json",
        dataset_path=args.dataset,
        model_name=args.model_name,
        summary=summary.to_dict(),
    )

    predictions = build_baseline_predictions(examples)
    predictions_path = write_jsonl_records(predictions, args.predictions_dir / "dry_run_predictions.jsonl")
    report = evaluate_records([example.to_record() for example in examples], predictions)
    evaluation_json_path = write_json_report(report, args.eval_dir / "evaluation_report.json")
    evaluation_markdown_path = write_markdown_report(report, args.eval_dir / "evaluation_report.md")

    return {
        "summary": summary.to_dict(),
        "preprocessed_path": preprocessed_path,
        "metadata_path": metadata_path,
        "predictions_path": predictions_path,
        "evaluation_json_path": evaluation_json_path,
        "evaluation_markdown_path": evaluation_markdown_path,
    }


def write_metadata(
    path: Path,
    *,
    dataset_path: Path,
    model_name: str,
    summary: dict[str, object],
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "dataset": str(dataset_path),
        "dry_run": True,
        "model_name": model_name,
        "summary": summary,
        "training_status": "not_started",
        "notes": "Local dry run validates and preprocesses data without downloading model weights.",
    }
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    main()
