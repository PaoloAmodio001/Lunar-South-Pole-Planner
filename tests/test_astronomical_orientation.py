"""Orientamento azimutale: nord geografico lunare ↔ nord di griglia."""
import json
import math
from pathlib import Path

import numpy as np
import pytest
import rasterio
from pyproj import CRS, Proj, Transformer
from rasterio.transform import from_origin

import src.mission_orchestrator as orchestrator
from src.astronomy import Observation, SITES
from src.illumination_analysis import estimate_direct_solar_visibility
from src.horizon_analysis import calculate_and_write_horizon
from src.lunar_geometry import (
    MOON_GEOGRAPHIC_CRS,
    AzimuthOrientationError,
    geographic_to_grid_azimuth,
    geographic_to_projected,
    grid_azimuth_offset,
    grid_to_geographic_azimuth,
)
from src.visibility import compare_with_horizon


SPS = ("+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +x_0=0 +y_0=0 "
       "+R=1737400 +units=m +no_defs")
SITE04 = Path("data/terrain/official-lola/Site04_final_adj_5mpp_surf.tif")
SHACK_LAT, SHACK_LON = SITES["Shackleton"]
SHACK_OFFSET = SHACK_LON % 360.0  # 188.13° (stereografica polare sud, lon_0 = 0)
needs_site04 = pytest.mark.skipif(not SITE04.is_file(), reason="Site04 assente")

KERNELS = Path("data/terrain/kernels")
DE421 = Path("de421.bsp")
HORIZONS_FIXTURE = Path("tests/data/horizons_shackleton_20261101_12h.json")
needs_spice = pytest.mark.skipif(
    not (DE421.is_file() and (KERNELS / "moon_pa_de421_1900-2050.bpc").is_file()
         and (KERNELS / "moon_080317.tf").is_file()
         and (KERNELS / "pck00008.tpc").is_file()),
    reason="kernel SPICE lunari locali non disponibili",
)


def shackleton_xy(crs=SPS):
    return geographic_to_projected(SHACK_LON, SHACK_LAT, crs)


def step_geographic(crs, x, y, grid_az_deg, distance=50.0):
    """Avanza di `distance` m lungo l'azimut di griglia e torna in lon/lat."""
    rad = math.radians(grid_az_deg)
    to_geo = Transformer.from_crs(CRS.from_user_input(crs), MOON_GEOGRAPHIC_CRS,
                                  always_xy=True)
    lon0, lat0 = to_geo.transform(x, y)
    lon1, lat1 = to_geo.transform(x + distance * math.sin(rad),
                                  y + distance * math.cos(rad))
    dlon = (lon1 - lon0 + 180) % 360 - 180
    return lat1 - lat0, dlon


# ------------------------------------------------ 1-3. Conversione e segno
def test_shackleton_offset_value_and_sign():
    x, y = shackleton_xy()
    result = grid_azimuth_offset(SPS, x, y)
    assert result["offset_deg"] == pytest.approx(SHACK_OFFSET, abs=1e-6)
    assert result["offset_deg"] == pytest.approx(188.13, abs=1e-6)
    # PROJ usa il segno opposto: meridian_convergence = -offset (mod 360).
    assert result["proj_meridian_convergence_deg"] == pytest.approx(171.87, abs=1e-6)
    assert result["east_minus_north_deg"] == pytest.approx(90.0, abs=1e-5)


@needs_site04
def test_site04_crs_at_shackleton_pixel():
    with rasterio.open(SITE04) as ds:
        x, y = ds.xy(1600, 1599)
        result = grid_azimuth_offset(ds.crs, x, y)
    # Centro pixel spostato di mezzo pixel dal punto nominale: lon -171.853°.
    assert result["observer_longitude_east_deg"] == pytest.approx(-171.8527, abs=1e-3)
    assert result["offset_deg"] == pytest.approx(188.1473, abs=1e-3)


