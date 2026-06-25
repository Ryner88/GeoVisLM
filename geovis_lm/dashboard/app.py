from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from shutil import copyfileobj
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from geovis_lm.gis.terrain import (
    calculate_hillshade,
    calculate_slope_degrees,
    classify_slope_risk,
    load_dem,
    save_raster,
)
from geovis_lm.reports.terrain_report import TerrainReportInputs, write_markdown_report


OUTPUT_ROOT = Path("outputs")
RUNS_ROOT = OUTPUT_ROOT / "runs"

app = FastAPI(title="GeoVisLM Dashboard", version="0.1.0")

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
RUNS_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(OUTPUT_ROOT)), name="outputs")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_dir(run_id: str) -> Path:
    safe_run_id = Path(run_id).name
    if safe_run_id != run_id:
        raise HTTPException(status_code=400, detail="Invalid run_id")
    return RUNS_ROOT / safe_run_id


def run_metadata_path(run_id: str) -> Path:
    return run_dir(run_id) / "metadata.json"


def write_json(path: Path, data: dict) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def read_json(path: Path) -> dict:
    import json

    if not path.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    return json.loads(path.read_text(encoding="utf-8"))


def update_run(run_id: str, **updates) -> dict:
    path = run_metadata_path(run_id)
    metadata = read_json(path)
    metadata.update(updates)
    metadata["updated_at"] = utc_now()
    write_json(path, metadata)
    return metadata


def create_run_folders(base_dir: Path) -> None:
    for child in ("inputs", "maps", "renders", "reports"):
        (base_dir / child).mkdir(parents=True, exist_ok=True)


def relative_output_url(path: Path) -> str:
    return "/" + path.as_posix()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>GeoVisLM Dashboard</title>
    <style>
      body { font-family: system-ui, sans-serif; margin: 2rem; max-width: 900px; }
      code, pre { background: #f4f4f4; padding: 0.2rem 0.35rem; }
      pre { padding: 1rem; overflow-x: auto; }
    </style>
  </head>
  <body>
    <h1>GeoVisLM Dashboard</h1>
    <p>Use the JSON API to create terrain analysis runs, upload DEM bytes, generate maps, and write reports.</p>
    <pre>curl -X POST http://127.0.0.1:8000/api/runs</pre>
    <pre>curl -X POST --data-binary @data/sample/sample_dem.tif \
"http://127.0.0.1:8000/api/runs/&lt;run_id&gt;/upload-dem?filename=sample_dem.tif"</pre>
  </body>
</html>
"""


@app.post("/api/runs")
def create_run() -> dict:
    run_id = uuid4().hex
    base_dir = run_dir(run_id)
    create_run_folders(base_dir)

    metadata = {
        "run_id": run_id,
        "status": "created",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "paths": {
            "run_dir": str(base_dir),
            "inputs": str(base_dir / "inputs"),
            "maps": str(base_dir / "maps"),
            "renders": str(base_dir / "renders"),
            "reports": str(base_dir / "reports"),
        },
        "outputs": {},
    }
    write_json(run_metadata_path(run_id), metadata)
    return metadata


@app.post("/api/runs/{run_id}/upload-dem")
async def upload_dem(
    run_id: str,
    request: Request,
    filename: str = Query(default="dem.tif", description="Filename to use for uploaded DEM bytes."),
) -> dict:
    base_dir = run_dir(run_id)
    if not base_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")

    safe_filename = Path(filename).name
    if not safe_filename:
        raise HTTPException(status_code=400, detail="filename is required")

    dem_path = base_dir / "inputs" / safe_filename
    with dem_path.open("wb") as output:
        async for chunk in request.stream():
            output.write(chunk)

    return update_run(
        run_id,
        status="uploaded",
        dem_path=str(dem_path),
    )


@app.post("/api/runs/{run_id}/analyze")
def analyze_run(run_id: str) -> dict:
    metadata = read_json(run_metadata_path(run_id))
    dem_path = Path(metadata.get("dem_path", ""))
    if not dem_path.exists():
        raise HTTPException(status_code=400, detail="Upload a DEM before analysis")

    maps_dir = run_dir(run_id) / "maps"
    update_run(run_id, status="running")

    try:
        dem, profile, transform, crs = load_dem(dem_path)
        slope = calculate_slope_degrees(dem, transform)
        hillshade = calculate_hillshade(dem, transform)
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
    except Exception as exc:
        update_run(run_id, status="failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Terrain analysis failed: {exc}") from exc

    outputs = {
        "slope": str(slope_path),
        "hillshade": str(hillshade_path),
        "terrain_risk": str(risk_path),
    }
    return update_run(run_id, status="completed", outputs=outputs, crs=str(crs))


@app.post("/api/runs/{run_id}/report")
def generate_report(run_id: str) -> dict:
    metadata = read_json(run_metadata_path(run_id))
    dem_path = Path(metadata.get("dem_path", ""))
    outputs = metadata.get("outputs", {})

    required = {
        "slope": outputs.get("slope"),
        "hillshade": outputs.get("hillshade"),
        "terrain_risk": outputs.get("terrain_risk"),
    }
    missing = [name for name, value in required.items() if not value or not Path(value).exists()]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Run analysis before report generation. Missing: {', '.join(missing)}",
        )

    report_path = run_dir(run_id) / "reports" / "terrain_analysis.md"
    write_markdown_report(
        TerrainReportInputs(
            dem_path=dem_path,
            slope_path=Path(required["slope"]),
            hillshade_path=Path(required["hillshade"]),
            terrain_risk_path=Path(required["terrain_risk"]),
            paraview_render_path=None,
            paraview_state_path=None,
        ),
        report_path,
    )

    outputs["report_md"] = str(report_path)
    metadata = update_run(run_id, status="reported", outputs=outputs)
    metadata["report_url"] = relative_output_url(report_path)
    return metadata


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    return read_json(run_metadata_path(run_id))


@app.get("/api/runs/{run_id}/outputs")
def list_outputs(run_id: str) -> dict:
    base_dir = run_dir(run_id)
    if not base_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")

    files = []
    for path in sorted(base_dir.rglob("*")):
        if path.is_file():
            files.append(
                {
                    "path": str(path),
                    "url": relative_output_url(path),
                    "bytes": path.stat().st_size,
                }
            )
    return {"run_id": run_id, "files": files}


def copy_sample_dem_to_run(run_id: str, sample_dem: Path = Path("data/sample/sample_dem.tif")) -> dict:
    base_dir = run_dir(run_id)
    if not base_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    if not sample_dem.exists():
        raise HTTPException(status_code=404, detail=f"Sample DEM not found: {sample_dem}")

    dem_path = base_dir / "inputs" / sample_dem.name
    with sample_dem.open("rb") as source, dem_path.open("wb") as target:
        copyfileobj(source, target)

    return update_run(run_id, status="uploaded", dem_path=str(dem_path))


@app.post("/api/runs/{run_id}/use-sample-dem")
def use_sample_dem(run_id: str) -> dict:
    return copy_sample_dem_to_run(run_id)
