from __future__ import annotations

from pathlib import Path
from typing import Callable

from geovis_lm.dashboard.operations import (
    DashboardConfig,
    claim_next_queued_job,
    get_run,
    update_job,
    update_run,
    utc_now,
)


AnalyzeRun = Callable[[str], dict]


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
        if run.get("status") == "canceled":
            append_job_log(job, "Run was canceled before execution")
            job = update_job(config, job["job_id"], status="canceled")
            return {"status": "canceled", "job": job}

        result = analyze_run(job["run_id"])
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
