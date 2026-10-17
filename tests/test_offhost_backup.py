from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

import pytest

from scripts import offhost_backup


def make_backup_set(tmp_path: Path) -> Path:
    root = tmp_path / "production-drill-20261017T010203Z"
    root.mkdir()
    for name in offhost_backup.REQUIRED_BACKUP_FILES:
        (root / name).write_text("fixture\n", encoding="utf-8")
    (root / "postgis.dump").write_bytes(b"database")
    (root / "outputs.tar.gz").write_bytes(b"outputs")
    checksums = []
    for name in ("postgis.dump", "outputs.tar.gz"):
        digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
        checksums.append(f"{digest}  {name}")
    (root / "checksums.sha256").write_text("\n".join(checksums) + "\n")
    (root / "result.txt").write_text(
        "status=pass\n"
        "database_fingerprint_match=true\n"
        "output_manifest_match=true\n"
        "isolated_api_validation=true\n"
        "backup_checksums_pass=true\n"
    )
    (root / "restored-content-validation.json").write_text(
        json.dumps(
            {
                "project_records": 1,
                "run_records": 1,
                "report_files": 1,
                "artifact_files": 1,
                "missing_output_references": [],
                "orphan_runs": [],
            }
        )
    )
    (root / "restored-api-validation.json").write_text(
        json.dumps(
            {
                "projects_verified": 1,
                "runs_verified": 1,
                "artifact_downloads_verified": 1,
                "report_or_metadata_downloads_verified": 1,
            }
        )
    )
    return root


def config() -> offhost_backup.Config:
    return offhost_backup.Config(
        bucket="private-backups",
        prefix="geovislm/production",
        recipient=None,
        alert_url=None,
        retries=3,
        retry_base_seconds=0,
        retention_days=90,
        retention_minimum=3,
    )


def test_validated_backup_covers_all_application_record_types(tmp_path):
    result = offhost_backup.validate_backup_set(make_backup_set(tmp_path))

    assert result["project_records"] == 1
    assert result["run_records"] == 1
    assert result["report_files"] == 1
    assert result["artifact_files"] == 1
    assert result["artifact_downloads_verified"] == 1


def test_backup_validation_rejects_corrupt_payload(tmp_path):
    backup = make_backup_set(tmp_path)
    (backup / "postgis.dump").write_bytes(b"changed")

    with pytest.raises(offhost_backup.BackupError, match="checksum failed"):
        offhost_backup.validate_backup_set(backup)


def test_backup_validation_rejects_missing_reports(tmp_path):
    backup = make_backup_set(tmp_path)
    content = json.loads((backup / "restored-content-validation.json").read_text())
    content["report_files"] = 0
    (backup / "restored-content-validation.json").write_text(json.dumps(content))

    with pytest.raises(offhost_backup.BackupError, match="report_files"):
        offhost_backup.validate_backup_set(backup)


def test_replication_key_must_be_bucket_and_prefix_scoped():
    allowed = {
        "bucketId": "bucket-id",
        "bucketName": "private-backups",
        "namePrefix": "geovislm/production/",
        "capabilities": sorted(offhost_backup.REPLICATION_CAPABILITIES),
    }

    offhost_backup.validate_least_privilege(allowed, config(), recovery=False)

    allowed["namePrefix"] = None
    with pytest.raises(offhost_backup.BackupError, match="object prefix"):
        offhost_backup.validate_least_privilege(allowed, config(), recovery=False)


def test_current_b2_v4_account_response_is_parsed_and_scoped():
    payload = {
        "apiInfo": {
            "storageApi": {
                "allowed": {
                    "buckets": [{"id": "bucket-id", "name": "private-backups"}],
                    "namePrefix": "geovislm/production/",
                    "capabilities": sorted(offhost_backup.REPLICATION_CAPABILITIES),
                }
            }
        }
    }

    allowed = offhost_backup.parse_account_allowed(payload)
    offhost_backup.validate_least_privilege(allowed, config(), recovery=False)


def test_non_b2_subprocesses_do_not_receive_storage_or_alert_secrets(monkeypatch):
    monkeypatch.setenv("B2_APPLICATION_KEY_ID", "key-id")
    monkeypatch.setenv("B2_APPLICATION_KEY", "secret-key")
    monkeypatch.setenv("GEOVIS_BACKUP_ALERT_URL", "https://alerts.example.invalid/secret")
    monkeypatch.setenv("AGE_RECIPIENT", "age1public")

    age_env = offhost_backup.subprocess_env(b2=False)
    b2_env = offhost_backup.subprocess_env(b2=True)

    assert "B2_APPLICATION_KEY_ID" not in age_env
    assert "B2_APPLICATION_KEY" not in age_env
    assert "GEOVIS_BACKUP_ALERT_URL" not in age_env
    assert "AGE_RECIPIENT" not in b2_env
    assert "GEOVIS_BACKUP_ALERT_URL" not in b2_env
    assert b2_env["B2_APPLICATION_KEY"] == "secret-key"


