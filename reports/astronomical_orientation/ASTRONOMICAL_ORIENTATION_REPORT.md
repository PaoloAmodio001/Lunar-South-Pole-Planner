# Validazione dell'orientamento astronomico — Report

- **Data:** 2026-11-14
- **Prima fase:** 21:33:49 – ~21:42 (verdetto provvisorio PARTIAL)
- **Completamento:** 21:44 – ~21:50 (verifica Horizons, verdetto finale)
- **Tempo effettivo:** circa 15 minuti su 25

## Verdetto: **PASS**

| Relazione | Stato | Evidenza |
|---|---|---|
| Nord geografico (frame del DEM) ↔ nord di griglia Site04 | **PASS — dimostrata** | 3 metodi indipendenti concordi entro 1e-6° (§4); verifica fisica sul terreno (§7) |
| Convenzione dell'azimut di griglia nei moduli | **PASS** | `terrain_horizon`, `visibility`, `illumination_analysis` e orchestratore usano la stessa convenzione (§5) |
| Azimut Horizons ↔ nord geografico del DEM | **PASS — dimostrata** | 61 + 61 osservazioni Horizons reali coincidono con un calcolo locale SPICE nel frame MOON_ME_DE421 entro 1e-5° (§8) |

Nella prima fase il terzo punto era NOT VERIFIED e il verdetto era PARTIAL. È stato chiuso con una verifica indipendente basata su kernel già presenti nel repository e su due query Horizons, le stesse che la pipeline esegue.

---

## 1. Analisi preliminare
- **Stato Git iniziale:** 29 voci. Salvato nel backup in `git_status_initial.txt`.
- **Identità del sito:** `reports/site_identity_validation/SITE_IDENTITY_VALIDATION_REPORT.md` stabilisce Site04 = Shackleton rim. Shackleton cade nel pixel (1600, 1599), a 0,3 m dal centro del DEM.
- **Backup:** `backups/astronomical-orientation-20261114-213458/` contiene `lunar_geometry.py`, `mission_orchestrator.py`, `illumination_analysis.py`, `mission_config.example.json`, `SHA256SUMS` e lo stato Git.

## 2. Parametri del CRS (DEM Site04)
```
+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +x_0=0 +y_0=0 +R=1737400 +units=m
transform = (5.0, 0.0, -9000.0, 0.0, -5.0, 1000.0)   # +x verso destra, +y verso l'alto
```
- Stereografica polare sud su sfera, meridiano centrale lon₀ = 0°, nessun falso est/nord.
- Il README LOLA indica X/Y in stereografica polare, frame **MOON_ME (DE421)**, pixel-registered.

## 3. Coordinate di Shackleton
- **Nominali** (`src/astronomy.py::SITES`, NASA Lunar Surface Data Book Tab. A2.1-1): lat **−89,7668°**, lon E **−171,87°**, cioè x = −1000,04 m, y = −7000,35 m.
- **Centro del pixel osservatore (1600, 1599):** x = −1002,5 m, y = −7002,5 m, lat −89,76672°, lon E −171,8527°.

## 4. Offset: formula, valore e segno

### 4.1 Convenzioni (fonte unica: `src/lunar_geometry.py`)
- **Azimut geografico** (Horizons, `QUANTITIES=4`): gradi, in senso orario dal nord geografico locale (N = 0°, E = 90°, S = 180°, W = 270°). Verificato in §8.
- **Azimut di griglia** (`terrain_horizon.calculate_horizon`): gradi, in senso orario dall'asse +y del raster verso +x. Il passo è (dx, dy) = (sin az, cos az), con `math.radians`.
- **Trasformazione:**
  `grid_azimuth = (geographic_azimuth + offset) mod 360`
  `geographic_azimuth = (grid_azimuth − offset) mod 360`
- **offset** = azimut di griglia della direzione del nord geografico nel punto considerato.

### 4.2 Derivazione analitica
Nella stereografica polare sud su sfera (lat_ts = −90°):

  ρ = 2R·tan(45° + φ/2),  x = ρ·sin(λ − λ₀),  y = ρ·cos(λ − λ₀)

