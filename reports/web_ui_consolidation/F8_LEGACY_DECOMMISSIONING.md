# F8 — Dismissione legacy

Data: 2026-11-15.

| Parte | Orario | Durata |
|---|---|---|
| Prima parte | 00:29:30 → 00:33 | ≈ 4 min |
| Completamento (strada B) | 00:35:41 → 00:41 | ≈ 6 min |
| **Totale** | | **≈ 10 minuti** (limite 60) |

## VERDETTO: **PASS**

Tutti i componenti che la specifica F8 indica come legacy sono stati **spostati in `legacy/`**, senza cancellare nulla. Il contenuto è identico all'originale (SHA-256).
L'unica interfaccia ufficiale rimasta è `python src/ui_web/app.py`.
Web UI, Science Tools e Mission Engine funzionano, e la suite completa è verde (**410 passed**).

**Precisazione sul verdetto.** Per Tkinter, Streamlit, Panda3D e trimesh le condizioni di §5 (parità funzionale, decisione D2, `rank_operational_windows`) **non sono soddisfatte**. L'archiviazione è avvenuta su **autorizzazione esplicita dell'utente (strada B)**, accettando che alcune funzioni non siano migrate (§6). Il PASS riguarda l'esecuzione di F8 così come autorizzata, **non** la parità funzionale della Web UI.

## 1. Specifica originale

`docs/technical_reports/WEB_UI_CONSOLIDATION_AUDIT_2026-11-14.md`:

- **§8, F8:** "Spostamento (non cancellazione) in `legacy/` di Tkinter, Streamlit, Panda3D, viewer Plotly/trimesh, patch-script; ri-esecuzione test". Rischio basso, "dopo verifica F4".
- **§5:**

| Componente | Condizione | Stato della condizione |
|---|---|---|
| `main.py` (Tkinter) | Parità funzionale §3.1 | **Non soddisfatta** (F4 = PARTIAL). Archiviato per autorizzazione esplicita |
| `app.py` (Streamlit) | Decisione D2 + profilo orizzonte | Orizzonte integrato (F4); **D2 aperta**. Archiviato per autorizzazione esplicita |
| `src/lunar_mission_3d.py` (Panda3D) | Esposizione di `rank_operational_windows` | **Non soddisfatta**. Archiviato per autorizzazione esplicita |
| `src/lunar_3d_app.py`, `src/lunar_globe_3d.py`, `src/lunar_native_viewer.py`, `ui/` | Nessun import da moduli attivi | Soddisfatta |
| `test_*_models.py`, `rebuild_lunar_ui.py`, `correggi_lunar_visual.py`, `install_*.py` | Nessun import | Soddisfatta |

## 2. Componenti archiviati

| Componente | Percorso originale | Destinazione | SHA-256 (identico prima e dopo) |
|---|---|---|---|
| **Tkinter** | `main.py` | `legacy/tkinter/main.py` | `245ac2ed846338c6b6bf1231cf8cf6aeeb29dc3ed7f47b436c29ba8592f52265` |
| **Viewer trimesh** | `src/lunar_native_viewer.py` | `legacy/tkinter/lunar_native_viewer.py` (accanto a `main.py`, che lo lancia) | `351e48176cf6bbee2fca2579a45a4e1eaea9e6785e30baa2e47a3a151f862727` |
| **Streamlit** | `app.py` | `legacy/streamlit/app.py` | `cf033037f8a780f9bb55a9af9acac0aa3e5f0c40867c90aaee379e777f06cb8e` |
| **Panda3D** | `src/lunar_mission_3d.py` | `legacy/panda3d/lunar_mission_3d.py` | `4400b9018ff36c3c6b1e06e4c169c415152383d442894dca04b1c9a37cb09dc2` |
| Viewer Plotly | `src/lunar_3d_app.py`, `src/lunar_globe_3d.py` | `legacy/viewers/` | in `backups/f8_legacy_20261115-003023/SHA256SUMS` |
| Risorse Plotly | `ui/` | `legacy/ui/` | idem |
| Script di prova Panda3D | `test_astronaut_fixed.py`, `test_fixed_models.py`, `test_nasa_models.py` | `legacy/panda3d_model_checks/` | idem |
| Patch-script | `rebuild_lunar_ui.py`, `correggi_lunar_visual.py`, `install_guided_home.py`, `install_lunar_explorer.py`, `install_profile_selector.py` | `legacy/patch_scripts/` | idem |

