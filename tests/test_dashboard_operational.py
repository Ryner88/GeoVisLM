from __future__ import annotations

import asyncio
import base64
import importlib
import json
import re
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture()
def app_module(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOVIS_OUTPUT_ROOT", str(tmp_path / "outputs"))
    monkeypatch.setenv("GEOVIS_REQUIRE_AUTH", "true")
    monkeypatch.setenv("GEOVIS_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("GEOVIS_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("GEOVIS_MAX_UPLOAD_FILE_MB", "1")
    monkeypatch.setenv("GEOVIS_MAX_UPLOAD_BATCH_MB", "2")
    monkeypatch.setenv("GEOVIS_MAX_BATCH_FILES", "4")

    for module_name in ("geovis_lm.dashboard.app", "geovis_lm.dashboard.operations"):
        sys.modules.pop(module_name, None)
    return importlib.import_module("geovis_lm.dashboard.app")


def request(app, method: str, url: str, **kwargs):
    async def call():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            return await getattr(client, method)(url, **kwargs)

    return asyncio.run(call())


def auth(user: str = "user-1", role: str = "owner") -> dict[str, str]:
    return {"authorization": "Bearer test-token", "x-geovis-user": user, "x-geovis-role": role}


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def create_project_and_run(app) -> tuple[dict, dict]:
    project_response = request(
        app,
        "post",
        "/api/projects",
        headers=auth(),
        json={"name": "Sample Terrain", "description": "Operational test project"},
    )
    assert project_response.status_code == 200
    project = project_response.json()

    run_response = request(
        app,
        "post",
        f"/api/projects/{project['id']}/runs",
        headers=auth(),
        json={"name": "Sample DEM run", "workflow_type": "terrain"},
    )
    assert run_response.status_code == 200
    return project, run_response.json()


def test_authentication_is_required_for_operational_routes(app_module):
    response = request(app_module.app, "post", "/api/projects", json={"name": "Nope"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"

    bad_token = request(
        app_module.app,
        "post",
        "/api/projects",
        headers={"authorization": "Bearer wrong", "x-geovis-user": "user-1"},
        json={"name": "Nope"},
    )
    assert bad_token.status_code == 401


def test_browser_login_session_and_logout_flow(app_module):
    unauthenticated = request(app_module.app, "get", "/", follow_redirects=False)
    assert unauthenticated.status_code == 303
    assert unauthenticated.headers["location"] == "/login?next=/"

    api_response = request(app_module.app, "get", "/api/projects")
    assert api_response.status_code == 401

    invalid = request(
        app_module.app,
        "post",
        "/login",
        content="token=wrong&user_id=browser-user&role=owner&next=/",
        headers={"content-type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert invalid.status_code == 303
    assert invalid.headers["location"] == "/login?error=1&next=/"

    async def browser_flow():
        async with AsyncClient(transport=ASGITransport(app=app_module.app), base_url="http://testserver") as client:
            login = await client.post(
                "/login",
                content="token=test-token&user_id=browser-user&role=owner&next=/",
                headers={"content-type": "application/x-www-form-urlencoded"},
                follow_redirects=False,
            )
            assert login.status_code == 303
            assert "geovis_session" in login.headers["set-cookie"]

            index = await client.get("/")
            assert index.status_code == 200
            assert "GeoVisLM Dashboard" in index.text

            project = await client.post(
                "/dashboard/projects",
                content="name=Browser%20Project&description=Session",
                headers={"content-type": "application/x-www-form-urlencoded"},
                follow_redirects=False,
            )
            assert project.status_code == 200
            assert "/projects/" in project.text

            logout = await client.post("/logout", follow_redirects=False)
            assert logout.status_code == 303

            after_logout = await client.get("/", follow_redirects=False)
            assert after_logout.status_code == 303
            assert after_logout.headers["location"] == "/login?next=/"

    asyncio.run(browser_flow())

    bearer = request(app_module.app, "get", "/api/projects", headers=auth())
    assert bearer.status_code == 200


def test_browser_end_to_end_workflow_from_login_to_outputs(app_module):
    from geovis_lm.dashboard.worker import run_worker_once

    async def browser_flow():
        async with AsyncClient(transport=ASGITransport(app=app_module.app), base_url="http://testserver") as client:
            unauthenticated = await client.get("/", follow_redirects=False)
            assert unauthenticated.status_code == 303
            assert unauthenticated.headers["location"] == "/login?next=/"

            login = await client.post(
                "/login",
                data={"token": "test-token", "user_id": "browser-e2e-user", "role": "owner", "next": "/"},
                follow_redirects=False,
            )
            assert login.status_code == 303

            project_response = await client.post(
                "/dashboard/projects",
                data={"name": "Browser E2E Project", "description": "Dashboard workflow"},
            )
            assert project_response.status_code == 200
            project_id = re.search(r"/projects/([a-f0-9]+)", project_response.text).group(1)

            project_page = await client.get(f"/projects/{project_id}")
            assert project_page.status_code == 200
            assert "Browser E2E Project" in project_page.text

            run_response = await client.post(
                f"/dashboard/projects/{project_id}/runs",
                data={"name": "Browser E2E Run"},
            )
            assert run_response.status_code == 200
            run_id = re.search(r"/runs/([a-f0-9]+)", run_response.text).group(1)

            run_page = await client.get(f"/runs/{run_id}")
            assert run_page.status_code == 200
            assert "Upload Input" in run_page.text

            uploads = [
                ("sample_dem.tif", "image/tiff", Path("data/sample/sample_dem.tif")),
                ("sample_overlay.geojson", "application/geo+json", Path("data/sample/sample_overlay.geojson")),
            ]
            for filename, content_type, path in uploads:
                upload = await client.post(
                    f"/dashboard/projects/{project_id}/runs/{run_id}/files",
                    data={
                        "filename": filename,
                        "content_type": content_type,
                        "content_b64": b64(path),
                    },
                )
                assert upload.status_code == 200

            uploaded_page = await client.get(f"/runs/{run_id}")
            assert uploaded_page.status_code == 200
            assert "sample_dem.tif" in uploaded_page.text
            assert "sample_overlay.geojson" in uploaded_page.text

            queue = await client.post(f"/dashboard/runs/{run_id}/queue")
            assert queue.status_code == 200

            worker_result = run_worker_once(app_module.CONFIG, app_module.run_analysis_workflow)
            assert worker_result["status"] == "completed"

            completed_page = await client.get(f"/runs/{run_id}")
            assert completed_page.status_code == 200
            assert "Status: <code>completed</code>" in completed_page.text
            assert "maps/slope_degrees.tif" in completed_page.text
            assert "vectors/sample_overlay_clipped.geojson" in completed_page.text
            assert "renders/terrain_overlay.png" in completed_page.text
            assert f"/api/runs/{run_id}/outputs/terrain_overlay_png/preview" in completed_page.text

            logout = await client.post("/logout", follow_redirects=False)
            assert logout.status_code == 303

            blocked = await client.get("/", follow_redirects=False)
            assert blocked.status_code == 303
            assert blocked.headers["location"] == "/login?next=/"

    asyncio.run(browser_flow())


def test_project_run_upload_analysis_report_and_outputs(app_module):
    project, run = create_project_and_run(app_module.app)

    upload_response = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/runs/{run['run_id']}/files",
        headers=auth(),
        json={
            "files": [
                {
                    "filename": "sample_dem.tif",
                    "content_b64": b64(Path("data/sample/sample_dem.tif")),
                    "content_type": "image/tiff",
                }
            ]
        },
    )
    assert upload_response.status_code == 200
    upload = upload_response.json()
    assert upload["batch_status"] == "valid"
    assert upload["files"][0]["status"] == "valid"
    assert upload["files"][0]["checksum_sha256"]

    analysis_response = request(app_module.app, "post", f"/api/runs/{run['run_id']}/analyze", headers=auth())
    assert analysis_response.status_code == 200
    analyzed = analysis_response.json()
    assert analyzed["status"] == "completed"
    assert Path(analyzed["outputs"]["slope"]).exists()
    assert Path(analyzed["outputs"]["hillshade"]).exists()
    assert Path(analyzed["outputs"]["terrain_risk"]).exists()
    assert Path(analyzed["outputs"]["terrain_summary_json"]).exists()
    assert analyzed["execution_adapter"] == "dem_terrain"
    assert "stage=complete" in analyzed["execution_metadata"]["logs"]
    assert [item["status"] for item in analyzed["status_history"]][-1] == "completed"

    report_response = request(app_module.app, "post", f"/api/runs/{run['run_id']}/report", headers=auth())
    assert report_response.status_code == 200
    reported = report_response.json()
    assert reported["status"] == "reported"
    assert Path(reported["outputs"]["report_md"]).exists()

    outputs_response = request(app_module.app, "get", f"/api/runs/{run['run_id']}/outputs", headers=auth())
    assert outputs_response.status_code == 200
    output_names = {item["filename"] for item in outputs_response.json()["files"]}
    assert {
        "slope_degrees.tif",
        "hillshade.tif",
        "terrain_risk.tif",
        "terrain_summary.json",
        "terrain_analysis.md",
    } <= output_names
    slope = next(item for item in outputs_response.json()["files"] if item["id"] == "slope")
    assert slope["category"] == "raster"
    assert slope["mime_type"] == "image/tiff"
    assert slope["size_bytes"] > 0
    assert slope["checksum_sha256"]
    assert slope["generated_stage"] == "terrain_analysis"
    assert slope["display_filename"] == "maps/slope_degrees.tif"
    assert slope["download_url"] == f"/api/runs/{run['run_id']}/outputs/slope/download"

    run_page = request(app_module.app, "get", f"/runs/{run['run_id']}", headers=auth())
    assert run_page.status_code == 200
    assert "Status:" in run_page.text
    assert "Raster Outputs" in run_page.text
    assert "Vector Outputs" in run_page.text
    assert "Render and Preview Outputs" in run_page.text
    assert "Metadata and Summary Outputs" in run_page.text
    assert "maps/slope_degrees.tif" in run_page.text
    assert "reports/terrain_summary.json" in run_page.text
    assert "terrain_analysis.md" in run_page.text


def test_dashboard_recent_runs_match_visible_projects(app_module):
    project, run = create_project_and_run(app_module.app)
    other_project = request(
        app_module.app,
        "post",
        "/api/projects",
        headers=auth("user-2", "owner"),
        json={"name": "Other User Project"},
    ).json()
    other_run = request(
        app_module.app,
        "post",
        f"/api/projects/{other_project['id']}/runs",
        headers=auth("user-2", "owner"),
        json={"name": "Hidden Run", "workflow_type": "terrain"},
    ).json()

    index = request(app_module.app, "get", "/", headers=auth())
    assert index.status_code == 200
    assert project["name"] in index.text
    assert run["name"] in index.text
    assert f"/projects/{project['id']}" in index.text
    assert "Other User Project" not in index.text
    assert other_run["name"] not in index.text

    runs_response = request(app_module.app, "get", "/api/runs", headers=auth())
    run_ids = {item["run_id"] for item in runs_response.json()["runs"]}
    assert run["run_id"] in run_ids
    assert other_run["run_id"] not in run_ids


def test_dashboard_hides_orphaned_runs_from_recent_runs(app_module):
    from geovis_lm.dashboard.operations import run_metadata_path, write_json

    project, _run = create_project_and_run(app_module.app)
    orphan = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/runs",
        headers=auth(),
        json={"name": "Orphaned Run", "workflow_type": "terrain"},
    ).json()
    orphan["project_id"] = "missing-project"
    write_json(run_metadata_path(app_module.CONFIG, orphan["run_id"]), orphan)

    index = request(app_module.app, "get", "/", headers=auth())
    assert index.status_code == 200
    assert "Orphaned Run" not in index.text

    runs_response = request(app_module.app, "get", "/api/runs", headers=auth())
    run_ids = {item["run_id"] for item in runs_response.json()["runs"]}
    assert orphan["run_id"] not in run_ids


def test_project_run_with_vector_overlay_generates_render_outputs(app_module):
    project, run = create_project_and_run(app_module.app)

    upload_response = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/runs/{run['run_id']}/files",
        headers=auth(),
        json={
            "files": [
                {
                    "filename": "sample_dem.tif",
                    "content_b64": b64(Path("data/sample/sample_dem.tif")),
                    "content_type": "image/tiff",
                },
                {
                    "filename": "sample_overlay.geojson",
                    "content_b64": b64(Path("data/sample/sample_overlay.geojson")),
                    "content_type": "application/geo+json",
                },
            ]
        },
    )
    assert upload_response.status_code == 200
    assert upload_response.json()["batch_status"] == "valid"

    analysis_response = request(app_module.app, "post", f"/api/runs/{run['run_id']}/analyze", headers=auth())
    assert analysis_response.status_code == 200
    analyzed = analysis_response.json()
    assert analyzed["status"] == "completed"
    assert Path(analyzed["outputs"]["vector_overlay_1"]).exists()
    assert Path(analyzed["outputs"]["terrain_overlay_png"]).exists()
    assert analyzed["execution_metadata"]["vector_layers"][0]["source_crs"] == "EPSG:4326"
    assert analyzed["execution_metadata"]["vector_layers"][0]["target_crs"] == "EPSG:3857"
    assert "stage=render_overlay" in analyzed["execution_metadata"]["logs"]

    outputs_response = request(app_module.app, "get", f"/api/runs/{run['run_id']}/outputs", headers=auth())
    output_names = {item["filename"] for item in outputs_response.json()["files"]}
    assert {"sample_overlay_clipped.geojson", "terrain_overlay.png"} <= output_names
    artifacts = {item["id"]: item for item in outputs_response.json()["files"]}
    assert artifacts["vector_overlay_1"]["category"] == "vector"
    assert artifacts["vector_overlay_1"]["mime_type"] == "application/geo+json"
    assert artifacts["terrain_overlay_png"]["category"] == "render"
    assert artifacts["terrain_overlay_png"]["mime_type"] == "image/png"
    assert artifacts["terrain_overlay_png"]["preview_url"] == f"/api/runs/{run['run_id']}/outputs/terrain_overlay_png/preview"


def test_output_preview_and_download_routes_for_registered_artifacts(app_module):
    project, run = create_project_and_run(app_module.app)

    upload_response = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/runs/{run['run_id']}/files",
        headers=auth(),
        json={
            "files": [
                {
                    "filename": "sample_dem.tif",
                    "content_b64": b64(Path("data/sample/sample_dem.tif")),
                    "content_type": "image/tiff",
                },
                {
                    "filename": "sample_overlay.geojson",
                    "content_b64": b64(Path("data/sample/sample_overlay.geojson")),
                    "content_type": "application/geo+json",
                },
            ]
        },
    )
    assert upload_response.status_code == 200

    analyzed = request(app_module.app, "post", f"/api/runs/{run['run_id']}/analyze", headers=auth()).json()
    assert analyzed["status"] == "completed"

    png_preview = request(
        app_module.app,
        "get",
        f"/api/runs/{run['run_id']}/outputs/terrain_overlay_png/preview",
        headers=auth(),
    )
    assert png_preview.status_code == 200
    assert png_preview.headers["content-type"] == "image/png"
    assert png_preview.content.startswith(b"\x89PNG")

    downloads = {
        "terrain_summary_json": "application/json",
        "vector_overlay_1": "application/geo+json",
        "slope": "image/tiff",
    }
    for output_key, content_type in downloads.items():
        response = request(
            app_module.app,
            "get",
            f"/api/runs/{run['run_id']}/outputs/{output_key}/download",
            headers=auth(),
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(content_type)
        assert response.content

    non_png_preview = request(
        app_module.app,
        "get",
        f"/api/runs/{run['run_id']}/outputs/slope/preview",
        headers=auth(),
    )
    assert non_png_preview.status_code == 400


def test_output_access_rejects_unauthorized_users(app_module):
    project, run = create_project_and_run(app_module.app)
    upload_response = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/runs/{run['run_id']}/files",
        headers=auth(),
        json={"files": [{"filename": "sample_dem.tif", "content_b64": b64(Path("data/sample/sample_dem.tif"))}]},
    )
    assert upload_response.status_code == 200
    assert request(app_module.app, "post", f"/api/runs/{run['run_id']}/analyze", headers=auth()).status_code == 200

    response = request(
        app_module.app,
        "get",
        f"/api/runs/{run['run_id']}/outputs/slope/download",
        headers=auth("user-2", "owner"),
    )

    assert response.status_code == 403


def test_output_routes_handle_missing_files_and_reject_traversal(app_module):
    project, run = create_project_and_run(app_module.app)
    upload_response = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/runs/{run['run_id']}/files",
        headers=auth(),
        json={"files": [{"filename": "sample_dem.tif", "content_b64": b64(Path("data/sample/sample_dem.tif"))}]},
    )
    assert upload_response.status_code == 200
    analyzed = request(app_module.app, "post", f"/api/runs/{run['run_id']}/analyze", headers=auth()).json()
    assert analyzed["status"] == "completed"

    Path(analyzed["outputs"]["terrain_summary_json"]).unlink()
    missing = request(
        app_module.app,
        "get",
        f"/api/runs/{run['run_id']}/outputs/terrain_summary_json/download",
        headers=auth(),
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Output file missing"

    traversal = request(
        app_module.app,
        "get",
        f"/api/runs/{run['run_id']}/outputs/%2E%2E%2Fmetadata/download",
        headers=auth(),
    )
    assert traversal.status_code == 400

    unregistered = request(
        app_module.app,
        "get",
        f"/api/runs/{run['run_id']}/outputs/metadata/download",
        headers=auth(),
    )
    assert unregistered.status_code == 404


def test_queue_creates_durable_job_and_worker_completes_it(app_module):
    from geovis_lm.dashboard.worker import run_worker_once

    project, run = create_project_and_run(app_module.app)
    upload_response = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/runs/{run['run_id']}/files",
        headers=auth(),
        json={
            "files": [
                {
                    "filename": "sample_dem.tif",
                    "content_b64": b64(Path("data/sample/sample_dem.tif")),
                }
            ]
        },
    )
    assert upload_response.status_code == 200

    queue_response = request(app_module.app, "post", f"/api/runs/{run['run_id']}/queue", headers=auth())
    assert queue_response.status_code == 200
    queued = queue_response.json()
    assert queued["status"] == "queued"
    assert queued["job"]["status"] == "queued"

    jobs_response = request(app_module.app, "get", f"/api/jobs?run_id={run['run_id']}", headers=auth())
    assert jobs_response.status_code == 200
    assert len(jobs_response.json()["jobs"]) == 1

    result = run_worker_once(app_module.CONFIG, app_module.run_analysis_workflow)
    assert result["status"] == "completed"
    assert result["job"]["status"] == "completed"
    assert Path(result["job"]["logs_path"]).exists()

    completed = request(app_module.app, "get", f"/api/runs/{run['run_id']}", headers=auth()).json()
    assert completed["status"] == "completed"


def test_upload_rejects_unsafe_and_unsupported_files(app_module):
    project, run = create_project_and_run(app_module.app)

    unsafe = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/runs/{run['run_id']}/files",
        headers=auth(),
        json={"files": [{"filename": "../sample.tif", "content_b64": "AA=="}]},
    )
    assert unsafe.status_code == 400
    assert unsafe.json()["detail"]["error_code"] == "unsafe_filename"

    unsupported = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/runs/{run['run_id']}/files",
        headers=auth(),
        json={"files": [{"filename": "payload.exe", "content_b64": "AA=="}]},
    )
    assert unsupported.status_code == 400
    assert unsupported.json()["detail"]["error_code"] == "unsupported_file_type"


