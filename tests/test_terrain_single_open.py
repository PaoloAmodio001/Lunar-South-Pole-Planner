"""DEM aperto una sola volta: invarianza numerica e ciclo di vita dei dataset.

``legacy_analyze_local_terrain`` è la copia letterale dell'implementazione
precedente (backups/terrain-single-open-20261114-211112/src/terrain_metrics.py)
ed è il riferimento per il confronto numerico.
"""
from datetime import datetime, timezone
from pathlib import Path
import inspect
import json

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

import src.site_selection as site_selection
from src.site_assessment import assess_candidate
from src.terrain_metrics import LocalTerrainMetrics, analyze_local_terrain
from src.site_selection import select_candidate_sites


REAL_DEM = Path("data/terrain/official-lola/Site04_final_adj_5mpp_surf.tif")
REAL_LDEC = Path("data/terrain/official-lola/Site04_final_adj_5mpp_ldec.tif")
REAL_TOTERR = Path("data/terrain/official-lola/Site04_final_adj_5mpp_toterr.tif")
TRANSFORM = from_origin(-150.0, 150.0, 5, 5)


# ---------------------------------------------------------------------------
# Implementazione precedente (riferimento, copia letterale: non modificare)
# ---------------------------------------------------------------------------
def legacy_analyze_local_terrain(raster_path, center_row: int, center_col: int, radius_pixels: int = 10) -> LocalTerrainMetrics:
    path = Path(raster_path)
    if radius_pixels < 2 or radius_pixels > 250:
        raise ValueError("radius_pixels deve essere compreso tra 2 e 250.")
    with rasterio.open(path) as ds:
        row, col = int(center_row), int(center_col)
        if not (0 <= row < ds.height and 0 <= col < ds.width):
            raise ValueError(f"Centro fuori raster: riga 0..{ds.height-1}, colonna 0..{ds.width-1}.")
        r0, r1 = max(0, row-radius_pixels), min(ds.height, row+radius_pixels+1)
        c0, c1 = max(0, col-radius_pixels), min(ds.width, col+radius_pixels+1)
        arr = ds.read(1, window=((r0,r1),(c0,c1)), masked=True).astype(np.float64)
        z = np.asarray(arr.filled(np.nan), dtype=float)
        if ds.nodata is not None:
            z[np.isclose(z, ds.nodata, equal_nan=True)] = np.nan
        z[~np.isfinite(z)] = np.nan
        valid = np.isfinite(z)
        count = int(valid.sum()); total = int(z.size)
        px, py = abs(float(ds.transform.a)), abs(float(ds.transform.e))
        cr, cc = row-r0, col-c0
        center = float(z[cr,cc]) if np.isfinite(z[cr,cc]) else None
        if count < 9:
            raise ValueError(f"Copertura valida insufficiente nella finestra: {count}/{total} pixel.")
        # Derivatives use local metric pixel spacing. Fill holes only for gradient calculation;
        # valid-only gradient cells are then retained for statistics.
        filled = z.copy()
        med = float(np.nanmedian(filled))
        filled[~np.isfinite(filled)] = med
        dz_drow, dz_dcol = np.gradient(filled, py, px)
        slope = np.degrees(np.arctan(np.hypot(dz_dcol, dz_drow)))
        # Least-squares plane residuals provide a scale-aware local roughness measure.
        rr, cc_grid = np.indices(z.shape)
        x = (cc_grid-(cc-0))*px
        y = -(rr-(cr-0))*py
        good = valid
        design = np.column_stack([x[good], y[good], np.ones(count)])
        coeff, *_ = np.linalg.lstsq(design, z[good], rcond=None)
        residual = z[good] - design @ coeff
        local_slopes = slope[good]
        center_slope = float(slope[cr,cc]) if valid[cr,cc] else None
        return LocalTerrainMetrics(
            raster_path=str(path), center_row=row, center_col=col, radius_pixels=radius_pixels,
            window_shape=tuple(map(int,z.shape)), valid_pixels=count, total_pixels=total,
            valid_fraction=count/total, pixel_size_x_m=px, pixel_size_y_m=py,
            center_elevation_m=center, slope_at_center_deg=center_slope,
            slope_median_deg=float(np.median(local_slopes)),
            slope_p95_deg=float(np.percentile(local_slopes,95)),
            roughness_plane_residual_std_m=float(np.std(residual)),
            generated_utc=datetime.now(timezone.utc).isoformat(),
        )


