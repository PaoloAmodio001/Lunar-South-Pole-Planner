"""Coerenza geografica tra sito dichiarato e raster di terreno."""
import json
import math
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

import src.mission_orchestrator as orchestrator
from src.astronomy import SITES
from src.lunar_geometry import SiteIdentityError, validate_site_in_raster
from src.mission_orchestrator import validate_mission_site_identity


SOUTH_POLAR_STEREO = (
    "+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +x_0=0 +y_0=0 "
    "+R=1737400 +units=m +no_defs"
)
LOLA = Path("data/terrain/official-lola")
SITE01 = LOLA / "Site01_final_adj_5mpp_surf.tif"
SITE04 = LOLA / "Site04_final_adj_5mpp_surf.tif"
SITE06 = LOLA / "Site06_final_adj_5mpp_surf.tif"
needs_real = pytest.mark.skipif(
    not (SITE01.is_file() and SITE04.is_file() and SITE06.is_file()),
    reason="DEM LOLA reali non disponibili",
)
SHACK_LAT, SHACK_LON = SITES["Shackleton"]
RIDGE_LAT, RIDGE_LON = SITES["Connecting Ridge"]


def make_raster(path, left=-2000.0, top=-6000.0, size=400, res=5.0,
                crs=SOUTH_POLAR_STEREO):
    """Piccolo raster attorno a Shackleton (x≈-1000, y≈-7000)."""
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=1,
        dtype="float32", crs=crs, transform=from_origin(left, top, res, res),
        nodata=np.nan,
    ) as ds:
        ds.write(np.zeros((size, size), dtype="float32"), 1)
    return path


def polar_stereo_xy(lat_deg, lon_deg, radius=1_737_400.0):
    """Formula sferica della stereografica polare sud (lat_ts = -90°)."""
    rho = 2 * radius * math.tan(math.radians(45 + lat_deg / 2))
    lon = math.radians(lon_deg)
    return rho * math.sin(lon), rho * math.cos(lon)


# --------------------------------------------------- 1. Shackleton ↔ Site04
@needs_real
def test_shackleton_is_at_center_of_site04():
    check = validate_site_in_raster("Shackleton", SHACK_LAT, SHACK_LON, SITE04)
    assert check["status"] == "inside_raster"
    assert (check["row"], check["col"]) == (1600, 1599)
    assert check["distance_from_raster_center_m"] < 5.0


@needs_real
@pytest.mark.parametrize("site,dem", [
    ("Connecting Ridge", SITE01), ("Shackleton", SITE04), ("Nobile", SITE06),
])
def test_each_site_matches_its_readme_dem(site, dem):
    lat, lon = SITES[site]
    check = validate_site_in_raster(site, lat, lon, dem)
    assert check["distance_from_raster_center_m"] < 5.0


# ---------------------------------------- 2. Connecting Ridge fuori da Site04
@needs_real
def test_connecting_ridge_outside_site04_is_explicit_error():
    with pytest.raises(SiteIdentityError,
                       match="'Connecting Ridge'.*fuori dall'estensione"):
        validate_site_in_raster("Connecting Ridge", RIDGE_LAT, RIDGE_LON, SITE04)


def test_site_outside_synthetic_raster(tmp_path):
    dem = make_raster(tmp_path / "dem.tif")
    with pytest.raises(SiteIdentityError, match="incompatibili"):
        validate_site_in_raster("Connecting Ridge", RIDGE_LAT, RIDGE_LON, dem)


# --------------------------------------------- 3. Trasformazione corretta
@pytest.mark.parametrize("site", list(SITES))
def test_transform_matches_spherical_formula(tmp_path, site):
    lat, lon = SITES[site]
    x_ref, y_ref = polar_stereo_xy(lat, lon)
    # Il sito cade al centro del pixel (200, 200), lontano dai bordi.
    dem = make_raster(tmp_path / "dem.tif", left=x_ref - 1002.5, top=y_ref + 1002.5)
    check = validate_site_in_raster(site, lat, lon, dem)
    assert check["x_m"] == pytest.approx(x_ref, abs=1e-3)
    assert check["y_m"] == pytest.approx(y_ref, abs=1e-3)
    assert (check["row"], check["col"]) == (200, 200)


def test_shackleton_projected_coordinates(tmp_path):
    check = validate_site_in_raster(
        "Shackleton", SHACK_LAT, SHACK_LON, make_raster(tmp_path / "d.tif"))
    assert check["x_m"] == pytest.approx(-1000.0, abs=1.0)
    assert check["y_m"] == pytest.approx(-7000.3, abs=1.0)