Prima dello spostamento ho verificato che i quattro file fossero davvero gli entrypoint indicati dall'audit:

- `main.py`: `tk.Tk()` e `__main__`;
- `app.py`: `st.set_page_config`;
- `src/lunar_mission_3d.py`: `class LunarMission3D(ShowBase)` e `__main__`;
- `src/lunar_native_viewer.py`: `trimesh.load` e `__main__`.

Spostamento fatto con `mv -n`, senza `git mv` e senza staging. I file sono stati rimossi dalla posizione originale, quindi non esistono duplicati attivi. Le sottocartelle di destinazione non esistevano e nessun file è stato sovrascritto.

## 3. Backup e verifica

| Backup | Contenuto | Verifica |
|---|---|---|
| `backups/f8_legacy_20261115-003023/` | `f8_pre_move.tar` (14 file: viewer Plotly, `ui/`, script, `README.md`, `requirements-legacy.txt`) + `SHA256SUMS` | Estrazione + `sha256sum -c`: 14/14 OK; dopo lo spostamento 14/14 identici |
| `backups/f8b_legacy_20261115-003555/` | `f8b_pre_move.tar`: i 4 componenti più `README.md`, `legacy/README.md`, `requirements-legacy.txt` e la prima versione di questo report (8 file) + `SHA256SUMS` | Estrazione + `sha256sum -c`: 8/8 OK; dopo lo spostamento i 4 componenti risultano identici (4/4 OK) |

## 4. Dipendenze analizzate

Ho cercato import, percorsi e invocazioni dei quattro componenti in `src/`, `tests/`, `scripts/`, README, requirements, `pytest.ini` e configurazioni.

| Riferimento | Provenienza | Tipo | Esito |
|---|---|---|---|
| `main.py:1139` → `src/lunar_native_viewer.py` (subprocess) | Legacy → legacy | Invocazione | Interna ai componenti archiviati, non tocca la Web UI. Spostati insieme in `legacy/tkinter/`; non ho modificato il percorso nel codice (§7) |
| `legacy/patch_scripts/*` → `src/lunar_mission_3d.py` | Legacy → legacy | Patch su file | Script archiviati. Ora non trovano più il bersaglio: un ulteriore motivo per non eseguirli |
| `src/ui_web/science_api.py:263` "usata da main.py" | Web UI | **Solo commento** | Nessuna dipendenza |
| `README.md`, `requirements-legacy.txt` | Documentazione | Testo | Aggiornati |
| Import `src.lunar_mission_3d` / `src.lunar_native_viewer` / `main` / `app` da `src/`, `tests/`, `scripts/` | — | — | **Nessuno** |
| Moduli scientifici usati dai componenti archiviati (`astronomy`, `mission_planning`, `mission_planner`, `site_assessment`, `site_comparison`, `data_quality`, `rover_planning`, `mission_report`, `psystem_adapter`, `terrain_horizon`, …) | Dipendenze legacy → scienza | Import | **Restano in `src/`, invariati.** Nessun modulo scientifico dipende dagli entrypoint archiviati |

Non ho trovato nessun conflitto critico, quindi nessun componente è stato lasciato indietro.

## 5. Modifiche complessive di F8

- **Spostati:** i 16 file della tabella §2 (in tutto 18 file, contando i 2 di `ui/`).
- **Modificati (solo documentazione):**
  - `README.md`: sezione "Interfacce legacy (archiviate)" e due riferimenti a `main.py` e Streamlit;
  - `requirements-legacy.txt`: solo i percorsi nei commenti; pacchetti e versioni invariati;
  - `legacy/README.md`: inventario, funzioni non migrate, avvertenze, ripristino;
  - questo report.
- **Eliminati:** nessun file.
- **Non toccati:** algoritmi, moduli scientifici, `data/`, DEM, raster, kernel SPICE, `de421.bsp`, `mission_config.example.json`, risultati, F4–F7.

## 6. Funzionalità non migrate (non disponibili nella Web UI)

