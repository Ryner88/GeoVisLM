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
from geovis_lm.model.prototype import (  # noqa: E402
    GeoMiniLMPrototype,
    compare_reports,
    run_leave_one_out_evaluation,
    train_and_save_checkpoint,
    write_comparison_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train or dry-run the local GeoMiniLM prototype.")
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
        default=None,
        help=(
            "Directory for evaluation reports. Defaults to outputs/eval/geominilm_dry_run "
            "with --dry-run and outputs/eval/geominilm_training otherwise."
        ),
    )
    parser.add_argument(
        "--model-name",
        default="geominilm-token-retrieval-v1",
        help="Prototype model or adapter name recorded in metadata.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and preprocess without downloading or training a model.",
    )
    parser.add_argument(
        "--held-out-eval",
        action="store_true",
        help="Run leave-one-out evaluation, excluding each evaluated record from its fold checkpoint.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        if args.held_out_eval:
            artifacts = run_held_out_evaluation(args)
            mode = "GeoMiniLM held-out evaluation complete"
        elif args.dry_run:
            artifacts = run_dry_run(args)
            mode = "GeoMiniLM dry run complete"
        else:
            artifacts = run_training(args)
            mode = "GeoMiniLM training complete"
    except EvaluationInputError as exc:
        for error in exc.errors:
            print(error, file=sys.stderr)
        raise SystemExit(2) from exc

    print(mode)
    print(f"Records: {artifacts['summary']['total_records']}")
    print(f"Preprocessed data: {artifacts['preprocessed_path']}")
    print(f"Metadata: {artifacts['metadata_path']}")
    print(f"Predictions: {artifacts['predictions_path']}")
    print(f"Evaluation: {artifacts['evaluation_json_path']}")
    if "checkpoint_path" in artifacts:
        print(f"Checkpoint: {artifacts['checkpoint_path']}")
        print(f"Baseline comparison: {artifacts['comparison_json_path']}")
    if "fold_checkpoint_dir" in artifacts:
        print(f"Fold checkpoints: {artifacts['fold_checkpoint_dir']}")
        print(f"Baseline comparison: {artifacts['comparison_json_path']}")


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
        training_status="not_started",
        dry_run=True,
    )

    predictions = build_baseline_predictions(examples)
    predictions_path = write_jsonl_records(predictions, args.predictions_dir / "dry_run_predictions.jsonl")
    report = evaluate_records([example.to_record() for example in examples], predictions)
    eval_dir = _eval_dir(args, dry_run=True)
    evaluation_json_path = write_json_report(report, eval_dir / "evaluation_report.json")
    evaluation_markdown_path = write_markdown_report(report, eval_dir / "evaluation_report.md")

    return {
        "summary": summary.to_dict(),
        "preprocessed_path": preprocessed_path,
        "metadata_path": metadata_path,
        "predictions_path": predictions_path,
        "evaluation_json_path": evaluation_json_path,
        "evaluation_markdown_path": evaluation_markdown_path,
    }


def run_training(args: argparse.Namespace) -> dict[str, object]:
    examples = load_geominilm_dataset(args.dataset)
    pairs = preprocess_examples(examples)
    summary = summarize_examples(examples)

    preprocessed_path = write_preprocessed_jsonl(pairs, args.output_dir / "training_pairs.jsonl")
    training_result = train_and_save_checkpoint(
        examples,
        args.output_dir / "checkpoint.json",
        model_name=args.model_name,
    )
    loaded_model = GeoMiniLMPrototype.load(training_result.checkpoint_path)
    predictions = loaded_model.predict_many(examples)
    predictions_path = write_jsonl_records(predictions, args.predictions_dir / "trained_predictions.jsonl")

    expected_records = [example.to_record() for example in examples]
    trained_report = evaluate_records(expected_records, predictions)
    baseline_predictions = build_baseline_predictions(examples)
    baseline_report = evaluate_records(expected_records, baseline_predictions)
    comparison = compare_reports(trained_report, baseline_report)

    eval_dir = _eval_dir(args, dry_run=False)
    evaluation_json_path = write_json_report(trained_report, eval_dir / "evaluation_report.json")
    evaluation_markdown_path = write_markdown_report(trained_report, eval_dir / "evaluation_report.md")
    comparison_json_path, comparison_markdown_path = write_comparison_report(
        comparison,
        eval_dir / "baseline_comparison.json",
        eval_dir / "baseline_comparison.md",
    )
    metadata_path = write_metadata(
        args.output_dir / "metadata.json",
        dataset_path=args.dataset,
        model_name=args.model_name,
        summary=summary.to_dict(),
        training_status="complete",
        dry_run=False,
        training=training_result.metadata,
        evaluation={
            "summary_score": round(trained_report.summary_score, 4),
            "passed": trained_report.passed,
            "baseline_summary_score": comparison["baseline_summary_score"],
            "summary_delta": comparison["summary_delta"],
        },
    )

    return {
        "summary": summary.to_dict(),
        "preprocessed_path": preprocessed_path,
        "metadata_path": metadata_path,
        "checkpoint_path": training_result.checkpoint_path,
        "predictions_path": predictions_path,
        "evaluation_json_path": evaluation_json_path,
        "evaluation_markdown_path": evaluation_markdown_path,
        "comparison_json_path": comparison_json_path,
        "comparison_markdown_path": comparison_markdown_path,
    }


