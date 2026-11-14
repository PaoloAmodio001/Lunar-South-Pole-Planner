# F5 — Consolidamento architetturale

Data: 2026-11-15 · Base: commit `ddb3283` più le modifiche F4, **non ancora committate**: `science_api.py`, `science.js`, `app.py`, `index.html`, test F4.

## VERDETTO: **PARTIAL**

Ho rimosso o centralizzato cinque duplicazioni reali; una di queste chiude anche una lacuna di validazione. Le verifiche sono complete: 410 test passati, rendering nel browser, `/api/ephemerides` con rete reale.

Restano non trattate due voci della specifica F5 e della tabella §6 (§5 di questo report): l'export lato client e la funzione di servizio unica per finestre e allineamento dei timestamp. Per questo il verdetto è PARTIAL e non PASS.

---

## 1. Specifica F5 originale

Fonte: `docs/technical_reports/WEB_UI_CONSOLIDATION_AUDIT_2026-11-14.md`.
- **§8:** "**F5 — Rimozione duplicati** · Fallback JS analytics, coordinate siti nel front-end, export client-side → server · Rischio basso".
- **§6 (duplicazioni rilevate):**
  - coordinate dei siti;
  - calcolo degli analytics (Python e JS);
  - ricerca delle finestre e allineamento dei timestamp (Web UI, orchestratore, `main.py`);
  - due moduli di planning;
  - scrittura dei report;
  - export missione (Blob JS e `mission_report`);
  - codice morto `drawChart`/`charts()`.

## 2. Duplicazioni trovate e interventi

| # | Duplicazione effettiva | Dove | Intervento F5 |
|---|---|---|---|
| 1 | **Coordinate dei siti** copiate a mano | `main.js` (oggetto `sites` con lat/lon) rispetto a `src/astronomy.SITES` | `main.js` le legge da `GET /api/sites` (F3), cioè da `astronomy.SITES`. Se l'API non risponde mostra "coordinate non disponibili" e non usa valori di riserva |
| 2 | **Analytics calcolati due volte** | `calculateMissionAnalytics` in `main.js` (~75 righe) rispetto a `src.mission_analytics.summarize_ephemerides` | Fallback JS **rimosso**. Se il server non fornisce gli analytics, la UI segnala l'errore e non ricalcola nulla. `/api/ephemerides` li include sempre (test e verifica con rete reale) |
| 3 | **Codice morto** | `drawChart` / `charts()` in `main.js` (grafici sinusoidali "illustrativi", non più chiamati) | **Rimosso** |
| 4 | **Chiavi di percorso definite due volte** | `mission_runner.READ_PATH_KEYS` (F1) rispetto a `mission_orchestrator.CONFIG_PATH_KEYS` (F2) | `READ_PATH_KEYS = CONFIG_PATH_KEYS`: unica definizione, nel motore. **Effetto di sicurezza:** la copia F1 non conteneva `plan_json`, quindi `energy.plan_json` in una configurazione caricata non veniva validato (per esempio `"/etc/passwd"` passava la validazione). Ora viene rifiutato |
| 5 | **Risoluzione dei percorsi e radice duplicate** | `PROJECT_ROOT` calcolato in `app.py`, `mission_runner.py` e `src/paths.py`; la validazione preventiva F1 rendeva assoluti i percorsi con una propria copia della logica | Un solo `PROJECT_ROOT` (`src/paths.py`). `app.py` mantiene solo il bootstrap di `sys.path` necessario all'avvio come script. La validazione preventiva usa `resolve_config_paths` del motore: stessa risoluzione di `run_mission_workflow` |

### Separazione dei livelli dopo F5

| Livello | Componenti | Responsabilità |
|---|---|---|
| UI | `index.html`, `main.js`, `mission.js`, `science.js` | Presentazione; nessun calcolo scientifico, nessuna coordinata o soglia copiata dal backend |
| API | `app.py` (routing, whitelist), `mission_runner.py` (esecuzioni del motore), `science_api.py` (endpoint scientifici sottili) | Validazione, sicurezza, invocazione dei moduli; nessun algoritmo |
| Motore e scienza | `mission_orchestrator.py`, `src/*.py` scientifici, `src/paths.py` | Algoritmi, risoluzione dei percorsi, definizione delle chiavi di configurazione |

Interfacce legacy (`main.py` Tkinter, `app.py` Streamlit, Panda3D): **non toccate**. Mantengono le loro copie (§5) finché saranno attive, come richiesto per la fase di transizione.

## 3. File

### Backup
`backups/F5_architecture_20261115T000852/` (con `SHA256SUMS`): `app.py`, `index.html`, `main.js`, `mission_runner.py`, `science_api.py`, nello stato **post-F4** (inizio di F5).

### Modificati o creati
Elenco verificato con `find -newer` rispetto all'inizio di F5.

