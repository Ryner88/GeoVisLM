#!/usr/bin/env python3
"""Send GeoVisLM off-host backup alerts without loading backup credentials."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
import sys
import time
from urllib.request import Request, urlopen


class AlertError(RuntimeError):
    pass


@dataclass(frozen=True)
class AlertConfig:
    url: str
    retries: int
    retry_base_seconds: float

    @classmethod
    def from_env(cls) -> "AlertConfig":
        url = os.getenv("GEOVIS_BACKUP_ALERT_URL", "")
        if not url:
            raise AlertError("required environment variable is missing: GEOVIS_BACKUP_ALERT_URL")
        if not url.startswith("https://"):
            raise AlertError("GEOVIS_BACKUP_ALERT_URL must use HTTPS")
        config = cls(
            url=url,
            retries=int(os.getenv("GEOVIS_BACKUP_RETRIES", "4")),
            retry_base_seconds=float(
                os.getenv("GEOVIS_BACKUP_RETRY_BASE_SECONDS", "2")
            ),
        )
        if config.retries < 1 or config.retry_base_seconds < 0:
            raise AlertError("retry configuration is invalid")
        return config


def send_alert(config: AlertConfig, message: str) -> None:
    payload = json.dumps(
        {
            "service": "GeoVisLM off-host backup",
            "status": "failure",
            "message": message,
        }
    ).encode()
    last_error: Exception | None = None
    for attempt in range(1, config.retries + 1):
        try:
            request = Request(
                config.url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urlopen(request, timeout=15) as response:
                if not 200 <= response.status < 300:
                    raise AlertError(
                        f"alert endpoint returned HTTP {response.status}"
                    )
            return
        except Exception as error:  # noqa: BLE001 - retry transport failures
            last_error = error
            if attempt < config.retries:
                time.sleep(config.retry_base_seconds * (2 ** (attempt - 1)))
    raise AlertError("alert delivery failed after configured retries") from last_error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--message", default="operator-requested alert delivery test"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        send_alert(AlertConfig.from_env(), args.message)
        print(json.dumps({"status": "delivered"}))
        return 0
    except (AlertError, OSError, ValueError) as error:
        # Never include the configured URL or an underlying exception that may
        # echo it; systemd receives only this sanitized failure summary.
        print(f"off-host alert error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
