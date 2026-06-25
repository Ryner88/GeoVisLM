from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import rasterio
from shapely.geometry import box


SUPPORTED_VECTOR_SUFFIXES = {".geojson", ".json", ".shp"}


def load_vector(path: str | Path) -> gpd.GeoDataFrame:
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED_VECTOR_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_VECTOR_SUFFIXES))
        raise ValueError(f"Unsupported vector format '{path.suffix}'. Supported: {supported}")
    if not path.exists():
        raise FileNotFoundError(f"Vector layer does not exist: {path}")
    return gpd.read_file(path)


def validate_vector(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.empty:
        raise ValueError("Vector layer has no features")
    if gdf.geometry.name not in gdf:
        raise ValueError("Vector layer has no geometry column")
    if gdf.geometry.isna().any():
        raise ValueError("Vector layer contains empty geometries")
    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        invalid_count = int(invalid.sum())
        raise ValueError(f"Vector layer contains {invalid_count} invalid geometries")
    if gdf.crs is None:
        raise ValueError("Vector layer is missing CRS metadata")
    return gdf


def detect_crs(gdf: gpd.GeoDataFrame):
    return gdf.crs


def reproject_vector(gdf: gpd.GeoDataFrame, target_crs) -> gpd.GeoDataFrame:
    if target_crs is None:
        raise ValueError("Target CRS is required for reprojection")
    if gdf.crs is None:
        raise ValueError("Vector layer is missing CRS metadata")
    if gdf.crs == target_crs:
        return gdf.copy()
    return gdf.to_crs(target_crs)


def raster_bounds_gdf(raster_path: str | Path) -> gpd.GeoDataFrame:
    raster_path = Path(raster_path)
    if not raster_path.exists():
        raise FileNotFoundError(f"Raster does not exist: {raster_path}")
    with rasterio.open(raster_path) as src:
        bounds_geom = box(*src.bounds)
        return gpd.GeoDataFrame({"id": ["raster_bounds"]}, geometry=[bounds_geom], crs=src.crs)


def clip_vector_to_raster_bounds(
    gdf: gpd.GeoDataFrame, raster_path: str | Path
) -> gpd.GeoDataFrame:
    bounds = raster_bounds_gdf(raster_path)
    reprojected = reproject_vector(gdf, bounds.crs)
    clipped = gpd.clip(reprojected, bounds)
    return clipped.reset_index(drop=True)


def write_vector_geojson(gdf: gpd.GeoDataFrame, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(output_path, driver="GeoJSON")
    return output_path