| Funzione | Componente archiviato | Stato |
|---|---|---|
| Scoring del sito con DEM + effemeridi | Tkinter | Modulo in `src/`, nessun endpoint |
| Diagnostica di illuminazione diretta | Tkinter | Solo tramite configurazione del Mission Engine |
| Multi-rover e journal P-System | Tkinter | Solo tramite configurazione del Mission Engine |
| Viewer nativo GLB (trimesh) | Tkinter | Non migrato (la Web UI ha il globo three.js) |
| Effemeridi offline Skyfield/SPICE | Streamlit | Non migrate; D2 aperta. La Web UI richiede la rete per le effemeridi |
| Ranking finestre scienza/ingegneria (`rank_operational_windows`) | Panda3D | Modulo in `src/`, nessun endpoint |
| Scena 3D Panda3D | Panda3D | Non migrata |

Queste funzioni sono indicate come **non disponibili** sia nel README (sezioni "Interfacce legacy" e "Limitazioni note") sia in `legacy/README.md`.

## 7. Verifiche

| Verifica | Risultato |
|---|---|
| Import di 20 moduli: Web UI (`app`, `science_api`, `mission_runner`), orchestratore e moduli scientifici, compresi quelli usati solo dal legacy (`mission_planner`, `site_assessment`, `illumination_analysis`, `multi_rover`, `terrain_horizon`, …) | OK |
| Sintassi dei 4 componenti archiviati | OK |
| Avvio della Web UI (`python src/ui_web/app.py --no-browser`) **da `/tmp`** | OK |
| GET di 11 risorse: `/`, `main.js`, `mission.js`, `science.js`, three.js, GLB, `/api/sites`, `/api/mission/configs`, `/api/mission/reports`, `/api/science/rasters`, `/api/terrain/lroc-quality` | Tutte 200 |
| Science Tools: `dem-audit`, `terrain`, `horizon`, `rover-plan` | 200 `ok`, con provenienza dal modulo originale |
| Link budget e simulazione termica | 200 `ok` con parametri validi. Con body incompleti rispondono 400 e l'elenco dei parametri mancanti: è la validazione prevista |
| Mission Engine: `validate` + `run` della configurazione di esempio, poi polling | `valid: true` → `state: completed`, `engine_status: completed_preliminary` |
| Riferimenti attivi ai vecchi entrypoint (`src/lunar_mission_3d`, `src/lunar_native_viewer`, `python main.py`, `streamlit run app.py`) in codice, test, README e requirements | Nessuno |
| Suite completa `python -m pytest -q` | **410 passed**, 7262 warning (le stesse deprecazioni di prima) |
| Checksum dei file archiviati rispetto agli originali | 4/4 + 14/14 identici |

## 8. Limitazioni e rischi residui

1. **Funzioni non migrate** (§6). Chi usava Tkinter, Streamlit o Panda3D per quelle funzioni non le trova nella Web UI. Restano recuperabili con il ripristino descritto in `legacy/README.md`.
2. **I componenti archiviati non sono eseguibili dalla nuova posizione.** Importano `src.*` o calcolano la radice dalla propria posizione; ad esempio `main.py` cerca `<sua cartella>/src/lunar_native_viewer.py`. Non li ho adattati per conservarli intatti e per non modificare codice fuori dallo scope.
3. **Git vede gli spostamenti come eliminazioni** più la cartella `legacy/` non tracciata. Al commit vanno aggiunti esplicitamente `legacy/` e le eliminazioni corrispondenti; git riconoscerà i rename perché il contenuto è identico.
4. **Restano in `src/` 41 backup storici** di `lunar_mission_3d.py` (`.backup-*`, `.bak-*`, `.before-*`), insieme agli altri file `*.before-*`. L'audit li mette nella pulizia generale (§5), non in F8, e non li ho toccati. Non sono importabili come moduli.
5. **Altra pulizia dell'audit non eseguita:** file spuri `json`, `sys`, `np`, `rasterio` in radice; archivi `.tar.gz`; `SCIENCE_STATUS.txt` obsoleto.
6. **`data/models/nasa/`** è ora usato solo da componenti archiviati. L'ho lasciato in `data/` per non toccare i dati.
7. **Effetto collaterale della verifica:** l'esecuzione di prova del Mission Engine ha creato una cartella in `reports/web_runs/` (`5992a4d7…`). La cartella è ignorata da git e non l'ho cancellata.
