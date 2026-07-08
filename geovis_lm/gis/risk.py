from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.warp import Resampling, reproject

from geovis_lm.gis.terrain import calculate_slope_degrees, load_dem, save_raster
from geovis_lm.gis.vector import (
    clip_vector_to_raster_bounds,
    load_vector,
    reproject_vector,
    validate_vector,
    write_vector_geojson,
)


RISK_CLASS_DESCRIPTIONS = {
    0: "nodata",
    1: "low",
    2: "moderate",
    3: "high",
}

FUEL_CLASS_ALIASES = {
    "bare": 1,
    "water": 1,
    "urban": 1,
    "low": 1,
    "grass": 2,
    "grassland": 2,
    "crop": 2,
    "crops": 2,
    "shrub": 2,
    "moderate": 2,
    "brush": 3,
    "timber": 3,
    "forest": 3,
    "woodland": 3,
    "dense": 3,
    "high": 3,
}


def _risk_class_metadata() -> dict[str, str]:
    return {str(key): value for key, value in RISK_CLASS_DESCRIPTIONS.items()}


def _masked_uint8(data: np.ndarray, mask) -> np.ma.MaskedArray:
    return np.ma.array(data.astype(np.uint8), mask=mask)


def low_elevation_flood_risk(dem) -> np.ma.MaskedArray:
    values = np.ma.masked_invalid(dem)
    if values.count() == 0:
        return _masked_uint8(np.zeros(values.shape, dtype=np.uint8), values.mask)
    low, medium = np.percentile(values.compressed(), [33, 66])
    risk = np.ones(values.shape, dtype=np.uint8)
    risk[values <= medium] = 2
    risk[values <= low] = 3
    return _masked_uint8(risk, values.mask)


def flat_terrain_flood_risk(slope) -> np.ma.MaskedArray:
    values = np.ma.masked_invalid(slope)
    risk = np.ones(values.shape, dtype=np.uint8)
    risk[(values >= 5) & (values < 15)] = 2
    risk[values < 5] = 3
    return _masked_uint8(risk, values.mask)


def slope_wildfire_risk(slope) -> np.ma.MaskedArray:
    values = np.ma.masked_invalid(slope)
    risk = np.ones(values.shape, dtype=np.uint8)
    risk[(values >= 10) & (values < 25)] = 2
    risk[values >= 25] = 3
    return _masked_uint8(risk, values.mask)


def combine_risk_layers(layers: list[tuple[np.ma.MaskedArray, float]]) -> np.ma.MaskedArray:
    if not layers:
        raise ValueError("At least one risk layer is required")
    total_weight = sum(weight for _layer, weight in layers)
    if total_weight <= 0:
        raise ValueError("Risk layer weights must be positive")

    mask = np.zeros(layers[0][0].shape, dtype=bool)
    weighted = np.zeros(layers[0][0].shape, dtype=np.float32)
    for layer, weight in layers:
        mask |= np.ma.getmaskarray(layer)
        weighted += layer.filled(0).astype(np.float32) * float(weight)

    combined = np.rint(weighted / total_weight).astype(np.uint8)
    combined = np.clip(combined, 1, 3)
    combined[mask] = 0
    return _masked_uint8(combined, mask)


def _rasterize_geometries(
    shapes: list[tuple[Any, int]],
    *,
    profile: dict[str, Any],
    fill: int = 0,
) -> np.ndarray:
    return rasterize(
        shapes,
        out_shape=(int(profile["height"]), int(profile["width"])),
        transform=profile["transform"],
        fill=fill,
        dtype="uint8",
        all_touched=True,
    )


def river_buffer_risk(
    river_layer: gpd.GeoDataFrame,
    *,
    dem_path: Path,
    profile: dict[str, Any],
    near_buffer: float = 150.0,
    medium_buffer: float = 450.0,
    far_buffer: float = 900.0,
) -> tuple[np.ma.MaskedArray, gpd.GeoDataFrame]:
    if not (0 < near_buffer <= medium_buffer <= far_buffer):
        raise ValueError("River buffers must satisfy 0 < near <= medium <= far")

    clipped = clip_vector_to_raster_bounds(validate_vector(river_layer), dem_path)
    if clipped.empty:
        raise ValueError("River layer does not overlap DEM bounds")

    buffered_layers = [
        ("far", far_buffer, 1),
        ("medium", medium_buffer, 2),
        ("near", near_buffer, 3),
    ]
    buffer_records = []
    shapes = []
    for zone, distance, risk in buffered_layers:
        buffered = clipped.copy()
        buffered["buffer_zone"] = zone
        buffered["buffer_distance"] = float(distance)
        buffered["risk_class"] = int(risk)
        buffered = buffered.set_geometry(buffered.geometry.buffer(distance))
        buffer_records.append(buffered)
        shapes.extend((geom, risk) for geom in buffered.geometry if not geom.is_empty)

    buffers = gpd.GeoDataFrame(pd.concat(buffer_records, ignore_index=True), crs=clipped.crs)
    raster = _rasterize_geometries(shapes, profile=profile, fill=0)
    risk = np.where(raster == 0, 1, raster).astype(np.uint8)
    return _masked_uint8(risk, np.zeros(risk.shape, dtype=bool)), buffers


