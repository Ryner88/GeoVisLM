from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import os


class DatabaseUnavailableError(RuntimeError):
    """Raised when database settings or drivers are unavailable."""


RUN_STATUSES = ("created", "uploaded", "running", "completed", "failed", "archived")


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

create table if not exists geovis_runs (
    id uuid primary key,
    status text not null check (status in ('created', 'uploaded', 'running', 'completed', 'failed', 'archived')),
    input_filename text,
    crs text,
    bounds geometry(Polygon, 4326),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists geovis_layers (
    id uuid primary key,
    run_id uuid not null references geovis_runs(id) on delete cascade,
    layer_type text not null,
    filename text not null,
    path text not null,
    crs text,
    bounds geometry(Polygon, 4326),
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


def store_uploaded_layer_metadata(
    layer_id: str,
    run_id: str,
    layer_type: str,
    path: str | Path,
    crs: str | None = None,
    metadata: dict[str, Any] | None = None,
    database_url: str | None = None,
) -> str:
    path = Path(path)
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into geovis_layers (id, run_id, layer_type, filename, path, crs, metadata)
                values (%s, %s, %s, %s, %s, %s, %s)
                on conflict (id) do update set
                    layer_type = excluded.layer_type,
                    filename = excluded.filename,
                    path = excluded.path,
                    crs = excluded.crs,
                    metadata = excluded.metadata
                """,
                (layer_id, run_id, layer_type, path.name, str(path), crs, metadata or {}),
            )
        conn.commit()
    return layer_id


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