def test_upload_rejects_oversized_batches(app_module):
    project, run = create_project_and_run(app_module.app)
    large_payload = base64.b64encode(b"x" * (1024 * 1024 + 1)).decode("ascii")

    response = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/runs/{run['run_id']}/files",
        headers=auth(),
        json={"files": [{"filename": "large.csv", "content_b64": large_payload}]},
    )

    assert response.status_code == 413
    assert response.json()["detail"]["error_code"] == "file_too_large"


def test_shapefile_bundle_records_missing_component_error(app_module):
    project, run = create_project_and_run(app_module.app)

    response = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/runs/{run['run_id']}/files",
        headers=auth(),
        json={"files": [{"filename": "roads.shp", "content_b64": "AA=="}]},
    )

    assert response.status_code == 200
    file_record = response.json()["files"][0]
    assert file_record["status"] == "invalid"
    assert file_record["validation_errors"][-1]["error_code"] == "missing_shapefile_component"


def test_authorization_rejects_cross_user_access(app_module):
    project, _run = create_project_and_run(app_module.app)

    response = request(app_module.app, "get", f"/api/projects/{project['id']}", headers=auth("user-2", "owner"))

    assert response.status_code == 403


def test_failed_run_can_create_retry_run(app_module):
    _project, run = create_project_and_run(app_module.app)

    failed_response = request(app_module.app, "post", f"/api/runs/{run['run_id']}/analyze", headers=auth())
    assert failed_response.status_code == 200
    failed = failed_response.json()
    assert failed["status"] == "failed"
    assert failed["error_code"] == "missing_dem"
    assert failed["retryable"] is True

    retry_response = request(app_module.app, "post", f"/api/runs/{run['run_id']}/retry", headers=auth())
    assert retry_response.status_code == 200
    retry = retry_response.json()
    assert retry["status"] == "queued"
    assert retry["retry_of_run_id"] == run["run_id"]
    assert retry["attempt_number"] == 2
    assert retry["job"]["status"] == "queued"


