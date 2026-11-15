"""Effemeridi locali (Skyfield/SPICE) contro Horizons registrato, finestre di luce e contatto."""
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.astronomy import SITES, Observation
from src.contact_windows import _windows, compute_windows, horizon_at, load_horizon
from src.ephemeris_validation import compare
from src.local_ephemeris import LocalEphemerisError, light_time_s, observe

FIXTURE = Path("tests/data/horizons_three_sites_20261115.json")
KERNELS_PRESENT = Path("de421.bsp").is_file() and Path("data/terrain/kernels/moon_pa_de421_1900-2050.bpc").is_file()
needs_kernels = pytest.mark.skipif(not KERNELS_PRESENT, reason="kernel SPICE assenti")


@needs_kernels
@pytest.mark.parametrize("key", sorted(json.loads(FIXTURE.read_text())["series"]))
def test_local_ephemeris_matches_recorded_horizons(key):
    site, target = key.split(":")
    lat, lon = SITES[site]
    reference = [Observation(**row) for row in json.loads(FIXTURE.read_text())["series"][key]]
    times = [datetime.fromisoformat(o.time_utc) for o in reference]
    local = observe("sun" if target == "Sun" else "earth", lat, lon, times)
    stats = compare(reference, local)
    assert stats["samples"] == len(reference)
    assert stats["elevation_deg"]["max_abs"] < 1e-3
    assert stats["azimuth_deg"]["max_abs"] < 1e-3
    assert stats["distance_rel"]["max_abs"] < 1e-6


@needs_kernels
def test_light_time_is_earth_moon_distance_over_c():
    lat, lon = SITES["Shackleton"]
    earth = observe("earth", lat, lon, [datetime(2026, 11, 15, tzinfo=timezone.utc)])[0]
    assert 1.18 < light_time_s(earth.distance_au) < 1.37


@needs_kernels
def test_outside_the_orientation_kernel_is_refused():
    with pytest.raises(LocalEphemerisError):
        observe("sun", -89.0, 0.0, [datetime(2051, 1, 1, tzinfo=timezone.utc)])


def test_naive_times_are_refused():
    with pytest.raises(ValueError):
        observe("sun", -89.0, 0.0, [datetime(2026, 1, 1)])


def test_windows_group_consecutive_samples():
    times = [f"t{i}" for i in range(6)]
    found = _windows(times, [False, True, True, False, True, True], 60)
    assert [(w["start_utc"], w["end_utc"], w["duration_h"]) for w in found] == [("t1", "t2", 1.0), ("t4", "t5", 1.0)]
    assert found[1]["open_at_end_of_series"]


def _flat_horizon(path: Path, elevation: float) -> Path:
    samples = [{"grid_azimuth_deg": a, "horizon_elevation_deg": elevation} for a in range(0, 360, 10)]
    path.write_text(json.dumps({"samples": samples, "observer": {}}))
    return path


def test_horizon_interpolation_wraps_around_north(tmp_path):
    samples = [{"grid_azimuth_deg": a, "horizon_elevation_deg": (5.0 if a == 350 else 1.0)} for a in range(0, 360, 10)]
    path = tmp_path / "h.json"
    path.write_text(json.dumps({"samples": samples}))
    az, el, _ = load_horizon(path)
    assert horizon_at(az, el, 355.0) == pytest.approx(3.0)
    assert horizon_at(az, el, -5.0) == pytest.approx(3.0)


@needs_kernels
def test_flat_horizon_makes_visibility_equal_to_positive_elevation(tmp_path):
    lat, lon = SITES["Nobile"]
    result = compute_windows(_flat_horizon(tmp_path / "flat.json", 0.0), 37.0, lat, lon,
                             datetime(2026, 11, 15, tzinfo=timezone.utc), 72, 120)
    for row in result["samples"]:
        assert row["sun_visible"] == (row["sun_elevation_deg"] > 0)
        assert row["earth_visible"] == (row["earth_elevation_deg"] > 0)
        assert row["contact"] == row["earth_visible"]


@needs_kernels
def test_a_link_that_does_not_close_removes_contact(tmp_path):
    lat, lon = SITES["Nobile"]
    weak = {"frequency_ghz": 8.4, "transmit_power_dbm": 0.0, "transmit_antenna_gain_dbi": 0.0,
            "receive_antenna_gain_dbi": 0.0, "system_losses_db": 0.0, "receiver_sensitivity_dbm": -100.0}
    result = compute_windows(_flat_horizon(tmp_path / "flat.json", -90.0), 37.0, lat, lon,
                             datetime(2026, 11, 15, tzinfo=timezone.utc), 24, 120, link=weak)
    assert result["summary"]["contact_fraction"] == 0.0
    assert all(row["link_margin_db"] < 0 for row in result["samples"])


@needs_kernels
def test_a_high_horizon_blocks_everything(tmp_path):
    lat, lon = SITES["Shackleton"]
    result = compute_windows(_flat_horizon(tmp_path / "wall.json", 45.0), 188.13, lat, lon,
                             datetime(2026, 11, 15, tzinfo=timezone.utc), 48, 120)
    assert result["summary"]["sun_visible_fraction"] == 0.0
    assert result["illumination_windows"] == [] and result["contact_windows"] == []
