# Lunar South Pole Planner

> Versione italiana del README precedente (salvata il 2026-11-15). Il README principale, in inglese, è [`../README.md`](../README.md).

Strumento di analisi preliminare per siti e operazioni al polo sud lunare.
Combina dati di terreno LOLA/LROC, effemeridi NASA/JPL Horizons e moduli locali
(terreno, orizzonte, percorso rover, comunicazioni, termica). La Web UI ufficiale
gira in locale.

La piattaforma è **pubblica**: homepage, profili Pubblico ed Educatore, globo lunare
(`/`) e le API che usano (`/api/health`, `/api/sites`, `/api/ephemerides`,
`/api/services`) non richiedono account.

Solo la sezione riservata **Pianificatori di missione** (dashboard MISSION PLANNERS,
`/dashboard`) richiede il login, con un unico sistema di autenticazione. Protegge
**Lunar Mission Control Planner** (`/mission-control`) e le API dei pianificatori
(`/api/mission/*`, `/api/science/*`, `/api/communications/*`, `/api/thermal/*`,
`/api/terrain/*`). Nella homepage il profilo **Pianificatore di missione** porta a `/dashboard`.

Architettura, autenticazione e gestione degli errori sono descritte in
[`docs/MISSION_PLANNERS.md`](MISSION_PLANNERS.md).

> I risultati sono **diagnostiche preliminari**, non certificate per la pianificazione
> operativa. Ogni risposta della Web UI indica il modulo e il raster da cui proviene.

## Avvio rapido

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./start.sh
```

`start.sh` svolge queste operazioni:

1. controlla il venv e le dipendenze;
2. se non esiste ancora un utente, lo segnala: il primo account si crea solo dalla pagina di accesso ai Pianificatori di missione (non ci sono credenziali predefinite);
3. avvia la piattaforma.

Il browser si apre sulla piattaforma pubblica `http://127.0.0.1:8765/`. La sezione
riservata è `http://127.0.0.1:8765/dashboard`. Per terminare: `Ctrl+C`.

> **Il server deve restare in esecuzione.** Se il processo Python termina, ad
> esempio perché il terminale viene chiuso, una scheda del browser già aperta o
> ripristinata mostra "Server: non raggiungibile" e "Effemeridi: backend non
> raggiungibile". La scheda riprende da sola quando il server viene riavviato.
>
> Prima della correzione del 2026-11-15, l'HTML era servito con `no-cache`. Una
> scheda ripristinata dalla cache poteva quindi mostrare il globo 3D, servito
> dalla cache, insieme a un generico `NetworkError` sulle effemeridi.

### Utenti

Al primo avvio non esiste alcun account: la pagina MISSION PLANNERS mostra il
modulo **Crea account amministratore** (nome utente, password di almeno 12
caratteri, conferma). Il modulo compare solo finché l'archivio utenti è vuoto;
dopo resta soltanto il normale login. `./start.sh` non chiede nulla nel terminale.

Gestione successiva da terminale:

```bash
python src/ui_web/auth_admin.py add-user <nome>   # utenti aggiuntivi; password chiesta senza eco
python src/ui_web/auth_admin.py passwd <nome>
python src/ui_web/auth_admin.py remove-user <nome>
```

