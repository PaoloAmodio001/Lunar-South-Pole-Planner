# F0 — Stabilizzazione della Web UI ufficiale

Data: 2026-11-14
Punto di ingresso ufficiale: `python src/ui_web/app.py`
Modalità predefinita: server locale + browser. PySide6 è opzionale e si attiva con `--desktop`.

## VERDETTO: **PASS**

Tutti gli 11 obiettivi sono stati raggiunti e verificati. I limiti residui, elencati sotto, non bloccano nulla.

---

## 1. Backup

`backups/F0_web_ui_20261114T231145/` (la cartella `backups/` è già esclusa da `.gitignore`)

| File | SHA-256 prima della modifica |
|---|---|
| `src/ui_web/app.py` | `91914135d07310619e6f50ad8f6997bb2568b4098e867351c1a50d729c79b941` |
| `src/ui_web/index.html` | `3eaae68edeb20aa6ffcb815b70e9abfb43cf96d308133b06452c68db9c4a3941` |
| `src/ui_web/main.js` | `5bbccf972fe5e44ed89f6a641e7866fff4c8748e7675614d22456445b9106b4a` |

I checksum sono salvati in `SHA256SUMS` dentro la cartella di backup. Per ripristinare: `cp -p backups/F0_web_ui_20261114T231145/src/ui_web/* src/ui_web/`.

## 2. File modificati o creati

| File | Tipo | Modifica |
|---|---|---|
| `src/ui_web/app.py` | modificato | Avvio, CLI, whitelist statica, ricerca report LROC, PySide6 caricato solo con `--desktop`. **La logica degli endpoint API è invariata.** |
| `src/ui_web/index.html` | modificato (2 righe) | Importmap: `three` → `/vendor/three/build/three.module.js`, aggiunto `three/addons/`; script `/main.js` |
| `src/ui_web/main.js` | modificato (2 righe) | `import ... from 'three'` e `from 'three/addons/loaders/GLTFLoader.js'` |
| `src/ui_web/vendor/three/` | nuovo | Subset di three.js r186 (npm `three@0.186.1`) copiato senza modifiche, con LICENSE (MIT) e VERSION.txt, 2,3 MB |
| `tests/test_web_ui_app.py` | nuovo | 39 test |
| `reports/web_ui_consolidation/F0_WEB_UI_STABILIZATION.md` | nuovo | Questo report |

Nessuna modifica ad algoritmi scientifici, mission orchestrator, scoring/ranking, raster o kernel. Le interfacce legacy (`app.py` Streamlit, `src/lunar_3d_app.py`, …) non sono state toccate. Non è stato fatto nessun commit o push.

## 3. Dettaglio per obiettivo

| # | Obiettivo | Soluzione |
|---|---|---|
| 1 | Backup timestamped | Vedi §1 |
| 2 | Indipendenza dalla directory corrente | Tutti i percorsi partono da `Path(__file__).resolve()`. Il server non usa più `directory=PROJECT_ROOT`. I moduli API non contengono percorsi relativi alla cwd (verificato con grep). |
| 3 | Comando ufficiale | `python src/ui_web/app.py` (invariato) |
| 4 | Apertura automatica del browser | `webbrowser.open(url)` 0,5 s dopo l'avvio del server. Si disattiva con `--no-browser` o `LUNAR_UI_NO_BROWSER=1`. |
| 5 | Host e porta configurabili | `--host` / `LUNAR_UI_HOST` (predefinito `127.0.0.1`), `--port` / `LUNAR_UI_PORT` (predefinita `8765`). Con un host diverso da loopback viene stampato un avviso esplicito: la UI non ha autenticazione. |
| 6 | Porta occupata | Viene intercettato `EADDRINUSE`. Il messaggio è `[ERRORE] La porta N su HOST è già in uso.` e suggerisce `--port N+1`. Exit code 2, nessuno stack trace. |
| 7 | PySide6 opzionale | L'import avviene solo dentro `_run_desktop()`. Se PySide6 manca, `--desktop` termina con exit code 3 e un messaggio che indica l'URL da aprire nel browser. |
| 8 | Superficie del server ridotta | `BaseHTTPRequestHandler` con whitelist esplicita: `/`, `/index.html`, `/main.js`, `/vendor/three/**/*.js` (con controllo di contenimento dopo `resolve()`), il solo file `Moon_NASA_LRO_8k_Topo_Small.glb`, e gli endpoint `/api/*` già esistenti. Tutto il resto risponde 404. Niente directory listing. `/src/ui_web/index.html` fa redirect 302 su `/` per compatibilità. |
| 9 | Three.js | Copia locale versionata in `src/ui_web/vendor/three/`, risolta tramite importmap (`three`, `three/addons/`). Non dipende più da `node_modules`, che è in `.gitignore` e quindi manca in un clone pulito. |
| 10 | Report LROC | `find_latest_lroc_report()` cerca `audit-reports/lroc-quality-mask-*.json` e sceglie il più recente in ordine lessicografico, che per il timestamp ISO compatto coincide con quello cronologico; a parità di nome decide `mtime`. Nessuna data scritta nel codice. |
| 11 | Avvio da `/tmp` | Verificato manualmente e con un test automatico (subprocess con `cwd=tmp_path`). |

