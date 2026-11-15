# Lunar South Pole Planner

Strumento di analisi preliminare per siti e operazioni al polo sud lunare.
Combina dati di terreno LOLA/LROC, effemeridi NASA/JPL Horizons e moduli locali
(terreno, orizzonte, percorso rover, comunicazioni, termica). La Web UI ufficiale
gira in locale.

> I risultati sono **diagnostiche preliminari**, non certificate per la pianificazione
> operativa. Ogni risposta della Web UI indica il modulo e il raster da cui proviene.

## Avvio rapido

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python src/ui_web/app.py
```

Il server parte su `http://127.0.0.1:8765/` e il browser di sistema si apre da solo.
Per terminare: `Ctrl+C`.

## Requisiti

- **Python 3.14.** È l'unica versione verificata (3.14.8). Altre versioni non sono state provate.
- Un browser moderno con supporto WebGL per il globo 3D.
- Rete per le effemeridi (JPL Horizons): vedi [Funzionamento offline](#funzionamento-offline).
- **npm non serve.** Three.js è già incluso in `src/ui_web/vendor/three/`.

## Installazione delle dipendenze

| File | Contenuto | Quando serve |
|---|---|---|
| `requirements.txt` | `requests`, `numpy`, `rasterio`, `pyproj`, `matplotlib` | Sempre: Web UI e moduli scientifici |
| `requirements-dev.txt` | `requirements.txt` + `pytest`, `skyfield` | Per eseguire i test |
| `requirements-desktop.txt` | `requirements.txt` + `PySide6` (~670 MB) | Solo per la modalità `--desktop` |
| `requirements-legacy.txt` | `requirements.txt` + Streamlit, Plotly, Panda3D, trimesh… | Solo per le interfacce legacy |

```bash
pip install -r requirements.txt          # uso da browser
pip install -r requirements-dev.txt      # sviluppo e test
pip install -r requirements-desktop.txt  # opzionale: finestra Qt
```

Le dipendenze dirette hanno versione fissata. Le dipendenze indirette le risolve pip.

## Avvio della Web UI

Comando ufficiale:

```bash
python src/ui_web/app.py
```

Funziona da qualsiasi directory corrente: i percorsi sono risolti rispetto alla radice del progetto.

| Opzione | Variabile d'ambiente | Effetto |
|---|---|---|
| `--host HOST` | `LUNAR_UI_HOST` | Indirizzo di ascolto (predefinito `127.0.0.1`) |
| `--port PORT` | `LUNAR_UI_PORT` | Porta TCP (predefinita `8765`) |
| `--no-browser` | `LUNAR_UI_NO_BROWSER=1` | Avvia solo il server, senza aprire il browser |
| `--desktop` | — | Apre la UI in una finestra PySide6 (opzionale) |

Esempi:

```bash
python src/ui_web/app.py --port 9000 --no-browser
python src/ui_web/app.py --desktop
```

- **Porta occupata.** Il server stampa un messaggio con la porta alternativa da usare ed esce con codice 2.
- **`--desktop` senza PySide6.** L'app indica l'URL da aprire nel browser ed esce con codice 3.
- **`--host` diverso da loopback** (ad esempio `0.0.0.0`). La UI diventa raggiungibile dalla rete **senza autenticazione**: all'avvio compare un avviso.

## Interfaccia

La pagina iniziale propone tre profili: **Pubblico**, **Educatore** e **Pianificatore di missione**.
Il profilo Pianificatore di missione (Mission Control) contiene gli strumenti operativi:

- **Globo 3D** (three.js) con i siti candidati di `src/astronomy.py` (`SITES`).
- **Effemeridi e finestre operative.** Elevazione di Sole e Terra da JPL Horizons e finestre di visibilità (`/api/ephemerides`).
- **Comunicazioni.** Link budget (`/api/communications/link-budget`).
- **Termica.** Modello a nodo singolo (`/api/thermal/simulate`).
- **Qualità LROC.** Riepilogo dell'ultimo report `lroc-quality-mask-*.json` (`/api/terrain/lroc-quality`).
- **Mission Engine.** Valida ed esegue `mission_config.example.json` con l'orchestratore, mostra lo stato e consente di riaprire i report e scaricare gli artifact. Le esecuzioni vengono salvate in `reports/web_runs/<id>/` (cartella ignorata da git).
- **Science Tools.** Strumenti sui raster LOLA Site04 e LROC NAC SR12:

  | Strumento | Endpoint | Modulo |
  |---|---|---|
  | Audit DEM | `POST /api/science/dem-audit` | `data_quality` |
  | Pendenza e rugosità locali | `POST /api/science/terrain` | `terrain_metrics` |
  | Profilo d'orizzonte | `POST /api/science/horizon` | `horizon_analysis` |
  | Percorso rover A* e stima energetica | `POST /api/science/rover-plan` | `rover_planning`, `rover_energy` |
  | Confronto geometrico dei siti (Sole/Terra) | `POST /api/science/site-comparison` | `site_comparison` (richiede la rete) |

  Terreno, orizzonte e rover lavorano in **riga/colonna del DEM**, non in coordinate geografiche.
  La stima energetica parte solo se si forniscono **tutti** i parametri del rover.
  Possono girare al massimo 2 calcoli contemporaneamente; oltre il limite il server risponde 503.

### Mission Engine da riga di comando

L'orchestratore usato dalla Web UI si può lanciare anche direttamente:

```bash
python -m src.mission_orchestrator mission_config.example.json
```

Il report viene scritto in `reports/mission/`, che a ogni esecuzione viene sovrascritta.

## Dati

Inclusi nel repository:

| Percorso | Contenuto |
|---|---|
| `data/terrain/official-lola/` | DEM LOLA 5 m/px (Site01, Site04, Site06), densità `ldec` ed errore `toterr` di Site04 |
| `data/terrain/reference-lroc/` | DTM LROC NAC SR12, raster di confidenza e maschere di qualità |
| `data/terrain/kernels/` | Kernel SPICE lunari (`moon_080317.tf`, `pck00008.tpc`, `moon_pa_de421_1900-2050.bpc`) |
| `de421.bsp` | Effemeridi planetarie DE421 |
| `data/terrain/global/Moon_NASA_LRO_8k_Topo_Small.glb` | Modello del globo per la Web UI |
| `data/models/nasa/` | Modelli GLB (usati dai visualizzatori legacy) |

Il percorso dei raster usati dal Mission Engine è definito in `mission_config.example.json`.
Gli strumenti Science usano un catalogo fisso: il browser non può indicare percorsi.

### Funzionamento offline

- **Senza rete funzionano:** audit DEM, terreno, orizzonte, percorso rover, qualità LROC, comunicazioni e termica. Il Mission Engine con la configurazione di esempio usa solo raster locali: gli step `astronomy` e `illumination` sono disabilitati. Questo è verificato sulla configurazione, non con un'esecuzione senza rete.
- **Richiedono la rete (JPL Horizons):** effemeridi e finestre operative, confronto dei siti e step `astronomy` del Mission Engine, se viene abilitato.
- **Fallback offline per le effemeridi:** non è presente nella Web UI. Le effemeridi Skyfield/SPICE esistono solo nell'interfaccia Streamlit archiviata (`legacy/streamlit/app.py`).

## Struttura del progetto

```
src/ui_web/app.py              Server HTTP e punto di ingresso ufficiale
src/ui_web/mission_runner.py   Esecuzione del Mission Engine in sottoprocesso
src/ui_web/science_api.py      Endpoint sottili sui moduli scientifici
src/ui_web/index.html, main.js, mission.js, science.js   Frontend
src/ui_web/vendor/three/       Three.js incluso nel repository
src/paths.py                   Radice del progetto (indipendenza dalla cwd)
src/mission_orchestrator.py    Motore di missione (anche CLI)
src/astronomy.py               JPL Horizons e siti candidati
src/*.py                       Moduli scientifici (terreno, orizzonte, illuminazione,
                               rover, LOLA/LROC, comunicazioni, termica, ...)
tests/                         Suite pytest
docs/technical_reports/        Audit e report tecnici
docs/history/                  README storici (V3–V11, Tkinter)
legacy/                        Componenti legacy archiviati (F8)
reports/                       Output dei calcoli e report delle fasi
```

### Interfacce legacy (archiviate)

L'unica interfaccia ufficiale è `python src/ui_web/app.py`.
Tutte le interfacce precedenti sono archiviate in `legacy/` (fase F8). Sono conservate solo per consultazione e recupero e **non sono entrypoint ufficiali**:

- `legacy/tkinter/`: `main.py` (Tkinter) e `lunar_native_viewer.py` (viewer trimesh);
- `legacy/streamlit/`: `app.py` (Streamlit);
- `legacy/panda3d/`: `lunar_mission_3d.py` (Panda3D);
- `legacy/viewers/` e `legacy/ui/`: visualizzatori Plotly;
- `legacy/panda3d_model_checks/` e `legacy/patch_scripts/`: script storici. **I patch-script non vanno eseguiti.**

Alcune funzioni esistevano solo in queste interfacce e **non sono disponibili nella Web UI**:

- scoring del sito con DEM + effemeridi;
- effemeridi offline;
- ranking delle finestre scienza/ingegneria;
- scena Panda3D e viewer trimesh.

Elenco completo e istruzioni di ripristino in `legacy/README.md`.
Le dipendenze sono in `requirements-legacy.txt`.

## Test

```bash
pip install -r requirements-dev.txt
python -m pytest            # usa testpaths = tests (pytest.ini)
```

Ultima esecuzione completa in un venv pulito: **410 passed** (fase F6).
I test della Web UI sono in `tests/test_web_ui_*.py`.

## Limitazioni note

- **Funzionalità scientifiche non ancora nella Web UI** (fase F4 = PARTIAL):
  - scoring del sito DEM + effemeridi;
  - analisi locale per sito (LDEC/TOTERR);
  - diagnostica di illuminazione diretta;
  - ranking delle finestre scienza/ingegneria;
  - multi-rover e journal P-System.

  Le ultime due e l'illuminazione sono raggiungibili solo tramite una configurazione dell'orchestratore.
- **Globo 3D.** I risultati non vengono proiettati sul globo: il frame del GLB non è validato rispetto alla griglia del DEM. I risultati sono mostrati in grafici 2D.
- **Consolidamento architetturale incompleto** (fase F5 = PARTIAL):
  - l'export della missione avviene lato client;
  - la ricerca delle finestre è duplicata tra Web UI e orchestratore (più la copia in `legacy/tkinter/main.py`);
  - i nomi dei siti sono ancora scritti in `index.html`.
- **Mission Engine dalla Web UI:**
  - usa solo `mission_config.example.json`, in sola lettura;
  - `reports/web_runs/` cresce senza pulizia automatica;
  - i report della CLI (`reports/mission/`) non sono elencati.
- **Orizzonte lento.** Il calcolo richiede circa 6–9 s (5 km, passo 2°) e non si può annullare.
- **Percorsi assoluti.** I report contengono il percorso assoluto della macchina locale.
- **Modalità `--desktop`.** Non è stata verificata con un display reale.
- **Test di interfaccia.** Non ci sono test end-to-end con click simulati nel browser.
- **Nessuna autenticazione.** Usare `--host` diverso da `127.0.0.1` solo su reti fidate.

I dettagli sono in `reports/web_ui_consolidation/F0…F7_*.md` e in
`docs/technical_reports/WEB_UI_CONSOLIDATION_AUDIT_2026-11-14.md`.