@pytest.mark.parametrize("geo_az,grid_az", [
    (0.0, 188.13), (90.0, 278.13), (180.0, 8.13), (270.0, 98.13),
    (45.0, 233.13), (135.0, 323.13), (225.0, 53.13), (315.0, 143.13),
])
def test_cardinal_and_intermediate_directions(geo_az, grid_az):
    assert geographic_to_grid_azimuth(geo_az, SHACK_OFFSET) == pytest.approx(grid_az)
    assert grid_to_geographic_azimuth(grid_az, SHACK_OFFSET) == pytest.approx(geo_az % 360)


@pytest.mark.parametrize("geo_az,expect", [
    (0.0, "lat+"), (180.0, "lat-"), (90.0, "lon+"), (270.0, "lon-"),
])
def test_grid_direction_moves_geographically_as_expected(geo_az, expect):
    """Verifica fisica del segno: muoversi verso N aumenta la latitudine, ecc."""
    x, y = shackleton_xy()
    offset = grid_azimuth_offset(SPS, x, y)["offset_deg"]
    dlat, dlon = step_geographic(SPS, x, y, geographic_to_grid_azimuth(geo_az, offset))
    if expect == "lat+":
        assert dlat > 0 and abs(dlon) < 0.05
    elif expect == "lat-":
        assert dlat < 0 and abs(dlon) < 0.05
    elif expect == "lon+":
        assert dlon > 0
    else:
        assert dlon < 0


@pytest.mark.parametrize("lon", [-171.87, -137.49, 37.36667, 0.0, 90.0, 179.0])
@pytest.mark.parametrize("lon_0", [0.0, 90.0])
def test_offset_matches_analytic_and_proj(lon, lon_0):
    crs = SPS.replace("+lon_0=0", f"+lon_0={lon_0}")
    x, y = geographic_to_projected(lon, -89.5, crs)
    result = grid_azimuth_offset(crs, x, y)
    analytic = (lon - lon_0) % 360.0
    assert (result["offset_deg"] - analytic + 180) % 360 - 180 == pytest.approx(0, abs=1e-6)
    gamma = Proj(CRS.from_user_input(crs)).get_factors(lon, -89.5).meridian_convergence
    assert (result["offset_deg"] + gamma + 180) % 360 - 180 == pytest.approx(0, abs=1e-6)


@pytest.mark.parametrize("az", [0.0, 12.3, 188.13, 359.999, 360.0, -10.0, 720.5])
@pytest.mark.parametrize("offset", [SHACK_OFFSET, -171.87, 0.0, 359.9])
def test_round_trip_and_range(az, offset):
    grid = geographic_to_grid_azimuth(az, offset)
    back = grid_to_geographic_azimuth(grid, offset)
    assert 0.0 <= grid < 360.0 and 0.0 <= back < 360.0
    assert (back - az % 360 + 180) % 360 - 180 == pytest.approx(0, abs=1e-9)


# ------------------------------------------- 4. Errori espliciti
@pytest.mark.parametrize("crs", [None, "EPSG:3857", "EPSG:4326",
                                 SPS.replace("1737400", "1738100")])
def test_unverifiable_crs_is_rejected(crs):
    with pytest.raises(AzimuthOrientationError):
        grid_azimuth_offset(crs, -1000.0, -7000.0)


def test_pole_is_rejected():
    with pytest.raises(AzimuthOrientationError, match="polo"):
        grid_azimuth_offset(SPS, 0.0, 0.0)


def test_mirrored_projection_is_rejected():
    mirrored = SPS + " +axis=wnu"
    with pytest.raises(AzimuthOrientationError, match="speculare"):
        grid_azimuth_offset(mirrored, 1000.0, -7000.0)


@pytest.mark.parametrize("bad", [math.nan, math.inf])
def test_non_finite_angles_rejected(bad):
    with pytest.raises(ValueError):
        geographic_to_grid_azimuth(bad, 0.0)
    with pytest.raises(ValueError):
        grid_to_geographic_azimuth(0.0, bad)


