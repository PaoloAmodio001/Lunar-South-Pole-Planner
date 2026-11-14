# F4 — Recupero delle funzionalità scientifiche nella Web UI

Data: 2026-11-15 · Base: commit `ddb3283` (F0–F3 pubblicati)

## VERDETTO: **PARTIAL**

Ho integrato e verificato cinque funzionalità scientifiche prioritarie, con un risultato reale per ciascuna e un confronto diretto con il modulo originale: audit DEM, terreno locale, profilo d'orizzonte, percorso rover più stima energetica, confronto siti. Non sono integrate, e restano documentate come residue (§7), quattro funzioni che il prompt elenca tra le priorità: scoring sito combinato DEM + effemeridi, analisi locale per sito, diagnostica di illuminazione e rappresentazione 3D dei risultati. Per questo il verdetto è PARTIAL e non PASS.

Test: **399 passed, 0 failed**.

---

## 1. Specifica F4 originale

Fonte: `docs/technical_reports/WEB_UI_CONSOLIDATION_AUDIT_2026-11-14.md`, §8:

> **F4 — Parità con Tkinter** · Endpoint sottili sui moduli di §3.1 (audit DEM, scoring, confronto siti, rover path + energia, terrain metrics, orizzonte, illuminazione, report). Sono esposizioni di funzioni esistenti, non nuove funzionalità · Rischio: Medio · Stima: 3–4 g

La decisione D3 dell'audit chiedeva di scegliere tra parità completa e solo moduli ad alta priorità. Il prompt F4 ha fissato le priorità 1–6 e il limite di 90 minuti.

## 2. Matrice delle funzionalità

