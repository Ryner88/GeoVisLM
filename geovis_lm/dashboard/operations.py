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
import fcntl
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import bleach
from fastapi import HTTPException, Request
from markdown_it import MarkdownIt


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
PROJECT_MEMBER_ROLES = {"viewer"}
REPORT_COMMENT_OUTPUT_KEY = "report_md"
COMMENT_MARKDOWN_MAX_LENGTH = 10000
COMMENT_MARKDOWN_TAGS = {
    "a",
    "blockquote",
    "br",
    "code",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "ul",
}
COMMENT_MARKDOWN_ATTRIBUTES = {"a": ["href", "title"]}

WORKFLOW_TEMPLATES: dict[str, dict[str, Any]] = {
    "terrain": {
        "template_id": "terrain-gis-analysis",
        "template_version": "1.0.0",
        "workflow_type": "terrain",
        "name": "Terrain GIS Analysis",
        "description": "Load a DEM, compute slope/hillshade/risk layers, and export terrain outputs.",
        "steps": [
            "Load the DEM and preserve raster metadata.",
            "Compute slope, hillshade, and terrain risk layers.",
            "Write the outputs to the run maps/renders directories.",
        ],
    },
    "flood_risk": {
        "template_id": "flood-risk-analysis",
        "template_version": "1.0.0",
        "workflow_type": "flood_risk",
        "name": "Flood Risk Analysis",
        "description": "Assess flood exposure from a DEM and project vector overlays.",
        "steps": [
            "Validate the DEM and aligned vector overlays.",
            "Run flood-risk raster analysis across project zones.",
            "Summarize exposure outputs and export the report artifact.",
        ],
    },
    "wildfire_risk": {
        "template_id": "wildfire-risk-analysis",
        "template_version": "1.0.0",
        "workflow_type": "wildfire_risk",
        "name": "Wildfire Risk Analysis",
        "description": "Combine slope, fuel, and fire exposure layers into wildfire risk outputs.",
        "steps": [
            "Validate the DEM, fuel layer, and vector inputs.",
            "Generate slope and fuel risk factors.",
            "Combine the layers and write wildfire risk summary outputs.",
        ],
    },
}


def normalize_workflow_type(workflow_type: str | None) -> str:
    if workflow_type is None:
        return "terrain"
    key = workflow_type.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "terrain": "terrain",
        "terrain_analysis": "terrain",
        "flood": "flood_risk",
        "flood_risk": "flood_risk",
        "flood_risk_analysis": "flood_risk",
        "wildfire": "wildfire_risk",
        "wildfire_risk": "wildfire_risk",
        "wildfire_risk_analysis": "wildfire_risk",
    }
    return aliases.get(key, key if key in WORKFLOW_TEMPLATES else "terrain")


def resolve_workflow_template(workflow_type: str | None) -> dict[str, Any]:
    key = normalize_workflow_type(workflow_type)
    template = WORKFLOW_TEMPLATES.get(key)
    if template is not None:
        return dict(template)
    return {
        "template_id": f"{key}-analysis",
        "template_version": "0.0.0",
        "workflow_type": key,
        "name": f"{key.replace('_', ' ').title()} Analysis",
        "description": "Custom workflow template generated for the requested analysis.",
        "steps": [],
    }