# ---------------------------------------------------------------------------
# Supporto
# ---------------------------------------------------------------------------

def make_raster(path, data, dtype="float32", nodata=np.nan, transform=TRANSFORM):
    data = np.asarray(data)
    with rasterio.open(
        path, "w", driver="GTiff", height=data.shape[0], width=data.shape[1],
        count=1, dtype=dtype, crs="EPSG:3857", transform=transform, nodata=nodata,
    ) as ds:
        ds.write(data.astype(dtype), 1)
    return path


def synthetic_dem():
    rng = np.random.default_rng(20261114)
    rows, cols = np.indices((60, 60))
    # Pendenza crescente verso est: candidati eleggibili a ovest, oltre
    # soglia a est; rumore modesto per rugosità non banale.
    z = (0.05 * rows + 0.02 * cols ** 2 + 0.5 * np.sin(rows / 5.0)
         + rng.normal(0.0, 0.05, (60, 60)))
    z[10:13, 40:44] = np.nan          # buco interno
    z[50:, :6] = np.nan               # angolo senza dati
    return z


def comparable(metrics):
    data = metrics.to_dict()
    data.pop("generated_utc")
    return data


def outcome(fn, raster, row, col, radius):
    """Risultato confrontabile oppure (tipo, messaggio) dell'eccezione."""
    try:
        return comparable(fn(raster, row, col, radius))
    except Exception as exc:  # noqa: BLE001 - confronto del comportamento
        return (type(exc).__name__, str(exc))


SYNTH_POINTS = [
    (r, c, rad)
    for rad in (2, 3, 5, 10)
    for r, c in [(0, 0), (0, 59), (59, 0), (59, 59), (30, 30), (11, 41),
                 (55, 2), (52, 5), (1, 30), (30, 58), (17, 23), (44, 9)]
] + [(30, 30, 1), (30, 30, 251), (60, 0, 3), (-1, 5, 3), (5, 60, 3)]


@pytest.fixture
def synth(tmp_path):
    return make_raster(tmp_path / "dem.tif", synthetic_dem())


@pytest.fixture
def synth_int_nodata(tmp_path):
    z = np.nan_to_num(synthetic_dem() * 10, nan=-9999).astype("int16")
    return make_raster(tmp_path / "dem_i16.tif", z, dtype="int16", nodata=-9999)


@pytest.fixture
def dem_opens(monkeypatch):
    """Traccia ogni dataset aperto via rasterio.open (tutti i moduli)."""
    opened = []
    original = rasterio.open

    def tracking(path, *args, **kwargs):
        ds = original(path, *args, **kwargs)
        opened.append(ds)
        return ds

    monkeypatch.setattr(rasterio, "open", tracking)
    return opened


def lola_rasters(tmp_path):
    return {
        "lola_density_path": make_raster(tmp_path / "ldec.tif", np.ones((60, 60))),
        "lola_error_path": make_raster(tmp_path / "toterr.tif",
                                       np.full((60, 60), 0.5)),
    }


# ---------------------------------------------------------------------------
# 1-2. Confronto numerico vecchia/nuova implementazione su più finestre
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fixture_name", ["synth", "synth_int_nodata"])
def test_path_api_identical_to_legacy(request, fixture_name):
    dem = request.getfixturevalue(fixture_name)
    for row, col, rad in SYNTH_POINTS:
        for raster in (dem, str(dem)):
            assert (outcome(analyze_local_terrain, raster, row, col, rad)
                    == outcome(legacy_analyze_local_terrain, raster, row, col, rad)), \
                (row, col, rad)


@pytest.mark.parametrize("fixture_name", ["synth", "synth_int_nodata"])
def test_open_dataset_api_identical_to_legacy(request, fixture_name):
    dem = request.getfixturevalue(fixture_name)
    successes = 0
    with rasterio.open(dem) as ds:
        for row, col, rad in SYNTH_POINTS:
            new = outcome(analyze_local_terrain, ds, row, col, rad)
            old = outcome(legacy_analyze_local_terrain, dem, row, col, rad)
            if isinstance(new, dict):
                successes += 1
                # Unica differenza ammessa: l'etichetta è il nome del dataset.
                assert new.pop("raster_path") == ds.name
                old.pop("raster_path")
            assert new == old, (row, col, rad)
        assert not ds.closed
    assert successes >= 40


