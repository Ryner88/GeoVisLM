from __future__ import annotations

from pathlib import Path
import logging
import time
from typing import Callable
from fastapi import HTTPException

from geovis_lm.dashboard.operations import (
    DashboardConfig,
    claim_next_queued_job,
    cleanup_abandoned_uploads,
    get_run,
    list_runs,
    project_upload_lock,
    update_job,
    update_run,
    utc_now,
)


AnalyzeRun = Callable[..., dict]
LOGGER = logging.getLogger(__name__)


def append_job_log(job: dict, message: str) -> None:
    logs_path = Path(job["logs_path"])
    logs_path.parent.mkdir(parents=True, exist_ok=True)
    with logs_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{utc_now()} {message}\n")


def run_worker_once(config: DashboardConfig, analyze_run: AnalyzeRun) -> dict:
    job = claim_next_queued_job(config)
    if job is None:
        return {"status": "idle", "message": "No queued jobs"}

    append_job_log(job, f"Claimed job {job['job_id']} for run {job['run_id']}")
    try:
        run = get_run(config, job["run_id"])
        if run.get("status") != "queued":
            append_job_log(job, f"Run is no longer queued: {run.get('status')}")
            job = update_job(config, job["job_id"], status="canceled")
            return {"status": "canceled", "job": job}

        result = analyze_run(job["run_id"], from_worker=True)
        if result.get("status") == "canceled":
            job = update_job(config, job["job_id"], status="canceled")
            return {"status": "canceled", "job": job, "run": result}
        if result.get("status") == "completed":
            append_job_log(job, "Run completed successfully")
            job = update_job(config, job["job_id"], status="completed")
            return {"status": "completed", "job": job, "run": result}

        append_job_log(job, f"Run finished with status {result.get('status')}: {result.get('error_message')}")
        job = update_job(
            config,
            job["job_id"],
            status="failed",
            error_code=result.get("error_code") or "run_failed",
            error_message=result.get("error_message") or "Run did not complete",
        )
        return {"status": "failed", "job": job, "run": result}
    except Exception as exc:
        append_job_log(job, f"Worker failed: {exc}")
        if isinstance(exc, HTTPException) and isinstance(exc.detail, dict) and exc.detail.get("error_code") == "run_not_ready":
            job = update_job(config, job["job_id"], status="canceled")
            return {"status": "canceled", "job": job, "run": get_run(config, job["run_id"])}
        run = get_run(config, job["run_id"])
        with project_upload_lock(config, run["project_id"]):
            current_run = get_run(config, job["run_id"])
            # The claimed job owns this queued run until analysis changes it to
            # running. Cover failures before that transition too, while the
            # project lock preserves a concurrent cancellation.
            if job.get("status") == "running" and current_run["status"] in {"queued", "running"}:
                update_run(
                    config,
                    job["run_id"],
                    status="failed",
                    status_message="Worker execution failed",
                    error_code="worker_failed",
                    error_message=str(exc),
                    error_detail=repr(exc),
                    retryable=True,
                )
        job = update_job(
            config,
            job["job_id"],
            status="failed",
            error_code="worker_failed",
            error_message=str(exc),
        )
        return {"status": "failed", "job": job}


def run_worker_loop(
    config: DashboardConfig,
    analyze_run: AnalyzeRun,
    *,
    poll_interval_seconds: float = 5.0,
    max_iterations: int | None = None,
) -> None:
    iterations = 0
    next_cleanup_at = 0.0
    while True:
        if time.monotonic() >= next_cleanup_at:
            try:
                project_ids = {run["project_id"] for run in list_runs(config)}
            except Exception:
                LOGGER.exception("Could not list projects for upload cleanup")
                project_ids = set()
            for project_id in project_ids:
                try:
                    cleanup_abandoned_uploads(config, project_id)
                except Exception:
                    LOGGER.exception("Upload cleanup failed for project %s", project_id)
            next_cleanup_at = time.monotonic() + 3600
        result = run_worker_once(config, analyze_run)
        if result["status"] == "idle":
            time.sleep(poll_interval_seconds)
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            return
