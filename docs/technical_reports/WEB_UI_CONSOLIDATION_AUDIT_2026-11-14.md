# Audit Web UI e piano di consolidamento — 2026-11-14

Fase 1 (sola analisi). Nessun file sorgente, raster, algoritmo, soglia o dipendenza è stato modificato.
Baseline test al momento dell'audit: `.venv/bin/python -m pytest -q` → **258 passed** (21,6 s).

Obiettivo: `python src/ui_web/app.py` come unico punto di ingresso ufficiale.

---

## 1. Architettura attuale

### 1.1 Entry point presenti nel repository

| Comando | Tecnologia | Stato reale | Cosa fa |
|---|---|---|---|
| `python src/ui_web/app.py` | `http.server` + **PySide6 QWebEngineView** + three.js | Attivo, in sviluppo (modifiche non committate) | Server HTTP su `127.0.0.1:8765`, finestra Qt che carica `src/ui_web/index.html` |
| `python main.py` | Tkinter + matplotlib | Il più completo funzionalmente; documentato in `README.txt` / `README_IMPLEMENTATION.md` | 15 pulsanti con quasi tutti i moduli scientifici |
| `streamlit run app.py` | Streamlit + Plotly + Skyfield | Legacy | Effemeridi locali (Skyfield + kernel SPICE + `de421.bsp`) e profilo d'orizzonte da DEM |
| `python src/mission_orchestrator.py <config.json>` | CLI | Attivo, è il motore della pipeline completa | `run_mission_workflow()`: 17 step, scrive `reports/mission/*` |
| `python src/lunar_mission_3d.py` | Panda3D | Legacy | Viewer 3D + `mission_planner.build_mission_plan` / `rank_operational_windows` |
| `python src/lunar_3d_app.py` | Plotly → HTML (`ui/lunar_explorer.html`, `ui/vendor/model-viewer.min.js`) | Legacy | Esploratore 3D statico nel browser |
| `python src/lunar_globe_3d.py` | Plotly → `reports/visualization/*.html` | Legacy | Globo 3D statico |
| `python src/lunar_native_viewer.py` | trimesh + pyglet | Legacy (lanciato da `main.py` via `subprocess`) | Viewer del GLB NASA |
| `test_*_models.py` (root) | Panda3D | Script di prova, non test pytest | Caricamento modelli GLB |
| `rebuild_lunar_ui.py`, `correggi_lunar_visual.py`, `install_*.py` | patch-script | Storici | Riscrivono file UI; non fanno parte del runtime |

### 1.2 Flusso della Web UI

```
src/ui_web/app.py
 ├─ ThreadingHTTPServer(127.0.0.1:8765), static root = RADICE DEL REPOSITORY
 │   GET  /api/ephemerides              → astronomy.query_observations (JPL Horizons, rete)
 │                                        → mission_planning.find_operational_windows
 │                                        → mission_analytics.summarize_ephemerides
 │   GET  /api/terrain/lroc-quality     → legge un JSON con nome hardcoded
 │                                        audit-reports/lroc-quality-mask-20261114T181357Z.json
 │   POST /api/communications/link-budget → communications.calculate_link_budget
 │   POST /api/thermal/simulate           → thermal_model.simulate_single_node_thermal
 └─ QApplication + QWebEngineView → http://127.0.0.1:8765/src/ui_web/index.html
       index.html + main.js (three.js da src/ui_web/node_modules, GLB NASA da data/terrain/global)
```

**Il `mission_orchestrator` non è collegato alla Web UI.** Nessun endpoint invoca `run_mission_workflow` né legge `reports/mission/*`.

---

## 2. Funzionalità già presenti nella Web UI

| Funzione | Backend | Note |
|---|---|---|
| Selezione profilo (Pubblico / Educatore / Planner) | solo front-end | |
| Globo lunare 3D (GLB NASA LRO, three.js) | statico | |
| Effemeridi Sole/Terra reali (JPL Horizons) per 3 siti | `/api/ephemerides` | Richiede rete |
| Finestre operative geometriche | `find_operational_windows` | |
| Mission analytics | `summarize_ephemerides` | Fallback JS duplicato (vedi §6) |
| Grafici elevazione Sole/Terra | front-end su dati reali | |
| Link budget RF | `/api/communications/link-budget` | |
| Simulazione termica nodo singolo | `/api/thermal/simulate` | |
| Export JSON missione | **solo client-side** (Blob) | Non usa `mission_report.py`; non salva in `reports/` |
| Qualità LROC (confidenza DTM) | `/api/terrain/lroc-quality` | Solo lettura di un report pre-generato con nome fisso |
| Percorso educativo | statico | |

