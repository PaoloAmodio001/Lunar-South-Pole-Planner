# F3 — Collegamento orchestrator: completamento minimo

Data: 2026-11-14 · Base: commit `102a086` (F0, F1, F2 pubblicati)
Specifica: `docs/technical_reports/WEB_UI_CONSOLIDATION_AUDIT_2026-11-14.md`, §8, riga F3:
> `POST /api/mission/run` (in thread, con stato), `GET /api/mission/status`, `GET /api/mission/reports`, `GET /api/sites`; pannello Planner che mostra step, warning e artefatti.

## VERDETTO: **PASS**

Tutti e cinque i requisiti F3 sono disponibili con i percorsi originali della specifica. Ho riusato l'implementazione F1 aggiungendo alias sottili e due endpoint di sola lettura, senza duplicare la logica. Verifiche: 369 test passati, prova end-to-end reale con la configurazione di esempio, output scientifici identici alla baseline.

## 1. Audit: requisiti F3 rispetto a F1

| Requisito F3 | Implementazione F1 esistente | Stato prima di F3 | Intervento |
|---|---|---|---|
| `POST /api/mission/run`, in background con stato | `POST /api/mission/runs` → `MissionManager.start` (sottoprocesso sorvegliato da un thread, lock contro i doppi avvii) | PARZIALE: solo il nome differiva | **Alias**: `/api/mission/run` chiama lo stesso `handle_mission_post` |
| `GET /api/mission/status` | `GET /api/mission/runs/<id>` → `status_payload`; `running_id` in `GET /api/mission/runs` | PARZIALE: serviva conoscere l'id | **Alias** `handle_mission_status`: `?id=<id>` oppure l'esecuzione in corso o, in mancanza, la più recente. Riusa `status_payload` |
| `GET /api/mission/reports` | Report e artifact per singola esecuzione (`/runs/<id>/report`, `/artifacts/<key>`); `/runs` elenca le esecuzioni ma non i report | MANCANTE come elenco | **Nuovo** `MissionManager.list_reports()`: elenca solo i `mission_report.json` realmente presenti, con URL del report e degli artifact. Riusa `list_runs`, `read_report` e `_artifact_path` (stesso controllo di contenimento F1) |
| `GET /api/sites` | assente | MANCANTE | **Nuovo**: legge `src.astronomy.SITES` (nome, latitudine, longitudine est), sola lettura |
| Pannello Planner: step, warning, artefatti | Sezione MISSION ENGINE (F1), visibile solo nel profilo Planner. Mostra sito, stato, step eseguiti e non eseguiti, warning ed errori, artefatti, report | COMPLETO, tranne l'elenco dei report precedenti | **Aggiunta minima**: lista "REPORT DISPONIBILI" alimentata da `/api/mission/reports`; un clic carica l'esecuzione |

Nessuna percentuale di avanzamento: lo stato durante l'esecuzione resta il testo reale di F1 ("L'orchestratore non espone avanzamento intermedio").

## 2. File

### Backup
`backups/F3_orchestrator_link_20261114T235442/`, con `SHA256SUMS`, contiene `app.py`, `mission_runner.py`, `mission.js` e `index.html` prima di F3.

### Modificati o creati
Elenco verificato con `find -newer` rispetto all'inizio di F3.

| File | Modifica | Righe |
|---|---|---|
| `src/ui_web/app.py` | alias `POST /api/mission/run`; `GET /api/mission/status`, `GET /api/mission/reports`, `GET /api/sites` | +27 |
| `src/ui_web/mission_runner.py` | `MissionManager.list_reports()` | +25 |
| `src/ui_web/mission.js` | `loadReports()` all'avvio e al termine di ogni esecuzione | +23 |
| `src/ui_web/index.html` | contenitore `#missionReports` | +2 |
| `tests/test_web_ui_f3.py` | nuovo: 8 test | — |
| `reports/web_ui_consolidation/F3_IMPLEMENTATION_REPORT.md` | nuovo: questo report | — |

Non ho toccato orchestratore, moduli scientifici, configurazioni, dati, raster né kernel. La whitelist statica F0 è invariata: nessuna nuova risorsa statica esposta. L'indipendenza dalla cwd introdotta in F2 è invariata.

## 3. Endpoint verificati