# ------------------------------------ 4. Coordinate non trasformabili
def test_raster_without_crs_is_rejected(tmp_path):
    dem = make_raster(tmp_path / "nocrs.tif", crs=None)
    with pytest.raises(SiteIdentityError, match="Trasformazione non disponibile"):
        validate_site_in_raster("Shackleton", SHACK_LAT, SHACK_LON, dem)


@pytest.mark.parametrize("crs", ["EPSG:3857", "EPSG:4326",
                                 SOUTH_POLAR_STEREO.replace("1737400", "1738100")])
def test_non_lunar_or_unprojected_crs_is_rejected(tmp_path, crs):
    dem = make_raster(tmp_path / "earth.tif", crs=crs)
    with pytest.raises(SiteIdentityError, match="non verificabile"):
        validate_site_in_raster("Shackleton", SHACK_LAT, SHACK_LON, dem)


@pytest.mark.parametrize("lat,lon", [(95.0, 0.0), (math.nan, 0.0), (-89.0, 720.0)])
def test_invalid_coordinates_are_rejected(tmp_path, lat, lon):
    dem = make_raster(tmp_path / "d.tif")
    with pytest.raises(SiteIdentityError, match="non riuscita"):
        validate_site_in_raster("X", lat, lon, dem)


def test_missing_raster(tmp_path):
    with pytest.raises(FileNotFoundError):
        validate_site_in_raster("Shackleton", SHACK_LAT, SHACK_LON,
                                tmp_path / "missing.tif")


# ------------------------------- 5. Configurazione sito/DEM incompatibili
def test_mission_report_site_incompatible_with_dem(tmp_path):
    dem = make_raster(tmp_path / "dem.tif")
    config = {
        "site_selection": {"dem_path": str(dem)},
        "mission_report": {"site_name": "Connecting Ridge"},
    }
    with pytest.raises(SiteIdentityError,
                       match=r"\[site_selection.dem_path\].*Connecting Ridge"):
        validate_mission_site_identity(config)


def test_declared_sites_must_agree(tmp_path):
    config = {
        "astronomy": {"enabled": True, "site": "Shackleton"},
        "mission_report": {"site_name": "Connecting Ridge"},
    }
    with pytest.raises(SiteIdentityError, match="Siti dichiarati incoerenti"):
        validate_mission_site_identity(config)


def test_every_active_raster_is_checked(tmp_path):
    near = make_raster(tmp_path / "near.tif")
    far = make_raster(tmp_path / "far.tif", left=50_000, top=50_000)
    config = {
        "rover_path": {"dem_path": str(near)},
        "lola_lroc_quality": {"lola_path": str(near), "lroc_path": str(far)},
        "mission_report": {"site_name": "Shackleton"},
    }
    with pytest.raises(SiteIdentityError, match=r"\[lola_lroc_quality.lroc_path\]"):
        validate_mission_site_identity(config)


def test_case_variants_cannot_bypass_check(tmp_path):
    dem = make_raster(tmp_path / "dem.tif")
    config = {"site_selection": {"dem_path": str(dem)},
              "mission_report": {"site_name": "  connecting   RIDGE "}}
    with pytest.raises(SiteIdentityError):
        validate_mission_site_identity(config)


def test_disabled_sections_are_ignored(tmp_path):
    far = make_raster(tmp_path / "far.tif", left=50_000, top=50_000)
    near = make_raster(tmp_path / "near.tif")
    config = {
        "site_selection": {"dem_path": str(near)},
        "horizon_analysis": {"enabled": False, "dem_path": str(far)},
        "local_site_analysis": {"enabled": False, "site_name": "Nobile",
                                "dem_path": str(far)},
        "mission_report": {"site_name": "Shackleton"},
    }
    summary = validate_mission_site_identity(config)
    assert summary["status"] == "validated"
    assert [r["source"] for r in summary["rasters_checked"]] == [
        "site_selection.dem_path"]


# ----------------------------------- 6. Blocco dell'astronomia
@pytest.fixture
def horizons_calls(monkeypatch):
    calls = []

    def fake_query(target, latitude, longitude, start_utc, hours=48, step="1h"):
        calls.append((target, latitude, longitude))
        return []

    monkeypatch.setattr(orchestrator, "query_observations", fake_query)
    return calls


def _write_config(tmp_path, config):
    path = tmp_path / "mission_config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


