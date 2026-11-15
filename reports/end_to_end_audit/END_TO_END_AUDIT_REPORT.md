# Lunar South Pole Planner — Audit end-to-end (time-boxed)

- **Data:** 2026-11-14
- **Inizio:** 21:21:34 · **Fine verifiche:** 21:24:06 · **Report chiuso:** ~21:27 (ora locale)
- **Tempo effettivo:** circa 6 minuti su 60 disponibili (vedi §9)
- **Ambito:** codice in `src/`, configurazione `mission_config.example.json`, raster in `data/terrain/`
- **Modifiche:** nessuna a codice di produzione, configurazioni o raster. Creati solo questo report e `evidence/`.

---

## 1. Stato complessivo

**PARTIAL — la pipeline è eseguibile e coerente sul piano software, ma con la configurazione attuale produce soltanto un'analisi topografica preliminare.**

| Area | Stato |
|---|---|
| Orchestrazione e propagazione errori | **PASS** |
| Dati LOLA (DEM, LDEC, TOTERR) | **PASS** (struttura) / PARTIAL (riferimento verticale non dichiarato in modo esplicito) |
| Confronto LOLA–LROC | **PARTIAL** |
| Selezione siti | **PASS** (implementazione) / PARTIAL (rappresentatività scientifica) |
| Coerenza sito ↔ DEM | **FAIL** (HIGH-1) |
| Illuminazione / visibilità Terra | **PARTIAL** — implementate ma disattivate e non eseguibili senza offset azimutale |
| Comunicazioni RF / termica | **PARTIAL** — moduli presenti, non integrati nell'orchestratore |
| Rover / energia | **PARTIAL** |
| Test | **PASS** — 150/150 |

Non sono emersi problemi **CRITICAL**: nessun errore che produca silenziosamente risultati numerici errati spacciati per validi. Gli avvisi nei report sono presenti e onesti. Il problema più serio è di **coerenza dei metadati di missione** (HIGH-1).

---

## 2. Diagramma dei componenti

```
mission_config.json
        │
        ▼
run_mission_workflow()  ── step(): cattura eccezioni → status "failed" → completed_with_errors (exit 1)
        │
        ├─[attivo]  descent_hazard_detection ── DEM LOLA (rc fisso 110,110) ─► descent_hazard_report.json
        ├─[attivo]  site_selection ── DEM LOLA + LDEC/TOTERR (diagnostici) ─► site_ranking.json
        ├─[attivo]  lola_lroc_quality ── LOLA 5 m ◄─ LROC 2 m (bilineare) + CONF (nearest) ─► lola_lroc_quality.json
        ├─[attivo]  rover_path ── DEM LOLA (start/goal fissi) ─► rover_plan.json, route_quality.json, PNG
        │
        ├─[off] astronomy (JPL Horizons, rete) ─► observations ─┐
        ├─[off] horizon_analysis (ray-cast nel DEM) ───────────┼─► illumination / visibility_analysis
        │                                                       │     (richiede grid_azimuth_offset_deg: null)
        ├─[off] local_site_analysis, lunar_geometry, site_assessment, confidence_validation, data_quality
        ├─[off] descent_risk_map, rover_energy (fisico), multi_rover, journal
        │
        └─► mission_report (sempre) ─► mission_status_report.json / .md

Non collegati all'orchestratore: communications.py (link budget RF), thermal_model.py,
mission_analytics.py → solo UI web; lroc_quality_mask.py → solo test; site_comparison.py → solo main.py.
```

**Flusso dati reale.** I quattro step attivi sono **indipendenti**: nessuno consuma l'output di un altro. Il ranking dei siti non alimenta né la discesa né il rover, che usano coordinate di griglia fisse nella config. L'unica catena dati è `rover_path → rover_energy`, e `rover_energy` è disattivato.

---

## 3. Verifiche eseguite (con evidenze)

