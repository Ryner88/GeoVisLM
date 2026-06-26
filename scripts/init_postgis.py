from pathlib import Path
import argparse
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from geovis_lm.storage.db import (
    DatabaseUnavailableError,
    database_url_from_env,
    initialize_schema,
    schema_sql,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize optional PostgreSQL/PostGIS storage for GeoVisLM."
    )
    parser.add_argument(
        "--database-url",
        help="PostgreSQL connection URL. Defaults to GEOVIS_DATABASE_URL.",
    )
    parser.add_argument(
        "--print-sql",
        action="store_true",
        help="Print schema SQL without connecting to a database.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and print what would run without connecting.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.print_sql:
        print(schema_sql())
        return

    database_url = args.database_url or database_url_from_env()
    if args.dry_run:
        print("PostGIS initialization dry run.")
        print(f"Database URL configured: {'yes' if database_url else 'no'}")
        print(
            "Schema tables: geovis_projects, geovis_runs, geovis_files, "
            "geovis_run_status_events, geovis_outputs, geovis_reports, "
            "geovis_visualizations"
        )
        return

    try:
        initialize_schema(database_url)
    except DatabaseUnavailableError as exc:
        raise SystemExit(str(exc)) from exc

    print("PostGIS schema initialized.")


if __name__ == "__main__":
    main()
