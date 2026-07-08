from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import typer

from geovis_lm.gis.risk import execute_flood_risk_workflow


app = typer.Typer(help="Run the GeoVisLM flood risk screening workflow.")


@app.command()
def flood(
    dem: Path = typer.Option(..., exists=True, help="DEM GeoTIFF used for terrain and elevation inputs."),
    rivers: Path = typer.Option(..., exists=True, help="River or stream vector layer."),
    output_dir: Path = typer.Option(Path("outputs/flood_risk"), help="Directory for flood risk outputs."),
    river_near_buffer: float = typer.Option(150.0, help="High-risk river buffer distance in DEM CRS units."),
    river_medium_buffer: float = typer.Option(450.0, help="Moderate-risk river buffer distance in DEM CRS units."),
    river_far_buffer: float = typer.Option(900.0, help="Low proximity-risk river buffer distance in DEM CRS units."),
):
    summary = execute_flood_risk_workflow(
        dem,
        rivers,
        output_dir=output_dir,
        parameters={
            "river_near_buffer": river_near_buffer,
            "river_medium_buffer": river_medium_buffer,
            "river_far_buffer": river_far_buffer,
        },
    )
    typer.echo(json.dumps(summary["outputs"], indent=2, sort_keys=True))


if __name__ == "__main__":
    app()
