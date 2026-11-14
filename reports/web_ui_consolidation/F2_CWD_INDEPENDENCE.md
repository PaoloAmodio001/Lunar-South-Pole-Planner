# F2 — Indipendenza dalla directory di avvio

Data: 2026-11-14 · Base: commit `ae4b9ba`

## VERDETTO: **PASS**

Il flusso di missione (orchestratore, mission report, controllo dell'identità del sito, Web UI) ora funziona allo stesso modo da qualunque directory di avvio. L'ho verificato dalla radice del progetto, da `/tmp` (script diretto e `python -m`) e tramite la Web UI avviata da `/tmp`. Gli output scientifici sono identici alla baseline. Suite di test: **361 passed, 0 failed**.

Una conseguenza visibile, voluta e documentata in §6: le **stringhe di percorso** scritte nei report sono ora assolute anziché relative. I file a cui puntano sono gli stessi e i valori scientifici non cambiano.

---

## 1. Problema di partenza (baseline misurata)

| Avvio | Esito prima di F2 |
|---|---|
| radice del progetto, `python -m src.mission_orchestrator cfg.json` | exit 0, `completed_preliminary` |
| `/tmp`, `python -m src.mission_orchestrator cfg.json` | `ModuleNotFoundError: No module named 'src'` |
| `/tmp`, stesso comando con `PYTHONPATH=<repo>` | exit 2: `FileNotFoundError: Raster di terreno non trovato: data/terrain/official-lola/…` |

Punti dipendenti dalla cwd che ho trovato:
- 4 `Path.cwd()` in `src/mission_orchestrator.py`: verifica degli artifact, `project_root` del mission report (2 punti), controllo di esistenza degli artifact;
- 1 `Path.cwd()` in `src/mission_report.py`, nel dettaglio degli artifact del Markdown;
- il default `project_root="."` di `build_mission_report`;
- tutti i percorsi della configurazione: `output_dir`, `*_path`, `horizon_json`, `energy.plan_json`, `journal.path`. Venivano passati ai moduli così com'erano e quindi risolti rispetto alla cwd.

## 2. Soluzione

**`src/paths.py` (nuovo).** `PROJECT_ROOT = Path(__file__).resolve().parents[1]` e `resolve_project_path(value)`:
- percorso assoluto → invariato;
- percorso relativo → `PROJECT_ROOT / value`;
- `None` → `None`.

Non verifica l'esistenza del file, così un input mancante produce ancora l'errore del modulo che lo legge.

**Regola unica.** Un percorso relativo dentro una configurazione di missione è relativo a `PROJECT_ROOT`, mai alla cwd.

Le configurazioni esistenti usano già percorsi relativi alla radice del progetto (`data/…`, `reports/mission`), quindi restano compatibili senza modifiche.

**`src/mission_orchestrator.py`** (solo risoluzione dei percorsi):
- **`resolve_config_paths(config)`:** restituisce una copia della configurazione (l'input non viene modificato) in cui vengono risolti solo `output_dir`, le chiavi di `CONFIG_PATH_KEYS` e `journal.path`. Le chiavi sono `dem_path`, `lola_path`, `lroc_path`, `confidence_path`, `density_path`, `error_path`, `lola_density_path`, `lola_error_path`, `horizon_json`, `raster_path`, `comparison_path`, `plan_json`. Nessun altro valore viene toccato: soglie, nomi, coordinate e `report_name` restano come sono.
- **`resolve_config_file(path)`:** il file di configurazione passato come argomento è cercato prima nella cwd (convenzione degli argomenti da riga di comando), poi in `PROJECT_ROOT`.
- **`run_mission_workflow`:** risolve il file di configurazione e i percorsi prima del controllo di identità del sito e di qualsiasi step.
- **`validate_mission_site_identity`:** risolve anche lei i raster relativi, così funziona anche se chiamata direttamente da un'altra cwd, come fa la Web UI.
- **`Path.cwd()`:** i 4 usi sono sostituiti con `PROJECT_ROOT`; il default `reports/rover_plan.json` dello step energia viene ancorato a `PROJECT_ROOT`.
- **Avvio come script:** `python /percorso/src/mission_orchestrator.py` ora funziona da qualunque directory. È un bootstrap di `sys.path` di 3 righe, attivo solo quando il file è eseguito come script.

**`src/mission_report.py`:**
- `project_root=None` come default, che significa `PROJECT_ROOT` (prima `"."`, cioè la cwd);
- `write_mission_report` risolve un `output_dir` relativo rispetto a `PROJECT_ROOT`;
- il `Path.cwd()` del Markdown è sostituito con `PROJECT_ROOT`.

**Non modificati**, perché non coinvolti nel flusso di missione: i default `output_path="reports/…"` dei moduli scientifici. L'orchestratore passa sempre percorsi espliciti, e quei default li usano le GUI legacy. Nessuna formula, soglia, peso, ranking, raster o kernel è stato toccato: il diff dell'orchestratore riguarda solo import, funzioni di risoluzione e le righe con percorsi.

## 3. File

### Backup
`backups/F2_cwd_independence_20261114T234344/` (con `SHA256SUMS`):

| File | SHA-256 prima di F2 |
|---|---|
| `src/mission_orchestrator.py` | `6e67ddd7530adcef7a935cef046be1f405d830b132ce64568dc57ff6bdaabc20` |
| `src/mission_report.py` | `b1ba855b364afd3be8f7ad25a3c98a73b796e9dff1e7b455241a0d6e4b9e4495` |
| `tests/test_web_ui_mission.py` | salvato prima della modifica (§4) |

### Modificati o creati
Elenco verificato con `find -newer` rispetto all'inizio di F2.

| File | Tipo | Righe |
|---|---|---|
| `src/paths.py` | nuovo | 28 |
| `src/mission_orchestrator.py` | modificato | +62 / −7 |
| `src/mission_report.py` | modificato | +6 / −4 |
| `tests/test_cwd_independence.py` | nuovo | 14 test |
| `tests/test_web_ui_mission.py` | modificato (1 asserzione, §4) | +2 / −1 |
| `reports/web_ui_consolidation/F2_CWD_INDEPENDENCE.md` | nuovo | questo report |

## 4. Test

Suite completa: **361 passed** (prima di F2: 347; +14 nuovi), 0 failed, 0 skipped.

**Unico test esistente adattato:** `test_web_ui_mission.py::test_real_orchestrator_completed_with_errors` confrontava il testo esatto dell'errore, che conteneva il percorso relativo `data/__f1_test_missing__.tif`. Ora il modulo riceve il percorso risolto, quindi il messaggio contiene `PROJECT_ROOT/data/__f1_test_missing__.tif`. L'asserzione verifica ancora il **messaggio esatto**, con il nuovo percorso: il test non è stato reso meno severo.

Nuovi test in `tests/test_cwd_independence.py`:

| Caso richiesto | Test |
|---|---|
| Percorsi relativi | `test_resolve_relative_absolute_none`, `test_resolve_config_paths_only_path_keys`, `test_workflow_relative_output_dir_anchored_to_project_root` |
| Percorsi assoluti | `test_resolve_relative_absolute_none`, `test_resolve_config_paths_only_path_keys` (assoluti invariati), `test_workflow_from_external_cwd_absolute_output` |
| File mancanti | `test_missing_relative_input_reported_with_project_path`: un file omonimo nella cwd **non** viene usato; l'errore cita il percorso nel progetto. Anche `test_missing_config_file_raises` |
| Avvio da directory esterne | `test_workflow_from_external_cwd_*` (nulla viene scritto nella cwd), `test_cli_script_from_external_cwd`, `test_cli_module_with_pythonpath_from_external_cwd`, `test_cli_example_like_config_from_tmp` (dati reali, `completed_preliminary`, 4 step `success`) |
| Componenti coinvolti | `test_site_identity_relative_raster_from_external_cwd`, `test_mission_report_defaults_use_project_root`, `test_write_mission_report_relative_dir`, `test_resolve_config_file_cwd_first_then_project_root` |

I test usano configurazioni sintetiche e cartelle temporanee, senza scaricare nulla. L'unico test che scrive dentro `reports/` usa una cartella con nome univoco e la rimuove alla fine.

## 5. Confronto degli output prima/dopo

Configurazione: `mission_config.example.json` con `output_dir` relativo, rediretta in una cartella temporanea per non sovrascrivere `reports/mission`.

| Esecuzione | Esito |
|---|---|
| **Prima**, dalla radice (baseline) | exit 0, `completed_preliminary`, 4 step `success` |
| **Dopo**, dalla radice | exit 0, `completed_preliminary`, 4 step `success` |
| **Dopo**, da `/tmp`, `python <repo>/src/mission_orchestrator.py` (senza PYTHONPATH) | exit 0, `completed_preliminary`, 4 step `success`; **nessun file scritto in `/tmp`** |
| **Dopo**, da `/tmp`, `PYTHONPATH=<repo> python -m src.mission_orchestrator` | exit 0 |
| **Dopo**, Web UI avviata da `/tmp` (`POST /api/mission/runs {"config_id":"example"}`) | `completed`, motore `completed_preliminary`, exit 0; 8/8 artifact scaricabili; top 3 `candidate_r2872_c964` 74,14 · `candidate_r2236_c646` 74,08 · `candidate_r2554_c328` 73,47 |

Confronto file per file tra la baseline e ciascuna esecuzione "dopo". La normalizzazione rimuove solo `generated_utc`, `run_id`, il percorso della configurazione e il prefisso delle cartelle `PROJECT_ROOT` e di output. In più ho confrontato a parte **tutti i valori numerici e booleani senza alcuna normalizzazione**.

| File | Normalizzato | Valori numerici/booleani grezzi |
|---|---|---|
| `site_ranking.json` | identico | identici |
| `lola_lroc_quality.json` | identico | identici |
| `descent_hazard_report.json` | identico | identici |
| `rover_plan.json`, `route_quality.json` | identici | identici |
| `mission_report.json`, `mission_status_report.json` | identici | identici |
| `rover_route_map.png` | **identico byte per byte** | — |
| `mission_status_report.md` | identico dopo aver rimosso "Generato UTC", "Run ID" e il prefisso del percorso | — |

Il risultato è lo stesso per le tre esecuzioni "dopo" (radice, `/tmp`, Web UI).

## 6. Problemi residui

1. **Stringhe di percorso assolute nei report** (conseguenza voluta). Prima: `"dem_path": "data/terrain/official-lola/Site04_final_adj_5mpp_surf.tif"`. Dopo: `"/home/paolo/Lunar-South-Pole-Planner/data/terrain/…"`. Lo stesso vale per artifact, messaggi d'errore e `raster_path` dell'identità del sito. Il file è lo stesso e la Web UI li gestisce già (artifact scaricabili, percorsi mostrati relativi). Però i report contengono il percorso locale della macchina e sono meno portabili. Per mantenere le stringhe relative bisognerebbe toccare i moduli scientifici che ripetono il percorso ricevuto (`site_selection`, `rover_planning`, `lunar_geometry`, …), cosa che ho evitato per rispettare il vincolo. Si può fare in una fase successiva, se lo ritieni utile.
2. **Cambio di semantica** per chi usava configurazioni con percorsi relativi a una cwd *diversa* dalla radice del progetto: ora vanno resi assoluti o relativi al progetto. Nessuna configurazione nel repository e nessun test usava questo schema.
3. **GUI legacy non toccate.** `main.py` (Tkinter) passa ancora `project_root=Path.cwd()` in modo esplicito; il suo comportamento resta quello di prima. Anche i default `reports/…` dei moduli scientifici, usati solo dalle GUI legacy, restano relativi alla cwd.
4. **Web UI.** `mission_runner.py` lancia ancora il sottoprocesso con `cwd=PROJECT_ROOT` e rende assoluti i percorsi nella validazione preventiva. Ora non serve più, ma è innocuo e l'ho lasciato invariato per non toccare F1.
5. Nessuna nuova dipendenza.

## 7. Conferme

- Formule, algoritmi, ranking, soglie, pesi: **non modificati**.
- Raster, DEM, LOLA, LROC, kernel SPICE: **non modificati**.
- Comportamento scientifico: **invariato** (§5).
- Nessun commit e nessun push.

## 8. Tempo impiegato

Circa 7 minuti di orologio di sistema, contro un limite di 30.
