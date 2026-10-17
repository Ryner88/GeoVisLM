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
    response = run_b2(config, "ls", "--json", "--recursive", object_uri(config, config.prefix + "/"))
    payload = json.loads(response.stdout)
    if isinstance(payload, dict):
        payload = payload.get("files", [])
    if not isinstance(payload, list):
        raise BackupError("B2 listing response was not a list")
    return [item for item in payload if isinstance(item, dict)]


def retention_deletions(
    object_names: Iterable[str], *, now: datetime, days: int, minimum: int
) -> list[str]:
    sets: dict[datetime, str] = {}
    for name in object_names:
        match = OBJECT_NAME.fullmatch(name)
        if match:
            stamp = datetime.strptime(match.group(2), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            sets[stamp] = name
    newest = set(sorted(sets, reverse=True)[:minimum])
    cutoff = now - timedelta(days=days)
    return [sets[stamp] for stamp in sorted(sets) if stamp < cutoff and stamp not in newest]


def apply_retention(config: Config, *, dry_run: bool) -> list[str]:
    objects = list_objects(config)
    names = []
    expected_parent = config.prefix.rstrip("/") + "/"
    for item in objects:
        name = str(item.get("fileName", item.get("file_name", "")))
        relative = name.removeprefix(expected_parent)
        if name.startswith(expected_parent) and "/" not in relative:
            names.append(name)
    deletions = retention_deletions(
        names,
        now=datetime.now(timezone.utc),
        days=config.retention_days,
        minimum=config.retention_minimum,
    )
    if not dry_run:
        for name in deletions:
            run_b2(config, "rm", "--no-progress", object_uri(config, name))
            run_b2(config, "rm", "--no-progress", object_uri(config, name + ".sha256"))
    return deletions


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
        deleted = apply_retention(config, dry_run=False)
        return {"status": "pass", "object_key": key, "ciphertext_sha256": digest, "coverage": coverage, "retention_deleted": deleted}
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
            result = {"dry_run": not args.apply, "objects": apply_retention(config, dry_run=not args.apply)}
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
