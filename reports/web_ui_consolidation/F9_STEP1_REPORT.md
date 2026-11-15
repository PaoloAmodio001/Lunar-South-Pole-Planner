# F9 — Passo 1: Infrastruttura

Data: 2026-11-15 · 01:08:38 → 01:18 · **Tempo impiegato ≈ 10 minuti** (stima della proposta: 1,5–2 h)

Riferimenti:

- `F9_DESIGN_PROPOSAL.md` §11, passo 1: "Prefisso `/ui/` + test (se D-F1 = A), cartella `ui/`, font, `tokens.css`, `base.css`, `data-ui="v2"`";
- `F9_STEP0_DECISIONS_BASELINE.md`.

Decisioni applicate in questo passo:

- **D-F1** (prefisso `/ui/`) e **D-F4** (Archivo): applicate.
- **D-F3** (passo 7) e **D-F5** (passo 3): non anticipate.
- **D-F2**, non autorizzata: non implementata.

## VERDETTO: **PASS**

Tutte le attività del passo 1 sono state completate. Le verifiche obbligatorie sono state tutte eseguite, con esito positivo:

- confronto con la baseline;
- test mirati e suite completa;
- console e rete;
- quattro larghezze;
- funzionalità esistenti;
- hash scientifici.

## 1. Attività eseguite