Verifica eseguita: avviando il server HTTP da `/tmp` (cwd diverso) index, three.js, GLB e API LROC rispondono 200 → **il server è già indipendente dalla working directory** per la parte statica.

---

## 3. Funzionalità mancanti nella Web UI

### 3.1 Da `main.py` (Tkinter) — moduli scientifici già esistenti, senza endpoint

| Funzione Tkinter | Modulo | Priorità |
|---|---|---|
| Audit DEM lunari | `data_quality.audit_raster` | Alta |
| Scoring sito con dati reali | `mission_planning.score_site`, `site_assessment.assess_candidate` | Alta |
| Confronto siti candidati | `site_comparison.compare_candidate_sites` | Alta |
| Pianificazione percorso rover (A*) | `rover_planning.plan_rover_path` | Alta |
| Stima energetica percorso | `rover_energy.estimate_route_energy` | Media |
| Analisi locale pendenza/rugosità | `terrain_metrics.analyze_local_terrain` | Media |
| Profilo d'orizzonte locale | `local_site_analysis` / `horizon_analysis` | Media |
| Illuminazione da orizzonte (diagnostica) | `illumination_analysis.estimate_direct_solar_visibility` | Media |
| Export rapporto missione (JSON+MD) | `mission_report.build/write_mission_report` | Alta |
| Coordinamento multi-rover | `multi_rover.allocate_tasks` | Bassa |
| P-System journal | `psystem_adapter.MissionJournal` | Bassa |

### 3.2 Dal `mission_orchestrator` (pipeline completa, CLI-only)

Esecuzione del workflow da config, e visualizzazione dei risultati di: site identity validation, selezione siti (ranking con qualità LOLA), qualità LOLA/LROC, descent hazard + mappa di rischio, confidence validation, diagnosi geometria lunare/orientazione astronomica, route quality, flotta, journal, mission status report.
**È la lacuna principale**: la Web UI oggi copre solo la parte astronomica/ingegneristica "leggera".

### 3.3 Da Streamlit (`app.py` root)

- Effemeridi **offline** con Skyfield + kernel SPICE locali (la Web UI dipende interamente dalla rete JPL).
- Profilo d'orizzonte interattivo da DEM LOLA (`terrain_horizon.calculate_horizon`).

### 3.4 Da Panda3D (`lunar_mission_3d.py`)

- `mission_planner.rank_operational_windows` / `build_mission_plan`: ranking finestre con priorità scienza/ingegneria. Nella Web UI i campi *Science / Engineering priority* sono raccolti ma **non usati** (solo esportati).

### 3.5 Altre lacune

- Endpoint LROC legato a un file con timestamp fisso (si rompe al prossimo report).
- Nessuna modalità senza display: l'app richiede sempre una finestra Qt.
- Porta 8765 fissa, nessun messaggio chiaro se occupata.
- `three` è in `node_modules/` (ignorato da git): **un clone pulito non ha three.js** → globo 3D rotto. Serve vendorizzarlo o documentare `npm ci`.

---

## 4. Dipendenze

### 4.1 Minime per la Web UI attuale

| Pacchetto | Motivo |
|---|---|
| `PySide6` (Essentials + WebEngine) | **Finestra host di `src/ui_web/app.py`** (~673 MB) |
| `requests` | `astronomy.py` (JPL Horizons) |
| stdlib | `communications`, `thermal_model`, `mission_planning`, `mission_analytics` |
| `three` 0.186.x (npm) | Render 3D front-end |

### 4.2 Necessarie quando il mission orchestrator sarà collegato

`numpy`, `rasterio` (+ `affine`), `pyproj` (`lunar_geometry`), `matplotlib` (grafici report/route), `pytest` (dev).

### 4.3 Usate solo da interfacce legacy

| Pacchetto | Usato da |
|---|---|
| `streamlit`, `altair`, `pydeck`, `pandas`, `pyarrow`, `watchdog`, `tornado`… | `app.py` (Streamlit) |
| `plotly` | `app.py`, `lunar_3d_app.py`, `lunar_globe_3d.py` |
| `skyfield`, `jplephem`, `sgp4` | `app.py` (Streamlit) |
| `Panda3D`, `panda3d-gltf`, `panda3d-simplepbr` | `lunar_mission_3d.py`, `test_*_models.py` |
| `trimesh`, `pyglet` | `lunar_native_viewer.py` |
| `spiceypy` | nessun import trovato in `src/` (da verificare) |
| `starlette`, `uvicorn`, `anyio`, `websockets`, `python-multipart`, `itsdangerous` | nessun import nel codice attivo (residui) |
| `tkinter` | `main.py` (stdlib, non in requirements) |

