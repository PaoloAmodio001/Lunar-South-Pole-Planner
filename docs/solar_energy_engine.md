# Solar Energy Engine

Modulo: `src/solar_energy_engine.py` · Schema del report: `lunar-solar-energy-budget/1.0`
Step dell'orchestratore: `solar_energy` · Artefatto: `solar_energy_budget.json`

> **Stato: modello ingegneristico preliminare.** Non è validato scientificamente
> né qualificato per operazioni reali. Il report lo dichiara in
> `model_validation.scientifically_validated = false`.

## Scopo

Il motore stima nel tempo:

- la potenza elettrica fotovoltaica utilizzabile;
- i consumi del rover per categoria;
- l'energia netta e lo stato di carica della batteria;
- i deficit.

Permette inoltre al Mission Decision Engine di separare le finestre
**geometricamente favorevoli** da quelle **energeticamente sostenibili**.

## Input riutilizzati (nessuna duplicazione)

| Fonte | Modulo | Dati usati |
|---|---|---|
| Astronomy | `mission_orchestrator.collect_astronomy` / `astronomy.py` | `time_utc`, `elevation_deg`, `azimuth_deg`, `distance_au` del Sole; `temporal_diagnostics.expected_step_seconds` |
| Illumination | `illumination_analysis.py` | `estimated_direct_sun_visible` per campione |
| Rover Energy (opz.) | `rover_energy.py` | `energy_wh.traction_after_drivetrain` |
| Configurazione | sezione `solar_energy` (+ fallback da `energy`) | pannelli, batteria, consumi, pianificazione |

Il passo temporale viene risolto con
`mission_decision_engine.resolve_expected_step` (Fase 1): non è mai dedotto dai
campioni. Le lacune usano la stessa tolleranza (`STEP_TOLERANCE_FACTOR = 1.01`).

## Modello

Per ogni campione astronomico del Sole:

```
G      = S0 / d²                                         [W/m²]
cos_i  = max(0, sin(el)·cos(tilt) + cos(el)·sin(tilt)·cos(az_sole − az_pannello))
P_dc   = G · A · η · cos_i · (1 − polvere) · (1 − degrado) · f_termico
P_use  = min(P_dc · (1 − perdite_sistema), max_output_w)
```

- **S0:** 1360.8 W/m², da Kopp & Lean (2011), GRL 38, L01706. Si può sovrascrivere.
- **d:** distanza osservatore–Sole di Horizons, in UA. Se manca, il campione è
  `missing_distance`, a meno che `allow_1au_distance_fallback = true`.
- **Incidenza per modalità:**
  - `fixed`: formula completa;
  - `azimuth_tracking`: Δaz = 0;
  - `two_axis_tracking`: cos_i = 1.
- **Sole occultato:** se il report di illuminazione indica il Sole occultato dal
  terreno, la produzione è 0. Se la visibilità manca, la produzione non è
  determinabile (`missing_illumination`). La visibilità del Sole è condizione
  necessaria, non sufficiente.
- **f_termico:** `1 + coeff·(T_cella − T_ref)`, applicato solo se configurato.

### Integrazione temporale

- Ogni intervallo [tᵢ, tᵢ₊₁) usa la potenza del campione iniziale (mantenimento
  di ordine zero). Non c'è interpolazione.
- Un intervallo oltre `passo × 1.01` è `temporal_gap`: l'energia non viene calcolata.
- I consumi per modalità sono pesati sulla sovrapposizione esatta tra
  l'intervallo e la pianificazione (`schedule`). Il tempo non pianificato usa
  `default_mode`.
- **Trazione:** si usa `traction_power_w` se configurata. Altrimenti l'energia di
  trazione del report Rover Energy viene distribuita uniformemente sulle ore di
  guida pianificate.
- **Batteria:**
  - carica: `net·η_c`, fino alla capacità; l'eccesso è `curtailed_wh`;
  - scarica: `net/η_d`, fino a 0 Wh; l'energia non erogabile è `unmet_load_wh`;
  - la riserva è un vincolo di pianificazione: la violazione viene segnalata,
    nessun carico viene distaccato.
- La traccia dello stato di carica si interrompe al primo intervallo non
  determinabile e non riprende. Il report indica dove si interrompe e perché
  (`data_quality.soc_trace_break_*`).

### Sostenibilità per campione (usata dal Decision Engine)

`energy_sustainable` vale:

