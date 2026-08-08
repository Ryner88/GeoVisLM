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
from geovis_lm.model.evaluation_design import (  # noqa: E402
    DEFAULT_MINIMUM_THRESHOLD_MARGIN,
    DEFAULT_MINIMUM_VALIDATION_RECORDS,
    DEFAULT_PRIMARY_METRIC,
    DEFAULT_PRODUCTION_PASS_THRESHOLD,
    SplitSpec,
    build_evaluation_manifest,
    build_production_decision,
    validate_evaluation_splits,
    validate_manifest_file,
)
from geovis_lm.model.prototype import (  # noqa: E402
    GeoMiniLMPrototype,
    compare_reports,
    run_grouped_holdout_evaluation,
    run_leave_one_out_evaluation,
    run_validation_experiment,
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
        "--extra-training-data",
        type=Path,
        action="append",
        default=[],
        help="Additional GeoMiniLM JSONL training data. Can be provided more than once.",
    )
    parser.add_argument(
        "--validation-set",
        type=Path,
        default=None,
        help="Frozen validation JSONL file for honest validation-set evaluation.",
    )
    parser.add_argument(
        "--failure-taxonomy",
        type=Path,
        default=Path("data/geominilm/failure_taxonomy.json"),
        help="Failure taxonomy used for per-category validation reporting.",
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
    parser.add_argument(
        "--grouped-held-out-eval",
        action="store_true",
        help="Run grouped workflow-family holdout evaluation for development model selection.",
    )
    parser.add_argument(
        "--evaluation-manifest",
        type=Path,
        default=Path("data/geominilm/evaluation_manifest.json"),
        help="Frozen production evaluation manifest. Validation runs verify this file when it exists.",
    )
    parser.add_argument(
        "--primary-metric",
        default=DEFAULT_PRIMARY_METRIC,
        help="Locked primary metric name for production validation runs.",
    )
    parser.add_argument(
        "--production-pass-threshold",
        type=float,
        default=DEFAULT_PRODUCTION_PASS_THRESHOLD,
        help="Locked pass threshold for the production validation gate.",
    )
    parser.add_argument(
        "--minimum-validation-records",
        type=int,
        default=DEFAULT_MINIMUM_VALIDATION_RECORDS,
        help="Minimum frozen validation examples required before dashboard integration can be authorized.",
    )
    parser.add_argument(
        "--minimum-threshold-margin",
        type=float,
        default=DEFAULT_MINIMUM_THRESHOLD_MARGIN,
        help="Minimum margin above the pass threshold required before dashboard integration can be authorized.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        if args.validation_set is not None:
            artifacts = run_validation_set_experiment(args)
            mode = "GeoMiniLM validation experiment complete"
        elif args.grouped_held_out_eval:
            artifacts = run_grouped_held_out_evaluation(args)
            mode = "GeoMiniLM grouped held-out evaluation complete"
        elif args.held_out_eval:
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
    if "experiment_comparison_path" in artifacts:
        print(f"Experiment comparison: {artifacts['experiment_comparison_path']}")


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
    examples = _load_training_examples(args)
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
    examples = _load_training_examples(args)
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
    calibration_path = write_auxiliary_json(
        heldout_result.comparison["confidence_calibration"],
        eval_dir / "confidence_calibration.json",
    )
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
        "calibration_path": calibration_path,
        "comparison_json_path": comparison_json_path,
        "comparison_markdown_path": comparison_markdown_path,
    }


def run_grouped_held_out_evaluation(args: argparse.Namespace) -> dict[str, object]:
    examples = _load_training_examples(args)
    pairs = preprocess_examples(examples)
    summary = summarize_examples(examples)

    preprocessed_path = write_preprocessed_jsonl(pairs, args.output_dir / "training_pairs.jsonl")
    heldout_result = run_grouped_holdout_evaluation(
        examples,
        args.output_dir / "grouped_heldout_folds",
        family_by_id=workflow_family_map(args.failure_taxonomy),
        model_name=args.model_name,
    )
    predictions_path = write_jsonl_records(heldout_result.predictions, args.predictions_dir / "grouped_heldout_predictions.jsonl")
    eval_dir = _eval_dir(args, dry_run=False, grouped_held_out=True)
    evaluation_json_path = write_json_report(heldout_result.heldout_report, eval_dir / "evaluation_report.json")
    evaluation_markdown_path = write_markdown_report(heldout_result.heldout_report, eval_dir / "evaluation_report.md")
    calibration_path = write_auxiliary_json(
        heldout_result.comparison["confidence_calibration"],
        eval_dir / "confidence_calibration.json",
    )
    comparison_json_path, comparison_markdown_path = write_comparison_report(
        heldout_result.comparison,
        eval_dir / "baseline_comparison.json",
        eval_dir / "baseline_comparison.md",
        trained_label="grouped_holdout",
    )
    metadata_path = write_metadata(
        args.output_dir / "grouped_heldout_metadata.json",
        dataset_path=args.dataset,
        model_name=args.model_name,
        summary=summary.to_dict(),
        training_status="grouped_held_out_complete",
        dry_run=False,
        training={
            "algorithm": "grouped_workflow_family_tfidf_nearest_neighbor",
            "candidate_components": ["tfidf_retrieval_checkpoint", "workflow_template_code"],
            "fold_count": len(heldout_result.folds),
            "workflow_families": heldout_result.comparison["workflow_families"],
        },
        evaluation={
            "grouped_holdout_summary_score": heldout_result.comparison["grouped_holdout_summary_score"],
            "baseline_summary_score": heldout_result.comparison["baseline_summary_score"],
            "summary_delta": heldout_result.comparison["summary_delta"],
            "failed_examples": heldout_result.comparison["failed_examples"],
        },
    )

    return {
        "summary": summary.to_dict(),
        "preprocessed_path": preprocessed_path,
        "metadata_path": metadata_path,
        "fold_checkpoint_dir": args.output_dir / "grouped_heldout_folds",
        "predictions_path": predictions_path,
        "evaluation_json_path": evaluation_json_path,
        "evaluation_markdown_path": evaluation_markdown_path,
        "calibration_path": calibration_path,
        "comparison_json_path": comparison_json_path,
        "comparison_markdown_path": comparison_markdown_path,
    }


def run_validation_set_experiment(args: argparse.Namespace) -> dict[str, object]:
    training_examples = _load_training_examples(args)
    validation_examples = load_geominilm_dataset(args.validation_set)
    pairs = preprocess_examples(training_examples)
    summary = summarize_examples(training_examples)
    split_specs = _production_split_specs(args)
    split_validation = validate_evaluation_splits(split_specs, taxonomy_path=args.failure_taxonomy)
    if not split_validation.passed:
        raise EvaluationInputError(
            [
                "production evaluation split validation failed",
                *[
                    (
                        f"{issue.kind}: {issue.left_split}/{issue.left_id} "
                        f"matches {issue.right_split}/{issue.right_id} at {issue.similarity:.4f}"
                    )
                    for issue in split_validation.issues
                ],
            ]
        )

    preprocessed_path = write_preprocessed_jsonl(pairs, args.output_dir / "training_pairs.jsonl")
    result = run_validation_experiment(
        training_examples,
        validation_examples,
        args.output_dir / "validation_checkpoint.json",
        model_name=args.model_name,
        primary_metric=args.primary_metric,
        pass_threshold=args.production_pass_threshold,
        minimum_validation_records=args.minimum_validation_records,
        minimum_threshold_margin=args.minimum_threshold_margin,
    )
    predictions_path = write_jsonl_records(result.predictions, args.predictions_dir / "validation_predictions.jsonl")
    honest_baseline_path = write_jsonl_records(
        result.honest_baseline_predictions,
        args.predictions_dir / "honest_baseline_predictions.jsonl",
    )

    eval_dir = _eval_dir(args, dry_run=False, validation=True)
    manifest_path = write_evaluation_manifest(args, split_specs, eval_dir)
    manifest_check = build_manifest_check(args)
    split_validation_payload = split_validation.to_dict()
    result.comparison["manifest_check"] = {
        "passed": manifest_check["passed"],
        "mismatches": manifest_check["mismatches"],
    }
    result.comparison["split_validation"] = {
        "passed": split_validation_payload["passed"],
        "issue_count": len(split_validation_payload["issues"]),
    }
    result.comparison["category_results"] = build_category_results(args.failure_taxonomy, result.comparison)
    result.comparison["production_decision"] = build_production_decision(result.comparison)
    manifest_check_path = write_auxiliary_json(manifest_check, eval_dir / "manifest_check.json")
    split_validation_path = write_split_validation(split_validation_payload, eval_dir / "split_validation.json")
    calibration_path = write_auxiliary_json(
        result.comparison["confidence_calibration"],
        eval_dir / "confidence_calibration.json",
    )
    production_decision_path = write_auxiliary_json(
        result.comparison["production_decision"],
        eval_dir / "production_decision.json",
    )
    evaluation_json_path = write_json_report(result.trained_report, eval_dir / "evaluation_report.json")
    evaluation_markdown_path = write_markdown_report(result.trained_report, eval_dir / "evaluation_report.md")
    honest_baseline_json_path = write_json_report(
        result.honest_baseline_report,
        eval_dir / "honest_baseline_report.json",
    )
    oracle_sanity_json_path = write_json_report(
        result.oracle_sanity_report,
        eval_dir / "oracle_sanity_report.json",
    )
    experiment_comparison_path = write_experiment_comparison(
        result.comparison,
        eval_dir / "experiment_comparison.json",
        eval_dir / "experiment_comparison.md",
    )
    metadata_path = write_metadata(
        args.output_dir / "validation_experiment_metadata.json",
        dataset_path=args.dataset,
        model_name=args.model_name,
        summary=summary.to_dict(),
        training_status="validation_experiment_complete",
        dry_run=False,
        training={
            "training_dataset": str(args.dataset),
            "extra_training_data": [str(path) for path in args.extra_training_data],
            "validation_set": str(args.validation_set),
            "training_records": len(training_examples),
            "validation_records": len(validation_examples),
            "checkpoint_path": str(args.output_dir / "validation_checkpoint.json"),
            "validation_ids": [example.id for example in validation_examples],
        },
        evaluation=result.comparison,
    )
    return {
        "summary": summary.to_dict(),
        "preprocessed_path": preprocessed_path,
        "metadata_path": metadata_path,
        "predictions_path": predictions_path,
        "honest_baseline_path": honest_baseline_path,
        "evaluation_json_path": evaluation_json_path,
        "evaluation_markdown_path": evaluation_markdown_path,
        "honest_baseline_json_path": honest_baseline_json_path,
        "oracle_sanity_json_path": oracle_sanity_json_path,
        "experiment_comparison_path": experiment_comparison_path,
        "manifest_path": manifest_path,
        "manifest_check_path": manifest_check_path,
        "split_validation_path": split_validation_path,
        "calibration_path": calibration_path,
        "production_decision_path": production_decision_path,
    }


def _load_training_examples(args: argparse.Namespace):
    examples = load_geominilm_dataset(args.dataset)
    seen_ids = {example.id for example in examples}
    duplicate_ids = []
    for path in args.extra_training_data:
        extra_examples = load_geominilm_dataset(path)
        for example in extra_examples:
            if example.id in seen_ids:
                duplicate_ids.append(example.id)
            seen_ids.add(example.id)
        examples.extend(extra_examples)
    if duplicate_ids:
        raise EvaluationInputError([f"duplicate training ids: {', '.join(sorted(duplicate_ids))}"])
    return examples


def build_category_results(taxonomy_path: Path, comparison: dict[str, object]) -> dict[str, dict[str, object]]:
    taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    records = {record["id"]: record for record in comparison["record_deltas"]}
    failed_ids = {record["id"] for record in comparison["failed_examples"]}
    category_results = {}
    for category_name, category in taxonomy["categories"].items():
        validation_ids = category["validation_ids"]
        category_records = [records[record_id] for record_id in validation_ids if record_id in records]
        trained_scores = [record["trained_score"] for record in category_records]
        honest_baseline_scores = [record["honest_baseline_score"] for record in category_records]
        category_results[category_name] = {
            "operation": category["operation"],
            "parameters": category["parameters"],
            "output_structure": category["output_structure"],
            "validation_ids": validation_ids,
            "training_expansion_ids": category["training_expansion_ids"],
            "trained_score": round(sum(trained_scores) / len(trained_scores), 4) if trained_scores else 0.0,
            "honest_baseline_score": (
                round(sum(honest_baseline_scores) / len(honest_baseline_scores), 4)
                if honest_baseline_scores
                else 0.0
            ),
            "failed_count": sum(1 for record in category_records if record["id"] in failed_ids),
            "total_count": len(category_records),
        }
    return category_results


def workflow_family_map(taxonomy_path: Path) -> dict[str, str]:
    taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))
    family_by_id: dict[str, str] = {}
    for category_name, category in taxonomy["categories"].items():
        for key in ("failure_ids", "training_expansion_ids", "validation_ids"):
            for record_id in category.get(key, []):
                family_by_id[record_id] = category_name
    return family_by_id


