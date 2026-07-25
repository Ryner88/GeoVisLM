from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def find_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(method: str, url: str, data: dict | bytes | None = None, token: str | None = None) -> tuple[int, str]:
    headers = {}
    payload = None
    if isinstance(data, dict):
        payload = json.dumps(data).encode("utf-8")
        headers["content-type"] = "application/json"
    elif isinstance(data, bytes):
        payload = data
    if token:
        headers["authorization"] = f"Bearer {token}"
        headers["x-geovis-user"] = "smoke-user"
        headers["x-geovis-role"] = "owner"
    req = urllib.request.Request(url, data=payload, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.status, response.read().decode("utf-8")


def request_bytes(method: str, url: str, token: str | None = None) -> tuple[int, str, bytes]:
    headers = {}
    if token:
        headers["authorization"] = f"Bearer {token}"
        headers["x-geovis-user"] = "smoke-user"
        headers["x-geovis-role"] = "owner"
    req = urllib.request.Request(url, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.status, response.headers.get("content-type", ""), response.read()


def wait_for_ready(base_url: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error = None
    while time.time() < deadline:
        try:
            status, body = request("GET", f"{base_url}/readyz")
            if status == 200 and "ready" in body:
                return
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"Dashboard did not become ready: {last_error}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an end-to-end GeoVisLM dashboard smoke test over HTTP.")
    parser.add_argument("--port", type=int, help="Port to bind. Defaults to an available local port.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--output-root", help="Storage root. Defaults to a temporary directory.")
    parser.add_argument("--sample-dem", default="data/sample/sample_dem.tif")
    parser.add_argument("--keep-output", action="store_true", help="Keep temporary output root after success.")
    return parser.parse_args()


def stop_process(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)
    if process.stdout:
        process.stdout.close()


def main() -> None:
    args = parse_args()
    port = args.port or find_port()
    output_root = Path(args.output_root) if args.output_root else Path(tempfile.mkdtemp(prefix="geovis-smoke-"))
    token = "local-smoke-token"
    base_url = f"http://{args.host}:{port}"

    env = os.environ.copy()
    env.update(
        {
            "GEOVIS_OUTPUT_ROOT": str(output_root),
            "GEOVIS_REQUIRE_AUTH": "true",
            "GEOVIS_AUTH_TOKEN": token,
        }
    )

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "geovis_lm.dashboard.app:app",
        "--host",
        args.host,
        "--port",
        str(port),
    ]
    process = subprocess.Popen(command, cwd=PROJECT_ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        wait_for_ready(base_url, args.timeout)

        status, body = request("POST", f"{base_url}/api/projects", {"name": "Smoke Test Project"}, token)
        assert status == 200, body
        project = json.loads(body)

        status, body = request(
            "POST",
            f"{base_url}/api/projects/{project['id']}/runs",
            {"name": "Smoke DEM Run", "workflow_type": "terrain"},
            token,
        )
        assert status == 200, body
        run = json.loads(body)

        dem_b64 = base64.b64encode((PROJECT_ROOT / args.sample_dem).read_bytes()).decode("ascii")
        status, body = request(
            "POST",
            f"{base_url}/api/projects/{project['id']}/runs/{run['run_id']}/files",
            {"files": [{"filename": "sample_dem.tif", "content_b64": dem_b64}]},
            token,
        )
        assert status == 200, body

        status, body = request("POST", f"{base_url}/api/runs/{run['run_id']}/analyze", token=token)
        assert status == 200, body
        analyzed = json.loads(body)
        assert analyzed["status"] == "completed", analyzed

        status, body = request("POST", f"{base_url}/api/runs/{run['run_id']}/report", token=token)
        assert status == 200, body
        reported = json.loads(body)

        status, body = request("GET", f"{base_url}/api/runs/{run['run_id']}/outputs", token=token)
        assert status == 200, body
        outputs = json.loads(body)["files"]
        artifacts = {item["id"]: item for item in outputs}
        assert {"slope", "hillshade", "terrain_risk", "terrain_summary_json", "report_md"} <= set(artifacts), artifacts
        assert artifacts["slope"]["mime_type"] == "image/tiff", artifacts["slope"]
        assert artifacts["terrain_summary_json"]["checksum_sha256"], artifacts["terrain_summary_json"]
        status, content_type, summary_bytes = request_bytes(
            "GET",
            f"{base_url}{artifacts['terrain_summary_json']['download_url']}",
            token=token,
        )
        assert status == 200, content_type
        assert content_type.startswith("application/json"), content_type
        assert json.loads(summary_bytes.decode("utf-8"))["adapter"] == "dem_terrain"
        assert reported["outputs"]["report_md"].endswith(artifacts["report_md"]["filename"]), artifacts["report_md"]

        print("Local operational smoke test passed.")
        print(f"Base URL: {base_url}")
        print(f"Output root: {output_root}")
    except Exception:
        if process.stdout:
            print(process.stdout.read(), file=sys.stderr)
        raise
    finally:
        stop_process(process)
        if not args.keep_output and args.output_root is None:
            import shutil

            shutil.rmtree(output_root, ignore_errors=True)


if __name__ == "__main__":
    main()