def normalize_fuel_value(value: Any) -> int:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return 2
    if isinstance(value, (int, float, np.integer, np.floating)):
        return int(np.clip(round(float(value)), 1, 3))
    normalized = str(value).strip().lower().replace("_", " ").replace("-", " ")
    if not normalized:
        return 2
    if normalized in FUEL_CLASS_ALIASES:
        return FUEL_CLASS_ALIASES[normalized]
    for token in normalized.split():
        if token in FUEL_CLASS_ALIASES:
            return FUEL_CLASS_ALIASES[token]
    return 2


def vector_fuel_risk(
    fuel_layer: gpd.GeoDataFrame,
    *,
    dem_path: Path,
    profile: dict[str, Any],
    fuel_field: str | None = None,
) -> tuple[np.ma.MaskedArray, dict[str, Any]]:
    clipped = clip_vector_to_raster_bounds(validate_vector(fuel_layer), dem_path)
    if clipped.empty:
        raise ValueError("Fuel layer does not overlap DEM bounds")

    field = fuel_field if fuel_field in clipped.columns else None
    if field is None:
        for candidate in ("fuel_risk", "risk", "fuel_class", "fuel", "vegetation", "veg_class", "landcover"):
            if candidate in clipped.columns:
                field = candidate
                break

    if field:
        risks = [normalize_fuel_value(value) for value in clipped[field]]
    else:
        risks = [2 for _ in range(len(clipped))]

    shapes = [(geom, risk) for geom, risk in zip(clipped.geometry, risks, strict=False) if not geom.is_empty]
    raster = _rasterize_geometries(shapes, profile=profile, fill=1)
    metadata = {
        "source_crs": str(fuel_layer.crs) if fuel_layer.crs else None,
        "target_crs": str(clipped.crs) if clipped.crs else None,
        "feature_count": int(len(fuel_layer)),
        "clipped_feature_count": int(len(clipped)),
        "fuel_field": field,
        "normalized_classes": sorted({int(value) for value in risks}),
    }
    return _masked_uint8(raster, np.zeros(raster.shape, dtype=bool)), metadata


def raster_fuel_risk(fuel_path: Path, *, profile: dict[str, Any]) -> tuple[np.ma.MaskedArray, dict[str, Any]]:
    fuel_path = Path(fuel_path)
    with rasterio.open(fuel_path) as src:
        destination = np.zeros((int(profile["height"]), int(profile["width"])), dtype=np.float32)
        reproject(
            source=rasterio.band(src, 1),
            destination=destination,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=profile["transform"],
            dst_crs=profile["crs"],
            resampling=Resampling.nearest,
        )
        nodata = src.nodata
        mask = destination == nodata if nodata is not None else np.zeros(destination.shape, dtype=bool)
    vectorized = np.vectorize(normalize_fuel_value)
    risk = vectorized(destination).astype(np.uint8)
    risk[mask] = 0
    return _masked_uint8(risk, mask), {"source_path": str(fuel_path), "source_type": "raster"}


def proximity_risk(
    layer: gpd.GeoDataFrame,
    *,
    dem_path: Path,
    profile: dict[str, Any],
    near_buffer: float = 200.0,
    far_buffer: float = 800.0,
) -> np.ma.MaskedArray:
    clipped = clip_vector_to_raster_bounds(validate_vector(layer), dem_path)
    if clipped.empty:
        risk = np.ones((int(profile["height"]), int(profile["width"])), dtype=np.uint8)
        return _masked_uint8(risk, np.zeros(risk.shape, dtype=bool))
    shapes = []
    for distance, value in ((far_buffer, 2), (near_buffer, 3)):
        buffered = clipped.geometry.buffer(distance)
        shapes.extend((geom, value) for geom in buffered if not geom.is_empty)
    raster = _rasterize_geometries(shapes, profile=profile, fill=1)
    return _masked_uint8(raster, np.zeros(raster.shape, dtype=bool))


