from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import rasterio

from geovis_lm.gis.terrain import (
    calculate_hillshade,
    calculate_slope_degrees,
    classify_slope_risk,
    load_dem,
    read_masked_band,
    save_raster,
)
from geovis_lm.gis.vector import (
    SUPPORTED_VECTOR_SUFFIXES,
    clip_vector_to_raster_bounds,
    load_vector,
    validate_vector,
    write_vector_geojson,
)
from geovis_lm.gis.risk import execute_flood_risk_workflow, execute_wildfire_risk_workflow


SUPPORTED_DEM_EXTENSIONS = {".tif", ".tiff"}


class AnalysisExecutionError(Exception):
    def __init__(
        self,
        error_code: str,
        error_message: str,
        *,
        retryable: bool = True,
        stage: str = "analysis",
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(error_message)
        self.error_code = error_code
        self.error_message = error_message
        self.retryable = retryable
        self.stage = stage
        self.detail = detail or {}

    def as_detail(self) -> dict[str, Any]:
        return {
            "adapter": "dem_terrain",
            "stage": self.stage,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "retryable": self.retryable,
            **self.detail,
        }


@dataclass(frozen=True)
class AnalysisExecutionResult:
    adapter: str
    outputs: dict[str, str]
    metadata: dict[str, Any] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)


def raster_stats(array) -> dict[str, float | None]:
    values = np.ma.masked_invalid(array)
    if values.count() == 0:
        return {"min": None, "max": None, "mean": None}
    return {
        "min": float(values.min()),
        "max": float(values.max()),
        "mean": float(values.mean()),
    }


def crs_label(crs) -> str | None:
    if crs is None:
        return None
    try:
        epsg = crs.to_epsg()
    except AttributeError:
        epsg = None
    return f"EPSG:{epsg}" if epsg else str(crs)


def bool_parameter(parameters: dict[str, Any], name: str, default: bool = True) -> bool:
    raw = parameters.get(name, default)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return bool(raw)


