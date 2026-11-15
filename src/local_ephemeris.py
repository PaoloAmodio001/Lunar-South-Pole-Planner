# Last updated: 2026-11-15
"""Effemeridi topocentriche lunari locali e offline (Skyfield + kernel SPICE NAIF).

Fonte indipendente da NASA/JPL Horizons: usa i file inclusi nel repository

- ``de421.bsp``: effemeridi planetarie JPL DE421;
- ``moon_pa_de421_1900-2050.bpc``: orientamento lunare (Principal Axes) coerente con DE421;
- ``moon_080317.tf``: definizione del frame ``MOON_ME_DE421`` (Mean Earth / polar axis);
- ``pck00008.tpc``: costanti planetarie.

Le coordinate del sito sono latitudine planetocentrica e longitudine est nel frame MOON_ME,
la stessa convenzione dei siti di ``src/astronomy.py`` e di Horizons (``coord@301``).
Azimut in gradi, in senso orario dal nord locale; elevazione rispetto all'orizzonte geometrico
(la Luna non ha atmosfera: nessuna rifrazione). La validità è limitata all'intervallo del kernel
di orientamento, 1900-2050.

La concordanza con Horizons è misurata da ``src/ephemeris_validation.py``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from src.astronomy import Observation
from src.paths import PROJECT_ROOT

KERNEL_DIR = PROJECT_ROOT / "data" / "terrain" / "kernels"
DE421_PATH = PROJECT_ROOT / "de421.bsp"
FRAME_NAME = "MOON_ME_DE421"
VALID_FROM = datetime(1900, 1, 2, tzinfo=timezone.utc)
VALID_TO = datetime(2049, 12, 31, tzinfo=timezone.utc)
AU_KM = 149_597_870.7
SPEED_OF_LIGHT_KM_S = 299_792.458

# Codici Horizons accettati, come in src/astronomy.py.
TARGETS = {"10": "sun", "399": "earth", "sun": "sun", "earth": "earth"}


class LocalEphemerisError(RuntimeError):
    """Kernel mancanti o richiesta fuori dall'intervallo di validità."""


@lru_cache(maxsize=1)
def _load():
    try:
        from skyfield.api import Loader
        from skyfield.planetarylib import PlanetaryConstants
    except ImportError as exc:  # pragma: no cover - dipende dall'ambiente
        raise LocalEphemerisError("Skyfield non installato (requirements-dev.txt).") from exc

    needed = [DE421_PATH] + [KERNEL_DIR / name for name in (
        "moon_080317.tf", "pck00008.tpc", "moon_pa_de421_1900-2050.bpc")]
    missing = [str(p) for p in needed if not p.is_file()]
    if missing:
        raise LocalEphemerisError(f"Kernel SPICE mancanti: {', '.join(missing)}")

    kernels = Loader(str(KERNEL_DIR), verbose=False)
    timescale = kernels.timescale(builtin=True)
    ephemeris = Loader(str(DE421_PATH.parent), verbose=False)(DE421_PATH.name)
    constants = PlanetaryConstants()
    constants.read_text(kernels("moon_080317.tf"))
    constants.read_text(kernels("pck00008.tpc"))
    constants.read_binary(kernels("moon_pa_de421_1900-2050.bpc"))
    frame = constants.build_frame_named(FRAME_NAME)
    return timescale, ephemeris, constants, frame


def light_time_s(distance_au: float) -> float:
    """Tempo di propagazione a senso unico per una distanza in UA."""
    return float(distance_au) * AU_KM / SPEED_OF_LIGHT_KM_S


def observe(target: str, latitude_deg: float, longitude_east_deg: float,
            times_utc: list[datetime]) -> list[Observation]:
    """Azimut/elevazione apparenti di Sole o Terra per un osservatore sulla superficie lunare."""
    body = TARGETS.get(str(target).lower())
    if body is None:
        raise ValueError(f"Bersaglio non supportato: {target!r} (usare 10/sun o 399/earth)")
    if not -90 <= latitude_deg <= 90 or not -360 <= longitude_east_deg <= 360:
        raise ValueError("Coordinate del sito fuori intervallo.")
    if not times_utc:
        return []
    for moment in times_utc:
        if moment.tzinfo is None:
            raise ValueError("I tempi devono avere un fuso orario.")
        if not VALID_FROM <= moment <= VALID_TO:
            raise LocalEphemerisError(
                f"{moment.isoformat()} fuori dall'intervallo del kernel di orientamento (1900-2050).")

    timescale, ephemeris, constants, frame = _load()
    place = ephemeris["moon"] + constants.build_latlon_degrees(
        frame, float(latitude_deg), float(longitude_east_deg))
    t = timescale.from_datetimes([m.astimezone(timezone.utc) for m in times_utc])
    astrometric = place.at(t).observe(ephemeris[body])
    apparent = astrometric.apparent()
    altitude, azimuth, distance = apparent.altaz()
    # Velocità radiale: derivata numerica della distanza su ±30 s.
    dt = 30.0 / 86400.0
    before = place.at(timescale.tt_jd(t.tt - dt)).observe(ephemeris[body]).apparent().distance().km
    after = place.at(timescale.tt_jd(t.tt + dt)).observe(ephemeris[body]).apparent().distance().km
    rate = (after - before) / 60.0

    result = []
    for i, moment in enumerate(times_utc):
        result.append(Observation(
            time_utc=moment.astimezone(timezone.utc).isoformat(),
            azimuth_deg=float(azimuth.degrees[i]) % 360.0,
            elevation_deg=float(altitude.degrees[i]),
            distance_au=float(distance.au[i]),
            range_rate_km_s=float(rate[i]),
        ))
    return result


def time_grid(start_utc: datetime, hours: float, step_minutes: float) -> list[datetime]:
    if start_utc.tzinfo is None:
        raise ValueError("start_utc deve avere un fuso orario.")
    if hours <= 0 or step_minutes <= 0:
        raise ValueError("hours e step_minutes devono essere positivi.")
    count = int(round(hours * 60.0 / step_minutes))
    return [start_utc + timedelta(minutes=step_minutes * i) for i in range(count + 1)]


def query_observations_local(target: str, latitude: float, longitude: float,
                             start_utc: datetime, hours: float = 48,
                             step_minutes: float = 60.0) -> list[Observation]:
    """Equivalente offline di ``astronomy.query_observations``."""
    return observe(target, latitude, longitude, time_grid(start_utc, hours, step_minutes))


def provenance() -> dict:
    return {
        "source": "skyfield+spice-local",
        "ephemeris": "JPL DE421 (de421.bsp)",
        "orientation": "moon_pa_de421_1900-2050.bpc",
        "frame": FRAME_NAME,
        "frame_kernel": "moon_080317.tf",
        "constants": "pck00008.tpc",
        "valid_utc": [VALID_FROM.isoformat(), VALID_TO.isoformat()],
        "azimuth_convention": "clockwise from local north",
        "elevation": "apparent, geometric horizon, no refraction",
    }