# ----------------------- 5-6. Gradi/radianti e coerenza tra moduli
def make_wall_dem(path, wall_geo_az=0.0, crs=SPS):
    """DEM piatto attorno a Shackleton con un muro alto 200 m a ~500 m
    nella direzione geografica `wall_geo_az` dall'osservatore."""
    xs, ys = shackleton_xy(crs) if crs == SPS else (-1000.0, -7000.0)
    left, top, res, n = xs - 1502.5, ys + 1502.5, 5.0, 601
    rows, cols = np.indices((n, n))
    px = left + (cols + 0.5) * res
    py = top - (rows + 0.5) * res
    dx, dy = px - xs, py - ys
    dist = np.hypot(dx, dy)
    grid_az = np.degrees(np.arctan2(dx, dy)) % 360
    offset = SHACK_OFFSET if crs == SPS else 0.0
    target = geographic_to_grid_azimuth(wall_geo_az, offset)
    ang = np.abs((grid_az - target + 180) % 360 - 180)
    z = np.zeros((n, n), dtype="float32")
    z[(dist > 450) & (dist < 550) & (ang < 15)] = 200.0
    with rasterio.open(path, "w", driver="GTiff", height=n, width=n, count=1,
                       dtype="float32", crs=crs,
                       transform=from_origin(left, top, res, res)) as ds:
        ds.write(z, 1)
    return path, 300, 300  # osservatore al centro (riga, colonna)


def test_horizon_peak_is_at_geographic_north(tmp_path):
    dem, row, col = make_wall_dem(tmp_path / "wall.tif")
    profile = json.loads(calculate_and_write_horizon(
        dem, row, col, observer_height_m=1.0, azimuth_step_deg=1.0,
        max_distance_m=1000.0, output_path=tmp_path / "h.json").read_text())
    az = np.array([s["grid_azimuth_deg"] for s in profile["samples"]])
    el = np.array([s["horizon_elevation_deg"] for s in profile["samples"]])
    # Centro angolare del muro (media circolare dei campioni oscurati): il muro
    # è piatto e largo ±15°, quindi argmax cadrebbe su un bordo qualsiasi.
    blocked = np.radians(az[el > 10.0])
    wall_grid = math.degrees(math.atan2(np.sin(blocked).sum(),
                                        np.cos(blocked).sum())) % 360
    offset = grid_azimuth_offset(profile["crs_wkt"], profile["observer"]["x_map_units"],
                                 profile["observer"]["y_map_units"])["offset_deg"]
    # Il centro del muro (assi della griglia) corrisponde al nord geografico.
    wall_geo = grid_to_geographic_azimuth(wall_grid, offset)
    assert min(wall_geo, 360 - wall_geo) <= 1.0
    # Gradi, non radianti: muro alto 200 m a ~500 m → ~21.8°.
    assert 18.0 < el.max() < 25.0

    north = compare_with_horizon(geographic_to_grid_azimuth(0.0, offset), 5.0, az, el)
    south = compare_with_horizon(geographic_to_grid_azimuth(180.0, offset), 5.0, az, el)
    assert north.status == "preliminary_blocked"
    assert south.status == "preliminary_visible"
    # Senza rotazione (assumendo nord griglia = nord geografico) l'esito si inverte:
    assert compare_with_horizon(0.0, 5.0, az, el).status == "preliminary_visible"


def test_illumination_module_uses_same_convention(tmp_path):
    dem, row, col = make_wall_dem(tmp_path / "wall.tif")
    horizon = calculate_and_write_horizon(
        dem, row, col, azimuth_step_deg=1.0, max_distance_m=1000.0,
        output_path=tmp_path / "h.json")
    obs = [{"time_utc": "t0", "azimuth_deg": 0.0, "elevation_deg": 5.0},
           {"time_utc": "t1", "azimuth_deg": 180.0, "elevation_deg": 5.0}]
    out = estimate_direct_solar_visibility(
        horizon, obs, grid_azimuth_offset_deg=SHACK_OFFSET,
        output_path=tmp_path / "ill.json")
    rows = json.loads(out.read_text())["observations"]
    assert [r["estimated_direct_sun_visible"] for r in rows] == [False, True]
    assert rows[0]["grid_azimuth_deg"] == pytest.approx(188.13)