## 4. Test

### Suite completa
- Prima delle modifiche: **258 passed**
- Dopo le modifiche: **297 passed** (258 esistenti + 39 nuovi), 0 falliti. Nessun test esistente è stato modificato.

### `tests/test_web_ui_app.py` (39 test)
| Verifica | Test |
|---|---|
| Accesso alla UI | `/` → 200 text/html; l'importmap punta a `/vendor/three` |
| Redirect legacy | `/src/ui_web/index.html` → 302 `/` |
| Caricamento Three.js | `three.module.js`, `three.core.js`, `GLTFLoader.js`, `BufferGeometryUtils.js`, `SkeletonUtils.js` → 200 text/javascript; `main.js` non contiene `node_modules` |
| Risorse necessarie | GLB (HEAD → 200 `model/gltf-binary`), `/api/terrain/lroc-quality` → 200 |
| Rifiuto dei percorsi interni (21 casi) | `.py`, `node_modules`, `.git/config`, `.env`, `backups/`, `audit-reports/`, config, `data/`, directory listing, LICENSE, traversal (`..`, `%2e%2e`, `..%2f`, `//etc/passwd`) → tutti 404. HEAD su un percorso non autorizzato → 404. |
| Report LROC | Sceglie il più recente tra nomi con date arbitrarie e ignora i file non pertinenti; con la directory vuota restituisce `None` |
| CLI / env | Valori predefiniti, override da env, `--host`/`--port`, porta non valida rifiutata |
| Porta occupata | exit 2, messaggio con "porta N" e "già in uso" |
| Avvio da altra directory | Subprocess reale con `cwd=tmp_path` |
| Funzionamento senza PySide6 | Stesso subprocess con un finto modulo `PySide6` che solleva `ImportError`: la UI parte e serve Three.js |
| PySide6 opzionale | Il sorgente importa PySide6 solo dentro la funzione desktop |

### Verifiche manuali
- **Avvio da `/tmp`**: `cd /tmp && python ~/Lunar-South-Pole-Planner/src/ui_web/app.py --no-browser --port 8799`. Risultati: `/` 200, `/main.js` 200, three.module.js 200, LROC 200; `/src/ui_web/app.py`, `/.git/config`, `/mission_config.example.json` e il traversal `%2e%2e` → 404.
- **Porta occupata**: una seconda istanza sulla stessa porta stampa il messaggio esplicito ed esce con codice 2.
- **Apertura del browser**: con `BROWSER` impostato su uno script stub, l'URL ricevuto è `http://127.0.0.1:8798/`.
- **Three.js nel browser reale**: Chromium headless (SwiftShader) carica la pagina. Il canvas `#viewport` riceve `data-engine="three.js r186"`, quindi `WebGLRenderer` è stato istanziato e importmap e moduli si sono risolti. Nel log non compaiono errori di risoluzione dei moduli.

## 5. Problemi residui (non bloccanti)

1. **`--desktop` non provato con un display interattivo.** Il codice Qt è quello originale, cambia solo il caricamento lazy. Il test copre soltanto il caso senza PySide6.
2. **`src/ui_web/vendor/` non è tracciata da git.** Va inclusa nel prossimo commit, altrimenti un clone pulito non avrà Three.js. `node_modules/` e `package.json` sono rimasti al loro posto ma non sono più usati a runtime.
3. **`requirements.txt` elenca ancora PySide6 tra le dipendenze.** Non l'ho modificato per restare nel perimetro. Si può valutare di spostarlo in un file opzionale, ad esempio `requirements-desktop.txt`.
4. **Nessuna autenticazione.** Con `--host 0.0.0.0` la UI è raggiungibile da tutta la rete: c'è un avviso esplicito ma nessun blocco.
5. **Il GLB da 81 MB viene servito senza Range/ETag.** Va bene in locale, nessuna regressione rispetto a prima.
6. **Il report LROC viene scelto in base al nome del file.** Se in futuro cambia lo schema dei nomi, bisogna aggiornare `LROC_REPORT_GLOB`.
7. **Gli URL `/src/ui_web/main.js` e `/src/ui_web/node_modules/...` ora rispondono 404.** È voluto: l'unico consumatore era la UI stessa, ora aggiornata.
8. **I file `main.js.before-*` in `src/ui_web/`** sono backup precedenti a F0. Non sono più esposti dal server e non sono stati toccati.

## 6. Tempo impiegato

Circa 4 minuti, misurati con il timestamp di sistema dal primo comando alla stesura del report. Il limite era di 30 minuti, quindi nessuna attività è stata rimandata.
