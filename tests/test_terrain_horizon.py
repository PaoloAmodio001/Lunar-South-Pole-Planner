# Last updated: 2026-11-14
import numpy as np
import rasterio
from rasterio.transform import from_origin

from src.terrain_horizon import calculate_horizon


def make_dem(tmp_path, wall=None, density_wall=False):
    dem_path = tmp_path / "dem.tif"
    density_path = tmp_path / "density.tif"

    dem = np.zeros((101, 101), dtype=np.float32)
    density = np.ones_like(dem)

    if wall == "north":
        dem[45, 40:61] = 10.0
        if density_wall:
            density[45, 40:61] = 0.0
    elif wall == "south":
        dem[55, 40:61] = 10.0
        if density_wall:
            density[55, 40:61] = 0.0

    transform = from_origin(-252.5, 252.5, 5, 5)

    for path, array in ((dem_path, dem), (density_path, density)):
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=101,
            width=101,
            count=1,
            dtype="float32",
            transform=transform,
            nodata=np.nan,
        ) as ds:
            ds.write(array, 1)

    return dem_path, density_path


def run_profile(dem_path, density_path=None):
    return calculate_horizon(
        dem_path,
        0.0,
        0.0,
        density_path=density_path,
        azimuth_step_deg=2.0,
        max_distance_m=200.0,
    )


def angle_at(profile, azimuth):
    idx = int(np.argmin(np.abs(profile.azimuth_deg - azimuth)))
    return profile.elevation_deg[idx]


def test_flat_terrain_has_zero_horizon(tmp_path):
    dem_path, _ = make_dem(tmp_path)
    profile = run_profile(dem_path)
    assert np.allclose(profile.elevation_deg, 0.0)


def test_north_wall_is_detected_at_north(tmp_path):
    dem_path, _ = make_dem(tmp_path, wall="north")
    profile = run_profile(dem_path)
    expected = np.degrees(np.arctan2(10.0, 25.0))
    assert np.isclose(angle_at(profile, 0), expected)
    assert np.isclose(angle_at(profile, 180), 0.0)
    assert profile.azimuth_deg[np.nanargmax(profile.elevation_deg)] == 0.0


def test_south_wall_is_detected_at_south(tmp_path):
    dem_path, _ = make_dem(tmp_path, wall="south")
    profile = run_profile(dem_path)
    expected = np.degrees(np.arctan2(10.0, 25.0))
    assert np.isclose(angle_at(profile, 180), expected)
    assert np.isclose(angle_at(profile, 0), 0.0)
    assert angle_at(profile, 180) > angle_at(profile, 0)


def test_zero_density_is_reported_for_wall(tmp_path):
    dem_path, density_path = make_dem(
        tmp_path, wall="north", density_wall=True
    )
    profile = run_profile(dem_path, density_path)
    assert profile.zero_density_fraction[0] > 0.0


def test_georeference_remains_unvalidated(tmp_path):
    dem_path, _ = make_dem(tmp_path)
    profile = run_profile(dem_path)
    assert profile.georeference_validated is False


def test_invalid_azimuth_step_raises(tmp_path):
    import pytest

    dem_path, _ = make_dem(tmp_path)
    with pytest.raises(ValueError, match="azimuth_step_deg"):
        calculate_horizon(dem_path, 0.0, 0.0, azimuth_step_deg=0)


def test_nonpositive_max_distance_raises(tmp_path):
    import pytest

    dem_path, _ = make_dem(tmp_path)
    with pytest.raises(ValueError, match="max_distance_m"):
        calculate_horizon(dem_path, 0.0, 0.0, max_distance_m=-5)


def test_observer_outside_dem_raises(tmp_path):
    import pytest

    dem_path, _ = make_dem(tmp_path)
    with pytest.raises(ValueError, match="fuori dal raster"):
        calculate_horizon(dem_path, 10000.0, 10000.0)


def test_observer_on_nodata_raises(tmp_path):
    import pytest

    dem_path, _ = make_dem(tmp_path)
    with rasterio.open(dem_path, "r+") as ds:
        ds.write(np.array([[np.nan]], dtype=np.float32), 1, window=((50, 51), (50, 51)))

    with pytest.raises(ValueError, match="Quota osservatore non valida"):
        calculate_horizon(dem_path, 0.0, 0.0)


# --- F11: geometria sferica -------------------------------------------------

import math

import pytest

LUNAR_STERE = (
    "+proj=stere +lat_0=-90 +lon_0=0 +k=1 +x_0=0 +y_0=0 "
    "+R=1737400 +units=m +no_defs"
)
R_MOON = 1737400.0


def make_crs_dem(tmp_path, crs, pixel=100.0, size=201, wall=None):
    """DEM piatto (z=0) centrato su (0, 0), opzionale muro a nord."""
    path = tmp_path / "crs_dem.tif"
    dem = np.zeros((size, size), dtype=np.float32)
    c = size // 2
    if wall is not None:
        offset_px, height_m = wall
        dem[c - offset_px, :] = height_m
    half = pixel * size / 2.0
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=1,
        dtype="float32", transform=from_origin(-half, half, pixel, pixel),
        nodata=np.nan, crs=crs,
    ) as ds:
        ds.write(dem, 1)
    return path


