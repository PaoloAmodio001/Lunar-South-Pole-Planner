"""Solar Energy Engine: produzione fotovoltaica e bilancio energetico del rover.

Modello ingegneristico PRELIMINARE, non validato scientificamente né
qualificato per operazioni reali.

Il modulo non introduce nuove osservazioni né nuovi modelli astronomici:
riusa i report già prodotti dalla pipeline.

- Astronomy (``lunar-astronomy-observations/1.0``): elevazione, azimut e
  distanza osservatore–Sole (``distance_au``) da JPL Horizons.
- Illumination (``lunar-solar-illumination-diagnostic/1.0``): visibilità
  diretta del Sole stimata sul profilo d'orizzonte DEM.
- Rover Energy (``lunar-rover-energy-assessment/1.0``, opzionale): energia di
  trazione del percorso, distribuita sugli intervalli di guida pianificati.

Le caratteristiche hardware (pannelli, batteria, carichi) devono essere
fornite esplicitamente nella configurazione. Se mancano, il report viene
comunque scritto ma è dichiarato parziale e le grandezze che ne dipendono
restano ``null``: nessun valore viene inventato.

Catena di conversione (per campione):

    G      = S0 / d_AU^2                         irradianza fuori atmosfera [W/m^2]
    cos_i  = max(0, sin(el)cos(tilt) + cos(el)sin(tilt)cos(az_sun - az_panel))
    P_dc   = G * A * eta_cell * cos_i * (1 - dust) * (1 - degradation) * f_thermal
    P_use  = min(P_dc * (1 - system_losses), max_output_w)

``P_use`` vale 0 quando il Sole non è visibile secondo l'analisi di
illuminazione: la visibilità è condizione necessaria, non sufficiente, per la
produzione.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import math

from src.mission_decision_engine import (
    STEP_TOLERANCE_FACTOR,
    _number,
    _timestamp,
    resolve_expected_step,
)


SCHEMA = "lunar-solar-energy-budget/1.0"

EXPECTED_SCHEMAS = {
    "astronomy": "lunar-astronomy-observations/1.0",
    "illumination": "lunar-solar-illumination-diagnostic/1.0",
    "rover_energy": "lunar-rover-energy-assessment/1.0",
}

# Irradianza solare totale a 1 UA: 1360.8 ± 0.5 W/m^2 (minimo solare 2008).
# Fonte: Kopp G., Lean J. L. (2011), "A new, lower value of total solar
# irradiance: Evidence and climate significance", Geophys. Res. Lett. 38,
# L01706, doi:10.1029/2010GL045777. Sovrascrivibile con
# ``solar_energy.solar_constant_w_m2``. Non è una caratteristica del rover.
DEFAULT_SOLAR_CONSTANT_W_M2 = 1360.8
SOLAR_CONSTANT_REFERENCE = (
    "Kopp & Lean (2011), Geophys. Res. Lett. 38, L01706, "
    "doi:10.1029/2010GL045777"
)

ORIENTATION_MODES = ("fixed", "azimuth_tracking", "two_axis_tracking")
LOAD_CATEGORIES = ("auxiliary", "science", "communications")
OPTIONAL_LOAD_CATEGORIES = ("thermal_control",)
ALL_CATEGORIES = ("traction",) + LOAD_CATEGORIES + OPTIONAL_LOAD_CATEGORIES

SECONDS_PER_HOUR = 3600.0


# --------------------------------------------------------------------------- #
# Lettura e validazione degli input
# --------------------------------------------------------------------------- #
def _read_report(path, source_name):
    if not path:
        return None, "not_configured"
    source = Path(path)
    if not source.is_file():
        return None, "file_missing"
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, "invalid_report"
    expected = EXPECTED_SCHEMAS[source_name]
    actual = data.get("schema")
    if actual != expected:
        return None, f"invalid_schema: expected {expected}, received {actual}"
    return data, None


def _section(cfg, key):
    value = cfg.get(key) if isinstance(cfg, dict) else None
    return value if isinstance(value, dict) else {}


class _Inputs:
    """Raccoglie parametri mancanti, non validi e la loro provenienza."""

    def __init__(self):
        self.missing = []
        self.invalid = []
        self.sources = {}

    def number(self, cfg, key, path, *, minimum=None, maximum=None,
               min_inclusive=True, max_inclusive=True, required=True,
               fallback=None, fallback_source=None):
        raw = cfg.get(key) if isinstance(cfg, dict) else None
        source = "configuration"
        if raw is None and fallback is not None:
            raw, source = fallback, fallback_source
        if raw is None:
            if required:
                self.missing.append({
                    "parameter": path,
                    "reason": "Parametro non configurato.",
                })
            return None

        value = _number(raw)
        reason = None
        if value is None:
            reason = "Valore non numerico o non finito."
        elif minimum is not None and (
            value < minimum or (not min_inclusive and value == minimum)
        ):
            reason = (
                f"Deve essere {'>=' if min_inclusive else '>'} {minimum}."
            )
        elif maximum is not None and (
            value > maximum or (not max_inclusive and value == maximum)
        ):
            reason = (
                f"Deve essere {'<=' if max_inclusive else '<'} {maximum}."
            )
        if reason:
            self.invalid.append({"parameter": path, "value": raw, "reason": reason})
            return None

        self.sources[path] = source
        return value

    def flag_missing(self, path, reason):
        self.missing.append({"parameter": path, "reason": reason})

    def flag_invalid(self, path, value, reason):
        self.invalid.append({"parameter": path, "value": value, "reason": reason})


def _parse_array(cfg, inputs):
    array_cfg = _section(cfg, "solar_array")
    base = "solar_energy.solar_array"

    area = inputs.number(array_cfg, "area_m2", f"{base}.area_m2",
                         minimum=0, min_inclusive=False)
    efficiency = inputs.number(array_cfg, "cell_efficiency",
                               f"{base}.cell_efficiency",
                               minimum=0, maximum=1, min_inclusive=False)
    system_loss = inputs.number(array_cfg, "system_loss_fraction",
                                f"{base}.system_loss_fraction",
                                minimum=0, maximum=1, max_inclusive=False)
    dust_loss = inputs.number(array_cfg, "dust_loss_fraction",
                              f"{base}.dust_loss_fraction",
                              minimum=0, maximum=1)
    degradation = inputs.number(array_cfg, "degradation_fraction",
                                f"{base}.degradation_fraction",
                                minimum=0, maximum=1)
    max_output = inputs.number(array_cfg, "max_output_w",
                               f"{base}.max_output_w",
                               minimum=0, min_inclusive=False, required=False)

    mode = array_cfg.get("orientation_mode")
    tilt = azimuth = None
    if mode is None:
        inputs.flag_missing(f"{base}.orientation_mode",
                            "Orientamento dei pannelli non configurato.")
    elif mode not in ORIENTATION_MODES:
        inputs.flag_invalid(f"{base}.orientation_mode", mode,
                            f"Valori ammessi: {', '.join(ORIENTATION_MODES)}.")
        mode = None
    else:
        if mode in ("fixed", "azimuth_tracking"):
            tilt = inputs.number(array_cfg, "tilt_deg", f"{base}.tilt_deg",
                                 minimum=0, maximum=180)
        if mode == "fixed":
            azimuth = inputs.number(array_cfg, "azimuth_deg",
                                    f"{base}.azimuth_deg",
                                    minimum=0, maximum=360, max_inclusive=False)

    thermal_cfg = array_cfg.get("thermal")
    thermal = None
    thermal_status = "not_configured"
    if isinstance(thermal_cfg, dict) and any(
        thermal_cfg.get(key) is not None
        for key in ("temperature_coefficient_per_c", "cell_temperature_c",
                    "reference_temperature_c")
    ):
        coefficient = inputs.number(
            thermal_cfg, "temperature_coefficient_per_c",
            f"{base}.thermal.temperature_coefficient_per_c",
        )
        cell_temp = inputs.number(
            thermal_cfg, "cell_temperature_c",
            f"{base}.thermal.cell_temperature_c", minimum=-273.15,
        )
        reference = inputs.number(
            thermal_cfg, "reference_temperature_c",
            f"{base}.thermal.reference_temperature_c", minimum=-273.15,
        )
        if None not in (coefficient, cell_temp, reference):
            factor = 1.0 + coefficient * (cell_temp - reference)
            if factor < 0:
                inputs.flag_invalid(
                    f"{base}.thermal", thermal_cfg,
                    "Il fattore termico risultante è negativo.",
                )
                thermal_status = "invalid"
            else:
                thermal = {
                    "temperature_coefficient_per_c": coefficient,
                    "cell_temperature_c": cell_temp,
                    "reference_temperature_c": reference,
                    "factor": factor,
                }
                thermal_status = "applied_constant_cell_temperature"
        else:
            thermal_status = "incomplete"

    complete = None not in (
        area, efficiency, system_loss, dust_loss, degradation, mode,
    ) and (mode == "two_axis_tracking" or tilt is not None) and (
        mode != "fixed" or azimuth is not None
    ) and thermal_status in ("not_configured", "applied_constant_cell_temperature")

    return {
        "complete": complete,
        "area_m2": area,
        "cell_efficiency": efficiency,
        "orientation_mode": mode,
        "tilt_deg": tilt,
        "azimuth_deg": azimuth,
        "system_loss_fraction": system_loss,
        "dust_loss_fraction": dust_loss,
        "degradation_fraction": degradation,
        "max_output_w": max_output,
        "thermal": thermal,
        "thermal_status": thermal_status,
    }


def _parse_battery(cfg, energy_cfg, inputs):
    battery_cfg = _section(cfg, "battery")
    base = "solar_energy.battery"
    energy_cfg = energy_cfg if isinstance(energy_cfg, dict) else {}

    capacity = inputs.number(
        battery_cfg, "capacity_wh", f"{base}.capacity_wh",
        minimum=0, min_inclusive=False,
        fallback=energy_cfg.get("battery_capacity_wh"),
        fallback_source="energy.battery_capacity_wh",
    )
    reserve_fallback = _number(energy_cfg.get("reserve_percent"))
    reserve = inputs.number(
        battery_cfg, "min_reserve_fraction", f"{base}.min_reserve_fraction",
        minimum=0, maximum=1, max_inclusive=False,
        fallback=(
            reserve_fallback / 100.0 if reserve_fallback is not None else None
        ),
        fallback_source="energy.reserve_percent",
    )
    initial = inputs.number(
        battery_cfg, "initial_soc_fraction", f"{base}.initial_soc_fraction",
        minimum=0, maximum=1,
    )
    charge_eff = inputs.number(
        battery_cfg, "charge_efficiency", f"{base}.charge_efficiency",
        minimum=0, maximum=1, min_inclusive=False,
    )
    discharge_eff = inputs.number(
        battery_cfg, "discharge_efficiency", f"{base}.discharge_efficiency",
        minimum=0, maximum=1, min_inclusive=False,
    )
    complete = None not in (capacity, reserve, initial, charge_eff, discharge_eff)
    return {
        "complete": complete,
        "capacity_wh": capacity,
        "min_reserve_fraction": reserve,
        "reserve_wh": capacity * reserve if complete else None,
        "initial_soc_fraction": initial,
        "initial_soc_wh": capacity * initial if complete else None,
        "charge_efficiency": charge_eff,
        "discharge_efficiency": discharge_eff,
    }


def _parse_utc(value):
    normalized = _timestamp(value)
    return datetime.fromisoformat(normalized) if normalized else None


def _parse_consumption(cfg, energy_cfg, rover_energy, inputs):
    consumption_cfg = _section(cfg, "consumption")
    base = "solar_energy.consumption"
    energy_cfg = energy_cfg if isinstance(energy_cfg, dict) else {}

    modes_cfg = consumption_cfg.get("modes")
    default_mode = consumption_cfg.get("default_mode")
    raw_schedule = consumption_cfg.get("schedule", [])

    if not isinstance(modes_cfg, dict) or not modes_cfg:
        inputs.flag_missing(f"{base}.modes",
                            "Nessuna modalità operativa configurata.")
        modes_cfg = {}
    if default_mode is None:
        inputs.flag_missing(f"{base}.default_mode",
                            "Modalità predefinita (soste) non configurata.")
    elif default_mode not in modes_cfg:
        inputs.flag_invalid(f"{base}.default_mode", default_mode,
                            "La modalità predefinita non è definita in modes.")
        default_mode = None

    schedule = []
    schedule_valid = True
    if raw_schedule is None:
        raw_schedule = []
    if not isinstance(raw_schedule, list):
        inputs.flag_invalid(f"{base}.schedule", raw_schedule,
                            "Deve essere una lista di intervalli.")
        raw_schedule, schedule_valid = [], False

    for index, entry in enumerate(raw_schedule):
        path = f"{base}.schedule[{index}]"
        if not isinstance(entry, dict):
            inputs.flag_invalid(path, entry, "Deve essere un oggetto.")
            schedule_valid = False
            continue
        start = _parse_utc(entry.get("start_utc"))
        end = _parse_utc(entry.get("end_utc"))
        mode = entry.get("mode")
        if start is None or end is None or end <= start:
            inputs.flag_invalid(
                path, entry,
                "start_utc/end_utc mancanti, senza fuso orario o non ordinati.",
            )
            schedule_valid = False
            continue
        if mode not in modes_cfg:
            inputs.flag_invalid(path, entry,
                                f"Modalità non definita in modes: {mode!r}.")
            schedule_valid = False
            continue
        schedule.append({"start": start, "end": end, "mode": mode})

    schedule.sort(key=lambda item: item["start"])
    for previous, current in zip(schedule, schedule[1:]):
        if current["start"] < previous["end"]:
            inputs.flag_invalid(
                f"{base}.schedule", None,
                "Intervalli sovrapposti: "
                f"{previous['start'].isoformat()}–{previous['end'].isoformat()} e "
                f"{current['start'].isoformat()}–{current['end'].isoformat()}.",
            )
            schedule_valid = False

    used_modes = {item["mode"] for item in schedule}
    if default_mode is not None:
        used_modes.add(default_mode)

    modes = {}
    modes_valid = True
    auxiliary_fallback = energy_cfg.get("auxiliary_power_w")
    for name in sorted(used_modes):
        mode_cfg = modes_cfg.get(name)
        path = f"{base}.modes.{name}"
        if not isinstance(mode_cfg, dict):
            inputs.flag_invalid(path, mode_cfg, "Deve essere un oggetto.")
            modes_valid = False
            continue
        powers = {}
        for category in LOAD_CATEGORIES:
            value = inputs.number(
                mode_cfg, f"{category}_w", f"{path}.{category}_w", minimum=0,
                fallback=auxiliary_fallback if category == "auxiliary" else None,
                fallback_source="energy.auxiliary_power_w",
            )
            if value is None:
                modes_valid = False
            powers[category] = value
        for category in OPTIONAL_LOAD_CATEGORIES:
            powers[category] = inputs.number(
                mode_cfg, f"{category}_w", f"{path}.{category}_w",
                minimum=0, required=False,
            )
        traction = mode_cfg.get("traction", False)
        if not isinstance(traction, bool):
            inputs.flag_invalid(f"{path}.traction", traction,
                                "Deve essere true o false.")
            modes_valid = False
            traction = False
        modes[name] = {"power_w": powers, "traction": traction}

    # Trazione: potenza esplicita oppure energia del report Rover Energy
    # distribuita uniformemente sul tempo di guida pianificato.
    traction_modes = {name for name, mode in modes.items() if mode["traction"]}
    scheduled_drive_s = sum(
        (item["end"] - item["start"]).total_seconds()
        for item in schedule if item["mode"] in traction_modes
    )
    traction = {
        "power_w": None,
        "source": None,
        "route_energy_wh": None,
        "scheduled_drive_hours": scheduled_drive_s / SECONDS_PER_HOUR,
    }
    explicit_traction = inputs.number(
        consumption_cfg, "traction_power_w", f"{base}.traction_power_w",
        minimum=0, required=False,
    )
    traction_valid = True
    if traction_modes:
        if explicit_traction is not None:
            traction["power_w"] = explicit_traction
            traction["source"] = "configuration"
        else:
            route_wh = _number(
                _section(rover_energy, "energy_wh").get(
                    "traction_after_drivetrain"
                )
            )
            if route_wh is None:
                inputs.flag_missing(
                    f"{base}.traction_power_w",
                    "Trazione pianificata ma senza potenza configurata né "
                    "report Rover Energy valido.",
                )
                traction_valid = False
            elif default_mode in traction_modes:
                inputs.flag_invalid(
                    f"{base}.default_mode", default_mode,
                    "Con energia di trazione da Rover Energy la modalità "
                    "predefinita non può includere trazione: il tempo di "
                    "guida non sarebbe determinabile.",
                )
                traction_valid = False
            elif scheduled_drive_s <= 0:
                inputs.flag_missing(
                    f"{base}.schedule",
                    "Energia di trazione disponibile ma nessun intervallo di "
                    "guida pianificato.",
                )
                traction_valid = False
            else:
                traction["route_energy_wh"] = route_wh
                traction["power_w"] = route_wh / (
                    scheduled_drive_s / SECONDS_PER_HOUR
                )
                traction["source"] = "rover_energy_report"
    else:
        traction["power_w"] = 0.0
        traction["source"] = "no_traction_mode_scheduled"

    complete = (
        default_mode is not None and schedule_valid and modes_valid
        and traction_valid and bool(modes)
    )
    return {
        "complete": complete,
        "default_mode": default_mode,
        "modes": modes,
        "schedule": schedule,
        "traction": traction,
    }


# --------------------------------------------------------------------------- #
# Modello fisico
# --------------------------------------------------------------------------- #
def _incidence_cosine(array, sun_elevation_deg, sun_azimuth_deg):
    mode = array["orientation_mode"]
    if mode == "two_axis_tracking":
        return 1.0
    if mode is None or array["tilt_deg"] is None:
        return None
    elevation = math.radians(sun_elevation_deg)
    tilt = math.radians(array["tilt_deg"])
    if mode == "azimuth_tracking":
        delta_azimuth = 0.0
    else:
        if array["azimuth_deg"] is None:
            return None
        delta_azimuth = math.radians(sun_azimuth_deg - array["azimuth_deg"])
    cosine = (
        math.sin(elevation) * math.cos(tilt)
        + math.cos(elevation) * math.sin(tilt) * math.cos(delta_azimuth)
    )
    return max(0.0, cosine)


def _sample_production(row, visible, array, solar_constant, allow_distance_fallback):
    """Produzione istantanea per un campione; None dove non determinabile."""
    elevation = _number(row.get("elevation_deg"))
    azimuth = _number(row.get("azimuth_deg"))
    distance = _number(row.get("distance_au"))
    if distance is not None and distance <= 0:
        distance = None

    result = {
        "sun_elevation_deg": elevation,
        "sun_azimuth_deg": azimuth,
        "distance_au": distance,
        "distance_source": "horizons" if distance is not None else None,
        "direct_sun_visible": visible,
        "irradiance_w_m2": None,
        "incidence_cosine": None,
        "plane_of_array_irradiance_w_m2": None,
        "array_power_before_losses_w": None,
        "usable_power_w": None,
        "production_status": None,
    }

    if elevation is None or azimuth is None:
        result["production_status"] = "missing_solar_geometry"
        return result

    if distance is None and allow_distance_fallback:
        distance = 1.0
        result["distance_source"] = "assumed_1_au"
    if distance is not None:
        result["irradiance_w_m2"] = solar_constant / distance ** 2

    result["incidence_cosine"] = _incidence_cosine(array, elevation, azimuth)

    if visible is None:
        result["production_status"] = "missing_illumination"
        return result
    if not array["complete"]:
        result["production_status"] = "missing_array_parameters"
        return result
    if visible is False:
        # Sole occultato dal terreno: nessuna produzione da irradianza diretta.
        result["plane_of_array_irradiance_w_m2"] = 0.0
        result["array_power_before_losses_w"] = 0.0
        result["usable_power_w"] = 0.0
        result["production_status"] = "estimated_shadowed"
        return result
    if result["irradiance_w_m2"] is None:
        result["production_status"] = "missing_distance"
        return result

    poa = result["irradiance_w_m2"] * result["incidence_cosine"]
    thermal_factor = array["thermal"]["factor"] if array["thermal"] else 1.0
    raw_power = poa * array["area_m2"] * array["cell_efficiency"]
    derated = (
        raw_power
        * (1.0 - array["dust_loss_fraction"])
        * (1.0 - array["degradation_fraction"])
        * thermal_factor
    )
    usable = derated * (1.0 - array["system_loss_fraction"])
    if array["max_output_w"] is not None:
        usable = min(usable, array["max_output_w"])

    result["plane_of_array_irradiance_w_m2"] = poa
    result["array_power_before_losses_w"] = raw_power
    result["usable_power_w"] = usable
    result["production_status"] = (
        "estimated_illuminated" if usable > 0 else "estimated_zero_incidence"
    )
    return result


def _mode_seconds(start, end, consumption):
    """Secondi trascorsi in ogni modalità nell'intervallo [start, end)."""
    seconds = {}
    covered = 0.0
    for item in consumption["schedule"]:
        overlap_start = max(start, item["start"])
        overlap_end = min(end, item["end"])
        if overlap_end > overlap_start:
            value = (overlap_end - overlap_start).total_seconds()
            seconds[item["mode"]] = seconds.get(item["mode"], 0.0) + value
            covered += value
    remaining = (end - start).total_seconds() - covered
    if remaining > 0:
        default = consumption["default_mode"]
        seconds[default] = seconds.get(default, 0.0) + remaining
    return seconds


