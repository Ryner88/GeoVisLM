# GeoVisLM

GeoVisLM is an AI geospatial and scientific visualization lab that combines GIS analysis, ParaView-style scientific visualization, and a small domain-specific language model called GeoMiniLM.

## Goals

- Automate geospatial analysis workflows.
- Generate terrain, slope, hillshade, and risk maps.
- Produce scientific visualization scripts and renders.
- Build a small custom LLM for GIS and visualization workflows.
- Export portfolio-ready reports.

## Initial MVP

The first MVP focuses on terrain analysis:

1. Load a DEM raster.
2. Generate slope and hillshade outputs.
3. Classify terrain risk.
4. Export map images.
5. Generate an analysis report.

## Stack

- Python
- Rasterio
- GeoPandas
- GDAL
- QGIS / PyQGIS later
- ParaView later
- Hugging Face Transformers / Tokenizers
- FastAPI dashboard later