| # | Verifica | Metodo | Esito |
|---|---|---|---|
| V1 | Esecuzione end-to-end con la config di esempio | `python -m src.mission_orchestrator`, output reindirizzato nello scratchpad (`evidence/e2e_config_used.json`) | 4 step eseguiti con successo, `completed_preliminary`, exit 0, 3,7 s — **PASS** |
| V2 | Propagazione errori | Config con TOTERR inesistente | `site_selection: failed (FileNotFoundError)`, `completed_with_errors`, exit 1 — **PASS** |
| V3 | Metadati raster | rasterio: CRS, transform, risoluzione, NoData, bande | Vedi §3.1 — **PASS** |
| V4 | Posizione dei siti nominali rispetto al DEM | Proiezione di `SITES` (astronomy.py) nel CRS del DEM | Site04 = Shackleton; Connecting Ridge fuori dal DEM — **FAIL** (HIGH-1) |
| V5 | Coordinate dei candidati | `map_x/map_y` confrontati con `ds.xy(row, col)` su 400 candidati | 0 discrepanze — **PASS** |
| V6 | Invarianza del ranking con LDEC/TOTERR | Verificata nelle sessioni precedenti (output identici, 400 e 2025 candidati) e coperta da test | **PASS** |
| V7 | Confronto LOLA–LROC | Lettura di `lola_lroc_quality.json` | Vedi §3.2 — **PARTIAL** |
| V8 | Orizzonte e illuminazione | Revisione di `terrain_horizon.py`, `illumination_analysis.py`, `astronomy.py` | Vedi §4 — **PARTIAL** |
| V9 | Formula RF | `communications.py`: FSPL = 92,45 + 20·log10(d_km) + 20·log10(f_GHz) | Costante corretta per km/GHz — **PASS** (formula) |
| V10 | Unità del modello energetico | `rover_energy.py`: g = 1,62 m/s², J→Wh con 3600, efficienza in (0,1] | **PASS** (unità) |
| V11 | Suite di test | `pytest -q` | 150 superati, 0 falliti — **PASS** |
| V12 | Integrità dei raster | SHA-256 prima/dopo | Invariati — **PASS** |

### 3.1 Dati

| Raster | Griglia | Risoluzione | NoData | CRS |
|---|---|---|---|---|
| LOLA `Site04_*_surf.tif` | 3200×3200 float32 | 5 m | NaN | Stereografica polare sud, sfera R = 1 737 400 m |
| LOLA `*_ldec.tif` / `*_toterr.tif` | identica al DEM | 5 m | NaN | identico |
| LROC `NAC_DTM_ESALL_SR12.TIF` | 2500×2500 float32 | 2 m | −3,4028e38 (31 % mascherato nel sottocampione) | identico (R = 1737,4 km) |
| LROC CONF `*_CONF_original.IMG` | 2500×2500 uint8 | 2 m | 0 | identico |

- La copertura LROC (x −5141…−141, y −9859…−4859) è interamente dentro Site04.
- Le griglie LOLA e LROC restano **separate**. Il confronto ricampiona LROC sulla griglia LOLA solo in memoria; i raster originali non vengono modificati.
- **Riferimento verticale.** La label LROC dichiara "height above the sphere 1737.4 km". Il README LOLA indica il frame MOON_ME (DE421) ma **non esplicita** la sfera di riferimento delle quote; la coerenza dipende dal CRS (R = 1737400). La concordanza osservata (mediana +0,70 m su CONF 14) è compatibile con lo stesso riferimento, ma **non lo dimostra**.
- Il frame orizzontale di LROC (ME o PA) non è dichiarato nei metadati letti: **NOT VERIFIED**.

### 3.2 Confronto LOLA–LROC (Site04, griglia LOLA)

- **CONF 14** (668 909 pixel): mediana +0,70 m, RMSE 1,17 m, p95 |Δ| 2,28 m, massimo 18,7 m.
- **CONF 4** (20 800 pixel): RMSE 6,17 m, massimo 192 m, 29 pixel oltre 100 m. Correttamente separata e non mescolata con CONF 14.
- Le classi non documentate (2, 5, 6) e le classi escluse (0, 1) sono riportate a parte. Non viene attribuito loro alcun significato.
- Bias sistematico LROC − LOLA ≈ +0,7 m: **riportato, non corretto**. È coerente con "nessuna correzione automatica", ma va interpretato prima di usare LROC come riferimento.

---

## 4. Problemi individuati

### HIGH

