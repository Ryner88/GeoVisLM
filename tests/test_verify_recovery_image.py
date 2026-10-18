import json
from pathlib import Path
import subprocess

import pytest

from scripts.verify_recovery_image import verify_image


COMMIT = "a" * 40
IMAGE_ID = "sha256:" + "b" * 64


def backup_state(tmp_path: Path, commit: str = COMMIT) -> Path:
    backup = tmp_path / "production-drill-20261017T010203Z"
    backup.mkdir()
    state = f"git_commit={commit}\ndb_volume=production\n"
    for name in ("production-state-before.txt", "production-state-after.txt"):
        (backup / name).write_text(state)
    return backup


def test_matching_image_is_resolved_to_immutable_id(tmp_path, monkeypatch):
    backup = backup_state(tmp_path)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if command[0] == "docker":
            return subprocess.CompletedProcess(
                command, 0,
                json.dumps({"Id": IMAGE_ID, "Config": {"Labels": {"org.opencontainers.image.revision": COMMIT}}}),
            )
        return subprocess.CompletedProcess(command, 0, "")

    monkeypatch.setattr(subprocess, "run", run)
    result = verify_image(backup, "geovis_lm_app:latest", tmp_path)

    assert result["image_id"] == IMAGE_ID
    assert result["production_commit"] == COMMIT
    assert calls[0] == ["git", "-C", str(tmp_path), "cat-file", "-e", f"{COMMIT}^{{commit}}"]
    assert calls[1][:4] == ["docker", "image", "inspect", "geovis_lm_app:latest"]


@pytest.mark.parametrize("label", [None, "c" * 40, "unknown"])
def test_latest_tag_without_matching_revision_is_rejected(tmp_path, monkeypatch, label):
    backup = backup_state(tmp_path)

    def run(command, **kwargs):
        if command[0] == "docker":
            labels = {} if label is None else {"org.opencontainers.image.revision": label}
            return subprocess.CompletedProcess(command, 0, json.dumps({"Id": IMAGE_ID, "Config": {"Labels": labels}}))
        return subprocess.CompletedProcess(command, 0, "")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ValueError, match="revision does not match"):
        verify_image(backup, "geovis_lm_app:latest", tmp_path)


def test_changed_production_state_is_rejected_before_image_inspection(tmp_path, monkeypatch):
    backup = backup_state(tmp_path)
    (backup / "production-state-after.txt").write_text("changed\n")
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: pytest.fail("unexpected inspection"))

    with pytest.raises(ValueError, match="production state changed"):
        verify_image(backup, "geovis_lm_app:latest", tmp_path)


def test_unknown_backup_commit_is_rejected(tmp_path, monkeypatch):
    backup = backup_state(tmp_path)

    def run(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(subprocess.CalledProcessError):
        verify_image(backup, "geovis_lm_app:latest", tmp_path)
