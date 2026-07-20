from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from geovis_lm.eval.workflow_eval import (  # noqa: E402
    DEFAULT_PASS_THRESHOLD,
    EvaluationInputError,
    evaluate_files,
    write_json_report,
    write_markdown_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate GeoMiniLM workflow JSONL predictions.")
    parser.add_argument(
        "--expected",
        type=Path,
        default=Path("data/geominilm/starter_workflows.jsonl"),
        help="Expected workflow JSONL file.",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        required=True,
        help="Predicted workflow JSONL file. Records must include id and predicted_workflow or expected_workflow.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/eval"),
        help="Directory for evaluation_report.json and evaluation_report.md.",
    )
    parser.add_argument(
        "--pass-threshold",
        type=float,
        default=DEFAULT_PASS_THRESHOLD,
        help="Minimum summary and per-record score required for a passing report.",
    )
    parser.add_argument(
        "--fail-on-threshold",
        action="store_true",
        help="Exit with status 1 when the generated report does not pass.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        report = evaluate_files(args.expected, args.predictions, pass_threshold=args.pass_threshold)
    except EvaluationInputError as exc:
        for error in exc.errors:
            print(error, file=sys.stderr)
        raise SystemExit(2) from exc

    json_path = write_json_report(report, args.output_dir / "evaluation_report.json")
    markdown_path = write_markdown_report(report, args.output_dir / "evaluation_report.md")

    print(f"Result: {'PASS' if report.passed else 'FAIL'}")
    print(f"Summary score: {report.summary_score:.3f}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")

    if args.fail_on_threshold and not report.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