| # | Attività (§11, passo 1) | Esito |
|---|---|---|
| 1 | **Prefisso statico `/ui/`** in `app.py` (D-F1) | Serve solo file sotto `src/ui_web/ui/` con estensione `.css`, `.js`, `.woff2` o `.svg`. Stessa protezione del prefisso `/vendor/three/`: rifiuta `\` e `\0`, risolve il percorso e verifica che resti dentro la base. Aggiunti i content-type `text/css`, `font/woff2`, `image/svg+xml`. **Nessun endpoint `/api/` toccato** |
| 2 | **Test del prefisso** | Nuovo file `tests/test_web_ui_static_assets.py` (22 test): asset serviti con content-type e `nosniff`; 13 percorsi non autorizzati o di traversal → 404; filtro delle estensioni anche su file reali; ordine e presenza dei `<link>`; `base.css` interamente limitato a `[data-ui="v2"]`; `tokens.css` contiene solo `@font-face` e variabili `--ui-*` |
| 3 | **Cartella `src/ui_web/ui/`** | Creata, con la struttura del §9.1 della proposta |
| 4 | **Font Archivo** (D-F4) | Scaricato **una sola volta** dall'API ufficiale Google Fonts CSS2 (`Archivo:wdth,wght@62..125,100..900`, v25): woff2 variabili latin (90 104 B) e latin-ext (86 240 B). Licenza `OFL.txt` dal repository `google/fonts`. Origine, URL e SHA-256 in `ui/fonts/SOURCE.md`. Il sottoinsieme vietnamita non è stato incluso. Nessuna dipendenza installata |
| 5 | **`ui/tokens.css`** | Palette di base e semantica (§3), scala tipografica 12–34 px, interlinee, larghezze dell'asse (75/100/125 %), spaziature a unità 4 px, raggi gerarchici, focus. Due `@font-face` con `font-stretch 62% 125%`, `font-weight 100 900`, `font-display: swap` e `unicode-range` dell'API. **Non applica stili a nessun elemento** |
| 6 | **`ui/base.css`** | Solo sotto `[data-ui="v2"]`: famiglia Archivo, cifre tabulari, `:focus-visible` ciano 2 px, `::selection`, `[hidden]{display:none!important}`, `prefers-reduced-motion`. Il passo 1 **non** cambia layout, dimensioni o colori dei componenti: quelli spettano ai passi 2–8 |
| 7 | **`data-ui="v2"`** e `<link>` | `<html lang="it" data-ui="v2">`. Due `<link>`, uno per foglio, dopo gli `<style>` esistenti, così a parità di specificità prevalgono; sono preceduti da un commento con la regola di rollback |

### Effetti visibili

Sono intenzionali e limitati alla base:

1. **Il carattere di tutta l'interfaccia passa ad Archivo** (prima `Inter, Segoe UI, Arial`, ma Inter non era caricato) e i numeri usano cifre tabulari. Dimensioni, pesi e maiuscole restano quelli attuali.
2. **Focus visibile:** gli elementi raggiunti da tastiera mostrano un contorno ciano. Lo splitter prima lo nascondeva (`.mission-splitter:focus{outline:none}`).
3. **Correzione di un difetto preesistente:** `science.js` mostra un solo pannello Science impostando `hidden`, ma la regola `.engineering-grid{display:grid}` annullava l'attributo, quindi i parametri di "Terreno locale" e "Orizzonte" restavano visibili insieme a quelli dello strumento selezionato. Con la regola di reset `[hidden]` ora è visibile solo il pannello attivo, come previsto dal codice JS, che non è stato toccato.
4. **Con `prefers-reduced-motion: reduce`** le transizioni CSS si azzerano. La rotazione automatica del globo è in JavaScript e verrà trattata al passo 3.

## 2. File

| File | Tipo | Modifica |
|---|---|---|
| `src/ui_web/app.py` | modificato | +17 righe: costanti `UI_ASSETS_*`, 3 content-type, ramo `/ui/` in `resolve_static()` |
| `src/ui_web/index.html` | modificato | `data-ui="v2"` su `<html>`; commento + 2 `<link>` prima di `</head>` (+4 / −1 righe) |
| `src/ui_web/ui/tokens.css` | nuovo | Token |
| `src/ui_web/ui/base.css` | nuovo | Base |
| `src/ui_web/ui/fonts/archivo-latin.woff2` | nuovo | `e3a28eade21a900c7155a247757f4b2834c07bb7ef07ad7efa55cebaac1e8f5e` |
| `src/ui_web/ui/fonts/archivo-latin-ext.woff2` | nuovo | `5717f37059660ca5c899bad6c48ee22c3ac55cb3c484055241689d0f905a1a86` |
| `src/ui_web/ui/fonts/OFL.txt` | nuovo | `108b4e57c9c796d3d38d0428ca7ee39de47ad93187302718d9b2d8864b9b716b` |
| `src/ui_web/ui/fonts/SOURCE.md` | nuovo | Origine e hash dei font (non servito) |
| `tests/test_web_ui_static_assets.py` | nuovo | 22 test |
| `reports/web_ui_consolidation/F9_STEP1_REPORT.md` | nuovo | Questo report |

`main.js`, `mission.js` e `science.js` **non sono stati modificati**: gli hash coincidono con la baseline. Nessun test esistente è stato modificato.

## 3. Backup e rollback

### Backup

**Backup incrementale** (prima delle modifiche): `backups/F9_ui_step1_20261115-010848/`, con `app.py` e `index.html` originali e `SHA256SUMS`. Verificato con `sha256sum -c`: 2/2 OK.
I backup F9 precedenti (completo, UI-only, passo 0) non sono stati toccati.

### Rollback per componente

Dal più leggero al completo:

| Cosa annullare | Come |
|---|---|
| Solo la base (font, focus, `[hidden]`, reduced motion) | Togliere `data-ui="v2"` da `<html>`, oppure la riga `<link … /ui/base.css>` |
| Base e token | Togliere entrambe le righe `<link>` e il commento in `index.html` |
| `index.html` intero | `cp backups/F9_ui_step1_20261115-010848/index.html src/ui_web/index.html` |
| Il prefisso `/ui/` | `cp backups/F9_ui_step1_20261115-010848/app.py src/ui_web/app.py` e rimuovere `tests/test_web_ui_static_assets.py` (altrimenti fallisce) |
| Gli asset | Rimuovere `src/ui_web/ui/`: tutti file nuovi, nessun file preesistente coinvolto |
| Tutto il passo 1 | I quattro punti precedenti, oppure dal backup UI-only di F9 (`ui_original.tar.zst`) |

## 4. Test

| Verifica | Risultato |
|---|---|
| `tests/test_web_ui_static_assets.py` | **22 passed**. Due errori iniziali erano nel test stesso, nel parsing di `:is(…)` e `@media`, e sono stati corretti nel test; `base.css` non è cambiato |
| Test Web UI esistenti (`app`, `f3`, `f5`, `mission`, `science`) | Tutti passati |
| **Suite completa** `python -m pytest -q` | **432 passed** (410 della baseline + 22 nuovi), 7262 warning, le stesse deprecazioni della baseline |

### Verifiche nel browser

Chromium 156 headless pilotato da `checks_step1.mjs` via CDP, server avviato da `/tmp`, profilo Pianificatore, 1440×900:

| Controllo | Esito |
|---|---|
| `data-ui` | `v2` |
| Famiglia calcolata di `body` | `Archivo, "Segoe UI Variable", system-ui, sans-serif` |
| Font caricato | `document.fonts.check('400 14px "Archivo"')` = true; latin `loaded`. Latin-ext non viene richiesto finché non serve, come previsto da `unicode-range` |
| **Asse di larghezza funzionante** | Lo stesso testo a 34 px misura 185,8 / 215,3 / 272,5 / 347,6 px con `font-stretch` 62 / 75 / 100 / 125 %. Prova empirica degli assi, perché fontTools non può leggere il woff2 senza `brotli` e `brotli` non è stato installato |
| Cifre tabulari | `font-variant-numeric: tabular-nums` |
| Pannelli Science | `dem-audit` visibile; `terrain`, `horizon`, `rover-plan` e `site-comparison` `display:none` |
| Focus da tastiera sullo splitter | `solid rgb(92, 207, 230) 2px` |
| Reduced motion | Transizione dello splitter 0,15 s → 1e-05 s con `prefers-reduced-motion: reduce` |
| Richieste `/ui/` | `tokens.css` 200 text/css, `base.css` 200 text/css, `archivo-latin.woff2` 200 font/woff2 |
| API usate dalla UI, chiamate dalla pagina | `/api/sites`, `/api/science/rasters`, `/api/mission/configs`, `/api/terrain/lroc-quality` → 200 |
| Errori JS / console | **Nessuna eccezione JavaScript.** Unico errore di rete: `GET /favicon.ico` 404, **preesistente** (la pagina non dichiara favicon e il server non l'ha mai servita). Non trattato, fuori dal passo 1 |

## 5. Confronto visivo con la baseline

Ho ripetuto la cattura del passo 0 con lo stesso script `capture.mjs`: 4 profili × 4 larghezze, 16 PNG.

- **Console:** 0 errori o avvisi in ogni cattura.
- **Overflow:** nessuno orizzontale del documento.
- **Modello:** `LOADED` in Pubblico e Pianificatore a tutte le larghezze.

Differenza in pixel rispetto alla baseline (soglia 24/255, Pillow già presente nel venv):

| Profilo | 1440 | 1024 | 768 | 390 |
|---|---|---|---|---|
| Scelta profilo | 2,7 % | 4,2 % | 4,0 % | 8,2 % |
| Pubblico | 7,5 % | 3,4 % | 10,1 % | 8,6 % |
| Educatore | 4,4 % | 7,0 % | 6,9 % | 11,5 % |
| Pianificatore | 3,8 % | 5,9 % | 7,6 % | 12,4 % |

**Interpretazione:**

- Le differenze vengono dalla **sostituzione del carattere** (glifi diversi in tutta la UI). Nei profili con il globo si aggiungono la rotazione automatica e le stelle generate a caso a ogni caricamento.
- Nelle viste controllate a occhio (Pianificatore a 1440 e 390) **disposizione, dimensioni dei pannelli, colori e contenuti sono identici alla baseline**: cambia solo il disegno delle lettere.
- I difetti a 390 px (griglia a due colonne, globo tagliato, intestazione sovrapposta) sono **preesistenti** e invariati: spettano al passo 2 (shell e responsive).

**Artefatti** (fuori dal progetto): `~/Lunar-South-Pole-Planner_backups/F9_step1_screens_20261115-011307/`

| Elemento | Contenuto |
|---|---|
| `screenshots/` | 16 PNG + `capture_summary.json` |
| `SHA256SUMS_screenshots.txt` | Hash delle catture |
| `diff_vs_baseline/` | Maschere delle differenze |
| `checks_step1.mjs`, `checks_step1.json` | Verifiche nel browser |
| `sci_hashes_before.txt`, `sci_hashes_after.txt` | Hash dei file scientifici |
| `pytest_step1.txt` | Risultato dei test |

## 6. Problemi residui

1. **`/favicon.ico` 404:** preesistente e innocuo. Si può risolvere con un SVG in `/ui/` e un `<link rel="icon">` in un passo successivo.
2. **La UI è in uno stato intermedio voluto:** carattere nuovo con dimensioni, colori e layout vecchi. I token `--ui-*` sono definiti ma non ancora usati dai componenti; li adotteranno i passi 2–8.
3. **Verifica degli assi del font solo empirica** (misure nel browser), non dalla tabella `fvar`, perché non ho installato `brotli`.
4. **Modalità `--desktop` (QtWebEngine) non verificata:** serve un display.
5. **Rete:** il passo 1 ha usato la rete una sola volta per scaricare i font. L'applicazione funziona offline perché i font sono locali.

## 7. Vincoli scientifici

Hash SHA-256 di **164 file** confrontati prima e dopo le modifiche: moduli `src/*.py`, tutto `data/`, `de421.bsp`, `mission_config*.json`, test esistenti. **164/164 identici.**

Non sono stati modificati:

- algoritmi, formule, calcoli o risultati;
- DEM, raster, kernel SPICE, Horizons o dati di missione;
- endpoint API, contratti, `science_api.py`, `mission_runner.py`.

Non ho eliminato file né componenti legacy, non ho installato dipendenze, non ho fatto commit o push.

## 8. Tempo

≈ 10 minuti effettivi (01:08:38 → 01:18), comprese le verifiche. La stima della proposta per il passo 1 era 1,5–2 h.

---

Il passo 2 (Shell) **non è stato avviato**: serve una nuova autorizzazione esplicita.