def test_dem_analysis_adapter_writes_outputs_and_summary(tmp_path):
    from geovis_lm.dashboard.analysis_adapter import execute_dem_analysis

    result = execute_dem_analysis(
        Path("data/sample/sample_dem.tif"),
        maps_dir=tmp_path / "maps",
        reports_dir=tmp_path / "reports",
    )

    assert result.adapter == "dem_terrain"
    assert set(result.outputs) == {"slope", "hillshade", "terrain_risk", "terrain_summary_json"}
    assert all(Path(path).exists() for path in result.outputs.values())
    summary = json.loads(Path(result.outputs["terrain_summary_json"]).read_text(encoding="utf-8"))
    assert summary["adapter"] == "dem_terrain"
    assert summary["outputs"]["slope"] == result.outputs["slope"]
    assert "stage=complete" in result.logs


def test_dem_analysis_adapter_processes_vector_without_render_when_disabled(tmp_path):
    from geovis_lm.dashboard.analysis_adapter import execute_dem_analysis

    result = execute_dem_analysis(
        Path("data/sample/sample_dem.tif"),
        maps_dir=tmp_path / "maps",
        reports_dir=tmp_path / "reports",
        vectors_dir=tmp_path / "vectors",
        renders_dir=tmp_path / "renders",
        vector_paths=[Path("data/sample/sample_overlay.geojson")],
        parameters={"render_overlay": False},
    )

    assert Path(result.outputs["vector_overlay_1"]).exists()
    assert "terrain_overlay_png" not in result.outputs
    assert result.metadata["vector_layers"][0]["source_crs"] == "EPSG:4326"
    assert result.metadata["vector_layers"][0]["target_crs"] == "EPSG:3857"
    assert result.metadata["render_enabled"] is False


