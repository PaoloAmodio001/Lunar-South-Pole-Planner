"""Metriche diagnostiche locali di densità e incertezza dei raster LOLA.

Non modifica le quote e non certifica l'accuratezza assoluta.
LDEC descrive il numero di ritorni laser per cella; TOTERR è
l'incertezza RMS riportata dal prodotto sorgente.

Struttura del modulo:

1. ``validate_lola_quality_grids``: validazione strutturale (una sola volta)
   di DEM, LDEC e TOTERR. Nessuna riproiezione o ricampionamento.
2. ``LolaQualityReader``: context manager che valida le griglie e mantiene
   aperti LDEC e TOTERR per tutta la durata del campionamento.
3. ``_summarize_arrays``: statistiche locali sulla finestra del candidato.

``summarize_lola_quality`` resta disponibile come API compatibile per
chiamate singole.
"""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
import math
import os

import numpy as np
import rasterio
from rasterio.windows import Window


INTERPRETATION = (
    "LDEC descrive i ritorni laser per cella; TOTERR è "
    "l'incertezza RMS del prodotto. Nessuno dei due, da solo, "
    "certifica l'accuratezza assoluta della quota."
)


@dataclass(frozen=True)
class LolaGridInfo:
    """Griglia comune verificata per DEM, LDEC e TOTERR."""

    width: int
    height: int
    crs: str
    transform: tuple

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "crs": self.crs,
            "transform": list(self.transform),
        }


# --------------------------------------------------------------------------
# 1. Validazione strutturale
# --------------------------------------------------------------------------

def _check_readable(label: str, dataset) -> None:
    """Verifica i metadati minimi necessari a leggere correttamente i dati."""
    if dataset.count != 1:
        raise ValueError(
            f"Raster {label}: attesa una sola banda, trovate {dataset.count}."
        )
    if dataset.width <= 0 or dataset.height <= 0:
        raise ValueError(f"Raster {label}: dimensioni non valide.")
    if np.dtype(dataset.dtypes[0]).kind not in "iuf":
        raise ValueError(
            f"Raster {label}: tipo di dato non numerico ({dataset.dtypes[0]})."
        )
    if dataset.crs is None:
        raise ValueError(f"Raster {label}: CRS assente.")
    transform = dataset.transform
    coefficients = tuple(transform)[:6]
    if not all(math.isfinite(value) for value in coefficients):
        raise ValueError(f"Raster {label}: trasformazione affine non finita.")
    if transform.determinant == 0:
        raise ValueError(f"Raster {label}: trasformazione affine degenere.")


def _is_open_dataset(raster) -> bool:
    return not isinstance(raster, (str, os.PathLike)) and hasattr(raster, "read")


def validate_lola_quality_grids(reference_path,
                                density_path: str | Path,
                                error_path: str | Path) -> LolaGridInfo:
    """Verifica che DEM, LDEC e TOTERR condividano esattamente la stessa griglia.

    Controlli: esistenza dei file, una sola banda numerica, CRS presente e
    identico, dimensioni identiche, trasformazione affine identica.

    ``reference_path`` può essere un percorso oppure il dataset DEM già
    aperto dal chiamante: in quel caso viene riutilizzato e non chiuso.

    Raises:
        FileNotFoundError: se uno dei raster non esiste.
        ValueError: per metadati insufficienti o griglie non allineate.
    """
    reference_is_open = _is_open_dataset(reference_path)
    if reference_is_open and reference_path.closed:
        raise ValueError("Il dataset DEM fornito è già chiuso.")
    labelled = (
        ("DEM", reference_path if reference_is_open else Path(reference_path)),
        ("LDEC", Path(density_path)),
        ("TOTERR", Path(error_path)),
    )
    for label, path in labelled:
        if isinstance(path, Path) and not path.is_file():
            raise FileNotFoundError(f"Raster {label} non trovato: {path}")

    with ExitStack() as stack:
        datasets = [
            (label, path if not isinstance(path, Path)
             else stack.enter_context(rasterio.open(path)))
            for label, path in labelled
        ]
        for label, dataset in datasets:
            _check_readable(label, dataset)

        reference = datasets[0][1]
        for label, dataset in datasets[1:]:
            if (dataset.width, dataset.height) != (
                    reference.width, reference.height):
                raise ValueError(
                    f"Raster {label} non allineato al DEM: dimensioni "
                    f"differenti ({dataset.width}x{dataset.height} vs "
                    f"{reference.width}x{reference.height})."
                )
            if dataset.crs != reference.crs:
                raise ValueError(
                    f"Raster {label} non allineato al DEM: CRS differente "
                    f"({dataset.crs} vs {reference.crs})."
                )
            if dataset.transform != reference.transform:
                raise ValueError(
                    f"Raster {label} non allineato al DEM: trasformazione "
                    f"affine differente ({tuple(dataset.transform)[:6]} vs "
                    f"{tuple(reference.transform)[:6]})."
                )

        return LolaGridInfo(
            width=int(reference.width),
            height=int(reference.height),
            crs=str(reference.crs),
            transform=tuple(float(v) for v in tuple(reference.transform)[:6]),
        )


# --------------------------------------------------------------------------
# 2. Apertura dei dataset (una sola volta per sessione di campionamento)
# --------------------------------------------------------------------------

