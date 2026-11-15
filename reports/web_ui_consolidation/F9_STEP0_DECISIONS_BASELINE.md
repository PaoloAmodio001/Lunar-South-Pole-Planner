# F9 — Passo 0: decisioni e baseline

Data: 2026-11-15 · 01:01 → 01:08 (≈ 7 minuti)
Riferimento: `reports/web_ui_consolidation/F9_DESIGN_PROPOSAL.md`, §11 passo 0.
**Nessun file di codice, grafica o configurazione modificato.** L'unico file creato nel progetto è questo report; gli artefatti di baseline sono fuori dal progetto.

## VERDETTO: **PASS**

Le decisioni sono registrate. La baseline di test, hash e screenshot (4 profili × 4 larghezze) è acquisita e verificabile.
Il passo 1 può partire su autorizzazione.

## 1. Decisioni registrate

| Id | Decisione | Esito | Conseguenza per i passi successivi |
|---|---|---|---|
| D-F1 | Prefisso statico `/ui/` in `app.py` (solo `.css/.js/.woff2/.svg`, protezione traversal, test) | **Autorizzata** | Passo 1: modifica limitata alla whitelist statica; nessun endpoint API toccato |
| D-F2 | Sfera provvisoria con `lunar_texture_preview.png` durante il caricamento | **Non autorizzata** | Non verrà implementata. Durante il caricamento si mostra solo l'avanzamento reale del GLB (`onProgress`) |
| D-F3 | Memorizzazione del profilo scelto (`localStorage`, in try/catch) | **Autorizzata** | Passo 7. "Cambia profilo" resta sempre visibile |
| D-F4 | Font Archivo (SIL OFL) self-hosted in woff2 | **Autorizzata** | Passo 1: download unico da sorgente ufficiale, insieme a `OFL.txt`, in `src/ui_web/ui/fonts/`. Nessuna dipendenza Python/npm |
| D-F5 | Vendorizzare `OrbitControls.js` r186 da `node_modules` senza modifiche | **Autorizzata** | Passo 3. File sorgente verificato (§3) |

## 2. Baseline dei test

`python -m pytest -q` → **410 passed**, 7262 warning (le stesse deprecazioni di F6–F8) in 57 s.
Salvato in `pytest_baseline.txt`.

## 3. Hash dei file UI prima del restyling

| File | SHA-256 |
|---|---|
| `src/ui_web/index.html` | `8c77318045b24c66c92ef7758eb7a20f7be0948c5e025381b56fce06081d89ac` |
| `src/ui_web/main.js` | `dad5783fd57d21b9c5868ca760868a7c8fbe0d580e16dff14d09bf6650042f9b` |
| `src/ui_web/mission.js` | `ca16f5ff4ffa75446ac7f9764ef83cf1307060f235f021ef87583a0e8e858738` |
| `src/ui_web/science.js` | `28bfc9a8a4e1da429d094064da7f2e36898e94711814714d332f983b309653a8` |
| `src/ui_web/app.py` | `0f31bf8acd4a783ec197e3222a2657f063a15603c0ebce564d34733bb4a1bd4b` |
| `node_modules/three/examples/jsm/controls/OrbitControls.js` (sorgente per D-F5) | `3d79d07ecb686b4e5d93232eedab255331c1beef711e13164eaa1f68655a5f2b` |

Note su `OrbitControls.js` (D-F5):

- `three` è installato nella versione **0.186.1**, la stessa di `vendor/three/VERSION.txt`;
- il file ha 1972 righe e importa **solo da `'three'`**, quindi funziona con l'importmap attuale senza adattamenti.

## 4. Screenshot di baseline

**Metodo.** Chromium 156 headless (swiftshader) pilotato tramite DevTools Protocol da Node 24, che ha `WebSocket` integrato. **Non è stata installata nessuna dipendenza.**

**Script:** `capture.mjs`, salvato con gli screenshot e riutilizzabile per i confronti dei passi successivi. Per ogni larghezza e profilo:

1. apre la pagina e clicca il pulsante `[data-profile]`;
2. per Pubblico e Pianificatore aspetta che `#modelStatus` sia `LOADED` (massimo 45 s);
3. cattura lo screenshot e registra overflow orizzontale ed errori o avvisi della console.

Server: `python src/ui_web/app.py --no-browser --port 8793`, avviato da `/tmp`.

| Profilo | 1440×900 | 1024×768 | 768×1024 | 390×844 |
|---|---|---|---|---|
| Scelta profilo (`home`) | ✓ | ✓ | ✓ | ✓ |
| Pubblico | ✓ GLB LOADED | ✓ LOADED | ✓ LOADED | ✓ LOADED |
| Educatore | ✓ | ✓ | ✓ | ✓ |
| Pianificatore | ✓ GLB LOADED | ✓ LOADED | ✓ LOADED | ✓ LOADED |

Per tutte le 16 catture: nessun errore o avviso in console, nessun overflow orizzontale del documento.

### Osservazioni dagli screenshot (vista Pianificatore, prima non disponibile)

Confermano l'analisi della proposta e la integrano:

- **1440:**
  - il globo è inquadrato sull'**equatore**; il polo sud si vede appena in basso a destra;
  - la riga "Mission Analytics" è tagliata dal bordo inferiore;
  - la colonna destra contiene stati statici: "Orbit interaction ENABLED", "Live ephemerides READY", "LIVE RENDER", "SYSTEM ONLINE".
- **390:**
  - la griglia resta su **due colonne affiancate**, quindi il globo è tagliato a destra;
  - l'intestazione va a capo e si sovrappone;
  - le etichette dei pannelli spezzano le parole ("LUNAR SURFACE / 3D EXPLORER" su 3 righe).

  Il problema non si vede come overflow del documento: il contenuto è tagliato dentro i pannelli (`overflow:hidden`).
- **Pubblico 1440:** il pannello flottante è leggibile, ma la lingua è mista ("ELEVATION MINIMA DEL SOLE").

## 5. Artefatti (fuori dal progetto)

`~/Lunar-South-Pole-Planner_backups/F9_step0_baseline_20261115-010147/` (4,5 MB):

| File | Contenuto |
|---|---|
| `screenshots/*.png` | 16 PNG `<profilo>_<larghezza>.png` |
| `screenshots/capture_summary.json` | Per ogni cattura: stato del GLB, overflow, console |
| `SHA256SUMS_screenshots.txt` | Hash degli screenshot |
| `SHA256SUMS_ui_baseline.txt` | Hash dei file UI (§3) |
| `pytest_baseline.txt` | Risultato pytest |
| `capture.mjs` | Script di cattura |

Per riprodurre la cattura:

```bash
python src/ui_web/app.py --no-browser --port 8793 &
chromium --headless=new --no-sandbox --use-angle=swiftshader --enable-unsafe-swiftshader \
  --hide-scrollbars --remote-debugging-port=9333 --user-data-dir=<tmp> about:blank &
node capture.mjs http://127.0.0.1:8793/ <cartella-output> 9333
```

## 6. Note

- Il backup completo e quello UI-only del report F9 restano il punto di ripristino del codice. Gli artefatti di questo passo sono solo un riferimento visivo e di test.
- **Il passo 1 richiederà accesso alla rete** per scaricare Archivo (D-F4) da una sorgente ufficiale (repository Google Fonts / Omnibus-Type, licenza OFL). Gli hash dei file scaricati saranno registrati.
