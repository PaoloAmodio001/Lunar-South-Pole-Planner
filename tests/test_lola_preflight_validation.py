"""Validazione preventiva LDEC/TOTERR e invarianza dello scoring."""
import json
import warnings

import numpy as np
import pytest
import rasterio
from rasterio.errors import NotGeoreferencedWarning
from rasterio.transform import from_origin

import src.lola_local_quality as llq
import src.site_selection as site_selection
from src.lola_local_quality import (
    LolaQualityReader,
    summarize_lola_quality,
    validate_lola_quality_grids,
)
from src.site_selection import select_candidate_sites


TRANSFORM = from_origin(-62.5, 62.5, 5, 5)
SHAPE = (25, 25)


def make_raster(path, data, transform=TRANSFORM, crs="EPSG:3857",
                count=1, dtype="float32"):
    data = np.asarray(data)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotGeoreferencedWarning)
        with rasterio.open(
            path, "w", driver="GTiff",
            height=data.shape[0], width=data.shape[1],
            count=count, dtype=dtype,
            crs=crs, transform=transform, nodata=np.nan,
        ) as ds:
            for band in range(1, count + 1):
                ds.write(data.astype(dtype), band)


def dem_surface():
    rows, cols = np.indices(SHAPE)
    # Pendenza crescente verso destra: produce candidati sia eleggibili
    # sia esclusi per soglia, per verificare entrambi gli elenchi.
    return (rows * 0.1 + (cols ** 2) * 0.04).astype("float32")


@pytest.fixture
def grids(tmp_path):
    dem = tmp_path / "dem.tif"
    density = tmp_path / "ldec.tif"
    error = tmp_path / "toterr.tif"
    make_raster(dem, dem_surface())
    density_data = (np.indices(SHAPE).sum(axis=0) % 4).astype("float32")
    density_data[0, :] = np.nan
    make_raster(density, density_data)
    error_data = np.linspace(0.1, 3.0, SHAPE[0] * SHAPE[1]).reshape(SHAPE)
    make_raster(error, error_data)
    return dem, density, error


def run(dem, out, **kwargs):
    return select_candidate_sites(
        dem, output_path=out, radius_pixels=2,
        target_candidates=36, top_n=100, **kwargs,
    )