def _eval_dir(
    args: argparse.Namespace,
    *,
    dry_run: bool,
    held_out: bool = False,
    grouped_held_out: bool = False,
    validation: bool = False,
) -> Path:
    if args.eval_dir is not None:
        return args.eval_dir
    if validation:
        return Path("outputs/eval/geominilm_validation")
    if held_out:
        return Path("outputs/eval/geominilm_heldout")
    if grouped_held_out:
        return Path("outputs/eval/geominilm_grouped_heldout")
    return Path("outputs/eval/geominilm_dry_run" if dry_run else "outputs/eval/geominilm_training")


def write_experiment_comparison(comparison: dict[str, object], json_path: Path, markdown_path: Path) -> Path:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# GeoMiniLM Validation Experiment",
        "",
        f"- Trained validation score: {comparison['trained_validation_score']:.4f}",
        f"- Honest baseline score: {comparison['honest_baseline_score']:.4f}",
        f"- Oracle sanity score: {comparison['oracle_sanity_score']:.4f}",
        f"- Reference held-out score: {comparison['reference_heldout_score']:.4f}",
        f"- Delta vs honest baseline: {comparison['delta_vs_honest_baseline']:.4f}",
        f"- Delta vs reference held-out: {comparison['delta_vs_reference_heldout']:.4f}",
        f"- Primary metric: {comparison['primary_metric']}",
        f"- Pass threshold: {comparison['pass_threshold']:.4f}",
        (
            f"- Dashboard integration: "
            f"{'allowed' if comparison['production_decision']['dashboard_integration_allowed'] else 'blocked'}"
        ),
        (
            f"- Expected calibration error: "
            f"{comparison['confidence_calibration']['expected_calibration_error']:.4f}"
        ),
        "",
        "The oracle sanity score uses expected validation outputs and is not a generalization benchmark.",
        comparison["baseline_notes"]["reference_heldout"],
        "",
        "| ID | Trained | Honest Baseline | Delta | Findings |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for record in comparison["record_deltas"]:
        findings = ", ".join(record["findings"]) or "none"
        lines.append(
            f"| {record['id']} | {record['trained_score']:.4f} | "
            f"{record['honest_baseline_score']:.4f} | {record['delta_vs_honest_baseline']:.4f} | {findings} |"
        )
    if comparison["failed_examples"]:
        lines.extend(["", "## Failed Examples", ""])
        for failure in comparison["failed_examples"]:
            findings = ", ".join(failure["findings"]) or "none"
            lines.append(f"- `{failure['id']}` score `{failure['trained_score']:.4f}`: {findings}")
    if comparison.get("category_results"):
        lines.extend(["", "## Category Results", "", "| Category | Trained | Honest Baseline | Failed |", "| --- | ---: | ---: | ---: |"])
        for category_name, result in comparison["category_results"].items():
            lines.append(
                f"| {category_name} | {result['trained_score']:.4f} | "
                f"{result['honest_baseline_score']:.4f} | {result['failed_count']}/{result['total_count']} |"
            )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path


