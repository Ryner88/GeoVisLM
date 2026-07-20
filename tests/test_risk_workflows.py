from __future__ import annotations

import json
from pathlib import Path
import base64
import importlib
import sys

import geopandas as gpd
import pytest
import rasterio
from httpx import ASGITransport, AsyncClient
from shapely.geometry import LineString, Polygon

from geovis_lm.gis.terrain import read_masked_band


def write_river_layer(path: Path) -> Path:
    gdf = gpd.GeoDataFrame(
        {"name": ["sample river"]},
        geometry=[LineString([(150, 100), (1500, 1200), (2850, 2300)])],
        crs="EPSG:3857",
    )
    gdf.to_file(path, driver="GeoJSON")
    return path


def write_fuel_layer(path: Path) -> Path:
    gdf = gpd.GeoDataFrame(
        {"fuel_class": ["grass", "forest"]},
        geometry=[
            Polygon([(0, 0), (1500, 0), (1500, 2400), (0, 2400)]),
            Polygon([(1500, 0), (3000, 0), (3000, 2400), (1500, 2400)]),
        ],
        crs="EPSG:3857",
    )
    gdf.to_file(path, driver="GeoJSON")
    return path


def raster_classes(path: Path) -> set[int]:
    with rasterio.open(path) as src:
        return {int(value) for value in read_masked_band(src).filled(0).ravel()}


@pytest.fixture()
def app_module(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOVIS_OUTPUT_ROOT", str(tmp_path / "outputs"))
    monkeypatch.setenv("GEOVIS_REQUIRE_AUTH", "true")
    monkeypatch.setenv("GEOVIS_AUTH_TOKEN", "test-token")
    monkeypatch.setenv("GEOVIS_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("GEOVIS_SESSION_COOKIE_SECURE", "false")

    for module_name in ("geovis_lm.dashboard.app", "geovis_lm.dashboard.operations"):
        sys.modules.pop(module_name, None)
    return importlib.import_module("geovis_lm.dashboard.app")


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def test_flood_risk_workflow_writes_raster_buffers_and_summary(tmp_path):
    from geovis_lm.gis.risk import execute_flood_risk_workflow

    river_path = write_river_layer(tmp_path / "rivers.geojson")
    summary = execute_flood_risk_workflow(
        Path("data/sample/sample_dem.tif"),
        river_path,
        output_dir=tmp_path / "flood",
    )

    flood_path = Path(summary["outputs"]["flood_risk"])
    buffer_path = Path(summary["outputs"]["river_buffers"])
    summary_path = Path(summary["outputs"]["flood_risk_summary_json"])

    assert flood_path.exists()
    assert buffer_path.exists()
    assert summary_path.exists()
    assert raster_classes(flood_path) <= {1, 2, 3}
    assert {"near", "medium", "far"} <= set(gpd.read_file(buffer_path)["buffer_zone"])

    saved = json.loads(summary_path.read_text(encoding="utf-8"))
    assert saved["risk_classes"]["3"] == "high"
    assert saved["model"]["proximity_weight"] == 0.45


def test_wildfire_risk_workflow_normalizes_fuel_and_writes_summary(tmp_path):
    from geovis_lm.gis.risk import execute_wildfire_risk_workflow

    fuel_path = write_fuel_layer(tmp_path / "fuel.geojson")
    summary = execute_wildfire_risk_workflow(
        Path("data/sample/sample_dem.tif"),
        fuel_path,
        output_dir=tmp_path / "wildfire",
        parameters={"fuel_field": "fuel_class"},
    )

    wildfire_path = Path(summary["outputs"]["wildfire_risk"])
    summary_path = Path(summary["outputs"]["wildfire_risk_summary_json"])

    assert wildfire_path.exists()
    assert summary_path.exists()
    assert raster_classes(wildfire_path) <= {1, 2, 3}
    assert summary["fuel"]["fuel_field"] == "fuel_class"
    assert summary["fuel"]["normalized_classes"] == [2, 3]

    saved = json.loads(summary_path.read_text(encoding="utf-8"))
    assert saved["risk_classes"]["2"] == "moderate"
    assert saved["model"]["fuel_weight"] == 0.5


@pytest.mark.parametrize(
    ("workflow_type", "vector_writer", "expected_outputs", "expected_adapter"),
    [
        ("flood_risk", write_river_layer, {"flood_risk", "river_buffers", "flood_risk_summary_json"}, "flood_risk"),
        ("wildfire_risk", write_fuel_layer, {"wildfire_risk", "wildfire_risk_summary_json"}, "wildfire_risk"),
    ],
)
def test_dashboard_dispatches_risk_workflows(
    tmp_path,
    app_module,
    workflow_type,
    vector_writer,
    expected_outputs,
    expected_adapter,
):
    import asyncio

    async def run_flow():
        headers = {"authorization": "Bearer test-token", "x-geovis-user": "risk-user", "x-geovis-role": "owner"}
        async with AsyncClient(transport=ASGITransport(app=app_module.app), base_url="http://testserver") as client:
            project = await client.post("/api/projects", headers=headers, json={"name": "Risk Project"})
            assert project.status_code == 200
            run = await client.post(
                f"/api/projects/{project.json()['id']}/runs",
                headers=headers,
                json={"name": f"{workflow_type} run", "workflow_type": workflow_type},
            )
            assert run.status_code == 200

            vector_path = vector_writer(tmp_path / f"{workflow_type}.geojson")
            upload = await client.post(
                f"/api/projects/{project.json()['id']}/runs/{run.json()['run_id']}/files",
                headers=headers,
                json={
                    "files": [
                        {
                            "filename": "sample_dem.tif",
                            "content_b64": b64(Path("data/sample/sample_dem.tif")),
                            "content_type": "image/tiff",
                        },
                        {
                            "filename": vector_path.name,
                            "content_b64": b64(vector_path),
                            "content_type": "application/geo+json",
                        },
                    ]
                },
            )
            assert upload.status_code == 200

            analyzed = await client.post(f"/api/runs/{run.json()['run_id']}/analyze", headers=headers)
            assert analyzed.status_code == 200
            body = analyzed.json()
            assert body["status"] == "completed"
            assert body["execution_adapter"] == expected_adapter
            assert expected_outputs <= set(body["outputs"])
            assert all(Path(body["outputs"][key]).exists() for key in expected_outputs)

    asyncio.run(run_flow())