# ----------------------------------------- 7. Integrazione orchestratore
def _run(tmp_path, monkeypatch, offset_value, crs=SPS, sun_az=(0.0, 180.0)):
    dem, row, col = make_wall_dem(tmp_path / "wall.tif", crs=crs)

    def fake_query(target, latitude, longitude, start_utc, hours=48, step="1h"):
        assert (latitude, longitude) == (SHACK_LAT, SHACK_LON)
        return [Observation(f"2026-10-25T0{i}:00:00+00:00", az, 5.0, 1.0, 0.0)
                for i, az in enumerate(sun_az)]

    monkeypatch.setattr(orchestrator, "query_observations", fake_query)
    out = tmp_path / "out"
    config = {
        "output_dir": str(out),
        "astronomy": {"enabled": True, "site": "Shackleton", "hours": 2,
                      "start_utc": "2026-10-25T00:00:00+00:00"},
        "horizon_analysis": {"enabled": True, "dem_path": str(dem),
                             "observer_row": row, "observer_col": col,
                             "azimuth_step_deg": 1.0, "max_distance_m": 1000.0},
        "illumination": {"enabled": True, "grid_azimuth_offset_deg": offset_value},
        "visibility_analysis": {"enabled": True,
                                "grid_azimuth_offset_deg": offset_value},
        "mission_report": {"site_name": "Shackleton"},
    }
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return orchestrator.run_mission_workflow(path), out


def test_orchestrator_derives_offset_from_profile(tmp_path, monkeypatch):
    result, out = _run(tmp_path, monkeypatch, "from_horizon_profile")
    assert result["steps"]["illumination"]["status"] == "success"
    assert result["steps"]["visibility_analysis"]["status"] == "success"
    ill = json.loads((out / "solar_illumination_diagnostic.json").read_text())
    vis = json.loads((out / "astronomical_visibility_diagnostic.json").read_text())
    for mapping in (ill["azimuth_mapping"], vis["azimuth_mapping"]):
        assert mapping["source"] == "horizon_profile_crs"
        assert mapping["offset_deg"] == pytest.approx(SHACK_OFFSET, abs=0.05)
        assert mapping["horizons_frame_equivalence_verified"] is False
    # Stesso offset nei due moduli (unica fonte).
    assert ill["azimuth_mapping"]["offset_deg"] == vis["azimuth_mapping"]["offset_deg"]
    assert [r["estimated_direct_sun_visible"] for r in ill["observations"]] == [False, True]
    sun = [r["status"] for r in vis["observations"] if r["target"] == "Sun"]
    assert sun == ["preliminary_blocked", "preliminary_visible"]


def test_orchestrator_rejects_wrong_numeric_offset(tmp_path, monkeypatch):
    result, _ = _run(tmp_path, monkeypatch, 0.0)
    for step in ("illumination", "visibility_analysis"):
        assert result["steps"][step]["status"] == "failed"
        assert result["steps"][step]["error_type"] == "AzimuthOrientationError"
    assert result["status"] == "completed_with_errors"


def test_orchestrator_accepts_correct_numeric_offset(tmp_path, monkeypatch):
    with rasterio.open(make_wall_dem(tmp_path / "probe.tif")[0]) as ds:
        x, y = ds.xy(300, 300)
    exact = grid_azimuth_offset(SPS, x, y)["offset_deg"]
    result, out = _run(tmp_path, monkeypatch, exact)
    assert result["steps"]["illumination"]["status"] == "success"
    ill = json.loads((out / "solar_illumination_diagnostic.json").read_text())
    assert ill["azimuth_mapping"]["source"] == "configured_checked_against_crs"