| # | Funzionalità | Modulo scientifico | Web UI prima di F4 | Legacy | Intervento F4 | Priorità |
|---|---|---|---|---|---|---|
| 1 | Ranking siti (pendenza/rugosità + qualità LOLA) | `site_selection.select_candidate_sites` | ✅ via Mission Engine (F1) | — (CLI) | nessuno | alta |
| 1 | Confronto geometrico dei 3 siti (Sole/Terra) | `site_comparison.compare_candidate_sites` | ❌ | Tkinter `compare_sites` | **integrato**: `POST /api/science/site-comparison` | alta |
| 1 | Scoring sito (DEM + effemeridi) | `site_assessment.assess_candidate`, `mission_planning.score_site` | ❌ | Tkinter `score_current_site` | **residuo** (§7) | alta |
| 2 | Audit DEM (metadati, copertura, quote) | `data_quality.audit_raster` | ❌ | Tkinter `audit_dem` | **integrato**: `POST /api/science/dem-audit` | alta |
| 2 | Pendenza/rugosità locali in una cella | `terrain_metrics.analyze_local_terrain` | ❌ | Tkinter (via scoring) | **integrato**: `POST /api/science/terrain` | alta |
| 2 | Qualità LOLA/LROC, confidenza DTM | `lola_lroc_quality`, `lroc_quality_mask` | ✅ pannello LROC + Mission Engine | — | nessuno | — |
| 3 | Profilo d'orizzonte da DEM | `horizon_analysis.calculate_and_write_horizon` | ❌ (solo da config orchestratore, disabilitato nell'esempio) | Streamlit (`terrain_horizon`) | **integrato**: `POST /api/science/horizon` + grafico | media |
| 3 | Analisi locale per sito (LDEC/TOTERR) | `local_site_analysis.analyze_local_site` | solo via config orchestratore | — | **residuo** | media |
| 4 | Finestre di visibilità Sole/Terra | `mission_planning.find_operational_windows`, `mission_analytics` | ✅ `/api/ephemerides` (pre-F0) | Tkinter, Streamlit | nessuno | — |
| 4 | Illuminazione da orizzonte (diagnostica) | `illumination_analysis.estimate_direct_solar_visibility` | solo via config orchestratore | Tkinter | **residuo** (§7) | media |
| 4 | Effemeridi offline (Skyfield + SPICE) | `app.py` Streamlit | ❌ | Streamlit | **residuo** (decisione D2 aperta) | media |
| 5 | Percorso rover A* su DEM | `rover_planning.plan_rover_path` | ✅ solo via Mission Engine (parametri fissi da config) | Tkinter `open_rover_planner` | **integrato**: `POST /api/science/rover-plan` con parametri + grafico | alta |
| 5 | Stima energetica percorso | `rover_energy.estimate_route_energy` | solo via config orchestratore (disabilitato) | Tkinter | **integrato** nello stesso endpoint, solo con parametri reali forniti | media |
| 6 | Globo 3D | three.js (F0) | ✅ | Panda3D, Plotly, trimesh | nessuno | — |
| 6 | Risultati rappresentati graficamente | — | ❌ | Tkinter (matplotlib) | **parziale**: grafici 2D di orizzonte e percorso; **niente proiezione sul globo 3D** (residuo) | media |
| — | Export rapporto missione | `mission_report` | ✅ via Mission Engine (F1) | Tkinter | nessuno | — |
| — | Multi-rover, journal P-System | `multi_rover`, `psystem_adapter` | solo via config orchestratore | Tkinter | **residuo** (priorità bassa nell'audit) | bassa |
| — | Ranking finestre scienza/ingegneria | `mission_planner.rank_operational_windows` | ❌ | Panda3D | **residuo** | media |

## 3. Funzioni integrate

Architettura: un nuovo modulo `src/ui_web/science_api.py` contiene solo validazione, catalogo e invocazione dei moduli; nessun algoritmo. Le rotte in `app.py` seguono lo schema F1/F3. La sezione **SCIENCE TOOLS** si trova nel pannello Planner ed è gestita da `science.js`.

| Endpoint | Modulo riutilizzato | Input | Output e provenienza |
|---|---|---|---|
| `GET /api/science/rasters` | — | — | catalogo fisso: `lola_site04` (LOLA Site04 5 m/px), `lroc_nac_sr12` (LROC NAC DTM); disponibilità e dimensioni |
| `POST /api/science/dem-audit` | `data_quality.audit_raster` | `raster_id` | audit completo del modulo |
| `POST /api/science/terrain` | `terrain_metrics.analyze_local_terrain` | `raster_id`, `row`, `col`, `radius_pixels` (1–250) | metriche del modulo |
| `POST /api/science/horizon` | `horizon_analysis.calculate_and_write_horizon` | `raster_id`, `row`, `col`, `observer_height_m` (0–100), `azimuth_step_deg` (0,5–45), `max_distance_m` (≤ 20 km) | profilo del modulo, scritto in una cartella temporanea e poi eliminato |
| `POST /api/science/rover-plan` | `rover_planning.plan_rover_path` (+ `rover_energy.estimate_route_energy`) | `start_rc`, `goal_rc`, `max_slope_deg`, `energy_wh_per_m`, `energy_budget_wh` (opz.), `energy` (opz.: **tutti** i parametri reali del rover) | piano e, se richiesta, stima energetica |
| `POST /api/science/site-comparison` | `site_comparison.compare_candidate_sites` | `start_utc`, `hours` (1–168) | confronto del modulo per i siti di `astronomy.SITES`; **richiede la rete** |

Regole applicate:
- **Provenienza esplicita.** Ogni risposta riporta `provenance`: modulo, funzione, raster, istante, tipo di risultato ("diagnostica preliminare dal modulo originale; non certificata"). Le note e gli avvisi dei moduli sono mostrati nella UI.
- **Nessun valore inventato.** NaN e infinito diventano `null`. La stima energetica parte solo se l'utente fornisce **tutti** i parametri del rover: i campi sono vuoti per impostazione predefinita e, se ne manca uno, la risposta è un 400 che elenca i parametri mancanti. Il confronto siti senza rete riporta l'errore per sito, con `matched_samples = 0` e nessuna elevazione.
- **Catalogo raster fisso.** Il browser non può mai indicare un percorso; il percorso rover è limitato al DEM LOLA. Righe e colonne vengono controllate rispetto alle dimensioni reali del raster.
- **Limiti solo sul costo di calcolo** (raggio, distanza, passo, ore); soglie e algoritmi dei moduli non cambiano. Al massimo 2 calcoli contemporanei; oltre risponde 503, così il server resta reattivo.
- **Errori coerenti** con lo schema F1: 400 input, 404 raster sconosciuto o assente, 502 servizio esterno, 503 occupato, 500 generico senza testo interno.
- **Indipendenza dalla cwd (F2).** I percorsi vengono dal catalogo basato su `PROJECT_ROOT`. Il piano temporaneo passato a `rover_energy` contiene il DEM con percorso assoluto, così la stima funziona anche se il server è stato avviato da un'altra directory (verificato).
- **Offline.** Audit, terreno, orizzonte e rover funzionano senza rete; solo il confronto siti ne ha bisogno, e la UI lo dichiara.

## 4. File

### Backup
`backups/F4_scientific_features_20261115T000040/` (con `SHA256SUMS`): `src/ui_web/app.py`, `src/ui_web/index.html` prima di F4.

### Modificati o creati
Elenco verificato con `find -newer` rispetto all'inizio di F4.

| File | Tipo | Righe |
|---|---|---|
| `src/ui_web/science_api.py` | nuovo | 350 |
| `src/ui_web/science.js` | nuovo | 212 |
| `src/ui_web/app.py` | modificato: rotte `/api/science/*`, `/science.js` in whitelist | +27 |
| `src/ui_web/index.html` | modificato: sezione SCIENCE TOOLS, script, 3 regole CSS | +64 |
| `tests/test_web_ui_science.py` | nuovo | 30 test |
| `reports/web_ui_consolidation/F4_SCIENTIFIC_FEATURES_INTEGRATION.md` | nuovo | questo report |

Non ho modificato moduli scientifici, orchestratore, configurazioni, raster, DEM, LROC/LOLA, kernel o interfacce legacy. Nessuna nuova dipendenza: `numpy` e `rasterio` erano già richiesti dal motore. Non resta nessun file temporaneo in `/tmp`.

## 5. Test

**Suite completa: 399 passed, 0 failed** (prima di F4: 369; +30 nuovi). Nessun test esistente modificato.

`tests/test_web_ui_science.py`:

| Area | Verifica |
|---|---|
| Collegamento al modulo | dem-audit, terreno e orizzonte: risposta **uguale** alla chiamata diretta del modulo originale (escluso `generated_utc`); stima energetica: `energy_wh` e `distance_m` uguali alla chiamata diretta di `estimate_route_energy` |
| Coerenza con il motore | percorso rover con i parametri di `mission_config.example.json` = output dello step `rover_path` dell'orchestratore (133,99494936611666 m, 2,6798989873223333 Wh, 19,799291107416934°, 558 nodi, 22 celle), uguaglianza esatta |
| Input non validi | cella fuori dal raster, negativi, non interi, booleani, raggio o distanza oltre i limiti, `start_rc` malformato, DTM LROC per il rover, data non valida, ore > 168 → 400 |
| Nessun valore inventato | energia con parametri incompleti → 400 con l'elenco dei mancanti; confronto siti offline (rete simulata assente) → errori per sito, nessuna elevazione |
| Sicurezza | `raster_id` come percorso (`../../etc/passwd`, `/etc/passwd`, percorso del DEM, `null`, numero) → 404; `/src/ui_web/science_api.py`, `/science_api.py`, endpoint sconosciuti → 404 |
| Concorrenza | slot occupati → 503 |
| F2 | stima energetica con cwd in una cartella temporanea: funziona e non scrive nulla nella cwd |
| UI | `/science.js` servito, sezione presente in `/` |
| F1/F3 | tutti i test precedenti verdi |

## 6. Prova end-to-end e confronto degli output

Server avviato da `/tmp` (`python <repo>/src/ui_web/app.py --no-browser`), dati locali:

| Strumento | Esito | Tempo |
|---|---|---|
| Audit DEM `lroc_nac_sr12` | 200; 2500×2500, 69,01 % valido, quote 638,05 / 1470,49 / 1739,41 m; avviso del modulo "Unità della banda non dichiarate" mostrato | 0,40 s |
| Terreno `lola_site04` (2872, 964), r = 10 | 200; slope P95 5,15079372607353°, rugosità 0,657111310981842 m, copertura 1,0 | 0,04 s |
| Orizzonte (1600, 1599), h = 1 m, passo 2°, 5 km | 200; 180 campioni, orizzonte massimo 32,92° | 6,2 s |
| Rover (120,113) → (100,100) + energia | 200; 133,99 m, 558 nodi; energia totale stimata 40,75 Wh, entro il budget | 0,59 s |
| Confronto siti (2026-11-01, 12 h) | 200; NASA/JPL Horizons raggiunto, 13 campioni per ciascuno dei 3 siti | 4,6 s |
| Chromium headless | sezione SCIENCE TOOLS renderizzata, catalogo raster caricato dal server (LOLA 3200×3200, LROC 2500×2500), nessun errore JavaScript | — |

**Confronto con gli output del motore:**
- **Terreno.** Le metriche per la cella (2872, 964) sono **identiche** a quelle del candidato n. 1 `candidate_r2872_c964` in `site_ranking.json` prodotto dall'orchestratore nella baseline F2: `slope_p95_deg`, `roughness_plane_residual_std_m` e `valid_fraction` coincidono fino all'ultima cifra.
- **Rover.** Il percorso è identico allo step `rover_path` dell'orchestratore (vedi §5).
- **Audit, terreno, orizzonte, energia.** Le risposte sono identiche alle chiamate dirette ai moduli (test automatici).

## 7. Funzionalità ancora mancanti

| Funzione | Motivo per cui non è stata integrata |
|---|---|
| Scoring sito con DEM + effemeridi (`site_assessment.assess_candidate`) | Richiede di accoppiare le serie Horizons di Sole e Terra con una cella DEM, come fa Tkinter, più la confidenza LROC. Per farlo bene serve definire come la UI fornisce effemeridi coerenti con la cella: con il tempo rimasto avrei rischiato un'integrazione superficiale |
| Analisi locale per sito (`local_site_analysis`, con LDEC/TOTERR) | Richiede le coordinate dell'osservatore in metri, ricavate dalla geometria lunare; oggi è raggiungibile solo via configurazione dell'orchestratore |
| Diagnostica di illuminazione (`illumination_analysis`) | Dipende da orizzonte, effemeridi Horizons (rete) e dalla risoluzione dell'offset azimutale griglia↔nord, già gestita dall'orchestratore (`_resolve_grid_azimuth_offset`). Una versione diretta duplicherebbe quella logica: resta disponibile via Mission Engine con una configurazione che abiliti `astronomy`, `horizon_analysis` e `illumination` |
| Effemeridi offline (Skyfield + SPICE) | Decisione D2 dell'audit ancora aperta |
| Ranking finestre scienza/ingegneria (`mission_planner`, Panda3D) | Non avviato per limite di tempo |
| Proiezione dei risultati sul globo 3D | Il globo usa un GLB globale senza frame validato rispetto alla griglia del DEM Site04; disegnare il percorso o i candidati richiederebbe una trasformazione non validata. Ho usato grafici 2D in coordinate di griglia, dichiarate come tali |
| Multi-rover, journal P-System | Priorità bassa nell'audit; disponibili via configurazione dell'orchestratore |

## 8. Problemi residui

1. **Click nella UI non automatizzati.** Gli endpoint sono verificati via HTTP e la sezione è verificata in rendering headless, ma senza click simulati: non ci sono test e2e di browser con interazione.
2. **Orizzonte lento.** Il calcolo blocca un thread del server per 6–9 s (5 km, passo 2°). Il server resta reattivo grazie al multithreading e al limite di 2 calcoli, ma non c'è una coda né un annullamento.
3. **Coordinate di griglia.** Terreno, orizzonte e rover lavorano in riga/colonna DEM, come i moduli originali. La UI non converte coordinate geografiche in celle; i valori predefiniti sono le celle usate dalla configurazione di esempio (1600/1599 = Shackleton secondo la validazione dell'identità del sito).
4. **Coordinate duplicate.** Le coordinate dei siti restano duplicate nel frontend: la rimozione dei duplicati spetta a F5.
5. **Nessun salvataggio.** Gli strumenti F4 restituiscono il risultato nella risposta e non scrivono report in `reports/`. Per un report persistente si usa il Mission Engine (F1).

## 9. Tempo

L'orologio di sistema ha misurato circa 6 minuti tra il primo comando F4 e la verifica dei file. Il lavoro completo, compresi analisi, test ed E2E, è rimasto entro il limite di 90 minuti.
