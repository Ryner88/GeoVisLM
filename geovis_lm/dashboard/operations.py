from __future__ import annotations

import base64
import csv
import hmac
import hashlib
import json
import mimetypes
import os
import re
import secrets
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request


RUN_STATUSES = {
    "created",
    "uploaded",
    "queued",
    "running",
    "completed",
    "failed",
    "canceling",
    "canceled",
    "retrying",
    "reported",
    "archived",
}
PROJECT_STATUSES = {"active", "archived", "deleted"}
ALLOWED_EXTENSIONS = {
    ".tif",
    ".tiff",
    ".geojson",
    ".json",
    ".csv",
    ".shp",
    ".shx",
    ".dbf",
    ".prj",
    ".cpg",
    ".qix",
    ".sbn",
    ".sbx",
    ".xml",
}
SHAPEFILE_REQUIRED = {".shp", ".shx", ".dbf"}
DASHBOARD_SESSION_COOKIE = "geovis_session"
SESSION_TTL_HOURS = 24
ACCOUNT_ROLES = {"admin", "owner", "editor", "viewer"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class DashboardConfig:
    output_root: Path
    max_upload_file_bytes: int
    max_upload_batch_bytes: int
    max_batch_files: int
    require_auth: bool
    auth_token: str | None
    session_secret: str | None
    signup_enabled: bool
    signup_invite_code: str | None
    session_cookie_secure: bool
    database_url: str | None

    @classmethod
    def from_env(cls) -> "DashboardConfig":
        output_root = Path(os.getenv("GEOVIS_OUTPUT_ROOT", "outputs"))
        file_mb = env_int("GEOVIS_MAX_UPLOAD_FILE_MB", 250)
        batch_mb = env_int("GEOVIS_MAX_UPLOAD_BATCH_MB", 1024)
        return cls(
            output_root=output_root,
            max_upload_file_bytes=file_mb * 1024 * 1024,
            max_upload_batch_bytes=batch_mb * 1024 * 1024,
            max_batch_files=env_int("GEOVIS_MAX_BATCH_FILES", 50),
            require_auth=env_bool("GEOVIS_REQUIRE_AUTH", False),
            auth_token=os.getenv("GEOVIS_AUTH_TOKEN"),
            session_secret=os.getenv("GEOVIS_SESSION_SECRET") or os.getenv("GEOVIS_SECRET_KEY"),
            signup_enabled=env_bool("GEOVIS_SIGNUP_ENABLED", False),
            signup_invite_code=os.getenv("GEOVIS_SIGNUP_INVITE_CODE"),
            session_cookie_secure=env_bool("GEOVIS_SESSION_COOKIE_SECURE", True),
            database_url=os.getenv("GEOVIS_DATABASE_URL"),
        )

    @property
    def projects_root(self) -> Path:
        return self.output_root / "projects"

    @property
    def runs_root(self) -> Path:
        return self.output_root / "runs"

    @property
    def jobs_root(self) -> Path:
        return self.output_root / "jobs"

    @property
    def users_root(self) -> Path:
        return self.output_root / "users"

    @property
    def effective_session_secret(self) -> str | None:
        return self.session_secret or self.auth_token


def ensure_storage(config: DashboardConfig) -> None:
    config.output_root.mkdir(parents=True, exist_ok=True)
    config.projects_root.mkdir(parents=True, exist_ok=True)
    config.runs_root.mkdir(parents=True, exist_ok=True)
    config.jobs_root.mkdir(parents=True, exist_ok=True)
    config.users_root.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, missing_detail: str) -> dict[str, Any]:
    if not path.exists():
        raise HTTPException(status_code=404, detail=missing_detail)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def safe_id(value: str, label: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value or ""):
        raise HTTPException(status_code=400, detail=f"Invalid {label}")
    return value


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:80] or "project"


def project_dir(config: DashboardConfig, project_id: str) -> Path:
    return config.projects_root / safe_id(project_id, "project_id")