@pytest.fixture
def terrain_calls(monkeypatch):
    """Conta le analisi del terreno: 0 significa 'prima del campionamento'."""
    calls = []
    original = site_selection.analyze_local_terrain

    def counting(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(site_selection, "analyze_local_terrain", counting)
    return calls


# ---------------------------------------------------------------- 1
def test_aligned_grids_pass(grids):
    grid = validate_lola_quality_grids(*grids)
    assert (grid.width, grid.height) == (25, 25)
    assert grid.crs == "EPSG:3857"
    assert grid.transform == tuple(TRANSFORM)[:6]


# ---------------------------------------------------------------- 2, 3
@pytest.mark.parametrize("label", ["LDEC", "TOTERR"])
def test_misaligned_aux_raster_fails_before_sampling(
        tmp_path, grids, terrain_calls, label):
    dem, density, error = grids
    target = density if label == "LDEC" else error
    make_raster(target, np.zeros(SHAPE), transform=from_origin(-60, 60, 5, 5))
    out = tmp_path / "ranking.json"

    with pytest.raises(ValueError,
                       match=f"{label} non allineato.*trasformazione"):
        run(dem, out, lola_density_path=density, lola_error_path=error)

    assert terrain_calls == []
    assert not out.exists()


# ---------------------------------------------------------------- 4
def test_different_dimensions_fail(tmp_path, grids, terrain_calls):
    dem, density, error = grids
    make_raster(density, np.zeros((24, 25)))
    with pytest.raises(ValueError, match="LDEC non allineato.*dimensioni"):
        run(dem, tmp_path / "r.json",
            lola_density_path=density, lola_error_path=error)
    assert terrain_calls == []


# ---------------------------------------------------------------- 5
def test_different_crs_fails(tmp_path, grids, terrain_calls):
    dem, density, error = grids
    make_raster(error, np.zeros(SHAPE), crs="EPSG:32633")
    with pytest.raises(ValueError, match="TOTERR non allineato.*CRS"):
        run(dem, tmp_path / "r.json",
            lola_density_path=density, lola_error_path=error)
    assert terrain_calls == []


@pytest.mark.parametrize("which,label", [(0, "DEM"), (1, "LDEC"), (2, "TOTERR")])
def test_missing_crs_fails(tmp_path, grids, which, label):
    paths = list(grids)
    make_raster(paths[which], np.zeros(SHAPE), crs=None)
    with pytest.raises(ValueError, match=f"Raster {label}: CRS assente"):
        validate_lola_quality_grids(*paths)


# ---------------------------------------------------------------- 6
@pytest.mark.parametrize("which,label", [(1, "LDEC"), (2, "TOTERR")])
def test_missing_aux_raster_raises_file_not_found(
        tmp_path, grids, terrain_calls, which, label):
    paths = list(grids)
    paths[which].unlink()
    with pytest.raises(FileNotFoundError, match=f"Raster {label} non trovato"):
        run(paths[0], tmp_path / "r.json",
            lola_density_path=paths[1], lola_error_path=paths[2])
    assert terrain_calls == []


# ---------------------------------------------------------------- 7
def test_multiband_raster_fails(tmp_path, grids, terrain_calls):
    dem, density, error = grids
    make_raster(density, np.zeros(SHAPE), count=2)
    with pytest.raises(ValueError, match="LDEC: attesa una sola banda, trovate 2"):
        run(dem, tmp_path / "r.json",
            lola_density_path=density, lola_error_path=error)
    assert terrain_calls == []


# ---------------------------------------------------------------- 8
@pytest.mark.parametrize("kwargs", [
    {"lola_density_path": "ldec.tif"},
    {"lola_error_path": "toterr.tif"},
])
def test_single_lola_path_is_rejected(tmp_path, grids, terrain_calls, kwargs):
    with pytest.raises(ValueError, match="configurati insieme"):
        run(grids[0], tmp_path / "r.json", **kwargs)
    assert terrain_calls == []


# ---------------------------------------------------------------- 9
def test_without_lola_behaviour_is_unchanged(tmp_path, grids, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("LOLA non deve essere usato senza configurazione")

    monkeypatch.setattr(llq, "validate_lola_quality_grids", forbidden)
    monkeypatch.setattr(site_selection, "LolaQualityReader", forbidden)

    result = run(grids[0], tmp_path / "r.json")
    assert result["eligible_count"] > 0
    assert result["lola_quality_validation"] is None
    assert all("lola_quality" not in c for c in result["top_candidates"])
    assert all("lola_quality" not in c for c in result["rejected_candidates"])


# ---------------------------------------------------------------- 10
def test_local_ldec_toterr_metrics_are_correct(tmp_path):
    dem = tmp_path / "dem.tif"
    density = tmp_path / "ldec.tif"
    error = tmp_path / "toterr.tif"
    make_raster(dem, np.zeros((9, 9)), transform=from_origin(0, 45, 5, 5))

    ldec = np.full((9, 9), 7.0)
    window_ldec = np.array([
        [0, 0, 1, 2, 3],
        [np.nan, 1, 1, 0, 5],
        [4, 4, 0, 1, 2],
        [3, 2, 1, 0, 0],
        [1, 1, 1, -1, 2],   # -1 non valido (negativo)
    ], dtype=float)
    ldec[2:7, 2:7] = window_ldec
    make_raster(density, ldec, transform=from_origin(0, 45, 5, 5))

    toterr = np.full((9, 9), 99.0)
    window_err = np.arange(25, dtype=float).reshape(5, 5) / 10.0
    window_err[0, 0] = np.nan
    window_err[4, 4] = -2.0  # negativo: non valido
    toterr[2:7, 2:7] = window_err
    make_raster(error, toterr, transform=from_origin(0, 45, 5, 5))

    result = summarize_lola_quality(dem, density, error, 4, 4, radius_pixels=2)

    valid_ldec = window_ldec[np.isfinite(window_ldec) & (window_ldec >= 0)]
    assert result["window"] == {
        "row_start": 2, "row_stop_exclusive": 7,
        "col_start": 2, "col_stop_exclusive": 7,
        "radius_pixels": 2, "total_cells": 25,
    }
    assert result["ldec"]["valid_cells"] == valid_ldec.size == 23
    assert result["ldec"]["valid_fraction"] == pytest.approx(23 / 25)
    assert result["ldec"]["zero_return_fraction"] == pytest.approx(
        np.mean(valid_ldec == 0))
    assert result["ldec"]["positive_return_fraction"] == pytest.approx(
        np.mean(valid_ldec > 0))
    assert result["ldec"]["counts_by_return_count"] == {
        str(v): int(np.count_nonzero(valid_ldec == v)) for v in range(6)
    }

    valid_err = window_err[np.isfinite(window_err) & (window_err >= 0)]
    assert result["toterr"]["count"] == valid_err.size == 23
    assert result["toterr"]["median_m"] == pytest.approx(np.median(valid_err))
    assert result["toterr"]["p95_m"] == pytest.approx(np.percentile(valid_err, 95))
    assert result["toterr"]["max_m"] == pytest.approx(valid_err.max())
    assert result["toterr"]["valid_fraction"] == pytest.approx(23 / 25)
    assert result["status"] == "available"


def test_reader_matches_single_call_api(grids):
    with LolaQualityReader(*grids) as reader:
        for row, col in [(2, 2), (12, 12), (22, 5)]:
            assert reader.summarize(row, col, 2) == summarize_lola_quality(
                *grids, row, col, radius_pixels=2)


# ---------------------------------------------------------------- 11
def _strip_lola(candidate):
    return {k: v for k, v in candidate.items() if k != "lola_quality"}


def test_ranking_and_scores_identical_with_and_without_lola(tmp_path, grids):
    dem, density, error = grids
    baseline = run(dem, tmp_path / "base.json")
    enriched = run(dem, tmp_path / "lola.json",
                   lola_density_path=density, lola_error_path=error)

    assert baseline["eligible_count"] > 0
    assert baseline["rejected_count"] > 0  # entrambi i rami esercitati

    assert ([_strip_lola(c) for c in enriched["top_candidates"]]
            == baseline["top_candidates"])
    assert ([_strip_lola(c) for c in enriched["rejected_candidates"]]
            == baseline["rejected_candidates"])
    for key in ("eligible_count", "rejected_count", "terrain_class_summary",
                "sampling", "thresholds", "ranking_method"):
        assert enriched[key] == baseline[key]

    for candidate in enriched["top_candidates"]:
        # Ricalcolo indipendente: solo pendenza (0.60) e rugosità (0.40).
        metrics = candidate["terrain_metrics"]
        slope_term = 1.0 - min(max(metrics["slope_p95_deg"], 0.0) / 15.0, 1.0)
        rough_term = 1.0 - min(
            max(metrics["roughness_plane_residual_std_m"], 0.0) / 5.0, 1.0)
        expected = round(100 * (0.60 * slope_term + 0.40 * rough_term), 2)
        assert candidate["score"]["score_0_100"] == pytest.approx(expected)
        assert set(candidate["score"]["components_0_100"]) == {
            "slope", "roughness"}
        assert candidate["score_scope"] == ["slope", "roughness"]
        assert candidate["lola_quality"]["status"] in {
            "available", "partial_or_missing"}

    validation = enriched["lola_quality_validation"]
    assert validation["status"] == "validated_once_before_sampling"
    assert validation["affects_score"] is False
    json.loads((tmp_path / "lola.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 12
@pytest.fixture
def tracked_open(monkeypatch):
    opened = []
    original = rasterio.open

    def tracking(path, *args, **kwargs):
        ds = original(path, *args, **kwargs)
        opened.append(ds)
        return ds

    monkeypatch.setattr(llq.rasterio, "open", tracking)
    return opened


def test_datasets_closed_after_validation_failure(grids, tracked_open):
    dem, density, error = grids
    make_raster(error, np.zeros(SHAPE), count=3)
    with pytest.raises(ValueError, match="una sola banda"):
        with LolaQualityReader(dem, density, error):
            pytest.fail("il blocco non deve essere eseguito")
    assert tracked_open
    assert all(ds.closed for ds in tracked_open)


def test_datasets_closed_after_exception_in_block(grids, tracked_open):
    with pytest.raises(RuntimeError, match="boom"):
        with LolaQualityReader(*grids) as reader:
            reader.summarize(10, 10, 2)
            assert not reader._density.closed
            raise RuntimeError("boom")
    assert len(tracked_open) == 5  # 3 per la validazione + LDEC + TOTERR
    assert all(ds.closed for ds in tracked_open)


def test_datasets_closed_after_select_candidate_sites(
        tmp_path, grids, tracked_open, monkeypatch):
    def failing(*args, **kwargs):
        raise KeyboardInterrupt  # non intercettato dal ciclo dei candidati

    run(grids[0], tmp_path / "ok.json",
        lola_density_path=grids[1], lola_error_path=grids[2])
    assert all(ds.closed for ds in tracked_open)

    monkeypatch.setattr(site_selection, "analyze_local_terrain", failing)
    with pytest.raises(KeyboardInterrupt):
        run(grids[0], tmp_path / "ko.json",
            lola_density_path=grids[1], lola_error_path=grids[2])
    assert all(ds.closed for ds in tracked_open)


def test_reader_unusable_after_close(grids):
    with LolaQualityReader(*grids) as reader:
        pass
    with pytest.raises(RuntimeError, match="non aperto"):
        reader.summarize(10, 10, 2)


# ------------------------------------------- validazione eseguita una volta
@pytest.mark.parametrize("target_candidates", [4, 36, 400])
def test_alignment_validated_once_per_call(
        tmp_path, grids, monkeypatch, tracked_open, target_candidates):
    calls = []
    original = llq.validate_lola_quality_grids

    def counting(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(llq, "validate_lola_quality_grids", counting)
    dem, density, error = grids

    result = select_candidate_sites(
        dem, output_path=tmp_path / "r.json", radius_pixels=2,
        target_candidates=target_candidates, top_n=5,
        lola_density_path=density, lola_error_path=error,
    )

    assert result["sampling"]["evaluated_candidates"] >= 1
    assert len(calls) == 1
    # Aperture di LDEC e TOTERR indipendenti dal numero di candidati:
    # 1 volta per la validazione + 1 volta per il campionamento.
    # (Le aperture del DEM sono verificate in test_terrain_single_open.py.)
    names = [ds.name for ds in tracked_open]
    assert names.count(str(density)) == 2
    assert names.count(str(error)) == 2
    assert all(ds.closed for ds in tracked_open)


def test_local_lola_error_does_not_reject_candidate(tmp_path, grids, monkeypatch):
    dem, density, error = grids
    baseline = run(dem, tmp_path / "base.json")

    def failing_summary(self, *args, **kwargs):
        raise ValueError("lettura locale non riuscita")

    monkeypatch.setattr(LolaQualityReader, "summarize", failing_summary)
    enriched = run(dem, tmp_path / "lola.json",
                   lola_density_path=density, lola_error_path=error)

    assert ([_strip_lola(c) for c in enriched["top_candidates"]]
            == baseline["top_candidates"])
    assert all(c["lola_quality"] == {"status": "error",
                                     "error": "lettura locale non riuscita"}
               for c in enriched["top_candidates"])
