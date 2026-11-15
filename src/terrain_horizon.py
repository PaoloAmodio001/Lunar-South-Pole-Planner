# Last updated: 2026-11-14
"""Profilo preliminare dell'orizzonte da raster LOLA.

Il risultato resta diagnostico finché la posizione dell'osservatore,
la proiezione e la geometria lunare non sono validate.

Modello geometrico (F11)
------------------------
Se il CRS del DEM è riconosciuto come lunare e verificabile (vedi
``_lunar_sphere_radius``), l'elevazione apparente è calcolata su una sfera:

1. le coordinate proiettate dei campioni (x, y) sono convertite in
   latitudine/longitudine planetocentriche con la trasformazione inversa
   PyProj del CRS stesso (una sola chiamata vettoriale per profilo);
2. ogni campione diventa il vettore cartesiano
   ``P = (R + z) * u(lat, lon)``, con ``R`` raggio della sfera del CRS e
   ``z`` quota DEM;
3. l'osservatore è ``O = (R + z0 + observer_height_m) * u0``, dove ``u0``
   è la verticale locale (radiale) nel punto ``(observer_x, observer_y)``;
4. l'elevazione è ``atan2((P - O)·u0, |(P - O) - ((P - O)·u0) u0|)``,
   quindi include la depressione dovuta alla curvatura.

Limitazioni:
- le quote DEM sono interpretate come altezze sopra la sfera di raggio
  ``R`` dichiarata dal CRS. Il riferimento altimetrico LOLA/LROC NON è
  validato in questo progetto: il risultato resta diagnostico;
- la verticale locale è radiale (sfera), non normale a un geoide/selenoide;
- il percorso di campionamento resta una retta nel piano proiettato con
  passo pari al pixel; vicino al polo è prossimo a un cerchio massimo, ma
  non coincide esattamente con una geodetica. ``max_distance_m`` riporta
  la distanza lungo la griglia proiettata, non la distanza geodetica;
- nessuna rifrazione (assente sulla Luna) né campionamento sub-pixel.

Per CRS assente, non lunare o non riconosciuto si usa la formula planare
precedente ``atan2(z - observer_z, distance)``, senza alcuna assunzione.
"""

from dataclasses import dataclass
from pathlib import Path
import math

import numpy as np
import rasterio

# Raggio sferico di riferimento dei DEM LOLA/LROC (IAU Moon, m).
LUNAR_RADIUS_M = 1737400.0
# Tolleranza per riconoscere una sfera "lunare" (copre 1737.1–1737.5 km).
_LUNAR_RADIUS_TOLERANCE_M = 1000.0
# Tolleranza del controllo andata/ritorno della proiezione (m).
_ROUNDTRIP_TOLERANCE_M = 1e-3


def _lunar_sphere_radius(crs, probe_x, probe_y):
    """Restituisce (raggio_m, transformer_inverso) oppure None.

    Il CRS è accettato solo se: esiste; è proiettato con unità metriche;
    il corpo di riferimento è una sfera (semiasse minore = maggiore) con
    raggio entro ``_LUNAR_RADIUS_TOLERANCE_M`` da ``LUNAR_RADIUS_M``;
    la trasformazione inversa PyProj verso il CRS geodetico e ritorno
    riproduce il punto di prova entro ``_ROUNDTRIP_TOLERANCE_M``.
    Qualsiasi errore o condizione non soddisfatta => None (fallback planare).
    """
    if crs is None:
        return None
    try:
        from pyproj import CRS, Transformer

        pcrs = CRS.from_user_input(crs.to_wkt() if hasattr(crs, "to_wkt") else crs)
        if not pcrs.is_projected:
            return None
        units = {(a.unit_name or "").lower() for a in pcrs.axis_info}
        if not units or not units <= {"metre", "meter"}:
            return None
        ell = pcrs.ellipsoid
        if ell is None:
            return None
        a = float(ell.semi_major_metre)
        b = float(ell.semi_minor_metre)
        if not (math.isfinite(a) and math.isfinite(b)) or abs(a - b) > 1e-6:
            return None
        if abs(a - LUNAR_RADIUS_M) > _LUNAR_RADIUS_TOLERANCE_M:
            return None

        geo = pcrs.geodetic_crs
        inverse = Transformer.from_crs(pcrs, geo, always_xy=True)
        forward = Transformer.from_crs(geo, pcrs, always_xy=True)
        lon, lat = inverse.transform(probe_x, probe_y)
        bx, by = forward.transform(lon, lat)
        if not all(math.isfinite(v) for v in (lon, lat, bx, by)):
            return None
        if math.hypot(bx - probe_x, by - probe_y) > _ROUNDTRIP_TOLERANCE_M:
            return None
        return a, inverse
    except Exception:
        return None


def _unit_vectors(inverse, xs, ys):
    """Versori radiali per coordinate proiettate (una chiamata PyProj)."""
    lon, lat = inverse.transform(np.asarray(xs, float), np.asarray(ys, float))
    lon = np.radians(lon)
    lat = np.radians(lat)
    cl = np.cos(lat)
    return np.stack((cl * np.cos(lon), cl * np.sin(lon), np.sin(lat)), axis=-1)


