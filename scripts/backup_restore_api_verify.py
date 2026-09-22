#!/usr/bin/env python3
"""Verify restored GeoVisLM records and artifacts through an isolated API."""

from __future__ import annotations

import hashlib
import json
from urllib.request import Request, urlopen


BASE_URL = "http://127.0.0.1:8000"
HEADERS = {"x-geovis-user": "restore-validator", "x-geovis-role": "admin"}


def get_json(path: str) -> dict:
    with urlopen(Request(BASE_URL + path, headers=HEADERS), timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"GET {path} returned {response.status}")
        return json.load(response)


def get_bytes(path: str) -> bytes:
    with urlopen(Request(BASE_URL + path, headers=HEADERS), timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"GET {path} returned {response.status}")
        return response.read()


def main() -> int:
    health = get_json("/healthz")
    projects = get_json("/api/projects")["projects"]
    run_count = 0
    artifact_count = 0
    report_count = 0
    downloaded_bytes = 0

    for project in projects:
        project_id = project["id"]
        restored_project = get_json(f"/api/projects/{project_id}")
        if restored_project["id"] != project_id:
            raise ValueError(f"project mismatch for {project_id}")
        runs = get_json(f"/api/projects/{project_id}/runs")["runs"]
        for run in runs:
            run_id = run["run_id"]
            restored_run = get_json(f"/api/runs/{run_id}")
            if restored_run["project_id"] != project_id:
                raise ValueError(f"run/project mismatch for {run_id}")
            run_count += 1
            artifacts = get_json(f"/api/runs/{run_id}/outputs")["files"]
            for artifact in artifacts:
                if not artifact["exists"]:
                    raise ValueError(f"missing registered artifact: {artifact}")
                payload = get_bytes(artifact["download_url"])
                digest = hashlib.sha256(payload).hexdigest()
                if digest != artifact["checksum_sha256"]:
                    raise ValueError(
                        f"download checksum mismatch for {run_id}/{artifact['id']}"
                    )
                if len(payload) != artifact["size_bytes"]:
                    raise ValueError(
                        f"download size mismatch for {run_id}/{artifact['id']}"
                    )
                artifact_count += 1
                downloaded_bytes += len(payload)
                if artifact["category"] == "metadata" or artifact["filename"].endswith(
                    (".md", ".pdf")
                ):
                    report_count += 1

    if not projects or not run_count or not artifact_count or not report_count:
        raise ValueError("isolated API did not expose all required record types")

    print(
        json.dumps(
            {
                "artifact_downloads_verified": artifact_count,
                "downloaded_bytes_verified": downloaded_bytes,
                "health_status": health["status"],
                "projects_verified": len(projects),
                "report_or_metadata_downloads_verified": report_count,
                "runs_verified": run_count,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
