from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

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