def _interval_consumption(start, end, consumption):
    if not consumption["complete"]:
        return None, None
    mode_seconds = _mode_seconds(start, end, consumption)
    energy = {category: 0.0 for category in ALL_CATEGORIES}
    for mode_name, seconds in mode_seconds.items():
        mode = consumption["modes"][mode_name]
        hours = seconds / SECONDS_PER_HOUR
        for category in LOAD_CATEGORIES + OPTIONAL_LOAD_CATEGORIES:
            power = mode["power_w"].get(category)
            if power is not None:
                energy[category] += power * hours
        if mode["traction"]:
            energy["traction"] += consumption["traction"]["power_w"] * hours
    energy["total"] = sum(energy[category] for category in ALL_CATEGORIES)
    mode_hours = {
        name: seconds / SECONDS_PER_HOUR for name, seconds in mode_seconds.items()
    }
    return energy, mode_hours


def _step_battery(soc_wh, net_wh, battery):
    """Aggiorna lo stato di carica; la riserva è un vincolo di pianificazione."""
    capacity = battery["capacity_wh"]
    if net_wh >= 0:
        stored = net_wh * battery["charge_efficiency"]
        accepted = min(stored, capacity - soc_wh)
        curtailed = (stored - accepted) / battery["charge_efficiency"]
        return soc_wh + accepted, accepted, 0.0, curtailed, 0.0
    required = -net_wh / battery["discharge_efficiency"]
    drawn = min(required, soc_wh)
    unmet = (required - drawn) * battery["discharge_efficiency"]
    return soc_wh - drawn, 0.0, drawn, 0.0, unmet


