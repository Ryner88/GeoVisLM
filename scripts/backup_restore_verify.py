#!/usr/bin/env python3
"""Build output manifests and validate a restored GeoVisLM output tree."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(root: Path) -> list[str]:
    rows: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        mode = stat.S_IMODE(path.stat().st_mode)
        rows.append(
            f"{file_digest(path)}\t{path.stat().st_size}\t{mode:04o}\t{relative}"
        )
    return rows


def resolve_output_reference(root: Path, value: str) -> Path | None:
    marker = "/app/outputs/"
    if value.startswith(marker):
        return root / value[len(marker) :]
    return None


def iter_values(value: object):
    if isinstance(value, dict):
        for child in value.values():
            yield from iter_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_values(child)
    else:
        yield value


def validate_tree(root: Path) -> dict[str, object]:
    json_files = sorted(root.rglob("*.json"))
    parsed: dict[Path, object] = {}
    for path in json_files:
        parsed[path] = json.loads(path.read_text(encoding="utf-8"))

    projects = sorted((root / "projects").glob("*/project.json"))
    runs = sorted((root / "runs").glob("*/metadata.json"))
    jobs = sorted((root / "jobs").glob("*/job.json"))
    reports = sorted((root / "runs").glob("*/reports/*"))
    artifacts = sorted(
        path
        for path in (root / "runs").rglob("*")
        if path.is_file() and path.name != "metadata.json"
    )

    missing_references: list[str] = []
    checked_references = 0
    for source, document in parsed.items():
        for value in iter_values(document):
            if not isinstance(value, str):
                continue
            referenced = resolve_output_reference(root, value)
            if referenced is None:
                continue
            checked_references += 1
            if not referenced.exists():
                missing_references.append(
                    f"{source.relative_to(root).as_posix()} -> {value}"
                )

    project_ids = {path.parent.name for path in projects}
    orphan_runs: list[str] = []
    for path in runs:
        document = parsed[path]
        if not isinstance(document, dict):
            orphan_runs.append(path.parent.name)
            continue
        project_id = document.get("project_id")
        if isinstance(project_id, str) and project_id not in project_ids:
            orphan_runs.append(path.parent.name)

    result: dict[str, object] = {
        "artifact_files": len(artifacts),
        "checked_output_references": checked_references,
        "file_count": len(build_manifest(root)),
        "job_records": len(jobs),
        "json_files_parsed": len(json_files),
        "missing_output_references": missing_references,
        "orphan_runs": orphan_runs,
        "project_records": len(projects),
        "report_files": len(reports),
        "run_records": len(runs),
        "total_bytes": sum(
            path.stat().st_size for path in root.rglob("*") if path.is_file()
        ),
    }
    if not projects or not runs or not reports or not artifacts:
        raise ValueError(f"restored tree is missing required record types: {result}")
    if missing_references or orphan_runs:
        raise ValueError(f"restored metadata integrity check failed: {result}")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest = subparsers.add_parser("manifest")
    manifest.add_argument("root", type=Path)

    validate = subparsers.add_parser("validate")
    validate.add_argument("root", type=Path)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        raise ValueError(f"output root is not a directory: {root}")
    if args.command == "manifest":
        sys.stdout.write("\n".join(build_manifest(root)) + "\n")
        return 0
    print(json.dumps(validate_tree(root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