| Endpoint | Verifica |
|---|---|
| `GET /api/sites` | 200; contenuto identico a `astronomy.SITES` (Shackleton, Connecting Ridge, Nobile) |
| `POST /api/mission/run` | 202 con `run_id`; 409 su avvio duplicato con l'id in corso; 400 con configurazione non valida (percorso assoluto `/etc/passwd`) |
| `GET /api/mission/status` | senza esecuzioni: `run: null`; durante l'esecuzione: `running` con il testo reale, senza `%`; a fine esecuzione: `completed` / `completed_with_errors` con risultati del motore; `?id=` non valido o inesistente → 404 |
| `GET /api/mission/reports` | elenco vuoto senza report; dopo un'esecuzione elenca il report reale e l'URL scaricabile risponde 200 |
| Accesso non autorizzato | `/src/ui_web/mission_runner.py`, `/reports/web_runs/`, `status?id=..%2F..%2Fetc`, `/api/sites/../../etc/passwd` → 404 |

## 4. Test

- **Suite completa: 369 passed, 0 failed** (prima di F3: 361; +8 nuovi). Nessun test esistente modificato.
- `tests/test_web_ui_f3.py` copre:
  - siti da `astronomy.SITES`;
  - stato ed elenco dei report vuoti;
  - ciclo completo tramite alias: avvio, `running`, duplicato 409, `completed`, report elencato e scaricabile;
  - fallimento di uno step visibile in `/status` (`completed_with_errors`, `FileNotFoundError`);
  - id non validi → 404;
  - configurazione non valida → 400 senza avvio;
  - pannello e JS collegati a `/api/mission/reports`.
- I test usano il vero orchestratore con configurazioni sintetiche (fixture F1 riusate), senza scaricare nulla.
- I test F1 (`test_web_ui_mission.py`, `test_web_ui_app.py`) e F2 (`test_cwd_independence.py`) sono tutti verdi.

## 5. Prova end-to-end

Server avviato da `/tmp` (`python <repo>/src/ui_web/app.py --no-browser --port 8831`); configurazione di esempio e dati locali.

| Passo | Risultato |
|---|---|
| `GET /api/sites` | 3 siti con coordinate |
| `POST /api/mission/run {"config_id":"example"}` | 202, run `1f5dc2589d58401ab965cff6557f5931` |
| `GET /api/mission/status` durante l'esecuzione | `running` · "Missione in esecuzione. L'orchestratore non espone avanzamento intermedio." |
| Secondo `POST /api/mission/run` | 409 |
| `GET /api/mission/status?id=…` a fine esecuzione | `completed`, motore `completed_preliminary`, sito Shackleton, 4 step `success`, 13 sezioni non eseguite (disabilitate), 4 warning, 8 artefatti |
| `GET /api/mission/reports` | 4 report reali (questo e le esecuzioni F1/F2 precedenti), ciascuno con 8 artefatti |
| Chromium headless | pannello in stato "COMPLETATA", lista "REPORT DISPONIBILI" popolata con data, sito, stato, configurazione e link a `mission_report.json` |
| Output scientifici rispetto alla baseline F2 | tutti i JSON identici (normalizzati) e valori numerici/booleani grezzi identici; `rover_route_map.png` identico byte per byte |

## 6. Limiti residui

1. **Report della CLI non elencati.** `GET /api/mission/reports` elenca solo i report prodotti dalla Web UI (`reports/web_runs/`). I report della CLI in `reports/mission/` non compaiono: quella cartella non ha un id per esecuzione e viene sovrascritta a ogni esecuzione.
2. **§7 dell'audit non applicato** (non fa parte della riga F3): cartella di output `reports/mission/<run_id>/` e salvataggio della configurazione dalla Web UI. Restano le scelte F1: `reports/web_runs/<id>/` e configurazione solo letta e validata.
3. **`/api/sites` non usato dal frontend.** Le coordinate dei siti restano duplicate in `index.html` e `main.js`: secondo l'audit (§6, riga F5) la rimozione dei duplicati appartiene a F5.
4. **Esecuzione in sottoprocesso.** La specifica dice "in thread"; F1 usa un sottoprocesso sorvegliato da un thread. Il comportamento visibile è lo stesso (non blocca, ha uno stato) ed è più sicuro: isolamento da crash ed eccezioni, nessun `chdir`. Non l'ho modificato.
5. **Click nel browser non automatizzati.** Il caricamento di un report dalla lista è verificato via HTTP e tramite il rendering headless, non con click simulati.

## 7. Tempo

Circa 3 minuti di orologio di sistema per audit, modifiche, test ed E2E, più la stesura del report: entro il limite di 20 minuti.