def _group_runs(intervals, predicate, energy_key=None):
    runs = []
    current = None
    for item in intervals:
        hit = predicate(item)
        if hit and current is not None and current["end_utc"] == item["start_utc"]:
            current["end_utc"] = item["end_utc"]
            current["interval_count"] += 1
            current["duration_hours"] += item["duration_hours"]
            if energy_key:
                current["energy_wh"] += abs(item[energy_key] or 0.0)
        elif hit:
            current = {
                "start_utc": item["start_utc"],
                "end_utc": item["end_utc"],
                "interval_count": 1,
                "duration_hours": item["duration_hours"],
            }
            if energy_key:
                current["energy_wh"] = abs(item[energy_key] or 0.0)
            runs.append(current)
        else:
            current = None
    return runs


# --------------------------------------------------------------------------- #
# Motore principale
# --------------------------------------------------------------------------- #
def build_solar_energy_budget(
    *,
    astronomy_path=None,
    illumination_path=None,
    rover_energy_path=None,
    solar_config=None,
    energy_config=None,
    expected_step_seconds=None,
    output_path,
):
    """Calcola produzione solare e bilancio energetico nel tempo.

    Scrive sempre un report (anche parziale) e ne restituisce un riepilogo.
    """
    cfg = solar_config if isinstance(solar_config, dict) else {}
    inputs = _Inputs()

    astronomy, astronomy_error = _read_report(astronomy_path, "astronomy")
    illumination, illumination_error = _read_report(
        illumination_path, "illumination"
    )
    rover_energy, rover_energy_error = _read_report(
        rover_energy_path, "rover_energy"
    )

    solar_constant = inputs.number(
        cfg, "solar_constant_w_m2", "solar_energy.solar_constant_w_m2",
        minimum=0, min_inclusive=False,
        fallback=DEFAULT_SOLAR_CONSTANT_W_M2,
        fallback_source=f"default: {SOLAR_CONSTANT_REFERENCE}",
    )
    allow_distance_fallback = cfg.get("allow_1au_distance_fallback", False) is True

    array = _parse_array(cfg, inputs)
    battery = _parse_battery(cfg, energy_config, inputs)
    consumption = _parse_consumption(cfg, energy_config, rover_energy, inputs)

    if astronomy is None:
        inputs.flag_missing("astronomy_report",
                            f"Report astronomico non disponibile: {astronomy_error}.")
    if illumination is None:
        inputs.flag_missing("illumination_report",
                            "Report di illuminazione non disponibile: "
                            f"{illumination_error}.")

    (
        step_seconds, step_source, _parameter_step, _report_step, step_warnings,
    ) = resolve_expected_step(expected_step_seconds, astronomy)

    # Serie del Sole e visibilità diretta indicizzate per timestamp UTC.
    sun_rows = {}
    invalid_sun_rows = 0
    observations = (astronomy or {}).get("observations")
    raw_sun = observations.get("Sun") if isinstance(observations, dict) else None
    for row in raw_sun if isinstance(raw_sun, list) else []:
        timestamp = _timestamp(row.get("time_utc")) if isinstance(row, dict) else None
        if timestamp and timestamp not in sun_rows:
            sun_rows[timestamp] = row
        else:
            invalid_sun_rows += 1

    visibility = {}
    illumination_rows = (illumination or {}).get("observations")
    for row in illumination_rows if isinstance(illumination_rows, list) else []:
        if not isinstance(row, dict):
            continue
        timestamp = _timestamp(row.get("time_utc"))
        value = row.get("estimated_direct_sun_visible")
        if timestamp and isinstance(value, bool):
            visibility[timestamp] = value

    ordered_times = sorted(sun_rows)
    samples = []
    for timestamp in ordered_times:
        if solar_constant is not None:
            production = _sample_production(
                sun_rows[timestamp], visibility.get(timestamp), array,
                solar_constant, allow_distance_fallback,
            )
        else:
            production = {
                "production_status": "invalid_solar_constant",
                "usable_power_w": None,
            }
        samples.append({"time_utc": timestamp, **production})

    # Integrazione temporale (mantenimento di ordine zero sul campione
    # iniziale di ciascun intervallo, senza interpolazione).
    gap_limit = (
        step_seconds * STEP_TOLERANCE_FACTOR if step_seconds is not None else None
    )
    soc_wh = battery["initial_soc_wh"] if battery["complete"] else None
    soc_break_reason = None if soc_wh is not None else "battery_parameters_missing"
    soc_break_utc = None
    reserve_wh = battery["reserve_wh"]

    if samples:
        samples[0]["soc_wh"] = soc_wh

    intervals = []
    for index in range(len(samples) - 1):
        first, second = samples[index], samples[index + 1]
        start = datetime.fromisoformat(first["time_utc"])
        end = datetime.fromisoformat(second["time_utc"])
        seconds = (end - start).total_seconds()
        hours = seconds / SECONDS_PER_HOUR

        interval = {
            "start_utc": first["time_utc"],
            "end_utc": second["time_utc"],
            "duration_hours": hours,
            "status": None,
            "usable_power_w": first.get("usable_power_w"),
            "production_wh": None,
            "consumption_wh": None,
            "mode_hours": None,
            "net_wh": None,
            "battery_charge_wh": None,
            "battery_discharge_wh": None,
            "curtailed_wh": None,
            "unmet_load_wh": None,
            "soc_start_wh": soc_wh,
            "soc_end_wh": None,
            "soc_end_fraction": None,
            "reserve_margin_end_wh": None,
            "below_reserve": None,
        }

        if gap_limit is not None and seconds > gap_limit:
            interval["status"] = "temporal_gap"
        else:
            if first.get("usable_power_w") is not None:
                interval["production_wh"] = first["usable_power_w"] * hours
            energy, mode_hours = _interval_consumption(start, end, consumption)
            interval["consumption_wh"] = energy
            interval["mode_hours"] = mode_hours

            if interval["production_wh"] is None:
                interval["status"] = first.get("production_status")
            elif energy is None:
                interval["status"] = "missing_consumption_parameters"
            else:
                interval["net_wh"] = interval["production_wh"] - energy["total"]
                interval["status"] = (
                    "estimated" if gap_limit is not None
                    else "estimated_continuity_not_verifiable"
                )

        if interval["net_wh"] is not None and soc_wh is not None:
            soc_wh, charged, discharged, curtailed, unmet = _step_battery(
                soc_wh, interval["net_wh"], battery
            )
            interval.update({
                "battery_charge_wh": charged,
                "battery_discharge_wh": discharged,
                "curtailed_wh": curtailed,
                "unmet_load_wh": unmet,
                "soc_end_wh": soc_wh,
                "soc_end_fraction": soc_wh / battery["capacity_wh"],
                "reserve_margin_end_wh": soc_wh - reserve_wh,
                "below_reserve": soc_wh < reserve_wh,
            })
        else:
            if soc_wh is not None:
                soc_break_reason = interval["status"]
                soc_break_utc = interval["start_utc"]
            soc_wh = None
        second["soc_wh"] = soc_wh
        intervals.append(interval)

    # Stato per campione, usato dal Mission Decision Engine.
    for index, sample in enumerate(samples):
        soc = sample.get("soc_wh")
        sample["soc_fraction"] = (
            soc / battery["capacity_wh"] if soc is not None else None
        )
        sample["reserve_margin_wh"] = (
            soc - reserve_wh if soc is not None else None
        )
        following = intervals[index] if index < len(intervals) else None
        if soc is None:
            sustainable = None
        elif soc < reserve_wh:
            sustainable = False
        elif following is None:
            sustainable = True
        elif following["below_reserve"] is None:
            sustainable = None
        else:
            sustainable = (
                not following["below_reserve"]
                and (following["unmet_load_wh"] or 0.0) == 0.0
            )
        sample["energy_sustainable"] = sustainable

    # ------------------------------------------------------------------ #
    # Riepiloghi
    # ------------------------------------------------------------------ #
    computed = [item for item in intervals if item["net_wh"] is not None]
    soc_computed = [item for item in intervals if item["soc_end_wh"] is not None]
    status_counts = {}
    for item in intervals:
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
    production_status_counts = {}
    for sample in samples:
        key = sample.get("production_status")
        production_status_counts[key] = production_status_counts.get(key, 0) + 1

    def total(key):
        values = [item[key] for item in intervals if item[key] is not None]
        return sum(values) if values else None

    consumption_by_category = None
    if computed:
        consumption_by_category = {
            category: sum(item["consumption_wh"][category] for item in computed)
            for category in ALL_CATEGORIES + ("total",)
        }

    evaluated_hours = sum(item["duration_hours"] for item in computed)
    production_evaluated = sum(item["production_wh"] for item in computed)
    mean_load_w = (
        consumption_by_category["total"] / evaluated_hours
        if consumption_by_category and evaluated_hours > 0 else None
    )
    peak_load_w = max(
        (item["consumption_wh"]["total"] / item["duration_hours"]
         for item in computed if item["duration_hours"] > 0),
        default=None,
    )

    soc_values = [battery["initial_soc_wh"]] + [
        item["soc_end_wh"] for item in soc_computed
    ] if soc_computed else []
    final_soc = soc_computed[-1]["soc_end_wh"] if soc_computed else None

    first_reserve_violation = next(
        (item for item in soc_computed if item["below_reserve"]), None
    )
    simulation_start = (
        datetime.fromisoformat(samples[0]["time_utc"]) if samples else None
    )

    def battery_only_hours(soc, load_w):
        if soc is None or load_w is None or load_w <= 0 or reserve_wh is None:
            return None
        return max(0.0, soc - reserve_wh) * battery["discharge_efficiency"] / load_w

    autonomy = {
        "time_to_reserve_hours": (
            (datetime.fromisoformat(first_reserve_violation["end_utc"])
             - simulation_start).total_seconds() / SECONDS_PER_HOUR
            if first_reserve_violation and simulation_start else None
        ),
        "reserve_reached_within_evaluated_period": (
            first_reserve_violation is not None if soc_computed else None
        ),
        "battery_only_hours_from_final_soc_at_mean_load": battery_only_hours(
            final_soc, mean_load_w
        ),
        "battery_only_hours_from_final_soc_at_peak_load": battery_only_hours(
            final_soc, peak_load_w
        ),
        "battery_only_hours_from_initial_soc_at_mean_load": battery_only_hours(
            battery["initial_soc_wh"], mean_load_w
        ),
        "mean_load_w": mean_load_w,
        "peak_interval_load_w": peak_load_w,
        "interpretation": (
            "time_to_reserve_hours deriva dalla simulazione temporale. Le "
            "autonomie 'battery_only' assumono assenza di produzione solare e "
            "carico costante pari al carico medio o al massimo di intervallo "
            "osservato nel periodo valutato; non sono previsioni operative."
        ),
    }

    deficit_intervals = {
        "net_deficit": _group_runs(
            computed, lambda item: item["net_wh"] < 0, "net_wh"
        ),
        "below_reserve": _group_runs(
            soc_computed, lambda item: item["below_reserve"]
        ),
        "unmet_load": _group_runs(
            soc_computed, lambda item: item["unmet_load_wh"] > 0, "unmet_load_wh"
        ),
        "definitions": {
            "net_deficit": "Produzione utilizzabile inferiore al consumo; "
                           "la batteria si scarica.",
            "below_reserve": "Stato di carica sotto la riserva minima configurata.",
            "unmet_load": "Batteria esaurita: parte del carico non è alimentabile.",
        },
    }

    temporal_gap_count = status_counts.get("temporal_gap", 0)
    soc_trace_complete = bool(intervals) and len(soc_computed) == len(intervals)
    has_input_issues = bool(inputs.missing or inputs.invalid)

    if not samples:
        status = "not_computable"
    elif has_input_issues:
        status = "partial_missing_inputs"
    elif not soc_trace_complete or step_seconds is None:
        status = "partial_incomplete_data"
    else:
        status = "preliminary_estimate"

    reserve_ok = (
        None if not soc_computed
        else not any(item["below_reserve"] for item in soc_computed)
    )
    unmet_total = total("unmet_load_wh")
    if not soc_computed:
        sustainability = "not_evaluated"
    elif unmet_total and unmet_total > 0:
        sustainability = "load_not_sustainable"
    elif reserve_ok is False:
        sustainability = "reserve_violated"
    elif soc_trace_complete:
        sustainability = "sustainable_in_evaluated_period"
    else:
        sustainability = "sustainable_in_partial_period"

    not_evaluated = [
        "Luce riflessa dal terreno (albedo) e sorgenti diffuse.",
        "Oscuramento parziale del disco solare vicino all'orizzonte (penombra).",
        "Ombre del rover stesso e di strutture locali sui pannelli.",
        "Temperatura dei pannelli variabile nel tempo (solo valore costante, se configurato).",
        "Dipendenza dell'efficienza dall'angolo di incidenza oltre il coseno.",
        "Comportamento elettrochimico della batteria (curve di tensione, temperatura, invecchiamento, autoscarica).",
        "Limiti di corrente/potenza di carica e scarica della batteria.",
        "Orientamento reale del rover durante la guida (il pannello è riferito al frame azimutale di Horizons).",
    ]
    if array["thermal"] is None:
        not_evaluated.append(
            "Derating termico dei pannelli: parametri termici non configurati."
        )
    if not any(
        mode["power_w"].get("thermal_control") is not None
        for mode in consumption["modes"].values()
    ):
        not_evaluated.append(
            "Consumo di controllo termico (riscaldatori): non configurato."
        )

    payload = {
        "schema": SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "model_validation": {
            "scientifically_validated": False,
            "operationally_qualified": False,
            "note": (
                "Modello ingegneristico preliminare basato su report "
                "diagnostici non certificati; non usare per decisioni "
                "operative."
            ),
        },
        "data_sources": {
            "astronomy": {"available": astronomy is not None,
                          "error": astronomy_error,
                          "path": str(astronomy_path) if astronomy_path else None},
            "illumination": {"available": illumination is not None,
                             "error": illumination_error,
                             "path": str(illumination_path) if illumination_path else None},
            "rover_energy": {"available": rover_energy is not None,
                             "error": rover_energy_error,
                             "path": str(rover_energy_path) if rover_energy_path else None,
                             "used_for_traction": consumption["traction"]["source"]
                             == "rover_energy_report"},
        },
        "parameters": {
            "solar_constant_w_m2": solar_constant,
            "solar_constant_reference": SOLAR_CONSTANT_REFERENCE,
            "allow_1au_distance_fallback": allow_distance_fallback,
            "solar_array": array,
            "battery": battery,
            "consumption": {
                "default_mode": consumption["default_mode"],
                "modes": consumption["modes"],
                "schedule": [
                    {"start_utc": item["start"].isoformat(),
                     "end_utc": item["end"].isoformat(),
                     "mode": item["mode"]}
                    for item in consumption["schedule"]
                ],
                "traction": consumption["traction"],
            },
            "parameter_sources": inputs.sources,
        },
        "missing_inputs": inputs.missing,
        "invalid_inputs": inputs.invalid,
        "assumptions": [
            "Irradianza diretta fuori atmosfera: S0 / d^2 con d distanza osservatore–Sole di JPL Horizons.",
            "Produzione nulla quando l'analisi di illuminazione indica il Sole occultato dal terreno.",
            "La visibilità del Sole è condizione necessaria ma non sufficiente: la produzione dipende da incidenza, area, efficienza e perdite.",
            "Incidenza: coseno tra normale del pannello e direzione del Sole, troncato a zero (nessuna produzione dal retro).",
            "Perdite (polvere, degrado, sistema) applicate come fattori moltiplicativi costanti.",
            "Potenza costante su ciascun intervallo, pari al valore del campione iniziale (mantenimento di ordine zero, nessuna interpolazione).",
            "Consumi per modalità costanti; le modalità seguono la pianificazione configurata, la modalità predefinita copre il tempo non pianificato.",
            "Energia di trazione del report Rover Energy distribuita uniformemente sul tempo di guida pianificato (se non è configurata una potenza esplicita).",
            "La riserva minima è un vincolo di pianificazione: la simulazione segnala la violazione ma non distacca carichi; la batteria non scende sotto 0 Wh.",
            "Il surplus oltre la capacità della batteria è conteggiato come energia non utilizzata (curtailed).",
            "La simulazione dello stato di carica si interrompe al primo intervallo non determinabile (lacuna temporale o dati mancanti) e non riprende.",
        ],
        "time_series": {
            "expected_step_seconds": step_seconds,
            "expected_step_source": step_source,
            "integration_method": "zero_order_hold_on_interval_start_sample",
            "samples": samples,
            "intervals": intervals,
        },
        "summary": {
            "sustainability": sustainability,
            "evaluated_hours": evaluated_hours,
            "observed_span_hours": (
                (datetime.fromisoformat(samples[-1]["time_utc"])
                 - simulation_start).total_seconds() / SECONDS_PER_HOUR
                if len(samples) >= 2 else None
            ),
            "production_wh_all_estimated_intervals": total("production_wh"),
            "production_wh_evaluated": production_evaluated if computed else None,
            "consumption_wh_by_category": consumption_by_category,
            "net_energy_wh": (
                production_evaluated - consumption_by_category["total"]
                if consumption_by_category else None
            ),
            "battery_capacity_wh": battery["capacity_wh"],
            "reserve_wh": reserve_wh,
            "initial_soc_wh": battery["initial_soc_wh"],
            "final_soc_wh": final_soc,
            "final_soc_fraction": (
                final_soc / battery["capacity_wh"] if final_soc is not None else None
            ),
            "min_soc_wh": min(soc_values) if soc_values else None,
            "min_reserve_margin_wh": (
                min(soc_values) - reserve_wh if soc_values else None
            ),
            "final_reserve_available_wh": (
                max(0.0, final_soc - reserve_wh) if final_soc is not None else None
            ),
            "curtailed_wh": total("curtailed_wh"),
            "unmet_load_wh": unmet_total,
            "reserve_respected": reserve_ok,
            "first_reserve_violation_utc": (
                first_reserve_violation["start_utc"]
                if first_reserve_violation else None
            ),
        },
        "deficit_intervals": deficit_intervals,
        "autonomy": autonomy,
        "data_quality": {
            "sample_count": len(samples),
            "interval_count": len(intervals),
            "invalid_or_duplicate_sun_rows": invalid_sun_rows,
            "samples_with_illumination": sum(
                1 for sample in samples if sample.get("direct_sun_visible") is not None
            ),
            "samples_with_horizons_distance": sum(
                1 for sample in samples if sample.get("distance_source") == "horizons"
            ),
            "production_status_counts": production_status_counts,
            "interval_status_counts": status_counts,
            "temporal_gap_count": temporal_gap_count if step_seconds is not None else None,
            "continuity_verifiable": step_seconds is not None and len(samples) >= 2,
            "step_warnings": step_warnings,
            "soc_trace_complete": soc_trace_complete,
            "soc_trace_break_utc": soc_break_utc,
            "soc_trace_break_reason": soc_break_reason if not soc_trace_complete else None,
        },
        "result_classes": {
            "estimated": [
                "Potenza utilizzabile e produzione per campioni con stato 'estimated_*'.",
                "Consumi, energia netta e stato di carica per intervalli con stato 'estimated'.",
            ],
            "missing_data": [
                item["parameter"] for item in inputs.missing
            ] + [
                f"{count} campioni con stato '{name}'"
                for name, count in production_status_counts.items()
                if name and name.startswith("missing")
            ],
            "not_validatable": [
                "Tutti i risultati: nessuna misura di riferimento disponibile per validare il modello.",
                "Offset azimutale e frame di Horizons usati dall'illuminazione non validati indipendentemente.",
                "Parametri hardware forniti dall'utente non verificati dal motore.",
            ],
        },
        "not_evaluated": not_evaluated,
        "limitations": [
            "Modello preliminare non validato scientificamente né qualificato per operazioni reali.",
            "La visibilità diretta del Sole proviene da un profilo d'orizzonte DEM diagnostico.",
            "La risoluzione temporale è quella delle osservazioni astronomiche.",
            "Nessun risultato costituisce autorizzazione operativa.",
        ],
    }

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "status": status,
        "report_file": str(destination),
        "sustainability": sustainability,
        "sample_count": len(samples),
        "estimated_interval_count": len(computed),
        "soc_trace_complete": soc_trace_complete,
        "missing_inputs": [item["parameter"] for item in inputs.missing],
        "invalid_inputs": [item["parameter"] for item in inputs.invalid],
        "production_wh_evaluated": production_evaluated if computed else None,
        "final_soc_wh": final_soc,
        "unmet_load_wh": unmet_total,
    }