**HIGH-1 — Sito nominale incoerente con il DEM analizzato.**
- `mission_report.site_name = "Connecting Ridge"` e anche `astronomy.site` (default compreso) vale "Connecting Ridge".
- Tutto il terreno analizzato è però `Site04`, che il README LOLA identifica come **"Shackleton rim"**.
- Il centro del DEM proiettato coincide con le coordinate di Shackleton in `SITES` (−89,7668°, −171,87°; pixel 1600,1599).
- Connecting Ridge (Site01) si proietta a x ≈ −11,0 km, y ≈ −12,0 km: **fuori** da Site04, il cui bordo ovest è a x = −9,0 km.
- Effetto: il rapporto di stato dichiara "Sito candidato: Connecting Ridge" per un'analisi topografica di Shackleton. Se si attiva `astronomy`, le effemeridi di Connecting Ridge verrebbero combinate con il terreno di Shackleton.
- Evidenza: V4 e `evidence/mission_status_report.md`.

**HIGH-2 — Le quote dei candidati migliori sono in gran parte interpolate.**
- Nei top 20 candidati la frazione di celle LDEC con **zero ritorni laser** va da 0,82 a 0,93 (mediana 0,90).
- Pendenza e rugosità a 5 m sono quindi calcolate in larga misura su una superficie interpolata (README: "interpolation filling empty pix").
- La diagnostica viene riportata ma non usata, come da requisito: non è un bug. Limita però fortemente l'affidabilità del ranking e va dichiarata in modo esplicito nelle conclusioni.

**HIGH-3 — Illuminazione e visibilità della Terra non sono eseguibili nella configurazione attuale.**
- `illumination` e `visibility_analysis` richiedono `grid_azimuth_offset_deg`, che vale `null`.
- Il codice, correttamente, **non** deduce l'offset.
- In proiezione stereografica polare la convergenza tra nord di griglia e nord geografico dipende dalla longitudine. È ricavabile analiticamente dal CRS, ma questo non è implementato né validato.
- Senza offset non esiste alcun risultato di illuminazione o di visibilità della Terra.

### MEDIUM

- **MED-1 — Orizzonte limitato all'estensione del DEM e senza curvatura lunare** (`terrain_horizon.py`).
  - Il ray-cast si ferma al bordo del tile (16 km) e usa `atan2(z − z0, d)` senza la correzione d²/(2R): circa 7 m a 5 km e 14 m a 7 km, cioè circa 0,08–0,11°.
  - Rilievi lontani fuori tile vengono ignorati, quindi l'orizzonte è **sottostimato** e l'illuminazione sovrastimata.
  - È rilevante al polo, dove l'elevazione solare resta entro circa ±1,5°.
- **MED-2 — Step indipendenti, output non riutilizzati.**
  - Discesa (rc 110,110) e rover (rc 120,113 → 100,100) usano posizioni fisse in un'area a circa 13 km da Shackleton, vicino al bordo nord del DEM.
  - Queste posizioni non sono collegate al ranking, il cui miglior candidato è r2872_c964.
- **MED-3 — Definizioni di rugosità incoerenti tra moduli.**
  - Site selection: deviazione standard dei residui da un piano, soglia 5 m.
  - Discesa: p95 − p5 della quota **non detrendizzata**, soglia 1 m.
  - Nella prova la "rugosità" di discesa vale 15,0 m su un'area con pendenza di 23°: misura soprattutto la pendenza.
- **MED-4 — La soglia di rugosità della selezione (5 m) non è mai vincolante.**
  - Il massimo tra gli eleggibili è 1,13 m e tutti i 313 esclusi lo sono solo per pendenza. Di fatto la selezione è un filtro sulla pendenza.
- **MED-5 — Campionamento rado.**
  - Passo di 159 px (795 m) con finestre di 105 m: circa 1,7 % dell'area analizzata (l'avviso è presente).
  - Un sito migliore può trovarsi tra due nodi della griglia.
- **MED-6 — Downsampling LROC 2 m → 5 m con interpolazione bilineare.**
  - Su un fattore 2,5 il bilineare non media i pixel sorgente (aliasing); `Resampling.average` sarebbe più rappresentativo.
  - Gli effetti sulle statistiche CONF 14 sono probabilmente piccoli, ma non sono quantificati: **NOT VERIFIED**.
