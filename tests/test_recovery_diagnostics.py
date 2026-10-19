import json
from pathlib import Path

from scripts import recovery_diagnostics as diagnostics


def test_capture_preserves_daemon_failure_without_masking_restore_error(tmp_path: Path, monkeypatch):
    def unavailable(*args: str):
        if args[0] == "logs":
            return {"error": "timeout", "detail": "Docker Desktop unavailable"}
        return {"error": "timeout", "detail": "Docker Desktop unavailable"}

    monkeypatch.setattr(diagnostics, "docker_command", unavailable)
    diagnostics.capture_failure(tmp_path, "db", "app", 1, "database fingerprint: public.spatial_ref_sys")

    state = json.loads((tmp_path / "container-state.json").read_text())
    assert state["stage"] == "database fingerprint: public.spatial_ref_sys"
    assert state["database_container"]["error"] == "timeout"
    assert state["docker_server"]["error"] == "timeout"
    assert (tmp_path / "postgresql.log").exists()
    assert (tmp_path / "container-state.json").stat().st_mode & 0o777 == 0o600


def test_capture_preserves_stopped_postgres_state_and_logs(tmp_path: Path, monkeypatch):
    def stopped(*args: str):
        if args[0] == "logs":
            return {"exit_code": 0, "stdout": "database system is shut down\n", "stderr": ""}
        if args[0] == "inspect":
            return {"exit_code": 0, "stdout": '{"Running":false,"ExitCode":137}', "stderr": ""}
        return {"exit_code": 0, "stdout": '{"Version":"test"}', "stderr": ""}

    monkeypatch.setattr(diagnostics, "docker_command", stopped)
    diagnostics.capture_failure(tmp_path, "db", "app", 1, "database fingerprint: public.spatial_ref_sys")

    assert "database system is shut down" in (tmp_path / "postgresql.log").read_text()
    state = json.loads((tmp_path / "container-state.json").read_text())
    assert '"Running":false' in state["database_container"]["stdout"]
    assert '"ExitCode":137' in state["database_container"]["stdout"]


def test_cleanup_must_be_provably_complete(tmp_path: Path, monkeypatch):
    def remaining(*args: str):
        if args[:2] == ("container", "ls"):
            return {"exit_code": 0, "stdout": "db\n", "stderr": ""}
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(diagnostics, "docker_command", remaining)
    assert diagnostics.verify_cleanup(tmp_path, ("db", "app"), ("db-volume", "output-volume")) is False
    evidence = json.loads((tmp_path / "scratch-cleanup.json").read_text())
    assert evidence["remaining_containers"] == ["db"]
    assert evidence["verified"] is False


def test_cleanup_fails_closed_when_docker_is_unreachable(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        diagnostics, "docker_command", lambda *_args: {"error": "timeout", "detail": "daemon unavailable"}
    )
    assert diagnostics.verify_cleanup(tmp_path, ("db", "app"), ("db-volume", "output-volume")) is False
    assert json.loads((tmp_path / "scratch-cleanup.json").read_text())["verified"] is False
