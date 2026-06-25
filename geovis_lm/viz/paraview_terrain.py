"""
ParaView terrain rendering entry point.

Run this script with ParaView's Python interpreter, not the project virtualenv:

    pvpython geovis_lm/viz/paraview_terrain.py data/sample/sample_dem.tif

The script expects ParaView to include GDAL raster reader support. It renders a
DEM as a warped terrain surface, writes a PNG screenshot, and saves a ParaView
state file for later interactive refinement.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_DIR = Path("outputs/renders")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a DEM raster as a terrain surface in ParaView."
    )
    parser.add_argument(
        "dem_path",
        type=Path,
        help="Input DEM raster path, usually a GeoTIFF generated or collected for analysis.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for render outputs. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--output-prefix",
        default="terrain",
        help="Base filename for screenshot and ParaView state outputs.",
    )
    parser.add_argument(
        "--elevation-scale",
        type=float,
        default=1.0,
        help="Vertical exaggeration factor applied by Warp By Scalar.",
    )
    parser.add_argument(
        "--image-width",
        type=int,
        default=1600,
        help="Screenshot width in pixels.",
    )
    parser.add_argument(
        "--image-height",
        type=int,
        default=1000,
        help="Screenshot height in pixels.",
    )
    return parser.parse_args()


def import_paraview_simple() -> Any:
    try:
        from paraview import simple
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "ParaView Python modules are not installed in this interpreter. "
            "Run with pvpython, for example: "
            "pvpython geovis_lm/viz/paraview_terrain.py data/sample/sample_dem.tif"
        ) from exc

    return simple


def get_first_scalar_name(source: Any) -> str | None:
    point_data = source.PointData
    if len(point_data) > 0:
        return point_data[0].GetName()

    cell_data = source.CellData
    if len(cell_data) > 0:
        return cell_data[0].GetName()

    return None


def render_terrain(
    dem_path: Path,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    output_prefix: str = "terrain",
    elevation_scale: float = 1.0,
    image_size: tuple[int, int] = (1600, 1000),
) -> tuple[Path, Path]:
    if not dem_path.exists():
        raise FileNotFoundError(f"DEM raster does not exist: {dem_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = output_dir / f"{output_prefix}.png"
    state_path = output_dir / f"{output_prefix}.pvsm"

    pv = import_paraview_simple()
    pv._DisableFirstRenderCameraReset()

    raster = pv.OpenDataFile(str(dem_path))
    pv.UpdatePipeline(proxy=raster)

    scalar_name = get_first_scalar_name(raster)
    if scalar_name is None:
        raise RuntimeError(f"No scalar raster band found in DEM: {dem_path}")

    warped = pv.WarpByScalar(Input=raster)
    warped.Scalars = ["POINTS", scalar_name]
    warped.ScaleFactor = elevation_scale
    pv.UpdatePipeline(proxy=warped)

    view = pv.GetActiveViewOrCreate("RenderView")
    view.ViewSize = list(image_size)
    view.Background = [0.06, 0.08, 0.1]

    display = pv.Show(warped, view)
    display.Representation = "Surface"
    pv.ColorBy(display, ("POINTS", scalar_name))
    display.RescaleTransferFunctionToDataRange(True, False)
    display.SetScalarBarVisibility(view, True)

    color_map = pv.GetColorTransferFunction(scalar_name)
    color_map.ApplyPreset("Terrain", True)

    opacity_map = pv.GetOpacityTransferFunction(scalar_name)
    opacity_map.RescaleTransferFunctionToDataRange()

    view.ResetCamera()
    camera = view.GetActiveCamera()
    camera.Elevation(35)
    camera.Azimuth(35)
    view.ResetCamera()

    pv.Render(view)
    pv.SaveScreenshot(str(screenshot_path), view)
    pv.SaveState(str(state_path))

    return screenshot_path, state_path


def main() -> None:
    args = parse_args()
    screenshot_path, state_path = render_terrain(
        dem_path=args.dem_path,
        output_dir=args.output_dir,
        output_prefix=args.output_prefix,
        elevation_scale=args.elevation_scale,
        image_size=(args.image_width, args.image_height),
    )

    print("ParaView terrain render complete.")
    print(f"Screenshot: {screenshot_path}")
    print(f"State:      {state_path}")


if __name__ == "__main__":
    main()
