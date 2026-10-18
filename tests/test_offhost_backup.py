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


def config(**overrides) -> offhost_backup.Config:
    values = dict(
        bucket="private-backups",
        prefix="geovislm/production",
        recipient=None,
        alert_url=None,
        retries=3,
        retry_base_seconds=0,
        retention_days=90,
        retention_minimum=3,
    )
    values.update(overrides)
    return offhost_backup.Config(**values)


def remote_object(name: str, file_id: str, action: str = "upload") -> dict[str, object]:
    return {"fileName": name, "fileId": file_id, "action": action}


def remote_pair(prefix: str, stamp: str, suffix: str = "") -> list[dict[str, object]]:
    name = f"{prefix}/production-drill-{stamp}.tar.age"
    return [
        remote_object(name, f"cipher-{stamp}{suffix}"),
        remote_object(name + ".sha256", f"checksum-{stamp}{suffix}"),
    ]


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
    cfg = config()
    objects = []
    for month in range(1, 7):
        objects.extend(remote_pair(cfg.prefix, f"20260{month}01T000000Z"))
    pairs = offhost_backup.parse_retention_inventory(cfg, objects)

    deleted = offhost_backup.eligible_pair_names(
        pairs,
        now=datetime(2026, 10, 17, tzinfo=timezone.utc),
        days=90,
        minimum=3,
    )

    assert deleted == [
        f"{cfg.prefix}/production-drill-20260{month}01T000000Z.tar.age"
        for month in range(1, 4)
    ]


def test_retention_inventory_requires_exact_canary_prefix_and_single_versions():
    cfg = config(prefix="geovislm/production/retention-canary")
    objects = remote_pair(cfg.prefix, "20260101T000000Z")

    pairs = offhost_backup.parse_retention_inventory(cfg, objects)
    assert len(pairs) == 1

    with pytest.raises(offhost_backup.BackupError, match="escaped"):
        offhost_backup.parse_retention_inventory(
            cfg,
            [remote_object("geovislm/production/wrong/object.tar.age", "wrong")],
        )

    with pytest.raises(offhost_backup.BackupError, match="multiple versions"):
        offhost_backup.parse_retention_inventory(
            cfg,
            objects + [remote_object(objects[0]["fileName"], "duplicate-version")],
        )


def test_unexpected_incomplete_pair_blocks_unrelated_retention(monkeypatch):
    cfg = config(prefix="geovislm/production/retention-canary")
    incomplete = remote_pair(cfg.prefix, "20200101T000000Z")[:1]
    monkeypatch.setattr(offhost_backup, "list_objects", lambda _config: incomplete)
    monkeypatch.setattr(
        offhost_backup,
        "delete_version",
        lambda *_args: pytest.fail("deletion must not start"),
    )

    with pytest.raises(offhost_backup.BackupError, match="incomplete backup pair"):
        offhost_backup.apply_retention(cfg, dry_run=False)