Il nord geografico è la direzione di φ crescente. Poiché ∂ρ/∂φ > 0, punta radialmente lontano dal polo, cioè lungo (sin(λ−λ₀), cos(λ−λ₀)). Il suo azimut di griglia è quindi:

  **offset = (λ − λ₀) mod 360**

L'est ha azimut offset + 90°: la proiezione non è speculare, quindi basta una rotazione.

### 4.3 Valore
| Punto | Offset |
|---|---|
| Shackleton nominale (λ = −171,87°) | **+188,13°** (≡ −171,87°) |
| Centro del pixel osservatore (1600, 1599) | **+188,1473°** |

- **Segno:** l'offset è positivo nel verso orario (+y → +x). Il nord geografico locale punta quasi esattamente verso **−y** della griglia.
- **Assumere nord di griglia = nord geografico** produrrebbe un errore di **188°**.
- **L'offset è locale.** Nel tile Site04 la longitudine varia da −149° a +155° (angoli), quindi l'offset va calcolato nella posizione dell'osservatore e non è un valore costante del DEM.

### 4.4 Verifica indipendente dell'offset
| Metodo | Risultato in Shackleton |
|---|---|
| A — formula analitica λ − λ₀ | 188,130000° |
| B — differenze finite sul CRS con pyproj (passo 1e-6° verso N e verso E) | 188,130000° (est − nord = 90,0000004°) |
| C — PROJ `get_factors().meridian_convergence` | 171,870000° = −188,13 mod 360 (PROJ usa la convenzione di segno opposta) |

`grid_azimuth_offset()` esegue il metodo B e lo verifica a ogni chiamata con C (tolleranza 1e-4°). Controlla anche che la proiezione non sia speculare.

## 5. Moduli interessati e convenzioni rilevate
| Modulo | Uso degli angoli | Esito |
|---|---|---|
| `astronomy.py` | Azimut ed elevazione apparenti da Horizons (gradi), sito con lon E | Convenzione e frame verificati (§8) |
| `terrain_horizon.py` | Azimut di griglia; `radians` → (sin, cos); elevazione `degrees(atan2(Δz, d))` | Coerente |
| `horizon_analysis.py` | Salva `grid_azimuth_deg`, la posizione x/y dell'osservatore e `crs_wkt` | Coerente: contiene tutto ciò che serve per l'offset |
| `visibility.compare_with_horizon` | Gradi, mod 360, interpolazione circolare; riceve azimut di griglia | Coerente |
| `illumination_analysis.py` | `grid = (Horizons + offset) mod 360` | Coerente; ora usa la funzione comune |
| `mission_orchestrator.py` | Prima: due chiavi di offset numeriche distinte (duplicazione) | Corretto: un'unica sorgente |
| `local_site_analysis.py` | Profilo in griglia, non usato con Horizons | Non interessato |

Nessun errore di segno, inversione o confusione gradi/radianti nelle formule esistenti. L'unico difetto era l'assenza dell'offset (`null`). Le formule fisiche non sono state modificate.

## 6. Modifiche effettuate
| File | Modifica |
|---|---|
| `src/lunar_geometry.py` | Documentazione delle convenzioni. Nuove funzioni `geographic_to_grid_azimuth`, `grid_to_geographic_azimuth`, `grid_azimuth_offset` e nuovo errore `AzimuthOrientationError`. Il controllo del CRS lunare è ora `_is_lunar_projected_crs`, con criterio identico, riusato da `validate_site_in_raster`. |
| `src/mission_orchestrator.py` | `_resolve_grid_azimuth_offset()`, condivisa da illumination e visibility_analysis. `"from_horizon_profile"` calcola l'offset dal CRS e dall'osservatore del profilo (unica fonte). Un valore numerico viene confrontato con il CRS (tolleranza 1e-3°) e rifiutato se incoerente; è accettato come `configured_unverified` solo se il CRS non consente il calcolo. `azimuth_mapping` riporta fonte, metodo, lat/lon dell'osservatore e `horizons_frame_equivalence_verified: false`. |
| `src/illumination_analysis.py` | Usa `geographic_to_grid_azimuth` (risultato identico). Nuovo parametro opzionale `azimuth_mapping_details`. |
| `mission_config.example.json` | `illumination` e `visibility_analysis`: `grid_azimuth_offset_deg` = `"from_horizon_profile"`. `horizon_analysis.observer_row/col` = 1600/1599. Le sezioni restano **disattivate**. |
| `tests/test_astronomical_orientation.py` | **Nuovo**, 72 test. |
| `tests/data/horizons_shackleton_20261101_12h.json` | **Nuovo**: risposta Horizons salvata, usata per la regressione offline (§8). |

