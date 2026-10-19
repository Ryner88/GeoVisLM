from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import geopandas as gpd
import pytest
from fastapi import HTTPException
from shapely.geometry import Point
from starlette.requests import Request

from geovis_lm.dashboard.operations import (
    DashboardConfig,
    batch_dir,
    cleanup_abandoned_uploads,
    complete_upload_batch,
    create_project,
    create_run_record,
    create_upload_batch,
    project_upload_bytes,
    begin_batch_file_transfer,
    ensure_storage,
    get_upload_batch,
    ingest_file_paths,
    write_json,
)


def setup_run(tmp_path: Path):
    config = replace(DashboardConfig.from_env(), output_root=tmp_path / "outputs")
    ensure_storage(config)
    project = create_project(config, "Test", "owner")
    run = create_run_record(config, project, "owner")
    return config, project, run


def test_complete_shapefile_bundle_is_one_valid_dataset(tmp_path):
    config, _, run = setup_run(tmp_path)
    source = tmp_path / "roads.shp"
    gpd.GeoDataFrame({"name": ["Main"]}, geometry=[Point(0, 0)], crs="EPSG:4326").to_file(source)
    paths = sorted(tmp_path.glob("roads.*"))
    result = ingest_file_paths(config, run, [(path.name, path, None) for path in paths])
    assert result["batch_status"] == "valid"
    assert {item["dataset_id"] for item in result["files"]} == {"roads"}
    assert all(item["status"] == "valid" and Path(item["path"]).exists() for item in result["files"])


def test_shapefile_xml_metadata_uses_dataset_stem(tmp_path):
    config, _, run = setup_run(tmp_path)
    source = tmp_path / "roads.shp"
    gpd.GeoDataFrame({"name": ["Main"]}, geometry=[Point(0, 0)], crs="EPSG:4326").to_file(source)
    metadata = tmp_path / "roads.shp.xml"
    metadata.write_text("<metadata/>")
    paths = sorted(tmp_path.glob("roads.*"))
    result = ingest_file_paths(config, run, [(path.name, path, None) for path in paths])
    assert result["batch_status"] == "valid"
    assert {item["dataset_id"] for item in result["files"]} == {"roads"}


def test_partial_bundle_keeps_errors_and_removes_bytes(tmp_path):
    config, _, run = setup_run(tmp_path)
    path = tmp_path / "roads.shp"
    path.write_bytes(b"xx")
    result = ingest_file_paths(config, run, [(path.name, path, None)])
    assert result["batch_status"] == "completed_with_errors"
    item = result["files"][0]
    assert item["status"] == "invalid" and item["path"] is None
    assert item["validation_errors"][0]["error_code"] == "missing_shapefile_component"


def test_project_quota_and_abandoned_batch_cleanup(tmp_path):
    config, project, run = setup_run(tmp_path)
    config = replace(config, max_project_bytes=20)
    with pytest.raises(HTTPException) as error:
        create_upload_batch(config, run, [{"filename": "a.csv", "size_bytes": 21}])
    assert error.value.status_code == 413
    assert error.value.detail["error_code"] == "project_quota_exceeded"
    batch = create_upload_batch(config, run, [{"filename": "a.csv", "size_bytes": 8}])
    with pytest.raises(HTTPException) as reserved_error:
        create_upload_batch(config, run, [{"filename": "b.csv", "size_bytes": 13}])
    assert reserved_error.value.detail["error_code"] == "project_quota_exceeded"
    directory = batch_dir(config, run["run_id"], batch["batch_id"])
    assert cleanup_abandoned_uploads(config, project["id"], now=datetime.now(timezone.utc) + timedelta(hours=25)) == 1
    assert not directory.exists()


def test_staged_batch_requires_all_files_before_validation(tmp_path):
    config, _, run = setup_run(tmp_path)
    batch = create_upload_batch(config, run, [{"filename": "a.csv", "size_bytes": 8}])
    with pytest.raises(HTTPException) as error:
        complete_upload_batch(config, run, batch["batch_id"])
    assert error.value.detail["error_code"] == "batch_incomplete"
    directory = batch_dir(config, run["run_id"], batch["batch_id"])
    (directory / "a.csv").write_bytes(b"a,b\n1,2\n")
    batch["files"][0]["status"] = "uploaded"
    write_json(directory / "batch.json", batch)
    result = complete_upload_batch(config, run, batch["batch_id"])
    assert result["batch_status"] == "valid"
    assert not (directory / "a.csv").exists()


def test_raw_file_transfer_checks_declared_size_and_records_progress(tmp_path, monkeypatch):
    import geovis_lm.dashboard.app as dashboard_app

    config, project, run = setup_run(tmp_path)
    monkeypatch.setattr(dashboard_app, "CONFIG", replace(config, require_auth=False))
    batch = create_upload_batch(config, run, [{"filename": "a.csv", "size_bytes": 8}])

    def request_with_body(body: bytes) -> Request:
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        return Request({"type": "http", "method": "PUT", "headers": [(b"x-geovis-user", b"owner")]}, receive)

    async def transfer(body: bytes):
        return await dashboard_app.stage_upload_file(project["id"], run["run_id"], batch["batch_id"], 0, request_with_body(body))

    with pytest.raises(HTTPException) as error:
        asyncio.run(transfer(b"short"))
    assert error.value.detail["error_code"] == "size_mismatch"
    assert not list(batch_dir(config, run["run_id"], batch["batch_id"]).glob("*.part"))
    uploaded = asyncio.run(transfer(b"a,b\n1,2\n"))
    assert uploaded["status"] == "uploaded"
    assert uploaded["bytes_uploaded"] == 8

    canceled = create_upload_batch(config, run, [{"filename": "b.csv", "size_bytes": 8}])

    async def disconnect():
        raise asyncio.CancelledError()

    request = Request({"type": "http", "method": "PUT", "headers": [(b"x-geovis-user", b"owner")]}, disconnect)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(dashboard_app.stage_upload_file(project["id"], run["run_id"], canceled["batch_id"], 0, request))
    assert get_upload_batch(config, run["run_id"], canceled["batch_id"])["files"][0]["status"] == "pending"
    assert not list(batch_dir(config, run["run_id"], canceled["batch_id"]).glob("*.part"))


