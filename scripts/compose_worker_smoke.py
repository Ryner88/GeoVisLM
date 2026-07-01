from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import time
import urllib.request


def request(method: str, base_url: str, path: str, token: str, payload: dict | None = None) -> dict:
    data = None
    headers = {
        "authorization": f"Bearer {token}",
        "x-geovis-user": "compose-worker-smoke",
        "x-geovis-role": "owner",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["content-type"] = "application/json"
    req = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def request_bytes(method: str, base_url: str, path: str, token: str) -> tuple[str, bytes]:
    headers = {
        "authorization": f"Bearer {token}",
        "x-geovis-user": "compose-worker-smoke",
        "x-geovis-role": "owner",
    }
    req = urllib.request.Request(base_url + path, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.headers.get("content-type", ""), response.read()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate dashboard + persistent Compose worker processing.")
    parser.add_argument("--base-url", default="http://dashboard:8000")
    parser.add_argument("--token", default="change-me-local-token")
    parser.add_argument("--sample-dem", default="data/sample/sample_dem.tif")
    parser.add_argument("--sample-vector", default="data/sample/sample_overlay.geojson")
    parser.add_argument("--timeout", type=int, default=90)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project = request("POST", args.base_url, "/api/projects", args.token, {"name": "Compose Worker Smoke"})
    run = request(
        "POST",
        args.base_url,
        f"/api/projects/{project['id']}/runs",
        args.token,
        {"name": "Compose Worker DEM Vector Run", "workflow_type": "terrain"},
    )
    files = [
        {
            "filename": Path(args.sample_dem).name,
            "content_b64": base64.b64encode(Path(args.sample_dem).read_bytes()).decode("ascii"),
        },
        {
            "filename": Path(args.sample_vector).name,
            "content_b64": base64.b64encode(Path(args.sample_vector).read_bytes()).decode("ascii"),
        },
    ]
    upload = request(
        "POST",
        args.base_url,
        f"/api/projects/{project['id']}/runs/{run['run_id']}/files",
        args.token,
        {"files": files},
    )
    if upload["batch_status"] != "valid":
        raise RuntimeError(upload)

    queued = request("POST", args.base_url, f"/api/runs/{run['run_id']}/queue", args.token)
    if queued["status"] != "queued":
        raise RuntimeError(queued)

    deadline = time.time() + args.timeout
    current = queued
    jobs = {"jobs": []}
    while time.time() < deadline:
        current = request("GET", args.base_url, f"/api/runs/{run['run_id']}", args.token)
        jobs = request("GET", args.base_url, f"/api/jobs?run_id={run['run_id']}", args.token)
        if current["status"] in {"completed", "failed"}:
            break
        time.sleep(1)

    if current["status"] != "completed":
        raise RuntimeError({"run": current, "jobs": jobs})
    outputs = request("GET", args.base_url, f"/api/runs/{run['run_id']}/outputs", args.token)
    artifacts = {item["id"]: item for item in outputs["files"]}
    output_names = {item["filename"] for item in outputs["files"]}
    required = {"slope_degrees.tif", "hillshade.tif", "terrain_risk.tif", "sample_overlay_clipped.geojson", "terrain_overlay.png"}
    missing = sorted(required - output_names)
    if missing:
        raise RuntimeError({"missing_outputs": missing, "outputs": sorted(output_names)})
    for output_id in ("slope", "hillshade", "terrain_risk", "vector_overlay_1", "terrain_overlay_png"):
        artifact = artifacts.get(output_id)
        if not artifact or not artifact.get("checksum_sha256") or not artifact.get("download_url"):
            raise RuntimeError({"invalid_artifact": output_id, "artifacts": artifacts})
    png_type, png_bytes = request_bytes("GET", args.base_url, artifacts["terrain_overlay_png"]["preview_url"], args.token)
    if png_type != "image/png" or not png_bytes.startswith(b"\x89PNG"):
        raise RuntimeError({"invalid_preview": png_type})
    json_type, json_bytes = request_bytes("GET", args.base_url, artifacts["vector_overlay_1"]["download_url"], args.token)
    if not json_type.startswith("application/geo+json") or not json_bytes:
        raise RuntimeError({"invalid_geojson_download": json_type})
    if "completed" not in {job["status"] for job in jobs["jobs"]}:
        raise RuntimeError({"jobs": jobs})

    print(
        json.dumps(
            {
                "project_id": project["id"],
                "run_id": run["run_id"],
                "run_status": current["status"],
                "job_statuses": [job["status"] for job in jobs["jobs"]],
                "output_count": len(outputs["files"]),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
