from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import typer

from geovis_lm.gis.risk import execute_wildfire_risk_workflow


app = typer.Typer(help="Run the GeoVisLM wildfire risk screening workflow.")


@app.command()
def wildfire(
    dem: Path = typer.Option(..., exists=True, help="DEM GeoTIFF used for slope inputs."),
    fuel: Path = typer.Option(..., exists=True, help="Vegetation or fuel vector/raster input."),
    output_dir: Path = typer.Option(Path("outputs/wildfire_risk"), help="Directory for wildfire risk outputs."),
    proximity: list[Path] = typer.Option(
        None,
        exists=True,
        help="Optional proximity vector layer, repeatable for roads, structures, or sensor zones.",
    ),
    fuel_field: str | None = typer.Option(None, help="Fuel attribute field to normalize when fuel is a vector."),
):
    summary = execute_wildfire_risk_workflow(
        dem,
        fuel,
        output_dir=output_dir,
        proximity_paths=proximity or [],
        parameters={"fuel_field": fuel_field} if fuel_field else {},
    )
    typer.echo(json.dumps(summary["outputs"], indent=2, sort_keys=True))


if __name__ == "__main__":
    app()