class LolaQualityReader:
    """Valida le griglie una volta e mantiene aperti LDEC e TOTERR.

    Uso::

        with LolaQualityReader(dem, ldec, toterr) as reader:
            reader.summarize(row, col, radius_pixels)

    I dataset vengono chiusi all'uscita dal blocco, anche in caso di
    eccezione.
    """

    def __init__(self, reference_path,
                 density_path: str | Path,
                 error_path: str | Path) -> None:
        # Percorso del DEM oppure dataset DEM già aperto (non viene chiuso).
        self.reference_path = (
            reference_path if _is_open_dataset(reference_path)
            else Path(reference_path)
        )
        self.density_path = Path(density_path)
        self.error_path = Path(error_path)
        self.grid: LolaGridInfo | None = None
        self._stack: ExitStack | None = None
        self._density = None
        self._error = None

    def __enter__(self) -> "LolaQualityReader":
        grid = validate_lola_quality_grids(
            self.reference_path, self.density_path, self.error_path
        )
        with ExitStack() as stack:
            self._density = stack.enter_context(rasterio.open(self.density_path))
            self._error = stack.enter_context(rasterio.open(self.error_path))
            # Trasferisce la proprietà degli handle solo se tutto è riuscito.
            self._stack = stack.pop_all()
        self.grid = grid
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        stack, self._stack = self._stack, None
        self._density = self._error = None
        if stack is not None:
            stack.close()

    def summarize(self, center_row: int, center_col: int,
                  radius_pixels: int = 10) -> dict:
        """Statistiche LDEC/TOTERR nella finestra locale del candidato."""
        if self._stack is None or self.grid is None:
            raise RuntimeError("LolaQualityReader non aperto.")
        center_row, center_col = _validate_window_args(
            center_row, center_col, radius_pixels
        )
        window, bounds = _candidate_window(
            self.grid.height, self.grid.width,
            center_row, center_col, radius_pixels,
        )
        density = self._density.read(1, window=window, masked=True)
        error = self._error.read(1, window=window, masked=True)
        return _summarize_arrays(density, error, bounds, radius_pixels)


# --------------------------------------------------------------------------
# 3. Statistiche locali
# --------------------------------------------------------------------------

def _validate_window_args(center_row, center_col,
                          radius_pixels) -> tuple[int, int]:
    if (isinstance(radius_pixels, bool) or int(radius_pixels) != radius_pixels
            or radius_pixels < 0):
        raise ValueError("radius_pixels deve essere un intero >= 0.")
    if int(center_row) != center_row or int(center_col) != center_col:
        raise ValueError("Le coordinate di griglia devono essere intere.")
    return int(center_row), int(center_col)


def _candidate_window(height: int, width: int, center_row: int,
                      center_col: int, radius_pixels: int):
    if not (0 <= center_row < height and 0 <= center_col < width):
        raise ValueError("Centro candidato fuori dal raster DEM.")
    radius_pixels = int(radius_pixels)
    row0 = max(0, center_row - radius_pixels)
    row1 = min(height, center_row + radius_pixels + 1)
    col0 = max(0, center_col - radius_pixels)
    col1 = min(width, center_col + radius_pixels + 1)
    window = Window(col0, row0, col1 - col0, row1 - row0)
    return window, (row0, row1, col0, col1)


def _to_float_with_nan(values) -> np.ndarray:
    array = np.asarray(
        np.ma.filled(np.ma.asarray(values).astype(np.float64), np.nan),
        dtype=float,
    )
    array[~np.isfinite(array)] = np.nan
    return array


def _summarize_arrays(density, error, bounds, radius_pixels: int) -> dict:
    row0, row1, col0, col1 = bounds
    density = _to_float_with_nan(density)
    error = _to_float_with_nan(error)

    density_valid = np.isfinite(density) & (density >= 0)
    error_valid = np.isfinite(error) & (error >= 0)

    density_values = density[density_valid]
    error_values = error[error_valid]

    total = int(density.size)
    density_counts = {
        str(value): int(np.count_nonzero(density_values == value))
        for value in (0, 1, 2, 3, 4, 5)
    }

    def stats(values: np.ndarray) -> dict:
        if values.size == 0:
            return {
                "count": 0, "median_m": None,
                "p95_m": None, "max_m": None,
            }
        return {
            "count": int(values.size),
            "median_m": float(np.median(values)),
            "p95_m": float(np.percentile(values, 95)),
            "max_m": float(np.max(values)),
        }

    return {
        "status": "available" if density_values.size and error_values.size
                  else "partial_or_missing",
        "window": {
            "row_start": row0, "row_stop_exclusive": row1,
            "col_start": col0, "col_stop_exclusive": col1,
            "radius_pixels": int(radius_pixels),
            "total_cells": total,
        },
        "ldec": {
            "valid_cells": int(density_valid.sum()),
            "valid_fraction": float(density_valid.sum() / total),
            "counts_by_return_count": density_counts,
            "zero_return_fraction": (
                float(np.mean(density_values == 0))
                if density_values.size else None
            ),
            "positive_return_fraction": (
                float(np.mean(density_values > 0))
                if density_values.size else None
            ),
        },
        "toterr": {
            **stats(error_values),
            "valid_fraction": float(error_valid.sum() / total),
        },
        "interpretation": INTERPRETATION,
    }


def summarize_lola_quality(
    reference_path: str | Path,
    density_path: str | Path,
    error_path: str | Path,
    center_row: int,
    center_col: int,
    radius_pixels: int = 10,
) -> dict:
    """Riassume LDEC e TOTERR nella finestra locale di un singolo candidato.

    API compatibile per chiamate singole: valida le griglie a ogni chiamata.
    Per molti candidati usare ``LolaQualityReader``.
    """
    _validate_window_args(center_row, center_col, radius_pixels)
    with LolaQualityReader(reference_path, density_path, error_path) as reader:
        return reader.summarize(center_row, center_col, radius_pixels)
