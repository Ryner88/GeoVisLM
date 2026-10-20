from __future__ import annotations

import base64
import importlib
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from geovis_lm.dashboard.operations import (
    DashboardConfig,
    create_project,
    create_report_comment,
    create_run_record,
    ensure_storage,
    ingest_base64_files,
    invite_project_member,
    list_project_audit_events,
    list_user_notifications,
    mark_user_notification_read,
    run_dir,
    update_run,
    user_notifications_path,
    user_path,
    write_json,
    write_project_members,
)


@pytest.fixture
def config(tmp_path: Path) -> DashboardConfig:
    config = replace(DashboardConfig.from_env(), output_root=tmp_path / "outputs", require_auth=True, auth_token="test-token")
    ensure_storage(config)
    return config


@pytest.fixture
def app_module(config: DashboardConfig, monkeypatch):
    monkeypatch.setenv("GEOVIS_OUTPUT_ROOT", str(config.output_root))
    monkeypatch.setenv("GEOVIS_REQUIRE_AUTH", "true")
    monkeypatch.setenv("GEOVIS_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("GEOVIS_SESSION_SECRET", "test-session-secret")
    sys.modules.pop("geovis_lm.dashboard.app", None)
    return importlib.import_module("geovis_lm.dashboard.app")


def principal_request(user_id: str, role: str = "owner") -> Request:
    headers = [
        (b"authorization", b"Bearer test-token"),
        (b"x-geovis-user", user_id.encode()),
        (b"x-geovis-role", role.encode()),
    ]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def seed_user(config: DashboardConfig, user_id: str, email: str) -> dict:
    user = {
        "id": user_id,
        "email": email,
        "password_hash": "unused",
        "display_name": user_id,
        "role": "owner",
        "active": True,
    }
    write_json(user_path(config, email), user)
    return user


def test_timeline_and_dashboard_are_available_to_project_members_but_not_outsiders(config, app_module):
    owner = seed_user(config, "owner", "owner@example.test")
    member = seed_user(config, "member", "member@example.test")
    project = create_project(config, "Timeline Project", owner["id"])
    invite_project_member(config, project, {"user_id": owner["id"], "role": "owner"}, member["email"])
    run = create_run_record(config, project, owner["id"], name="Analysis")
    update_run(config, run["run_id"], status="completed", status_message="Finished")

    app_module.CONFIG = config
    timeline = app_module.project_timeline_api(project["id"], principal_request(member["id"]), limit=100)
    event_types = [event["event_type"] for event in timeline["events"]]
    assert {"project.created", "project.member_invited", "run.created", "run.status_changed"} <= set(event_types)
    invite_event = next(event for event in timeline["events"] if event["event_type"] == "project.member_invited")
    assert invite_event["details"] == {"message": "Project membership changed"}
    page = app_module.project_page(project["id"], principal_request(member["id"]))
    assert "Project timeline" in page and "run created</strong> Analysis</li>" in page
    with pytest.raises(HTTPException) as denied:
        app_module.project_timeline_api(project["id"], principal_request("outsider"), limit=100)
    assert denied.value.status_code == 404
    with pytest.raises(HTTPException) as raw_audit_denied:
        app_module.list_project_audit_events_api(project["id"], principal_request(member["id"], "viewer"))
    assert raw_audit_denied.value.status_code == 403


def test_invitation_and_run_completion_deliver_private_actionable_notifications(config, app_module):
    owner = seed_user(config, "owner", "owner@example.test")
    member = seed_user(config, "member", "member@example.test")
    project = create_project(config, "Notifications", owner["id"])
    invite_project_member(config, project, {"user_id": owner["id"], "role": "owner"}, member["email"])
    run = create_run_record(config, project, owner["id"], name="Analysis")
    update_run(config, run["run_id"], status="completed")

    app_module.CONFIG = config
    inbox = app_module.notifications_api(principal_request(member["id"], "viewer"), limit=50)
    assert inbox["unread_count"] == 2
    assert {item["event_type"] for item in inbox["notifications"]} == {"project.member_invited", "run.status_changed"}
    assert {item["href"] for item in inbox["notifications"]} == {f"/projects/{project['id']}", f"/runs/{run['run_id']}"}
    dashboard = app_module.index(principal_request(member["id"], "viewer"))
    assert "Notifications" in dashboard and "Mark read" in dashboard

    notification = inbox["notifications"][0]
    marked = mark_user_notification_read(config, {"user_id": member["id"], "role": "viewer"}, notification["id"])
    assert marked["read_at"]
    assert any(
        item["id"] == notification["id"] and item["read_at"]
        for item in list_user_notifications(config, {"user_id": member["id"], "role": "viewer"})
    )
    with pytest.raises(HTTPException) as wrong_user:
        mark_user_notification_read(config, {"user_id": "outsider", "role": "viewer"}, notification["id"])
    assert wrong_user.value.status_code == 404


def test_revoked_member_cannot_read_timeline_notifications_or_follow_old_links(config, app_module):
    owner = seed_user(config, "owner", "owner@example.test")
    member = seed_user(config, "member", "member@example.test")
    project = create_project(config, "Revocation", owner["id"])
    invite_project_member(config, project, {"user_id": owner["id"], "role": "owner"}, member["email"])
    run = create_run_record(config, project, owner["id"], name="Analysis")
    update_run(config, run["run_id"], status="completed")
    inbox_before = list_user_notifications(config, {"user_id": member["id"], "role": "viewer"})
    assert inbox_before
    notification_id = inbox_before[0]["id"]
    write_project_members(config, project["id"], {"members": []})

    app_module.CONFIG = config
    assert list_user_notifications(config, {"user_id": member["id"], "role": "viewer"}) == []
    with pytest.raises(HTTPException) as timeline_denied:
        app_module.project_timeline_api(project["id"], principal_request(member["id"], "viewer"), limit=100)
    assert timeline_denied.value.status_code == 404
    with pytest.raises(HTTPException) as notification_denied:
        mark_user_notification_read(config, {"user_id": member["id"], "role": "viewer"}, notification_id)
    assert notification_denied.value.status_code == 404
    with pytest.raises(HTTPException) as link_denied:
        app_module.run_page(run["run_id"], principal_request(member["id"], "viewer"))
    assert link_denied.value.status_code == 404


def test_upload_report_and_comment_activity_and_comment_notifications(config, app_module):
    owner = seed_user(config, "owner", "owner@example.test")
    member = seed_user(config, "member", "member@example.test")
    project = create_project(config, "Activity", owner["id"])
    write_project_members(config, project["id"], {"members": [{"user_id": member["id"], "role": "viewer"}]})
    run = create_run_record(config, project, owner["id"], name="Analysis")
    ingest_base64_files(
        config,
        run,
        [{"filename": "elevation.csv", "content_b64": base64.b64encode(b"x,y\n1,2\n").decode("ascii")}],
        actor_user_id=member["id"],
    )
    outputs = {}
    for key in ("slope", "hillshade", "terrain_risk"):
        path = run_dir(config, run["run_id"]) / "maps" / f"{key}.tif"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test")
        outputs[key] = str(path)
    run = update_run(config, run["run_id"], outputs=outputs)
    app_module.CONFIG = config
    run = app_module.generate_report(run["run_id"], principal_request(owner["id"]))
    create_report_comment(config, run, project, {"user_id": member["id"], "role": "viewer"}, "Please review.")

    event_types = {event["event_type"] for event in list_project_audit_events(config, project["id"])}
    assert {"upload.completed", "report.generated", "report_comment.created"} <= event_types
    owner_notifications = list_user_notifications(config, {"user_id": owner["id"], "role": "owner"})
    assert any(item["event_type"] == "report_comment.created" and item["href"] == f"/runs/{run['run_id']}" for item in owner_notifications)
    assert list_user_notifications(config, {"user_id": member["id"], "role": "viewer"}) == []


def test_analysis_status_events_keep_the_authenticated_actor(config, app_module):
    owner = seed_user(config, "owner", "owner@example.test")
    project = create_project(config, "Actor", owner["id"])
    run = create_run_record(config, project, owner["id"], name="Missing DEM")
    app_module.CONFIG = config

    result = app_module.analyze_run(run["run_id"], principal_request(owner["id"]))

    assert result["status"] == "failed"
    status_events = [
        event for event in list_project_audit_events(config, project["id"])
        if event["event_type"] == "run.status_changed"
    ]
    assert [event["actor_user_id"] for event in status_events[-2:]] == [owner["id"], owner["id"]]


def test_synchronous_completion_excludes_the_initiator_from_notifications(config):
    owner = seed_user(config, "owner", "owner@example.test")
    member = seed_user(config, "member", "member@example.test")
    project = create_project(config, "Completion", owner["id"])
    invite_project_member(config, project, {"user_id": owner["id"], "role": "owner"}, member["email"])
    run = create_run_record(config, project, owner["id"], name="Analysis")

    update_run(config, run["run_id"], status="completed", actor_user_id=owner["id"])

    owner_notifications = list_user_notifications(config, {"user_id": owner["id"], "role": "owner"})
    member_notifications = list_user_notifications(config, {"user_id": member["id"], "role": "viewer"})
    assert owner_notifications == []
    assert [item["event_type"] for item in member_notifications] == ["run.status_changed", "project.member_invited"]


def test_unread_notification_count_includes_older_unread_items(config, app_module):
    owner = seed_user(config, "owner", "owner@example.test")
    project = create_project(config, "Unread", owner["id"])
    inbox_path = user_notifications_path(config, owner["id"])
    write_json(
        inbox_path,
        {
            "user_id": owner["id"],
            "notifications": [
                {
                    "id": f"notice-{index}",
                    "user_id": owner["id"],
                    "project_id": project["id"],
                    "title": "Analysis update",
                    "message": "Test notice",
                    "href": f"/projects/{project['id']}",
                    "created_at": f"2026-01-{index % 28 + 1:02d}T00:00:00Z",
                    "read_at": None,
                }
                for index in range(503)
            ],
        },
    )
    app_module.CONFIG = config

    result = app_module.notifications_api(principal_request(owner["id"]), limit=50)
    older_page = app_module.notifications_api(principal_request(owner["id"]), limit=50, offset=500)

    assert result["unread_count"] == 503
    assert len(result["notifications"]) == 50
    assert len(older_page["notifications"]) == 3
    dashboard = app_module.index(principal_request(owner["id"]))
    assert "Older notifications" in dashboard
