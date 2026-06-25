from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse


class QGISUnavailableError(RuntimeError):
    """Raised when PyQGIS is not available in the active Python environment."""


@dataclass(frozen=True)
class QGISWorkflowOutputs:
    slope: Path
    hillshade: Path
    clipped_raster: Path | None = None


def import_qgis_processing():
    try:
        import processing
        from qgis.core import QgsApplication
    except ModuleNotFoundError as exc:
        raise QGISUnavailableError(
            "PyQGIS is not available in this Python environment. Install QGIS "
            "separately and run this script with QGIS's configured Python, or "
            "use the Rasterio terrain pipeline for the basic workflow."
        ) from exc

    return QgsApplication, processing


def planned_outputs(output_dir: Path) -> QGISWorkflowOutputs:
    return QGISWorkflowOutputs(
        slope=output_dir / "qgis_slope_degrees.tif",
        hillshade=output_dir / "qgis_hillshade.tif",
        clipped_raster=None,
    )


def run_qgis_terrain_workflow(dem_path: Path, output_dir: Path) -> QGISWorkflowOutputs:
    if not dem_path.exists():
        raise FileNotFoundError(f"DEM raster does not exist: {dem_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = planned_outputs(output_dir)
    QgsApplication, processing = import_qgis_processing()

    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        processing.run(
            "native:slope",
            {
                "INPUT": str(dem_path),
                "Z_FACTOR": 1.0,
                "OUTPUT": str(outputs.slope),
            },
        )
        processing.run(
            "native:hillshade",
            {
                "INPUT": str(dem_path),
                "Z_FACTOR": 1.0,
                "AZIMUTH": 315.0,
                "V_ANGLE": 45.0,
                "OUTPUT": str(outputs.hillshade),
            },
        )
    finally:
        qgs.exitQgis()

    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run optional QGIS Processing terrain workflows."
    )
    parser.add_argument("--dem", type=Path, required=True, help="Input DEM raster path.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/qgis"),
        help="Directory for QGIS-generated outputs.",
    )
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Print planned outputs without importing or running PyQGIS.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    outputs = planned_outputs(args.output_dir)

    if args.plan_only:
        print("QGIS terrain workflow plan:")
        print(f"Slope:     {outputs.slope}")
        print(f"Hillshade: {outputs.hillshade}")
        return

    try:
        outputs = run_qgis_terrain_workflow(args.dem, args.output_dir)
    except QGISUnavailableError as exc:
        raise SystemExit(str(exc)) from exc

    print("QGIS terrain workflow complete.")
    print(f"Slope:     {outputs.slope}")
    print(f"Hillshade: {outputs.hillshade}")


if __name__ == "__main__":
    main()