- `true` se lo stato di carica è ≥ riserva al campione e alla fine
  dell'intervallo successivo, e nessun carico resta non servito;
- `false` se una di queste condizioni non è rispettata;
- `null` se non è determinabile.

Il Decision Engine produce `mission_windows.energy_sustainable`: le finestre
in cui il campione è geometricamente favorevole **e** energeticamente sostenibile.

## Configurazione

Vedi la sezione `solar_energy` di `mission_config.example.json`. La sottochiave
`documentation` descrive ogni parametro con unità, intervallo ammesso e
obbligatorietà.

Tutti i parametri hardware nell'esempio sono `null`. Il motore non inventa
valori: i parametri mancanti finiscono in `missing_inputs`, quelli fuori
intervallo in `invalid_inputs`. Il report viene comunque scritto, con
`status = partial_missing_inputs`, e le grandezze dipendenti restano `null`.

**Parametri obbligatori:**

- **Pannelli:** `area_m2`, `cell_efficiency`, `orientation_mode` (e
  `tilt_deg`/`azimuth_deg` a seconda della modalità), `system_loss_fraction`,
  `dust_loss_fraction`, `degradation_fraction`.
- **Batteria:** `capacity_wh`, `min_reserve_fraction`, `initial_soc_fraction`,
  `charge_efficiency`, `discharge_efficiency`.
- **Consumi:** per ogni modalità usata `auxiliary_w`, `science_w`,
  `communications_w`; inoltre la trazione, se pianificata.

**Fallback espliciti dalla sezione `energy`** (la provenienza è registrata in
`parameters.parameter_sources`):

- `battery_capacity_wh`;
- `reserve_percent`;
- `auxiliary_power_w`.

## Report

| Chiave | Contenuto |
|---|---|
| `parameters`, `missing_inputs`, `invalid_inputs` | Parametri usati, con provenienza, e input mancanti o non validi |
| `assumptions`, `not_evaluated`, `limitations` | Ipotesi del modello e grandezze non valutate |
| `time_series.samples` | Geometria, irradianza, incidenza, potenza utilizzabile, stato di carica, `energy_sustainable` |
| `time_series.intervals` | Produzione, consumi per categoria, netto, carica/scarica, curtailed, non servito, stato di carica, margine di riserva |
| `summary` | Totali, stato di carica iniziale/finale/minimo, riserva, sostenibilità |
| `deficit_intervals` | Intervalli di deficit netto, sotto riserva e con carico non servito |
| `autonomy` | Tempo fino alla riserva (simulato); autonomia solo batteria al carico medio e di picco |
| `data_quality` | Completezza dei dati, stati degli intervalli, continuità, interruzione della traccia |
| `result_classes` | Separazione tra risultati stimati, dati mancanti e risultati non validabili |

**Stati del report:**

| Stato | Significato |
|---|---|
| `preliminary_estimate` | Bilancio completo |
| `partial_missing_inputs` | Mancano parametri |
| `partial_incomplete_data` | Lacune nei dati o continuità non verificabile |
| `not_computable` | Nessun campione |

## Integrazioni

- **Orchestratore:** lo step `solar_energy` (opt-in, `enabled: true`) viene
  eseguito dopo `rover_energy` e prima di `mission_decision`.
- **Decision Engine:** `build_mission_decision(solar_energy_path=...)` produce:
  - `solar_energy_summary`;
  - `mission_windows.energy_sustainable`;
  - `mission_decision.energy_sustainability_status`.
- **Report generale:** `mission_status_report.json` contiene la sezione
  `solar_energy`. Il Markdown contiene la sezione "Bilancio energetico solare" e
  la voce corrispondente nel quadro decisionale.
- **Web UI:** il pannello "SOLAR ENERGY ENGINE" mostra:
  - le card riepilogative;
  - il grafico della potenza (produzione, consumo e trazione), con deficit e
    lacune evidenziati;
  - il grafico dello stato di carica con riserva e capacità;
  - le tabelle di consumi, deficit e qualità dei dati.

  Il pannello del Decision Engine mostra le finestre sostenibili.

## Grandezze non valutate

Il report le elenca in `not_evaluated`:

- albedo e luce diffusa;
- penombra del disco solare;
- autombreggiamento;
- temperatura variabile;
- risposta angolare oltre il coseno;
- elettrochimica della batteria e limiti di corrente;
- orientamento reale del rover durante la guida.
