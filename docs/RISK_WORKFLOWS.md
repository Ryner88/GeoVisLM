# Flood and Wildfire Risk Workflows

GeoVisLM includes two filesystem-first screening workflows that run without the
dashboard or PostGIS. They are intended for early prioritization and QA, not for
regulatory flood modeling, emergency response decisions, or production fire
behavior forecasting.

## Risk Classes

Both workflows write single-band `uint8` GeoTIFF risk rasters:

| Value | Class |
| --- | --- |
| 0 | nodata |
| 1 | low |
| 2 | moderate |
| 3 | high |

## Flood Risk

Run:

```bash
.venv/bin/python scripts/run_flood_risk.py \
  --dem data/sample/sample_dem.tif \
  --rivers path/to/rivers.geojson \
  --output-dir outputs/flood_risk
```

Inputs:

- A DEM GeoTIFF.
- At least one river or stream vector layer with valid geometries and CRS.

Outputs:

- `flood_risk.tif`: combined flood-risk raster.
- `river_buffers.geojson`: generated near, medium, and far river buffers.
- `flood_risk_summary.json`: model weights, class descriptions, inputs, and outputs.

The flood workflow combines river proximity, low relative elevation within the
DEM, and flat-slope terrain. Buffer distances are interpreted in the DEM CRS
units and can be adjusted with `--river-near-buffer`, `--river-medium-buffer`,
and `--river-far-buffer`.

Limitations:

- It does not model rainfall, hydrology, drainage, culverts, levees, or return periods.
- Relative elevation is computed only within the supplied DEM extent.
- River buffers are geometric screening zones, not hydraulic inundation extents.

## Wildfire Risk

Run:

```bash
.venv/bin/python scripts/run_wildfire_risk.py \
  --dem data/sample/sample_dem.tif \
  --fuel path/to/fuel.geojson \
  --fuel-field fuel_class \
  --output-dir outputs/wildfire_risk
```

Inputs:

- A DEM GeoTIFF.
- A vegetation/fuel vector layer or fuel raster.
- Optional proximity vector layers, supplied with repeated `--proximity` flags.

Outputs:

- `wildfire_risk.tif`: combined wildfire-risk raster.
- `wildfire_risk_summary.json`: normalized fuel metadata, class descriptions,
  inputs, proximity layers, and outputs.

Fuel vector fields are normalized into stable classes. Numeric values are
rounded and clipped to `1..3`. Text values such as `bare`, `grass`, `shrub`,
`forest`, `timber`, `low`, `moderate`, and `high` are mapped into low,
moderate, and high fuel risk. Missing or unknown fuel values default to
moderate.

Limitations:

- It does not model live fuel moisture, ignition probability, suppression
  capacity, plume behavior, or forecast weather.
- Optional proximity layers are screening modifiers only.
- Raster fuel inputs are nearest-neighbor reprojected to the DEM grid.
