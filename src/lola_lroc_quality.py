# Last updated: 2026-11-14
"""Confronto diagnostico LOLA-LROC con classificazione PDS3 prudente.

Il confronto viene effettuato sulla griglia LOLA:
- LROC DTM: ricampionamento bilineare;
- CONF PDS3: ricampionamento nearest-neighbour;
- CONF 14: gruppo primario;
- CONF 4: gruppo interpolato, separato;
- CONF 1 e 0: esclusi;
- classi non documentate: gruppo irrisolto separato.

Non certifica co-registrazione fisica, datum verticale o accuratezza assoluta.
Non modifica i raster sorgente.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling


DOCUMENTED_CLASSES = {
    0: "NoData / fuori dal perimetro valido",
    1: "Ombra",
    4: "Interpolato o estrapolato",
    14: "Basato sui risultati dell'image matching",
}

OUTSIDE_CONFIDENCE = -1


def _empty_stats() -> dict:
    return {
        "pixel_count": 0,
        "median_difference_m": None,
        "mean_difference_m": None,
        "mae_m": None,
        "rmse_m": None,
        "p95_absolute_difference_m": None,
        "max_absolute_difference_m": None,
        "absolute_difference_over_10m": 0,
        "absolute_difference_over_50m": 0,
        "absolute_difference_over_100m": 0,
    }


def _stats(delta: np.ndarray, mask: np.ndarray) -> dict:
    values = delta[mask]
    if values.size == 0:
        return _empty_stats()

    absolute = np.abs(values)
    return {
        "pixel_count": int(values.size),
        "median_difference_m": float(np.median(values)),
        "mean_difference_m": float(np.mean(values)),
        "mae_m": float(np.mean(absolute)),
        "rmse_m": float(np.sqrt(np.mean(values ** 2))),
        "p95_absolute_difference_m": float(np.percentile(absolute, 95)),
        "max_absolute_difference_m": float(np.max(absolute)),
        "absolute_difference_over_10m": int(np.count_nonzero(absolute > 10)),
        "absolute_difference_over_50m": int(np.count_nonzero(absolute > 50)),
        "absolute_difference_over_100m": int(np.count_nonzero(absolute > 100)),
    }


def compare_lola_lroc_quality(
    lola_path: str | Path,
    lroc_path: str | Path,
    confidence_path: str | Path,
    output_path: str | Path,
) -> dict:
    """Produce un report riproducibile delle differenze LOLA-LROC."""

    lola_path = Path(lola_path)
    lroc_path = Path(lroc_path)
    confidence_path = Path(confidence_path)
    output_path = Path(output_path)

    for path in (lola_path, lroc_path, confidence_path):
        if not path.is_file():
            raise FileNotFoundError(f"File raster non trovato: {path}")

    source_paths = {
        p.resolve() for p in (lola_path, lroc_path, confidence_path)
    }
    if output_path.resolve() in source_paths:
        raise ValueError("Il report non può sovrascrivere un raster sorgente.")

    with rasterio.open(lola_path) as lo, \
         rasterio.open(lroc_path) as lr, \
         rasterio.open(confidence_path) as cf:

        for name, ds in (("LOLA", lo), ("LROC DTM", lr), ("CONF", cf)):
            if ds.count != 1:
                raise ValueError(f"{name}: è richiesta una sola banda.")
            if ds.crs is None:
                raise ValueError(f"{name}: CRS assente, confronto interrotto.")

        if cf.dtypes[0] != "uint8":
            raise ValueError("La confidenza originale deve essere uint8.")

        lola_ma = lo.read(1, masked=True).astype(np.float64)
        lola = lola_ma.filled(np.nan)
        lola_valid = (~np.ma.getmaskarray(lola_ma)) & np.isfinite(lola)

        # Legge il DTM rispettando sia nodata sia la maschera GDAL.
        lroc_ma = lr.read(1, masked=True).astype(np.float32)
        lroc_source = lroc_ma.filled(np.nan).astype(np.float32)

        lroc = np.full((lo.height, lo.width), np.nan, dtype=np.float32)
        reproject(
            source=lroc_source,
            destination=lroc,
            src_transform=lr.transform,
            src_crs=lr.crs,
            src_nodata=np.nan,
            dst_transform=lo.transform,
            dst_crs=lo.crs,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
            init_dest_nodata=True,
        )

        # Conserva i valori PDS3 originali, compresi gli zeri.
        # La copertura geometrica viene ricampionata separatamente:
        # -1 identifica soltanto l'assenza di copertura sulla griglia LOLA.
        confidence_source = cf.read(1, masked=False).astype(np.int16)

        codes = np.full(
            (lo.height, lo.width),
            OUTSIDE_CONFIDENCE,
            dtype=np.int16,
        )
        reproject(
            source=confidence_source,
            destination=codes,
            src_transform=cf.transform,
            src_crs=cf.crs,
            src_nodata=None,
            dst_transform=lo.transform,
            dst_crs=lo.crs,
            dst_nodata=OUTSIDE_CONFIDENCE,
            resampling=Resampling.nearest,
            init_dest_nodata=True,
        )

        source_coverage = np.ones(
            (cf.height, cf.width),
            dtype=np.uint8,
        )
        confidence_coverage = np.zeros(
            (lo.height, lo.width),
            dtype=np.uint8,
        )
        reproject(
            source=source_coverage,
            destination=confidence_coverage,
            src_transform=cf.transform,
            src_crs=cf.crs,
            src_nodata=None,
            dst_transform=lo.transform,
            dst_crs=lo.crs,
            dst_nodata=0,
            resampling=Resampling.nearest,
            init_dest_nodata=True,
        )

        lroc_valid = np.isfinite(lroc)
        confidence_covered = confidence_coverage > 0

        dem_overlap = lola_valid & lroc_valid
        classified_overlap = dem_overlap & confidence_covered

        primary = classified_overlap & (codes == 14)
        interpolated = classified_overlap & (codes == 4)
        shadow = classified_overlap & (codes == 1)
        confidence_nodata = classified_overlap & (codes == 0)

        known = np.isin(codes, [0, 1, 4, 14])
        unresolved = classified_overlap & ~known

        # Solo i gruppi con semantica documentata e interpretabile
        # come confronto altimetrico entrano nelle statistiche.
        comparison_valid = primary | interpolated

        delta = lroc.astype(np.float64) - lola
        delta[~np.isfinite(delta)] = 0.0

        class_counts = {
            str(int(code)): int(np.count_nonzero(
                classified_overlap & (codes == code)
            ))
            for code in np.unique(codes[classified_overlap])
        }

        per_class = {}
        for code_text, count in class_counts.items():
            code = int(code_text)
            mask = classified_overlap & (codes == code)
            per_class[code_text] = {
                "description": DOCUMENTED_CLASSES.get(
                    code, "Classe non documentata: significato non attribuito"
                ),
                "included_in_elevation_statistics": bool(
                    code in (4, 14)
                ),
                **_stats(delta, mask),
            }

        output = {
            "schema": "lola-lroc-quality-report/2.0",
            "method": {
                "target_grid": "LOLA",
                "lroc_dem_resampling": "bilinear",
                "confidence_resampling": "nearest",
                "difference_definition": "LROC minus LOLA, metres",
                "comparison_groups": {
                    "primary": "CONF 14",
                    "interpolated": "CONF 4",
                    "unresolved": "CONF classes not documented",
                    "excluded": ["CONF 0", "CONF 1", "outside confidence coverage"],
                },
            },
            "sources": {
                "lola_dem": str(lola_path),
                "lroc_dem": str(lroc_path),
                "lroc_original_confidence": str(confidence_path),
            },
            "coverage": {
                "lola_valid_pixels": int(np.count_nonzero(lola_valid)),
                "lroc_valid_pixels_on_lola_grid": int(np.count_nonzero(lroc_valid)),
                "dem_overlap_pixels": int(np.count_nonzero(dem_overlap)),
                "confidence_covered_pixels_on_dem_overlap": int(
                    np.count_nonzero(classified_overlap)
                ),
                "outside_confidence_coverage_pixels_on_dem_overlap": int(
                    np.count_nonzero(dem_overlap & ~confidence_covered)
                ),
                "valid_comparison_pixels": int(
                    np.count_nonzero(comparison_valid)
                ),
            },
            "confidence_class_counts_on_overlap": class_counts,
            "by_confidence_class": per_class,
            "comparison_groups": {
                "primary_conf_14": _stats(delta, primary),
                "interpolated_conf_4": _stats(delta, interpolated),
                "unresolved_classes": _stats(delta, unresolved),
            },
            "excluded_pixels": {
                "confidence_0_nodata": int(np.count_nonzero(confidence_nodata)),
                "confidence_1_shadow": int(np.count_nonzero(shadow)),
            },
            "code_14_reference_comparison": _stats(delta, primary),
            "warnings": [
                "Confronto diagnostico, non validazione geodetica.",
                "CONF 14 indica image matching riuscito, non accuratezza assoluta certificata.",
                "CONF 4 è analizzata separatamente perché interpolata o estrapolata.",
                "CONF 0 e CONF 1 sono escluse dalle statistiche altimetriche.",
                "Le classi CONF non documentate restano irrisolte.",
                "Le differenze non sono correzioni da applicare automaticamente alle quote.",
                "La confidenza LROC non è una maschera di percorribilità del rover.",
                "Il confronto non certifica frame fisico lunare o datum verticale equivalenti.",
                "Il ricampionamento non dimostra la co-registrazione fisica dei prodotti.",
            ],
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    return {
        "output_path": str(output_path),
        "valid_overlap_pixels": output["coverage"]["valid_comparison_pixels"],
        "code_14_mae_m": output["code_14_reference_comparison"]["mae_m"],
        "code_14_rmse_m": output["code_14_reference_comparison"]["rmse_m"],
        "class_counts": class_counts,
    }
