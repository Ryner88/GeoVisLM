from pathlib import Path
import argparse
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and clip a vector overlay to DEM/raster bounds."
    )
    parser.add_argument("--vector", type=Path, required=True, help="Input GeoJSON, JSON, or Shapefile path.")
    parser.add_argument("--raster", type=Path, required=True, help="Raster path whose bounds and CRS should be used.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/vector_overlay_clipped.geojson"),
        help="Output GeoJSON path for the processed vector overlay.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        from geovis_lm.gis.vector import (
            clip_vector_to_raster_bounds,
            detect_crs,
            load_vector,
            validate_vector,
            write_vector_geojson,
        )
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Vector overlay processing requires GeoPandas, Rasterio, and Shapely. "
            "Run this command inside the project virtualenv, for example: "
            ".venv/bin/python scripts/process_vector_overlay.py --help"
        ) from exc

    gdf = validate_vector(load_vector(args.vector))
    clipped = clip_vector_to_raster_bounds(gdf, args.raster)
    output_path = write_vector_geojson(clipped, args.output)

    print("Vector overlay processed.")
    print(f"Input CRS:       {detect_crs(gdf)}")
    print(f"Input features:  {len(gdf)}")
    print(f"Output features: {len(clipped)}")
    print(f"Output:          {output_path}")


if __name__ == "__main__":
    main()
