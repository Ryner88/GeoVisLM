from pathlib import Path
import argparse
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from geovis_lm.reports.terrain_report import (
    TerrainReportInputs,
    write_markdown_report,
    write_pdf_report,
)


def existing_or_default(path: Path) -> Path | None:
    return path if path.exists() else None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate GeoVisLM terrain analysis reports."
    )
    parser.add_argument("--dem", type=Path, required=True, help="Input DEM raster path.")
    parser.add_argument(
        "--maps-dir",
        type=Path,
        default=Path("outputs/maps"),
        help="Directory containing slope_degrees.tif, hillshade.tif, and terrain_risk.tif.",
    )
    parser.add_argument(
        "--renders-dir",
        type=Path,
        default=Path("outputs/renders"),
        help="Directory containing optional ParaView render outputs.",
    )
    parser.add_argument(
        "--slope",
        type=Path,
        help="Slope raster path. Defaults to <maps-dir>/slope_degrees.tif.",
    )
    parser.add_argument(
        "--hillshade",
        type=Path,
        help="Hillshade raster path. Defaults to <maps-dir>/hillshade.tif.",
    )
    parser.add_argument(
        "--terrain-risk",
        type=Path,
        help="Terrain risk raster path. Defaults to <maps-dir>/terrain_risk.tif.",
    )
    parser.add_argument("--qgis-export", type=Path, help="Optional QGIS export image.")
    parser.add_argument(
        "--paraview-render",
        type=Path,
        help="Optional ParaView render image. Defaults to <renders-dir>/terrain.png when present.",
    )
    parser.add_argument(
        "--paraview-state",
        type=Path,
        help="Optional ParaView state file. Defaults to <renders-dir>/terrain.pvsm when present.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        default=Path("outputs/reports/terrain_analysis.md"),
        help="Markdown report output path.",
    )
    parser.add_argument(
        "--output-pdf",
        type=Path,
        help="Optional PDF report output path. Requires reportlab.",
    )
    return parser.parse_args()


def build_report_inputs(args: argparse.Namespace) -> TerrainReportInputs:
    maps_dir = args.maps_dir
    renders_dir = args.renders_dir
    paraview_render = args.paraview_render
    paraview_state = args.paraview_state

    if paraview_render is None:
        paraview_render = existing_or_default(renders_dir / "terrain.png")
    if paraview_state is None:
        paraview_state = existing_or_default(renders_dir / "terrain.pvsm")

    return TerrainReportInputs(
        dem_path=args.dem,
        slope_path=args.slope or maps_dir / "slope_degrees.tif",
        hillshade_path=args.hillshade or maps_dir / "hillshade.tif",
        terrain_risk_path=args.terrain_risk or maps_dir / "terrain_risk.tif",
        qgis_export_path=args.qgis_export,
        paraview_render_path=paraview_render,
        paraview_state_path=paraview_state,
    )


def main() -> None:
    args = parse_args()
    inputs = build_report_inputs(args)

    markdown_path = write_markdown_report(inputs, args.output_md)
    print(f"Markdown report: {markdown_path}")

    if args.output_pdf is not None:
        try:
            pdf_path = write_pdf_report(inputs, args.output_pdf)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"PDF report:      {pdf_path}")


if __name__ == "__main__":
    main()
