# Prime Host GDAL Tools

This record applies to the Prime production host only. Installing GDAL in WSL,
on an operator laptop, or only inside the application container does not satisfy
this operational task.

## Scope

- Host: Prime production VPS
- Hostname observed: `racknerd-47a02a8`
- Public IPv4: `192.3.31.132`
- Repository path: `/opt/geovis_lm`
- Validation timestamp: `2026-08-01T17:53:24Z` UTC

Host GDAL tools are for production diagnostics, independent inspection of
retained/restored geospatial files, and incident triage. They do not replace
the containerized Python/Rasterio/Fiona runtime used by the dashboard and
worker.

## Installed Packages

Prime reports:

```text
gdal-bin 3.8.4+dfsg-3ubuntu3 install ok installed
libgdal34t64 3.8.4+dfsg-3ubuntu3 install ok installed
```

The package source is Ubuntu Noble `universe`; `apt-cache policy gdal-bin`
reported installed and candidate version `3.8.4+dfsg-3ubuntu3`.

## Command Versions

```text
gdalinfo --version
GDAL 3.8.4, released 2024/02/08

ogrinfo --version
GDAL 3.8.4, released 2024/02/08
```

## Sample DEM Inspection

Command:

```bash
cd /opt/geovis_lm
gdalinfo data/sample/sample_dem.tif
```

Prime result summary:

```text
Driver: GTiff/GeoTIFF
Files: data/sample/sample_dem.tif
Size is 100, 80
Coordinate System is:
Data axis to CRS axis mapping: 1,2
Origin = (0.000000000000000,2400.000000000000000)
Pixel Size = (30.000000000000000,-30.000000000000000)
Band 1 Block=100x20 Type=Float32, ColorInterp=Gray
  NoData Value=-9999
```

Full output included CRS `EPSG:3857` / WGS 84 Pseudo-Mercator metadata.

## Sample Vector Inspection

Command:

```bash
cd /opt/geovis_lm
ogrinfo -so data/sample/sample_overlay.geojson sample_overlay
```

Prime result summary:

```text
INFO: Open of `data/sample/sample_overlay.geojson'
Layer name: sample_overlay
Geometry: Polygon
Feature Count: 1
Extent: (0.000000, 0.000000) - (1.000000, 1.000000)
id: String (0.0)
kind: String (0.0)
```

Full output included `EPSG:4326` / WGS 84 layer CRS metadata.

## Runtime Validation

After confirming host GDAL tools, Prime still reported all Compose services
healthy:

```text
geovis_lm-dashboard-1   Up 2 weeks (healthy)   127.0.0.1:8000->8000/tcp
geovis_lm-db-1          Up 3 weeks (healthy)   5432/tcp
geovis_lm-worker-1      Up 2 weeks (healthy)   8000/tcp
```

Container test validation on Prime:

```text
docker compose exec -T dashboard python -m pytest -q
39 passed, 19 warnings in 9.64s
```

The warnings are the known NumPy `2.5` masked-array deprecation warnings in the
production container test suite. Host GDAL installation did not require changing
container runtime dependencies.

## Usage Guidance

- Use host `gdalinfo` and `ogrinfo` for production diagnostics and restored-file
  inspection from `/opt/geovis_lm`.
- Use containerized application commands for normal GeoVisLM processing,
  dashboard tests, and worker execution.
- Do not treat WSL or laptop GDAL output as production-host validation.
- Do not add GDAL CLI assumptions to user-facing workflows unless the workflow
  explicitly targets host operations; the dashboard remains container-driven.