> ⚠️ **Correzione rispetto all'obiettivo 9**: PySide6 **non** è un'interfaccia secondaria — è il contenitore della Web UI ufficiale. Non può essere dismesso senza cambiare `app.py` (vedi decisione D1).

---

## 5. Interfacce da mantenere o dismettere

| Interfaccia | Raccomandazione | Condizione prima della dismissione |
|---|---|---|
| `src/ui_web/app.py` | **Ufficiale** | — |
| `src/mission_orchestrator.py` CLI | **Mantenere** come motore e come CLI per batch/CI (non è un'interfaccia utente concorrente) | Esposto anche via Web UI |
| `main.py` (Tkinter) | Legacy → spostare in `legacy/` | Dopo parità funzionale §3.1 |
| `app.py` root (Streamlit) | Legacy → `legacy/` | Dopo decisione su effemeridi offline (D2) e profilo orizzonte |
| `src/lunar_mission_3d.py` (Panda3D) | Legacy → `legacy/` | Dopo esposizione di `rank_operational_windows` |
| `src/lunar_3d_app.py`, `src/lunar_globe_3d.py`, `src/lunar_native_viewer.py`, `ui/` | Legacy → `legacy/` | Sostituiti dal globo three.js; nessun import da moduli attivi |
| `test_*_models.py`, `rebuild_lunar_ui.py`, `correggi_lunar_visual.py`, `install_*.py` | Archiviare | Nessun import |
| `README_V3…V10.md`, `README.txt`, `README_IMPLEMENTATION.md`, `IMPLEMENTATION_V11.md` | Archiviare in `docs/history/` | Contenuto unificato nel README |

Pulizia di repository (non di codice) da segnalare: file spuri `json`, `sys`, `np`, `rasterio` in radice (screenshot PostScript da comando `import` errato), ~25 file `*.before-*` in `src/` e ~22 archivi `.tar.gz` in radice (già ignorati da git).

---

## 6. Duplicazioni rilevate

| Duplicazione | Dove | Proposta |
|---|---|---|
| Coordinate siti | `src/astronomy.SITES`, `app.py` (Streamlit), `main.js`, `index.html` | Endpoint `GET /api/sites` da `astronomy.SITES`; front-end lo consuma |
| Calcolo analytics | `mission_analytics.summarize_ephemerides` (Python) e `calculateMissionAnalytics` (JS) | Rimuovere il fallback JS, usare solo il backend |
| Ricerca finestre + allineamento timestamp | `ui_web/app.py`, `mission_orchestrator.collect_astronomy`, `main.py` | Funzione di servizio unica riusata dall'API |
| Due moduli di planning | `mission_planning.py` e `mission_planner.py` | Documentare i ruoli; nessuna modifica agli algoritmi |
| Scrittura report | `main.py` scrive in `reports/` con path hardcoded; orchestrator in `output_dir` | Solo `mission_report` + orchestrator |
| Export missione | JS Blob vs `mission_report.write_mission_report` | Export via endpoint server |
| Codice morto | `drawChart`/`charts()` in `main.js` (grafici sinusoidali illustrativi, non più chiamati) | Rimuovere |

---

## 7. Configurazione, errori, percorsi

- **Dipendenza dalla cwd**: `mission_orchestrator.py` (righe ~1429, 1537, 1668, 1868), `mission_report.py` (righe 51-52, 65, 106, 485) e `main.py` risolvono percorsi relativi rispetto a `Path.cwd()`. `mission_config.example.json` usa percorsi relativi. Lanciando l'orchestratore dalla Web UI senza correzione, i path dipenderebbero da dove l'utente ha avviato il comando.
  → Proposta: un modulo `src/paths.py` con `PROJECT_ROOT` e una funzione di risoluzione "relativo alla radice del progetto"; passaggio esplicito di `project_root` (che `mission_report` già accetta come parametro). Nessuna modifica alla logica scientifica.
- **Static root troppo ampio**: il server espone l'intero repository (verificato: `/src/mission_orchestrator.py` e `/.mission_audit_20261028.json` rispondono 200). È su `127.0.0.1`, ma va ristretto a `src/ui_web/`, `data/terrain/global/` e `reports/` (whitelist).
- **Gestione errori**: già coerente nelle API (`{"status":"error","error":...}` con 400/404/500/502). Va estesa ai nuovi endpoint con lo stesso schema; i 500 oggi includono il testo dell'eccezione.
- **Configurazione**: oggi i parametri arrivano da querystring, body JSON o `mission_config.example.json`. Proposta: la Web UI legge/valida/salva la config dell'orchestratore (`mission_config.json`), unica sorgente.
- **Report**: un solo output dir (`reports/mission/<run_id>/`), scelto dall'orchestratore; la Web UI elenca e serve i report invece di puntare a un file fisso.

---

## 8. Modifiche necessarie (piano per fasi)

Ogni fase: backup in `backups/<data>-<fase>/` dei file toccati, `pytest` prima e dopo (baseline 258 passed), nessuna modifica ad algoritmi, ranking, formule, soglie o raster, nessun commit.

| Fase | Contenuto | Rischio |
|---|---|---|
| **F0 — Preparazione** | Backup; `src/paths.py` (PROJECT_ROOT); test smoke del server HTTP senza Qt (Handler su porta 0) | Basso |
| **F1 — Robustezza entry point** | Whitelist static; porta configurabile + messaggio se occupata; LROC report = più recente in `audit-reports/` invece di nome fisso; vendorizzare `three` o documentare `npm ci`; eliminare codice morto JS | Basso |
| **F2 — Indipendenza dalla cwd** | Orchestrator e `mission_report` risolvono path relativi rispetto a PROJECT_ROOT (oggi `Path.cwd()`); test che lanciano da `/tmp` | Medio (tocca l'orchestratore, non gli algoritmi) |
| **F3 — Collegamento orchestrator** | `POST /api/mission/run` (in thread, con stato), `GET /api/mission/status`, `GET /api/mission/reports`, `GET /api/sites`; pannello Planner che mostra step, warning e artefatti | Medio |
| **F4 — Parità con Tkinter** | Endpoint sottili sui moduli di §3.1 (audit DEM, scoring, confronto siti, rover path + energia, terrain metrics, orizzonte, illuminazione, report). Sono esposizioni di funzioni esistenti, non nuove funzionalità | Medio |
| **F5 — Rimozione duplicati** | Fallback JS analytics, coordinate siti nel front-end, export client-side → server | Basso |
| **F6 — Dipendenze** | `requirements.txt` (Web UI + scienza) e `requirements-legacy.txt`; verifica `pip install` in venv pulito | Basso |
| **F7 — Documentazione** | README unico con solo `python src/ui_web/app.py`; vecchi README in `docs/history/` | Basso |
| **F8 — Dismissione legacy** | Spostamento (non cancellazione) in `legacy/` di Tkinter, Streamlit, Panda3D, viewer Plotly/trimesh, patch-script; ri-esecuzione test | Basso, dopo verifica F4 |

---

## 9. Stima dei tempi

| Fase | Stima |
|---|---|
| F0 | 0,5 g |
| F1 | 1 g |
| F2 | 1 g |
| F3 | 2–3 g |
| F4 | 3–4 g |
| F5 | 0,5 g |
| F6 | 0,5 g |
| F7 | 0,5 g |
| F8 | 0,5 g |
| **Totale** | **≈ 9,5–11,5 giorni/persona** |

Percorso minimo per una demo Space Apps (F0+F1+F2+F3+F6+F7): **≈ 5,5–6,5 giorni**, lasciando F4 per i soli moduli ad alta priorità.

---

## 10. Decisioni richieste prima della Fase 2

- **D1 — PySide6**: (a) mantenere la finestra Qt come unica modalità (richiede ~673 MB e un display); (b) aggiungere a `app.py` un'opzione per aprire il browser di sistema quando PySide6 non è disponibile, rendendo PySide6 opzionale. (b) cambia il comportamento di avvio, quindi va autorizzata.
- **D2 — Effemeridi offline**: la Web UI usa solo JPL Horizons (rete). Esporre il calcolo Skyfield di Streamlit come fallback, o accettare la dipendenza dalla rete alla demo?
- **D3 — Ambito F4**: parità completa con Tkinter o solo i moduli ad alta priorità per la demo.
- **D4 — Modifiche non committate**: 10 file modificati e molti non tracciati sono in corso (LOLA/LROC, site selection, ecc.). Conviene consolidarli/committarli prima di iniziare, per avere un punto di ripristino git oltre ai backup.