- **MED-7 — Fallback silenzioso su un piano rover obsoleto.**
  - `rover_energy` usa `reports/rover_plan.json` se lo step `rover_path` non ha prodotto output in questa esecuzione.
  - Potrebbe così valutare un percorso di un run precedente.
- **MED-8 — Due modelli energetici divergenti.**
  - `rover_path` riporta `estimated_energy_wh` con un costo costante di 0,02 Wh/m (2,68 Wh su 134 m).
  - `rover_energy` usa un modello fisico (rotolamento + salita), ma è disattivato.
  - Il rapporto può mostrare il valore costante come "energia stimata".

### LOW

- **LOW-1** — Il flag `enabled` non è uniforme: `site_selection`, `lola_lroc_quality`, `rover_path` e `descent_hazard_detection` partono ogni volta che la sezione è presente.
- **LOW-2** — `terrain_class_summary.EXCLUDED_BY_CONFIGURED_THRESHOLDS = len(rejected)` include anche i candidati `ANALISI_NON_DISPONIBILE`. Nel run reale sono 0, quindi senza effetto pratico.
- **LOW-3** — Horizons è interrogato con altitudine 0 km invece della quota DEM del sito (tra circa −2,8 e +1,8 km). L'effetto sulla direzione del Sole è trascurabile, mentre sull'orizzonte geometrico locale è piccolo ma non nullo.
- **LOW-4** — Moduli con codice morto o solo UI: `lroc_quality_mask.py` (solo test), `communications.py`, `thermal_model.py`, `mission_analytics.py` (solo UI). Il link budget RF non è collegato alla visibilità della Terra.
- **LOW-5** — `PendingDeprecationWarning` per `transform * (col, row)` in `site_selection.py` (righe 191–192).
- **LOW-6** — Il prodotto LOLA include `*_slperr.tif` (incertezza di pendenza, la più pertinente per la selezione), ma il file non è presente in `data/`.

---

## 5. Componenti non verificati

| Componente | Motivo |
|---|---|
| `astronomy` (JPL Horizons) | Disattivato; richiede rete. Non ho fatto richieste esterne. Non verificato se Horizons usi ME o PA per `coord@301`. |
| `horizon_analysis`, `illumination`, `visibility_analysis` (esecuzione) | Disattivati; offset azimutale `null` (HIGH-3). Verificati solo per revisione del codice. |
| `local_site_analysis`, `lunar_geometry`, `site_assessment`, `confidence_validation`, `data_quality`, `descent_risk_map` | Disattivati nella config; non eseguiti end-to-end. Coperti solo dai test unitari esistenti. |
| `rover_energy` fisico, `multi_rover`, `journal` | Disattivati; mancano i parametri reali del rover. Non ho simulato valori. |
| Thermal e link budget RF in scenario | Non integrati nell'orchestratore; solo formula e unità controllate. |
| UI web (`src/ui_web/*`), viewer 3D | Fuori priorità. |
| Frame orizzontale LROC (ME/PA) | Non dichiarato nei metadati consultati. |
| Impatto quantitativo del bilineare (MED-6) | Richiede un confronto `average` vs `bilinear`: rimandato. |
| Site01 / Site06 | Presenti ma non usati dalla config; non analizzati. |

---

## 6. Risultati dei test

- **Suite completa** (`pytest -q`, 25 file, 150 test): **150 superati, 0 falliti**, 8,5 s.
- Gli avvisi sono solo il `PendingDeprecationWarning` noto (LOW-5).
- Prove end-to-end:
  - run nominale: `completed_preliminary`, exit 0;
  - run con errore indotto: `completed_with_errors`, exit 1.
- **Lacuna di copertura:** nessun test verifica la coerenza tra sito nominale e DEM (HIGH-1), né il fallback del piano rover (MED-7).

---

## 7. Limitazioni scientifiche

