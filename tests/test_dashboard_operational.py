from __future__ import annotations

import asyncio
import base64
import importlib
import json
import re
import sys
import warnings
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from geovis_lm.model.dataset import GeoMiniLMExample
from geovis_lm.model.prototype import GeoMiniLMPrototype


@pytest.fixture()
def app_module(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOVIS_OUTPUT_ROOT", str(tmp_path / "outputs"))
    monkeypatch.setenv("GEOVIS_REQUIRE_AUTH", "true")
    monkeypatch.setenv("GEOVIS_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("GEOVIS_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("GEOVIS_SIGNUP_ENABLED", "true")
    monkeypatch.setenv("GEOVIS_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("GEOVIS_MAX_UPLOAD_FILE_MB", "1")
    monkeypatch.setenv("GEOVIS_MAX_UPLOAD_BATCH_MB", "2")
    monkeypatch.setenv("GEOVIS_MAX_BATCH_FILES", "6")

    for module_name in ("geovis_lm.dashboard.app", "geovis_lm.dashboard.operations"):
        sys.modules.pop(module_name, None)
    return importlib.import_module("geovis_lm.dashboard.app")


@pytest.fixture()
def geominilm_checkpoint(tmp_path, monkeypatch):
    checkpoint_path = tmp_path / "geominilm-checkpoint.json"
    example = GeoMiniLMExample(
        id="dashboard-test-terrain",
        domain="gis",
        instruction="Recommend a terrain workflow for a DEM.",
        inputs={"files": ["sample_dem.tif"]},
        expected_workflow=[
            {"step": 1, "action": "load_dem", "tool": "rasterio"},
            {"step": 2, "action": "calculate_slope", "tool": "gdal"},
        ],
        explanation="Load the DEM and calculate slope.",
    )
    GeoMiniLMPrototype.train([example]).save(checkpoint_path)
    monkeypatch.setenv("GEOVIS_GEOMINILM_CHECKPOINT", str(checkpoint_path))
    return checkpoint_path


def request(app, method: str, url: str, **kwargs):
    async def call():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            return await getattr(client, method)(url, **kwargs)

    return asyncio.run(call())


def auth(user: str = "user-1", role: str = "owner") -> dict[str, str]:
    return {"authorization": "Bearer test-token", "x-geovis-user": user, "x-geovis-role": role}


def seed_dashboard_user(app_module, user_id: str, email: str, display_name: str) -> dict:
    operations = sys.modules["geovis_lm.dashboard.operations"]
    user = {
        "id": user_id,
        "email": email,
        "password_hash": "unused",
        "display_name": display_name,
        "role": "owner",
        "active": True,
        "created_at": "2026-08-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:00:00+00:00",
        "activated_at": "2026-08-01T00:00:00+00:00",
    }
    operations.write_json(operations.user_path(app_module.CONFIG, email), user)
    return user


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


def test_runs_record_workflow_template_metadata(app_module):
    operations = sys.modules["geovis_lm.dashboard.operations"]
    _project, run = create_project_and_run(app_module.app)
    operations.copy_sample_dem_to_run(app_module.CONFIG, run["run_id"], Path("data/sample/sample_dem.tif"))

    result = request(app_module.app, "post", f"/api/runs/{run['run_id']}/analyze", headers=auth())
    assert result.status_code == 200
    payload = result.json()
    assert payload["template_id"] == "terrain-gis-analysis"
    assert payload["template_version"] == "1.0.0"
    assert payload["status"] == "completed"

    stored = operations.get_run(app_module.CONFIG, run["run_id"])
    assert stored["template_id"] == "terrain-gis-analysis"
    assert stored["template_version"] == "1.0.0"


def test_geominilm_recommendation_requires_explicit_approval(app_module, geominilm_checkpoint):
    project, run = create_project_and_run(app_module.app)

    recommendation = request(
        app_module.app,
        "post",
        f"/api/runs/{run['run_id']}/recommendation",
        headers=auth(),
    )
    assert recommendation.status_code == 200
    assert recommendation.json()["status"] == "pending_approval"
    assert "confidence" in recommendation.json()
    assert recommendation.json()["predicted_workflow"]

    blocked = request(app_module.app, "post", f"/api/runs/{run['run_id']}/analyze", headers=auth())
    assert blocked.status_code == 200
    assert blocked.json()["error_code"] == "recommendation_not_approved"

    approved = request(
        app_module.app,
        "post",
        f"/api/runs/{run['run_id']}/recommendation/approve",
        headers=auth(),
    )
    assert approved.status_code == 200
    assert approved.json()["recommendation"]["status"] == "approved"
    assert approved.json()["recommendation"]["approved_by_user_id"] == "user-1"


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


def test_first_party_signup_login_logout_and_user_isolation(app_module):
    async def browser_flow():
        async with AsyncClient(transport=ASGITransport(app=app_module.app), base_url="http://testserver") as alice:
            signup = await alice.post(
                "/signup",
                data={
                    "email": "Alice@example.com",
                    "display_name": "Alice",
                    "password": "correct horse battery staple",
                    "next": "/",
                },
                follow_redirects=False,
            )
            assert signup.status_code == 303
            assert signup.headers["location"] == "/"
            assert "geovis_session" in signup.headers["set-cookie"]

            me = await alice.get("/api/auth/me")
            assert me.status_code == 200
            assert me.json()["user"]["email"] == "alice@example.com"

            project = await alice.post(
                "/api/projects",
                json={"name": "Alice Project", "description": "Private"},
            )
            assert project.status_code == 200
            alice_project = project.json()

            logout = await alice.post("/logout", follow_redirects=False)
            assert logout.status_code == 303
            assert (await alice.get("/api/projects")).status_code == 401

            login = await alice.post(
                "/login",
                data={"email": "alice@example.com", "password": "correct horse battery staple", "next": "/"},
                follow_redirects=False,
            )
            assert login.status_code == 303
            assert (await alice.get(f"/api/projects/{alice_project['id']}")).status_code == 200

        async with AsyncClient(transport=ASGITransport(app=app_module.app), base_url="http://testserver") as bob:
            bob_signup = await bob.post(
                "/api/auth/signup",
                json={
                    "email": "bob@example.com",
                    "display_name": "Bob",
                    "password": "correct horse battery staple",
                },
            )
            assert bob_signup.status_code == 200
            assert bob_signup.json()["user"]["email"] == "bob@example.com"

            forbidden = await bob.get(f"/api/projects/{alice_project['id']}")
            assert forbidden.status_code == 404

            projects = await bob.get("/api/projects")
            assert projects.status_code == 200
            assert projects.json()["projects"] == []

    asyncio.run(browser_flow())


def test_project_invitations_grant_read_only_access_and_can_be_revoked(app_module):
    alice = seed_dashboard_user(app_module, "alice", "alice@example.com", "Alice")
    bob = seed_dashboard_user(app_module, "bob", "bob@example.com", "Bob")
    seed_dashboard_user(app_module, "charlie", "charlie@example.com", "Charlie")

    project_response = request(
        app_module.app,
        "post",
        "/api/projects",
        headers=auth(alice["id"]),
        json={"name": "Shared Project", "description": "Membership test"},
    )
    assert project_response.status_code == 200
    project = project_response.json()

    missing = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/invitations",
        headers=auth(alice["id"]),
        json={"email": "missing@example.com"},
    )
    assert missing.status_code == 404

    invite = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/invitations",
        headers=auth(alice["id"]),
        json={"email": "bob@example.com"},
    )
    assert invite.status_code == 200
    assert invite.json()["member"]["role"] == "viewer"
    assert invite.json()["member"]["user_id"] == bob["id"]

    shared_project = request(app_module.app, "get", f"/api/projects/{project['id']}", headers=auth(bob["id"]))
    assert shared_project.status_code == 200
    assert shared_project.json()["id"] == project["id"]

    bob_projects = request(app_module.app, "get", "/api/projects", headers=auth(bob["id"]))
    assert bob_projects.status_code == 200
    assert [item["id"] for item in bob_projects.json()["projects"]] == [project["id"]]

    read_only = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/runs",
        headers=auth(bob["id"]),
        json={"name": "Blocked collaborator run", "workflow_type": "terrain"},
    )
    assert read_only.status_code == 403

    member_admin = request(app_module.app, "get", f"/api/projects/{project['id']}/members", headers=auth(bob["id"]))
    assert member_admin.status_code == 403

    concealed = request(app_module.app, "get", f"/api/projects/{project['id']}", headers=auth("charlie"))
    assert concealed.status_code == 404

    members = request(app_module.app, "get", f"/api/projects/{project['id']}/members", headers=auth(alice["id"]))
    assert members.status_code == 200
    assert [member["user_id"] for member in members.json()["members"]] == [bob["id"]]

    revoke = request(
        app_module.app,
        "delete",
        f"/api/projects/{project['id']}/members/{bob['id']}",
        headers=auth(alice["id"]),
    )
    assert revoke.status_code == 200
    assert revoke.json()["revoked_user_id"] == bob["id"]

    revoked_project = request(app_module.app, "get", f"/api/projects/{project['id']}", headers=auth(bob["id"]))
    assert revoked_project.status_code == 404

    audit = request(app_module.app, "get", f"/api/projects/{project['id']}/audit-events", headers=auth(alice["id"]))
    assert audit.status_code == 200
    assert [event["event_type"] for event in audit.json()["events"]] == [
        "project.created",
        "project.member_invited",
        "project.member_revoked",
    ]
    assert audit.json()["events"][0]["actor_user_id"] == alice["id"]