@dataclass
class HorizonProfile:
    azimuth_deg: np.ndarray
    elevation_deg: np.ndarray
    max_distance_m: np.ndarray
    valid_samples: np.ndarray
    zero_density_fraction: np.ndarray
    mean_dem_error_m: np.ndarray
    observer_elevation_m: float
    observer_row: int
    observer_col: int
    georeference_validated: bool = False


def calculate_horizon(
    dem_path,
    observer_x,
    observer_y,
    density_path=None,
    error_path=None,
    azimuth_step_deg=2.0,
    max_distance_m=7000.0,
    observer_height_m=0.0,
):
    if not 0 < azimuth_step_deg <= 45:
        raise ValueError("azimuth_step_deg deve essere tra 0 e 45")
    if max_distance_m <= 0:
        raise ValueError("max_distance_m deve essere positivo")

    with rasterio.open(dem_path) as ds:
        dem = ds.read(1, masked=True).filled(np.nan).astype(np.float32)
        transform = ds.transform
        row, col = ds.index(observer_x, observer_y)

        if not (0 <= row < ds.height and 0 <= col < ds.width):
            raise ValueError("Punto osservatore fuori dal raster")

        z0 = float(dem[row, col])
        if not math.isfinite(z0):
            raise ValueError("Quota osservatore non valida")

        pixel_size = min(abs(transform.a), abs(transform.e))
        if pixel_size <= 0:
            raise ValueError("Risoluzione raster non valida")

        height, width = dem.shape
        crs = ds.crs

    density = None
    error = None

    if density_path and Path(density_path).is_file():
        with rasterio.open(density_path) as ds:
            density = ds.read(1, masked=True).filled(np.nan).astype(np.float32)

    if error_path and Path(error_path).is_file():
        with rasterio.open(error_path) as ds:
            error = ds.read(1, masked=True).filled(np.nan).astype(np.float32)

    for name, arr in (("densità", density), ("errore", error)):
        if arr is not None and arr.shape != dem.shape:
            raise ValueError(f"Raster {name} non allineato al DEM")

    observer_z = z0 + observer_height_m
    azimuths = np.arange(0.0, 360.0, azimuth_step_deg)

    elevations = np.full(azimuths.shape, np.nan)
    max_distances = np.zeros(azimuths.shape)
    valid_counts = np.zeros(azimuths.shape, dtype=int)
    zero_density = np.full(azimuths.shape, np.nan)
    mean_errors = np.full(azimuths.shape, np.nan)

    # Il campionamento avviene in memoria: nessuna lettura raster nel ciclo.
    distances = np.arange(
        pixel_size, max_distance_m + pixel_size, pixel_size
    )

    # Geometria sferica solo per CRS lunare riconosciuto e verificabile.
    lunar = _lunar_sphere_radius(crs, observer_x, observer_y)
    sample_units = None
    if lunar is not None:
        radius, inverse = lunar
        az_rad = np.radians(azimuths)[:, None]
        grid_x = observer_x + np.sin(az_rad) * distances[None, :]
        grid_y = observer_y + np.cos(az_rad) * distances[None, :]
        # Unica trasformazione vettoriale per tutti i campioni del profilo.
        sample_units = _unit_vectors(inverse, grid_x, grid_y)
        up0 = _unit_vectors(inverse, [observer_x], [observer_y])[0]
        observer_vec = (radius + observer_z) * up0

    for i, azimuth in enumerate(azimuths):
        rad = math.radians(float(azimuth))
        dx, dy = math.sin(rad), math.cos(rad)

        best_angle = -90.0
        best_distance = 0.0
        valid = 0
        zero_count = 0
        errors = []

        for k, distance in enumerate(distances):
            x = observer_x + dx * distance
            y = observer_y + dy * distance
            rr, cc = rasterio.transform.rowcol(transform, x, y)

            if not (0 <= rr < height and 0 <= cc < width):
                break

            z = float(dem[rr, cc])
            if not math.isfinite(z):
                continue

            if sample_units is None:
                angle = math.degrees(
                    math.atan2(z - observer_z, float(distance))
                )
            else:
                los = (radius + z) * sample_units[i, k] - observer_vec
                vertical = float(los @ up0)
                horizontal = float(np.linalg.norm(los - vertical * up0))
                angle = math.degrees(math.atan2(vertical, horizontal))
            if angle > best_angle:
                best_angle = angle
                best_distance = float(distance)

            valid += 1

            if density is not None:
                d = float(density[rr, cc])
                if not math.isfinite(d) or d <= 0:
                    zero_count += 1

            if error is not None:
                e = float(error[rr, cc])
                if math.isfinite(e):
                    errors.append(e)

        if valid:
            elevations[i] = best_angle
            max_distances[i] = best_distance
            valid_counts[i] = valid

            if density is not None:
                zero_density[i] = zero_count / valid
            if errors:
                mean_errors[i] = float(np.mean(errors))

    return HorizonProfile(
        azimuth_deg=azimuths,
        elevation_deg=elevations,
        max_distance_m=max_distances,
        valid_samples=valid_counts,
        zero_density_fraction=zero_density,
        mean_dem_error_m=mean_errors,
        observer_elevation_m=observer_z,
        observer_row=row,
        observer_col=col,
    )