Gli utenti e le sessioni sono salvati fuori dal repository, in
`~/.config/lunar-mission-control/` oppure in `$LUNAR_AUTH_DIR`. Le password sono
conservate solo come hash scrypt. I dettagli sono in
[`docs/MISSION_PLANNERS.md`](MISSION_PLANNERS.md#autenticazione).

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

Comando consigliato: `./start.sh`. Il comando diretto equivalente è:

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
| — | `LUNAR_AUTH_DIR` | Directory di utenti e sessioni (predefinita `~/.config/lunar-mission-control`) |
| — | `LUNAR_SESSION_IDLE_MINUTES`, `LUNAR_SESSION_MAX_HOURS` | Scadenza per inattività (30 min) e scadenza assoluta (12 h) |
| — | `LUNAR_COOKIE_SECURE=1` | Cookie `Secure`, da usare dietro un reverse proxy HTTPS |

Esempi:

```bash
python src/ui_web/app.py --port 9000 --no-browser
python src/ui_web/app.py --desktop
```

- **Porta occupata.** Il server stampa un messaggio con la porta alternativa da usare ed esce con codice 2.
- **`--desktop` senza PySide6.** L'app indica l'URL da aprire nel browser ed esce con codice 3.
- **`--host` diverso da loopback** (ad esempio `0.0.0.0`). La piattaforma diventa raggiungibile dalla rete. Il login resta attivo, ma il traffico è HTTP in chiaro: all'avvio compare un avviso. Usare una rete fidata o un reverse proxy HTTPS.

## Interfaccia

La homepage `/` è pubblica. Il collegamento **Mission Planners →** nella barra
superiore apre la sezione riservata: la pagina di login se non si è autenticati,
altrimenti la **dashboard** (`/dashboard`). Contiene:

- la sezione **MISSION PLANNERS**, da cui si apre Lunar Mission Control Planner (`/mission-control`);
- lo **stato dei servizi**: backend, NASA/JPL Horizons e sessione.

Il comando **Esci** (visibile solo con una sessione attiva) chiude la sessione e
riporta alla piattaforma pubblica `/`.

La homepage propone tre profili: **Pubblico**, **Educatore** (entrambi liberi) e **Pianificatore di missione**,
che apre la sezione riservata `/dashboard`. Lunar Mission Control Planner (`/mission-control`, con login) contiene gli strumenti operativi:

- **Globo 3D** (three.js) con i siti candidati di `src/astronomy.py` (`SITES`).
- **Effemeridi e finestre operative.** Elevazione di Sole e Terra da JPL Horizons e finestre di visibilità (`/api/ephemerides`). Gli errori sono classificati e mostrati separatamente:
  - backend non raggiungibile;
  - JPL non disponibile (timeout, DNS/rete, HTTP);
  - risposta astronomica non valida;
  - parametri non validi.

  Quando il servizio torna disponibile, la richiesta viene ripetuta da sola. Nessun dato dimostrativo viene mai mostrato.
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

### Sezione Educatori (pubblica)

Il profilo **Educatore** della homepage apre un percorso didattico libero, senza login né
registrazione, per insegnanti, divulgatori e studenti. È organizzato in 7 capitoli:

1. Perché esistono gli educatori di missione
2. Perché esplorare il polo sud lunare (con il grado di certezza di ogni affermazione:
   *Confermato*, *Da verificare*, *Obiettivo di programma*)
3. Le sfide di una missione lunare (luce e ombre, temperature, terreno, regioni in ombra
   permanente, energia, comunicazioni, navigazione, sicurezza, pianificazione)
4. Laboratori interattivi
5. Percorsi formativi (scuole secondarie, istituti tecnici e professionali, università,
   laboratori STEM, associazioni scientifiche, insegnanti e divulgatori)
6. Attività pratiche con obiettivi, esercitazioni, lavoro di gruppo e rubrica di valutazione
7. Cooperazione internazionale e futuro

Tre livelli di approfondimento (Base, Intermedio, Avanzato) mostrano o nascondono i
contenuti più tecnici. Attività e schede si possono stampare.

I laboratori **riusano il motore della piattaforma** e solo API pubbliche: `/api/sites` e
`/api/ephemerides` (NASA/JPL Horizons) per confrontare i siti, più l'Esploratore pubblico,
che il pulsante «Apri nel 3D» precompila e avvia. La sezione non chiama le API dei
Pianificatori e non salva dati personali: capitolo e livello restano nel `localStorage`
del browser. I risultati dei laboratori sono geometrici e non considerano le ombre dei rilievi.

Dettagli: [`docs/EDUCATORS.md`](EDUCATORS.md).

### Mission Engine da riga di comando

L'orchestratore usato dalla Web UI si può lanciare anche direttamente:

```bash
python -m src.mission_orchestrator mission_config.example.json
```

Il report viene scritto in `reports/mission/`, che a ogni esecuzione viene sovrascritta.

### Solar Energy Engine

La sezione `solar_energy` della configurazione è opzionale. Se è abilitata, il
motore stima:

- la produzione fotovoltaica;
- i consumi per categoria;
- lo stato di carica della batteria;
- i deficit.

Usa i report di astronomy, illumination e, se presente, rover_energy. Il
risultato alimenta il Mission Decision Engine, che separa le finestre
geometriche da quelle energeticamente sostenibili, e la Web UI.

I parametri hardware non hanno valori predefiniti. Se mancano, il report è
dichiarato parziale. Il modello è preliminare e non validato. I dettagli sono
in `docs/solar_energy_engine.md`.

## Integrazione con P-System

Il planner pubblica i propri risultati come *mission record* certificati da un comitato P-System
(`src/psystem_adapter.py`, `PSystemBridge`). Ogni nodo di missione ha la propria identità Ed25519;
ogni record ha entità, versione, digest del contenuto e dipendenze causali (`parents`). Il ponte
li registra in un outbox durevole, li invia ai nodi, verifica i certificati con il light client di
P-System e costruisce una vista riconciliata con la provenienza.

```bash
python -m src.psystem_cluster --dir reports/psystem_local   # 4 nodi P-System locali (Ctrl+C per fermarli)
```

Inserire gli URL e il `genesis_path` stampati nella sezione `psystem` di
`mission_config.example.json` e impostare `"enabled": true`: lo step `psystem_sync`
dell'orchestratore pubblica la corsa e il report mostra la sezione `psystem_integration`.
Richiede P-System in `~/Github P-system` (o `PSYSTEM_HOME`) con il suo `.venv` e `cryptography`
nel venv del planner. Il documento `REPORT_INTEGRAZIONE.md` citato in precedenza non è presente in questo repository.

## Effemeridi locali, finestre di luce e contatto, flotta

- `src/local_ephemeris.py`: Sole e Terra visti da un sito lunare, offline (Skyfield + kernel SPICE inclusi);
  `astronomy.source = "local"` nell'orchestratore. Confronto con Horizons:
  `python -m src.ephemeris_validation --start 2026-11-15T00:00`.
- `src/contact_windows.py`: finestre di illuminazione e di contatto con la Terra da orizzonte DEM,
  offset del CRS, effemeridi e bilancio di collegamento.
- `src/terrain_cross_validation.py`: confronto di orizzonte e illuminazione tra LOLA e LROC NAC.
- `src/multi_rover.py`, `plan_fleet_on_dem`: percorsi A* per più rover, budget energetico,
  sovrapposizioni, contatto con la Terra alla destinazione (step `multi_rover_dem`).

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
start.sh                       Avvio unico (controlli + primo utente + server)
src/ui_web/app.py              Server HTTP e punto di ingresso ufficiale
src/ui_web/auth.py             Unico login: hash scrypt, sessioni, limiti tentativi
src/ui_web/auth_admin.py       Gestione utenti da terminale
src/ui_web/login.html, dashboard.html, dashboard.js, session.js   Login, dashboard, sessione
docs/MISSION_PLANNERS.md       Sezione Pianificatori di missione e autenticazione
docs/EDUCATORS.md              Sezione Educatori (pubblica)
src/ui_web/mission_runner.py   Esecuzione del Mission Engine in sottoprocesso
src/ui_web/science_api.py      Endpoint sottili sui moduli scientifici
src/ui_web/index.html, main.js, mission.js, science.js   Frontend
src/ui_web/ui/educator.css, educator.js   Sezione Educatori (stili e laboratori)
src/ui_web/vendor/three/       Three.js incluso nel repository
src/paths.py                   Radice del progetto (indipendenza dalla cwd)
src/mission_orchestrator.py    Motore di missione (anche CLI)
src/astronomy.py               JPL Horizons e siti candidati
src/solar_energy_engine.py     Produzione solare e bilancio energetico (preliminare)
src/mission_decision_engine.py Aggregazione decisionale e finestre di missione
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
- **Autenticazione senza TLS proprio.** Il server parla solo HTTP. Fuori da `127.0.0.1` va usato un reverse proxy HTTPS con `LUNAR_COOKIE_SECURE=1`.
- **Test.** La suite esistente crea il server senza autenticazione (`create_server(..., auth=None)`). Login e nuova gestione degli errori non hanno ancora test automatici. I test che avviano `app.py` come processo, come `test_subprocess_launch_from_foreign_cwd`, si aspettano `GET /` = 200 senza login, come previsto (il login riguarda solo `/dashboard`, `/mission-control` e le API dei pianificatori). Dopo queste modifiche la suite non è stata eseguita.

I dettagli sono in `reports/web_ui_consolidation/F0…F7_*.md` e in
`docs/technical_reports/WEB_UI_CONSOLIDATION_AUDIT_2026-11-14.md`.
