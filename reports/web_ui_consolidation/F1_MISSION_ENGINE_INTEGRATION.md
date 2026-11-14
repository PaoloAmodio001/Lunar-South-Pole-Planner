# F1 — Integrazione Web UI ↔ Mission Orchestrator

Data: 2026-11-14
Comando ufficiale (invariato): `python src/ui_web/app.py`. La modalità predefinita resta browser; PySide6 resta opzionale (`--desktop`).

## VERDETTO: **PASS**

La Web UI avvia il vero orchestratore (`src/mission_orchestrator.py`) e ne riporta stato e risultati reali. Ho verificato una missione end-to-end con la configurazione di esempio e i dati locali, sia tramite API sia tramite rendering in Chromium headless. Gli output scientifici prodotti dalla Web UI coincidono con quelli della CLI ufficiale (§7). Test: **347 passed, 0 failed, 0 skipped**.

---

## 1. Architettura trovata (analisi preliminare)

| Elemento | Comportamento effettivo |
|---|---|
| Ingresso del motore | `run_mission_workflow(config_path)` (sincrono). CLI: `python -m src.mission_orchestrator <config.json>` |
| Configurazione | JSON; `_read_json` richiede un oggetto. Il controllo preventivo `validate_mission_site_identity(config)` viene eseguito prima di ogni step e solleva `SiteIdentityError` |
| Attivazione sezioni | `descent_hazard_detection`, `site_selection`, `lola_lroc_quality` e `rover_path` girano **se presenti**, senza guardare `enabled`. `mission_report` è attivo salvo `enabled: false`. Tutte le altre sezioni richiedono `enabled: true` |
| Gestione errori | Ogni step è racchiuso in `step()`: un'eccezione diventa `{"status":"failed", ...}` e la missione continua |
| Esito | `mission_report.json` → `status` ∈ {`completed`, `completed_preliminary`, `completed_with_warnings`, `completed_with_errors`}. Exit code CLI: 0 = ok, 1 = `completed_with_errors`, 2 = eccezione (es. configurazione o identità del sito) |
| Avanzamento | **Nessun callback di progresso intermedio** |
| Percorsi | **Tutti relativi alla cwd** (DEM, `output_dir`, `Path.cwd()` usato come project_root nel mission report) |
| Report | `output_dir/mission_report.json` più artifact per step (`site_ranking.json`, `lola_lroc_quality.json`, `rover_route_map.png`, `mission_status_report.{json,md}`, …) |
| Rete | Solo lo step `astronomy` (JPL Horizons) richiede la rete ed è disabilitato nell'esempio. Gli step terreno lavorano offline sui dati locali |

## 2. Modalità di integrazione

**Il vero orchestratore viene eseguito in un sottoprocesso**: `[sys.executable, "-m", "src.mission_orchestrator", <config>]` con `cwd=PROJECT_ROOT`, lanciato da un thread di sorveglianza in background.

Perché un sottoprocesso:
- **Percorsi relativi alla cwd.** L'orchestratore li risolve rispetto alla directory corrente. Un `os.chdir` dentro un server multi-thread sarebbe pericoloso; la cwd fissata del sottoprocesso lo evita.
- **Server mai bloccato.** Un thread daemon resta in `wait()` sul processo; il server continua a rispondere. Misurato: 0,7 ms per una risorsa statica durante l'esecuzione.
- **Crash isolati.** Un'eccezione o un crash nativo (rasterio/GDAL) non abbatte il server.
- **Nessuna dipendenza nuova.** Solo stdlib.
- **Stesso codice della CLI.** Il percorso eseguito è esattamente quello ufficiale; nessuna seconda implementazione.

Isolamento delle esecuzioni: ogni avvio crea `reports/web_runs/<id>/` con questi file:
- `config.json`: la configurazione effettiva. Rispetto all'originale cambia solo `output_dir`, che punta a `reports/web_runs/<id>/output`, e l'avviso di validazione lo segnala. `reports/mission/` non viene sovrascritto.
- `output/`: tutto ciò che scrive il motore.
- `stdout.log` e `stderr.log`.
- `job.json`: lo stato dell'esecuzione.

Stati esposti, calcolati dall'esito reale:

| Stato UI | Condizione |
|---|---|
| `running` | processo attivo. La UI mostra "Missione in esecuzione. L'orchestratore non espone avanzamento intermedio." e il tempo trascorso reale. **Nessuna percentuale** |
| `completed` | `mission_report.status` ∈ {completed, completed_preliminary, completed_with_warnings} |
| `completed_with_errors` | `mission_report.status == completed_with_errors` |
| `failed` | nessun report valido (eccezione, crash, config illeggibile). Mostra motivo, exit code e coda di stdout/stderr |
| `failed` (interrotta) | `job.json` ancora `running` dopo un riavvio del server: l'esito non è stato osservato e viene dichiarato tale |