def test_immediate_revalidation_rejects_changed_object_versions(monkeypatch):
    cfg = config(prefix="geovislm/production/retention-canary")
    target_name = f"{cfg.prefix}/production-drill-20200101T000000Z.tar.age"
    objects = remote_pair(cfg.prefix, "20200101T000000Z", "-changed")
    for stamp in ("20260701T000000Z", "20260801T000000Z", "20260901T000000Z"):
        objects.extend(remote_pair(cfg.prefix, stamp))
    monkeypatch.setattr(offhost_backup, "preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(offhost_backup, "list_objects", lambda _config: objects)

    with pytest.raises(offhost_backup.BackupError, match="versions changed"):
        offhost_backup.revalidate_pair_for_deletion(
            cfg,
            target_name,
            {"cipher-original", "checksum-original"},
        )


def test_two_object_deletion_records_partial_failure(monkeypatch, tmp_path):
    cfg = config(
        prefix="geovislm/production/retention-canary",
        retention_state_dir=tmp_path / "state",
    )
    target_name = f"{cfg.prefix}/production-drill-20200101T000000Z.tar.age"
    target_objects = remote_pair(cfg.prefix, "20200101T000000Z")
    target_pairs = offhost_backup.parse_retention_inventory(cfg, target_objects)
    protected_objects = []
    for stamp in ("20260701T000000Z", "20260801T000000Z", "20260901T000000Z"):
        protected_objects.extend(remote_pair(cfg.prefix, stamp))
    protected = offhost_backup.inventory_version_map(
        offhost_backup.parse_retention_inventory(cfg, protected_objects)
    )
    monkeypatch.setattr(
        offhost_backup,
        "delete_version",
        lambda _config, version: (
            (True, None)
            if version["name"] == target_name
            else (False, "simulated sidecar failure")
        ),
    )
    monkeypatch.setattr(
        offhost_backup,
        "list_objects",
        lambda _config: [target_objects[1], *protected_objects],
    )

    with pytest.raises(offhost_backup.RetentionRecoveryRequired, match="partial"):
        offhost_backup.execute_pair_deletion(
            cfg,
            target_name,
            target_pairs[target_name],
            protected,
        )

    records = list(cfg.retention_state_dir.glob("*.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text())
    assert record["status"] == "partial"
    assert record["components"]["ciphertext"]["absent_after"] is True
    assert record["components"]["checksum"]["absent_after"] is False
    assert record["components"]["ciphertext"]["file_id"] == target_objects[0]["fileId"]
    assert record["components"]["checksum"]["file_id"] == target_objects[1]["fileId"]


def test_recovery_intent_is_durable_before_first_delete(monkeypatch, tmp_path):
    cfg = config(
        prefix="geovislm/production/retention-canary",
        retention_state_dir=tmp_path / "state",
    )
    target_name = f"{cfg.prefix}/production-drill-20200101T000000Z.tar.age"
    target_objects = remote_pair(cfg.prefix, "20200101T000000Z")
    target_pair = offhost_backup.parse_retention_inventory(cfg, target_objects)[target_name]
    protected_objects = remote_pair(cfg.prefix, "20260901T000000Z")
    protected = offhost_backup.inventory_version_map(
        offhost_backup.parse_retention_inventory(cfg, protected_objects)
    )
    attempts = []

    def delete(_config, version):
        saved = json.loads(next(cfg.retention_state_dir.glob("*.json")).read_text())
        if not attempts:
            assert saved["status"] == "prepared"
            assert all(
                saved["components"][component]["delete_command_succeeded"] is None
                for component in ("ciphertext", "checksum")
            )
        else:
            assert saved["status"] == "deletion_in_progress"
            assert saved["components"]["ciphertext"]["delete_command_succeeded"] is True
        attempts.append(version["file_id"])
        return True, None

    monkeypatch.setattr(offhost_backup, "delete_version", delete)
    monkeypatch.setattr(offhost_backup, "list_objects", lambda _config: protected_objects)

    result = offhost_backup.execute_pair_deletion(
        cfg,
        target_name,
        target_pair,
        protected,
    )

    assert result["status"] == "complete"
    assert len(attempts) == 2
    persisted = json.loads(Path(result["recovery_record"]).read_text())
    assert persisted["status"] == "complete"


def test_partial_deletion_retry_is_idempotent_and_verifies_inventory(monkeypatch, tmp_path):
    cfg = config(
        prefix="geovislm/production/retention-canary",
        retention_state_dir=tmp_path / "state",
    )
    target_name = f"{cfg.prefix}/production-drill-20200101T000000Z.tar.age"
    target_objects = remote_pair(cfg.prefix, "20200101T000000Z")
    protected_objects = []
    for stamp in ("20260701T000000Z", "20260801T000000Z", "20260901T000000Z"):
        protected_objects.extend(remote_pair(cfg.prefix, stamp))
    protected = offhost_backup.inventory_version_map(
        offhost_backup.parse_retention_inventory(cfg, protected_objects)
    )
    record = {
        "schema_version": 1,
        "bucket": cfg.bucket,
        "prefix": cfg.prefix,
        "pair_name": target_name,
        "backup_timestamp": "2020-01-01T00:00:00+00:00",
        "checked_at": "2026-10-18T00:00:00+00:00",
        "retention_days": 90,
        "retention_minimum": 3,
        "components": {
            "ciphertext": {
                "name": target_objects[0]["fileName"],
                "file_id": target_objects[0]["fileId"],
                "absent_after": True,
            },
            "checksum": {
                "name": target_objects[1]["fileName"],
                "file_id": target_objects[1]["fileId"],
                "absent_after": False,
            },
        },
        "protected_versions": protected,
        "status": "partial",
    }
    cfg.retention_state_dir.mkdir(mode=0o700)
    recovery_file = cfg.retention_state_dir / "partial.json"
    recovery_file.write_text(json.dumps(record))
    recovery_file.chmod(0o600)
    inventories = iter(
        [
            [target_objects[1], *protected_objects],
            protected_objects,
        ]
    )
    monkeypatch.setattr(offhost_backup, "preflight", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(offhost_backup, "list_objects", lambda _config: next(inventories))
    attempted = []

    def delete(_config, version):
        attempted.append(version["file_id"])
        return (version["file_id"] == target_objects[1]["fileId"], None)

    monkeypatch.setattr(offhost_backup, "delete_version", delete)

    result = offhost_backup.retry_retention(cfg, recovery_file)

    assert result["status"] == "complete"
    assert set(attempted) == {target_objects[0]["fileId"], target_objects[1]["fileId"]}
    saved = json.loads(recovery_file.read_text())
    assert saved["status"] == "complete"
    assert all(
        saved["components"][component]["absent_after"]
        for component in ("ciphertext", "checksum")
    )


def test_final_inventory_must_preserve_every_non_target_version(monkeypatch, tmp_path):
    cfg = config(
        prefix="geovislm/production/retention-canary",
        retention_state_dir=tmp_path / "state",
    )
    target_name = f"{cfg.prefix}/production-drill-20200101T000000Z.tar.age"
    target_objects = remote_pair(cfg.prefix, "20200101T000000Z")
    target_pair = offhost_backup.parse_retention_inventory(cfg, target_objects)[target_name]
    protected_objects = remote_pair(cfg.prefix, "20260901T000000Z")
    protected = offhost_backup.inventory_version_map(
        offhost_backup.parse_retention_inventory(cfg, protected_objects)
    )
    monkeypatch.setattr(offhost_backup, "delete_version", lambda *_args: (True, None))
    monkeypatch.setattr(offhost_backup, "list_objects", lambda _config: [])

    with pytest.raises(
        offhost_backup.RetentionRecoveryRequired,
        match="inventory verification failed",
    ):
        offhost_backup.execute_pair_deletion(
            cfg,
            target_name,
            target_pair,
            protected,
        )

    record = json.loads(next(cfg.retention_state_dir.glob("*.json")).read_text())
    assert record["status"] == "inventory_verification_failed"


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