def run_held_out_evaluation(args: argparse.Namespace) -> dict[str, object]:
    examples = load_geominilm_dataset(args.dataset)
    pairs = preprocess_examples(examples)
    summary = summarize_examples(examples)

    preprocessed_path = write_preprocessed_jsonl(pairs, args.output_dir / "training_pairs.jsonl")
    heldout_result = run_leave_one_out_evaluation(
        examples,
        args.output_dir / "heldout_folds",
        model_name=args.model_name,
    )
    predictions_path = write_jsonl_records(heldout_result.predictions, args.predictions_dir / "heldout_predictions.jsonl")
    eval_dir = _eval_dir(args, dry_run=False, held_out=True)
    evaluation_json_path = write_json_report(heldout_result.heldout_report, eval_dir / "evaluation_report.json")
    evaluation_markdown_path = write_markdown_report(heldout_result.heldout_report, eval_dir / "evaluation_report.md")
    comparison_json_path, comparison_markdown_path = write_comparison_report(
        heldout_result.comparison,
        eval_dir / "baseline_comparison.json",
        eval_dir / "baseline_comparison.md",
        trained_label="heldout",
    )
    metadata_path = write_metadata(
        args.output_dir / "heldout_metadata.json",
        dataset_path=args.dataset,
        model_name=args.model_name,
        summary=summary.to_dict(),
        training_status="held_out_complete",
        dry_run=False,
        training={
            "algorithm": "leave_one_out_tfidf_nearest_neighbor",
            "fold_count": len(heldout_result.folds),
            "folds": [
                {
                    "heldout_record_id": fold.record_id,
                    "checkpoint_path": str(fold.checkpoint_path),
                    "training_record_ids": fold.training_record_ids,
                    "source_checkpoint_record_id": fold.prediction.get("source_checkpoint_record_id"),
                }
                for fold in heldout_result.folds
            ],
        },
        evaluation={
            "heldout_summary_score": heldout_result.comparison["heldout_summary_score"],
            "baseline_summary_score": heldout_result.comparison["baseline_summary_score"],
            "summary_delta": heldout_result.comparison["summary_delta"],
            "failed_examples": heldout_result.comparison["failed_examples"],
        },
    )

    return {
        "summary": summary.to_dict(),
        "preprocessed_path": preprocessed_path,
        "metadata_path": metadata_path,
        "fold_checkpoint_dir": args.output_dir / "heldout_folds",
        "predictions_path": predictions_path,
        "evaluation_json_path": evaluation_json_path,
        "evaluation_markdown_path": evaluation_markdown_path,
        "comparison_json_path": comparison_json_path,
        "comparison_markdown_path": comparison_markdown_path,
    }


def _eval_dir(args: argparse.Namespace, *, dry_run: bool, held_out: bool = False) -> Path:
    if args.eval_dir is not None:
        return args.eval_dir
    if held_out:
        return Path("outputs/eval/geominilm_heldout")
    return Path("outputs/eval/geominilm_dry_run" if dry_run else "outputs/eval/geominilm_training")


def write_metadata(
    path: Path,
    *,
    dataset_path: Path,
    model_name: str,
    summary: dict[str, object],
    training_status: str,
    dry_run: bool,
    training: dict[str, object] | None = None,
    evaluation: dict[str, object] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "created_at": datetime.now(UTC).isoformat(),
        "dataset": str(dataset_path),
        "dry_run": dry_run,
        "model_name": model_name,
        "summary": summary,
        "training_status": training_status,
        "notes": "Local prototype uses a deterministic TF-IDF nearest-neighbor checkpoint over workflow prompts.",
    }
    if training is not None:
        metadata["training"] = training
    if evaluation is not None:
        metadata["evaluation"] = evaluation
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    main()