def test_missing_offset_still_rejected(tmp_path, monkeypatch):
    result, _ = _run(tmp_path, monkeypatch, None)
    assert result["steps"]["illumination"]["status"] == "failed"
    assert "grid_azimuth_offset_deg" in result["steps"]["illumination"]["error"]


def test_example_config_uses_single_offset_source():
    config = json.loads(Path("mission_config.example.json").read_text("utf-8"))
    assert config["illumination"]["grid_azimuth_offset_deg"] == "from_horizon_profile"
    assert config["visibility_analysis"]["grid_azimuth_offset_deg"] == "from_horizon_profile"
    assert (config["horizon_analysis"]["observer_row"],
            config["horizon_analysis"]["observer_col"]) == (1600, 1599)


# ------------------- 9. Convenzione e frame di Horizons (verifica offline)
def _local_altaz(frame_name, target, times_utc):
    """Azimut/elevazione apparenti a Shackleton da DE421 + orientazione lunare."""
    from datetime import datetime
    from skyfield.api import load, load_file
    from skyfield.planetarylib import PlanetaryConstants

    ts = load.timescale(builtin=True)
    eph = load_file(str(DE421))
    pc = PlanetaryConstants()
    with open(KERNELS / "moon_080317.tf", "rb") as f:
        pc.read_text(f)
    with open(KERNELS / "pck00008.tpc", "rb") as f:
        pc.read_text(f)
    pc.read_binary(open(KERNELS / "moon_pa_de421_1900-2050.bpc", "rb"))
    place = eph["moon"] + pc.build_latlon_degrees(
        pc.build_frame_named(frame_name), SHACK_LAT, SHACK_LON)
    az, el = [], []
    for iso in times_utc:
        alt, a, _ = place.at(ts.from_datetime(datetime.fromisoformat(iso))) \
            .observe(eph[target]).apparent().altaz()
        az.append(a.degrees)
        el.append(alt.degrees)
    return np.array(az), np.array(el)


def _wrap(a):
    return (np.asarray(a) + 180.0) % 360.0 - 180.0


@needs_spice
@pytest.mark.parametrize("name,target", [("Sun", "sun"), ("Earth", "earth")])
def test_horizons_azimuth_is_clockwise_from_north_in_moon_me(name, target):
    """Le osservazioni Horizons salvate coincidono con il calcolo locale nel
    frame MOON_ME_DE421 (lo stesso del DEM LOLA) con azimut orario da nord."""
    fixture = json.loads(HORIZONS_FIXTURE.read_text(encoding="utf-8"))
    assert (fixture["request"]["latitude_deg"],
            fixture["request"]["longitude_east_deg"]) == (SHACK_LAT, SHACK_LON)
    rows = fixture["observations"][name]
    times = [r["time_utc"] for r in rows]
    h_az = np.array([r["azimuth_deg"] for r in rows])
    h_el = np.array([r["elevation_deg"] for r in rows])

    me_az, me_el = _local_altaz("MOON_ME_DE421", target, times)
    assert np.abs(_wrap(h_az - me_az)).max() < 1e-3
    assert np.abs(h_el - me_el).max() < 1e-3

    # Il frame PA differisce in modo misurabile: Horizons non lo usa.
    pa_az, _ = _local_altaz("MOON_PA_DE421", target, times)
    assert np.abs(_wrap(h_az - pa_az)).max() > 0.01
    # Convenzioni alternative escluse (antioraria, da sud).
    assert np.abs(_wrap(h_az - (360.0 - me_az))).max() > 10.0
    assert np.abs(_wrap(h_az - (me_az + 180.0))).max() > 170.0


@needs_spice
def test_horizons_sun_samples_cover_full_azimuth_circle():
    rows = json.loads(HORIZONS_FIXTURE.read_text("utf-8"))["observations"]["Sun"]
    sectors = {int(r["azimuth_deg"] // 45) % 8 for r in rows}
    assert sectors == set(range(8))
