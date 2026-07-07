from __future__ import annotations

from pathlib import Path

import pytest

from geovis_lm.dashboard.operations import DashboardConfig
from scripts import validate_docker_deployment


def test_compose_requires_deployment_secrets():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "change-me-local-token" not in compose
    assert "POSTGRES_PASSWORD: geovis" not in compose
    assert "${GEOVIS_AUTH_TOKEN:?set GEOVIS_AUTH_TOKEN}" in compose
    assert "${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}" in compose


def test_session_cookie_secure_defaults_to_true(monkeypatch, tmp_path):
    monkeypatch.setenv("GEOVIS_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.delenv("GEOVIS_SESSION_COOKIE_SECURE", raising=False)

    assert DashboardConfig.from_env().session_cookie_secure is True


def test_session_cookie_secure_can_be_disabled_for_local_http(monkeypatch, tmp_path):
    monkeypatch.setenv("GEOVIS_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setenv("GEOVIS_SESSION_COOKIE_SECURE", "false")

    assert DashboardConfig.from_env().session_cookie_secure is False


def test_docker_command_rejects_untrusted_path(monkeypatch, tmp_path):
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(validate_docker_deployment.shutil, "which", lambda name: str(docker))

    with pytest.raises(SystemExit, match="Refusing untrusted Docker executable"):
        validate_docker_deployment.docker_command()