Prevenzione dei doppi avvii: una sola missione alla volta (lock); un secondo avvio riceve **409** con l'id in corso. Alla riapertura della pagina la UI riprende il monitoraggio della missione in corso. Il pulsante RUN resta disabilitato durante l'esecuzione.

Validazione (`validate_config`): è conservativa e non modifica la configurazione.
- **Formato:** oggetto JSON, al massimo 256 KB, niente NaN/Infinity, ogni sezione deve essere un oggetto.
- **Percorsi di input** (`dem_path`, `lola_path`, `lroc_path`, `confidence_path`, `*_density_path`, `*_error_path`, `horizon_json`, `raster_path`, `comparison_path`): solo relativi, senza `..`, `~`, `\` o NUL, e solo sotto `data/` o `reports/`.
- **`report_name`:** solo un nome di file semplice, senza separatori e senza punto iniziale.
- **`journal.path`:** solo sotto `reports/`.
- **File di input mancanti** in sezioni attive: **avviso, non errore**. Lo step fallirà e l'orchestratore lo riporterà come `failed`, senza nascondere nulla.
- **Controllo identità del sito:** esegue la funzione dell'orchestratore stesso (`validate_mission_site_identity`) su una copia con percorsi assoluti.

## 3. Endpoint introdotti

| Metodo | Percorso | Funzione |
|---|---|---|
| GET | `/api/mission/configs` | Catalogo delle configurazioni selezionabili (solo id ed etichetta, **mai percorsi**). Oggi contiene `example` |
| GET | `/api/mission/configs/<id>` | Contenuto JSON di una configurazione del catalogo |
| POST | `/api/mission/validate` | `{config_id}` oppure `{config, filename}` → `{valid, errors, warnings, sections, site_identity}` |
| POST | `/api/mission/runs` | Avvio. 202 `{run_id}`; 400 se la configurazione non è valida; 409 se una missione è già in corso |
| GET | `/api/mission/runs` | Elenco delle esecuzioni più `running_id` |
| GET | `/api/mission/runs/<id32hex>` | Stato; a esecuzione terminata, riassunto dei risultati |
| GET | `/api/mission/runs/<id32hex>/report` | `mission_report.json` |
| GET | `/api/mission/runs/<id32hex>/artifacts/<key>` | Artifact **per chiave**, solo se il percorso dichiarato nel report risolve **dentro** `reports/web_runs/<id>/output` |

Endpoint F0 non modificati: `/api/ephemerides`, `/api/terrain/lroc-quality`, `/api/communications/link-budget`, `/api/thermal/simulate`. Alla whitelist statica F0 è stato aggiunto solo `/mission.js`.

Il browser non può fornire percorsi da leggere al server: le configurazioni si scelgono per id oppure si caricano come contenuto, e gli artifact si scaricano per chiave. L'id esecuzione è validato con `^[0-9a-f]{32}$`. Nessun endpoint esegue comandi arbitrari: il comando è fisso, con la configurazione validata come unico argomento. Variabili d'ambiente e segreti non vengono mai serializzati; `pid` e i timer interni vengono rimossi dalle risposte.

## 4. Visualizzazione dei risultati (UI)

Nuova sezione **MISSION ENGINE · ORCHESTRATOR** nel pannello inferiore. Usa gli stili esistenti (`engineering-section`, `analytics-card`, `windows-table`) più 7 regole CSS minime. Contiene:
- **Configurazione:** selezione dal catalogo oppure caricamento di un file JSON; pulsanti VALIDATE CONFIG e RUN MISSION.
- **Validazione:** errori, avvisi, sezioni attive e disabilitate, esito dell'identità del sito.
- **Stato:** stato onesto, id dell'esecuzione, tempo trascorso, exit code.
- **Riepilogo:** stato del motore, run_id del motore, sito e identità, step OK/falliti, configurazione con hash.
- **Step del motore:** tabella con esito ed errore reale; elenco delle **sezioni non eseguite** con il motivo ("disabilitata nella configurazione").
- **Ranking topografico:** metodo, soglie, idonei ed esclusi, top 20 con score, componenti, metriche, classe terreno e metriche escluse dallo score.
- **Qualità dati LOLA:** **tabella separata**, con l'indicazione esplicita `affects_score = false` presa dal motore.
- **Altri step:** risultati JSON grezzi, comprimibili.
- **Avvisi:** avvisi del motore e della validazione.
- **File prodotti:** link al report e agli artifact, con il percorso; configurazione effettiva comprimibile.

Tutti i valori mostrati vengono letti dai file del motore; la UI non ricalcola nulla. Il testo viene inserito con `textContent`, quindi non c'è rischio di XSS.

## 5. File

### Backup
`backups/F1_mission_engine_20261114T231806/` (con `SHA256SUMS`):

| File | SHA-256 prima di F1 |
|---|---|
| `src/ui_web/app.py` | `aa770e7d55588103a95a74c2705c88eb65bc6e31e6777a530755d332c39e636a` |
| `src/ui_web/index.html` | `ab6af098d0c56f084a5f559eb939787f084f7f72642946cd32a0dde3ecabaa70` |
| `src/ui_web/main.js` | `7f953fd8ebc7fd1440f7563cc7f578e08b913b32914f6d1b75b4387cf1a0f38b` (salvato per prudenza, non modificato) |
| `tests/test_web_ui_app.py` | `4aa4418ecdfdaa7bc1ba94a135f4efd4041b61de8d417ed480904d93fc0bddd3` (salvato per prudenza, non modificato) |

### Modificati o creati
L'elenco è verificato con `find -newer` rispetto all'inizio di F1.

| File | Tipo |
|---|---|
| `src/ui_web/app.py` | modificato: routing `/api/mission/*`, `/mission.js` in whitelist, terminazione del sottoprocesso alla chiusura |
| `src/ui_web/index.html` | modificato: sezione MISSION ENGINE, tag `<script src="/mission.js">`, 7 regole CSS |
| `src/ui_web/mission_runner.py` | nuovo: validazione, `MissionManager`, riassunto dei risultati (nessuna logica scientifica) |
| `src/ui_web/mission.js` | nuovo: logica UI della sezione |
| `tests/test_web_ui_mission.py` | nuovo: 50 test |
| `reports/web_ui_consolidation/F1_MISSION_ENGINE_INTEGRATION.md` | nuovo: questo report |
| `reports/web_runs/` | nuova cartella di output, con 2 esecuzioni E2E reali dalla Web UI |

## 6. Test

Suite completa: **347 passed** in 40,9 s (prima di F1: 297; +50 nuovi). Nessun test esistente è stato modificato.

| # | Requisito | Test in `tests/test_web_ui_mission.py` |
|---|---|---|
| 1 | Validazione della configurazione | `test_minimal_config_is_valid`, `test_example_config_valid_with_site_identity`, `test_missing_input_is_warning_not_error`, `test_site_identity_conflict_rejected` |
| 2 | Avvio effettivo dell'orchestratore | `test_real_orchestrator_completed`, `test_real_orchestrator_completed_with_errors` (vero `python -m src.mission_orchestrator`) |
| 3 | Background non bloccante | `test_http_mission_lifecycle`: durante l'esecuzione `/main.js` e lo stato rispondono in meno di 1 s |
| 4 | Recupero dello stato | `test_http_mission_lifecycle` (`running` → `completed`, nessuna percentuale) |
| 5 | Recupero dei risultati | `test_real_orchestrator_*`, `test_http_mission_lifecycle` (report via HTTP), `test_e2e_example_config` |
| 6 | Gestione delle eccezioni | `test_engine_crash_reported_as_failed`, `test_orchestrator_exception_reported_as_failed` (exit 2 reale), `test_spawn_failure_releases_lock`, `test_interrupted_run_reported_as_failed` |
| 7 | Configurazioni non valide | `test_invalid_configs_rejected` (12 casi), `test_oversized_config_rejected`, `test_invalid_config_not_started`, `test_http_invalid_start` (5 casi), `test_catalog_does_not_accept_paths` |
| 8 | Avvii duplicati | `test_duplicate_start_rejected` (anche il riavvio dopo il termine), 409 in `test_http_mission_lifecycle` |
| 9 | Accesso controllato ai report | `test_artifact_outside_run_dir_not_served`, `test_run_id_format_enforced` (5), `test_http_unauthorized_mission_paths` (9) |
| 10 | Compatibilità F0 | `tests/test_web_ui_app.py` (39 test F0, tutti verdi), `test_ui_assets_served`, `test_http_configs_catalog`; controllo manuale del comando ufficiale da `/tmp` con apertura del browser (§8) |
| 11 | Nessuna regressione | suite completa 347/347 |

Le configurazioni di test sono sintetiche (`{"mission_report":{"enabled":false}}` e una variante con DEM mancante) ed eseguono il vero motore in meno di 0,3 s. Nessun download.

## 7. Prova end-to-end e confronto prima/dopo

1. **Baseline**, prima di ogni modifica F1: CLI ufficiale `python -m src.mission_orchestrator` sulla configurazione di esempio, con il solo `output_dir` spostato in una cartella temporanea. Esito `completed_preliminary` in 3,6 s; step `descent_hazard_detection`, `site_selection`, `lola_lroc_quality` e `rover_path` tutti `success`.
2. **Web UI**: `POST /api/mission/runs {"config_id":"example"}` sul server avviato da `/tmp` (esecuzione `14450381a9dc4c7fa76b4e41e7e05ee4`). Esito `completed_preliminary`, exit 0, 4 step `success`, 87 candidati idonei e 313 esclusi. Top 3: `candidate_r2872_c964` 74,14 · `candidate_r2236_c646` 74,08 · `candidate_r2554_c328` 73,47.
3. **Confronto file per file** tra baseline e Web UI, normalizzando solo `generated_utc`, `run_id` e il prefisso del percorso di output:

| File | Esito |
|---|---|
| `site_ranking.json` | identico |
| `lola_lroc_quality.json` | identico |
| `descent_hazard_report.json` | identico |
| `rover_plan.json`, `route_quality.json` | identici |
| `mission_report.json`, `mission_status_report.json` | identici |
| `rover_route_map.png` | **identico byte per byte** |
| `mission_status_report.md` | differisce solo per le righe "Generato UTC" e "Run ID" |

4. **Rendering nel browser**: seconda esecuzione (`55ab6956af504a0b883591257ede8486`) caricata in Chromium headless. La sezione mostra stato COMPLETATA, motore `completed_preliminary`, sito Shackleton (identità validated), 4 step OK, 13 sezioni "disabilitata nella configurazione" e il ranking con metodo, soglie e candidati. Nessun errore JavaScript nel log.
5. **Integrità del motore**: SHA-256 di `src/mission_orchestrator.py`, `src/site_selection.py` e `mission_config.example.json` identici prima e dopo. `find -newer` conferma che nessun file fuori da `src/ui_web/` e `tests/` è stato toccato.

## 8. Comando ufficiale

`cd /tmp && python ~/Lunar-South-Pole-Planner/src/ui_web/app.py` → `Web UI attiva su http://127.0.0.1:<porta>/`. Il browser viene aperto sull'URL corretto (verificato con `BROWSER` stub). Host e porta (`--host`, `--port`, `LUNAR_UI_*`), gestione della porta occupata e `--desktop` opzionale sono invariati rispetto a F0.

## 9. Funzionalità non ancora integrate

- **Catalogo configurazioni con una sola voce** (`mission_config.example.json`). Le altre configurazioni si caricano come file. Non ho aggiunto altre voci per non introdurre configurazioni non verificate.
- **Annullamento di una missione in corso dalla UI**: non richiesto, non implementato. Il sottoprocesso viene comunque terminato alla chiusura del server.
- **Storico esecuzioni**: l'API `/api/mission/runs` elenca le ultime 20 esecuzioni, ma la UI mostra solo l'ultima o quella in corso. Manca un selettore dello storico.
- **Editor della configurazione nel browser**: non implementato. Si seleziona o si carica un file intero.
- **Avanzamento per step**: non disponibile, perché il motore non lo espone. Lo stato viene mostrato in modo onesto.
- **Visualizzazione dei candidati sul globo 3D**: non fa parte di F1.

## 10. Problemi residui

1. **Click sui pulsanti non automatizzato in un browser.** Il ciclo VALIDATE → RUN → polling è verificato via HTTP con gli stessi endpoint usati da `mission.js`; il rendering dei risultati è verificato in Chromium headless. Non ci sono test end-to-end con click simulati (Playwright o simili non sono installati e non li ho aggiunti).
2. **Esecuzioni accumulate.** `reports/web_runs/` cresce a ogni esecuzione (circa 800 KB con l'esempio) e non c'è pulizia automatica. Non è in `.gitignore`: va deciso se escluderla prima del commit.
3. **`journal.path` resta quello configurato** (es. `reports/mission/mission_events.jsonl`): se il journal è abilitato, le esecuzioni Web scrivono sul journal condiviso. Il comportamento è identico a quello della CLI ed è limitato a `reports/`.
4. **Disallineamento delle regole di attivazione.** Lo specchio di `mission_runner.py` serve solo a mostrare le sezioni attive e non attive. Se l'orchestratore cambia le sue regole, va aggiornato. Lo stato reale mostrato dopo l'esecuzione viene sempre dal report del motore.
5. **Avvisi pre-esistenti.** I 7262 avvisi della suite sono `PendingDeprecationWarning` già presenti in `src/site_selection.py` e non sono stati toccati.

## 11. Conferme

- Algoritmi, formule, soglie, pesi, criteri di ranking e risultati del motore: **non modificati**.
- Raster, DEM, LOLA, LROC, kernel SPICE e altri dati scientifici: **non modificati** e mai scritti.
- Tkinter, Streamlit e Panda3D legacy: **non toccati**.
- Funzionamento offline: invariato; l'esempio gira interamente sui dati locali.
- Nessun commit e nessun push.

## 12. Tempo impiegato

Circa 8 minuti di orologio di sistema, dal primo comando F1 alla stesura del report, contro un limite di 60.