@pytest.mark.skipif(not REAL_DEM.is_file(), reason="DEM Site04 non disponibile")
def test_real_dem_windows_identical_to_legacy():
    rng = np.random.default_rng(7)
    with rasterio.open(REAL_DEM) as ds:
        points = [(int(r), int(c)) for r, c in zip(
            rng.integers(0, ds.height, 40), rng.integers(0, ds.width, 40))]
        points += [(0, 0), (ds.height - 1, ds.width - 1), (1600, 1600)]
        for row, col in points:
            for rad in (2, 10, 25):
                new = outcome(analyze_local_terrain, ds, row, col, rad)
                old = outcome(legacy_analyze_local_terrain, REAL_DEM, row, col, rad)
                if isinstance(new, dict):
                    new.pop("raster_path")
                    old.pop("raster_path")
                assert new == old, (row, col, rad)


# ---------------------------------------------------------------------------
# 3. Punteggi e graduatoria identici
# ---------------------------------------------------------------------------

def _legacy_terrain_reopening(ds_or_path, row, col, radius):
    """Vecchio percorso: riapre il raster per ogni candidato."""
    path = ds_or_path.name if hasattr(ds_or_path, "read") else ds_or_path
    return legacy_analyze_local_terrain(path, row, col, radius)


def _strip_volatile(result):
    result = dict(result)
    result.pop("generated_utc")
    result.pop("output_path")
    return result


@pytest.mark.parametrize("with_lola", [False, True])
def test_ranking_and_scores_identical_to_legacy(tmp_path, synth, monkeypatch,
                                                with_lola):
    lola = lola_rasters(tmp_path) if with_lola else {}
    kwargs = dict(radius_pixels=3, target_candidates=120, top_n=500, **lola)
    new = select_candidate_sites(synth, output_path=tmp_path / "n.json", **kwargs)
    monkeypatch.setattr(site_selection, "analyze_local_terrain",
                        _legacy_terrain_reopening)
    old = select_candidate_sites(synth, output_path=tmp_path / "o.json", **kwargs)

    assert new["eligible_count"] > 0 and new["rejected_count"] > 0
    assert _strip_volatile(new) == _strip_volatile(old)


@pytest.mark.skipif(not REAL_DEM.is_file(), reason="DEM Site04 non disponibile")
def test_real_dem_ranking_identical_to_legacy(tmp_path, monkeypatch):
    kwargs = dict(radius_pixels=10, target_candidates=150, top_n=1000,
                  lola_density_path=REAL_LDEC, lola_error_path=REAL_TOTERR)
    new = select_candidate_sites(REAL_DEM, output_path=tmp_path / "n.json", **kwargs)
    monkeypatch.setattr(site_selection, "analyze_local_terrain",
                        _legacy_terrain_reopening)
    old = select_candidate_sites(REAL_DEM, output_path=tmp_path / "o.json", **kwargs)
    assert new["eligible_count"] > 0
    assert _strip_volatile(new) == _strip_volatile(old)


# ---------------------------------------------------------------------------
# 4. Compatibilità delle chiamate esistenti
# ---------------------------------------------------------------------------

def test_signature_is_backward_compatible():
    params = inspect.signature(analyze_local_terrain).parameters
    assert list(params) == ["raster_path", "center_row", "center_col",
                            "radius_pixels"]
    assert params["radius_pixels"].default == 10


def test_existing_call_styles(synth):
    expected = comparable(legacy_analyze_local_terrain(synth, 30, 30))
    assert comparable(analyze_local_terrain(synth, 30, 30)) == expected
    assert comparable(analyze_local_terrain(str(synth), 30, 30, 10)) == expected
    assert comparable(analyze_local_terrain(
        raster_path=synth, center_row=30, center_col=30,
        radius_pixels=10)) == expected
    result = analyze_local_terrain(synth, 30, 30)
    assert isinstance(result, LocalTerrainMetrics)
    assert result.raster_path == str(synth)
    json.dumps(result.to_dict())


def test_site_assessment_caller_still_works(synth):
    assessment = assess_candidate(
        candidate_name="c", dem_path=synth, row=30, col=30, radius_pixels=5,
        sun_elevations_deg=[1.0, -1.0], earth_elevations_deg=[2.0, 3.0],
    )
    legacy = legacy_analyze_local_terrain(synth, 30, 30, 5)
    assert assessment.terrain_metrics["slope_p95_deg"] == legacy.slope_p95_deg
    assert (assessment.terrain_metrics["roughness_plane_residual_std_m"]
            == legacy.roughness_plane_residual_std_m)


