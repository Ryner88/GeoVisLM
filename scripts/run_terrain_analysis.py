from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import typer

from geovis_lm.gis.terrain import (
    calculate_hillshade,
    calculate_slope_degrees,
    classify_slope_risk,
    load_dem,
    save_raster,
)

app = typer.Typer(help="GeoVisLM terrain analysis tools.")


@app.command()
def terrain(
    dem_path: str = typer.Argument(..., help="Path to DEM raster, usually a GeoTIFF."),
    output_dir: str = typer.Option("outputs/maps", help="Output directory."),
):
    dem_path = Path(dem_path)
    output_dir = Path(output_dir)

    typer.echo(f"Loading DEM: {dem_path}")
    dem, profile, transform, crs = load_dem(dem_path)

    typer.echo("Calculating slope...")
    slope = calculate_slope_degrees(dem, transform)

    typer.echo("Calculating hillshade...")
    hillshade = calculate_hillshade(dem, transform)

    typer.echo("Classifying terrain risk...")
    risk = classify_slope_risk(slope)

    slope_path = save_raster(
        output_dir / "slope_degrees.tif", slope, profile, dtype="float32", nodata=-9999
    )
    hillshade_path = save_raster(
        output_dir / "hillshade.tif", hillshade, profile, dtype="float32", nodata=-9999
    )
    risk_path = save_raster(
        output_dir / "terrain_risk.tif", risk, profile, dtype="uint8", nodata=0
    )

    typer.echo("")
    typer.echo("Terrain analysis complete.")
    typer.echo(f"Slope:     {slope_path}")
    typer.echo(f"Hillshade: {hillshade_path}")
    typer.echo(f"Risk:      {risk_path}")


if __name__ == "__main__":
    app()