1. **Risultato attuale:** un ranking **topografico** preliminare (pendenza p95 e rugosità a 105 m di scala) per Shackleton rim. Non è una selezione di sito di allunaggio.
2. Le quote dei candidati migliori sono interpolate per circa il 90 % (HIGH-2). TOTERR p95 locale è di circa 0,3–0,4 m, ma è un'incertezza **formale** del prodotto, non un errore verificato.
3. Assenti come risultati: illuminazione (la geometria Horizons non è energia disponibile), visibilità della Terra (non equivale a un collegamento RF), termica e link budget.
4. Il confronto LOLA–LROC è diagnostico: non è una validazione geodetica. Il bias di +0,7 m non è spiegato.
5. Nord di griglia e nord geografico non sono riconciliati (HIGH-3). L'orizzonte è troncato al tile ed è senza curvatura (MED-1).
6. La discesa usa una scansione **sintetica** derivata dallo stesso DEM: le discrepanze di circa 0,04 m misurano solo il rumore iniettato.

---

## 8. Piano di correzione (ordinato per priorità)

| Priorità | Azione | Problema |
|---|---|---|
| 1 | Allineare `site_name`/`astronomy.site` al DEM ("Shackleton" per Site04), oppure usare il DEM Site01 per Connecting Ridge. Aggiungere un controllo bloccante che il sito nominale cada dentro il DEM, più un test. | HIGH-1 |
| 2 | Esporre nel ranking (solo report, senza cambiare lo score) la frazione di quote interpolate e dichiararla nelle conclusioni. Valutare l'acquisizione di `*_slperr.tif`. | HIGH-2, LOW-6 |
| 3 | Implementare il calcolo dell'offset azimutale dalla proiezione (convergenza della stereografica polare), con test su punti noti. Mantenerlo esplicito e verificabile. | HIGH-3 |
| 4 | Estendere l'orizzonte con un DEM regionale a risoluzione più bassa e aggiungere la correzione di curvatura. | MED-1 |
| 5 | Collegare il miglior candidato del ranking a discesa e rover, oppure documentare che le posizioni restano fisse. | MED-2 |
| 6 | Uniformare la definizione di rugosità (detrend nella discesa) e rivedere la soglia di 5 m nella selezione. | MED-3, MED-4 |
| 7 | Eliminare il fallback a `reports/rover_plan.json`, oppure fallire se il piano non appartiene al run corrente. Distinguere nel report l'energia "costante" da quella "fisica". | MED-7, MED-8 |
| 8 | Quantificare `average` vs `bilinear` nel confronto LOLA–LROC. | MED-6 |
| 9 | Valutare un campionamento più fitto o raffinato attorno ai migliori candidati. | MED-5 |
| 10 | Uniformare `enabled`, correggere il conteggio delle classi, usare l'altitudine del sito in Horizons, risolvere l'avviso `@`, rimuovere o integrare i moduli scollegati. | LOW-1…5 |

---

## 9. Tempo impiegato

| Fase | Orario | Durata |
|---|---|---|
| Architettura e lancio end-to-end in background | 21:21:34 – 21:22 | ~1 min |
| Dati, CRS e confronto LOLA–LROC | 21:22 – 21:22:40 | <1 min |
| Selezione siti, coordinate, coerenza sito/DEM | 21:22:40 – 21:23:15 | <1 min |
| Illuminazione, comunicazioni, rover/energia | 21:23:15 – 21:23:53 | <1 min |
| Test completi ed evidenze | 21:23:53 – 21:24:06 | <1 min |
| Stesura del report | 21:24 – ~21:27 | ~3 min |
| **Totale** | | **circa 6 minuti su 60** |

Il tempo è stato inferiore al limite: verifiche e test sono stati eseguiti in parallelo, e il contesto di site selection e LOLA era già noto dalle sessioni precedenti. Le voci in §5 restano aperte per scelta di ambito (rete esterna, step disattivati, parametri reali mancanti), non per esaurimento del tempo.

## Evidenze

In `reports/end_to_end_audit/evidence/` (percorsi dello scratchpad anonimizzati):
- `e2e_config_used.json`
- `e2e_orchestrator_stdout.json`
- `e2e_failure_propagation_stdout.json`
- `lola_lroc_quality.json`
- `descent_hazard_report.json`
- `route_quality.json`
- `mission_status_report.md`
