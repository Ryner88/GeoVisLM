#!/usr/bin/env python3
"""Resolve a recovery image to an immutable ID matching the backed-up release."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys


COMMIT = re.compile(r"[0-9a-f]{40}")
IMAGE_ID = re.compile(r"sha256:[0-9a-f]{64}")
REVISION_LABEL = "org.opencontainers.image.revision"


def verify_image(backup_dir: Path, image: str, repository: Path) -> dict[str, str]:
    state = (backup_dir / "production-state-before.txt").read_text(encoding="utf-8")
    commits = [line.removeprefix("git_commit=") for line in state.splitlines() if line.startswith("git_commit=")]
    if len(commits) != 1 or not COMMIT.fullmatch(commits[0]):
        raise ValueError("backup has no valid, unique production Git commit")
    commit = commits[0]
    if (backup_dir / "production-state-after.txt").read_bytes() != state.encode("utf-8"):
        raise ValueError("backup production state changed during the original drill")
    subprocess.run(
        ["git", "-C", str(repository), "cat-file", "-e", f"{commit}^{{commit}}"],
        check=True,
        capture_output=True,
    )
    inspected = subprocess.run(
        ["docker", "image", "inspect", image, "--format", "{{json .}}"],
        check=True,
        capture_output=True,
        text=True,
    )
    details = json.loads(inspected.stdout)
    image_id = details.get("Id")
    labels = details.get("Config", {}).get("Labels") or {}
    if not isinstance(image_id, str) or not IMAGE_ID.fullmatch(image_id):
        raise ValueError("recovery image has no valid immutable image ID")
    if labels.get(REVISION_LABEL) != commit:
        raise ValueError("recovery image revision does not match the backup production commit")
    return {"image_id": image_id, "production_commit": commit, "revision_label": REVISION_LABEL}


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: verify_recovery_image.py BACKUP_DIR IMAGE", file=sys.stderr)
        return 2
    try:
        print(json.dumps(verify_image(Path(sys.argv[1]), sys.argv[2], Path.cwd()), sort_keys=True))
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"recovery image verification failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
