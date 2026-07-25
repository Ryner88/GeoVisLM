from __future__ import annotations

import asyncio
import importlib
import subprocess
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from fastapi import HTTPException

from geovis_lm.dashboard.operations import (
    DashboardConfig,
    authenticate_user,
    create_user,
    ensure_storage,
    provision_user,
    set_user_active,
    set_user_password,
)
from scripts import local_operational_smoke
from scripts import validate_docker_deployment


def test_compose_requires_deployment_secrets():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "change-me-local-token" not in compose
    assert "POSTGRES_PASSWORD: geovis" not in compose
    assert "${GEOVIS_AUTH_TOKEN:?set GEOVIS_AUTH_TOKEN}" in compose
    assert "${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}" in compose


def test_deploy_runbook_requires_compose_v2_and_preserves_postgis():
    runbook = Path("deploy_runbook.sh").read_text(encoding="utf-8")

    assert 'COMPOSE_CMD=("${DOCKER_CMD[@]}" compose)' in runbook
    assert "Docker Compose v2 is required" in runbook
    assert "docker-compose" not in runbook
    assert 'up -d --wait --wait-timeout "$DEPLOY_WAIT_TIMEOUT" db' in runbook
    assert "docker run" not in runbook
    assert "--no-deps --no-build --force-recreate --wait" in runbook


def test_redeploy_smoke_check_covers_legacy_failure_and_volume_persistence():
    smoke = Path("scripts/verify_compose_redeploy.sh").read_text(encoding="utf-8")

    assert 'REDEPLOY_ATTEMPTS:-2' in smoke
    assert "ContainerConfig" in smoke
    assert "pg_control_system" in smoke
    assert "PostGIS cluster changed during redeploy" in smoke
    assert "dashboard worker db" in smoke
    assert 'PUBLIC_BASE_URL}/readyz' in smoke


def test_session_cookie_secure_defaults_to_true(monkeypatch, tmp_path):
    monkeypatch.setenv("GEOVIS_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.delenv("GEOVIS_SESSION_COOKIE_SECURE", raising=False)

    assert DashboardConfig.from_env().session_cookie_secure is True


def test_session_cookie_secure_can_be_disabled_for_local_http(monkeypatch, tmp_path):
    monkeypatch.setenv("GEOVIS_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("GEOVIS_SESSION_COOKIE_SECURE", "false")

    assert DashboardConfig.from_env().session_cookie_secure is False


def test_closed_signup_allows_offline_provisioning_and_recovery(monkeypatch, tmp_path):
    monkeypatch.setenv("GEOVIS_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("GEOVIS_SIGNUP_ENABLED", "false")
    config = DashboardConfig.from_env()
    ensure_storage(config)

    with pytest.raises(HTTPException, match="Signup is disabled"):
        create_user(config, "owner@example.com", "initial password value")

    provision_user(config, "owner@example.com", "initial password value", role="admin")
    assert authenticate_user(config, "owner@example.com", "initial password value")["role"] == "admin"

    set_user_active(config, "owner@example.com", False)
    with pytest.raises(HTTPException, match="Invalid email or password"):
        authenticate_user(config, "owner@example.com", "initial password value")

    set_user_password(config, "owner@example.com", "replacement password value")
    set_user_active(config, "owner@example.com", True)
    with pytest.raises(HTTPException, match="Invalid email or password"):
        authenticate_user(config, "owner@example.com", "initial password value")
    assert authenticate_user(config, "owner@example.com", "replacement password value")["active"] is True


def test_docker_command_rejects_untrusted_path(monkeypatch, tmp_path):
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(validate_docker_deployment.shutil, "which", lambda name: str(docker))

    with pytest.raises(SystemExit, match="Refusing untrusted Docker executable"):
        validate_docker_deployment.docker_command()


def test_compose_config_validator_supplies_local_placeholder_secrets(monkeypatch, tmp_path):
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\n", encoding="utf-8")
    captured = {}

    monkeypatch.delenv("GEOVIS_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.setattr(validate_docker_deployment, "trusted_docker_paths", lambda: {docker.resolve()})

    def run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        captured["env_file_text"] = Path(command[3]).read_text(encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(validate_docker_deployment.subprocess, "run", run)

    result = validate_docker_deployment.run_docker_compose_config(docker)

    assert result.returncode == 0
    assert captured["command"][:3] == ["docker", "compose", "--env-file"]
    assert captured["command"][4:] == ["config"]
    assert "GEOVIS_AUTH_TOKEN=compose-config-validation-token" in captured["env_file_text"]
    assert "POSTGRES_PASSWORD=compose-config-validation-password" in captured["env_file_text"]


def test_local_operational_smoke_closes_server_output_pipe():
    class OutputPipe:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    class Process:
        def __init__(self) -> None:
            self.stdout = OutputPipe()
            self.terminated = False
            self.waited = False

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout: int) -> None:
            assert timeout == 10
            self.waited = True

        def kill(self) -> None:
            raise AssertionError("kill should not be called when graceful shutdown succeeds")

    process = Process()

    local_operational_smoke.stop_process(process)

    assert process.terminated is True
    assert process.waited is True
    assert process.stdout.closed is True


def test_logout_clears_session_cookie_with_secure_attributes(monkeypatch, tmp_path):
    monkeypatch.setenv("GEOVIS_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("GEOVIS_REQUIRE_AUTH", "true")
    monkeypatch.setenv("GEOVIS_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("GEOVIS_SESSION_COOKIE_SECURE", "true")

    for module_name in ("geovis_lm.dashboard.app", "geovis_lm.dashboard.operations"):
        sys.modules.pop(module_name, None)

    app_module = importlib.import_module("geovis_lm.dashboard.app")

    async def logout_flow():
        async with AsyncClient(transport=ASGITransport(app=app_module.app), base_url="http://testserver") as client:
            return await client.post("/logout", follow_redirects=False)

    response = asyncio.run(logout_flow())

    assert response.status_code == 303
    assert "geovis_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"]