**Flag `horizons_frame_equivalence_verified: false`.** È intenzionale: nessuna esecuzione della pipeline ripete la verifica. L'equivalenza è dimostrata staticamente per Shackleton e per i kernel DE421 in questo report, ed è protetta dal test di regressione.

Non sono stati toccati: raster, kernel, formule fisiche, scoring o pesi, ranking, UI. Nessun nuovo modulo, nessun commit.

## 7. Test
| # | Requisito | Test principali | Esito |
|---|---|---|---|
| 1 | Geografico → griglia | `test_shackleton_offset_value_and_sign`, `test_site04_crs_at_shackleton_pixel` | PASS |
| 2 | Conversione inversa | `test_round_trip_and_range` (28 casi) | PASS |
| 3 | Segno dell'offset | Confronto con formula e PROJ su 6 longitudini × 2 meridiani centrali; spostamento verso N, S, E, W | PASS |
| 4 | Cardinali e intermedi | N/E/S/W e NE/SE/SW/NW | PASS |
| 5 | Intervallo 0–360 | Input 360, −10, 720,5, 359,999 | PASS |
| 6 | Gradi/radianti | Muro di 200 m a 500 m → orizzonte di circa 21,8° | PASS |
| 7 | Coerenza tra moduli | Muro a nord geografico: Sole a N bloccato, a S visibile (inverso senza rotazione). Orchestratore end-to-end: stesso offset nei due moduli, offset errato rifiutato, offset corretto accettato, offset mancante rifiutato. CRS non lunari, polo e proiezione speculare rifiutati. | PASS |
| 8 | Scoring invariato | Moduli di scoring non modificati in sessione (ultima modifica 21:14). Ranking reale Site04 **identico** al riferimento pre-sessioni. | PASS |
| 9 | Frame e convenzione di Horizons | `test_horizons_azimuth_is_clockwise_from_north_in_moon_me[Sun/Earth]`, `test_horizons_sun_samples_cover_full_azimuth_circle` | PASS |

**Risultati:**
- `tests/test_astronomical_orientation.py`: **72/72**.
- **Suite completa: 258 superati, 0 falliti.**
- Una correzione al test durante la prima fase (centro del muro calcolato con media circolare invece di `argmax`; tolleranza ristretta da 10° a 1°).
- **Prova end-to-end** con `mission_config.example.json` (output nello scratchpad): exit 0, `completed_preliminary`.
- **Raster:** SHA-256 invariati per tutti e 7 i file. `de421.bsp` e i kernel in `data/terrain/kernels/` sono stati solo letti (ultima modifica 23–25 ottobre).

## 8. Verifica del frame e della convenzione di Horizons

**Metodo.**
- **Calcolo locale indipendente** con skyfield 1.55 e i kernel già presenti nel repository: `de421.bsp`, `moon_pa_de421_1900-2050.bpc`, `moon_080317.tf` (definisce MOON_ME_DE421 e MOON_PA_DE421), `pck00008.tpc`.
- Il calcolo produce azimut ed elevazione apparenti di Sole e Terra a Shackleton (lat −89,7668°, lon E −171,87°).
- **Dati di confronto:** 2 query JPL Horizons con il codice della pipeline (`query_observations`, `CENTER='coord@301'`, `COORD_TYPE=GEODETIC`, `QUANTITIES='4,20'`). Periodo 2026-11-01 → 2026-12-01, passo 12 h, 61 campioni per target. Sono state inviate solo le coordinate pubbliche del sito.

