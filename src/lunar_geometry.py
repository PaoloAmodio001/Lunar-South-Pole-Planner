# Last updated: 2026-11-14
"""Geometria cartografica lunare: trasformazioni diagnostiche.

ATTENZIONE:
- La trasformazione matematica non convalida il datum o il frame lunare.
- La longitudine di ingresso deve essere esplicitamente est positiva.
- georeference_validated rimane False finché non esiste una verifica esterna.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

import rasterio
from pyproj import CRS, Proj, Transformer


MOON_RADIUS_M = 1_737_400.0

# Ipotesi di lavoro: longitudine est positiva e sfera lunare.
# La compatibilità con MOON_ME / DE421 deve ancora essere verificata.
MOON_GEOGRAPHIC_CRS = CRS.from_proj4(
    f"+proj=longlat +R={MOON_RADIUS_M} +no_defs +type=crs"
)


@dataclass(frozen=True)
class ObserverLocation:
    longitude_east_deg: float
    latitude_deg: float
    x_m: float
    y_m: float
    row: int
    col: int
    inside_raster: bool
    georeference_validated: bool
    status: str
    message: str


def geographic_to_projected(
    longitude_east_deg: float,
    latitude_deg: float,
    target_crs,
) -> tuple[float, float]:
    """Trasforma lon/lat lunari in coordinate del CRS indicato.

    La longitudine deve essere est positiva. Il risultato non certifica
    che il CRS di destinazione condivida il frame fisico delle coordinate.
    """
    if not math.isfinite(longitude_east_deg):
        raise ValueError("La longitudine deve essere finita.")
    if not math.isfinite(latitude_deg) or not -90 <= latitude_deg <= 90:
        raise ValueError("La latitudine deve essere finita e compresa tra -90 e 90.")
    if not -360 <= longitude_east_deg <= 360:
        raise ValueError("La longitudine deve essere compresa tra -360 e 360.")

    target = CRS.from_user_input(target_crs)
    transformer = Transformer.from_crs(
        MOON_GEOGRAPHIC_CRS, target, always_xy=True
    )
    x, y = transformer.transform(longitude_east_deg, latitude_deg)

    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError("La trasformazione ha prodotto coordinate non finite.")

    return float(x), float(y)


def locate_observer(
    dem_path: str | Path,
    longitude_east_deg: float,
    latitude_deg: float,
) -> ObserverLocation:
    """Localizza un candidato nel raster senza dichiararlo validato."""
    path = Path(dem_path)
    if not path.is_file():
        raise FileNotFoundError(f"DEM non trovato: {path}")

    with rasterio.open(path) as ds:
        if ds.crs is None:
            raise ValueError("Il DEM non dichiara un CRS.")

        x, y = geographic_to_projected(
            longitude_east_deg, latitude_deg, ds.crs
        )

        row, col = ds.index(x, y)
        inside = 0 <= row < ds.height and 0 <= col < ds.width

        status = "candidate_inside" if inside else "outside_raster"
        message = (
            "Punto candidato dentro i limiti raster; frame e posizione "
            "geografica non ancora convalidati."
            if inside else
            "Il punto candidato è fuori dal raster secondo la trasformazione "
            "ipotizzata; verificare convenzione della longitudine e frame."
        )

        return ObserverLocation(
            longitude_east_deg=float(longitude_east_deg),
            latitude_deg=float(latitude_deg),
            x_m=x,
            y_m=y,
            row=int(row),
            col=int(col),
            inside_raster=inside,
            georeference_validated=False,
            status=status,
            message=message,
        )


def sample_elevation(
    dem_path: str | Path,
    location: ObserverLocation,
) -> float | None:
    """Legge la quota del pixel candidato; restituisce None se non valida."""
    if not location.inside_raster:
        return None

    with rasterio.open(dem_path) as ds:
        value = next(ds.sample([(location.x_m, location.y_m)], masked=True))[0]
        if bool(getattr(value, "mask", False)):
            return None

        elevation = float(value)
        if not math.isfinite(elevation):
            return None
        return elevation


# ---------------------------------------------------------------------------
# Validazione dell'identità geografica sito ↔ raster
# ---------------------------------------------------------------------------

class SiteIdentityError(ValueError):
    """Sito dichiarato e raster di terreno geograficamente incompatibili."""


# Tolleranza sul raggio della sfera del CRS: il CRS del raster deve usare la
# stessa sfera lunare di MOON_GEOGRAPHIC_CRS, altrimenti la trasformazione
# lon/lat → x/y non è verificabile.
_SPHERE_TOLERANCE_M = 1.0


def _is_lunar_projected_crs(crs: CRS) -> bool:
    ellipsoid = crs.ellipsoid
    return bool(
        crs.is_projected and ellipsoid is not None
        and abs(ellipsoid.semi_major_metre - MOON_RADIUS_M) <= _SPHERE_TOLERANCE_M
        and abs(ellipsoid.semi_minor_metre - MOON_RADIUS_M) <= _SPHERE_TOLERANCE_M
    )


def validate_site_in_raster(
    site_name: str,
    latitude_deg: float,
    longitude_east_deg: float,
    raster_path: str | Path,
) -> dict:
    """Verifica che le coordinate del sito ricadano nell'estensione del raster.

    Solleva ``FileNotFoundError`` se il raster manca e ``SiteIdentityError``
    se il CRS è assente, non proiettato, non basato sulla sfera lunare
    (R = 1 737 400 m), se la trasformazione fallisce o se il sito è fuori
    dall'estensione del raster. Non riproietta né modifica il raster.
    """
    path = Path(raster_path)
    if not path.is_file():
        raise FileNotFoundError(f"Raster di terreno non trovato: {path}")

    with rasterio.open(path) as ds:
        if ds.crs is None:
            raise SiteIdentityError(
                f"Trasformazione non disponibile: il raster {path} non "
                "dichiara un CRS; impossibile collocare il sito "
                f"{site_name!r}."
            )
        crs = CRS.from_user_input(ds.crs)
        if not _is_lunar_projected_crs(crs):
            raise SiteIdentityError(
                f"Trasformazione non verificabile per {path}: il CRS deve "
                f"essere proiettato sulla sfera lunare R={MOON_RADIUS_M:.0f} m "
                f"(trovato: {crs.to_string()})."
            )
        try:
            x, y = geographic_to_projected(longitude_east_deg, latitude_deg, crs)
        except Exception as exc:  # pyproj/valori non validi
            raise SiteIdentityError(
                f"Trasformazione delle coordinate del sito {site_name!r} "
                f"non riuscita per {path}: {exc}"
            ) from exc

        row, col = ds.index(x, y)
        bounds = ds.bounds
        inside = 0 <= row < ds.height and 0 <= col < ds.width
        if not inside:
            raise SiteIdentityError(
                f"Sito {site_name!r} (lat {latitude_deg}, lon E "
                f"{longitude_east_deg}) fuori dall'estensione del raster "
                f"{path}: x={x:.1f} m, y={y:.1f} m, limiti "
                f"x[{bounds.left}, {bounds.right}] y[{bounds.bottom}, "
                f"{bounds.top}]. Sito e dataset incompatibili."
            )
        center_x = (bounds.left + bounds.right) / 2.0
        center_y = (bounds.bottom + bounds.top) / 2.0
        return {
            "site": site_name,
            "latitude_deg": float(latitude_deg),
            "longitude_east_deg": float(longitude_east_deg),
            "raster_path": str(path),
            "crs": crs.to_string(),
            "x_m": x,
            "y_m": y,
            "row": int(row),
            "col": int(col),
            "bounds_m": {
                "left": bounds.left, "bottom": bounds.bottom,
                "right": bounds.right, "top": bounds.top,
            },
            "distance_from_raster_center_m": math.hypot(
                x - center_x, y - center_y
            ),
            "status": "inside_raster",
        }


# ---------------------------------------------------------------------------
# Orientamento azimutale: nord geografico ↔ nord di griglia
# ---------------------------------------------------------------------------
#
# Convenzioni del progetto (unica fonte):
# - Azimut geografico (Horizons, QUANTITIES=4): gradi, in senso orario dal
#   nord geografico locale (N=0, E=90, S=180, W=270).
# - Azimut di griglia (terrain_horizon): gradi, in senso orario dall'asse +y
#   del raster verso +x; direzione di passo (dx, dy) = (sin az, cos az).
# - grid_azimuth = (geographic_azimuth + offset) mod 360
#   geographic_azimuth = (grid_azimuth - offset) mod 360
# - offset = azimut di griglia della direzione del nord geografico nel punto.
#   Per la stereografica polare sud (lat_0 = -90) vale lon_E - lon_0; PROJ
#   riporta meridian_convergence = -offset (mod 360).

class AzimuthOrientationError(ValueError):
    """Offset azimutale non determinabile o non verificabile dal CRS."""


def _wrap180(angle_deg: float) -> float:
    return (float(angle_deg) + 180.0) % 360.0 - 180.0


def geographic_to_grid_azimuth(azimuth_deg: float, offset_deg: float) -> float:
    """Azimut geografico (orario da nord) → azimut di griglia, in [0, 360)."""
    if not (math.isfinite(azimuth_deg) and math.isfinite(offset_deg)):
        raise ValueError("Azimut e offset devono essere finiti (gradi).")
    return (float(azimuth_deg) + float(offset_deg)) % 360.0


def grid_to_geographic_azimuth(azimuth_deg: float, offset_deg: float) -> float:
    """Azimut di griglia → azimut geografico (orario da nord), in [0, 360)."""
    if not (math.isfinite(azimuth_deg) and math.isfinite(offset_deg)):
        raise ValueError("Azimut e offset devono essere finiti (gradi).")
    return (float(azimuth_deg) - float(offset_deg)) % 360.0


def grid_azimuth_offset(crs_input, x_m: float, y_m: float) -> dict:
    """Offset tra nord geografico e nord di griglia nel punto (x_m, y_m).

    Metodo: differenze finite con il CRS stesso (passo di 1e-6° verso nord
    e verso est), verificate con il meridian_convergence di PROJ. Richiede
    un CRS proiettato sulla sfera lunare, un punto non coincidente con il
    polo e una proiezione non speculare (est = nord + 90°).
    """
    if crs_input is None:
        raise AzimuthOrientationError("CRS assente: offset non determinabile.")
    crs = CRS.from_user_input(crs_input)
    if not _is_lunar_projected_crs(crs):
        raise AzimuthOrientationError(
            "Offset non verificabile: il CRS deve essere proiettato sulla "
            f"sfera lunare R={MOON_RADIUS_M:.0f} m (trovato: {crs.to_string()})."
        )
    if not (math.isfinite(x_m) and math.isfinite(y_m)):
        raise AzimuthOrientationError("Coordinate dell'osservatore non finite.")

    to_geo = Transformer.from_crs(crs, MOON_GEOGRAPHIC_CRS, always_xy=True)
    to_grid = Transformer.from_crs(MOON_GEOGRAPHIC_CRS, crs, always_xy=True)
    lon, lat = to_geo.transform(x_m, y_m)
    if not (math.isfinite(lon) and math.isfinite(lat)) or abs(lat) > 89.99999:
        raise AzimuthOrientationError(
            "Punto coincidente con il polo o non trasformabile: il nord "
            "geografico non è definito."
        )

    step = 1e-6
    sign = 1.0 if lat < 0 else -1.0  # passo verso il nord senza superare il polo
    x0, y0 = to_grid.transform(lon, lat)
    xn, yn = to_grid.transform(lon, lat + sign * step)
    xe, ye = to_grid.transform(lon + step, lat)
    north = math.degrees(math.atan2(sign * (xn - x0), sign * (yn - y0))) % 360.0
    east = math.degrees(math.atan2(xe - x0, ye - y0)) % 360.0

    handedness = _wrap180(east - north)
    if abs(handedness - 90.0) > 1e-3:
        raise AzimuthOrientationError(
            f"Proiezione non conforme o speculare: est - nord = {handedness:.6f}°; "
            "una rotazione non basta a convertire gli azimut."
        )

    convergence = float(Proj(crs).get_factors(lon, lat).meridian_convergence)
    if abs(_wrap180(north + convergence)) > 1e-4:
        raise AzimuthOrientationError(
            f"Verifica indipendente fallita: differenze finite {north:.6f}°, "
            f"PROJ meridian_convergence {convergence:.6f}°."
        )

    return {
        "offset_deg": north,
        "convention": "grid_azimuth = (geographic_azimuth + offset) mod 360",
        "observer_x_m": float(x_m),
        "observer_y_m": float(y_m),
        "observer_latitude_deg": float(lat),
        "observer_longitude_east_deg": float(lon),
        "east_minus_north_deg": handedness,
        "proj_meridian_convergence_deg": convergence,
        "method": "finite_difference_on_crs_checked_with_proj_meridian_convergence",
        "crs": crs.to_string(),
    }
