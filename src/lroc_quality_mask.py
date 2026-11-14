"""Costruzione di una maschera di qualità sulla griglia nativa LROC.

La maschera non corregge le elevazioni e non certifica l'accuratezza
assoluta del DTM o la sua co-registrazione fisica.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio


INVALID = 0
PRIMARY = 1
INTERPOLATED = 2
UNRESOLVED = 3
OUTPUT_NODATA = 255

CLASS_NAMES = {
    INVALID: "INVALID",
    PRIMARY: "PRIMARY",
    INTERPOLATED: "INTERPOLATED",
    UNRESOLVED: "UNRESOLVED",
}


def build_lroc_quality_mask(
    dtm_path: str | Path,
    confidence_path: str | Path,
    output_raster: str | Path,
    output_report: str | Path,
) -> dict:
    """Genera una classificazione pixel-per-pixel sul DTM LROC nativo.

    Regole:
      0 = DTM non valido, CONF 0 oppure CONF 1 (ombra)
      1 = CONF 14 e DTM valido
      2 = CONF 4 e DTM valido
      3 = altra classe CONF e DTM valido

    Il valore 255 è riservato a NoData del raster di output.
    """
    dtm_path = Path(dtm_path)
    confidence_path = Path(confidence_path)
    output_raster = Path(output_raster)
    output_report = Path(output_report)

    for path in (dtm_path, confidence_path):
        if not path.is_file():
            raise FileNotFoundError(f"File sorgente non trovato: {path}")

    source_paths = {
        dtm_path.resolve(),
        confidence_path.resolve(),
    }
    if output_raster.resolve() in source_paths:
        raise ValueError("Il raster di output non può sovrascrivere un sorgente.")
    if output_report.resolve() in source_paths:
        raise ValueError("Il report non può sovrascrivere un sorgente.")

    with rasterio.open(dtm_path) as dtm, rasterio.open(confidence_path) as conf:
        if dtm.count != 1 or conf.count != 1:
            raise ValueError("DTM e CONF devono avere una sola banda.")

        if dtm.crs is None or conf.crs is None:
            raise ValueError("CRS assente: impossibile verificare la griglia.")

        if dtm.crs != conf.crs:
            raise ValueError("CRS DTM e CONF differenti: operazione interrotta.")

        if dtm.transform != conf.transform:
            raise ValueError(
                "Trasformazioni affine DTM e CONF differenti: "
                "non è consentita alcuna riproiezione automatica."
            )

        if (dtm.width, dtm.height) != (conf.width, conf.height):
            raise ValueError("Dimensioni DTM e CONF differenti.")

        elevation_valid = dtm.read_masks(1) > 0
        confidence = conf.read(1)

        if confidence.dtype != np.uint8:
            raise ValueError(
                f"CONF deve essere uint8; trovato {confidence.dtype}."
            )

        result = np.zeros(confidence.shape, dtype=np.uint8)

        result[elevation_valid & (confidence == 14)] = PRIMARY
        result[elevation_valid & (confidence == 4)] = INTERPOLATED

        documented = np.isin(confidence, [0, 1, 4, 14])
        result[elevation_valid & ~documented] = UNRESOLVED

        # I pixel con DTM non valido restano INVALID, indipendentemente
        # dal codice CONF.
        result[~elevation_valid] = INVALID

        pixel_area_m2 = abs(
            dtm.transform.a * dtm.transform.e
            - dtm.transform.b * dtm.transform.d
        )

        counts = {
            name: int(np.count_nonzero(result == code))
            for code, name in CLASS_NAMES.items()
        }

        raw_classes, raw_counts = np.unique(
            confidence, return_counts=True
        )
        confidence_histogram = {
            str(int(code)): int(count)
            for code, count in zip(raw_classes, raw_counts)
        }

        unresolved_codes = sorted(
            int(code)
            for code in np.unique(confidence[elevation_valid])
            if int(code) not in (0, 1, 4, 14)
        )

        profile = dtm.profile.copy()
        profile.update(
            driver="GTiff",
            count=1,
            dtype="uint8",
            nodata=OUTPUT_NODATA,
            compress="deflate",
            predictor=2,
        )

        output_raster.parent.mkdir(parents=True, exist_ok=True)
        output_report.parent.mkdir(parents=True, exist_ok=True)

        with rasterio.open(output_raster, "w", **profile) as dst:
            dst.write(result, 1)
            dst.set_band_description(1, "LROC native-grid quality class")
            dst.update_tags(
                0,
                classification="LROC_CONF_DTM_NATIVE_GRID",
                class_0="INVALID",
                class_1="PRIMARY: CONF 14 and valid DTM",
                class_2="INTERPOLATED: CONF 4 and valid DTM",
                class_3="UNRESOLVED: undocumented CONF and valid DTM",
                nodata="255",
                source_dtm=str(dtm_path),
                source_confidence=str(confidence_path),
                warning=(
                    "Classification only; not an absolute accuracy "
                    "or physical co-registration certification."
                ),
            )

        report = {
            "status": "success",
            "dtm_path": str(dtm_path),
            "confidence_path": str(confidence_path),
            "output_raster": str(output_raster),
            "grid": {
                "width": dtm.width,
                "height": dtm.height,
                "crs": str(dtm.crs),
                "transform": list(dtm.transform)[:6],
                "pixel_area_m2": pixel_area_m2,
            },
            "classification": {
                "0": "INVALID: DTM invalid, CONF 0 or CONF 1",
                "1": "PRIMARY: CONF 14 and valid DTM",
                "2": "INTERPOLATED: CONF 4 and valid DTM",
                "3": "UNRESOLVED: undocumented CONF and valid DTM",
                "255": "NoData reserved value",
            },
            "pixel_counts": counts,
            "area_km2": {
                name: count * pixel_area_m2 / 1_000_000
                for name, count in counts.items()
            },
            "confidence_histogram": confidence_histogram,
            "unresolved_confidence_codes_on_valid_dtm": unresolved_codes,
            "valid_dtm_pixels": int(np.count_nonzero(elevation_valid)),
            "total_pixels": int(result.size),
            "warnings": [
                "La classificazione non certifica l'accuratezza assoluta del DTM.",
                "La coincidenza della griglia non dimostra la co-registrazione fisica.",
                "Le classi CONF non documentate sono mantenute come UNRESOLVED.",
                "La maschera è riferita esclusivamente alla griglia nativa LROC.",
                "Non applicare direttamente questa maschera al DEM LOLA.",
            ],
        }

    output_report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report