def execute_flood_risk_workflow(
    dem_path: Path,
    river_path: Path,
    *,
    output_dir: Path,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parameters = parameters or {}
    output_dir.mkdir(parents=True, exist_ok=True)
    dem, profile, transform, crs = load_dem(dem_path)
    slope = calculate_slope_degrees(dem, transform)
    river_layer = load_vector(river_path)

    proximity, buffers = river_buffer_risk(
        river_layer,
        dem_path=Path(dem_path),
        profile=profile,
        near_buffer=float(parameters.get("river_near_buffer", 150)),
        medium_buffer=float(parameters.get("river_medium_buffer", 450)),
        far_buffer=float(parameters.get("river_far_buffer", 900)),
    )
    elevation_risk = low_elevation_flood_risk(dem)
    slope_risk = flat_terrain_flood_risk(slope)
    risk = combine_risk_layers([(proximity, 0.45), (elevation_risk, 0.30), (slope_risk, 0.25)])

    flood_path = save_raster(output_dir / "flood_risk.tif", risk, profile, dtype="uint8", nodata=0)
    buffer_path = write_vector_geojson(buffers, output_dir / "river_buffers.geojson")
    summary = {
        "adapter": "flood_risk",
        "input_dem": str(dem_path),
        "input_rivers": str(river_path),
        "crs": str(crs) if crs else None,
        "risk_classes": _risk_class_metadata(),
        "model": {
            "proximity_weight": 0.45,
            "low_elevation_weight": 0.30,
            "flat_slope_weight": 0.25,
            "limitations": "Screening workflow only; it does not model rainfall, hydrology, drainage, or return periods.",
        },
        "parameters": parameters,
        "outputs": {"flood_risk": str(flood_path), "river_buffers": str(buffer_path)},
    }
    summary_path = output_dir / "flood_risk_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    summary["outputs"]["flood_risk_summary_json"] = str(summary_path)
    return summary


def execute_wildfire_risk_workflow(
    dem_path: Path,
    fuel_path: Path,
    *,
    output_dir: Path,
    proximity_paths: list[Path] | None = None,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    parameters = parameters or {}
    proximity_paths = proximity_paths or []
    output_dir.mkdir(parents=True, exist_ok=True)
    dem, profile, transform, crs = load_dem(dem_path)
    slope = calculate_slope_degrees(dem, transform)
    slope_risk = slope_wildfire_risk(slope)

    fuel_path = Path(fuel_path)
    if fuel_path.suffix.lower() in {".tif", ".tiff"}:
        fuel_risk, fuel_metadata = raster_fuel_risk(fuel_path, profile=profile)
    else:
        fuel_layer = load_vector(fuel_path)
        fuel_risk, fuel_metadata = vector_fuel_risk(
            fuel_layer,
            dem_path=Path(dem_path),
            profile=profile,
            fuel_field=parameters.get("fuel_field"),
        )

    layers = [(fuel_risk, 0.50), (slope_risk, 0.35)]
    proximity_metadata = []
    if proximity_paths:
        combined = np.ones(fuel_risk.shape, dtype=np.uint8)
        for proximity_path in proximity_paths:
            layer = load_vector(proximity_path)
            risk = proximity_risk(
                layer,
                dem_path=Path(dem_path),
                profile=profile,
                near_buffer=float(parameters.get("proximity_near_buffer", 200)),
                far_buffer=float(parameters.get("proximity_far_buffer", 800)),
            )
            combined = np.maximum(combined, risk.filled(1))
            proximity_metadata.append({"source_path": str(proximity_path), "feature_count": int(len(layer))})
        layers.append((_masked_uint8(combined, np.zeros(combined.shape, dtype=bool)), 0.15))

    risk = combine_risk_layers(layers)
    wildfire_path = save_raster(output_dir / "wildfire_risk.tif", risk, profile, dtype="uint8", nodata=0)
    summary = {
        "adapter": "wildfire_risk",
        "input_dem": str(dem_path),
        "input_fuel": str(fuel_path),
        "crs": str(crs) if crs else None,
        "risk_classes": _risk_class_metadata(),
        "fuel": fuel_metadata,
        "proximity_layers": proximity_metadata,
        "model": {
            "fuel_weight": 0.50,
            "slope_weight": 0.35,
            "proximity_weight": 0.15 if proximity_paths else 0.0,
            "limitations": "Screening workflow only; it does not model live fuel moisture, ignition probability, suppression capacity, or forecast weather.",
        },
        "parameters": parameters,
        "outputs": {"wildfire_risk": str(wildfire_path)},
    }
    summary_path = output_dir / "wildfire_risk_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    summary["outputs"]["wildfire_risk_summary_json"] = str(summary_path)
    return summary
