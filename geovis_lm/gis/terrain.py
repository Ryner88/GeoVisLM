from pathlib import Path

import numpy as np
import rasterio


def load_dem(path: str | Path):
    path = Path(path)
    with rasterio.open(path) as src:
        dem = src.read(1, masked=True)
        profile = src.profile.copy()
        transform = src.transform
        crs = src.crs
    return dem, profile, transform, crs


def calculate_slope_degrees(dem, transform):
    """
    Calculate simple slope in degrees from a DEM array.
    This is an MVP implementation. Later we can replace/compare with GDAL/QGIS slope tools.
    """
    x_res = transform.a
    y_res = abs(transform.e)

    dz_dy, dz_dx = np.gradient(dem.filled(np.nan), y_res, x_res)
    slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
    slope_deg = np.degrees(slope_rad)

    return np.ma.masked_invalid(slope_deg)


def calculate_hillshade(dem, transform, azimuth=315, altitude=45):
    """
    Basic hillshade calculation.
    """
    x_res = transform.a
    y_res = abs(transform.e)

    data = dem.filled(np.nan)
    dz_dy, dz_dx = np.gradient(data, y_res, x_res)

    slope = np.pi / 2.0 - np.arctan(np.sqrt(dz_dx * dz_dx + dz_dy * dz_dy))
    aspect = np.arctan2(-dz_dx, dz_dy)

    azimuth_rad = np.radians(azimuth)
    altitude_rad = np.radians(altitude)

    shaded = (
        np.sin(altitude_rad) * np.sin(slope)
        + np.cos(altitude_rad) * np.cos(slope) * np.cos(azimuth_rad - aspect)
    )

    hillshade = 255 * (shaded + 1) / 2
    return np.ma.masked_invalid(hillshade)


def classify_slope_risk(slope):
    """
    Simple terrain risk classification:
    1 = low
    2 = medium
    3 = high
    """
    risk = np.zeros(slope.shape, dtype=np.uint8)

    risk[(slope >= 0) & (slope < 10)] = 1
    risk[(slope >= 10) & (slope < 25)] = 2
    risk[slope >= 25] = 3

    return np.ma.array(risk, mask=slope.mask)


def save_raster(output_path: str | Path, array, profile, dtype="float32", nodata=None):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    out_profile = profile.copy()
    out_profile.update(
        dtype=dtype,
        count=1,
        compress="lzw",
        nodata=nodata,
    )

    data = array.filled(nodata if nodata is not None else 0).astype(dtype)

    with rasterio.open(output_path, "w", **out_profile) as dst:
        dst.write(data, 1)

    return output_path
