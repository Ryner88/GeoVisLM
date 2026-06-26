from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from geovis_lm.dashboard.app import CONFIG, run_analysis_workflow
from geovis_lm.dashboard.worker import run_worker_once


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Claim and execute one queued GeoVisLM dashboard job.")
    parser.add_argument("--json", action="store_true", help="Print the worker result as JSON.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_worker_once(CONFIG, run_analysis_workflow)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    print(f"Worker status: {result['status']}")


if __name__ == "__main__":
    main()