@pytest.mark.parametrize("site_cfg", [
    {"site": "Connecting Ridge"},
    {},  # default storico: Connecting Ridge
])
def test_astronomy_blocked_when_site_outside_dem(tmp_path, horizons_calls, site_cfg):
    dem = make_raster(tmp_path / "dem.tif")
    out = tmp_path / "out"
    config = _write_config(tmp_path, {
        "output_dir": str(out),
        "astronomy": {"enabled": True, "hours": 2, **site_cfg},
        "site_selection": {"dem_path": str(dem), "radius_pixels": 2},
    })
    with pytest.raises(SiteIdentityError, match="Connecting Ridge"):
        orchestrator.run_mission_workflow(config)
    assert horizons_calls == []
    assert not out.exists()


def test_astronomy_with_unknown_site_and_dem_is_blocked(tmp_path, horizons_calls):
    dem = make_raster(tmp_path / "dem.tif")
    config = _write_config(tmp_path, {
        "output_dir": str(tmp_path / "out"),
        "astronomy": {"enabled": True, "site": "Sito Inventato"},
        "rover_path": {"dem_path": str(dem)},
    })
    with pytest.raises(SiteIdentityError, match="non ha coordinate note"):
        orchestrator.run_mission_workflow(config)
    assert horizons_calls == []


def test_cli_returns_configuration_error(tmp_path, horizons_calls, monkeypatch, capsys):
    dem = make_raster(tmp_path / "dem.tif")
    config = _write_config(tmp_path, {
        "output_dir": str(tmp_path / "out"),
        "astronomy": {"enabled": True, "site": "Connecting Ridge"},
        "site_selection": {"dem_path": str(dem)},
    })
    monkeypatch.setattr("sys.argv", ["mission_orchestrator", str(config)])
    assert orchestrator.main() == 2
    assert "SiteIdentityError" in capsys.readouterr().out
    assert horizons_calls == []


def test_astronomy_runs_with_coherent_site(tmp_path, horizons_calls):
    dem = make_raster(tmp_path / "dem.tif")
    config = _write_config(tmp_path, {
        "output_dir": str(tmp_path / "out"),
        "astronomy": {"enabled": True, "site": "Shackleton", "hours": 2,
                      "start_utc": "2026-10-25T00:00:00+00:00"},
        "rover_path": {"dem_path": str(dem), "start_rc": [10, 10],
                       "goal_rc": [12, 12]},
        "mission_report": {"site_name": "Shackleton"},
    })
    result = orchestrator.run_mission_workflow(config)
    assert {c[0] for c in horizons_calls} == {"10", "399"}
    assert all((c[1], c[2]) == (SHACK_LAT, SHACK_LON) for c in horizons_calls)
    assert result["site_identity"]["status"] == "validated"
    assert result["site_identity"]["site"] == "Shackleton"


# ------------------------------- 7. Configurazioni valide non interessate
@pytest.mark.parametrize("config", [
    {},
    {"astronomy": {"enabled": True, "site": "Shackleton"}},        # senza DEM
    {"astronomy": {"enabled": True, "site": "Connecting Ridge"}},  # senza DEM
    {"mission_report": {"site_name": "Shackleton"}},
    {"mission_report": {"site_name": "Candidato provvisorio"},     # etichetta libera
     "site_selection": {"dem_path": "non/usato.tif"}},
    {"astronomy": {"enabled": False, "site": "Nobile"},
     "mission_report": {"enabled": False, "site_name": "Nobile"},
     "site_selection": {"dem_path": "non/usato.tif"}},
])
def test_configs_without_geographic_conflict_pass(config):
    assert validate_mission_site_identity(config)["status"] == "not_applicable"


@needs_real
def test_example_config_is_geographically_coherent():
    config = json.loads(Path("mission_config.example.json").read_text("utf-8"))
    summary = validate_mission_site_identity(config)
    assert summary["status"] == "validated"
    assert summary["site"] == "Shackleton"
    assert {r["source"] for r in summary["rasters_checked"]} == {
        "site_selection.dem_path", "rover_path.dem_path",
        "descent_hazard_detection.dem_path", "lola_lroc_quality.lola_path",
        "lola_lroc_quality.lroc_path",
    }
    geometry = config["lunar_geometry"]
    assert (geometry["latitude_deg"], geometry["longitude_east_deg"]) == SITES["Shackleton"]


@needs_real
def test_previous_example_config_is_now_rejected():
    backup = sorted(Path("backups").glob(
        "site-identity-validation-*/mission_config.example.json"))
    if not backup:
        pytest.skip("backup della configurazione precedente non disponibile")
    config = json.loads(backup[0].read_text("utf-8"))
    with pytest.raises(SiteIdentityError, match="Connecting Ridge"):
        validate_mission_site_identity(config)
