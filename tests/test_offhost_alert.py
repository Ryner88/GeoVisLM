from __future__ import annotations

import io
import json

import pytest

from scripts import offhost_alert


class Response(io.BytesIO):
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_alert_config_is_independent_of_backup_and_b2_settings(monkeypatch):
    monkeypatch.setenv("GEOVIS_BACKUP_ALERT_URL", "https://alerts.example.invalid/hook")
    monkeypatch.delenv("B2_BUCKET", raising=False)
    monkeypatch.delenv("B2_PREFIX", raising=False)
    monkeypatch.delenv("B2_APPLICATION_KEY", raising=False)

    config = offhost_alert.AlertConfig.from_env()

    assert config.url.startswith("https://")
    assert config.retries == 4


def test_alert_sends_expected_json_and_accepts_2xx(monkeypatch):
    captured = {}

    def fake_open(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(offhost_alert, "urlopen", fake_open)
    config = offhost_alert.AlertConfig(
        url="https://alerts.example.invalid/hook",
        retries=1,
        retry_base_seconds=0,
    )

    offhost_alert.send_alert(config, "systemd failure-path test")

    assert captured["timeout"] == 15
    assert json.loads(captured["request"].data) == {
        "service": "GeoVisLM off-host backup",
        "status": "failure",
        "message": "systemd failure-path test",
    }


def test_alert_retries_without_leaking_endpoint(monkeypatch):
    calls = 0

    def fail(_request, timeout):
        nonlocal calls
        calls += 1
        assert timeout == 15
        raise OSError("transport failed")

    monkeypatch.setattr(offhost_alert, "urlopen", fail)
    monkeypatch.setattr(offhost_alert.time, "sleep", lambda _delay: None)
    config = offhost_alert.AlertConfig(
        url="https://alerts.example.invalid/sensitive-token",
        retries=3,
        retry_base_seconds=0,
    )

    with pytest.raises(offhost_alert.AlertError) as error:
        offhost_alert.send_alert(config, "failure")

    assert calls == 3
    assert "sensitive-token" not in str(error.value)


@pytest.mark.parametrize(
    ("url", "error"),
    [("", "missing"), ("http://alerts.example.invalid", "HTTPS")],
)
def test_alert_rejects_missing_or_insecure_endpoint(monkeypatch, url, error):
    if url:
        monkeypatch.setenv("GEOVIS_BACKUP_ALERT_URL", url)
    else:
        monkeypatch.delenv("GEOVIS_BACKUP_ALERT_URL", raising=False)

    with pytest.raises(offhost_alert.AlertError, match=error):
        offhost_alert.AlertConfig.from_env()