def run_dir(config: DashboardConfig, run_id: str) -> Path:
    return config.runs_root / safe_id(run_id, "run_id")


def project_metadata_path(config: DashboardConfig, project_id: str) -> Path:
    return project_dir(config, project_id) / "project.json"


def run_metadata_path(config: DashboardConfig, run_id: str) -> Path:
    return run_dir(config, run_id) / "metadata.json"


def job_metadata_path(config: DashboardConfig, job_id: str) -> Path:
    return config.jobs_root / safe_id(job_id, "job_id") / "job.json"


def create_run_folders(base_dir: Path) -> None:
    for child in ("inputs/raw", "inputs/validated", "maps", "vectors", "renders", "reports", "logs"):
        (base_dir / child).mkdir(parents=True, exist_ok=True)


def _session_signature(config: DashboardConfig, payload: str) -> str:
    secret = config.effective_session_secret
    if not secret:
        raise HTTPException(
            status_code=500,
            detail="GEOVIS_SESSION_SECRET must be configured when GEOVIS_REQUIRE_AUTH is true",
        )
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_dashboard_session(config: DashboardConfig, user_id: str, role: str = "owner") -> str:
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=SESSION_TTL_HOURS)).isoformat()
    payload = base64.urlsafe_b64encode(
        json.dumps({"user_id": user_id, "role": role, "expires_at": expires_at}, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return f"{payload}.{_session_signature(config, payload)}"


def verify_dashboard_session(config: DashboardConfig, session_value: str | None) -> dict[str, str] | None:
    if not session_value or "." not in session_value:
        return None
    payload, signature = session_value.rsplit(".", 1)
    if not hmac.compare_digest(signature, _session_signature(config, payload)):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None
    user_id = str(data.get("user_id") or "").strip()
    role = str(data.get("role") or "owner").strip() or "owner"
    expires_at = str(data.get("expires_at") or "").strip()
    if not user_id:
        return None
    if expires_at:
        try:
            if datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
                return None
        except ValueError:
            return None
    return {"user_id": user_id, "role": role}


def normalize_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
        raise HTTPException(status_code=400, detail="A valid email address is required")
    return normalized


def user_path(config: DashboardConfig, email: str) -> Path:
    digest = hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()
    return config.users_root / f"{digest}.json"


def public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user.get("display_name") or user["email"],
        "role": user.get("role", "owner"),
        "active": bool(user.get("active", True)),
        "created_at": user.get("created_at"),
        "updated_at": user.get("updated_at"),
    }


def password_hasher():
    from argon2 import PasswordHasher

    return PasswordHasher()


def get_user_by_email(config: DashboardConfig, email: str) -> dict[str, Any] | None:
    path = user_path(config, email)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def get_user_by_id(config: DashboardConfig, user_id: str) -> dict[str, Any] | None:
    safe_id(user_id, "user_id")
    for path in sorted(config.users_root.glob("*.json")):
        user = json.loads(path.read_text(encoding="utf-8"))
        if user.get("id") == user_id:
            return user
    return None


def create_user(
    config: DashboardConfig,
    email: str,
    password: str,
    display_name: str = "",
    invite_code: str | None = None,
) -> dict[str, Any]:
    if not config.signup_enabled:
        raise HTTPException(status_code=403, detail="Signup is disabled")
    if config.signup_invite_code and not secrets.compare_digest(invite_code or "", config.signup_invite_code):
        raise HTTPException(status_code=403, detail="A valid invite code is required")
    return provision_user(config, email, password, display_name=display_name)


def provision_user(
    config: DashboardConfig,
    email: str,
    password: str,
    display_name: str = "",
    role: str = "owner",
) -> dict[str, Any]:
    normalized_email = normalize_email(email)
    if len(password) < 12:
        raise HTTPException(status_code=400, detail="Password must be at least 12 characters")
    normalized_role = role.strip().lower()
    if normalized_role not in ACCOUNT_ROLES:
        raise HTTPException(status_code=400, detail="Invalid account role")
    path = user_path(config, normalized_email)
    if path.exists():
        raise HTTPException(status_code=409, detail="A user with that email already exists")
    now = utc_now()
    user = {
        "id": uuid4().hex,
        "email": normalized_email,
        "password_hash": password_hasher().hash(password),
        "display_name": display_name.strip() or normalized_email,
        "role": normalized_role,
        "active": True,
        "created_at": now,
        "updated_at": now,
        "activated_at": now,
    }
    write_json(path, user)
    return user


def set_user_password(config: DashboardConfig, email: str, password: str) -> dict[str, Any]:
    if len(password) < 12:
        raise HTTPException(status_code=400, detail="Password must be at least 12 characters")
    user = get_user_by_email(config, email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user["password_hash"] = password_hasher().hash(password)
    user["updated_at"] = utc_now()
    write_json(user_path(config, user["email"]), user)
    return user


def set_user_active(config: DashboardConfig, email: str, active: bool) -> dict[str, Any]:
    user = get_user_by_email(config, email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user["active"] = active
    user["updated_at"] = utc_now()
    write_json(user_path(config, user["email"]), user)
    return user


def authenticate_user(config: DashboardConfig, email: str, password: str) -> dict[str, Any]:
    from argon2.exceptions import VerificationError, VerifyMismatchError

    user = get_user_by_email(config, email)
    if not user or not user.get("active", True):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    hasher = password_hasher()
    try:
        verified = hasher.verify(user["password_hash"], password)
    except (VerifyMismatchError, VerificationError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password") from exc
    if not verified:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if hasher.check_needs_rehash(user["password_hash"]):
        user["password_hash"] = hasher.hash(password)
        user["updated_at"] = utc_now()
        write_json(user_path(config, user["email"]), user)
    return user


def principal_from_request(request: Request, config: DashboardConfig) -> dict[str, str]:
    user_id = request.headers.get("x-geovis-user")
    role = request.headers.get("x-geovis-role", "owner")
    if config.require_auth:
        auth_header = request.headers.get("authorization", "")
        bearer_prefix = "Bearer "
        bearer_token = auth_header[len(bearer_prefix) :] if auth_header.startswith(bearer_prefix) else None
        supplied_token = bearer_token or request.headers.get("x-geovis-token")
        if supplied_token:
            if not config.auth_token:
                raise HTTPException(
                    status_code=500,
                    detail="GEOVIS_AUTH_TOKEN must be configured for bearer API authentication",
                )
            if not secrets.compare_digest(supplied_token, config.auth_token):
                raise HTTPException(status_code=401, detail="Authentication required")
            if not user_id:
                raise HTTPException(status_code=401, detail="Authenticated requests must include x-geovis-user")
        else:
            session_principal = verify_dashboard_session(config, request.cookies.get(DASHBOARD_SESSION_COOKIE))
            if not session_principal:
                raise HTTPException(status_code=401, detail="Authentication required")
            user = get_user_by_id(config, session_principal["user_id"])
            if user:
                if not user.get("active", True):
                    raise HTTPException(status_code=401, detail="Authentication required")
                return {"user_id": user["id"], "role": user.get("role", session_principal.get("role", "owner"))}
            return session_principal
    return {"user_id": user_id or "local-dev", "role": role}


def assert_project_access(project: dict[str, Any], principal: dict[str, str], action: str) -> None:
    role = principal.get("role", "viewer")
    owner_id = project.get("owner_user_id")
    is_owner = principal.get("user_id") == owner_id
    if is_owner:
        return
    if action == "view" and role in {"viewer", "editor"}:
        return
    if action in {"create_run", "upload", "analyze", "report", "retry", "cancel"} and role == "editor":
        return
    raise HTTPException(status_code=403, detail="Project permission denied")


def create_project(config: DashboardConfig, name: str, owner_user_id: str, description: str = "") -> dict[str, Any]:
    project_id = uuid4().hex
    now = utc_now()
    project = {
        "id": project_id,
        "name": name,
        "slug": slugify(name),
        "description": description,
        "owner_user_id": owner_user_id,
        "status": "active",
        "created_at": now,
        "updated_at": now,
        "metadata": {},
    }
    write_json(project_metadata_path(config, project_id), project)
    return project


def get_project(config: DashboardConfig, project_id: str) -> dict[str, Any]:
    return read_json(project_metadata_path(config, project_id), "Project not found")


def list_projects(config: DashboardConfig, principal: dict[str, str]) -> list[dict[str, Any]]:
    projects = []
    for path in sorted(config.projects_root.glob("*/project.json")):
        project = read_json(path, "Project not found")
        if project.get("owner_user_id") == principal["user_id"] or principal.get("role") == "admin":
            projects.append(project)
    return projects


def create_run_record(
    config: DashboardConfig,
    project: dict[str, Any],
    created_by_user_id: str,
    workflow_type: str = "terrain",
    name: str | None = None,
    parameters: dict[str, Any] | None = None,
    retry_of_run_id: str | None = None,
    attempt_number: int = 1,
) -> dict[str, Any]:
    run_id = uuid4().hex
    base_dir = run_dir(config, run_id)
    create_run_folders(base_dir)
    now = utc_now()
    metadata = {
        "run_id": run_id,
        "id": run_id,
        "project_id": project["id"],
        "name": name or f"{workflow_type.title()} Run",
        "workflow_type": workflow_type,
        "status": "created",
        "created_by_user_id": created_by_user_id,
        "retry_of_run_id": retry_of_run_id,
        "attempt_number": attempt_number,
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "completed_at": None,
        "failed_at": None,
        "retryable": False,
        "error_code": None,
        "error_message": None,
        "error_detail": None,
        "parameters": parameters or {},
        "inputs": [],
        "outputs": {},
        "status_history": [{"status": "created", "at": now, "message": "Run created"}],
        "paths": {
            "run_dir": str(base_dir),
            "inputs": str(base_dir / "inputs"),
            "maps": str(base_dir / "maps"),
            "renders": str(base_dir / "renders"),
            "reports": str(base_dir / "reports"),
            "logs": str(base_dir / "logs"),
        },
    }
    write_json(run_metadata_path(config, run_id), metadata)
    return metadata


def create_job_record(
    config: DashboardConfig,
    run: dict[str, Any],
    created_by_user_id: str,
    job_type: str = "terrain_analysis",
) -> dict[str, Any]:
    job_id = uuid4().hex
    now = utc_now()
    job = {
        "id": job_id,
        "job_id": job_id,
        "run_id": run["run_id"],
        "project_id": run["project_id"],
        "job_type": job_type,
        "status": "queued",
        "created_by_user_id": created_by_user_id,
        "created_at": now,
        "updated_at": now,
        "claimed_at": None,
        "completed_at": None,
        "failed_at": None,
        "error_code": None,
        "error_message": None,
        "logs_path": str(run_dir(config, run["run_id"]) / "logs" / f"{job_id}.log"),
        "attempt_number": int(run.get("attempt_number", 1)),
    }
    write_json(job_metadata_path(config, job_id), job)
    return job


def get_job(config: DashboardConfig, job_id: str) -> dict[str, Any]:
    return read_json(job_metadata_path(config, job_id), "Job not found")


def list_jobs(
    config: DashboardConfig,
    status: str | None = None,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    jobs = []
    for path in sorted(config.jobs_root.glob("*/job.json")):
        job = read_json(path, "Job not found")
        if status is not None and job.get("status") != status:
            continue
        if run_id is not None and job.get("run_id") != run_id:
            continue
        jobs.append(job)
    return jobs


def update_job(config: DashboardConfig, job_id: str, **updates) -> dict[str, Any]:
    job = get_job(config, job_id)
    now = utc_now()
    job.update(updates)
    job["updated_at"] = now
    if updates.get("status") == "running" and not job.get("claimed_at"):
        job["claimed_at"] = now
    if updates.get("status") == "completed":
        job["completed_at"] = now
    if updates.get("status") == "failed":
        job["failed_at"] = now
    write_json(job_metadata_path(config, job_id), job)
    return job


def claim_next_queued_job(config: DashboardConfig) -> dict[str, Any] | None:
    queued = list_jobs(config, status="queued")
    if not queued:
        return None
    return update_job(config, queued[0]["job_id"], status="running")


def get_run(config: DashboardConfig, run_id: str) -> dict[str, Any]:
    return read_json(run_metadata_path(config, run_id), "Run not found")


def list_runs(config: DashboardConfig, project_id: str | None = None) -> list[dict[str, Any]]:
    runs = []
    for path in sorted(config.runs_root.glob("*/metadata.json")):
        run = read_json(path, "Run not found")
        if project_id is None or run.get("project_id") == project_id:
            runs.append(run)
    return runs


def visible_project_ids(config: DashboardConfig, principal: dict[str, str]) -> set[str]:
    return {project["id"] for project in list_projects(config, principal)}


def list_visible_runs(config: DashboardConfig, principal: dict[str, str]) -> list[dict[str, Any]]:
    allowed_project_ids = visible_project_ids(config, principal)
    return [run for run in list_runs(config) if run.get("project_id") in allowed_project_ids]


def update_run(config: DashboardConfig, run_id: str, status_message: str | None = None, **updates) -> dict[str, Any]:
    metadata = get_run(config, run_id)
    status = updates.get("status")
    if status and status not in RUN_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid run status: {status}")
    now = utc_now()
    metadata.update(updates)
    metadata["updated_at"] = now
    if status:
        metadata.setdefault("status_history", []).append(
            {"status": status, "at": now, "message": status_message or status}
        )
        if status == "running" and not metadata.get("started_at"):
            metadata["started_at"] = now
        if status in {"completed", "reported"}:
            metadata["completed_at"] = now
        if status == "failed":
            metadata["failed_at"] = now
    write_json(run_metadata_path(config, run_id), metadata)
    return metadata


def normalize_filename(filename: str) -> str:
    if not filename or "\x00" in filename:
        raise HTTPException(status_code=400, detail={"error_code": "unsafe_filename", "error_message": "Filename is required"})
    if filename.startswith(("/", "\\")) or ".." in Path(filename).parts or "\\" in filename:
        raise HTTPException(status_code=400, detail={"error_code": "unsafe_filename", "error_message": f"Unsafe filename: {filename}"})
    name = Path(filename).name.strip()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    if not name or name.startswith(".") or len(name) > 180:
        raise HTTPException(status_code=400, detail={"error_code": "unsafe_filename", "error_message": f"Unsafe filename: {filename}"})
    return name


def ensure_child_path(root: Path, target: Path) -> Path:
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise HTTPException(status_code=400, detail={"error_code": "unsafe_filename", "error_message": "Path escapes storage root"})
    return resolved_target


def checksum_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mime_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".tif", ".tiff"}:
        return "image/tiff"
    if suffix == ".geojson":
        return "application/geo+json"
    if suffix == ".json":
        return "application/json"
    if suffix == ".png":
        return "image/png"
    guessed, _encoding = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def output_stage(output_key: str) -> str:
    if output_key in {"slope", "hillshade", "terrain_risk"}:
        return "terrain_analysis"
    if output_key in {"flood_risk", "river_buffers"}:
        return "flood_risk"
    if output_key == "wildfire_risk":
        return "wildfire_risk"
    if output_key.startswith("vector_overlay_"):
        return "vector_overlay"
    if output_key.endswith("_png"):
        return "render_overlay"
    if output_key.endswith("_json"):
        return "summary"
    if output_key.endswith("_md"):
        return "report"
    return "output"


def output_category(output_key: str, path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".tif", ".tiff"}:
        return "raster"
    if suffix == ".geojson" or output_key.startswith("vector_overlay_"):
        return "vector"
    if suffix == ".png":
        return "render"
    if suffix in {".json", ".md"}:
        return "metadata"
    return "other"


def output_type_label(output_key: str, path: Path) -> str:
    labels = {
        "slope": "slope GeoTIFF",
        "hillshade": "hillshade GeoTIFF",
        "terrain_risk": "risk GeoTIFF",
        "flood_risk": "flood risk GeoTIFF",
        "wildfire_risk": "wildfire risk GeoTIFF",
        "river_buffers": "river buffer GeoJSON",
        "terrain_summary_json": "summary JSON",
        "flood_risk_summary_json": "flood risk summary JSON",
        "wildfire_risk_summary_json": "wildfire risk summary JSON",
        "terrain_overlay_png": "overlay PNG render",
        "report_md": "terrain report",
    }
    if output_key.startswith("vector_overlay_"):
        return "clipped vector GeoJSON"
    return labels.get(output_key, path.suffix.lower().lstrip(".") or "output")


def artifact_display_name(config: DashboardConfig, run_id: str, path: Path) -> str:
    try:
        return path.resolve().relative_to(run_dir(config, run_id).resolve()).as_posix()
    except ValueError:
        return path.name


def registered_output_path(config: DashboardConfig, run: dict[str, Any], output_key: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", output_key or ""):
        raise HTTPException(status_code=400, detail="Invalid output key")
    outputs = run.get("outputs", {})
    raw_path = outputs.get(output_key)
    if not raw_path:
        raise HTTPException(status_code=404, detail="Output not found")
    path = ensure_child_path(run_dir(config, run["run_id"]), Path(raw_path))
    if path.suffix.lower() not in {".tif", ".tiff", ".geojson", ".json", ".png", ".md"}:
        raise HTTPException(status_code=404, detail="Output not found")
    return path


def output_artifact_record(config: DashboardConfig, run: dict[str, Any], output_key: str) -> dict[str, Any]:
    path = registered_output_path(config, run, output_key)
    exists = path.exists() and path.is_file()
    size_bytes = path.stat().st_size if exists else None
    checksum = checksum_sha256(path) if exists else None
    return {
        "id": output_key,
        "run_id": run["run_id"],
        "project_id": run["project_id"],
        "output_type": output_type_label(output_key, path),
        "category": output_category(output_key, path),
        "mime_type": mime_type_for_path(path),
        "size_bytes": size_bytes,
        "checksum_sha256": checksum,
        "generated_stage": output_stage(output_key),
        "filename": path.name,
        "display_filename": artifact_display_name(config, run["run_id"], path),
        "exists": exists,
        "download_url": f"/api/runs/{run['run_id']}/outputs/{output_key}/download",
        "preview_url": f"/api/runs/{run['run_id']}/outputs/{output_key}/preview"
        if path.suffix.lower() == ".png"
        else None,
    }


def list_output_artifacts(config: DashboardConfig, run: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = []
    for output_key, raw_path in sorted(run.get("outputs", {}).items()):
        if not raw_path:
            continue
        artifacts.append(output_artifact_record(config, run, output_key))
    return artifacts


def decode_upload_content(content_b64: str) -> bytes:
    try:
        return base64.b64decode(content_b64, validate=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error_code": "invalid_upload", "error_message": "content_b64 is not valid base64"}) from exc


def file_type_from_extension(extension: str) -> str:
    if extension in {".tif", ".tiff"}:
        return "dem"
    if extension in {".geojson", ".json", ".shp"}:
        return "vector"
    if extension == ".csv":
        return "csv"
    if extension in {".shx", ".dbf", ".prj", ".cpg", ".qix", ".sbn", ".sbx", ".xml"}:
        return "shapefile_sidecar"
    return "unknown"


def validate_raster(path: Path) -> dict[str, Any]:
    try:
        import rasterio

        with rasterio.open(path) as src:
            if src.count < 1 or src.width <= 0 or src.height <= 0:
                raise ValueError("Raster has no readable bands or dimensions")
            return {
                "driver": src.driver,
                "width": src.width,
                "height": src.height,
                "band_count": src.count,
                "crs": str(src.crs) if src.crs else None,
                "bounds": list(src.bounds),
                "dtype": src.dtypes[0] if src.dtypes else None,
                "nodata": src.nodata,
            }
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"error_code": "raster_open_failed", "error_message": str(exc)}) from exc


def validate_vector(path: Path) -> dict[str, Any]:
    try:
        import geopandas as gpd

        frame = gpd.read_file(path)
        if frame.empty:
            raise ValueError("Vector layer has no features")
        if frame.geometry is None:
            raise ValueError("Vector layer has no geometry column")
        invalid_count = int((~frame.geometry.is_valid).sum())
        if invalid_count:
            raise ValueError(f"Vector layer has {invalid_count} invalid geometries")
        return {
            "driver": "geopandas",
            "feature_count": int(len(frame)),
            "crs": str(frame.crs) if frame.crs else None,
            "bounds": list(frame.total_bounds),
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"error_code": "vector_open_failed", "error_message": str(exc)}) from exc


def validate_csv(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            sample = handle.read(2048)
            handle.seek(0)
            if not csv.Sniffer().has_header(sample):
                raise ValueError("CSV header row is required")
            reader = csv.DictReader(handle)
            columns = reader.fieldnames or []
            row_count = sum(1 for _ in reader)
            if not columns or row_count == 0:
                raise ValueError("CSV must include a header and at least one row")
            return {"columns": columns, "row_count": row_count}
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"error_code": "csv_parse_failed", "error_message": str(exc)}) from exc


def validate_file_content(path: Path, extension: str) -> dict[str, Any]:
    if extension in {".tif", ".tiff"}:
        return validate_raster(path)
    if extension in {".geojson", ".json", ".shp"}:
        return validate_vector(path)
    if extension == ".csv":
        return validate_csv(path)
    return {}


def validate_shapefile_bundle(file_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_stem: dict[str, set[str]] = {}
    for record in file_records:
        suffix = record["extension"]
        if suffix in {".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix", ".sbn", ".sbx", ".xml"}:
            by_stem.setdefault(Path(record["stored_filename"]).stem, set()).add(suffix)

    for record in file_records:
        if record["extension"] != ".shp":
            continue
        stem = Path(record["stored_filename"]).stem
        missing = sorted(SHAPEFILE_REQUIRED - by_stem.get(stem, set()))
        if missing:
            record["status"] = "invalid"
            record["validation_errors"].append(
                {
                    "error_code": "missing_shapefile_component",
                    "error_message": f"Missing Shapefile components for {stem}: {', '.join(missing)}",
                }
            )
        elif ".prj" not in by_stem.get(stem, set()):
            record["warnings"].append({"warning_code": "missing_crs", "message": "Shapefile .prj file is recommended"})
    return file_records


def ingest_base64_files(
    config: DashboardConfig,
    run: dict[str, Any],
    uploads: list[dict[str, str]],
) -> dict[str, Any]:
    if len(uploads) > config.max_batch_files:
        raise HTTPException(status_code=413, detail={"error_code": "too_many_files", "error_message": f"Maximum files per batch is {config.max_batch_files}"})

    raw_dir = run_dir(config, run["run_id"]) / "inputs" / "raw"
    validated_dir = run_dir(config, run["run_id"]) / "inputs" / "validated"
    raw_dir.mkdir(parents=True, exist_ok=True)
    validated_dir.mkdir(parents=True, exist_ok=True)

    decoded: list[tuple[dict[str, str], str, bytes]] = []
    total_size = 0
    for upload in uploads:
        stored_filename = normalize_filename(upload.get("filename", ""))
        extension = Path(stored_filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail={"error_code": "unsupported_file_type", "error_message": f"Unsupported file extension: {extension}"})
        content = decode_upload_content(upload.get("content_b64", ""))
        if len(content) > config.max_upload_file_bytes:
            raise HTTPException(status_code=413, detail={"error_code": "file_too_large", "error_message": f"{stored_filename} exceeds the configured file limit"})
        total_size += len(content)
        decoded.append((upload, stored_filename, content))
    if total_size > config.max_upload_batch_bytes:
        raise HTTPException(status_code=413, detail={"error_code": "batch_too_large", "error_message": "Upload batch exceeds the configured limit"})

    records: list[dict[str, Any]] = []
    for upload, stored_filename, content in decoded:
        raw_path = ensure_child_path(raw_dir, raw_dir / stored_filename)
        raw_path.write_bytes(content)
        extension = raw_path.suffix.lower()
        checksum = hashlib.sha256(content).hexdigest()
        record = {
            "id": uuid4().hex,
            "project_id": run["project_id"],
            "run_id": run["run_id"],
            "role": "input",
            "file_type": file_type_from_extension(extension),
            "original_filename": upload.get("filename", stored_filename),
            "stored_filename": stored_filename,
            "extension": extension,
            "content_type": upload.get("content_type"),
            "path": str(raw_path),
            "size_bytes": len(content),
            "checksum_sha256": checksum,
            "status": "validating",
            "validation_errors": [],
            "warnings": [],
            "metadata": {},
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }
        try:
            record["metadata"] = validate_file_content(raw_path, extension)
            if record["metadata"].get("crs") is None and extension in {".tif", ".tiff", ".geojson", ".json", ".shp"}:
                record["warnings"].append({"warning_code": "missing_crs", "message": "CRS is missing"})
            validated_path = ensure_child_path(validated_dir, validated_dir / stored_filename)
            shutil.copy2(raw_path, validated_path)
            record["path"] = str(validated_path)
            record["status"] = "valid"
        except HTTPException as exc:
            record["status"] = "invalid"
            record["validation_errors"].append(exc.detail)
        record["updated_at"] = utc_now()
        records.append(record)

    records = validate_shapefile_bundle(records)
    existing = run.get("inputs", [])
    run = update_run(config, run["run_id"], status="uploaded", status_message="Files uploaded", inputs=existing + records)
    batch_status = "valid" if all(record["status"] == "valid" for record in records) else "completed_with_errors"
    return {"run_id": run["run_id"], "batch_status": batch_status, "files": records, "run": run}


def first_valid_dem(run: dict[str, Any]) -> Path | None:
    for record in run.get("inputs", []):
        if record.get("file_type") == "dem" and record.get("status") == "valid":
            return Path(record["path"])
    legacy = run.get("dem_path")
    return Path(legacy) if legacy else None


def valid_vector_inputs(run: dict[str, Any]) -> list[Path]:
    return [
        Path(record["path"])
        for record in run.get("inputs", [])
        if record.get("file_type") == "vector" and record.get("status") == "valid"
    ]


def relative_output_url(config: DashboardConfig, path: Path) -> str:
    try:
        relative = path.resolve().relative_to(config.output_root.resolve())
    except ValueError:
        return ""
    return "/outputs/" + relative.as_posix()


def copy_sample_dem_to_run(config: DashboardConfig, run_id: str, sample_dem: Path = Path("data/sample/sample_dem.tif")) -> dict[str, Any]:
    run = get_run(config, run_id)
    if not sample_dem.exists():
        raise HTTPException(status_code=404, detail=f"Sample DEM not found: {sample_dem}")
    content_b64 = base64.b64encode(sample_dem.read_bytes()).decode("ascii")
    return ingest_base64_files(config, run, [{"filename": sample_dem.name, "content_b64": content_b64}])["run"]
