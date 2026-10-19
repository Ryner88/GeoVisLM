from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

from scripts import offhost_backup


def test_single_canary_has_ten_direct_pairs_and_one_expired_candidate(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "offhost_backup", offhost_backup)
    path = Path(__file__).resolve().parents[1] / "scripts/prepare_retention_fixtures.py"
    spec = importlib.util.spec_from_file_location("prepare_retention_fixtures", path)
    assert spec and spec.loader
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    monkeypatch.setattr(
        fixtures.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=b"encrypted fixture"),
    )
    now = datetime(2026, 10, 18, 20, 0, tzinfo=timezone.utc)
    destination = tmp_path / "canary"
    prefix = "geovislm/production/retention-canary-test"
    manifest = fixtures.prepare_single_canary(destination, prefix, "age1test", now)

    assert manifest["prefix"] == prefix
    assert len(manifest["payload_sha256"]) == 10
    assert len(manifest["expected_delete"]) == 1
    assert len(manifest["expected_keep"]) == 9
    assert len(list(destination.glob("*.tar.age"))) == 10
    assert len(list(destination.glob("*.tar.age.sha256"))) == 10
    assert not any(path.is_dir() for path in destination.iterdir())
    assert manifest["expected_delete"] == offhost_backup.retention_deletions(
        [f"{prefix}/{name}" for name in manifest["payload_sha256"]],
        now=now,
        days=90,
        minimum=3,
    )
    newest_three = sorted(manifest["expected_keep"])[-3:]
    assert all(name not in manifest["expected_delete"] for name in newest_three)