def test_replication_key_rejects_administrative_capabilities():
    allowed = {
        "bucketId": "bucket-id",
        "bucketName": "private-backups",
        "namePrefix": "geovislm/production/",
        "capabilities": sorted(offhost_backup.REPLICATION_CAPABILITIES | {"writeKeys"}),
    }

    with pytest.raises(offhost_backup.BackupError, match="beyond least privilege"):
        offhost_backup.validate_least_privilege(allowed, config(), recovery=False)


def test_recovery_key_can_be_read_only():
    allowed = {
        "bucketId": "bucket-id",
        "bucketName": "private-backups",
        "namePrefix": "geovislm/production/",
        "capabilities": sorted(offhost_backup.RECOVERY_CAPABILITIES),
    }

    offhost_backup.validate_least_privilege(allowed, config(), recovery=True)


def test_retry_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(offhost_backup.time, "sleep", lambda _: None)
    calls = 0

    def operation():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise subprocess.CalledProcessError(1, ["b2"])
        return subprocess.CompletedProcess(["b2"], 0, "ok", "")

    result = offhost_backup.retry(operation, attempts=3, base_seconds=1)

    assert result.stdout == "ok"
    assert calls == 3


def test_retention_keeps_recent_and_newest_three():
    names = [
        f"geovislm/production/production-drill-20260{month}01T000000Z.tar.age"
        for month in range(1, 7)
    ]

    deleted = offhost_backup.retention_deletions(
        names,
        now=datetime(2026, 10, 17, tzinfo=timezone.utc),
        days=90,
        minimum=3,
    )

    assert deleted == names[:3]


def test_safe_extract_rejects_path_traversal(tmp_path):
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as archive:
        member = tarfile.TarInfo("../escape")
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))
    payload.seek(0)

    with pytest.raises(offhost_backup.BackupError, match="unsafe"):
        offhost_backup.safe_extract_stream(payload, tmp_path / "extract")


def test_encrypt_happens_before_upload(monkeypatch, tmp_path):
    backup = make_backup_set(tmp_path)
    events = []
    cfg = offhost_backup.Config(
        bucket="private-backups",
        prefix="geovislm/production",
        recipient="age1testrecipient",
        alert_url="https://alerts.example.invalid/hook",
        retries=1,
        retry_base_seconds=0,
        retention_days=90,
        retention_minimum=3,
    )
    monkeypatch.setattr(offhost_backup.Config, "from_env", lambda **_: cfg)
    monkeypatch.setattr(offhost_backup, "preflight", lambda *_args, **_kwargs: None)

    def encrypt(_source, destination, _recipient):
        events.append("encrypt")
        destination.write_bytes(b"age-encrypted-ciphertext")

    def upload(_config, encrypted, checksum, key):
        events.append("upload")
        assert encrypted.suffix == ".age"
        assert hashlib.sha256(encrypted.read_bytes()).hexdigest() in checksum.read_text()
        assert key.endswith(".tar.age")

    monkeypatch.setattr(offhost_backup, "encrypt_backup", encrypt)
    monkeypatch.setattr(offhost_backup, "upload_and_verify", upload)
    monkeypatch.setattr(offhost_backup, "apply_retention", lambda *_args, **_kwargs: [])

    result = offhost_backup.replicate(backup)

    assert result["status"] == "pass"
    assert events == ["encrypt", "upload"]


def test_systemd_timer_is_not_enabled_by_repository_changes():
    timer = Path("deploy/systemd/geovis-offhost-backup.timer").read_text()
    service = Path("deploy/systemd/geovis-offhost-backup.service").read_text()

    assert "OnCalendar=" in timer
    assert "Persistent=true" in timer
    assert "OnFailure=geovis-offhost-backup-alert.service" in service
    assert "EnvironmentFile=/etc/geovis-lm/offhost-backup.env" in service
    alert_service = Path("deploy/systemd/geovis-offhost-backup-alert.service").read_text()
    assert "EnvironmentFile=/etc/geovis-lm/offhost-alert.env" in alert_service
    assert "offhost-backup.env" not in alert_service
    assert "WantedBy=timers.target" in timer


def test_secret_files_are_not_committed():
    example = Path("deploy/offhost-backup.env.example").read_text()
    gitignore = Path(".gitignore").read_text()

    assert "replace-with-secret" in example
    assert "offhost-backup.env" in gitignore
    assert "offhost-alert.env" in gitignore
