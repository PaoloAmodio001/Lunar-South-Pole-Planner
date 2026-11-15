# Audit di completezza del repository — Lunar South Pole Planner

**Data:** 2026-11-15
**Metodo:** analisi in sola lettura del disco e dell'indice Git, con `git ls-files`, `git ls-files -o --exclude-standard`, `git check-ignore`, `find` e lettura del codice.

Durante l'audit non ho modificato file del progetto e non ho eseguito `git add`, commit, push, test né avvio dell'applicazione. L'unico file creato è questo report.

> **Premessa.** I numeri e le classi A–F descrivono lo stato del disco **al momento dell'audit**, quando su GitHub c'era solo il commit `f056381`.
>
> **Aggiornamento (2026-11-15):** dopo l'audit l'autore ha autorizzato la pubblicazione. I file "nuovi" e "modificati" sono stati pubblicati con `ed112fe`; le due presentazioni della radice con `6a546c9`. Dettagli nella sezione [Registro della pubblicazione](#registro-della-pubblicazione).

---

## 1–5. Numeri

| Voce | Numero | Note |
|---|---:|---|
| **1. File locali totali** (esclusa `.git/`) | **22.596** | Di cui 35 link simbolici in `.venv/bin`. Escludendo `.venv/` e `backups/` restano 1.999 file. |
| **2. File già tracciati** (A) | **295** | Tutti presenti su disco: 0 cancellati localmente. |
| **3. Nuovi file candidati** (B) | **76** | Circa 17,8 MB, non ignorati. Vengono pubblicati con `git add -A`. |
| **4. File modificati** (C) | **24** | Sono un sottoinsieme dei 295 tracciati. |
| **5. File ignorati** (D) | **22.225** | Dettaglio nella tabella seguente. |

Controllo: 295 + 76 + 22.225 = 22.596 ✔

**Composizione dei file ignorati:**

| Categoria | File | Dimensione | Classe |
|---|---:|---:|---|
| `.venv/` (ambiente Python) | 18.373 | 1,6 GB | F, rigenerabile |
| `backups/` (backup locali) | 2.224 | 3,2 GB | F |
| `src/ui_web/node_modules/` | 1.264 | 23 MB | F, sostituito da `src/ui_web/vendor/three/` (tracciato) |
| Copie `*.bak*`, `*.before-*`, `*.backup-*` fuori da `backups/` | 147 | — | F |
| Cache (`__pycache__`, `.pytest_cache`) | 116 | — | F |
| `reports/web_runs/` (esecuzioni del Mission Engine dalla Web UI) | 65 | 4 MB | F, output per esecuzione |
| `video/` (lavoro in corso) | 32 | 27 MB | D, vedi §6 |
| Bozze di presentazione nella radice | 2 | 6,3 MB | D al momento dell'audit; **pubblicate dopo** (`6a546c9`) |
| `np`, `rasterio` nella radice (screenshot ImageMagick salvati per errore) | 2 | 12 MB | F |

### Distribuzione per area

| Cartella | Tracciati (A) | di cui modificati (C) | Nuovi (B) | Ignorati (D/F) |
|---|---:|---:|---:|---:|
| radice | 12 | 5 | 2 (`start.sh`, `REPOSITORY_UPDATE_REPORT.md`) | 6 |
| `src/` (moduli scientifici) | 34 | 6 | 7 | 185 (backup e cache) |
| `src/ui_web/` | 30 | 9 | 9 | 1.273 (node_modules e backup) |
| `data/` | 55 | 0 | 0 | 0 |
| `tests/` | 37 | 4 | 4 | 48 (cache) |
| `reports/` | 80 | 0 | 29 (`reports/validation/`) | 65 (`web_runs`) |
| `audit-reports/` | 11 | 0 | 0 | 0 |
| `docs/` | 13 | 0 | 4 | 0 |
| `legacy/` | 17 | 0 | 0 | 0 |
| `scripts/` | 6 | 0 | 0 | 6 (cache, 1 `.bak`) |
| `submission/` | 0 | 0 | 21 | 0 |
| `video/` | 0 | 0 | 0 | 32 |

Più `REPOSITORY_COMPLETENESS_AUDIT.md`: questo file, nuovo. Diventerebbe il 77° file nuovo.

**Classe E (non presente nel repository locale):** nessun file tracciato manca dal disco. Mancano solo componenti esterni al progetto, vedi §8–9.

---

## Inventario per componente

Legenda: **A** tracciato · **B** nuovo, pronto · **C** modificato · **D** escluso da `.gitignore` · **E** non presente in locale · **F** generato o non necessario.

### Moduli Python (`src/`, 41 moduli attivi)

| Stato | Moduli |
|---|---|
| **A** invariati (28) | `__init__`, `communications`, `confidence_validation`, `data_quality`, `descent_hazard_detection`, `export_descent_risk_raster`, `horizon_analysis`, `illumination_analysis`, `local_site_analysis`, `lola_local_quality`, `lola_lroc_quality`, `lroc_quality_mask`, `lunar_geometry`, `mission_analytics`, `mission_planner`, `mission_planning`, `paths`, `plot_rover_route`, `route_quality`, `rover_energy`, `rover_planning`, `site_assessment`, `site_comparison`, `site_selection`, `style_descent_risk_map`, `terrain_metrics`, `thermal_model`, `visibility` |
| **C** modificati (6) | `astronomy`, `mission_orchestrator`, `mission_report`, `multi_rover`, `psystem_adapter`, `terrain_horizon` |
| **B** nuovi (7) | `contact_windows`, `ephemeris_validation`, `local_ephemeris`, `mission_decision_engine`, `psystem_cluster`, `solar_energy_engine`, `terrain_cross_validation` |
| **F** esclusi (134) | Copie storiche `*.before-*`, `*.bak*`, `*.backup-*` (es. 41 copie di `lunar_mission_3d.py`, 70 di `mission_orchestrator`). La versione attiva di `lunar_mission_3d.py` è in `legacy/panda3d/` (**A**). |

**Import interni:** tutti gli `import src.*`, `tests.*` e `scripts.*` puntano a file tracciati o nuovi. Nessuno punta a un file ignorato. `src.ui_web` non ha `__init__.py` e funziona come *namespace package*; era così anche prima.

### Componenti per sottosistema

| Sottosistema | File principali | Stato |
|---|---|---|
| **Interfaccia web** | `app.py`, `science_api.py`, `index.html`, `main.js`, `mission.js`, `science.js`, `mission_runner.py`, `ui/*.css,js`, font Archivo, `vendor/three/` (r186) | A + C |
| **Autenticazione e portale** | `auth.py`, `auth_admin.py`, `login.html`, `dashboard.html/.js`, `session.js`, `ui/portal.css` | **B** |
| **Sezione Educatori** | `ui/educator.css`, `ui/educator.js` (contenuti in `index.html`) | **B** + C |
| **Interfaccia desktop** | Opzione `--desktop` (PySide6) in `app.py`, `requirements-desktop.txt` | A/C |
| **Interfacce desktop legacy** | `legacy/tkinter/`, `legacy/panda3d/`, `legacy/streamlit/`, `legacy/viewers/`, `legacy/ui/` | A (17 file) |
| **Mission Engine** | `mission_orchestrator`, `mission_report`, `mission_runner`, `mission_config.example.json` | C |
| **Motore decisionale ed energetico** | `mission_decision_engine`, `solar_energy_engine`, `rover_energy` | B + A |
| **DEM LOLA/LROC** | `data_quality`, `terrain_metrics`, `terrain_horizon`, `horizon_analysis`, `lola_*`, `lroc_quality_mask`, `confidence_validation`, `terrain_cross_validation` | A + C + B |
| **Effemeridi** | Horizons: `astronomy`. SPICE e Skyfield: `local_ephemeris`. Confronto: `ephemeris_validation`. Finestre: `contact_windows` | C + B |
| **Kernel SPICE** | `de421.bsp`, `data/terrain/kernels/` (3 kernel) | A |
| **Rover e flotta** | `rover_planning`, `rover_energy`, `route_quality`, `plot_rover_route`, `multi_rover` | A + C |
| **Science Tools** | `science_api.py`, `science.js` | A + C |
| **Visualizzazione 3D** | `main.js`, `ui/globe-markers.js`, `vendor/three/`, `data/terrain/global/Moon_NASA_LRO_8k_Topo_Small.glb` | A + C |
| **P-System** (sperimentale) | `psystem_adapter` (C), `psystem_cluster` (B), test (B) | Il software P-System è esterno, vedi §8 |
| **Script di installazione e avvio** | `start.sh` (B), `requirements*.txt` (C), `pytest.ini` (A) | — |
| **Script diagnostici** | `scripts/*.py` (5 analisi LOLA/LROC e orizzonte) | A |
| **Script QGIS** | `src/style_descent_risk_map.py`, che richiede la console QGIS | A |

**Asset web:** tutti i file serviti da `STATIC_ROUTES`, `/ui/` e `/vendor/three/` e tutti i riferimenti nell'HTML, nel JS e nel CSS sono tracciati (A) oppure nuovi (B): `educator.css`, `educator.js`, `portal.css`, `login.html`, `dashboard.*`, `session.js`. **Nessun asset referenziato è ignorato o mancante.** `three` arriva dall'*importmap* verso `/vendor/three/` e non da `node_modules`.

### Dataset, texture, immagini e modelli (`data/`: 55 file, tutti A, circa 727 MB)

| Risorsa | Stato | Usata da |
|---|---|---|
| DEM LOLA 5 m/px Site01, Site04, Site06 (+ LDEC, TOTERR, clone di errore Site04, README PGDA) | A | App, Mission Engine, figure della submission |
| DTM LROC NAC SR12 (+ CONF, LBL, README, IMG originale PDS3) | A | App, Mission Engine |
| Raster derivati (`processed/`, `shackleton_site04_*.tif`, PNG) | A | Mission Engine, report |
| Nuvole di punti `source/*.xyzi` | A | Non lette da `src/` |
| Globo NASA SVS `Moon_NASA_LRO_8k_Topo_Small.glb` (77,7 MB, texture inclusa nel GLB) | A | Web UI |
| Modelli NASA `data/models/nasa/*.glb` (LRO, Apollo LM, Astronaut, Gateway) | A | Solo viewer legacy |
| `lunar_texture_preview.png` e PNG di orizzonte | A | Report e documentazione |
| Kernel SPICE e `de421.bsp` | A | Effemeridi offline |

Nessun file in `data/` è ignorato o non tracciato. Il file più grande è di 77,7 MB, sotto il limite di 100 MB di GitHub.

### Test e report

| Elemento | Stato |
|---|---|
| `tests/`: 38 file di test, 309 funzioni `test_` | 34 A (4 C) + 3 B |
| `tests/data/` (risposte Horizons registrate) | 1 A + 1 B |
| `tests/js/globe_markers_geodesy.mjs` | A |
| Percorsi di dati citati nei test | Tutti tracciati o nuovi. Gli altri sono percorsi volutamente inesistenti (test negativi) o stringhe di sola risoluzione dei percorsi. |
| Benchmark | Non esiste una suite di benchmark separata. Ci sono i tempi dell'orizzonte nel README e le diagnostiche in `reports/`. |
| `reports/` (80 A) | Diagnostiche LOLA/LROC, orizzonte, missione, visualizzazione, `web_ui_consolidation/F0–F11` |
| `reports/validation/` (29 B) | Prove di validazione citate dal README e usate da `submission/tools/make_figures.py`. **Indispensabile.** |
| `audit-reports/` (11 A) | Audit LOLA/LROC del 2026-11-14 |
| `reports/web_runs/` (65 F) | Output per esecuzione. Correttamente escluso. |

### Documentazione

| File | Stato |
|---|---|
| `README.md` (inglese) | C |
| `docs/README_IT.md`, `docs/EDUCATORS.md`, `docs/MISSION_PLANNERS.md`, `docs/solar_energy_engine.md` | B |
| `docs/technical_reports/` (2), `docs/history/` (11), `legacy/README.md` | A |
| `REPOSITORY_UPDATE_REPORT.md`, `REPOSITORY_COMPLETENESS_AUDIT.md` | B |
| `SCIENCE_STATUS.txt` | A, contenuto superato (vedi §7) |

---

## 6. Esclusioni importanti: analisi e raccomandazione

| Risorsa esclusa | Contenuto | Serve per eseguire? | Serve per riprodurre i risultati? | Raccomandazione |
|---|---|---|---|---|
| **`video/`** (32 file, 27 MB) | 6 script Blender (`common.py`, `s01_opening.py`, `prep_data.py`, …), `bl.sh` con percorso `/home/paolo/...` scritto nel codice, heightmap `.npy` e PNG generati, 4 fotogrammi di anteprima, 7 font Lato/FiraCode, `earth_nasa_visible_earth.jpg` | No | Solo per il video, che è una bozza (solo la scena 1) | **Tenere escluso** finché il video non è finito. Per pubblicarlo servono tre cose: rimuovere il percorso assoluto da `bl.sh`, documentare la fonte dell'immagine della Terra (NASA Visible Earth, oggi non registrata) e pubblicare solo gli script, perché i dati si rigenerano con `prep_data.py`. Non è un problema di dimensioni. |
| **`LUNAR_P_SYSTEM_PRESENTATION.pdf`** (316 KB) | Documento tecnico "Lunar South Pole Planner & P-System" firmato dall'autore | No | No | **Pubblicato** su richiesta dell'autore (commit `6a546c9`), nella radice. Contiene il nome dell'autore. Non ho verificato che i dati citati siano coerenti con la submission. |
| **`P-System Space Group · with P-System technology (1).pptx`** (6,2 MB) | Bozza di presentazione; il "(1)" indica un download duplicato | No | No | **Pubblicato** su richiesta dell'autore (commit `6a546c9`) con il nome originale. La presentazione ufficiale resta `submission/…NASA_2026.pptx`. Rinominato dopo, senza il suffisso "(1)": `P-System Space Group · with P-System technology.pptx`. |
| `src/ui_web/node_modules/` (1.264 file) | three.js da npm | No: l'app usa `vendor/three/` (tracciato) | No | **Tenere escluso**. `package.json` è tracciato. |
| `.venv/` | Ambiente Python | Sì, ma si rigenera con `requirements*.txt` | — | **Tenere escluso**, già documentato. |
| `backups/` (3,2 GB), 147 copie `*.bak*`/`*.before-*` | Copie storiche, incluso il Site Explorer rimosso volontariamente | No | No | **Tenere escluso.** Il Site Explorer è stato rimosso su tua richiesta e non va ripubblicato. |
| `reports/web_runs/` | Output delle esecuzioni dalla Web UI | No | Si rigenerano | **Tenere escluso.** |
| `np`, `rasterio` (radice) | Screenshot salvati per errore da un comando `import` | No | No | **Tenere escluso.** |
| Regole `*.key`, `*.pem`, `reports/psystem_local/`, `*.db` | Oggi nessun file corrisponde | — | — | **Tenere**: proteggono le chiavi private create da `psystem_cluster`. |

**Altre categorie richieste:**

- **Modelli GLB:** tutti tracciati. **Texture NASA:** incluse nel GLB del globo e nel PNG di anteprima, tracciati. **DEM:** tutti tracciati.
- **Asset della presentazione** (`submission/assets/`, 8 file): nuovi (B), nessuno escluso.
- **Configurazione:** `mission_config.example.json` è C; `pytest.ini` e i file `requirements` sono A/C. Nessun file di configurazione è escluso. L'archivio utenti e sessioni sta **fuori dal repository** (`~/.config/lunar-mission-control/`) e **non deve** essere pubblicato.
- **Screenshot dell'interfaccia:** **non esistono** su disco (classe E). Non sono esclusi: non sono mai stati catturati.

---

## 4. Cartella `submission/`

I 21 file della cartella sono tutti **nuovi (B)**: candidati alla pubblicazione, nessuno ignorato.

| File | Presente | Stato |
|---|---|---|
| `PROJECT_SUMMARY.md` | ✔ | B |
| `PROJECT_DETAILS.md` | ✔ | B |
| `NASA_DATA_SOURCES.md` | ✔ | B |
| `OTHER_RESOURCES.md` | ✔ | B |
| `AI_USAGE_DISCLOSURE.md` | ✔ | B |
| `TECHNICAL_ARCHITECTURE.md` | ✔ | B |
| `DEMONSTRATION_SCRIPT.md` | ✔ | B |
| `SUBMISSION_CHECKLIST.md` | ✔ | B |
| `Lunar_South_Pole_Planner_NASA_2026.pptx` (4,0 MB) | ✔ | B, PowerPoint 2007+ |
| `Lunar_South_Pole_Planner_NASA_2026.pdf` (5,6 MB) | ✔ | B, 7 pagine |
| `assets/`: 7 PNG + `figure_stats.json` | ✔ | B |
| `tools/`: `make_figures.py`, `build_deck.py`, `deck_print.html` | ✔ | B |

**Riproducibilità:** tutti gli input di `make_figures.py` sono nel repository: DEM LOLA (A) e `reports/validation/*` (B). Tutte le immagini usate da `build_deck.py` esistono in `assets/`.

**Nota:** `tools/deck_print.html` è un file generato che contiene percorsi assoluti `file:///home/paolo/...`. Funziona solo su questa macchina, ma `build_deck.py` lo rigenera.

**Nota:** `PROJECT_DETAILS.md` cita `lunar.pptx` come fonte del nome del team. Quel file non è nel progetto: si trova nel Cestino di sistema.

---

## 7. Componenti del progetto mancanti

Non manca nessun componente funzionale. Ogni modulo importato, asset web servito, dataset letto e input delle figure è tracciato oppure nuovo e pronto.

Lacune documentali e di contenuto (non bloccanti):

1. **Screenshot dell'interfaccia:** non esistono. `DEMONSTRATION_SCRIPT.md` ne prevede 5.
2. **Video:** solo una bozza, esclusa (§6).
3. **LICENSE:** assente. Secondo la tua indicazione non l'ho aggiunta; va decisa prima della pubblicazione.
4. **Report dei test** (`documentation/REPORT_TEST.md`): non è più nel progetto (è nel Cestino). Il conteggio "494 passed" non è verificabile dal repository.
5. **File superati nella radice:** `SCIENCE_STATUS.txt` (contenuto vecchio, con `\n` letterali), `.descent_integration_check.json`, `.mission_audit_20261028.json`. Sono tracciati e verrebbero ripubblicati così come sono.
6. **Documentazione dei moduli in italiano** (`docs/*.md`), mentre il README è in inglese.
7. **`src/style_descent_risk_map.py`:** richiede QGIS, ma il file non lo dichiara.

## 8. Risorse necessarie per l'esecuzione non incluse

| Risorsa | Necessaria per | Documentata? |
|---|---|---|
| Pacchetti Python (`.venv`) | Tutto | ✔ `requirements*.txt` e README §11 |
| Rete verso NASA/JPL Horizons | Effemeridi live, finestre, confronto siti | ✔ README §12 (Offline operation) |
| **Software P-System** (`~/Github P-system` o `$PSYSTEM_HOME`, con il suo `.venv`) più `cryptography` | Solo l'integrazione P-System, opzionale e disattivata | ⚠ **Parziale**: il README dice che serve un'installazione separata, ma **non indica dove ottenerla** (nessun URL). Senza P-System i test relativi vengono saltati. |
| QGIS | Solo `style_descent_risk_map.py` | ⚠ Non documentato |
| Blender (flatpak) | Solo `video/` (escluso) | — |
| Browser con WebGL | Globo 3D | ✔ |
| `python-pptx`, `Pillow`, `lxml`, Google Chrome | Solo per ricostruire la presentazione | ✔ `SUBMISSION_CHECKLIST.md` |
| Archivio utenti | Login | ✔ Si crea dal web al primo avvio e non va pubblicato |

## 9. Risorse da scaricare esternamente

Per eseguire il progetto e riprodurre i risultati principali **non serve scaricare nessun dataset**: DEM LOLA, DTM LROC, kernel SPICE, DE421 e il GLB del globo sono già nel repository (circa 870 MB tracciati).

Da scaricare o installare a parte:

- **Horizons:** servizio online interrogato a runtime (`https://ssd.jpl.nasa.gov/api/horizons.api`).
- **P-System:** solo per la funzione sperimentale. La fonte non è documentata (§8).
- Le pagine di download originali dei dati NASA sono comunque in `submission/NASA_DATA_SOURCES.md`, per chi vuole verificarli o riscaricarli.

---

## 10. Verdetto finale

| Ambito | Esito |
|---|---|
| Codice sorgente (Python, Web UI, desktop, legacy) | Completo: 41 moduli attivi e tutti gli asset web tracciati o nuovi |
| Motore scientifico, Mission Engine, LOLA/LROC, effemeridi, rover e flotta, Science Tools, 3D | Completo |
| Dati necessari all'esecuzione | Completo: tutto tracciato, nulla escluso |
| Prove di validazione | Completo, a patto di pubblicare `reports/validation/` (nuovo) |
| Submission NASA | Completa: 10 documenti e file richiesti + 8 asset + 3 strumenti |
| Test | Completo come file; esecuzione non verificata |
| Script di installazione e avvio | Completo (`start.sh` è nuovo) |
| Materiali dimostrativi | Lacunosi: niente screenshot, video in bozza ed escluso |
| Dipendenze esterne documentate | Quasi complete: manca la fonte di P-System, opzionale, e la nota su QGIS |

### Risultato: **COMPLETE** (per lo stato preparato sul disco)

Tutto il materiale necessario per eseguire, verificare e valutare il Lunar South Pole Planner è incluso nei 295 file tracciati e nei 76 file nuovi, oppure è documentato. Nessun file importante è escluso solo per le dimensioni. L'unica esclusione di contenuto rimasta è `video/`, che non serve all'esecuzione. Le due presentazioni sono state pubblicate dopo l'audit.

**Condizioni del verdetto:**

1. Il verdetto valeva solo dopo `git add -A` + commit + push. **Condizione soddisfatta:** commit `ed112fe` pubblicato il 2026-11-15. Ora GitHub corrisponde al progetto locale, salvo i file esclusi da `.gitignore`.
2. Lacune minori da valutare prima della pubblicazione, nessuna bloccante per la completezza del codice:
   - LICENSE;
   - screenshot;
   - fonte di P-System;
   - file superati nella radice;
   - percorsi assoluti in `deck_print.html` e nei report di validazione.

> Nota: se si esegue `git add -A`, questo file `REPOSITORY_COMPLETENESS_AUDIT.md` verrà pubblicato. Se non lo vuoi nel repository pubblico, spostalo o escludilo prima.

---

## Registro della pubblicazione

Tutti i commit sono stati pubblicati su `origin/main` il 2026-11-15, su autorizzazione esplicita dell'autore.

| Commit | Contenuto |
|---|---|
| `ed112fe` | 77 file aggiunti e 24 modificati: tutti i file "nuovi" e "modificati" di questo audit, più il file stesso. `.gitignore` rispettato: **non** sono stati pubblicati `.venv/`, `backups/`, `video/`, cache, copie `.bak` e chiavi. |
| `6a546c9` | `LUNAR_P_SYSTEM_PRESENTATION.pdf`, `P-System Space Group · with P-System technology (1).pptx` e la relativa modifica a `.gitignore` |
| `655100d` | Aggiornamento di questo audit e di `REPOSITORY_UPDATE_REPORT.md` |
| commit successivo | `.pptx` rinominato in `P-System Space Group · with P-System technology.pptx` (tolto "(1)") |

**Esito aggiornato: COMPLETE**, ora anche su GitHub.

**Restano aperti:**
- LICENSE;
- esecuzione dei test;
- screenshot;
- `video/`, ancora escluso;
- `SCIENCE_STATUS.txt`, superato;
- la fonte di P-System.