# ---------------------------------------------------------------------------
# 5. Eccezioni e chiusura dei dataset
# ---------------------------------------------------------------------------

def test_path_api_closes_dataset_on_error(synth, dem_opens):
    with pytest.raises(ValueError, match="Centro fuori raster"):
        analyze_local_terrain(synth, 999, 999, 3)
    assert len(dem_opens) == 1 and dem_opens[0].closed


def test_caller_owned_dataset_is_never_closed(synth):
    with rasterio.open(synth) as ds:
        with pytest.raises(ValueError, match="Centro fuori raster"):
            analyze_local_terrain(ds, 999, 999, 3)
        with pytest.raises(ValueError, match="radius_pixels"):
            analyze_local_terrain(ds, 30, 30, 1)
        assert not ds.closed
        analyze_local_terrain(ds, 30, 30, 3)  # ancora utilizzabile
        assert not ds.closed


def test_closed_dataset_is_rejected(synth):
    with rasterio.open(synth) as ds:
        pass
    with pytest.raises(ValueError, match="già chiuso"):
        analyze_local_terrain(ds, 30, 30, 3)


def test_selection_closes_dem_on_success_and_failure(tmp_path, synth,
                                                     dem_opens, monkeypatch):
    select_candidate_sites(synth, output_path=tmp_path / "ok.json",
                           radius_pixels=3, target_candidates=20)
    assert dem_opens and all(ds.closed for ds in dem_opens)

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt  # non intercettato dal ciclo dei candidati

    monkeypatch.setattr(site_selection, "analyze_local_terrain", interrupted)
    with pytest.raises(KeyboardInterrupt):
        select_candidate_sites(synth, output_path=tmp_path / "ko.json",
                               radius_pixels=3, target_candidates=20)
    assert all(ds.closed for ds in dem_opens)
    assert not (tmp_path / "ko.json").exists()


def test_selection_closes_dem_on_lola_misalignment(tmp_path, synth, dem_opens):
    ldec = make_raster(tmp_path / "ldec.tif", np.ones((60, 60)),
                       transform=from_origin(0, 0, 5, 5))
    toterr = make_raster(tmp_path / "toterr.tif", np.ones((60, 60)))
    with pytest.raises(ValueError, match="LDEC non allineato"):
        select_candidate_sites(synth, output_path=tmp_path / "x.json",
                               radius_pixels=3, lola_density_path=ldec,
                               lola_error_path=toterr)
    assert dem_opens and all(ds.closed for ds in dem_opens)


def test_terrain_error_still_rejects_candidate_locally(tmp_path):
    z = synthetic_dem()
    z[:, :20] = np.nan  # finestre senza copertura sufficiente
    dem = make_raster(tmp_path / "holes.tif", z)
    result = select_candidate_sites(dem, output_path=tmp_path / "r.json",
                                    radius_pixels=3, target_candidates=60)
    errors = [c for c in result["rejected_candidates"]
              if c["exclusion_reasons"] == ["ANALISI_NON_DISPONIBILE"]]
    assert errors and all("Copertura valida insufficiente" in c["error"]
                          for c in errors)
    assert result["eligible_count"] > 0


# ---------------------------------------------------------------------------
# 6. DEM aperto una sola volta nella selezione completa
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("target_candidates", [4, 50, 400])
@pytest.mark.parametrize("with_lola", [False, True])
def test_dem_opened_once_per_selection(tmp_path, synth, dem_opens,
                                       target_candidates, with_lola):
    lola = lola_rasters(tmp_path) if with_lola else {}
    dem_opens.clear()
    result = select_candidate_sites(synth, output_path=tmp_path / "r.json",
                                    radius_pixels=3,
                                    target_candidates=target_candidates, **lola)
    assert result["sampling"]["evaluated_candidates"] >= 1
    names = [ds.name for ds in dem_opens]
    assert names.count(str(synth)) == 1
    if with_lola:
        assert names.count(str(lola["lola_density_path"])) == 2
        assert names.count(str(lola["lola_error_path"])) == 2
    assert all(ds.closed for ds in dem_opens)
