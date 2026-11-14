import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from src.lola_local_quality import summarize_lola_quality


def make_raster(path, data, transform=None):
    if transform is None:
        transform = from_origin(-252.5, 252.5, 5, 5)

    with rasterio.open(
        path, "w", driver="GTiff",
        height=data.shape[0], width=data.shape[1],
        count=1, dtype="float32",
        crs="EPSG:3857", transform=transform, nodata=np.nan,
    ) as ds:
        ds.write(data.astype("float32"), 1)


def test_local_lola_quality_statistics(tmp_path):
    dem = tmp_path / "dem.tif"
    density = tmp_path / "density.tif"
    error = tmp_path / "error.tif"

    make_raster(dem, np.zeros((21, 21)))
    make_raster(density, np.ones((21, 21)))
    make_raster(error, np.full((21, 21), 0.5))

    result = summarize_lola_quality(
        dem, density, error, 10, 10, radius_pixels=2
    )

    assert result["status"] == "available"
    assert result["window"]["total_cells"] == 25
    assert result["ldec"]["positive_return_fraction"] == 1.0
    assert result["ldec"]["zero_return_fraction"] == 0.0
    assert result["toterr"]["median_m"] == pytest.approx(0.5)
    assert result["toterr"]["p95_m"] == pytest.approx(0.5)


def test_zero_returns_are_reported_not_rejected(tmp_path):
    dem = tmp_path / "dem.tif"
    density = tmp_path / "density.tif"
    error = tmp_path / "error.tif"

    make_raster(dem, np.zeros((21, 21)))
    make_raster(density, np.zeros((21, 21)))
    make_raster(error, np.full((21, 21), 0.4))

    result = summarize_lola_quality(dem, density, error, 10, 10, 2)

    assert result["status"] == "available"
    assert result["ldec"]["zero_return_fraction"] == 1.0
    assert result["ldec"]["positive_return_fraction"] == 0.0


def test_misaligned_density_is_rejected(tmp_path):
    dem = tmp_path / "dem.tif"
    density = tmp_path / "density.tif"
    error = tmp_path / "error.tif"

    array = np.zeros((21, 21))
    make_raster(dem, array)
    make_raster(density, array, from_origin(-250, 250, 5, 5))
    make_raster(error, array)

    with pytest.raises(ValueError, match="non allineato"):
        summarize_lola_quality(dem, density, error, 10, 10)


def test_candidate_outside_raster_is_rejected(tmp_path):
    dem = tmp_path / "dem.tif"
    density = tmp_path / "density.tif"
    error = tmp_path / "error.tif"

    array = np.zeros((21, 21))
    for path in (dem, density, error):
        make_raster(path, array)

    with pytest.raises(ValueError, match="fuori dal raster"):
        summarize_lola_quality(dem, density, error, 30, 30)


def test_invalid_radius_is_rejected(tmp_path):
    dem = tmp_path / "dem.tif"
    density = tmp_path / "density.tif"
    error = tmp_path / "error.tif"

    array = np.zeros((21, 21))
    for path in (dem, density, error):
        make_raster(path, array)

    with pytest.raises(ValueError, match="radius_pixels"):
        summarize_lola_quality(dem, density, error, 10, 10, -1)
