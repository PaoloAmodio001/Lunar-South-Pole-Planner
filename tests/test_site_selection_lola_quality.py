import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from src.site_selection import select_candidate_sites


def make_raster(path, data, transform):
    with rasterio.open(
        path, "w", driver="GTiff",
        height=data.shape[0], width=data.shape[1],
        count=1, dtype="float32",
        crs="EPSG:3857", transform=transform, nodata=np.nan,
    ) as ds:
        ds.write(data.astype("float32"), 1)


def test_lola_quality_does_not_change_terrain_ranking(tmp_path):
    transform = from_origin(-62.5, 62.5, 5, 5)
    rows, cols = np.indices((25, 25))
    dem_data = (rows * 0.1 + cols * 0.05).astype("float32")

    dem = tmp_path / "dem.tif"
    density = tmp_path / "density.tif"
    error = tmp_path / "error.tif"

    make_raster(dem, dem_data, transform)
    make_raster(density, np.ones((25, 25)), transform)
    make_raster(error, np.full((25, 25), 0.4), transform)

    baseline = select_candidate_sites(
        dem, output_path=tmp_path / "baseline.json",
        radius_pixels=2, target_candidates=16, top_n=10,
    )
    enriched = select_candidate_sites(
        dem, output_path=tmp_path / "enriched.json",
        radius_pixels=2, target_candidates=16, top_n=10,
        lola_density_path=density,
        lola_error_path=error,
    )

    baseline_ranking = [
        (item["name"], item["score"]["score_0_100"])
        for item in baseline["top_candidates"]
    ]
    enriched_ranking = [
        (item["name"], item["score"]["score_0_100"])
        for item in enriched["top_candidates"]
    ]

    assert enriched_ranking == baseline_ranking
    assert all("lola_quality" in item for item in enriched["top_candidates"])

    first = enriched["top_candidates"][0]["lola_quality"]
    assert first["status"] == "available"
    assert first["ldec"]["positive_return_fraction"] == pytest.approx(1.0)
    assert first["toterr"]["median_m"] == pytest.approx(0.4)


def test_lola_paths_must_be_configured_together(tmp_path):
    dem = tmp_path / "dem.tif"
    make_raster(dem, np.zeros((25, 25)), from_origin(-62.5, 62.5, 5, 5))

    with pytest.raises(ValueError, match="devono essere configurati insieme"):
        select_candidate_sites(
            dem,
            output_path=tmp_path / "ranking.json",
            radius_pixels=2,
            lola_density_path=tmp_path / "density.tif",
        )


def test_misaligned_lola_grid_is_not_silently_accepted(tmp_path):
    transform = from_origin(-62.5, 62.5, 5, 5)
    dem = tmp_path / "dem.tif"
    density = tmp_path / "density.tif"
    error = tmp_path / "error.tif"

    data = np.zeros((25, 25))
    make_raster(dem, data, transform)
    make_raster(density, data, from_origin(-60, 60, 5, 5))
    make_raster(error, data, transform)

    with pytest.raises(ValueError, match="non allineato"):
        select_candidate_sites(
            dem, output_path=tmp_path / "ranking.json",
            radius_pixels=2, target_candidates=16,
            lola_density_path=density,
            lola_error_path=error,
        )