def _production_split_specs(args: argparse.Namespace) -> list[SplitSpec]:
    return [
        SplitSpec("starter", "training", args.dataset),
        *[SplitSpec(f"extra_training_{index}", "training", path) for index, path in enumerate(args.extra_training_data, start=1)],
        SplitSpec("expanded_validation", "validation", args.validation_set),
    ]


def write_evaluation_manifest(args: argparse.Namespace, split_specs: list[SplitSpec], eval_dir: Path) -> Path:
    if args.evaluation_manifest.exists():
        manifest = json.loads(args.evaluation_manifest.read_text(encoding="utf-8"))
    else:
        manifest = build_evaluation_manifest(
            split_specs,
            taxonomy_path=args.failure_taxonomy,
            primary_metric=args.primary_metric,
            pass_threshold=args.production_pass_threshold,
            minimum_validation_records=args.minimum_validation_records,
            minimum_threshold_margin=args.minimum_threshold_margin,
        )
    return write_auxiliary_json(manifest, eval_dir / "evaluation_manifest.json")


def build_manifest_check(args: argparse.Namespace) -> dict[str, object]:
    if args.evaluation_manifest.exists():
        return validate_manifest_file(args.evaluation_manifest)
    return {
        "passed": False,
        "mismatches": ["evaluation_manifest_missing"],
        "expected": None,
    }


def write_split_validation(payload: dict[str, object], path: Path) -> Path:
    return write_auxiliary_json(payload, path)


def write_auxiliary_json(payload: dict[str, object], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


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