| File | Modifica F5 |
|---|---|
| `src/ui_web/main.js` | siti da `/api/sites`; rimossi `calculateMissionAnalytics` e `drawChart`/`charts` (+17 / −101 righe) |
| `src/ui_web/mission_runner.py` | `PROJECT_ROOT` da `src.paths`; `READ_PATH_KEYS = CONFIG_PATH_KEYS`; validazione preventiva con `resolve_config_paths` |
| `src/ui_web/app.py` | `PROJECT_ROOT` da `src.paths` (bootstrap minimo invariato) |
| `tests/test_web_ui_f5.py` | nuovo: 11 test |
| `reports/web_ui_consolidation/F5_ARCHITECTURE_CONSOLIDATION.md` | nuovo: questo report |

`index.html` e `science_api.py` sono nel backup ma non sono stati modificati in F5. Non ho toccato algoritmi, formule, soglie, ranking, orchestratore, dati, raster o kernel.

## 4. Test e verifiche

- **Suite completa: 410 passed, 0 failed** (dopo F4: 399; +11 nuovi). Nessun test esistente modificato.
- `tests/test_web_ui_f5.py`:
  - **Fonte unica:** stesso oggetto `PROJECT_ROOT` in `app`, `mission_runner` e `science_api`; `READ_PATH_KEYS is CONFIG_PATH_KEYS`.
  - **Validazione:** `energy.plan_json` assoluto, con `..` o fuori da `data/`/`reports/` viene rifiutato (3 casi).
  - **Validazione preventiva:** con la configurazione di esempio, avviata da una cwd esterna, risulta `validated` e i percorsi mostrati restano relativi.
  - **Frontend:** nessuna coordinata di `SITES` in `main.js`; uso di `/api/sites`; nomi dei siti nella `<select>` identici a `SITES`; fallback analytics e codice morto assenti.
  - **Backend:** `/api/ephemerides` include sempre `analytics` con lo schema atteso, con le effemeridi sostituite da dati sintetici, senza rete.
- **Verifiche manuali** (server avviato da `/tmp`):
  - **Chromium headless:** `#coords` = "-89.77°, -171.87°", letto da `/api/sites`; `#targetName` = Shackleton; globo three.js r186 attivo; nessun errore JavaScript.
  - **`/api/ephemerides` con rete reale (Nobile, 12 h):** `ok`, 13 campioni, analytics `lunar-ephemeris-analytics/1.0` dal backend.
- **Funzionalità F0–F4:** tutti i loro test sono verdi; whitelist, sicurezza degli endpoint e indipendenza dalla cwd invariate.

## 5. Problemi residui e duplicazioni non trattate

1. **Export missione lato client** (Blob JS, specifica F5) **non spostato** sul server. L'export contiene dati presenti solo nel browser (priorità scienza/ingegneria, ultimi modelli RF/termici calcolati). Spostarlo richiede un nuovo endpoint e la definizione di come quei dati arrivano al server. Il report persistente lato server esiste già tramite il Mission Engine (F1, `mission_report`).
2. **Ricerca delle finestre e allineamento dei timestamp** duplicati in `ui_web/app.py` (`/api/ephemerides`), `mission_orchestrator` (step astronomia) e `main.py`. Unificarli richiede di estrarre una funzione di servizio dall'orchestratore. Non l'ho fatto: tocca il motore e i suoi output dovrebbero essere ri-verificati, cosa che non rientrava nel tempo disponibile.
3. **Nomi dei siti** ancora scritti in `index.html` (`<select>` e pulsanti del profilo Pubblico). Le coordinate non sono più duplicate; i nomi sono verificati da un test di coerenza con `SITES`, ma la generazione dinamica della `<select>` non è stata introdotta.
4. **Interfacce legacy:** `main.py` (percorsi `reports/` codificati, `project_root=Path.cwd()`) e `app.py` Streamlit (coordinate proprie) mantengono le loro copie. Vanno trattate alla dismissione (F8).
5. **`mission_planning.py` e `mission_planner.py`:** ruoli da documentare.
   - `mission_planning`: finestre operative e scoring del sito, usato da Web UI e orchestratore.
   - `mission_planner`: ranking delle finestre per priorità scienza/ingegneria, usato solo da Panda3D.
   Nessuna modifica.
6. **F4 non ancora committata.** Le modifiche F5 a `app.py` sono sullo stesso file delle modifiche F4 non committate. Per due commit separati serve uno staging parziale, oppure commit in ordine F4 → F5 usando i backup come riferimento: `backups/F5_architecture_*` contiene esattamente lo stato post-F4.

## 6. Tempo

L'orologio di sistema ha misurato circa 3 minuti tra il primo comando F5 e la verifica dei file, entro il limite di 30.
