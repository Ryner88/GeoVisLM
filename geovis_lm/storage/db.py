from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import os


class DatabaseUnavailableError(RuntimeError):
    """Raised when database settings or drivers are unavailable."""


RUN_STATUSES = (
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
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def database_url_from_env() -> str | None:
    return os.getenv("GEOVIS_DATABASE_URL")


def import_psycopg():
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise DatabaseUnavailableError(
            "PostGIS storage requires the optional 'psycopg' package. "
            "Install it and set GEOVIS_DATABASE_URL, or continue using file-only mode."
        ) from exc
    return psycopg


def require_database_url(database_url: str | None = None) -> str:
    resolved = database_url or database_url_from_env()
    if not resolved:
        raise DatabaseUnavailableError(
            "GEOVIS_DATABASE_URL is not configured. File-only mode remains available."
        )
    return resolved


def schema_sql() -> str:
    return """
create extension if not exists postgis;

create table if not exists geovis_projects (
    id uuid primary key,
    name text not null,
    slug text not null,
    owner_user_id text not null,
    status text not null check (status in ('active', 'archived', 'deleted')),
    description text not null default '',
    default_crs text,
    area_of_interest geometry(Geometry, 4326),
    metadata jsonb not null default '{}'::jsonb,
    archived_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists geovis_runs (
    id uuid primary key,
    project_id uuid references geovis_projects(id) on delete cascade,
    workflow_type text not null default 'terrain',
    name text,
    status text not null check (status in ('created', 'uploaded', 'queued', 'running', 'completed', 'failed', 'canceling', 'canceled', 'retrying', 'reported', 'archived')),
    created_by_user_id text,
    input_filename text,
    crs text,
    bounds geometry(Polygon, 4326),
    started_at timestamptz,
    completed_at timestamptz,
    failed_at timestamptz,
    retry_of_run_id uuid references geovis_runs(id),
    attempt_number integer not null default 1,
    retryable boolean not null default false,
    error_code text,
    error_message text,
    error_detail text,
    parameters jsonb not null default '{}'::jsonb,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists geovis_files (
    id uuid primary key,
    project_id uuid references geovis_projects(id) on delete cascade,
    run_id uuid references geovis_runs(id) on delete cascade,
    role text not null,
    file_type text not null,
    original_filename text,
    stored_filename text not null,
    path text not null,
    status text not null,
    content_type text,
    extension text,
    size_bytes bigint,
    checksum_sha256 text,
    crs text,
    bounds geometry(Geometry, 4326),
    validation_errors jsonb not null default '[]'::jsonb,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists geovis_run_status_events (
    id uuid primary key,
    run_id uuid not null references geovis_runs(id) on delete cascade,
    status text not null,
    message text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists geovis_outputs (
    id uuid primary key,
    run_id uuid not null references geovis_runs(id) on delete cascade,
    output_type text not null,
    path text not null,
    crs text,
    bounds geometry(Polygon, 4326),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists geovis_reports (
    id uuid primary key,
    run_id uuid not null references geovis_runs(id) on delete cascade,
    report_type text not null,
    path text not null,
    format text not null,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists geovis_visualizations (
    id uuid primary key,
    run_id uuid not null references geovis_runs(id) on delete cascade,
    visualization_type text not null,
    path text not null,
    state_path text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
""".strip()


def connect(database_url: str | None = None):
    resolved_url = require_database_url(database_url)
    psycopg = import_psycopg()
    return psycopg.connect(resolved_url)


def initialize_schema(database_url: str | None = None) -> None:
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(schema_sql())
        conn.commit()


def create_run_record(
    run_id: str,
    status: str = "created",
    input_filename: str | None = None,
    crs: str | None = None,
    metadata: dict[str, Any] | None = None,
    database_url: str | None = None,
) -> str:
    if status not in RUN_STATUSES:
        raise ValueError(f"Invalid run status: {status}")

    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into geovis_runs (id, status, input_filename, crs, metadata, updated_at)
                values (%s, %s, %s, %s, %s, now())
                on conflict (id) do update set
                    status = excluded.status,
                    input_filename = excluded.input_filename,
                    crs = excluded.crs,
                    metadata = excluded.metadata,
                    updated_at = now()
                """,
                (run_id, status, input_filename, crs, metadata or {}),
            )
        conn.commit()
    return run_id


def create_project_record(
    project_id: str,
    name: str,
    slug: str,
    owner_user_id: str,
    status: str = "active",
    description: str = "",
    metadata: dict[str, Any] | None = None,
    database_url: str | None = None,
) -> str:
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into geovis_projects (id, name, slug, owner_user_id, status, description, metadata, updated_at)
                values (%s, %s, %s, %s, %s, %s, %s, now())
                on conflict (id) do update set
                    name = excluded.name,
                    slug = excluded.slug,
                    owner_user_id = excluded.owner_user_id,
                    status = excluded.status,
                    description = excluded.description,
                    metadata = excluded.metadata,
                    updated_at = now()
                """,
                (project_id, name, slug, owner_user_id, status, description, metadata or {}),
            )
        conn.commit()
    return project_id


def store_file_metadata(
    file_id: str,
    project_id: str,
    run_id: str | None,
    role: str,
    file_type: str,
    stored_filename: str,
    path: str | Path,
    status: str,
    original_filename: str | None = None,
    crs: str | None = None,
    metadata: dict[str, Any] | None = None,
    database_url: str | None = None,
) -> str:
    path = Path(path)
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into geovis_files (
                    id, project_id, run_id, role, file_type, original_filename,
                    stored_filename, path, status, crs, metadata, updated_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                on conflict (id) do update set
                    role = excluded.role,
                    file_type = excluded.file_type,
                    original_filename = excluded.original_filename,
                    stored_filename = excluded.stored_filename,
                    path = excluded.path,
                    status = excluded.status,
                    crs = excluded.crs,
                    metadata = excluded.metadata,
                    updated_at = now()
                """,
                (
                    file_id,
                    project_id,
                    run_id,
                    role,
                    file_type,
                    original_filename or stored_filename,
                    stored_filename,
                    str(path),
                    status,
                    crs,
                    metadata or {},
                ),
            )
        conn.commit()
    return file_id


def store_uploaded_layer_metadata(
    layer_id: str,
    run_id: str,
    layer_type: str,
    path: str | Path,
    crs: str | None = None,
    metadata: dict[str, Any] | None = None,
    database_url: str | None = None,
) -> str:
    file_metadata = metadata or {}
    project_id = file_metadata.pop("project_id", None)
    if project_id is None:
        raise ValueError("metadata.project_id is required for uploaded layer metadata")
    return store_file_metadata(
        layer_id,
        project_id,
        run_id,
        role="input",
        file_type=layer_type,
        stored_filename=Path(path).name,
        path=path,
        status=file_metadata.pop("status", "valid"),
        crs=crs,
        metadata=file_metadata,
        database_url=database_url,
    )


def store_output_metadata(
    output_id: str,
    run_id: str,
    output_type: str,
    path: str | Path,
    crs: str | None = None,
    metadata: dict[str, Any] | None = None,
    database_url: str | None = None,
) -> str:
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into geovis_outputs (id, run_id, output_type, path, crs, metadata)
                values (%s, %s, %s, %s, %s, %s)
                on conflict (id) do update set
                    output_type = excluded.output_type,
                    path = excluded.path,
                    crs = excluded.crs,
                    metadata = excluded.metadata
                """,
                (output_id, run_id, output_type, str(path), crs, metadata or {}),
            )
        conn.commit()
    return output_id