**Risultati** (`evidence/horizons_vs_local_spice.txt`):

| Target | Frame locale | max \|Δaz\| | max \|Δel\| |
|---|---|---|---|
| Sole (azimut 5,6°–359,5°, giro completo) | **MOON_ME_DE421** | **< 1e-5°** | **1e-5°** |
| Sole | MOON_PA_DE421 | 0,0195° | 0,0218° |
| Terra (azimut 164,6°–178,5°) | **MOON_ME_DE421** | **1e-5°** | **1e-5°** |
| Terra | MOON_PA_DE421 | 0,0190° | 0,0218° |
| Sole — ipotesi antioraria (360 − az) | ME | 178,16° | — |
| Sole — ipotesi da sud (az + 180) | ME | 180,00° | — |

**Conclusioni.**
1. Horizons interpreta le coordinate del sito e misura gli azimut nel frame **MOON_ME_DE421**, lo stesso del DEM LOLA (README).
2. La convenzione è **orario da nord** (N → E). Le alternative sono escluse da scarti di 178–180°.
3. Ne segue che `grid = (Horizons + offset) mod 360` con offset = λ − λ₀ è corretta senza ulteriori correzioni di frame.
4. **Correzione rispetto alla prima versione del report:** avevo stimato una possibile incertezza di frame "dell'ordine dei gradi". La misura reale della differenza ME–PA a Shackleton è **≈0,02°**, ed è comunque irrilevante perché Horizons usa ME.
5. **Fisicamente coerente:** la Terra appare a sud (≈176°), cioè oltre il polo verso il meridiano 0°. L'azimut del Sole decresce di circa 0,51°/h (E → N → W), il moto atteso per un osservatore australe.

Le osservazioni Horizons sono salvate in `tests/data/horizons_shackleton_20261101_12h.json`. Il test di regressione ripete il confronto offline, senza rete.

## 9. Esempio di risultato (Shackleton, offset 188,13°)
| Direzione geografica | Azimut di griglia |
|---|---|
| N 0° | 188,13° |
| E 90° | 278,13° |
| S 180° | 8,13° |
| W 270° | 98,13° |

## 10. Limitazioni residue
1. **Validità geografica e temporale.** La verifica di Horizons è dimostrata per Shackleton, per i kernel DE421 e per il periodo nov 2026. La formula dell'offset vale per ogni punto del CRS (testata su 6 longitudini). Per altri siti o altre epoche il test di regressione andrebbe esteso, ma il meccanismo resta lo stesso.
2. **Altitudine del sito in Horizons = 0 km** (audit LOW-3): non influisce sull'azimut e l'effetto sull'elevazione è trascurabile. Anche il calcolo locale usa altitudine 0, quindi il confronto è omogeneo.
3. **Risoluzione angolare dell'orizzonte:** il passo predefinito di 2° domina sulle incertezze dell'offset (1e-6°) e sullo scarto tra centro pixel e punto nominale (0,017°).
4. **Orizzonte troncato al tile e senza curvatura** (audit MED-1): non risolto, fuori ambito. È ora il limite principale per illuminazione e visibilità.
5. Illuminazione e visibilità restano **disattivate** nella config e i loro risultati restano diagnostici (`independently_validated: false`).

## 11. Tempo impiegato
| Fase | Intervallo |
|---|---|
| Analisi e backup | 21:33:49 – 21:35 |
| Calcolo dell'offset (3 metodi) | 21:35 |
| Implementazione e integrazione | 21:35 – 21:36:30 |
| Test, suite, invarianza, end-to-end, checksum | 21:36:30 – ~21:39 |
| Prima versione del report (PARTIAL) | ~21:39 – 21:42 |
| Calcolo SPICE locale, query Horizons, confronto | 21:44 – 21:46:30 |
| Fixture e test di regressione, suite completa | 21:46:30 – 21:47:40 |
| Report finale | 21:47:40 – ~21:50 |
| **Totale** | **circa 15 minuti su 25** |