def list_workflow_templates() -> list[dict[str, Any]]:
    return [dict(template) for template in WORKFLOW_TEMPLATES.values()]


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
    max_project_bytes: int
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
        project_mb = env_int("GEOVIS_MAX_PROJECT_MB", 5120)
        batch_files = env_int("GEOVIS_MAX_BATCH_FILES", 50)
        if min(file_mb, batch_mb, project_mb, batch_files) <= 0:
            raise RuntimeError("Upload size limits must be positive")
        return cls(
            output_root=output_root,
            max_upload_file_bytes=file_mb * 1024 * 1024,
            max_upload_batch_bytes=batch_mb * 1024 * 1024,
            max_batch_files=batch_files,
            max_project_bytes=project_mb * 1024 * 1024,
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
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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


def project_members_path(config: DashboardConfig, project_id: str) -> Path:
    return project_dir(config, project_id) / "members.json"


def project_invitations_path(config: DashboardConfig, project_id: str) -> Path:
    return project_dir(config, project_id) / "invitations.json"


def project_audit_path(config: DashboardConfig, project_id: str) -> Path:
    return project_dir(config, project_id) / "audit.jsonl"


def run_metadata_path(config: DashboardConfig, run_id: str) -> Path:
    return run_dir(config, run_id) / "metadata.json"


def report_comments_path(config: DashboardConfig, run_id: str) -> Path:
    return run_dir(config, run_id) / "reports" / "comments.json"


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


def _project_permission_error(can_view: bool) -> HTTPException:
    if can_view:
        return HTTPException(status_code=403, detail="Project permission denied")
    return HTTPException(status_code=404, detail="Project not found")


def read_project_members(config: DashboardConfig, project_id: str) -> dict[str, Any]:
    path = project_members_path(config, project_id)
    if not path.exists():
        return {"project_id": safe_id(project_id, "project_id"), "members": []}
    return json.loads(path.read_text(encoding="utf-8"))


def write_project_members(config: DashboardConfig, project_id: str, data: dict[str, Any]) -> None:
    data["project_id"] = safe_id(project_id, "project_id")
    data["members"] = sorted(
        data.get("members", []), key=lambda member: (member.get("email", ""), member.get("user_id", ""))
    )
    write_json(project_members_path(config, project_id), data)


def read_project_invitations(config: DashboardConfig, project_id: str) -> dict[str, Any]:
    path = project_invitations_path(config, project_id)
    if not path.exists():
        return {"project_id": safe_id(project_id, "project_id"), "invitations": []}
    return json.loads(path.read_text(encoding="utf-8"))


def write_project_invitations(config: DashboardConfig, project_id: str, data: dict[str, Any]) -> None:
    data["project_id"] = safe_id(project_id, "project_id")
    data["invitations"] = sorted(
        data.get("invitations", []), key=lambda invite: (invite.get("created_at", ""), invite.get("id", ""))
    )
    write_json(project_invitations_path(config, project_id), data)


def append_project_audit_event(
    config: DashboardConfig,
    project_id: str,
    event_type: str,
    actor_user_id: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "id": uuid4().hex,
        "project_id": safe_id(project_id, "project_id"),
        "event_type": event_type,
        "actor_user_id": actor_user_id,
        "details": details or {},
        "created_at": utc_now(),
    }
    path = project_audit_path(config, project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def list_project_audit_events(config: DashboardConfig, project_id: str) -> list[dict[str, Any]]:
    path = project_audit_path(config, project_id)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def project_member_for_principal(
    config: DashboardConfig, project: dict[str, Any], principal: dict[str, str]
) -> dict[str, Any] | None:
    principal_user_id = principal.get("user_id")
    if not principal_user_id:
        return None
    for member in read_project_members(config, project["id"]).get("members", []):
        if member.get("user_id") == principal_user_id and member.get("role") in PROJECT_MEMBER_ROLES:
            return member
    return None


def can_view_project(config: DashboardConfig, project: dict[str, Any], principal: dict[str, str]) -> bool:
    return (
        principal.get("user_id") == project.get("owner_user_id")
        or principal.get("role") == "admin"
        or project_member_for_principal(config, project, principal) is not None
    )


def assert_project_access(
    config: DashboardConfig, project: dict[str, Any], principal: dict[str, str], action: str
) -> None:
    role = principal.get("role", "viewer")
    owner_id = project.get("owner_user_id")
    is_owner = principal.get("user_id") == owner_id
    is_admin = role == "admin"
    can_view = can_view_project(config, project, principal)
    if is_owner or is_admin:
        return
    if action == "view" and can_view:
        return
    raise _project_permission_error(can_view)


def assert_project_owner(config: DashboardConfig, project: dict[str, Any], principal: dict[str, str]) -> None:
    assert_project_access(config, project, principal, "manage_members")


def is_project_owner_or_admin(project: dict[str, Any], principal: dict[str, str]) -> bool:
    return principal.get("user_id") == project.get("owner_user_id") or principal.get("role") == "admin"


def list_project_members(config: DashboardConfig, project: dict[str, Any], principal: dict[str, str]) -> dict[str, Any]:
    assert_project_owner(config, project, principal)
    members = []
    for member in read_project_members(config, project["id"]).get("members", []):
        user = get_user_by_id(config, member["user_id"])
        public = public_user(user) if user else {"id": member["user_id"], "email": member.get("email", "")}
        members.append({**member, "user": public})
    return {"project_id": project["id"], "members": members}


def invite_project_member(
    config: DashboardConfig,
    project: dict[str, Any],
    principal: dict[str, str],
    email: str,
    role: str = "viewer",
) -> dict[str, Any]:
    assert_project_owner(config, project, principal)
    normalized_role = role.strip().lower()
    if normalized_role not in PROJECT_MEMBER_ROLES:
        raise HTTPException(status_code=400, detail="Invalid project member role")
    user = get_user_by_email(config, email)
    if not user or not user.get("active", True):
        raise HTTPException(status_code=404, detail="Account not found")
    if user["id"] == project.get("owner_user_id"):
        raise HTTPException(status_code=400, detail="Project owner already has access")
    members = read_project_members(config, project["id"])
    for member in members.get("members", []):
        if member.get("user_id") == user["id"]:
            raise HTTPException(status_code=409, detail="Project member already exists")
    now = utc_now()
    invitation = {
        "id": uuid4().hex,
        "project_id": project["id"],
        "email": user["email"],
        "user_id": user["id"],
        "role": normalized_role,
        "status": "accepted",
        "invited_by_user_id": principal["user_id"],
        "created_at": now,
        "accepted_at": now,
    }
    member = {
        "user_id": user["id"],
        "email": user["email"],
        "role": normalized_role,
        "invited_by_user_id": principal["user_id"],
        "invitation_id": invitation["id"],
        "created_at": now,
        "updated_at": now,
    }
    members.setdefault("members", []).append(member)
    invitations = read_project_invitations(config, project["id"])
    invitations.setdefault("invitations", []).append(invitation)
    write_project_members(config, project["id"], members)
    write_project_invitations(config, project["id"], invitations)
    append_project_audit_event(
        config,
        project["id"],
        "project.member_invited",
        principal["user_id"],
        {"target_user_id": user["id"], "target_email": user["email"], "role": normalized_role},
    )
    return {"project_id": project["id"], "invitation": invitation, "member": member}


def revoke_project_member(
    config: DashboardConfig,
    project: dict[str, Any],
    principal: dict[str, str],
    user_id: str,
) -> dict[str, Any]:
    assert_project_owner(config, project, principal)
    safe_user_id = safe_id(user_id, "user_id")
    if safe_user_id == project.get("owner_user_id"):
        raise HTTPException(status_code=400, detail="Project owner access cannot be revoked")
    members = read_project_members(config, project["id"])
    retained = [member for member in members.get("members", []) if member.get("user_id") != safe_user_id]
    if len(retained) == len(members.get("members", [])):
        raise HTTPException(status_code=404, detail="Project member not found")
    members["members"] = retained
    write_project_members(config, project["id"], members)
    append_project_audit_event(
        config,
        project["id"],
        "project.member_revoked",
        principal["user_id"],
        {"target_user_id": safe_user_id},
    )
    return {"project_id": project["id"], "revoked_user_id": safe_user_id}


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
    write_project_members(config, project_id, {"members": []})
    return project


def get_project(config: DashboardConfig, project_id: str) -> dict[str, Any]:
    return read_json(project_metadata_path(config, project_id), "Project not found")


def list_projects(config: DashboardConfig, principal: dict[str, str]) -> list[dict[str, Any]]:
    projects = []
    for path in sorted(config.projects_root.glob("*/project.json")):
        project = read_json(path, "Project not found")
        if can_view_project(config, project, principal):
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
    workflow_type = normalize_workflow_type(workflow_type)
    template = resolve_workflow_template(workflow_type)
    metadata = {
        "run_id": run_id,
        "id": run_id,
        "project_id": project["id"],
        "name": name or f"{workflow_type.title()} Run",
        "workflow_type": workflow_type,
        "template_id": template["template_id"],
        "template_version": template["template_version"],
        "template": template,
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
    workflow_type = updates.get("workflow_type")
    if workflow_type is not None:
        normalized = normalize_workflow_type(workflow_type)
        template = resolve_workflow_template(normalized)
        metadata["workflow_type"] = normalized
        metadata["template_id"] = template["template_id"]
        metadata["template_version"] = template["template_version"]
        metadata["template"] = template
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
    if not name or name.startswith(".") or len(name) > 180 or name.lower() == "batch.json":
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


def report_markdown_path(config: DashboardConfig, run: dict[str, Any]) -> Path:
    try:
        path = registered_output_path(config, run, REPORT_COMMENT_OUTPUT_KEY)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise HTTPException(status_code=404, detail="Report not found") from exc
        raise
    if path.suffix.lower() != ".md" or not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Report not found")
    return path


def sanitize_comment_markdown(markdown: str) -> tuple[str, str]:
    body_markdown = (markdown or "").strip()
    if not body_markdown:
        raise HTTPException(status_code=400, detail="Comment body is required")
    if len(body_markdown) > COMMENT_MARKDOWN_MAX_LENGTH:
        raise HTTPException(status_code=400, detail="Comment body is too long")
    body_markdown = re.sub(r"(?i)javascript\s*:", "blocked:", body_markdown)
    html = MarkdownIt("commonmark", {"html": False, "linkify": False}).render(body_markdown)
    clean_html = bleach.clean(
        html,
        tags=COMMENT_MARKDOWN_TAGS,
        attributes=COMMENT_MARKDOWN_ATTRIBUTES,
        protocols={"http", "https", "mailto"},
        strip=True,
    )
    return body_markdown, clean_html


def read_report_comments(config: DashboardConfig, run_id: str) -> dict[str, Any]:
    path = report_comments_path(config, run_id)
    if not path.exists():
        return {"run_id": safe_id(run_id, "run_id"), "comments": []}
    return json.loads(path.read_text(encoding="utf-8"))


def write_report_comments(config: DashboardConfig, run_id: str, data: dict[str, Any]) -> None:
    data["run_id"] = safe_id(run_id, "run_id")
    data["comments"] = sorted(data.get("comments", []), key=lambda comment: comment.get("created_at", ""))
    write_json(report_comments_path(config, run_id), data)


def _public_comment_author(config: DashboardConfig, user_id: str) -> dict[str, Any]:
    user = get_user_by_id(config, user_id)
    if user:
        return public_user(user)
    return {"id": user_id, "email": "", "display_name": user_id}


def public_report_comment(config: DashboardConfig, comment: dict[str, Any]) -> dict[str, Any]:
    return {**comment, "author": _public_comment_author(config, comment["author_user_id"])}


def list_report_comments(
    config: DashboardConfig,
    run: dict[str, Any],
    project: dict[str, Any],
    principal: dict[str, str],
) -> dict[str, Any]:
    assert_project_access(config, project, principal, "view")
    report_markdown_path(config, run)
    comments = [
        public_report_comment(config, comment)
        for comment in read_report_comments(config, run["run_id"]).get("comments", [])
        if comment.get("status") != "deleted"
    ]
    return {
        "project_id": project["id"],
        "run_id": run["run_id"],
        "output_key": REPORT_COMMENT_OUTPUT_KEY,
        "comments": comments,
    }


def create_report_comment(
    config: DashboardConfig,
    run: dict[str, Any],
    project: dict[str, Any],
    principal: dict[str, str],
    body_markdown: str,
) -> dict[str, Any]:
    assert_project_access(config, project, principal, "view")
    report_markdown_path(config, run)
    body_markdown, body_html = sanitize_comment_markdown(body_markdown)
    now = utc_now()
    comment = {
        "id": uuid4().hex,
        "project_id": project["id"],
        "run_id": run["run_id"],
        "output_key": REPORT_COMMENT_OUTPUT_KEY,
        "author_user_id": principal["user_id"],
        "body_markdown": body_markdown,
        "body_html": body_html,
        "status": "open",
        "created_at": now,
        "updated_at": now,
        "resolved_at": None,
        "resolved_by_user_id": None,
        "deleted_at": None,
        "deleted_by_user_id": None,
        "edit_history": [],
    }
    data = read_report_comments(config, run["run_id"])
    data.setdefault("comments", []).append(comment)
    write_report_comments(config, run["run_id"], data)
    append_project_audit_event(
        config,
        project["id"],
        "report_comment.created",
        principal["user_id"],
        {"run_id": run["run_id"], "comment_id": comment["id"], "output_key": REPORT_COMMENT_OUTPUT_KEY},
    )
    return public_report_comment(config, comment)


def _find_report_comment(data: dict[str, Any], comment_id: str) -> dict[str, Any]:
    safe_comment_id = safe_id(comment_id, "comment_id")
    for comment in data.get("comments", []):
        if comment.get("id") == safe_comment_id and comment.get("status") != "deleted":
            return comment
    raise HTTPException(status_code=404, detail="Comment not found")


def get_report_comment(
    config: DashboardConfig,
    run: dict[str, Any],
    project: dict[str, Any],
    principal: dict[str, str],
    comment_id: str,
) -> dict[str, Any]:
    assert_project_access(config, project, principal, "view")
    report_markdown_path(config, run)
    comment = _find_report_comment(read_report_comments(config, run["run_id"]), comment_id)
    return public_report_comment(config, comment)


def update_report_comment(
    config: DashboardConfig,
    run: dict[str, Any],
    project: dict[str, Any],
    principal: dict[str, str],
    comment_id: str,
    body_markdown: str,
) -> dict[str, Any]:
    assert_project_access(config, project, principal, "view")
    report_markdown_path(config, run)
    data = read_report_comments(config, run["run_id"])
    comment = _find_report_comment(data, comment_id)
    if comment.get("author_user_id") != principal.get("user_id"):
        raise HTTPException(status_code=403, detail="Comment permission denied")
    body_markdown, body_html = sanitize_comment_markdown(body_markdown)
    now = utc_now()
    comment.setdefault("edit_history", []).append(
        {
            "edited_at": now,
            "edited_by_user_id": principal["user_id"],
            "previous_body_markdown": comment["body_markdown"],
            "previous_body_html": comment["body_html"],
        }
    )
    comment["body_markdown"] = body_markdown
    comment["body_html"] = body_html
    comment["updated_at"] = now
    write_report_comments(config, run["run_id"], data)
    append_project_audit_event(
        config,
        project["id"],
        "report_comment.edited",
        principal["user_id"],
        {"run_id": run["run_id"], "comment_id": comment["id"], "output_key": REPORT_COMMENT_OUTPUT_KEY},
    )
    return public_report_comment(config, comment)


def moderate_report_comment(
    config: DashboardConfig,
    run: dict[str, Any],
    project: dict[str, Any],
    principal: dict[str, str],
    comment_id: str,
    action: str,
) -> dict[str, Any]:
    assert_project_access(config, project, principal, "view")
    report_markdown_path(config, run)
    if not is_project_owner_or_admin(project, principal):
        raise HTTPException(status_code=403, detail="Comment moderation permission denied")
    if action not in {"resolve", "reopen", "delete"}:
        raise HTTPException(status_code=400, detail="Invalid comment moderation action")
    data = read_report_comments(config, run["run_id"])
    comment = _find_report_comment(data, comment_id)
    now = utc_now()
    if action == "resolve":
        comment["status"] = "resolved"
        comment["resolved_at"] = now
        comment["resolved_by_user_id"] = principal["user_id"]
        event_type = "report_comment.resolved"
    elif action == "reopen":
        comment["status"] = "open"
        comment["resolved_at"] = None
        comment["resolved_by_user_id"] = None
        event_type = "report_comment.reopened"
    else:
        comment["status"] = "deleted"
        comment["deleted_at"] = now
        comment["deleted_by_user_id"] = principal["user_id"]
        event_type = "report_comment.deleted"
    comment["updated_at"] = now
    write_report_comments(config, run["run_id"], data)
    append_project_audit_event(
        config,
        project["id"],
        event_type,
        principal["user_id"],
        {"run_id": run["run_id"], "comment_id": comment["id"], "output_key": REPORT_COMMENT_OUTPUT_KEY},
    )
    if action == "delete":
        return {"project_id": project["id"], "run_id": run["run_id"], "deleted_comment_id": comment["id"]}
    return public_report_comment(config, comment)


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


SHAPEFILE_EXTENSIONS = {".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix", ".sbn", ".sbx", ".xml"}


def shapefile_stem(filename: str) -> str:
    lower = filename.lower()
    return lower[:-8] if lower.endswith(".shp.xml") else Path(lower).stem


def upload_error(code: str, message: str, filename: str | None = None, status: int = 400) -> HTTPException:
    detail = {"error_code": code, "error_message": message}
    if filename:
        detail["filename"] = filename
    return HTTPException(status_code=status, detail=detail)


@contextmanager
def project_upload_lock(config: DashboardConfig, project_id: str):
    lock_path = project_dir(config, project_id) / "upload.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def project_upload_bytes(config: DashboardConfig, project_id: str) -> int:
    total = 0
    retained_paths: set[Path] = set()
    for run in list_runs(config, project_id):
        for record in run.get("inputs", []):
            if record.get("path"):
                path = Path(record["path"]).resolve()
                if path.is_file() and path not in retained_paths:
                    retained_paths.add(path)
                    total += path.stat().st_size
        staging = run_dir(config, run["run_id"]) / "inputs" / "staging"
        if staging.exists():
            for directory in staging.iterdir():
                manifest = directory / "batch.json"
                if not manifest.is_file():
                    continue
                try:
                    batch = json.loads(manifest.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    total += sum(path.stat().st_size for path in directory.iterdir() if path.is_file() and path != manifest)
                    continue
                committed = {item.get("stored_filename") for item in run.get("inputs", []) if item.get("source_batch_id") == batch.get("batch_id")}
                if batch.get("status") == "validating" and committed == {item.get("filename") for item in batch.get("files", [])}:
                    continue
                if batch.get("status") in {"created", "uploading", "validating"}:
                    total += sum(int(item["size_bytes"]) for item in batch.get("files", []))
                elif batch.get("status") == "interrupted":
                    total += sum(int(item["size_bytes"]) for item in batch.get("files", []) if item["status"] in {"uploaded", "receiving"})
    return total


def validate_shapefile_bundle(file_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_stem: dict[str, dict[str, dict[str, Any]]] = {}
    for record in file_records:
        if record["extension"] in SHAPEFILE_EXTENSIONS:
            by_stem.setdefault(shapefile_stem(record["stored_filename"]), {})[record["extension"]] = record
    for stem, parts in by_stem.items():
        missing = sorted(SHAPEFILE_REQUIRED - parts.keys())
        if missing:
            for record in parts.values():
                record["status"] = "invalid"
                record["validation_errors"].append({
                    "error_code": "missing_shapefile_component",
                    "error_message": f"{record['stored_filename']}: add {', '.join(missing)} for Shapefile bundle {stem}",
                })
        elif ".prj" not in parts:
            for record in parts.values():
                record["warnings"].append({"warning_code": "missing_crs", "message": f"{stem}.prj is recommended; assign a CRS before analysis"})
    return file_records


def ingest_file_paths(config: DashboardConfig, run: dict[str, Any], paths: list[tuple[str, Path, str | None]]) -> dict[str, Any]:
    with project_upload_lock(config, run["project_id"]):
        return _ingest_file_paths_locked(config, run, paths)


def _ingest_file_paths_locked(config: DashboardConfig, run: dict[str, Any], paths: list[tuple[str, Path, str | None]], *, staged_bytes: int = 0, source_batch_id: str | None = None) -> dict[str, Any]:
    if not paths:
        raise upload_error("empty_batch", "Select at least one file")
    if len(paths) > config.max_batch_files:
        raise upload_error("too_many_files", f"Maximum files per batch is {config.max_batch_files}", status=413)
    names = [normalize_filename(name) for name, _, _ in paths]
    if len(set(name.lower() for name in names)) != len(names):
        raise upload_error("duplicate_filename", "File names in a batch must be unique")
    existing_names = {item.get("stored_filename", "").lower() for item in run.get("inputs", [])}
    if any(name.lower() in existing_names for name in names):
        raise upload_error("duplicate_filename", "A file with this name is already in the run; create a new run to replace it")
    sizes = [path.stat().st_size for _, path, _ in paths]
    for name, size in zip(names, sizes):
        if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
            raise upload_error("unsupported_file_type", f"Unsupported file extension for {name}", name)
        if size > config.max_upload_file_bytes:
            raise upload_error("file_too_large", f"{name} exceeds the {config.max_upload_file_bytes} byte file limit", name, 413)
    if sum(sizes) > config.max_upload_batch_bytes:
        raise upload_error("batch_too_large", f"Batch exceeds the {config.max_upload_batch_bytes} byte limit", status=413)
    run = get_run(config, run["run_id"])
    if run["status"] not in {"created", "uploaded", "retrying"}:
        raise upload_error("run_not_editable", "Uploads are closed for this analysis")
    current_names = {item.get("stored_filename", "").lower() for item in run.get("inputs", [])}
    if any(name.lower() in current_names for name in names):
        raise upload_error("duplicate_filename", "A file with this name is already in the run; create a new run to replace it")
    if project_upload_bytes(config, run["project_id"]) - staged_bytes + sum(sizes) > config.max_project_bytes:
        raise upload_error("project_quota_exceeded", f"Project upload quota is {config.max_project_bytes} bytes", status=413)
    raw_dir = run_dir(config, run["run_id"]) / "inputs" / "raw"
    validated_dir = run_dir(config, run["run_id"]) / "inputs" / "validated"
    raw_dir.mkdir(parents=True, exist_ok=True)
    validated_dir.mkdir(parents=True, exist_ok=True)
    records = []
    try:
        for (original, source, content_type), name, size in zip(paths, names, sizes):
            extension = Path(name).suffix.lower()
            raw_path = ensure_child_path(raw_dir, raw_dir / name)
            shutil.copyfile(source, raw_path)
            record = {
                "id": uuid4().hex, "project_id": run["project_id"], "run_id": run["run_id"],
                "role": "input", "file_type": file_type_from_extension(extension),
                "dataset_id": shapefile_stem(name) if extension in SHAPEFILE_EXTENSIONS else uuid4().hex,
                "original_filename": original, "stored_filename": name, "extension": extension,
                "source_batch_id": source_batch_id,
                "content_type": content_type, "path": str(raw_path), "size_bytes": size,
                "checksum_sha256": checksum_sha256(raw_path), "status": "validating",
                "validation_errors": [], "warnings": [], "metadata": {},
                "created_at": utc_now(), "updated_at": utc_now(),
            }
            records.append(record)
    except Exception:
        for name in names:
            (raw_dir / name).unlink(missing_ok=True)
        raise
    try:
        validate_shapefile_bundle(records)
        for record in records:
            raw_path = Path(record["path"])
            extension = record["extension"]
            try:
                if record["status"] != "invalid":
                    record["metadata"] = validate_file_content(raw_path, extension)
                    if record["metadata"].get("crs") is None and extension in {".tif", ".tiff", ".geojson", ".json", ".shp"}:
                        record["warnings"].append({"warning_code": "missing_crs", "message": "CRS is missing; assign a CRS before analysis"})
                    record["status"] = "valid"
            except HTTPException as exc:
                record["status"] = "invalid"
                record["validation_errors"].append({
                    **exc.detail, "filename": record["stored_filename"],
                    "validation_stage": "content", "retryable": False,
                })
            record["updated_at"] = utc_now()
        # A bundle is one dataset: one corrupt component invalidates all its siblings.
        invalid_stems = {shapefile_stem(item["stored_filename"]) for item in records if item["extension"] in SHAPEFILE_EXTENSIONS and item["status"] == "invalid"}
        for record in records:
            if record["extension"] in SHAPEFILE_EXTENSIONS and shapefile_stem(record["stored_filename"]) in invalid_stems and record["status"] == "valid":
                record["status"] = "invalid"
                record["validation_errors"].append({"error_code": "invalid_shapefile_bundle", "error_message": f"{record['stored_filename']}: another bundle component failed validation"})
        for record in records:
            raw_path = Path(record["path"])
            if record["status"] == "invalid":
                raw_path.unlink(missing_ok=True)
                record["path"] = None
            else:
                validated_path = ensure_child_path(validated_dir, validated_dir / record["stored_filename"])
                shutil.move(raw_path, validated_path)
                record["path"] = str(validated_path)
        run = update_run(config, run["run_id"], status="uploaded", status_message="Files validated", inputs=run.get("inputs", []) + records)
    except Exception:
        for name in names:
            (raw_dir / name).unlink(missing_ok=True)
            (validated_dir / name).unlink(missing_ok=True)
        raise
    batch_status = "valid" if all(record["status"] == "valid" for record in records) else "completed_with_errors"
    return {"run_id": run["run_id"], "batch_status": batch_status, "files": records, "run": run}


def ingest_base64_files(
    config: DashboardConfig,
    run: dict[str, Any],
    uploads: list[dict[str, str]],
) -> dict[str, Any]:
    if len(uploads) > config.max_batch_files:
        raise upload_error("too_many_files", f"Maximum files per batch is {config.max_batch_files}", status=413)
    with tempfile.TemporaryDirectory(dir=run_dir(config, run["run_id"])) as temporary:
        paths = []
        total_size = 0
        for index, upload in enumerate(uploads):
            name = normalize_filename(upload.get("filename", ""))
            if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
                raise upload_error("unsupported_file_type", f"Unsupported file extension for {name}", name)
            content = decode_upload_content(upload.get("content_b64", ""))
            if len(content) > config.max_upload_file_bytes:
                raise upload_error("file_too_large", f"{name} exceeds the {config.max_upload_file_bytes} byte file limit", name, 413)
            total_size += len(content)
            if total_size > config.max_upload_batch_bytes:
                raise upload_error("batch_too_large", f"Batch exceeds the {config.max_upload_batch_bytes} byte limit", status=413)
            path = Path(temporary) / str(index)
            path.write_bytes(content)
            paths.append((upload["filename"], path, upload.get("content_type")))
        return ingest_file_paths(config, run, paths)


def batch_dir(config: DashboardConfig, run_id: str, batch_id: str) -> Path:
    return run_dir(config, run_id) / "inputs" / "staging" / safe_id(batch_id, "batch_id")


def get_upload_batch(config: DashboardConfig, run_id: str, batch_id: str) -> dict[str, Any]:
    directory = batch_dir(config, run_id, batch_id)
    batch = read_json(directory / "batch.json", "Upload batch not found")
    if batch.get("run_id") != run_id or batch.get("batch_id") != batch_id:
        raise upload_error("invalid_batch", "Upload batch identity is invalid")
    for item in batch.get("files", []):
        name = item.get("filename", "")
        if normalize_filename(name) != name:
            raise upload_error("invalid_batch", "Upload batch contains an unsafe filename")
        ensure_child_path(directory, directory / name)
    return batch


def begin_batch_file_transfer(config: DashboardConfig, project_id: str, run_id: str, batch_id: str, file_index: int, *, replace_uploaded: bool = False) -> dict[str, Any]:
    with project_upload_lock(config, project_id):
        run = get_run(config, run_id)
        if run["project_id"] != project_id or run["status"] not in {"created", "uploaded", "retrying"}:
            raise upload_error("run_not_editable", "Uploads are closed for this analysis")
        batch = get_upload_batch(config, run_id, batch_id)
        if batch["status"] not in {"created", "uploading", "interrupted"} or file_index < 0 or file_index >= len(batch["files"]):
            raise upload_error("batch_not_ready", "Batch or file index is not ready")
        item = batch["files"][file_index]
        was_uploaded = item["status"] == "uploaded"
        if item["status"] == "uploaded" and replace_uploaded:
            (batch_dir(config, run_id, batch_id) / item["filename"]).unlink(missing_ok=True)
            item["status"] = "pending"
        if item["status"] == "pending":
            if batch["status"] == "interrupted" and not was_uploaded and project_upload_bytes(config, project_id) + item["size_bytes"] > config.max_project_bytes:
                raise upload_error("project_quota_exceeded", f"Project upload quota is {config.max_project_bytes} bytes", item["filename"], 413)
            item["status"] = "receiving"
            if batch["status"] == "created":
                batch["status"] = "uploading"
            batch["updated_at"] = utc_now()
            write_json(batch_dir(config, run_id, batch_id) / "batch.json", batch)
        elif item["status"] != "uploaded":
            raise upload_error("file_uploading", f"{item['filename']} is already being uploaded", item["filename"])
        return dict(item)


def finish_batch_file_transfer(config: DashboardConfig, project_id: str, run_id: str, batch_id: str, file_index: int, status: str) -> None:
    if status not in {"pending", "uploaded"}:
        raise ValueError("Invalid transfer status")
    with project_upload_lock(config, project_id):
        batch = get_upload_batch(config, run_id, batch_id)
        if batch["status"] not in {"uploading", "interrupted"} or batch["files"][file_index]["status"] != "receiving":
            raise upload_error("batch_not_ready", "Batch transfer state changed")
        batch["files"][file_index]["status"] = status
        if status == "pending":
            batch["status"] = "interrupted"
        batch["updated_at"] = utc_now()
        write_json(batch_dir(config, run_id, batch_id) / "batch.json", batch)


def cleanup_abandoned_uploads(config: DashboardConfig, project_id: str, *, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    removed = 0
    with project_upload_lock(config, project_id):
        for run in list_runs(config, project_id):
            staging = run_dir(config, run["run_id"]) / "inputs" / "staging"
            for directory in staging.iterdir() if staging.exists() else []:
                if not directory.is_dir():
                    continue
                metadata = directory / "batch.json"
                updated = datetime.fromtimestamp(directory.stat().st_mtime, timezone.utc)
                if metadata.exists():
                    try:
                        updated = datetime.fromisoformat(json.loads(metadata.read_text())["updated_at"])
                    except (ValueError, KeyError, TypeError):
                        pass
                for partial in directory.glob("*.part"):
                    updated = max(updated, datetime.fromtimestamp(partial.stat().st_mtime, timezone.utc))
                if now - updated >= timedelta(hours=24):
                    shutil.rmtree(directory)
                    removed += 1
    return removed


def create_upload_batch(config: DashboardConfig, run: dict[str, Any], files: list[dict[str, Any]], *, idempotency_key: str | None = None) -> dict[str, Any]:
    if idempotency_key is not None and (not idempotency_key or len(idempotency_key) > 64 or safe_id(idempotency_key, "idempotency_key") != idempotency_key):
        raise upload_error("invalid_idempotency_key", "Invalid idempotency key")
    if not files or len(files) > config.max_batch_files:
        raise upload_error("too_many_files", f"Select 1 to {config.max_batch_files} files", status=413)
    names = [normalize_filename(item.get("filename", "")) for item in files]
    if len({name.lower() for name in names}) != len(names):
        raise upload_error("duplicate_filename", "File names in a batch must be unique")
    existing = {item.get("stored_filename", "").lower() for item in run.get("inputs", [])}
    entries = []
    total = 0
    for item, name in zip(files, names):
        if name.lower() in existing:
            raise upload_error("duplicate_filename", f"{name} is already in this run", name)
        if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
            raise upload_error("unsupported_file_type", f"Unsupported file extension for {name}", name)
        size = item.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise upload_error("invalid_size", f"{name} needs a nonnegative byte size", name)
        if size > config.max_upload_file_bytes:
            raise upload_error("file_too_large", f"{name} exceeds the {config.max_upload_file_bytes} byte file limit", name, 413)
        total += size
        entries.append({"filename": name, "original_filename": item["filename"], "size_bytes": size, "content_type": item.get("content_type"), "status": "pending"})
    if total > config.max_upload_batch_bytes:
        raise upload_error("batch_too_large", f"Batch exceeds the {config.max_upload_batch_bytes} byte limit", status=413)
    with project_upload_lock(config, run["project_id"]):
        current_run = get_run(config, run["run_id"])
        if current_run["status"] not in {"created", "uploaded", "retrying"}:
            raise upload_error("run_not_editable", "Uploads are closed for this analysis")
        current_names = {item.get("stored_filename", "").lower() for item in current_run.get("inputs", [])}
        if any(name.lower() in current_names for name in names):
            raise upload_error("duplicate_filename", "A file with this name is already in the run")
        staging = run_dir(config, run["run_id"]) / "inputs" / "staging"
        for manifest in staging.glob("*/batch.json"):
            batch = get_upload_batch(config, run["run_id"], manifest.parent.name)
            if idempotency_key and batch.get("idempotency_key") == idempotency_key:
                if [(entry["filename"], entry["size_bytes"]) for entry in batch["files"]] != [(entry["filename"], entry["size_bytes"]) for entry in entries]:
                    raise upload_error("idempotency_conflict", "Idempotency key was used for different files")
                return batch
            if batch["status"] in {"created", "uploading", "interrupted", "validating"} and any(entry["filename"].lower() in {name.lower() for name in names} for entry in batch["files"]):
                raise upload_error("duplicate_filename", "A file with this name is already in an unfinished batch")
        if project_upload_bytes(config, run["project_id"]) + total > config.max_project_bytes:
            raise upload_error("project_quota_exceeded", f"Project upload quota is {config.max_project_bytes} bytes", status=413)
        batch_id = uuid4().hex
        directory = batch_dir(config, run["run_id"], batch_id)
        directory.mkdir(parents=True)
        batch = {"batch_id": batch_id, "run_id": run["run_id"], "project_id": run["project_id"], "status": "created", "files": entries, "idempotency_key": idempotency_key, "created_at": utc_now(), "updated_at": utc_now()}
        write_json(directory / "batch.json", batch)
    return batch


def complete_upload_batch(config: DashboardConfig, run: dict[str, Any], batch_id: str) -> dict[str, Any]:
    directory = batch_dir(config, run["run_id"], batch_id)
    with project_upload_lock(config, run["project_id"]):
        batch = get_upload_batch(config, run["run_id"], batch_id)
        if batch["status"] == "completed":
            return batch["result"]
        if batch["status"] == "validating":
            current_run = get_run(config, run["run_id"])
            records = [item for item in current_run.get("inputs", []) if item.get("source_batch_id") == batch_id]
            if {item["stored_filename"] for item in records} == {item["filename"] for item in batch["files"]}:
                result = {"run_id": run["run_id"], "batch_status": "valid" if all(item["status"] == "valid" for item in records) else "completed_with_errors", "files": records, "run": current_run}
                batch["status"] = "completed"
                batch["result"] = result
                batch["updated_at"] = utc_now()
                write_json(directory / "batch.json", batch)
                for item in batch["files"]:
                    (directory / item["filename"]).unlink(missing_ok=True)
                return result
        if batch["status"] not in {"created", "uploading", "interrupted", "validating"}:
            raise upload_error("batch_not_ready", "Batch cannot be finalized")
        missing = [item["filename"] for item in batch["files"] if item["status"] != "uploaded"]
        if missing:
            raise upload_error("batch_incomplete", f"Upload these files before validating: {', '.join(missing)}")
        batch["status"] = "validating"
        batch["updated_at"] = utc_now()
        write_json(directory / "batch.json", batch)
        paths = [(item["original_filename"], directory / item["filename"], item.get("content_type")) for item in batch["files"]]
        try:
            result = _ingest_file_paths_locked(config, run, paths, staged_bytes=sum(item["size_bytes"] for item in batch["files"]), source_batch_id=batch_id)
        except Exception:
            batch["status"] = "failed"
            batch["updated_at"] = utc_now()
            write_json(directory / "batch.json", batch)
            for _, path, _ in paths:
                path.unlink(missing_ok=True)
            raise
        batch["status"] = "completed"
        batch["updated_at"] = utc_now()
        batch["result"] = result
        write_json(directory / "batch.json", batch)
        for _, path, _ in paths:
            path.unlink(missing_ok=True)
        return result


def cancel_upload_batch(config: DashboardConfig, run: dict[str, Any], batch_id: str) -> dict[str, str]:
    with project_upload_lock(config, run["project_id"]):
        directory = batch_dir(config, run["run_id"], batch_id)
        batch = get_upload_batch(config, run["run_id"], batch_id)
        if batch["status"] == "completed":
            raise upload_error("batch_completed", "Completed uploads cannot be canceled")
        shutil.rmtree(directory)
        return {"batch_id": batch_id, "status": "canceled"}


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