def test_unexpected_validation_failure_removes_uncommitted_bytes(tmp_path, monkeypatch):
    config, _, run = setup_run(tmp_path)
    source = tmp_path / "a.csv"
    source.write_bytes(b"a,b\n1,2\n")

    def crash(_path, _extension):
        raise RuntimeError("parser unavailable")

    monkeypatch.setitem(ingest_file_paths.__globals__, "validate_file_content", crash)
    with pytest.raises(RuntimeError, match="parser unavailable"):
        ingest_file_paths(config, run, [(source.name, source, None)])
    assert not (config.runs_root / run["run_id"] / "inputs" / "raw" / source.name).exists()
    assert not (config.runs_root / run["run_id"] / "inputs" / "validated" / source.name).exists()


def test_manifest_filename_cannot_escape_staging_or_replace_receipt(tmp_path):
    config, _, run = setup_run(tmp_path)
    with pytest.raises(HTTPException) as reserved:
        create_upload_batch(config, run, [{"filename": "batch.json", "size_bytes": 2}])
    assert reserved.value.detail["error_code"] == "unsafe_filename"
    batch = create_upload_batch(config, run, [{"filename": "a.csv", "size_bytes": 8}])
    victim = tmp_path / "victim"
    victim.write_text("safe")
    batch["files"][0]["filename"] = "../../../../../victim"
    write_json(batch_dir(config, run["run_id"], batch["batch_id"]) / "batch.json", batch)
    with pytest.raises(HTTPException):
        complete_upload_batch(config, run, batch["batch_id"])
    assert victim.read_text() == "safe"


def test_batch_creation_idempotency_and_duplicate_name_reservation(tmp_path):
    config, _, run = setup_run(tmp_path)
    files = [{"filename": "a.csv", "size_bytes": 8}]
    first = create_upload_batch(config, run, files, idempotency_key="request-1")
    assert create_upload_batch(config, run, files, idempotency_key="request-1")["batch_id"] == first["batch_id"]
    with pytest.raises(HTTPException) as duplicate:
        create_upload_batch(config, run, files, idempotency_key="request-2")
    assert duplicate.value.detail["error_code"] == "duplicate_filename"


def test_finalization_recovers_committed_inputs_without_double_quota(tmp_path):
    config, project, run = setup_run(tmp_path)
    batch = create_upload_batch(config, run, [{"filename": "a.csv", "size_bytes": 8}])
    directory = batch_dir(config, run["run_id"], batch["batch_id"])
    (directory / "a.csv").write_bytes(b"a,b\n1,2\n")
    batch["files"][0]["status"] = "uploaded"
    write_json(directory / "batch.json", batch)
    original = complete_upload_batch(config, run, batch["batch_id"])
    assert project_upload_bytes(config, project["id"]) == 8
    batch["status"] = "validating"
    write_json(directory / "batch.json", batch)
    assert project_upload_bytes(config, project["id"]) == 8
    recovered = complete_upload_batch(config, run, batch["batch_id"])
    assert recovered["files"][0]["id"] == original["files"][0]["id"]
    assert project_upload_bytes(config, project["id"]) == 8


def test_retry_records_count_each_retained_path_once(tmp_path):
    config, project, run = setup_run(tmp_path)
    source = tmp_path / "a.csv"
    source.write_bytes(b"a,b\n1,2\n")
    ingest_file_paths(config, run, [(source.name, source, None)])
    from geovis_lm.dashboard.operations import get_run
    retained = get_run(config, run["run_id"])["inputs"]
    retry = create_run_record(config, project, "owner")
    write_json(config.runs_root / retry["run_id"] / "metadata.json", {**retry, "inputs": retained})
    assert project_upload_bytes(config, project["id"]) == 8


def test_queued_run_rejects_new_staged_transfer(tmp_path):
    config, _, run = setup_run(tmp_path)
    batch = create_upload_batch(config, run, [{"filename": "a.csv", "size_bytes": 8}])
    from geovis_lm.dashboard.operations import update_run
    update_run(config, run["run_id"], status="queued")
    with pytest.raises(HTTPException) as error:
        begin_batch_file_transfer(config, run["project_id"], run["run_id"], batch["batch_id"], 0)
    assert error.value.detail["error_code"] == "run_not_editable"


def test_worker_continues_when_upload_cleanup_fails(tmp_path, monkeypatch):
    import geovis_lm.dashboard.worker as worker

    config, _, _ = setup_run(tmp_path)
    monkeypatch.setattr(worker, "cleanup_abandoned_uploads", lambda *_: (_ for _ in ()).throw(OSError("cleanup failed")))
    worker.run_worker_loop(config, lambda *_args, **_kwargs: {}, poll_interval_seconds=0, max_iterations=1)