def pole_elevation_deg(rho, z, observer_z):
    """Elevazione analitica con osservatore al polo, campione a raggio
    stereografico rho (k=1): colatitudine theta = 2 atan(rho / 2R)."""
    theta = 2.0 * math.atan(rho / (2.0 * R_MOON))
    vertical = (R_MOON + z) * math.cos(theta) - (R_MOON + observer_z)
    horizontal = (R_MOON + z) * math.sin(theta)
    return math.degrees(math.atan2(vertical, horizontal))


def test_spherical_flat_terrain_shows_curvature_dip(tmp_path):
    path = make_crs_dem(tmp_path, LUNAR_STERE, pixel=100.0)
    profile = calculate_horizon(path, 0.0, 0.0, azimuth_step_deg=10.0,
                                max_distance_m=5000.0)
    expected = pole_elevation_deg(100.0, 0.0, 0.0)  # campione più vicino
    assert expected < 0.0
    assert np.allclose(profile.elevation_deg, expected, atol=1e-9)
    assert np.allclose(profile.max_distance_m, 100.0)


def test_spherical_raised_obstacle_matches_sphere_geometry(tmp_path):
    # muro alto 500 m a 20 km a nord
    path = make_crs_dem(tmp_path, LUNAR_STERE, pixel=200.0, size=241,
                        wall=(100, 500.0))
    profile = calculate_horizon(path, 0.0, 0.0, azimuth_step_deg=2.0,
                                max_distance_m=23000.0)
    expected = pole_elevation_deg(20000.0, 500.0, 0.0)
    planar = math.degrees(math.atan2(500.0, 20000.0))
    north = angle_at(profile, 0)
    assert np.isclose(north, expected, atol=1e-9)
    assert planar - north > 0.2  # la curvatura abbassa l'ostacolo
    assert np.isclose(profile.max_distance_m[0], 20000.0)


def test_spherical_observer_height_dips_horizon(tmp_path):
    h = 10.0
    path = make_crs_dem(tmp_path, LUNAR_STERE, pixel=100.0)
    profile = calculate_horizon(path, 0.0, 0.0, azimuth_step_deg=45.0,
                                max_distance_m=9000.0, observer_height_m=h)
    rhos = np.arange(100.0, 9100.0, 100.0)
    expected = max(pole_elevation_deg(r, 0.0, h) for r in rhos)
    dip = -math.degrees(math.acos(R_MOON / (R_MOON + h)))
    assert profile.observer_elevation_m == pytest.approx(h)
    assert np.isclose(angle_at(profile, 0), expected, atol=1e-9)
    assert dip - 0.01 < angle_at(profile, 0) < 0.0


def test_spherical_off_pole_observer_flat_is_symmetric(tmp_path):
    # osservatore a ~100 km dal polo: terreno piatto => stessa depressione
    path = make_crs_dem(tmp_path, LUNAR_STERE, pixel=100.0)
    with rasterio.open(path) as ds:
        dem = ds.read(1)
        profile_crs = ds.crs
    off = tmp_path / "off.tif"
    with rasterio.open(
        off, "w", driver="GTiff", height=201, width=201, count=1,
        dtype="float32", nodata=np.nan, crs=profile_crs,
        transform=from_origin(-10050.0, -89950.0, 100.0, 100.0),
    ) as ds:
        ds.write(dem, 1)
    profile = calculate_horizon(off, 0.0, -100000.0, azimuth_step_deg=30.0,
                                max_distance_m=5000.0)
    assert np.all(profile.elevation_deg < 0.0)
    assert np.allclose(profile.elevation_deg, profile.elevation_deg[0],
                       atol=1e-6)


def test_missing_crs_keeps_planar_behaviour(tmp_path):
    dem_path, _ = make_dem(tmp_path, wall="north")
    profile = run_profile(dem_path)
    assert np.isclose(angle_at(profile, 0), np.degrees(np.arctan2(10.0, 25.0)))
    assert np.isclose(angle_at(profile, 180), 0.0)


@pytest.mark.parametrize(
    "crs",
    [
        # sfera lunare ma geografica (gradi): non verificabile => planare
        "+proj=longlat +R=1737400 +no_defs",
        # stereografica polare con raggio marziano: non lunare
        "+proj=stere +lat_0=-90 +lon_0=0 +k=1 +R=3396190 +units=m +no_defs",
        # ellissoide terrestre (EPSG:3031)
        "EPSG:3031",
        # raggio lunare ma ellissoide schiacciato: non sferico
        "+proj=stere +lat_0=-90 +lon_0=0 +k=1 +a=1737400 +b=1730000 "
        "+units=m +no_defs",
    ],
)
def test_non_lunar_or_incompatible_crs_falls_back_to_planar(tmp_path, crs):
    path = make_crs_dem(tmp_path, crs, pixel=100.0, size=101)
    profile = calculate_horizon(path, 0.0, 0.0, azimuth_step_deg=30.0,
                                max_distance_m=3000.0)
    assert np.allclose(profile.elevation_deg, 0.0)
