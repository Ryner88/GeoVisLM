# GeoVisLM QGIS Workflow

This guide explains how to open and style the first GeoVisLM terrain-analysis outputs in QGIS.

## Expected Outputs

Run the terrain pipeline first:

```bash
python scripts/run_terrain_analysis.py data/sample/sample_dem.tif --output-dir outputs/maps
```

The current MVP writes these GeoTIFF files:

```text
outputs/maps/slope_degrees.tif
outputs/maps/hillshade.tif
outputs/maps/terrain_risk.tif
```

## Open the Layers in QGIS

1. Open QGIS.
2. Create a new project.
3. Use **Layer > Add Layer > Add Raster Layer**.
4. Add these files from `outputs/maps/`:
   - `hillshade.tif`
   - `slope_degrees.tif`
   - `terrain_risk.tif`
5. Save the QGIS project as `outputs/maps/terrain_analysis.qgz` if you want a local working project file.

The `.qgz` project file is ignored by Git by default.

## Recommended Layer Order

Use this order from top to bottom:

```text
terrain_risk.tif
slope_degrees.tif
hillshade.tif
```

The hillshade should sit at the bottom as terrain context. Slope and risk layers sit above it.

## Hillshade Styling

Layer: `hillshade.tif`

Recommended settings:

- Render type: `Singleband gray`
- Color gradient: `Black to white`
- Contrast enhancement: `Stretch to MinMax`
- Opacity: `100%`

Purpose:

The hillshade gives visual relief so the terrain shape is readable under analysis layers.

## Slope Styling

Layer: `slope_degrees.tif`

Recommended settings:

- Render type: `Singleband pseudocolor`
- Color ramp: `Viridis`, `Turbo`, or `YlOrRd`
- Mode: `Equal interval` or `Continuous`
- Min: use the raster minimum
- Max: use the raster maximum
- Opacity: `45%` to `65%`

Suggested classes:

| Slope degrees | Meaning |
| --- | --- |
| `0-10` | Low slope |
| `10-25` | Moderate slope |
| `25+` | Steep slope |

Purpose:

The slope layer shows where terrain changes quickly and supports terrain-risk interpretation.

## Terrain Risk Styling

Layer: `terrain_risk.tif`

Recommended settings:

- Render type: `Paletted/Unique values`
- Opacity: `60%` to `80%`

Suggested classes:

| Value | Label | Color |
| --- | --- | --- |
| `0` | NoData / background | Transparent |
| `1` | Low risk | Green |
| `2` | Medium risk | Yellow |
| `3` | High risk | Red |

Set value `0` transparent if QGIS shows it as a background class.

Purpose:

The terrain-risk layer summarizes the MVP slope-based risk classification.

## Map Export

To export a portfolio-ready map image:

1. Confirm the layer order and styling.
2. Use **Project > New Print Layout**.
3. Add a map frame.
4. Add a title, legend, scale bar, and north arrow.
5. Export as PNG.

Recommended local output path:

```text
outputs/maps/qgis_terrain_risk_map.png
```

Recommended documentation copy, when you want to version a selected portfolio image:

```text
docs/qgis/exports/qgis_terrain_risk_map.png
```

## Screenshot Locations

Use these folders for QGIS documentation assets:

```text
docs/qgis/screenshots/
docs/qgis/exports/
```

Suggested screenshot names:

```text
docs/qgis/screenshots/qgis_layer_order.png
docs/qgis/screenshots/qgis_slope_styling.png
docs/qgis/screenshots/qgis_risk_styling.png
docs/qgis/exports/qgis_terrain_risk_map.png
```

## Current MVP Limitations

- The current risk layer is slope-only.
- Flood, river, building, or land-cover overlays are not included yet.
- QGIS styling is manual for now; PyQGIS automation will be added later.
- `gdalinfo` and `ogrinfo` are not required for this workflow because Rasterio generated valid GeoTIFF outputs.
