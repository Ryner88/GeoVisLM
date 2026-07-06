"""Shared helpers for staging verification scripts."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import requests


@dataclass(frozen=True)
class StagingTarget:
    """Normalized staging target values used by DNS, curl, and browser checks."""

    host: str
    port: int
    url: str


def normalize_staging_target(value: str) -> StagingTarget:
    """Accept a hostname or URL and return canonical host and HTTPS URL values."""
    target = value.strip()
    if not target:
        raise ValueError("staging domain cannot be empty")

    parsed = urlsplit(target if "://" in target else f"https://{target}")
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported URL scheme: {parsed.scheme}")
    if not parsed.netloc or not parsed.hostname:
        raise ValueError(f"could not determine hostname from: {value}")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or ""
    url = urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))
    return StagingTarget(host=parsed.hostname, port=port, url=url)


def https_check(target: StagingTarget):
    print(f"Checking HTTPS GET {target.url}")
    try:
        r = requests.get(target.url, timeout=10)
        print(f"Status: {r.status_code}")
        print("Server:", r.headers.get("server"))
        print("Via:", r.headers.get("via"))
        body = r.text[:400]
        print("Body preview:", body.replace("\n", " "))
        return r.status_code, r.headers, r.text
    except requests.exceptions.SSLError as e:
        print("SSL error when connecting (expected if using origin cert locally):", e)
    except Exception as e:
        print("HTTPS request failed:", e)
    return None, None, None


def print_cloudflare_access_heuristics(headers, body):
    if headers:
        loc = headers.get("location", "")
        if "cloudflare" in loc.lower() or "access" in loc.lower():
            print("Redirects to Cloudflare Access login (heuristic)")
        if headers.get("server", "").lower().find("cloudflare") != -1:
            print("Server header is Cloudflare (expected)")
    if body and ("Cloudflare" in body or "Access" in body or "access" in body.lower()):
        print("Found Cloudflare/Access text in body (heuristic)")
