#!/usr/bin/env python3
"""Preserve Docker recovery diagnostics and prove scratch cleanup."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys


DOCKER_TIMEOUT_SECONDS = 10


def docker_command(*arguments: str) -> dict[str, object]:
    command = ["docker", *arguments]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=DOCKER_TIMEOUT_SECONDS
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired as error:
        return {"error": "timeout", "detail": str(error)}
    except OSError as error:
        return {"error": type(error).__name__, "detail": str(error)}


def write_private(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def capture_failure(work_dir: Path, database: str, app: str, status: int, stage: str) -> None:
    logs = docker_command("logs", "--timestamps", database)
    write_private(work_dir / "postgresql.log", str(logs.get("stdout", "")) + str(logs.get("stderr", "")))
    state = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "exit_status": status,
        "stage": stage,
        "postgresql_logs": {key: value for key, value in logs.items() if key != "stdout"},
        "database_container": docker_command(
            "inspect", "--format", "{{json .State}}", database
        ),
        "application_container": docker_command(
            "inspect", "--format", "{{json .State}}", app
        ),
        "docker_server": docker_command("version", "--format", "{{json .Server}}"),
    }
    write_private(work_dir / "container-state.json", json.dumps(state, indent=2, sort_keys=True) + "\n")


def verify_cleanup(work_dir: Path, containers: tuple[str, str], volumes: tuple[str, str]) -> bool:
    container_list = docker_command("container", "ls", "--all", "--format", "{{.Names}}")
    volume_list = docker_command("volume", "ls", "--format", "{{.Name}}")
    containers_seen = set(str(container_list.get("stdout", "")).splitlines())
    volumes_seen = set(str(volume_list.get("stdout", "")).splitlines())
    remaining_containers = sorted(containers_seen.intersection(containers))
    remaining_volumes = sorted(volumes_seen.intersection(volumes))
    verified = (
        container_list.get("exit_code") == 0
        and volume_list.get("exit_code") == 0
        and not remaining_containers
        and not remaining_volumes
    )
    evidence = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "containers_absent": not remaining_containers,
        "volumes_absent": not remaining_volumes,
        "remaining_containers": remaining_containers,
        "remaining_volumes": remaining_volumes,
        "container_list_error": container_list.get("stderr", container_list.get("error", "")),
        "volume_list_error": volume_list.get("stderr", volume_list.get("error", "")),
        "verified": verified,
    }
    write_private(work_dir / "scratch-cleanup.json", json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return bool(verified)


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "capture" and len(args) == 6:
        _, work_dir, database, app, status, stage = args
        capture_failure(Path(work_dir), database, app, int(status), stage)
        return 0
    if args and args[0] == "verify-cleanup" and len(args) == 6:
        _, work_dir, database, app, db_volume, output_volume = args
        return 0 if verify_cleanup(Path(work_dir), (database, app), (db_volume, output_volume)) else 1
    print("usage: recovery_diagnostics.py capture|verify-cleanup ...", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
