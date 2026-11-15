# F6 — Dipendenze e installazione

Data: 2026-11-15 · Inizio 00:20:11 · Fine ≈ 00:25 · **Tempo impiegato ≈ 5 minuti** (limite 30)
Specifica: `docs/technical_reports/WEB_UI_CONSOLIDATION_AUDIT_2026-11-14.md`, §4 e §8 (F6):
"`requirements.txt` (Web UI + scienza) e `requirements-legacy.txt`; verifica `pip install` in venv pulito".
Comando ufficiale (invariato): `python src/ui_web/app.py`.

## 1. Obiettivi

| Obiettivo | Stato |
|---|---|
| `requirements.txt` ridotto alle dipendenze di Web UI + scienza | Fatto |
| `requirements-legacy.txt` per le interfacce legacy | Fatto |
| Dipendenze desktop (PySide6) separate e opzionali (decisione D1 già applicata in F0) | Fatto: `requirements-desktop.txt` |
| Dipendenze di test separate | Fatto: `requirements-dev.txt` |
| Verifica `pip install` in venv pulito | Fatto, nessun conflitto (`pip check`) |
| Nessuna dipendenza superflua o duplicata | Fatto (vedi §3) |
| Comando ufficiale invariato | Verificato |

## 2. File

| File | Azione |
|---|---|
| `requirements.txt` | Riscritto. Prima era un `pip freeze` di 63 pacchetti, PySide6 incluso. Ora contiene 5 dipendenze dirette con versione fissata e le istruzioni d'uso. |
| `requirements-dev.txt` | Nuovo |
| `requirements-desktop.txt` | Nuovo |
| `requirements-legacy.txt` | Nuovo |
| `reports/web_ui_consolidation/F6_DEPENDENCIES_INSTALLATION.md` | Nuovo (questo report) |

Backup: `backups/f6_dependencies_20261115-002050/requirements.txt`
(SHA-256 `bab9d50ed8c1b0ffe526a98bfb1fc49f6bc1d6878acf92b98174c52cae647385`, identico all'originale).

Non sono stati modificati codice Python o JS, dati, DEM, raster, kernel SPICE, README, F4 o F5.

## 3. Dipendenze

Le dipendenze sono state ricavate con una scansione AST transitiva degli import a partire da
`src/ui_web/app.py`: 32 moduli locali. A questa si aggiunge un grep degli import in `src/`, `tests/`, `scripts/` e nella radice.

### Obbligatorie: Web UI e scienza (`requirements.txt`)

| Pacchetto | Usato da |
|---|---|
| `requests==2.34.2` | `src/astronomy.py` (JPL Horizons) |
| `numpy==2.5.4` | moduli scientifici, `science_api.py` |
| `rasterio==1.5.2` | raster LOLA/LROC (installa `affine`, `attrs`, `click`, `certifi`…) |
| `pyproj==3.8.0` | `src/lunar_geometry.py` |
| `matplotlib==3.11.2` | `src/mission_orchestrator.py` |

Three.js è vendorizzato e tracciato da git in `src/ui_web/vendor/three/`, quindi **npm non è richiesto**.
Il problema "clone pulito senza three.js" segnalato in audit §3 è già risolto.

### Opzionali

| File | Contenuto | Scopo |
|---|---|---|
| `requirements-dev.txt` | `pytest==9.1.1`, `skyfield==1.55` | test (`skyfield` serve alla verifica offline DE421 in `test_astronomical_orientation.py`) |
| `requirements-desktop.txt` | `PySide6==6.12.0` (~670 MB) | solo per `--desktop` |
| `requirements-legacy.txt` | `streamlit`, `pandas`, `plotly`, `skyfield`, `Panda3D`, `panda3d-gltf`, `trimesh`, `pyglet<2` (1.5.31) | Streamlit `app.py`, viewer Plotly/Panda3D/trimesh |

### Rimosse perché non usate o ridondanti

- Nessun import nel codice: `starlette`, `uvicorn`, `anyio`, `websockets`, `python-multipart`, `itsdangerous`, `spiceypy` e `panda3d-simplepbr`.
- Transitive, ora risolte da pip: `altair`, `pydeck`, `pyarrow`, `watchdog`, `protobuf`, `jplephem`, `sgp4`, `affine`, `MarkupSafe`, `Jinja2` e simili.
- Sotto-pacchetti `PySide6_*` e `shiboken6`: li installa il meta-pacchetto `PySide6`.

## 4. Installazione e avvio verificati

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt          # Web UI (browser)
pip install -r requirements-dev.txt      # + test
pip install -r requirements-desktop.txt  # opzionale: finestra Qt
python src/ui_web/app.py                 # comando ufficiale
```

La verifica è stata fatta in un venv temporaneo fuori dal progetto (scratchpad, Python 3.14.8).
Il `.venv` principale non è stato toccato.

| Verifica | Risultato |
|---|---|
| `pip install -r requirements-dev.txt` | OK |
| `pip check` | "No broken requirements found." |
| PySide6, Streamlit, Panda3D, Plotly e trimesh presenti nel venv | 0 (nessuno installato) |
| Import di `app`, `mission_orchestrator`, `science_api`, `mission_runner` | OK, PySide6 non caricato |
| `python src/ui_web/app.py --no-browser --port 8799` | Server attivo. `/`, `/main.js` e `/vendor/three/build/three.module.js` rispondono 200 |
| `--desktop` senza PySide6 | Messaggio chiaro con l'URL per il browser, exit code 3 (come da F0) |

## 5. Test

Tutti eseguiti nel venv pulito.

- Test mirati: Web UI (app, F3, F5, mission, science), cwd independence, lunar_geometry, astronomical_orientation → **229 passed**.
- Suite completa `tests/` → **410 passed**, 7262 warning. I warning sono deprecazioni, tra cui `skyfield` con NumPy 2.5. Nessun fallimento.

Nota: la suite completa è durata circa 65 s, quindi l'ho eseguita entro il tempo disponibile.

## 6. Problemi aperti

1. **Versioni fissate solo per le dipendenze dirette.** Le transitive le risolve pip al momento dell'installazione. Se serve una riproducibilità bit-per-bit si può aggiungere un lock file (`pip freeze > requirements-lock.txt` oppure `pip-tools`). Non l'ho fatto perché è fuori dalla specifica F6.
2. **Solo Python 3.14 verificato.** Non ho provato altre versioni di Python. Non c'è un `pyproject.toml` con `requires-python`.
3. **`requirements-desktop.txt` e `requirements-legacy.txt` non installati nel venv di prova.** Le versioni sono quelle già presenti nel `.venv` principale, dove funzionano. `--desktop` con display reale non è verificato (stessa limitazione di F0).
4. **README non aggiornato.** Le istruzioni d'installazione sono nell'intestazione di `requirements.txt` e in questo report. Il README unico spetta a F7.
5. **`src/ui_web/package.json` e `node_modules/` sono ancora presenti.** Servono solo per aggiornare il vendoring di three.js. Non li ho toccati.
6. **Il `.venv` principale contiene ancora tutti i pacchetti del vecchio freeze.** È innocuo e non l'ho modificato.

## 7. Verdetto

**PASS.** Gli obiettivi F6 sono raggiunti: dipendenze minime per il browser, desktop e legacy separati e opzionali, installazione verificata in un venv pulito, suite completa verde e comando ufficiale invariato.
