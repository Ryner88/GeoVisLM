"""Check the isolated restore commands without B2 credentials or a Docker daemon."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/offhost_restore_drill.sh"
IMAGE_ID = "sha256:" + "b" * 64


@pytest.fixture
def restore_fixture(tmp_path: Path):
    backup = tmp_path / "production-drill-20261017T010203Z"
    backup.mkdir()
    (backup / "postgis.dump").write_bytes(b"database")
    (backup / "outputs.tar.gz").write_bytes(b"outputs")
    (backup / "production-db-before.tsv").write_text("extension|postgis|3.4\n")
    (backup / "production-outputs-before.tsv").write_text("digest\t1\t0644\tfile\n")
    (backup / "checksums.sha256").write_text(
        "".join(
            f"{hashlib.sha256((backup / name).read_bytes()).hexdigest()}  {name}\n"
            for name in ("postgis.dump", "outputs.tar.gz")
        )
    )
    deployment = tmp_path / "deployment"
    scripts = deployment / "scripts"
    scripts.mkdir(parents=True)
    fetch = scripts / "offhost_backup.py"
    fetch.write_text(
        f"#!{sys.executable}\n"
        "import json, os\n"
        "print(json.dumps({'extracted_backup': os.environ['FAKE_BACKUP_DIR']}))\n"
    )
    fetch.chmod(0o755)
    (scripts / "verify_recovery_image.py").write_text(
        "import json, os, sys\n"
        "if os.environ.get('FAIL_IMAGE') == '1': sys.exit(1)\n"
        f"print(json.dumps({{'image_id': '{IMAGE_ID}', 'production_commit': 'a' * 40}}))\n"
    )
    (scripts / "backup_restore_verify.py").write_text("# mounted into helper\n")
    (scripts / "backup_restore_api_verify.py").write_text("# mounted into app\n")
    shutil.copyfile(SCRIPT.with_name("recovery_diagnostics.py"), scripts / "recovery_diagnostics.py")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "args = sys.argv[1:]\n"
        "with Path(os.environ['DOCKER_LOG']).open('a') as log:\n"
        "    log.write(json.dumps(args) + '\\n')\n"
        "if args[:2] == ['volume', 'create']:\n"
        "    print(args[-1])\n"
        "elif args[:2] == ['container', 'ls'] or args[:2] == ['volume', 'ls']:\n"
        "    pass\n"
        "elif args[0] == 'logs':\n"
        "    if '--tail' in args:\n"
        "        count_file = Path(os.environ['DB_LOG_POLL_COUNT'])\n"
        "        count = int(count_file.read_text()) + 1 if count_file.exists() else 1\n"
        "        count_file.write_text(str(count))\n"
        "        print('PostgreSQL init process complete; ready for start up.' if count >= 3 else 'temporary server running')\n"
        "    else: print('PostgreSQL diagnostic log')\n"
        "elif args[0] == 'inspect':\n"
        "    print('{\"Running\": true, \"ExitCode\": 0}')\n"
        "elif args[0] == 'version':\n"
        "    print('{\"Version\": \"test\"}')\n"
        "elif args[0] == 'exec' and 'psql' in args:\n"
        "    if 'from pg_extension' in args[-1]: print('postgis|3.4')\n"
        "    elif 'from pg_tables' in args[-1] and os.environ.get('FAKE_SPATIAL_TABLE') == '1': print('public.spatial_ref_sys')\n"
        "    elif 'from public.spatial_ref_sys' in args[-1]:\n"
        "        if os.environ.get('FAIL_FINGERPRINT') == '1':\n"
        "            print('server closed the connection unexpectedly', file=sys.stderr)\n"
        "            sys.exit(1)\n"
        "        print('public.spatial_ref_sys|1|digest')\n"
        "elif args[0] == 'exec' and '/restore-api-verify.py' in args:\n"
        "    print('{}')\n"
        "elif args[0] == 'run' and 'tar' in args and os.environ.get('FAIL_TAR') == '1':\n"
        "    sys.exit(1)\n"
        "elif args[0] == 'run' and 'manifest' in args:\n"
        "    print('digest\\t1\\t0644\\tfile')\n"
        "elif args[0] == 'run' and 'validate' in args:\n"
        "    print('{}')\n"
    )
    docker.chmod(0o755)
    sleep = bin_dir / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n")
    sleep.chmod(0o755)
    log_path = tmp_path / "docker.jsonl"
    environment = os.environ.copy()
    environment.update(
        PATH=f"{bin_dir}:{environment['PATH']}",
        DOCKER_LOG=str(log_path),
        DB_LOG_POLL_COUNT=str(tmp_path / "db-log-polls"),
        FAKE_BACKUP_DIR=str(backup),
        DEPLOYMENT_ROOT=str(deployment),
        RECOVERY_ROOT=str(tmp_path / "recovery"),
        GEOVIS_RECOVERY_ENVIRONMENT="independent",
        RECOVERY_APP_IMAGE="geovis_lm_app:latest",
    )

    def run(**overrides: str):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--object-key", "geovislm/production/test.tar.age", "--identity-file", str(tmp_path / "identity")],
            env=environment | overrides,
            capture_output=True,
            text=True,
            timeout=15,
        )
        calls = [json.loads(line) for line in log_path.read_text().splitlines()] if log_path.exists() else []
        return result, calls

    return run, backup


def test_restore_uses_immutable_image_and_isolated_volume_helpers(restore_fixture):
    run, backup = restore_fixture
    result, calls = run()

    assert result.returncode == 0, result.stderr
    helpers = [call for call in calls if call[:2] == ["run", "--rm"]]
    assert len(helpers) == 3
    assert all("--network" in call and "none" in call and "--read-only" in call for call in helpers)
    assert all(IMAGE_ID in call for call in helpers)
    assert sum(any("target=/restore/outputs,readonly" in arg for arg in call) for call in helpers) == 2
    assert any(
        any(f"source={backup / 'outputs.tar.gz'},target=/restore/outputs.tar.gz,readonly" in arg for arg in call)
        for call in helpers
    )
    assert any(call[0] == "run" and "-d" in call and IMAGE_ID in call for call in calls)
    assert any("pg_restore" in call for call in calls)
    assert sum(call[0] == "logs" and "--tail" in call for call in calls) >= 3
    assert max(index for index, call in enumerate(calls) if call[0] == "logs" and "--tail" in call) < next(
        index for index, call in enumerate(calls) if "pg_restore" in call
    )
    assert any("/restore-api-verify.py" in call for call in calls)
    assert not any(call[:2] == ["volume", "inspect"] for call in calls)
    assert sum(call[:2] == ["volume", "rm"] for call in calls) == 2
    evidence = next((backup.parent / "recovery").glob("offhost-*/scratch-cleanup.json"))
    assert json.loads(evidence.read_text())["verified"] is True


def test_restore_failure_cleans_up_scratch_resources(restore_fixture):
    run, _ = restore_fixture
    result, calls = run(FAIL_TAR="1")

    assert result.returncode != 0
    assert sum(call[:2] == ["volume", "rm"] for call in calls) == 2
    assert sum(call[:2] == ["rm", "-f"] for call in calls) == 2


def test_checksum_failure_prevents_volume_creation(restore_fixture):
    run, backup = restore_fixture
    (backup / "outputs.tar.gz").write_bytes(b"changed")

    result, calls = run()

    assert result.returncode != 0
    assert not any(call[:2] == ["volume", "create"] for call in calls)


def test_unverified_image_prevents_volume_creation(restore_fixture):
    run, _ = restore_fixture

    result, calls = run(FAIL_IMAGE="1")

    assert result.returncode != 0
    assert not any(call[:2] == ["volume", "create"] for call in calls)


def test_spatial_fingerprint_failure_preserves_logs_and_state_before_cleanup(restore_fixture):
    run, backup = restore_fixture

    result, calls = run(FAKE_SPATIAL_TABLE="1", FAIL_FINGERPRINT="1")

    assert result.returncode != 0
    work_dir = next((backup.parent / "recovery").glob("offhost-*"))
    assert "public.spatial_ref_sys" in (work_dir / "fingerprint-queries.tsv").read_text()
    assert "fail\tpublic.spatial_ref_sys" in (work_dir / "fingerprint-queries.tsv").read_text()
    assert "server closed the connection" in (work_dir / "fingerprint-public.spatial_ref_sys.stderr").read_text()
    assert "PostgreSQL diagnostic log" in (work_dir / "postgresql.log").read_text()
    state = json.loads((work_dir / "container-state.json").read_text())
    assert state["stage"] == "database fingerprint: public.spatial_ref_sys"
    assert state["database_container"]["exit_code"] == 0
    assert json.loads((work_dir / "scratch-cleanup.json").read_text())["verified"] is True
    assert next(index for index, call in enumerate(calls) if call[0] == "logs") < next(
        index for index, call in enumerate(calls) if call[:2] == ["rm", "-f"]
    )
    assert not (work_dir / "result.txt").exists()
