"""Aggregazione conservativa dei risultati scientifici della missione lunare."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import math


SCHEMA = "lunar-mission-decision/1.0"

EXPECTED_SCHEMAS = {
    "astronomy": "lunar-astronomy-observations/1.0",
    "illumination": "lunar-solar-illumination-diagnostic/1.0",
    "visibility": "lunar-astronomical-visibility-diagnostic/1.0",
    "energy": "lunar-rover-energy-assessment/1.0",
    "solar_energy": "lunar-solar-energy-budget/1.0",
}


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


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def _rows(report, key):
    if not isinstance(report, dict):
        return []
    value = report.get(key)
    return value if isinstance(value, list) else []


def _safe_mapping(report, key):
    if not isinstance(report, dict):
        return {}
    value = report.get(key)
    return value if isinstance(value, dict) else {}



# Tolleranza numerica sul confronto intervallo/passo: identica a quella usata da
# mission_orchestrator._diagnose_temporal_continuity (fattore 1.01), così che
# Decision Engine e diagnostica astronomica classifichino le lacune allo stesso modo.
# Non è un parametro scientifico: assorbe solo arrotondamenti dei timestamp.
STEP_TOLERANCE_FACTOR = 1.01


def _validated_step_seconds(value):
    """Restituisce il passo in secondi se finito e positivo, altrimenti None."""
    number = _number(value)
    if number is None or number <= 0:
        return None
    return number


def resolve_expected_step(expected_step_seconds, astronomy_report):
    """Risolve il passo temporale atteso senza dedurlo dai campioni.

    Confronta il passo passato esplicitamente (configurazione) con quello
    dichiarato in ``temporal_diagnostics.expected_step_seconds`` del report
    astronomico. Restituisce
    ``(passo, origine, passo_parametro, passo_report, avvisi)``; il passo è
    None quando assente, non valido o discordante.
    Usata anche dal Solar Energy Engine.
    """
    step_warnings = []
    parameter_step = _validated_step_seconds(expected_step_seconds)
    if expected_step_seconds is not None and parameter_step is None:
        step_warnings.append(
            f"Passo temporale configurato non valido: {expected_step_seconds!r}."
        )

    astronomy_diagnostics = _safe_mapping(astronomy_report, "temporal_diagnostics")
    raw_report_step = astronomy_diagnostics.get("expected_step_seconds")
    report_step = _validated_step_seconds(raw_report_step)
    if raw_report_step is not None and report_step is None:
        step_warnings.append(
            "Passo temporale non valido nel report astronomico: "
            f"{raw_report_step!r}."
        )

    if parameter_step is not None and report_step is not None:
        if math.isclose(parameter_step, report_step, rel_tol=1e-9):
            resolved_step, step_source = parameter_step, "configuration"
        else:
            resolved_step, step_source = None, None
            step_warnings.append(
                "Passo configurato e passo del report astronomico discordanti "
                f"({parameter_step} s vs {report_step} s): "
                "continuità non determinabile."
            )
    elif parameter_step is not None:
        resolved_step, step_source = parameter_step, "configuration"
    elif report_step is not None:
        resolved_step, step_source = report_step, "astronomy_report"
    else:
        resolved_step, step_source = None, None
        step_warnings.append(
            "Passo temporale atteso non disponibile: "
            "continuità non determinabile."
        )

    return resolved_step, step_source, parameter_step, report_step, step_warnings


def _ordered_samples(samples):
    """Campioni con timestamp valido, ordinati e senza duplicati temporali."""
    ordered = {}
    for row in samples:
        timestamp = _timestamp(row.get("time_utc"))
        if timestamp and timestamp not in ordered:
            ordered[timestamp] = row
    return sorted(
        (datetime.fromisoformat(timestamp), row)
        for timestamp, row in ordered.items()
    )


def _find_temporal_gaps(ordered, expected_step_seconds):
    """Lacune effettive: intervalli tra campioni consecutivi oltre il passo atteso.

    Senza un passo validato le lacune non sono determinabili e la funzione
    restituisce None (non una lista vuota, che significherebbe "nessuna lacuna").
    """
    if expected_step_seconds is None:
        return None

    limit = expected_step_seconds * STEP_TOLERANCE_FACTOR
    gaps = []
    for index in range(1, len(ordered)):
        previous, current = ordered[index - 1][0], ordered[index][0]
        interval = (current - previous).total_seconds()
        if interval > limit:
            gaps.append({
                "last_sample_before_utc": previous.isoformat(),
                "first_sample_after_utc": current.isoformat(),
                "interval_seconds": interval,
            })
    return gaps


def _segment_series(ordered, predicate, expected_step_seconds):
    """Suddivide la serie in segmenti semanticamente distinti.

    - ``favorable``: campioni osservati che soddisfano il predicato;
    - ``unfavorable_observed``: campioni osservati che non lo soddisfano
      (condizioni sfavorevoli, NON perdita di dati);
    - ``temporal_gap``: lacuna effettiva rilevata rispetto al passo atteso.

    Un segmento termina al cambio di condizione o in corrispondenza di una
    lacuna effettiva. Senza passo validato le lacune non vengono rilevate e
    i segmenti si basano soltanto sull'adiacenza dei campioni osservati.
    """
    limit = (
        expected_step_seconds * STEP_TOLERANCE_FACTOR
        if expected_step_seconds is not None else None
    )
    segments = []
    current = None
    previous_time = None

    for timestamp, row in ordered:
        if previous_time is not None and limit is not None:
            interval = (timestamp - previous_time).total_seconds()
            if interval > limit:
                segments.append({
                    "kind": "temporal_gap",
                    "start": previous_time,
                    "end": timestamp,
                    "interval_seconds": interval,
                })
                current = None

        kind = "favorable" if predicate(row) else "unfavorable_observed"
        if current is None or current["kind"] != kind:
            current = {"kind": kind, "rows": []}
            segments.append(current)
        current["rows"].append((timestamp, row))
        previous_time = timestamp

    return segments


def _build_windows(samples, predicate, expected_step_seconds=None):
    """Raggruppa i campioni favorevoli usando esclusivamente il passo configurato.

    Il passo non viene mai dedotto dagli intervalli osservati. Se il passo
    configurato non è disponibile o non è valido, le finestre seguono solo
    l'adiacenza dei campioni osservati e la loro continuità è dichiarata
    non determinabile.
    """
    step = _validated_step_seconds(expected_step_seconds)
    ordered = _ordered_samples(samples)
    segments = _segment_series(ordered, predicate, step)

    windows = []
    previous_end = None
    unfavorable_before = 0
    gaps_before = 0

    for segment in segments:
        kind = segment["kind"]
        if kind == "temporal_gap":
            if previous_end is not None:
                gaps_before += 1
            continue
        if kind == "unfavorable_observed":
            if previous_end is not None:
                unfavorable_before += len(segment["rows"])
            continue

        group = segment["rows"]
        start, end = group[0][0], group[-1][0]
        span = (end - start).total_seconds()
        gap_before = (
            (start - previous_end).total_seconds()
            if previous_end is not None else None
        )

        if previous_end is None:
            interruption_type = None
        elif step is None:
            interruption_type = (
                "unfavorable_observed" if unfavorable_before
                else "not_determinable"
            )
        elif gaps_before and unfavorable_before:
            interruption_type = "unfavorable_observed_and_temporal_gap"
        elif gaps_before:
            interruption_type = "temporal_gap"
        else:
            interruption_type = "unfavorable_observed"

        windows.append({
            "start_utc": start.isoformat(),
            "end_utc": end.isoformat(),
            "sample_count": len(group),
            "observed_span_minutes": span / 60.0,
            "duration_is_extrapolated": False,
            "continuity_basis_seconds": step,
            "continuity_verifiable": step is not None,
            "continuity_status": (
                "verified_against_expected_step" if step is not None
                else "not_determinable"
            ),
            "single_sample": len(group) == 1,
            "interruption_before": previous_end is not None,
            "interruption_before_type": interruption_type,
            "unfavorable_observed_samples_before": (
                unfavorable_before if previous_end is not None else None
            ),
            "temporal_gaps_before": (
                gaps_before if previous_end is not None and step is not None
                else None
            ),
            "gap_before_seconds": gap_before,
        })
        previous_end = end
        unfavorable_before = 0
        gaps_before = 0

    windows.sort(
        key=lambda item: (
            -item["observed_span_minutes"],
            item["start_utc"],
        )
    )
    for rank, window in enumerate(windows, start=1):
        window["duration_rank"] = rank

    return windows


def _build_unfavorable_intervals(samples, predicate, expected_step_seconds=None):
    """Intervalli osservati in cui le condizioni non sono favorevoli.

    Sono distinti dalle lacune temporali: esistono campioni, ma il predicato
    operativo non è soddisfatto.
    """
    step = _validated_step_seconds(expected_step_seconds)
    segments = _segment_series(_ordered_samples(samples), predicate, step)
    intervals = []
    for segment in segments:
        if segment["kind"] != "unfavorable_observed":
            continue
        rows = segment["rows"]
        start, end = rows[0][0], rows[-1][0]
        intervals.append({
            "start_utc": start.isoformat(),
            "end_utc": end.isoformat(),
            "sample_count": len(rows),
            "observed_span_minutes": (end - start).total_seconds() / 60.0,
        })
    return intervals


def build_mission_decision(
    *,
    astronomy_path=None,
    illumination_path=None,
    visibility_path=None,
    energy_path=None,
    output_path,
    min_sun_elevation_deg=5.0,
    min_earth_elevation_deg=5.0,
    expected_step_seconds=None,
    solar_energy_path=None,
):
    """Correla report scientifici senza attribuire loro validazione operativa.

    ``solar_energy_path`` (opzionale) è il report del Solar Energy Engine:
    consente di distinguere le finestre geometricamente favorevoli da quelle
    energeticamente sostenibili (batteria sopra la riserva, carico servito).

    ``expected_step_seconds`` è il passo temporale configurato per le
    osservazioni astronomiche. Non viene mai dedotto dai campioni: se assente
    o non valido, la continuità temporale è dichiarata non determinabile.
    """

    try:
        sun_threshold = float(min_sun_elevation_deg)
        earth_threshold = float(min_earth_elevation_deg)
    except (TypeError, ValueError):
        raise ValueError("Soglie di elevazione non numeriche.") from None

    if (
        not math.isfinite(sun_threshold)
        or not math.isfinite(earth_threshold)
        or not -90 <= sun_threshold <= 90
        or not -90 <= earth_threshold <= 90
    ):
        raise ValueError("Soglie di elevazione non valide.")

    astronomy, astronomy_error = _read_report(
        astronomy_path, "astronomy"
    )
    illumination, illumination_error = _read_report(
        illumination_path, "illumination"
    )
    visibility, visibility_error = _read_report(
        visibility_path, "visibility"
    )
    energy, energy_error = _read_report(
        energy_path, "energy"
    )
    solar_energy, solar_energy_error = _read_report(
        solar_energy_path, "solar_energy"
    )

    # Sostenibilità energetica per campione, così come calcolata dal
    # Solar Energy Engine (True / False / None = non determinabile).
    energy_by_time = {}
    solar_series = _safe_mapping(solar_energy, "time_series")
    solar_samples = solar_series.get("samples")
    for row in solar_samples if isinstance(solar_samples, list) else []:
        if not isinstance(row, dict):
            continue
        timestamp = _timestamp(row.get("time_utc"))
        value = row.get("energy_sustainable")
        if timestamp:
            energy_by_time[timestamp] = (
                value if isinstance(value, bool) else None
            )

    (
        resolved_step, step_source, parameter_step, report_step, step_warnings,
    ) = resolve_expected_step(expected_step_seconds, astronomy)

    observations = _safe_mapping(astronomy, "observations")
    sun_rows = observations.get("Sun", [])
    earth_rows = observations.get("Earth", [])

    if not isinstance(sun_rows, list):
        sun_rows = []
    if not isinstance(earth_rows, list):
        earth_rows = []

    sun = {}
    earth = {}
    invalid_astronomy_rows = 0

    for row in sun_rows:
        if not isinstance(row, dict):
            invalid_astronomy_rows += 1
            continue

        timestamp = _timestamp(row.get("time_utc"))
        elevation = _number(row.get("elevation_deg"))

        if timestamp and elevation is not None:
            sun[timestamp] = elevation
        else:
            invalid_astronomy_rows += 1

    for row in earth_rows:
        if not isinstance(row, dict):
            invalid_astronomy_rows += 1
            continue

        timestamp = _timestamp(row.get("time_utc"))
        elevation = _number(row.get("elevation_deg"))

        if timestamp and elevation is not None:
            earth[timestamp] = elevation
        else:
            invalid_astronomy_rows += 1

    light_by_time = {}
    invalid_illumination_rows = 0

    for row in _rows(illumination, "observations"):
        if not isinstance(row, dict):
            invalid_illumination_rows += 1
            continue

        timestamp = _timestamp(row.get("time_utc"))
        if timestamp:
            light_by_time[timestamp] = row
        else:
            invalid_illumination_rows += 1

    visibility_by_time = {}
    invalid_visibility_rows = 0

    for row in _rows(visibility, "observations"):
        if not isinstance(row, dict):
            invalid_visibility_rows += 1
            continue

        timestamp = _timestamp(row.get("time_utc"))
        target = row.get("target")
        status = row.get("status")

        if timestamp and target in ("Sun", "Earth"):
            visibility_by_time[(target, timestamp)] = status
        else:
            invalid_visibility_rows += 1

    common_timestamps = sorted(set(sun) & set(earth))
    samples = []

    for timestamp in common_timestamps:
        sun_elevation = sun[timestamp]
        earth_elevation = earth[timestamp]

        geometry_pass = (
            sun_elevation >= sun_threshold
            and earth_elevation >= earth_threshold
        )

        light = light_by_time.get(timestamp)
        raw_sun_visibility = (
            light.get("estimated_direct_sun_visible")
            if light else None
        )
        sun_visible = (
            raw_sun_visibility
            if isinstance(raw_sun_visibility, bool)
            else None
        )

        sun_terrain = visibility_by_time.get(("Sun", timestamp))
        earth_terrain = visibility_by_time.get(("Earth", timestamp))

        terrain_complete = (
            sun_terrain in ("preliminary_visible", "preliminary_blocked")
            and earth_terrain in (
                "preliminary_visible",
                "preliminary_blocked",
            )
        )

        terrain_preliminary_clear = (
            sun_terrain == "preliminary_visible"
            and earth_terrain == "preliminary_visible"
        )

        evidence_complete = (
            sun_visible is not None
            and terrain_complete
        )

        environmental_candidate = (
            geometry_pass
            and sun_visible is True
            and terrain_preliminary_clear
        )

        if environmental_candidate:
            classification = "preliminary_environmental_candidate"
        elif not geometry_pass:
            classification = "geometric_constraints_not_met"
        elif not evidence_complete:
            classification = "incomplete_environmental_evidence"
        else:
            classification = "environmental_constraints_not_met"

        samples.append({
            "time_utc": timestamp,
            "sun_elevation_deg": sun_elevation,
            "earth_elevation_deg": earth_elevation,
            "geometric_constraints_met": geometry_pass,
            "estimated_direct_sun_visible": sun_visible,
            "terrain_visibility": {
                "sun": sun_terrain,
                "earth": earth_terrain,
            },
            "environmental_evidence_complete": evidence_complete,
            "environmental_candidate": environmental_candidate,
            "classification": classification,
            "energy_sustainable": energy_by_time.get(timestamp),
            "geometric_and_energy_sustainable": (
                geometry_pass and energy_by_time.get(timestamp) is True
            ),
        })

    def geometric_predicate(row):
        return row["geometric_constraints_met"]

    def environmental_predicate(row):
        return row["environmental_candidate"]

    geometric_windows = _build_windows(
        samples, geometric_predicate, resolved_step
    )
    environmental_windows = _build_windows(
        samples, environmental_predicate, resolved_step
    )
    def energy_predicate(row):
        return row["geometric_and_energy_sustainable"]

    energy_windows = _build_windows(
        samples, energy_predicate, resolved_step
    )
    energy_unfavorable = _build_unfavorable_intervals(
        samples, energy_predicate, resolved_step
    )
    energy_sustainable_count = sum(
        row["geometric_and_energy_sustainable"] for row in samples
    )
    energy_unknown_count = sum(
        row["geometric_constraints_met"] and row["energy_sustainable"] is None
        for row in samples
    )
    geometric_sample_count = sum(
        row["geometric_constraints_met"] for row in samples
    )
    if solar_energy is None:
        energy_sustainability_status = "not_evaluated"
    elif energy_sustainable_count:
        energy_sustainability_status = "energy_sustainable_geometric_windows_available"
    elif geometric_sample_count and energy_unknown_count == geometric_sample_count:
        energy_sustainability_status = "energy_sustainability_not_determinable"
    elif geometric_sample_count:
        energy_sustainability_status = "no_energy_sustainable_geometric_window"
    else:
        energy_sustainability_status = "no_geometric_candidate"

    geometric_unfavorable = _build_unfavorable_intervals(
        samples, geometric_predicate, resolved_step
    )
    environmental_unfavorable = _build_unfavorable_intervals(
        samples, environmental_predicate, resolved_step
    )

    ordered_samples = _ordered_samples(samples)
    temporal_gaps = _find_temporal_gaps(ordered_samples, resolved_step)
    continuity_verifiable = (
        resolved_step is not None and len(ordered_samples) >= 2
    )
    if resolved_step is not None and len(ordered_samples) < 2:
        step_warnings.append(
            "Meno di due campioni comuni: continuità non verificabile."
        )

    if not continuity_verifiable:
        continuity_status = "not_determinable"
    elif temporal_gaps:
        continuity_status = "gaps_detected"
    else:
        continuity_status = "continuous_at_expected_step"

    series_span_seconds = (
        (ordered_samples[-1][0] - ordered_samples[0][0]).total_seconds()
        if len(ordered_samples) >= 2 else 0.0 if ordered_samples else None
    )
    gap_seconds = (
        sum(gap["interval_seconds"] for gap in temporal_gaps)
        if temporal_gaps is not None else None
    )

    temporal_continuity = {
        "expected_step_seconds": resolved_step,
        "expected_step_source": step_source,
        "configured_step_seconds": parameter_step,
        "astronomy_report_step_seconds": report_step,
        "step_tolerance_factor": STEP_TOLERANCE_FACTOR,
        "sample_count": len(ordered_samples),
        "first_sample_utc": (
            ordered_samples[0][0].isoformat() if ordered_samples else None
        ),
        "last_sample_utc": (
            ordered_samples[-1][0].isoformat() if ordered_samples else None
        ),
        "observed_span_minutes": (
            series_span_seconds / 60.0
            if series_span_seconds is not None else None
        ),
        "geometric_window_count": len(geometric_windows),
        "environmental_window_count": len(environmental_windows),
        "geometric_unfavorable_observed_intervals": geometric_unfavorable,
        "environmental_unfavorable_observed_intervals": environmental_unfavorable,
        "temporal_gap_count": (
            len(temporal_gaps) if temporal_gaps is not None else None
        ),
        "temporal_gap_minutes": (
            gap_seconds / 60.0 if gap_seconds is not None else None
        ),
        "temporal_gaps": temporal_gaps,
        "continuity_verifiable": continuity_verifiable,
        "continuity_status": continuity_status,
        "warnings": step_warnings,
        "interpretation": (
            "Le lacune temporali sono intervalli tra campioni consecutivi "
            "superiori al passo configurato. Gli intervalli sfavorevoli "
            "osservati contengono campioni e non sono perdita di dati."
        ),
    }

    geometric_count = sum(
        row["geometric_constraints_met"] for row in samples
    )
    environmental_count = sum(
        row["environmental_candidate"] for row in samples
    )
    incomplete_count = sum(
        row["classification"] == "incomplete_environmental_evidence"
        for row in samples
    )

    best_geometric = geometric_windows[0] if geometric_windows else None
    best_environmental = (
        environmental_windows[0] if environmental_windows else None
    )

    mission_window_intelligence = {
        "geometric_window_count": len(geometric_windows),
        "environmental_window_count": len(environmental_windows),
        "best_geometric_window": best_geometric,
        "best_environmental_window": best_environmental,
        "environmental_to_geometric_window_ratio": (
            len(environmental_windows) / len(geometric_windows)
            if geometric_windows else None
        ),
        "temporal_interruptions": {
            "geometric": sum(
                bool(window["interruption_before"])
                for window in geometric_windows
            ),
            "environmental": sum(
                bool(window["interruption_before"])
                for window in environmental_windows
            ),
        },
        "ranking_basis": "observed_span_minutes_descending",
        "interpretation": (
            "Ranking descrittivo basato sui campioni osservati; "
            "non rappresenta una previsione di continuità fisica."
        ),
    }

    def summarize_windows(windows, unfavorable_intervals):
        gaps = [
            window["gap_before_seconds"]
            for window in windows
            if window.get("gap_before_seconds") is not None
        ]
        by_type = {}
        for window in windows:
            kind = window.get("interruption_before_type")
            if kind:
                by_type[kind] = by_type.get(kind, 0) + 1
        return {
            "interruption_types": by_type,
            "unfavorable_observed_interval_count": len(unfavorable_intervals),
            "window_count": len(windows),
            "observed_span_minutes": round(sum(
                window["observed_span_minutes"] for window in windows
            ), 2),
            "interruption_count": len(gaps),
            "total_interruption_minutes": round(sum(gaps) / 60, 2),
            "longest_interruption_minutes": (
                round(max(gaps) / 60, 2) if gaps else None
            ),
        }

    temporal_intelligence = {
        "sample_count": len(samples),
        "geometric_favorable_samples": geometric_count,
        "environmental_favorable_samples": environmental_count,
        "geometric_favorable_sample_percent": (
            round(geometric_count / len(samples) * 100, 2)
            if samples else None
        ),
        "environmental_favorable_sample_percent": (
            round(environmental_count / len(samples) * 100, 2)
            if samples else None
        ),
        "geometric": summarize_windows(
            geometric_windows, geometric_unfavorable
        ),
        "environmental": summarize_windows(
            environmental_windows, environmental_unfavorable
        ),
        "expected_step_seconds": resolved_step,
        "temporal_gap_count": temporal_continuity["temporal_gap_count"],
        "continuity_verifiable": continuity_verifiable,
        "continuity_status": continuity_status,
        "best_environmental_window": best_environmental,
        "best_geometric_window": best_geometric,
        "duration_interpretation": (
            "Somma degli intervalli tra campioni favorevoli osservati; "
            "non rappresenta continuità fisica certificata."
        ),
        "percentage_denominator": "common_astronomical_samples",
    }

    energy_values = _safe_mapping(energy, "energy_wh")
    energy_budget = energy_values.get("within_budget")

    if not isinstance(energy_budget, bool):
        energy_budget = None

    energy_status = (
        "within_configured_battery_budget"
        if energy_budget is True
        else "exceeds_configured_battery_budget"
        if energy_budget is False
        else "not_evaluated"
    )

    if environmental_count:
        classification = "preliminary_environmental_candidates_available"
    elif geometric_count:
        classification = "geometric_candidates_only"
    elif not samples:
        classification = "insufficient_astronomical_data"
    else:
        classification = "no_geometric_candidate_in_available_samples"

    payload = {
        "schema": SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": "preliminary",
        "mission_decision": {
            "classification": classification,
            "geometric_candidate_samples": geometric_count,
            "environmental_candidate_samples": environmental_count,
            "incomplete_environmental_samples": incomplete_count,
            "energy_status": energy_status,
            "energy_within_budget": energy_budget,
            "energy_sustainability_status": energy_sustainability_status,
            "geometric_and_energy_sustainable_samples": energy_sustainable_count,
            "operational_safety_certified": False,
        },
        "thresholds_deg": {
            "sun": sun_threshold,
            "earth": earth_threshold,
        },
        "data_sources": {
            "astronomy": {
                "available": astronomy is not None,
                "error": astronomy_error,
            },
            "illumination": {
                "available": illumination is not None,
                "error": illumination_error,
            },
            "visibility": {
                "available": visibility is not None,
                "error": visibility_error,
            },
            "energy": {
                "available": energy is not None,
                "error": energy_error,
            },
            "solar_energy": {
                "available": solar_energy is not None,
                "error": solar_energy_error,
            },
        },
        "data_quality": {
            "invalid_astronomy_rows": invalid_astronomy_rows,
            "invalid_illumination_rows": invalid_illumination_rows,
            "invalid_visibility_rows": invalid_visibility_rows,
            "common_astronomical_samples": len(samples),
        },
        "energy_summary": {
            "status": energy_status,
            "total_estimated_wh": _number(
                energy_values.get("total_estimated")
            ),
            "usable_battery_after_reserve_wh": _number(
                energy_values.get("usable_battery_after_reserve")
            ),
            "remaining_after_estimate_wh": _number(
                energy_values.get("remaining_after_estimate")
            ),
            "applies_to_environmental_window_classification": False,
        },
        "solar_energy_summary": {
            "available": solar_energy is not None,
            "report_status": (
                solar_energy.get("status") if solar_energy else None
            ),
            "sustainability": _safe_mapping(solar_energy, "summary").get(
                "sustainability"
            ),
            "energy_sustainability_status": energy_sustainability_status,
            "geometric_samples": geometric_sample_count,
            "geometric_and_energy_sustainable_samples": energy_sustainable_count,
            "geometric_samples_energy_not_determinable": energy_unknown_count,
            "energy_sustainable_window_count": len(energy_windows),
            "best_energy_sustainable_window": (
                energy_windows[0] if energy_windows else None
            ),
            "model_scientifically_validated": False,
        },
        "sample_count": len(samples),
        "mission_windows": {
            "method": (
                "observed timestamps segmented with configured step; "
                "no interpolation"
            ),
            "temporal_continuity": temporal_continuity,
            "geometric": geometric_windows,
            "environmental": environmental_windows,
            "energy_sustainable": energy_windows,
            "energy_sustainable_definition": (
                "Campioni geometricamente favorevoli in cui il Solar Energy "
                "Engine stima batteria sopra la riserva e carico servito "
                "nell'intervallo successivo."
            ),
            "energy_unfavorable_observed_intervals": energy_unfavorable,
            "intelligence": mission_window_intelligence,
            "temporal_intelligence": temporal_intelligence,
        },
        "samples": samples,
        "limitations": [
            "Aggregazione di report esistenti, senza nuovi modelli fisici.",
            "Le osservazioni astronomiche sono geometriche.",
            "La visibilità del terreno è preliminare e non certificata.",
            "La visibilità solare non equivale a energia elettrica generata.",
            "Il budget energetico Rover Energy non include generazione solare; "
            "la produzione solare è valutata dal Solar Energy Engine.",
            "La sostenibilità energetica dipende da un modello preliminare "
            "non validato e dai parametri hardware configurati.",
            "Il budget energetico è valutato separatamente dalle finestre ambientali.",
            "Non viene calcolato un RF link budget.",
            "Non vengono valutati limiti termici o sicurezza di atterraggio.",
            "I report con schema inatteso vengono esclusi dall'aggregazione.",
            "La continuità temporale si basa sul passo configurato; "
            "senza passo valido è dichiarata non determinabile.",
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
        "status": "preliminary",
        "report_file": str(destination),
        "sample_count": len(samples),
        "geometric_candidate_samples": geometric_count,
        "environmental_candidate_samples": environmental_count,
        "incomplete_environmental_samples": incomplete_count,
        "energy_status": energy_status,
        "energy_sustainability_status": energy_sustainability_status,
        "energy_sustainable_window_count": len(energy_windows),
        "expected_step_seconds": resolved_step,
        "continuity_status": continuity_status,
    }
