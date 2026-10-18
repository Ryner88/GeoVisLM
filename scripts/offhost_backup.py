#!/usr/bin/env python3
"""Encrypt, replicate, verify, fetch, and retain GeoVisLM backup sets in B2."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Callable, Iterable
from urllib.request import Request, urlopen


BACKUP_NAME = re.compile(r"^production-drill-(\d{8}T\d{6}Z)$")
OBJECT_NAME = re.compile(r"^(?:.*/)?(production-drill-(\d{8}T\d{6}Z))\.tar\.age$")
REQUIRED_BACKUP_FILES = {
    "postgis.dump",
    "outputs.tar.gz",
    "checksums.sha256",
    "production-db-before.tsv",
    "production-outputs-before.tsv",
    "restored-db.tsv",
    "restored-outputs.tsv",
    "restored-content-validation.json",
    "restored-api-validation.json",
    "production-state-before.txt",
    "production-state-after.txt",
    "timings.env",
    "result.txt",
}
REPLICATION_CAPABILITIES = {
    "listBuckets",
    "listFiles",
    "readFiles",
    "writeFiles",
    "deleteFiles",
}
RECOVERY_CAPABILITIES = {"listBuckets", "listFiles", "readFiles"}
class BackupError(RuntimeError):
    pass


class RetentionRecoveryRequired(BackupError):
    """Raised when an exact, persisted retry is required after deletion."""


@dataclass(frozen=True)
class Config:
    bucket: str
    prefix: str
    recipient: str | None
    alert_url: str | None
    retries: int
    retry_base_seconds: float
    retention_days: int
    retention_minimum: int
    retention_state_dir: Path = Path("/root/geovis-backups/offhost-retention-state")

    @classmethod
    def from_env(cls, *, need_recipient: bool, need_alert: bool) -> "Config":
        bucket = required_env("B2_BUCKET")
        prefix = required_env("B2_PREFIX").strip("/")
        recipient = required_env("AGE_RECIPIENT") if need_recipient else None
        alert_url = required_env("GEOVIS_BACKUP_ALERT_URL") if need_alert else os.getenv(
            "GEOVIS_BACKUP_ALERT_URL"
        )
        if (
            not re.fullmatch(r"[A-Za-z0-9.-]{6,63}", bucket)
            or bucket.startswith((".", "b2-"))
            or bucket.endswith(".")
            or ".." in bucket
        ):
            raise BackupError("B2_BUCKET is not a valid bucket name")
        if not prefix or prefix.startswith("/") or ".." in prefix.split("/"):
            raise BackupError("B2_PREFIX must be a non-empty relative object prefix")
        if recipient and not recipient.startswith(("age1", "age1pq1")):
            raise BackupError("AGE_RECIPIENT must be a native age public recipient")
        if alert_url and not alert_url.startswith("https://"):
            raise BackupError("GEOVIS_BACKUP_ALERT_URL must use HTTPS")
        config = cls(
            bucket=bucket,
            prefix=prefix,
            recipient=recipient,
            alert_url=alert_url,
            retries=int(os.getenv("GEOVIS_BACKUP_RETRIES", "4")),
            retry_base_seconds=float(os.getenv("GEOVIS_BACKUP_RETRY_BASE_SECONDS", "2")),
            retention_days=int(os.getenv("GEOVIS_BACKUP_RETENTION_DAYS", "90")),
            retention_minimum=int(os.getenv("GEOVIS_BACKUP_RETENTION_MINIMUM", "3")),
            retention_state_dir=Path(
                os.getenv(
                    "GEOVIS_RETENTION_STATE_DIR",
                    "/root/geovis-backups/offhost-retention-state",
                )
            ),
        )
        if config.retries < 1 or config.retry_base_seconds < 0:
            raise BackupError("retry configuration is invalid")
        if config.retention_days < 1 or config.retention_minimum < 1:
            raise BackupError("retention configuration is invalid")
        return config


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise BackupError(f"required environment variable is missing: {name}")
    return value


def require_credentials() -> None:
    required_env("B2_APPLICATION_KEY_ID")
    required_env("B2_APPLICATION_KEY")


def subprocess_env(*, b2: bool) -> dict[str, str]:
    env = os.environ.copy()
    if b2:
        env.pop("AGE_RECIPIENT", None)
        env.pop("GEOVIS_BACKUP_ALERT_URL", None)
    else:
        env.pop("B2_APPLICATION_KEY_ID", None)
        env.pop("B2_APPLICATION_KEY", None)
        env.pop("GEOVIS_BACKUP_ALERT_URL", None)
    return env


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def retry(
    operation: Callable[[], subprocess.CompletedProcess[str]],
    *,
    attempts: int,
    base_seconds: float,
) -> subprocess.CompletedProcess[str]:
    last_error: subprocess.CalledProcessError | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except subprocess.CalledProcessError as error:
            last_error = error
            if attempt == attempts:
                break
            time.sleep(base_seconds * (2 ** (attempt - 1)))
    assert last_error is not None
    raise BackupError(f"remote operation failed after {attempts} attempts") from last_error


def run_b2(config: Config, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = subprocess_env(b2=True)
    env["B2_ACCOUNT_INFO"] = os.getenv(
        "B2_ACCOUNT_INFO", "/run/geovis-offhost/b2-account-info"
    )
    return retry(
        lambda: subprocess.run(
            ["b2", *arguments],
            check=True,
            text=True,
            capture_output=True,
            env=env,
        ),
        attempts=config.retries,
        base_seconds=config.retry_base_seconds,
    )


def parse_account_allowed(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise BackupError("B2 account response was not an object")
    allowed = payload.get("allowed")
    if not isinstance(allowed, dict):
        account_info = payload.get("accountInfo")
        if isinstance(account_info, dict):
            allowed = account_info.get("allowed")
    if not isinstance(allowed, dict):
        api_info = payload.get("apiInfo")
        storage_api = api_info.get("storageApi") if isinstance(api_info, dict) else None
        if isinstance(storage_api, dict):
            allowed = storage_api.get("allowed")
    if not isinstance(allowed, dict):
        raise BackupError("B2 account response did not include allowed restrictions")
    return allowed


def validate_least_privilege(
    allowed: dict[str, object], config: Config, *, recovery: bool
) -> None:
    capabilities = set(allowed.get("capabilities") or [])
    required = RECOVERY_CAPABILITIES if recovery else REPLICATION_CAPABILITIES
    missing = required - capabilities
    excessive = capabilities - required
    if missing:
        raise BackupError(f"B2 key lacks required capabilities: {sorted(missing)}")
    if excessive:
        raise BackupError(f"B2 key has capabilities beyond least privilege: {sorted(excessive)}")
    bucket_names: set[str] = set()
    if isinstance(allowed.get("bucketName"), str):
        bucket_names.add(str(allowed["bucketName"]))
    buckets = allowed.get("buckets")
    if isinstance(buckets, list):
        for bucket in buckets:
            if isinstance(bucket, dict):
                name = bucket.get("name", bucket.get("bucketName"))
                if isinstance(name, str):
                    bucket_names.add(name)
            elif isinstance(bucket, str):
                bucket_names.add(bucket)
    if bucket_names and bucket_names != {config.bucket}:
        raise BackupError("B2 key is not restricted to only the configured bucket")
    if not allowed.get("bucketId") and not bucket_names and not buckets:
        raise BackupError("B2 key is not restricted to the configured bucket")
    name_prefix = allowed.get("namePrefix")
    expected = config.prefix.rstrip("/") + "/"
    if name_prefix != expected:
        raise BackupError("B2 key must be restricted to the configured object prefix")


def preflight(config: Config, *, recovery: bool) -> None:
    require_credentials()
    required_tools = ["b2", "age"] if recovery else ["b2", "age", "tar"]
    missing = [tool for tool in required_tools if shutil.which(tool) is None]
    if missing:
        raise BackupError(f"required executables are missing: {', '.join(missing)}")
    account = run_b2(config, "account", "get")
    validate_least_privilege(
        parse_account_allowed(json.loads(account.stdout)), config, recovery=recovery
    )


def parse_checksum_file(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([^/]+)", line)
        if not match:
            raise BackupError(f"invalid checksum line in {path.name}")
        checksums[match.group(2)] = match.group(1)
    return checksums


def validate_backup_set(backup_dir: Path) -> dict[str, object]:
    backup_dir = backup_dir.resolve()
    if not backup_dir.is_dir() or not BACKUP_NAME.fullmatch(backup_dir.name):
        raise BackupError("backup directory must be named production-drill-<UTC timestamp>")
    missing = sorted(name for name in REQUIRED_BACKUP_FILES if not (backup_dir / name).is_file())
    if missing:
        raise BackupError(f"backup set is incomplete: {missing}")
    result = dict(
        line.split("=", 1)
        for line in (backup_dir / "result.txt").read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    required_results = {
        "status": "pass",
        "database_fingerprint_match": "true",
        "output_manifest_match": "true",
        "isolated_api_validation": "true",
        "backup_checksums_pass": "true",
    }
    for key, expected in required_results.items():
        if result.get(key) != expected:
            raise BackupError(f"backup result does not prove {key}={expected}")
    for name, expected in parse_checksum_file(backup_dir / "checksums.sha256").items():
        target = backup_dir / name
        if not target.is_file() or sha256(target) != expected:
            raise BackupError(f"backup payload checksum failed: {name}")
    content = json.loads((backup_dir / "restored-content-validation.json").read_text())
    api = json.loads((backup_dir / "restored-api-validation.json").read_text())
    positive_fields = {
        "project_records": content,
        "run_records": content,
        "report_files": content,
        "artifact_files": content,
        "projects_verified": api,
        "runs_verified": api,
        "artifact_downloads_verified": api,
        "report_or_metadata_downloads_verified": api,
    }
    for field, source in positive_fields.items():
        if not isinstance(source.get(field), int) or source[field] <= 0:
            raise BackupError(f"backup validation does not cover {field}")
    if content.get("missing_output_references") or content.get("orphan_runs"):
        raise BackupError("backup validation contains broken metadata relationships")
    return {"backup": backup_dir.name, **{field: source[field] for field, source in positive_fields.items()}}


def encrypt_backup(backup_dir: Path, destination: Path, recipient: str) -> None:
    tar_process = subprocess.Popen(
        ["tar", "-C", str(backup_dir.parent), "-cf", "-", backup_dir.name],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=subprocess_env(b2=False),
    )
    assert tar_process.stdout is not None
    age = subprocess.run(
        ["age", "--encrypt", "--recipient", recipient, "--output", str(destination)],
        stdin=tar_process.stdout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=False,
        env=subprocess_env(b2=False),
    )
    tar_process.stdout.close()
    tar_stderr = tar_process.stderr.read() if tar_process.stderr else b""
    tar_status = tar_process.wait()
    if age.returncode or tar_status:
        destination.unlink(missing_ok=True)
        raise BackupError(
            "backup encryption failed" if age.returncode else f"backup archive failed: {tar_stderr.decode(errors='replace')}"
        )


def object_uri(config: Config, key: str) -> str:
    return f"b2://{config.bucket}/{key}"


def upload_and_verify(config: Config, encrypted: Path, checksum: Path, key: str) -> None:
    run_b2(config, "file", "upload", "--no-progress", config.bucket, str(encrypted), key)
    run_b2(
        config,
        "file",
        "upload",
        "--no-progress",
        config.bucket,
        str(checksum),
        key + ".sha256",
    )
    with tempfile.TemporaryDirectory(prefix="geovis-b2-verify-") as temp:
        downloaded = Path(temp) / encrypted.name
        downloaded_checksum = Path(temp) / checksum.name
        run_b2(config, "file", "download", "--no-progress", object_uri(config, key), str(downloaded))
        run_b2(
            config,
            "file",
            "download",
            "--no-progress",
            object_uri(config, key + ".sha256"),
            str(downloaded_checksum),
        )
        expected = downloaded_checksum.read_text(encoding="ascii").split()[0]
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or sha256(downloaded) != expected:
            raise BackupError("downloaded ciphertext failed SHA-256 verification")


def list_objects(config: Config) -> list[dict[str, object]]:
    response = run_b2(
        config,
        "ls",
        "--json",
        "--recursive",
        "--versions",
        object_uri(config, config.prefix + "/"),
    )
    payload = json.loads(response.stdout)
    if isinstance(payload, dict):
        payload = payload.get("files", [])
    if not isinstance(payload, list):
        raise BackupError("B2 listing response was not a list")
    return [item for item in payload if isinstance(item, dict)]


def object_field(item: dict[str, object], *names: str) -> object | None:
    for name in names:
        if name in item:
            return item[name]
    return None


def parse_retention_inventory(
    config: Config,
    objects: Iterable[dict[str, object]],
    *,
    allowed_incomplete: str | None = None,
) -> dict[str, dict[str, dict[str, str] | datetime | None]]:
    """Return exact, single-version backup pairs or reject unsafe inventory."""
    expected_parent = config.prefix.rstrip("/") + "/"
    versions: dict[str, list[dict[str, str]]] = {}
    for item in objects:
        name_value = object_field(item, "fileName", "file_name")
        file_id_value = object_field(item, "fileId", "file_id")
        action_value = object_field(item, "action")
        if not isinstance(name_value, str) or not isinstance(file_id_value, str):
            raise BackupError("B2 inventory entry is missing its name or version ID")
        if not name_value.startswith(expected_parent):
            raise BackupError("B2 inventory escaped the configured bucket prefix")
        relative = name_value.removeprefix(expected_parent)
        if not relative:
            raise BackupError("B2 retention prefix contains an empty object name")
        if "/" in relative:
            # B2 recursively lists child prefixes. A production retention run
            # must leave an isolated canary beneath that prefix untouched.
            continue
        if action_value != "upload":
            raise BackupError(f"B2 object has an unsupported version action: {relative}")
        versions.setdefault(name_value, []).append(
            {"name": name_value, "file_id": file_id_value}
        )

    for name, object_versions in versions.items():
        if len(object_versions) != 1:
            raise BackupError(f"B2 object has multiple versions and requires review: {name}")

    pairs: dict[str, dict[str, dict[str, str] | datetime | None]] = {}
    for name, object_versions in versions.items():
        if name.endswith(".tar.age.sha256"):
            ciphertext_name = name[: -len(".sha256")]
            component = "checksum"
        elif name.endswith(".tar.age"):
            ciphertext_name = name
            component = "ciphertext"
        else:
            raise BackupError(f"unexpected object in retention prefix: {name}")
        match = OBJECT_NAME.fullmatch(ciphertext_name)
        if not match:
            raise BackupError(f"unexpected backup object name: {name}")
        stamp = datetime.strptime(match.group(2), "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc
        )
        pair = pairs.setdefault(
            ciphertext_name,
            {"timestamp": stamp, "ciphertext": None, "checksum": None},
        )
        pair[component] = object_versions[0]

    incomplete = [
        name
        for name, pair in pairs.items()
        if pair["ciphertext"] is None or pair["checksum"] is None
    ]
    unexpected = [name for name in incomplete if name != allowed_incomplete]
    if unexpected:
        raise BackupError(
            "unexpected incomplete backup pair blocks retention: "
            + ", ".join(sorted(unexpected))
        )
    if allowed_incomplete is not None and any(
        name != allowed_incomplete for name in incomplete
    ):
        raise BackupError("an unrelated incomplete pair blocks retention recovery")
    return pairs


def eligible_pair_names(
    pairs: dict[str, dict[str, dict[str, str] | datetime | None]],
    *,
    now: datetime,
    days: int,
    minimum: int,
) -> list[str]:
    future = [
        name
        for name, pair in pairs.items()
        if pair["timestamp"] > now + timedelta(minutes=5)
    ]
    if future:
        raise BackupError("retention inventory has a future-dated backup: " + ", ".join(sorted(future)))
    ordered = sorted(
        pairs,
        key=lambda name: pairs[name]["timestamp"],
        reverse=True,
    )
    protected = set(ordered[:minimum])
    cutoff = now - timedelta(days=days)
    return [
        name
        for name in reversed(ordered)
        if name not in protected and pairs[name]["timestamp"] < cutoff
    ]


def retention_deletions(
    object_names: Iterable[str], *, now: datetime, days: int, minimum: int
) -> list[str]:
    """Select names for local disposable-fixture preparation."""
    stamps: dict[datetime, str] = {}
    for name in object_names:
        match = OBJECT_NAME.fullmatch(name)
        if match:
            stamp = datetime.strptime(match.group(2), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            if stamp > now + timedelta(minutes=5):
                raise BackupError(f"retention inventory has a future-dated backup: {name}")
            stamps[stamp] = name
    newest = set(sorted(stamps, reverse=True)[:minimum])
    cutoff = now - timedelta(days=days)
    return [stamps[stamp] for stamp in sorted(stamps) if stamp < cutoff and stamp not in newest]


def inventory_version_map(
    pairs: dict[str, dict[str, dict[str, str] | datetime | None]],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for pair in pairs.values():
        for component in ("ciphertext", "checksum"):
            version = pair[component]
            if isinstance(version, dict):
                result[version["file_id"]] = version["name"]
    return result


def write_retention_record(
    config: Config,
    record: dict[str, object],
    *,
    existing: Path | None = None,
) -> Path:
    configured_state_dir = config.retention_state_dir
    if not configured_state_dir.is_absolute() or (
        configured_state_dir.exists() and configured_state_dir.is_symlink()
    ):
        raise BackupError("retention state directory must be an absolute non-symlink path")
    state_dir = configured_state_dir.resolve()
    created_directories: list[Path] = []
    ancestor = state_dir
    while not ancestor.exists():
        created_directories.append(ancestor)
        ancestor = ancestor.parent
    state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    for created in reversed(created_directories):
        parent_descriptor = os.open(created.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    if state_dir.stat().st_uid != os.geteuid():
        raise BackupError("retention state directory must be owned by the operator")
    state_dir.chmod(0o700)
    if existing is not None:
        destination = existing.resolve()
        if destination.parent != state_dir or not destination.is_file():
            raise BackupError("recovery record is outside the configured state directory")
    else:
        pair_name = Path(str(record["pair_name"])).name
        scope = hashlib.sha256(f"{config.bucket}/{config.prefix}".encode()).hexdigest()[:12]
        destination = state_dir / f"retention-{scope}-{pair_name}.json"
        if destination.exists():
            raise BackupError("retention recovery record already exists; review it before another apply")
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        directory_descriptor = os.open(state_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def load_retention_record(config: Config, path: Path) -> dict[str, object]:
    resolved = path.resolve()
    if resolved.parent != config.retention_state_dir.resolve():
        raise BackupError("recovery record is outside the configured state directory")
    if not resolved.is_file() or stat.S_IMODE(resolved.stat().st_mode) & 0o077:
        raise BackupError("recovery record must exist with mode 0600 or stricter")
    if resolved.stat().st_uid != os.geteuid():
        raise BackupError("recovery record must be owned by the operator")
    record = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or record.get("schema_version") != 1:
        raise BackupError("invalid retention recovery record")
    if record.get("bucket") != config.bucket or record.get("prefix") != config.prefix:
        raise BackupError("recovery record bucket or prefix does not match configuration")
    return record


def reject_pending_retention_records(config: Config) -> None:
    state_dir = config.retention_state_dir
    if not state_dir.exists():
        return
    if state_dir.is_symlink() or not state_dir.is_dir():
        raise BackupError("retention state directory is unsafe")
    for path in state_dir.glob("retention-*.json"):
        if path.is_symlink() or not path.is_file():
            raise BackupError("retention state directory contains an unsafe record")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise BackupError("retention state directory contains an unreadable record") from error
        if not isinstance(record, dict):
            raise BackupError("retention state directory contains an invalid record")
        if (
            record.get("bucket") == config.bucket
            and record.get("prefix") == config.prefix
            and record.get("status") != "complete"
        ):
            raise BackupError(f"pending retention recovery blocks unrelated deletion: {path}")


def verify_protected_versions(
    current: dict[str, str], protected: dict[str, str]
) -> None:
    changed = {
        file_id: name
        for file_id, name in protected.items()
        if current.get(file_id) != name
    }
    if changed:
        raise BackupError("post-deletion inventory lost or changed protected objects")


def delete_version(config: Config, version: dict[str, str]) -> tuple[bool, str | None]:
    try:
        run_b2(
            config,
            "rm",
            "--no-progress",
            "--fail-fast",
            f"b2id://{version['file_id']}",
        )
        return True, None
    except (BackupError, OSError, subprocess.SubprocessError) as error:
        return False, str(error)


def execute_pair_deletion(
    config: Config,
    pair_name: str,
    expected_pair: dict[str, dict[str, str] | datetime | None],
    protected: dict[str, str],
    *,
    recovery_path: Path | None = None,
    skip_absent: set[str] | None = None,
) -> dict[str, object]:
    skip_absent = skip_absent or set()
    prior_record = load_retention_record(config, recovery_path) if recovery_path else None
    results: dict[str, dict[str, object]] = {}
    for component in ("ciphertext", "checksum"):
        version = expected_pair[component]
        assert isinstance(version, dict)
        results[component] = {
            "name": version["name"],
            "file_id": version["file_id"],
            "delete_command_succeeded": None,
            "error": None,
            "absent_after": False,
            "skipped_as_absent": component in skip_absent,
        }

    record: dict[str, object] = {
        "schema_version": 1,
        "bucket": config.bucket,
        "prefix": config.prefix,
        "pair_name": pair_name,
        "backup_timestamp": expected_pair["timestamp"].isoformat(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "retention_days": config.retention_days,
        "retention_minimum": config.retention_minimum,
        "components": results,
        "protected_versions": protected,
        "status": "prepared",
        "attempt_history": (
            [*prior_record.get("attempt_history", []), {
                "checked_at": prior_record.get("checked_at"),
                "status": prior_record.get("status"),
                "components": prior_record.get("components"),
            }]
            if prior_record else []
        ),
    }
    record_path = write_retention_record(config, record, existing=recovery_path)
    for component in ("ciphertext", "checksum"):
        if component in skip_absent:
            continue
        version = expected_pair[component]
        assert isinstance(version, dict)
        command_succeeded, error = delete_version(config, version)
        results[component]["delete_command_succeeded"] = command_succeeded
        results[component]["error"] = error
        record["status"] = "deletion_in_progress"
        record["checked_at"] = datetime.now(timezone.utc).isoformat()
        write_retention_record(config, record, existing=record_path)
        if not command_succeeded:
            break

    try:
        final_pairs = parse_retention_inventory(
            config,
            list_objects(config),
            allowed_incomplete=pair_name,
        )
        final_versions = inventory_version_map(final_pairs)
        verify_protected_versions(final_versions, protected)
        present_names = set(final_versions.values())
        for component in ("ciphertext", "checksum"):
            file_id = str(results[component]["file_id"])
            name = str(results[component]["name"])
            results[component]["absent_after"] = (
                file_id not in final_versions and name not in present_names
            )
    except Exception as error:
        record["status"] = "inventory_verification_failed"
        record["verification_error"] = f"{type(error).__name__}: {error}"
        path = write_retention_record(config, record, existing=record_path)
        raise RetentionRecoveryRequired(
            f"retention inventory verification failed; recovery record: {path}"
        ) from error

    absent = [bool(results[name]["absent_after"]) for name in ("ciphertext", "checksum")]
    if all(absent):
        record["status"] = "complete"
        record["recovery_record"] = str(record_path)
        write_retention_record(config, record, existing=record_path)
        return record
    record["status"] = "partial" if any(absent) else "failed"
    path = write_retention_record(config, record, existing=record_path)
    raise RetentionRecoveryRequired(
        f"two-object deletion is {record['status']}; retry only with recovery record: {path}"
    )


def revalidate_pair_for_deletion(
    config: Config,
    pair_name: str,
    expected_ids: set[str],
    *,
    allowed_incomplete: str | None = None,
) -> tuple[
    dict[str, dict[str, str] | datetime | None],
    dict[str, str],
]:
    preflight(config, recovery=False)
    pairs = parse_retention_inventory(
        config,
        list_objects(config),
        allowed_incomplete=allowed_incomplete,
    )
    if pair_name not in pairs and allowed_incomplete == pair_name:
        match = OBJECT_NAME.fullmatch(pair_name)
        if not match:
            raise BackupError("recovery record has an invalid pair name")
        pairs[pair_name] = {
            "timestamp": datetime.strptime(
                match.group(2), "%Y%m%dT%H%M%SZ"
            ).replace(tzinfo=timezone.utc),
            "ciphertext": None,
            "checksum": None,
        }
    eligible = eligible_pair_names(
        pairs,
        now=datetime.now(timezone.utc),
        days=config.retention_days,
        minimum=config.retention_minimum,
    )
    if pair_name not in eligible:
        raise BackupError("backup pair is no longer eligible after immediate revalidation")
    pair = pairs[pair_name]
    current_ids = {
        version["file_id"]
        for component in ("ciphertext", "checksum")
        if isinstance((version := pair[component]), dict)
    }
    if not current_ids.issubset(expected_ids) or (
        not current_ids and allowed_incomplete != pair_name
    ):
        raise BackupError("backup object versions changed before deletion")
    all_versions = inventory_version_map(pairs)
    protected = {
        file_id: name
        for file_id, name in all_versions.items()
        if file_id not in expected_ids
    }
    return pair, protected


def retry_retention(config: Config, recovery_file: Path) -> dict[str, object]:
    record = load_retention_record(config, recovery_file)
    if (
        record.get("retention_days") != config.retention_days
        or record.get("retention_minimum") != config.retention_minimum
    ):
        raise BackupError("retention policy changed since the recovery record was written")
    pair_name = str(record["pair_name"])
    components = record.get("components")
    parent = config.prefix.rstrip("/") + "/"
    if not pair_name.startswith(parent) or "/" in pair_name.removeprefix(parent) or not OBJECT_NAME.fullmatch(pair_name):
        raise BackupError("recovery record has an invalid pair name or prefix")
    if not isinstance(components, dict) or set(components) != {"ciphertext", "checksum"}:
        raise BackupError("recovery record must contain exactly two components")
    expected_ids: set[str] = set()
    for component_name, expected_name in (
        ("ciphertext", pair_name),
        ("checksum", pair_name + ".sha256"),
    ):
        component = components[component_name]
        if (
            not isinstance(component, dict)
            or component.get("name") != expected_name
            or not isinstance(component.get("file_id"), str)
            or not component["file_id"]
        ):
            raise BackupError("recovery record component name or version ID is invalid")
        expected_ids.add(component["file_id"])
    if len(expected_ids) != 2:
        raise BackupError("recovery record repeats a version ID")
    recorded_protected = record.get("protected_versions")
    if (
        not isinstance(recorded_protected, dict)
        or any(not isinstance(key, str) or not isinstance(value, str) for key, value in recorded_protected.items())
        or expected_ids & set(recorded_protected)
    ):
        raise BackupError("recovery record has no protected inventory")
    if record.get("status") == "complete":
        preflight(config, recovery=False)
        final_pairs = parse_retention_inventory(config, list_objects(config))
        final_versions = inventory_version_map(final_pairs)
        verify_protected_versions(final_versions, recorded_protected)
        present_names = set(final_versions.values())
        if any(
            component["file_id"] in final_versions or component["name"] in present_names
            for component in components.values()
        ):
            raise BackupError("completed retention target versions changed or reappeared")
        return record
    pair, current_protected = revalidate_pair_for_deletion(
        config,
        pair_name,
        expected_ids,
        allowed_incomplete=pair_name,
    )
    verify_protected_versions(current_protected, recorded_protected)
    skip_absent = {
        component for component in ("ciphertext", "checksum") if pair[component] is None
    }
    for component in ("ciphertext", "checksum"):
        if pair[component] is None:
            saved = components.get(component)
            if not isinstance(saved, dict):
                raise BackupError("recovery record component is invalid")
            pair[component] = {
                "name": str(saved["name"]),
                "file_id": str(saved["file_id"]),
            }
    return execute_pair_deletion(
        config,
        pair_name,
        pair,
        current_protected,
        recovery_path=recovery_file,
        skip_absent=skip_absent,
    )


def apply_retention(
    config: Config,
    *,
    dry_run: bool,
    recovery_file: Path | None = None,
) -> dict[str, object]:
    if recovery_file is not None:
        if dry_run:
            raise BackupError("a recovery retry requires --apply")
        return retry_retention(config, recovery_file)
    pairs = parse_retention_inventory(config, list_objects(config))
    candidates = eligible_pair_names(
        pairs,
        now=datetime.now(timezone.utc),
        days=config.retention_days,
        minimum=config.retention_minimum,
    )
    if dry_run:
        return {
            "status": "preview",
            "bucket": config.bucket,
            "prefix": config.prefix,
            "candidates": candidates,
        }
    reject_pending_retention_records(config)
    completed: list[dict[str, object]] = []
    for pair_name in candidates:
        planned_pair = pairs[pair_name]
        expected_ids = {
            version["file_id"]
            for component in ("ciphertext", "checksum")
            if isinstance((version := planned_pair[component]), dict)
        }
        current_pair, protected = revalidate_pair_for_deletion(
            config, pair_name, expected_ids
        )
        completed.append(
            execute_pair_deletion(
                config,
                pair_name,
                current_pair,
                protected,
            )
        )
    return {
        "status": "complete",
        "bucket": config.bucket,
        "prefix": config.prefix,
        "deleted_pairs": completed,
    }


def send_alert(config: Config, message: str) -> None:
    if not config.alert_url:
        raise BackupError("GEOVIS_BACKUP_ALERT_URL is not configured")
    payload = json.dumps({"service": "GeoVisLM off-host backup", "status": "failure", "message": message}).encode()
    last_error: Exception | None = None
    for attempt in range(1, config.retries + 1):
        try:
            request = Request(config.alert_url, data=payload, headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=15) as response:
                if not 200 <= response.status < 300:
                    raise BackupError(f"alert endpoint returned HTTP {response.status}")
            return
        except Exception as error:  # noqa: BLE001 - retry any transport failure
            last_error = error
            if attempt < config.retries:
                time.sleep(config.retry_base_seconds * (2 ** (attempt - 1)))
    raise BackupError("alert delivery failed") from last_error


def safe_extract_stream(stream, destination: Path) -> Path:
    destination.mkdir(parents=True, mode=0o700, exist_ok=False)
    root_name: str | None = None
    try:
        with tarfile.open(fileobj=stream, mode="r|") as archive:
            for member in archive:
                path = Path(member.name)
                if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                    raise BackupError("decrypted archive contains an unsafe member")
                if root_name is None:
                    root_name = path.parts[0]
                if not path.parts or path.parts[0] != root_name:
                    raise BackupError("decrypted archive has multiple roots")
                archive.extract(member, destination, filter="data")
        if not root_name:
            raise BackupError("decrypted archive is empty")
        extracted = destination / root_name
        validate_backup_set(extracted)
        return extracted
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def fetch_and_decrypt(config: Config, key: str, identity: Path, destination: Path) -> Path:
    expected_prefix = config.prefix.rstrip("/") + "/"
    relative_key = key.removeprefix(expected_prefix)
    if not key.startswith(expected_prefix) or "/" in relative_key or not OBJECT_NAME.fullmatch(key):
        raise BackupError("object key is outside the configured backup prefix")
    if not identity.is_file() or stat.S_IMODE(identity.stat().st_mode) & 0o077:
        raise BackupError("age identity must exist with mode 0600 or stricter")
    if identity.stat().st_uid != os.geteuid():
        raise BackupError("age identity must be owned by the recovery operator")
    if str(identity.resolve()).startswith("/root/geovis-backups/"):
        raise BackupError("age identity must not be stored beside Prime backup payloads")
    with tempfile.TemporaryDirectory(prefix="geovis-b2-restore-") as temp:
        encrypted = Path(temp) / "backup.tar.age"
        checksum = Path(temp) / "backup.tar.age.sha256"
        run_b2(config, "file", "download", "--no-progress", object_uri(config, key), str(encrypted))
        run_b2(config, "file", "download", "--no-progress", object_uri(config, key + ".sha256"), str(checksum))
        expected = checksum.read_text(encoding="ascii").split()[0]
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or sha256(encrypted) != expected:
            raise BackupError("off-host ciphertext failed SHA-256 verification")
        age = subprocess.Popen(
            ["age", "--decrypt", "--identity", str(identity), str(encrypted)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=subprocess_env(b2=False),
        )
        assert age.stdout is not None
        extraction_error: Exception | None = None
        extracted: Path | None = None
        try:
            extracted = safe_extract_stream(age.stdout, destination)
        except Exception as error:  # ensure the decryptor is always reaped
            extraction_error = error
        age.stdout.close()
        stderr = age.stderr.read() if age.stderr else b""
        if age.wait() != 0:
            raise BackupError(f"age decryption failed: {stderr.decode(errors='replace')}")
        if extraction_error is not None:
            raise extraction_error
        assert extracted is not None
        return extracted


def replicate(backup_dir: Path) -> dict[str, object]:
    config = Config.from_env(need_recipient=True, need_alert=True)
    try:
        preflight(config, recovery=False)
        coverage = validate_backup_set(backup_dir)
        with tempfile.TemporaryDirectory(prefix="geovis-offhost-") as temp:
            encrypted = Path(temp) / f"{backup_dir.name}.tar.age"
            assert config.recipient is not None
            encrypt_backup(backup_dir.resolve(), encrypted, config.recipient)
            digest = sha256(encrypted)
            checksum = encrypted.with_suffix(encrypted.suffix + ".sha256")
            checksum.write_text(f"{digest}  {encrypted.name}\n", encoding="ascii")
            key = f"{config.prefix}/{encrypted.name}"
            upload_and_verify(config, encrypted, checksum, key)
        retention_result = apply_retention(config, dry_run=False)
        return {"status": "pass", "object_key": key, "ciphertext_sha256": digest, "coverage": coverage, "retention_result": retention_result}
    except Exception as error:
        try:
            send_alert(config, f"replication failed: {type(error).__name__}")
        except Exception:
            pass
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    replicate_parser = subparsers.add_parser("replicate")
    replicate_parser.add_argument("--backup-dir", required=True, type=Path)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("backup_dir", type=Path)
    prune = subparsers.add_parser("retention")
    prune.add_argument("--apply", action="store_true")
    prune.add_argument("--recovery-file", type=Path)
    alert = subparsers.add_parser("alert-test")
    alert.add_argument("--message", default="operator-requested alert delivery test")
    fetch = subparsers.add_parser("fetch")
    fetch.add_argument("--object-key", required=True)
    fetch.add_argument("--identity-file", required=True, type=Path)
    fetch.add_argument("--destination", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "validate":
            result = validate_backup_set(args.backup_dir)
        elif args.command == "replicate":
            result = replicate(args.backup_dir)
        elif args.command == "retention":
            config = Config.from_env(need_recipient=False, need_alert=False)
            preflight(config, recovery=False)
            result = apply_retention(
                config,
                dry_run=not args.apply,
                recovery_file=args.recovery_file,
            )
        elif args.command == "alert-test":
            config = Config.from_env(need_recipient=False, need_alert=True)
            send_alert(config, args.message)
            result = {"status": "delivered"}
        else:
            config = Config.from_env(need_recipient=False, need_alert=False)
            preflight(config, recovery=True)
            extracted = fetch_and_decrypt(config, args.object_key, args.identity_file, args.destination)
            result = {"status": "pass", "extracted_backup": str(extracted)}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (BackupError, OSError, ValueError, json.JSONDecodeError, tarfile.TarError) as error:
        print(f"off-host backup error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