def test_report_comments_permissions_history_sanitization_and_audit(app_module):
    operations = sys.modules["geovis_lm.dashboard.operations"]
    owner = seed_dashboard_user(app_module, "owner-user", "owner@example.com", "Owner")
    collaborator = seed_dashboard_user(app_module, "collab-user", "collab@example.com", "Collaborator")
    outsider = seed_dashboard_user(app_module, "outside-user", "outside@example.com", "Outsider")

    project_response = request(
        app_module.app,
        "post",
        "/api/projects",
        headers=auth(owner["id"]),
        json={"name": "Commented Project"},
    )
    assert project_response.status_code == 200
    project = project_response.json()
    run_response = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/runs",
        headers=auth(owner["id"]),
        json={"name": "Report Run", "workflow_type": "terrain"},
    )
    assert run_response.status_code == 200
    run = run_response.json()
    report_path = operations.run_dir(app_module.CONFIG, run["run_id"]) / "reports" / "terrain_analysis.md"
    report_path.write_text("# Terrain Report\n", encoding="utf-8")
    operations.update_run(
        app_module.CONFIG,
        run["run_id"],
        status="reported",
        status_message="Report generated",
        outputs={"report_md": str(report_path)},
    )

    no_report_project, no_report_run = create_project_and_run(app_module.app)
    no_report = request(
        app_module.app,
        "get",
        f"/api/runs/{no_report_run['run_id']}/report/comments",
        headers=auth(),
    )
    assert no_report.status_code == 404
    assert no_report.json()["detail"] == "Report not found"
    assert no_report_project["id"] != project["id"]

    invite = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/invitations",
        headers=auth(owner["id"]),
        json={"email": collaborator["email"]},
    )
    assert invite.status_code == 200

    owner_comment = request(
        app_module.app,
        "post",
        f"/api/runs/{run['run_id']}/report/comments",
        headers=auth(owner["id"]),
        json={"body_markdown": "**Review** this output."},
    )
    assert owner_comment.status_code == 200
    assert owner_comment.json()["author_user_id"] == owner["id"]

    create = request(
        app_module.app,
        "post",
        f"/api/runs/{run['run_id']}/report/comments",
        headers=auth(collaborator["id"]),
        json={"body_markdown": "**Looks good** <script>alert(1)</script> [bad](javascript:alert(1))"},
    )
    assert create.status_code == 200
    comment = create.json()
    assert comment["author_user_id"] == collaborator["id"]
    assert "<strong>Looks good</strong>" in comment["body_html"]
    assert "<script" not in comment["body_html"]
    assert "javascript:" not in comment["body_html"]

    outsider_list = request(
        app_module.app,
        "get",
        f"/api/runs/{run['run_id']}/report/comments",
        headers=auth(outsider["id"]),
    )
    assert outsider_list.status_code == 404

    owner_edit_collaborator = request(
        app_module.app,
        "patch",
        f"/api/runs/{run['run_id']}/report/comments/{comment['id']}",
        headers=auth(owner["id"]),
        json={"body_markdown": "Owner edit"},
    )
    assert owner_edit_collaborator.status_code == 403

    edited = request(
        app_module.app,
        "patch",
        f"/api/runs/{run['run_id']}/report/comments/{comment['id']}",
        headers=auth(collaborator["id"]),
        json={"body_markdown": "Updated **note**"},
    )
    assert edited.status_code == 200
    assert edited.json()["body_markdown"] == "Updated **note**"
    assert edited.json()["edit_history"][0]["previous_body_markdown"] == comment["body_markdown"]
    assert edited.json()["edit_history"][0]["edited_by_user_id"] == collaborator["id"]

    collaborator_resolve = request(
        app_module.app,
        "post",
        f"/api/runs/{run['run_id']}/report/comments/{comment['id']}/resolve",
        headers=auth(collaborator["id"]),
    )
    assert collaborator_resolve.status_code == 403

    resolved = request(
        app_module.app,
        "post",
        f"/api/runs/{run['run_id']}/report/comments/{comment['id']}/resolve",
        headers=auth(owner["id"]),
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["resolved_by_user_id"] == owner["id"]

    reopened = request(
        app_module.app,
        "post",
        f"/api/runs/{run['run_id']}/report/comments/{comment['id']}/reopen",
        headers=auth(owner["id"]),
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "open"
    assert reopened.json()["resolved_by_user_id"] is None

    deleted = request(
        app_module.app,
        "delete",
        f"/api/runs/{run['run_id']}/report/comments/{comment['id']}",
        headers=auth(owner["id"]),
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted_comment_id"] == comment["id"]

    hidden_comment = request(
        app_module.app,
        "get",
        f"/api/runs/{run['run_id']}/report/comments/{comment['id']}",
        headers=auth(collaborator["id"]),
    )
    assert hidden_comment.status_code == 404

    remaining = request(
        app_module.app,
        "get",
        f"/api/runs/{run['run_id']}/report/comments",
        headers=auth(owner["id"]),
    )
    assert remaining.status_code == 200
    assert [item["id"] for item in remaining.json()["comments"]] == [owner_comment.json()["id"]]

    audit = request(app_module.app, "get", f"/api/projects/{project['id']}/audit-events", headers=auth(owner["id"]))
    assert audit.status_code == 200
    comment_events = [event["event_type"] for event in audit.json()["events"] if event["event_type"].startswith("report_comment.")]
    assert comment_events == [
        "report_comment.created",
        "report_comment.created",
        "report_comment.edited",
        "report_comment.resolved",
        "report_comment.reopened",
        "report_comment.deleted",
    ]


def test_signup_invite_code_is_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOVIS_OUTPUT_ROOT", str(tmp_path / "outputs"))
    monkeypatch.setenv("GEOVIS_REQUIRE_AUTH", "true")
    monkeypatch.setenv("GEOVIS_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("GEOVIS_SIGNUP_ENABLED", "true")
    monkeypatch.setenv("GEOVIS_SIGNUP_INVITE_CODE", "invite-only")
    monkeypatch.setenv("GEOVIS_SESSION_COOKIE_SECURE", "false")

    for module_name in ("geovis_lm.dashboard.app", "geovis_lm.dashboard.operations"):
        sys.modules.pop(module_name, None)
    app_module = importlib.import_module("geovis_lm.dashboard.app")

    missing_invite = request(
        app_module.app,
        "post",
        "/api/auth/signup",
        json={"email": "user@example.com", "password": "correct horse battery staple"},
    )
    assert missing_invite.status_code == 403

    accepted = request(
        app_module.app,
        "post",
        "/api/auth/signup",
        json={
            "email": "user@example.com",
            "password": "correct horse battery staple",
            "invite_code": "invite-only",
        },
    )
    assert accepted.status_code == 200


def test_deactivated_account_loses_existing_session(app_module):
    from geovis_lm.dashboard.operations import set_user_active

    async def browser_flow():
        async with AsyncClient(transport=ASGITransport(app=app_module.app), base_url="http://testserver") as client:
            signup = await client.post(
                "/api/auth/signup",
                json={"email": "disabled@example.com", "password": "correct horse battery staple"},
            )
            assert signup.status_code == 200

            set_user_active(app_module.CONFIG, "disabled@example.com", False)
            response = await client.get("/api/projects")
            assert response.status_code == 401

    asyncio.run(browser_flow())


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

    assert response.status_code == 404


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


def test_staged_shapefile_bundle_uploads_as_one_dataset(app_module, tmp_path):
    import geopandas as gpd
    from shapely.geometry import Point

    source = tmp_path / "roads.shp"
    gpd.GeoDataFrame({"name": ["Main"]}, geometry=[Point(0, 0)], crs="EPSG:4326").to_file(source)
    parts = sorted(tmp_path.glob("roads.*"))
    project, run = create_project_and_run(app_module.app)
    base = f"/api/projects/{project['id']}/runs/{run['run_id']}"
    created = request(app_module.app, "post", f"{base}/batches", headers=auth(), json={"files": [
        {"filename": path.name, "size_bytes": path.stat().st_size} for path in parts
    ]})
    assert created.status_code == 200
    batch_id = created.json()["batch_id"]
    incomplete = request(app_module.app, "post", f"{base}/batches/{batch_id}/complete", headers=auth())
    assert incomplete.status_code == 400
    assert incomplete.json()["detail"]["error_code"] == "batch_incomplete"
    for index, path in enumerate(parts):
        uploaded = request(app_module.app, "put", f"{base}/batches/{batch_id}/files/{index}", headers=auth(), content=path.read_bytes())
        assert uploaded.status_code == 200
        assert uploaded.json()["bytes_uploaded"] == path.stat().st_size
    completed = request(app_module.app, "post", f"{base}/batches/{batch_id}/complete", headers=auth())
    assert completed.status_code == 200
    data = completed.json()
    assert data["batch_status"] == "valid"
    assert {item["dataset_id"] for item in data["files"]} == {"roads"}
    assert all(item["status"] == "valid" for item in data["files"])
    assert all(Path(item["path"]).exists() for item in data["files"])
    assert request(app_module.app, "post", f"{base}/batches/{batch_id}/complete", headers=auth()).status_code == 200


def test_multipart_shapefile_bundle_and_mixed_validation(app_module, tmp_path):
    import geopandas as gpd
    from shapely.geometry import Point

    source = tmp_path / "roads.shp"
    gpd.GeoDataFrame({"name": ["Main"]}, geometry=[Point(0, 0)], crs="EPSG:4326").to_file(source)
    parts = sorted(tmp_path.glob("roads.*"))
    project, run = create_project_and_run(app_module.app)
    base = f"/api/projects/{project['id']}/runs/{run['run_id']}"
    response = request(app_module.app, "post", f"{base}/files/multipart", headers=auth(), files=[
        ("files", (path.name, path.read_bytes(), "application/octet-stream")) for path in parts
    ])
    assert response.status_code == 200, response.text
    assert response.json()["batch_status"] == "valid"
    assert {item["dataset_id"] for item in response.json()["files"]} == {"roads"}
    assert all(item["status"] == "valid" for item in response.json()["files"])

    second = request(app_module.app, "post", f"{base}/files/multipart", headers=auth(), files=[
        ("files", ("table.csv", b"a,b\n1,2\n", "text/csv")),
        ("files", ("broken.geojson", b"not geojson", "application/geo+json")),
    ])
    assert second.status_code == 200
    assert second.json()["batch_status"] == "completed_with_errors"
    by_name = {item["stored_filename"]: item for item in second.json()["files"]}
    assert by_name["table.csv"]["status"] == "valid"
    assert by_name["broken.geojson"]["status"] == "invalid"
    assert by_name["broken.geojson"]["validation_errors"][0]["filename"] == "broken.geojson"
    assert by_name["broken.geojson"]["path"] is None


def test_shapefile_without_crs_is_reported_before_analysis(app_module, tmp_path):
    import geopandas as gpd
    from shapely.geometry import Point

    source = tmp_path / "roads.shp"
    gpd.GeoDataFrame({"name": ["Main"]}, geometry=[Point(0, 0)], crs="EPSG:4326").to_file(source)
    (tmp_path / "roads.prj").unlink()
    project, run = create_project_and_run(app_module.app)
    parts = sorted(tmp_path.glob("roads.*"))
    uploads = [("files", (path.name, path.read_bytes(), "application/octet-stream")) for path in parts]
    uploads.append(("files", ("sample_dem.tif", Path("data/sample/sample_dem.tif").read_bytes(), "image/tiff")))
    response = request(
        app_module.app, "post", f"/api/projects/{project['id']}/runs/{run['run_id']}/files/multipart",
        headers=auth(), files=uploads,
    )
    assert response.status_code == 200
    shapefile = next(item for item in response.json()["files"] if item["extension"] == ".shp")
    assert shapefile["status"] == "valid"
    assert any(warning["warning_code"] == "missing_crs" for warning in shapefile["warnings"])
    analyzed = request(app_module.app, "post", f"/api/runs/{run['run_id']}/analyze", headers=auth())
    assert analyzed.status_code == 200
    assert analyzed.json()["status"] == "failed"
    assert analyzed.json()["error_code"] == "missing_crs"


def test_multipart_upload_rejects_quotas_and_partial_bundle(app_module):
    from dataclasses import replace

    project, run = create_project_and_run(app_module.app)
    base = f"/api/projects/{project['id']}/runs/{run['run_id']}"
    forbidden = request(app_module.app, "post", f"{base}/files/multipart", headers=auth("user-2"), files=[
        ("files", ("a.csv", b"a,b\n1,2\n", "text/csv")),
    ])
    assert forbidden.status_code == 404
    app_module.CONFIG = replace(app_module.CONFIG, max_project_bytes=20)
    quota = request(app_module.app, "post", f"{base}/files/multipart", headers=auth(), files=[
        ("files", ("large.csv", b"a,b\n" + b"1,2\n" * 6, "text/csv")),
    ])
    assert quota.status_code == 413
    assert quota.json()["detail"]["error_code"] == "project_quota_exceeded"
    assert not request(app_module.app, "get", f"/api/runs/{run['run_id']}", headers=auth()).json()["inputs"]

    partial = request(app_module.app, "post", f"{base}/files/multipart", headers=auth(), files=[
        ("files", ("roads.shp", b"xx", "application/octet-stream")),
        ("files", ("roads.shx", b"xx", "application/octet-stream")),
    ])
    assert partial.status_code == 200
    assert partial.json()["batch_status"] == "completed_with_errors"
    assert all(item["validation_errors"][0]["error_code"] == "missing_shapefile_component" for item in partial.json()["files"])
    assert all(item["path"] is None for item in partial.json()["files"])


def test_multipart_chunked_upload_is_bounded_without_content_length(app_module):
    from dataclasses import replace

    project, run = create_project_and_run(app_module.app)
    app_module.CONFIG = replace(app_module.CONFIG, max_upload_batch_bytes=8)
    boundary = b"geovis-test-boundary"
    body = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="files"; filename="large.csv"\r\n'
        b"Content-Type: text/csv\r\n\r\n"
        + b"x" * (1024 * 1024 + 32)
        + b"\r\n--" + boundary + b"--\r\n"
    )

    async def chunks():
        yield body[:512000]
        yield body[512000:]

    response = request(
        app_module.app, "post",
        f"/api/projects/{project['id']}/runs/{run['run_id']}/files/multipart",
        headers={**auth(), "content-type": f"multipart/form-data; boundary={boundary.decode()}"},
        content=chunks(),
    )
    assert response.status_code == 413
    assert response.json()["detail"]["error_code"] == "batch_too_large"


def test_legacy_raw_dem_upload_streams_and_enforces_file_limit(app_module):
    from dataclasses import replace

    _project, run = create_project_and_run(app_module.app)
    payload = Path("data/sample/sample_dem.tif").read_bytes()
    app_module.CONFIG = replace(app_module.CONFIG, max_upload_file_bytes=len(payload) - 1)
    rejected = request(
        app_module.app, "post", f"/api/runs/{run['run_id']}/upload-dem?filename=sample_dem.tif",
        headers=auth(), content=payload,
    )
    assert rejected.status_code == 413
    assert rejected.json()["detail"]["error_code"] == "file_too_large"
    assert not request(app_module.app, "get", f"/api/runs/{run['run_id']}", headers=auth()).json()["inputs"]

    app_module.CONFIG = replace(app_module.CONFIG, max_upload_file_bytes=len(payload) + 1)
    uploaded = request(
        app_module.app, "post", f"/api/runs/{run['run_id']}/upload-dem?filename=sample_dem.tif",
        headers=auth(), content=payload,
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["inputs"][0]["status"] == "valid"


def test_staged_upload_rejects_partial_bundle_and_cleans_invalid_bytes(app_module):
    project, run = create_project_and_run(app_module.app)
    base = f"/api/projects/{project['id']}/runs/{run['run_id']}"
    created = request(app_module.app, "post", f"{base}/batches", headers=auth(), json={"files": [
        {"filename": "roads.shp", "size_bytes": 2}, {"filename": "roads.shx", "size_bytes": 2}
    ]})
    batch_id = created.json()["batch_id"]
    for index in range(2):
        assert request(app_module.app, "put", f"{base}/batches/{batch_id}/files/{index}", headers=auth(), content=b"xx").status_code == 200
    completed = request(app_module.app, "post", f"{base}/batches/{batch_id}/complete", headers=auth())
    assert completed.json()["batch_status"] == "completed_with_errors"
    for item in completed.json()["files"]:
        assert item["status"] == "invalid"
        assert item["path"] is None
        assert item["validation_errors"][0]["error_code"] == "missing_shapefile_component"


def test_staged_upload_quota_authorization_and_cleanup(app_module, tmp_path):
    from dataclasses import replace
    from datetime import datetime, timedelta, timezone

    project, run = create_project_and_run(app_module.app)
    base = f"/api/projects/{project['id']}/runs/{run['run_id']}"
    app_module.CONFIG = replace(app_module.CONFIG, max_project_bytes=20)
    forbidden = request(app_module.app, "post", f"{base}/batches", headers=auth("user-2"), json={"files": [{"filename": "a.csv", "size_bytes": 8}]})
    assert forbidden.status_code == 404
    too_large = request(app_module.app, "post", f"{base}/batches", headers=auth(), json={"files": [{"filename": "a.csv", "size_bytes": 21}]})
    assert too_large.status_code == 413
    assert too_large.json()["detail"]["error_code"] == "project_quota_exceeded"
    created = request(app_module.app, "post", f"{base}/batches", headers=auth(), json={"files": [{"filename": "a.csv", "size_bytes": 8}]})
    batch_id = created.json()["batch_id"]
    wrong_size = request(app_module.app, "put", f"{base}/batches/{batch_id}/files/0", headers=auth(), content=b"short")
    assert wrong_size.status_code == 400
    assert wrong_size.json()["detail"]["error_code"] == "size_mismatch"
    operations = sys.modules["geovis_lm.dashboard.operations"]
    directory = operations.batch_dir(app_module.CONFIG, run["run_id"], batch_id)
    assert not list(directory.glob("*.part"))
    removed = operations.cleanup_abandoned_uploads(app_module.CONFIG, project["id"], now=datetime.now(timezone.utc) + timedelta(hours=25))
    assert removed == 1
    assert not directory.exists()


def test_staged_batch_metadata_is_bounded_before_json_parsing(app_module):
    from dataclasses import replace

    project, run = create_project_and_run(app_module.app)
    base = f"/api/projects/{project['id']}/runs/{run['run_id']}/batches"
    oversized = request(
        app_module.app,
        "post",
        base,
        headers={**auth(), "content-type": "application/json"},
        content=b'{"files":[],"padding":"' + b"x" * (64 * 1024) + b'"}',
    )
    assert oversized.status_code == 413
    assert oversized.json()["detail"]["error_code"] == "batch_metadata_too_large"

    long_filename = request(
        app_module.app,
        "post",
        base,
        headers=auth(),
        json={"files": [{"filename": "a" * 256 + ".csv", "size_bytes": 1}]},
    )
    assert long_filename.status_code == 422

    too_many = request(
        app_module.app,
        "post",
        base,
        headers=auth(),
        json={"files": [{"filename": f"{index}.csv", "size_bytes": 1} for index in range(51)]},
    )
    assert too_many.status_code == 413

    app_module.CONFIG = replace(app_module.CONFIG, max_batch_files=55)
    configured_limit = request(
        app_module.app,
        "post",
        base,
        headers=auth(),
        json={"files": [{"filename": f"configured-{index}.csv", "size_bytes": 0} for index in range(51)]},
    )
    assert configured_limit.status_code == 200, configured_limit.text

    over_configured_limit = request(
        app_module.app,
        "post",
        base,
        headers=auth(),
        json={"files": [{"filename": f"over-{index}.csv", "size_bytes": 0} for index in range(56)]},
    )
    assert over_configured_limit.status_code == 413


def test_interrupted_batch_releases_unused_quota_and_can_resume_or_cancel(app_module):
    from dataclasses import replace

    project, run = create_project_and_run(app_module.app)
    base = f"/api/projects/{project['id']}/runs/{run['run_id']}/batches"
    app_module.CONFIG = replace(app_module.CONFIG, max_project_bytes=20)
    created = request(app_module.app, "post", base, headers=auth(), json={"files": [
        {"filename": "a.csv", "size_bytes": 8}, {"filename": "b.csv", "size_bytes": 8},
    ]})
    assert created.status_code == 200
    batch_id = created.json()["batch_id"]
    assert request(app_module.app, "put", f"{base}/{batch_id}/files/0", headers=auth(), content=b"a,b\n1,2\n").status_code == 200
    failed = request(app_module.app, "put", f"{base}/{batch_id}/files/1", headers=auth(), content=b"short")
    assert failed.status_code == 400
    status = request(app_module.app, "get", f"{base}/{batch_id}", headers=auth()).json()
    assert status["status"] == "interrupted"
    assert [item["status"] for item in status["files"]] == ["uploaded", "pending"]

    other = request(app_module.app, "post", base, headers=auth(), json={"files": [{"filename": "c.csv", "size_bytes": 12}]})
    assert other.status_code == 200
    blocked = request(app_module.app, "put", f"{base}/{batch_id}/files/1", headers=auth(), content=b"a,b\n1,2\n")
    assert blocked.status_code == 413
    assert blocked.json()["detail"]["error_code"] == "project_quota_exceeded"
    assert request(app_module.app, "delete", f"{base}/{other.json()['batch_id']}", headers=auth()).status_code == 200
    assert request(app_module.app, "put", f"{base}/{batch_id}/files/1", headers=auth(), content=b"a,b\n1,2\n").status_code == 200
    assert request(app_module.app, "post", f"{base}/{batch_id}/complete", headers=auth()).json()["batch_status"] == "valid"
    assert request(app_module.app, "delete", f"{base}/{batch_id}", headers=auth()).status_code == 400


def test_partial_validation_retains_only_accepted_file_bytes(app_module):
    from dataclasses import replace

    project, run = create_project_and_run(app_module.app)
    base = f"/api/projects/{project['id']}/runs/{run['run_id']}/batches"
    app_module.CONFIG = replace(app_module.CONFIG, max_project_bytes=20)
    created = request(app_module.app, "post", base, headers=auth(), json={"files": [
        {"filename": "valid.csv", "size_bytes": 8}, {"filename": "bad.geojson", "size_bytes": 4},
    ]})
    batch_id = created.json()["batch_id"]
    assert request(app_module.app, "put", f"{base}/{batch_id}/files/0", headers=auth(), content=b"a,b\n1,2\n").status_code == 200
    assert request(app_module.app, "put", f"{base}/{batch_id}/files/1", headers=auth(), content=b"oops").status_code == 200
    result = request(app_module.app, "post", f"{base}/{batch_id}/complete", headers=auth()).json()
    assert result["batch_status"] == "completed_with_errors"
    assert [item["status"] for item in result["files"]] == ["valid", "invalid"]
    assert request(app_module.app, "post", base, headers=auth(), json={"files": [{"filename": "more.csv", "size_bytes": 12}]}).status_code == 200
    blocked = request(app_module.app, "post", base, headers=auth(), json={"files": [{"filename": "too.csv", "size_bytes": 1}]})
    assert blocked.status_code == 413


def test_cancel_partially_uploaded_batch_releases_staged_quota(app_module):
    from dataclasses import replace

    operations = sys.modules["geovis_lm.dashboard.operations"]
    project, run = create_project_and_run(app_module.app)
    base = f"/api/projects/{project['id']}/runs/{run['run_id']}/batches"
    app_module.CONFIG = replace(app_module.CONFIG, max_project_bytes=16)
    created = request(app_module.app, "post", base, headers=auth(), json={"files": [
        {"filename": "a.csv", "size_bytes": 8}, {"filename": "b.csv", "size_bytes": 8},
    ]})
    batch_id = created.json()["batch_id"]
    assert request(app_module.app, "put", f"{base}/{batch_id}/files/0", headers=auth(), content=b"a,b\n1,2\n").status_code == 200
    assert operations.project_upload_bytes(app_module.CONFIG, project["id"]) == 16
    assert request(app_module.app, "delete", f"{base}/{batch_id}", headers=auth("user-2")).status_code == 404
    assert operations.project_upload_bytes(app_module.CONFIG, project["id"]) == 16
    assert request(app_module.app, "delete", f"{base}/{batch_id}", headers=auth()).status_code == 200
    assert operations.project_upload_bytes(app_module.CONFIG, project["id"]) == 0
    assert request(app_module.app, "post", base, headers=auth(), json={"files": [{"filename": "retry.csv", "size_bytes": 16}]}).status_code == 200


def test_finalization_and_queue_are_serialized_and_stale_upload_is_rejected(app_module, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    operations = sys.modules["geovis_lm.dashboard.operations"]
    project, run = create_project_and_run(app_module.app)
    base = f"/api/projects/{project['id']}/runs/{run['run_id']}/batches"

    def staged_csv(name):
        created = request(app_module.app, "post", base, headers=auth(), json={"files": [{"filename": name, "size_bytes": 8}]})
        batch_id = created.json()["batch_id"]
        assert request(app_module.app, "put", f"{base}/{batch_id}/files/0", headers=auth(), content=b"a,b\n1,2\n").status_code == 200
        return batch_id

    first = staged_csv("first.csv")
    entered, release = Event(), Event()
    original = operations.validate_file_content

    def pause_validation(path, extension):
        entered.set()
        assert release.wait(5)
        return original(path, extension)

    monkeypatch.setattr(operations, "validate_file_content", pause_validation)
    with ThreadPoolExecutor(max_workers=2) as pool:
        finalize = pool.submit(request, app_module.app, "post", f"{base}/{first}/complete", headers=auth())
        assert entered.wait(5)
        queue = pool.submit(request, app_module.app, "post", f"/api/runs/{run['run_id']}/queue", headers=auth())
        assert not queue.done()
        release.set()
        assert finalize.result(timeout=5).status_code == 200
        assert queue.result(timeout=5).json()["status"] == "queued"
    assert operations.get_run(app_module.CONFIG, run["run_id"])["status"] == "queued"

    # An upload that reached the server first may still finalize after queueing.
    second_project, second_run = create_project_and_run(app_module.app)
    second_base = f"/api/projects/{second_project['id']}/runs/{second_run['run_id']}/batches"
    created = request(app_module.app, "post", second_base, headers=auth(), json={"files": [{"filename": "later.csv", "size_bytes": 8}]})
    second = created.json()["batch_id"]
    assert request(app_module.app, "put", f"{second_base}/{second}/files/0", headers=auth(), content=b"a,b\n1,2\n").status_code == 200
    assert request(app_module.app, "post", f"/api/runs/{second_run['run_id']}/queue", headers=auth()).status_code == 200
    stale = request(app_module.app, "post", f"{second_base}/{second}/complete", headers=auth())
    assert stale.status_code == 400
    assert operations.get_run(app_module.CONFIG, second_run["run_id"])["status"] == "queued"
    assert operations.get_upload_batch(app_module.CONFIG, second_run["run_id"], second)["status"] == "failed"
    assert operations.project_upload_bytes(app_module.CONFIG, second_project["id"]) == 0


def test_running_analysis_cannot_be_overwritten_by_staged_finalization(app_module, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    operations = sys.modules["geovis_lm.dashboard.operations"]
    project, run = create_project_and_run(app_module.app)
    upload = request(app_module.app, "post", f"/api/projects/{project['id']}/runs/{run['run_id']}/files", headers=auth(), json={
        "files": [{"filename": "sample_dem.tif", "content_b64": b64(Path("data/sample/sample_dem.tif"))}]
    })
    assert upload.status_code == 200
    base = f"/api/projects/{project['id']}/runs/{run['run_id']}/batches"
    created = request(app_module.app, "post", base, headers=auth(), json={"files": [{"filename": "later.csv", "size_bytes": 8}]})
    batch_id = created.json()["batch_id"]
    assert request(app_module.app, "put", f"{base}/{batch_id}/files/0", headers=auth(), content=b"a,b\n1,2\n").status_code == 200
    entered, release = Event(), Event()

    def pause_analysis(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        raise app_module.AnalysisExecutionError("test_stop", "Stopped after concurrency check")

    monkeypatch.setattr(app_module, "execute_dem_analysis", pause_analysis)
    with ThreadPoolExecutor(max_workers=1) as pool:
        analysis = pool.submit(app_module.run_analysis_workflow, run["run_id"])
        assert entered.wait(5)
        assert operations.get_run(app_module.CONFIG, run["run_id"])["status"] == "running"
        stale = request(app_module.app, "post", f"{base}/{batch_id}/complete", headers=auth())
        assert stale.status_code == 400
        assert operations.get_run(app_module.CONFIG, run["run_id"])["status"] == "running"
        assert request(app_module.app, "post", f"/api/runs/{run['run_id']}/cancel", headers=auth()).status_code == 200
        release.set()
        assert analysis.result(timeout=5)["status"] == "canceled"
    assert operations.get_run(app_module.CONFIG, run["run_id"])["status"] == "canceled"


def test_direct_analysis_cannot_bypass_queued_job(app_module):
    from geovis_lm.dashboard.worker import run_worker_once

    project, run = create_project_and_run(app_module.app)
    assert request(app_module.app, "post", f"/api/runs/{run['run_id']}/queue", headers=auth()).status_code == 200
    direct = request(app_module.app, "post", f"/api/runs/{run['run_id']}/analyze", headers=auth())
    assert direct.status_code == 400
    assert request(app_module.app, "get", f"/api/runs/{run['run_id']}", headers=auth()).json()["status"] == "queued"
    result = run_worker_once(app_module.CONFIG, app_module.run_analysis_workflow)
    assert result["status"] == "failed"  # Missing DEM, but the queued job owns the transition.
    assert result["run"]["error_code"] == "missing_dem"


def test_worker_startup_exception_fails_queued_run(app_module):
    from geovis_lm.dashboard.worker import run_worker_once

    _project, run = create_project_and_run(app_module.app)
    assert request(app_module.app, "post", f"/api/runs/{run['run_id']}/queue", headers=auth()).status_code == 200

    def fail_before_start(*_args, **_kwargs):
        raise OSError("initial transition failed")

    result = run_worker_once(app_module.CONFIG, fail_before_start)
    assert result["status"] == "failed"
    failed = sys.modules["geovis_lm.dashboard.operations"].get_run(app_module.CONFIG, run["run_id"])
    assert failed["status"] == "failed"
    assert failed["error_code"] == "worker_failed"
    assert failed["retryable"] is True


def test_staged_batch_locking_runs_off_event_loop(app_module, monkeypatch):
    import threading

    project, run = create_project_and_run(app_module.app)
    caller_thread = threading.get_ident()
    operation_threads = []
    monkeypatch.setattr(app_module, "cleanup_abandoned_uploads", lambda *_: operation_threads.append(threading.get_ident()))

    def create_batch(*_args, **_kwargs):
        operation_threads.append(threading.get_ident())
        return {"batch_id": "batch-test"}

    monkeypatch.setattr(app_module, "create_upload_batch", create_batch)
    response = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/runs/{run['run_id']}/batches",
        headers=auth(),
        json={"files": [{"filename": "a.csv", "size_bytes": 1}]},
    )
    assert response.status_code == 200
    assert response.json()["batch_id"] == "batch-test"
    assert len(operation_threads) == 2
    assert all(thread_id != caller_thread for thread_id in operation_threads)


def test_legacy_json_body_is_bounded_before_parsing(app_module):
    from dataclasses import replace

    project, run = create_project_and_run(app_module.app)
    app_module.CONFIG = replace(app_module.CONFIG, max_upload_batch_bytes=8)
    response = request(app_module.app, "post", f"/api/projects/{project['id']}/runs/{run['run_id']}/files", headers=auth(), content=b"x" * 100)
    assert response.status_code == 413
    assert response.json()["detail"]["error_code"] == "legacy_upload_too_large"

    app_module.CONFIG = replace(app_module.CONFIG, max_upload_batch_bytes=1024)
    malformed = request(app_module.app, "post", f"/api/projects/{project['id']}/runs/{run['run_id']}/files", headers=auth(), content=b"not json")
    assert malformed.status_code == 422
    invalid_schema = request(app_module.app, "post", f"/api/projects/{project['id']}/runs/{run['run_id']}/files", headers=auth(), json={"files": "bad"})
    assert invalid_schema.status_code == 422


def test_concurrent_multipart_uploads_respect_project_quota(app_module):
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace

    project, run = create_project_and_run(app_module.app)
    app_module.CONFIG = replace(app_module.CONFIG, max_project_bytes=12)
    base = f"/api/projects/{project['id']}/runs/{run['run_id']}/files/multipart"
    def upload(name):
        return request(app_module.app, "post", base, headers=auth(), files=[("files", (name, b"a,b\n1,2\n", "text/csv"))])
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(upload, ["a.csv", "b.csv"]))
    assert sorted(result.status_code for result in results) == [200, 413]


def test_multipart_reserves_project_quota_before_reading_body(app_module):
    from dataclasses import replace
    from fastapi import HTTPException
    from starlette.requests import Request
    from geovis_lm.dashboard.operations import MULTIPART_METADATA_OVERHEAD_BYTES

    project, run = create_project_and_run(app_module.app)
    app_module.CONFIG = replace(app_module.CONFIG, max_project_bytes=16)
    received = False

    async def receive():
        nonlocal received
        received = True
        return {"type": "http.request", "body": b"", "more_body": False}

    headers = [
        (b"authorization", b"Bearer test-token"),
        (b"x-geovis-user", b"user-1"),
        (b"x-geovis-role", b"owner"),
        (b"content-type", b"multipart/form-data; boundary=unused"),
        (b"content-length", str(MULTIPART_METADATA_OVERHEAD_BYTES + 17).encode()),
    ]
    request_obj = Request({"type": "http", "method": "POST", "headers": headers}, receive)
    with pytest.raises(HTTPException) as error:
        asyncio.run(app_module.upload_project_run_multipart(project["id"], run["run_id"], request_obj))
    assert error.value.detail["error_code"] == "project_quota_exceeded"
    assert received is False


def test_multipart_rejects_non_file_form_fields(app_module):
    project, run = create_project_and_run(app_module.app)
    response = request(
        app_module.app,
        "post",
        f"/api/projects/{project['id']}/runs/{run['run_id']}/files/multipart",
        headers=auth(),
        files=[
            ("files", ("data.csv", b"a,b\n1,2\n", "text/csv")),
            ("note", (None, "unexpected field")),
        ],
    )
    assert response.status_code == 400


def test_authorization_rejects_cross_user_access(app_module):
    project, _run = create_project_and_run(app_module.app)

    response = request(app_module.app, "get", f"/api/projects/{project['id']}", headers=auth("user-2", "owner"))

    assert response.status_code == 404


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
    assert retry["status"] == "retrying"
    assert retry["retry_of_run_id"] == run["run_id"]
    assert retry["attempt_number"] == 2
    assert "job" not in retry


def test_retry_run_drops_invalid_input_name_reservations(app_module):
    project, run = create_project_and_run(app_module.app)
    base = f"/api/projects/{project['id']}/runs/{run['run_id']}"
    invalid_upload = request(
        app_module.app,
        "post",
        f"{base}/files/multipart",
        headers=auth(),
        files=[("files", ("terrain.tif", b"not a raster", "image/tiff"))],
    )
    assert invalid_upload.status_code == 200
    assert invalid_upload.json()["files"][0]["status"] == "invalid"

    failed = request(app_module.app, "post", f"/api/runs/{run['run_id']}/analyze", headers=auth())
    assert failed.status_code == 200
    assert failed.json()["retryable"] is True

    retry_response = request(app_module.app, "post", f"/api/runs/{run['run_id']}/retry", headers=auth())
    assert retry_response.status_code == 200
    retry = retry_response.json()
    assert retry["inputs"] == []
    assert retry["status"] == "retrying"
    retry_base = f"/api/projects/{project['id']}/runs/{retry['run_id']}/files/multipart"
    corrected = request(
        app_module.app,
        "post",
        retry_base,
        headers=auth(),
        files=[("files", ("terrain.tif", Path("data/sample/sample_dem.tif").read_bytes(), "image/tiff"))],
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["files"][0]["status"] == "valid"
    queued = request(app_module.app, "post", f"/api/runs/{retry['run_id']}/queue", headers=auth())
    assert queued.status_code == 200
    assert queued.json()["status"] == "queued"


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


def test_load_dem_avoids_numpy_masked_shape_deprecation():
    from geovis_lm.gis.terrain import load_dem

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        dem, profile, transform, crs = load_dem(Path("data/sample/sample_dem.tif"))

    assert dem.shape == (profile["height"], profile["width"])
    assert transform == profile["transform"]
    assert crs is not None


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
