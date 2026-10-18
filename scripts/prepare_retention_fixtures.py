#!/usr/bin/env python3
"""Build harmless age-encrypted retention canaries for isolated B2 testing."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

from offhost_backup import retention_deletions


def archive_bytes(label: str) -> bytes:
    content = f"Disposable GeoVisLM retention fixture: {label}\n".encode()
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        member = tarfile.TarInfo("fixture.txt")
        member.size = len(content)
        member.mode = 0o600
        archive.addfile(member, io.BytesIO(content))
    return stream.getvalue()


def prepare(destination: Path, prefix: str, recipient: str, now: datetime) -> dict[str, object]:
    if destination.exists():
        raise ValueError("fixture destination must not exist")
    if not recipient.startswith("age1"):
        raise ValueError("recipient must be a native age public key")
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    destination.mkdir(mode=0o700, parents=True)
    scenarios = {
        "cutoff": [
            now - timedelta(days=91),
            now - timedelta(days=89),
            now - timedelta(days=80),
            now - timedelta(days=40),
            now - timedelta(days=2),
            now - timedelta(days=1),
        ],
        "minimum": [now - timedelta(days=180 - offset * 10) for offset in range(4)],
    }
    manifest: dict[str, object] = {"as_of": now.isoformat(), "disposable": True, "scenarios": {}}
    for scenario, timestamps in scenarios.items():
        directory = destination / scenario
        directory.mkdir(mode=0o700)
        scenario_prefix = f"{prefix.rstrip('/')}/{scenario}"
        names: list[str] = []
        files: dict[str, str] = {}
        for stamp in timestamps:
            filename = f"production-drill-{stamp:%Y%m%dT%H%M%SZ}.tar.age"
            key = f"{scenario_prefix}/{filename}"
            encrypted = subprocess.run(
                ["age", "--encrypt", "--recipient", recipient],
                input=archive_bytes(key),
                capture_output=True,
                check=True,
            ).stdout
            payload = directory / filename
            payload.write_bytes(encrypted)
            payload.chmod(0o600)
            digest = hashlib.sha256(encrypted).hexdigest()
            sidecar = directory / f"{filename}.sha256"
            sidecar.write_text(f"{digest}  {filename}\n", encoding="ascii")
            sidecar.chmod(0o600)
            names.append(key)
            files[filename] = digest
        expected = [names[0]]
        actual = retention_deletions(names, now=now, days=90, minimum=3)
        if actual != expected:
            raise ValueError(f"retention boundary mismatch for {scenario}: {actual}")
        manifest["scenarios"][scenario] = {
            "prefix": scenario_prefix,
            "expected_delete": expected,
            "expected_keep": names[1:],
            "payload_sha256": files,
        }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    manifest_path.chmod(0o600)
    return manifest


def prepare_single_canary(destination: Path, prefix: str, recipient: str, now: datetime) -> dict[str, object]:
    """Create ten direct-child pairs with exactly one expired candidate."""
    if destination.exists():
        raise ValueError("fixture destination must not exist")
    if not recipient.startswith("age1"):
        raise ValueError("recipient must be a native age public key")
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    destination.mkdir(mode=0o700, parents=True)
    prefix = prefix.rstrip("/")
    offsets = (91, 89, 80, 70, 60, 50, 40, 30, 2, 1)
    names: list[str] = []
    files: dict[str, str] = {}
    for days in offsets:
        stamp = now - timedelta(days=days)
        filename = f"production-drill-{stamp:%Y%m%dT%H%M%SZ}.tar.age"
        key = f"{prefix}/{filename}"
        encrypted = subprocess.run(
            ["age", "--encrypt", "--recipient", recipient],
            input=archive_bytes(key),
            capture_output=True,
            check=True,
        ).stdout
        payload = destination / filename
        payload.write_bytes(encrypted)
        payload.chmod(0o600)
        digest = hashlib.sha256(encrypted).hexdigest()
        sidecar = destination / f"{filename}.sha256"
        sidecar.write_text(f"{digest}  {filename}\n", encoding="ascii")
        sidecar.chmod(0o600)
        names.append(key)
        files[filename] = digest
    expected = [names[0]]
    actual = retention_deletions(names, now=now, days=90, minimum=3)
    if actual != expected:
        raise ValueError(f"retention boundary mismatch: {actual}")
    manifest: dict[str, object] = {
        "as_of": now.isoformat(),
        "disposable": True,
        "prefix": prefix,
        "expected_delete": expected,
        "expected_keep": names[1:],
        "payload_sha256": files,
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    manifest_path.chmod(0o600)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--single-canary", action="store_true")
    args = parser.parse_args()
    if args.single_canary:
        manifest = prepare_single_canary(args.destination, args.prefix, args.recipient, datetime.now(timezone.utc))
        print(json.dumps({"destination": str(args.destination), "prefix": manifest["prefix"]}, sort_keys=True))
    else:
        manifest = prepare(args.destination, args.prefix, args.recipient, datetime.now(timezone.utc))
        print(json.dumps({"destination": str(args.destination), "scenarios": list(manifest["scenarios"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