def render_overlay_preview(dem_path: Path, clipped_layers: list[tuple[str, Any]], output_path: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(dem_path) as src:
        dem = read_masked_band(src)
        bounds = src.bounds

    fig, ax = plt.subplots(figsize=(8, 6), dpi=120)
    ax.imshow(
        dem,
        cmap="gray",
        extent=(bounds.left, bounds.right, bounds.bottom, bounds.top),
        origin="upper",
    )
    colors = ["#e11d48", "#2563eb", "#16a34a", "#f59e0b"]
    for index, (label, layer) in enumerate(clipped_layers):
        if layer.empty:
            continue
        layer.boundary.plot(ax=ax, color=colors[index % len(colors)], linewidth=1.5, label=label)
    if any(not layer.empty for _, layer in clipped_layers):
        ax.legend(loc="upper right")
    ax.set_axis_off()
    fig.tight_layout(pad=0)
    fig.savefig(output_path, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return output_path


def process_vector_overlays(
    vector_paths: list[Path],
    *,
    dem_path: Path,
    vectors_dir: Path,
    renders_dir: Path,
    parameters: dict[str, Any],
    logs: list[str],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    outputs: dict[str, str] = {}
    layers: list[dict[str, Any]] = []
    clipped_for_render = []
    vectors_dir.mkdir(parents=True, exist_ok=True)

    for index, vector_path in enumerate(vector_paths, start=1):
        vector_path = Path(vector_path)
        if vector_path.suffix.lower() not in SUPPORTED_VECTOR_SUFFIXES:
            raise AnalysisExecutionError(
                "unsupported_vector_input",
                f"Unsupported vector input extension: {vector_path.suffix.lower()}",
                retryable=False,
                stage="vector_validation",
                detail={
                    "input_path": str(vector_path),
                    "supported_extensions": sorted(SUPPORTED_VECTOR_SUFFIXES),
                },
            )

        logs.append(f"stage=vector_load input={vector_path}")
        try:
            source = validate_vector(load_vector(vector_path))
            clipped = clip_vector_to_raster_bounds(source, dem_path)
            output_path = write_vector_geojson(
                clipped,
                vectors_dir / f"{vector_path.stem}_clipped.geojson",
            )
        except Exception as exc:
            raise AnalysisExecutionError(
                "vector_overlay_failed",
                str(exc),
                retryable=True,
                stage="vector_overlay",
                detail={
                    "input_path": str(vector_path),
                    "error_type": type(exc).__name__,
                    "logs": logs,
                },
            ) from exc

        key = f"vector_overlay_{index}"
        outputs[key] = str(output_path)
        layer_metadata = {
            "source_path": str(vector_path),
            "output_path": str(output_path),
            "source_crs": crs_label(source.crs),
            "target_crs": crs_label(clipped.crs),
            "feature_count": int(len(source)),
            "clipped_feature_count": int(len(clipped)),
            "reprojected": crs_label(source.crs) != crs_label(clipped.crs),
        }
        layers.append(layer_metadata)
        clipped_for_render.append((vector_path.stem, clipped))

    if vector_paths and bool_parameter(parameters, "render_overlay", True):
        logs.append("stage=render_overlay")
        render_path = render_overlay_preview(dem_path, clipped_for_render, renders_dir / "terrain_overlay.png")
        outputs["terrain_overlay_png"] = str(render_path)

    return outputs, layers


def execute_dem_analysis(
    dem_path: Path,
    *,
    maps_dir: Path,
    reports_dir: Path,
    vectors_dir: Path | None = None,
    renders_dir: Path | None = None,
    vector_paths: list[Path] | None = None,
    parameters: dict[str, Any] | None = None,
) -> AnalysisExecutionResult:
    parameters = parameters or {}
    vector_paths = vector_paths or []
    dem_path = Path(dem_path)
    maps_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    vectors_dir = vectors_dir or maps_dir
    renders_dir = renders_dir or reports_dir
    logs = [f"adapter=dem_terrain input={dem_path}"]

    if not dem_path.exists():
        raise AnalysisExecutionError(
            "missing_dem",
            f"DEM input does not exist: {dem_path}",
            retryable=True,
            stage="input_validation",
            detail={"input_path": str(dem_path)},
        )
    if dem_path.suffix.lower() not in SUPPORTED_DEM_EXTENSIONS:
        raise AnalysisExecutionError(
            "unsupported_input",
            f"Unsupported DEM input extension: {dem_path.suffix.lower()}",
            retryable=False,
            stage="input_validation",
            detail={"input_path": str(dem_path), "supported_extensions": sorted(SUPPORTED_DEM_EXTENSIONS)},
        )

    try:
        logs.append("stage=load_dem")
        dem, profile, transform, crs = load_dem(dem_path)

        logs.append("stage=calculate_slope")
        slope = calculate_slope_degrees(dem, transform)

        logs.append("stage=calculate_hillshade")
        hillshade = calculate_hillshade(
            dem,
            transform,
            azimuth=float(parameters.get("hillshade_azimuth", 315)),
            altitude=float(parameters.get("hillshade_altitude", 45)),
        )

        logs.append("stage=classify_slope_risk")
        risk = classify_slope_risk(slope)

        slope_path = save_raster(
            maps_dir / "slope_degrees.tif", slope, profile, dtype="float32", nodata=-9999
        )
        hillshade_path = save_raster(
            maps_dir / "hillshade.tif", hillshade, profile, dtype="float32", nodata=-9999
        )
        risk_path = save_raster(
            maps_dir / "terrain_risk.tif", risk, profile, dtype="uint8", nodata=0
        )
        vector_outputs, vector_layers = process_vector_overlays(
            vector_paths,
            dem_path=dem_path,
            vectors_dir=vectors_dir,
            renders_dir=renders_dir,
            parameters=parameters,
            logs=logs,
        )

        summary = {
            "adapter": "dem_terrain",
            "input_dem": str(dem_path),
            "crs": crs_label(crs),
            "width": int(profile.get("width", 0)),
            "height": int(profile.get("height", 0)),
            "dtype": profile.get("dtype"),
            "parameters": parameters,
            "slope_degrees": raster_stats(slope),
            "hillshade": raster_stats(hillshade),
            "terrain_risk_classes": sorted(int(value) for value in np.unique(risk.compressed())),
            "vector_layers": vector_layers,
            "outputs": {
                "slope": str(slope_path),
                "hillshade": str(hillshade_path),
                "terrain_risk": str(risk_path),
                **vector_outputs,
            },
        }
        summary_path = reports_dir / "terrain_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    except AnalysisExecutionError:
        raise
    except Exception as exc:
        raise AnalysisExecutionError(
            "dem_analysis_failed",
            str(exc),
            retryable=True,
            stage=logs[-1].removeprefix("stage=") if logs else "analysis",
            detail={
                "input_path": str(dem_path),
                "error_type": type(exc).__name__,
                "logs": logs,
            },
        ) from exc

    logs.append("stage=complete")
    return AnalysisExecutionResult(
        adapter="dem_terrain",
        outputs={
            "slope": str(slope_path),
            "hillshade": str(hillshade_path),
            "terrain_risk": str(risk_path),
            "terrain_summary_json": str(summary_path),
            **vector_outputs,
        },
        metadata={
            "crs": crs_label(crs),
            "summary_path": str(summary_path),
            "vector_layers": vector_layers,
            "render_enabled": bool_parameter(parameters, "render_overlay", True),
            "logs": logs,
        },
        logs=logs,
    )


def _ensure_vector_inputs(vector_paths: list[Path], workflow: str) -> list[Path]:
    if not vector_paths:
        raise AnalysisExecutionError(
            f"missing_{workflow}_vector",
            f"{workflow.replace('_', ' ').title()} workflow requires at least one vector input",
            retryable=True,
            stage="input_validation",
        )
    for vector_path in vector_paths:
        if vector_path.suffix.lower() not in SUPPORTED_VECTOR_SUFFIXES:
            raise AnalysisExecutionError(
                "unsupported_vector_input",
                f"Unsupported vector input extension: {vector_path.suffix.lower()}",
                retryable=False,
                stage="vector_validation",
                detail={
                    "input_path": str(vector_path),
                    "supported_extensions": sorted(SUPPORTED_VECTOR_SUFFIXES),
                },
            )
    return [Path(path) for path in vector_paths]


def execute_flood_analysis(
    dem_path: Path,
    *,
    maps_dir: Path,
    reports_dir: Path,
    vector_paths: list[Path] | None = None,
    parameters: dict[str, Any] | None = None,
) -> AnalysisExecutionResult:
    parameters = parameters or {}
    vector_paths = _ensure_vector_inputs(vector_paths or [], "flood_risk")
    maps_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    logs = [f"adapter=flood_risk input={dem_path}", f"stage=river_input input={vector_paths[0]}"]
    try:
        summary = execute_flood_risk_workflow(
            Path(dem_path),
            vector_paths[0],
            output_dir=maps_dir,
            parameters=parameters,
        )
        summary_path = maps_dir / "flood_risk_summary.json"
        reports_summary_path = reports_dir / "flood_risk_summary.json"
        reports_summary_path.write_text(summary_path.read_text(encoding="utf-8"), encoding="utf-8")
    except AnalysisExecutionError:
        raise
    except Exception as exc:
        raise AnalysisExecutionError(
            "flood_risk_failed",
            str(exc),
            retryable=True,
            stage="flood_risk",
            detail={"input_path": str(dem_path), "error_type": type(exc).__name__, "logs": logs},
        ) from exc

    logs.append("stage=complete")
    outputs = {
        "flood_risk": summary["outputs"]["flood_risk"],
        "river_buffers": summary["outputs"]["river_buffers"],
        "flood_risk_summary_json": str(reports_summary_path),
    }
    return AnalysisExecutionResult(
        adapter="flood_risk",
        outputs=outputs,
        metadata={
            "crs": summary.get("crs"),
            "risk_classes": summary.get("risk_classes", {}),
            "summary_path": str(reports_summary_path),
            "river_input": str(vector_paths[0]),
            "logs": logs,
        },
        logs=logs,
    )


def execute_wildfire_analysis(
    dem_path: Path,
    *,
    maps_dir: Path,
    reports_dir: Path,
    vector_paths: list[Path] | None = None,
    parameters: dict[str, Any] | None = None,
) -> AnalysisExecutionResult:
    parameters = parameters or {}
    vector_paths = _ensure_vector_inputs(vector_paths or [], "wildfire_risk")
    maps_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    fuel_path = vector_paths[0]
    proximity_paths = vector_paths[1:]
    logs = [f"adapter=wildfire_risk input={dem_path}", f"stage=fuel_input input={fuel_path}"]
    try:
        summary = execute_wildfire_risk_workflow(
            Path(dem_path),
            fuel_path,
            output_dir=maps_dir,
            proximity_paths=proximity_paths,
            parameters=parameters,
        )
        summary_path = maps_dir / "wildfire_risk_summary.json"
        reports_summary_path = reports_dir / "wildfire_risk_summary.json"
        reports_summary_path.write_text(summary_path.read_text(encoding="utf-8"), encoding="utf-8")
    except AnalysisExecutionError:
        raise
    except Exception as exc:
        raise AnalysisExecutionError(
            "wildfire_risk_failed",
            str(exc),
            retryable=True,
            stage="wildfire_risk",
            detail={"input_path": str(dem_path), "error_type": type(exc).__name__, "logs": logs},
        ) from exc

    logs.append("stage=complete")
    outputs = {
        "wildfire_risk": summary["outputs"]["wildfire_risk"],
        "wildfire_risk_summary_json": str(reports_summary_path),
    }
    return AnalysisExecutionResult(
        adapter="wildfire_risk",
        outputs=outputs,
        metadata={
            "crs": summary.get("crs"),
            "risk_classes": summary.get("risk_classes", {}),
            "summary_path": str(reports_summary_path),
            "fuel": summary.get("fuel", {}),
            "proximity_layers": summary.get("proximity_layers", []),
            "logs": logs,
        },
        logs=logs,
    )