def test_dem_analysis_adapter_rejects_unsupported_input(tmp_path):
    from geovis_lm.dashboard.analysis_adapter import AnalysisExecutionError, execute_dem_analysis

    csv_path = tmp_path / "points.csv"
    csv_path.write_text("x,y\n1,2\n", encoding="utf-8")

    with pytest.raises(AnalysisExecutionError) as exc_info:
        execute_dem_analysis(csv_path, maps_dir=tmp_path / "maps", reports_dir=tmp_path / "reports")

    error = exc_info.value
    assert error.error_code == "unsupported_input"
    assert error.retryable is False
    assert error.as_detail()["stage"] == "input_validation"


def test_dem_analysis_adapter_rejects_unsupported_vector_input(tmp_path):
    from geovis_lm.dashboard.analysis_adapter import AnalysisExecutionError, execute_dem_analysis

    csv_path = tmp_path / "points.csv"
    csv_path.write_text("x,y\n1,2\n", encoding="utf-8")

    with pytest.raises(AnalysisExecutionError) as exc_info:
        execute_dem_analysis(
            Path("data/sample/sample_dem.tif"),
            maps_dir=tmp_path / "maps",
            reports_dir=tmp_path / "reports",
            vector_paths=[csv_path],
        )

    error = exc_info.value
    assert error.error_code == "unsupported_vector_input"
    assert error.retryable is False
    assert error.as_detail()["stage"] == "vector_validation"


def test_dem_analysis_adapter_captures_structured_failure(tmp_path, monkeypatch):
    import geovis_lm.dashboard.analysis_adapter as adapter
    from geovis_lm.dashboard.analysis_adapter import AnalysisExecutionError, execute_dem_analysis

    def fail_load(_path):
        raise RuntimeError("raster exploded")

    monkeypatch.setattr(adapter, "load_dem", fail_load)

    with pytest.raises(AnalysisExecutionError) as exc_info:
        execute_dem_analysis(
            Path("data/sample/sample_dem.tif"),
            maps_dir=tmp_path / "maps",
            reports_dir=tmp_path / "reports",
        )

    detail = exc_info.value.as_detail()
    assert detail["error_code"] == "dem_analysis_failed"
    assert detail["error_type"] == "RuntimeError"
    assert detail["stage"] == "load_dem"
    assert "stage=load_dem" in detail["logs"]
