# F9 — Implementazione del redesign Mission Control

Data: 2026-11-15 · 01:26:04 → 01:46 · **Tempo totale effettivo ≈ 20 minuti** (budget: 60 minuti).
Skill usata: `frontend-design:frontend-design`.
Riferimenti: `F9_DESIGN_PROPOSAL.md`, `F9_STEP0_DECISIONS_BASELINE.md`, `F9_STEP1_REPORT.md`.

Decisioni applicate:

- **D-F1** (`/ui/`): usata per tutti i nuovi moduli;
- **D-F3** (profilo ricordato): applicata;
- **D-F4** (Archivo): in uso;
- **D-F5** (OrbitControls locale): applicata.

**D-F2 non è autorizzata e non è stata implementata.** Durante il caricamento si vede solo l'avanzamento reale del GLB.

## VERDETTO: **PASS** (con i limiti dichiarati nel §8)

Il redesign è implementato e verificato nel browser con dati reali. Esito delle verifiche:

- 4 profili a 4 larghezze;
- marker e selezione dei siti;
- 6 viste;
- effemeridi JPL, RF, termica, audit DEM, LROC, Mission Engine;
- console pulita, nessun errore HTTP;
- focus da tastiera e reduced motion;
- suite completa;
- hash scientifici.

Non verificati:

- la modalità `--desktop` (QtWebEngine), perché manca un display;
- la **corrispondenza geodetica dei marker**, che è solo coerente con la mappatura della texture (§4).

---

## 1. Modifiche realizzate

### Shell (barra di stato, sidebar, area di lavoro, ispettore)

- **Barra di stato (52 px).** Contiene:
  - il nome del prodotto;
  - il contesto corrente (sito, durata e inizio UTC presi dai campi);
  - **stati reali**: server, modello 3D, effemeridi e orologio UTC;
  - "Cambia profilo".

  Server: `fetch('/api/sites')` all'avvio e ogni 60 s. Modello 3D ed effemeridi: rispecchiano con un `MutationObserver` `#modelStatus` e `#ephemerisStatus`, che il codice esistente aggiorna con esiti veri.

  Rimossi gli stati statici "SYSTEM ONLINE", "LIVE RENDER", "Scene ACTIVE" e "Orbit interaction ENABLED".
- **Sidebar.** Ha 6 aree; il nome mostrato in UI è tra parentesi:
  - Solar Illumination (Illuminazione solare);
  - Earth Communication (Comunicazione Terra);
  - Terrain Analysis (Analisi del terreno);
  - Rover Mission (Missione rover);
  - Site Comparison (Confronto siti);
  - Mission Status (Stato missione).

  Ogni sezione dichiara le viste a cui appartiene con `data-views`; la vista attiva nasconde le altre via CSS. Nessuna sezione è stata rimossa o duplicata.
- **Viste Rover e Confronto.** Selezionano lo strumento corrispondente di `science.js` simulando un click sul suo pulsante. La logica di `science.js` non cambia.
- **Responsive.**

  | Larghezza | Layout |
  |---|---|
  | ≥ 1280 px | Sidebar estesa a 216 px |
  | 1001–1279 px | Sidebar a icone (64 px) |
  | 768–1000 px | Flusso verticale; lo splitter si disattiva come prima |
  | < 768 px | Globo a 55 vh, schede orizzontali, area di lavoro e ispettore in colonna; target di 44 px |

  A tutte le larghezze i gap di 1 px sul fondo dei filetti fanno da separatori; non ci sono card con ombra.
- **Ispettore.**
  - Scheda del sito: nome in Archivo largo (`wdth 125`, 34 px), l'unico tratto tipografico forte. Coordinate, durata, soglie e priorità sono in lista `dl`.
  - Stato dei sistemi.
  - Parametri della missione, in gruppi `fieldset`: Periodo, Soglie di elevazione, Priorità.
- **Splitter.** Stessa logica inline, stesso id e ruolo ARIA; ora ha un focus visibile.
- **Copy.** Italiano, frasi con la sola iniziale maiuscola, verbi d'azione ("Calcola effemeridi e finestre", "Avvia analisi"). Le stringhe richieste dai test sono invariate.

### Globo 3D (`main.js`, solo la parte grafica)

| Aspetto | Implementazione |
|---|---|
| Orientamento | Vista iniziale dal polo sud (camera a 152° dall'asse +Y, 25° di azimut). Pulsanti "Polo sud" ed "Emisfero" |
| Illuminazione | Una direzionale **radente**, circa 3° sotto il piano equatoriale. L'emisferica scende da 1,15 a 0,42 e si aggiunge un debole riflesso ciano; `roughness` 0,97 e `metalness` 0. Didascalia sempre visibile: *"Luce radente indicativa: non è la posizione reale del Sole."* |
| Controlli | `OrbitControls` r186 vendorizzato, con smorzamento, senza pan, zoom 4,2–15. Rotazione automatica **attorno all'asse polare**, che si ferma alla prima interazione |
| Tastiera | Sul canvas: frecce per ruotare, `+`/`−` per lo zoom, `Home`/`0` per tornare al polo. Doppio click: vista polo |
| Marker | Shackleton, Connecting Ridge e Nobile come pulsanti DOM (`ui/globe-markers.js`): focusabili, `aria-pressed`, nascosti sul lato non visibile. Le etichette vicine si nascondono a favore del sito selezionato, perché Shackleton e Connecting Ridge distano pochi km |
| Selezione | Click sul marker → `#site` + evento `change`, quindi il codice esistente aggiorna scheda e testi. Il `select` sincronizza il marker. Volo della camera di 650 ms, immediato con reduced motion |
| Caricamento | Avanzamento reale da `GLTFLoader` `onProgress` (percentuale e MB). In caso di errore: messaggio e pulsante "Riprova il caricamento". Senza WebGL: messaggio esplicito, pannelli utilizzabili |
| Prestazioni | Il rendering si sospende con `document.hidden` |

### Pannelli scientifici (solo presentazione)

- **Grafici:** stessi canvas e stesse funzioni. Cambiano solo i colori:
  - Sole `#EAD9A7`, Terra `#5CCFE6`;
  - soglia tratteggiata nel colore dell'astro;
  - bande GO `#4CC38A` al 14 %;
  - griglia `#323A44`, Archivo 12 px.
- **Valori:** griglie di valori con filetti, tabella delle finestre leggibile (12 px, intestazioni condensate `wdth 75`).
- **Science Tools:** controllo segmentato.
- **LROC:** barra di distribuzione con i colori dei token.

## 2. File

| File | Tipo | Contenuto |
|---|---|---|
| `src/ui_web/index.html` | modificato | Header, `<nav>`, `<aside>` ispettore, stage del globo, `data-views`, copy, 4 `<link>` + favicon + `<script src="/ui/shell.js">`, persistenza del profilo nello script inline. **Nessun id rimosso**; `.right` e `.left` sono stati spostati dentro `<aside>` |
| `src/ui_web/main.js` | modificato | Righe 1–143 (globo) riscritte. Inoltre: hook dei marker sui siti, `liveStatus` → `#ephemerisStatus`, colori e font dei grafici, titoli dei grafici in italiano |
| `src/ui_web/ui/shell.css` | nuovo | Layout, barra di stato, sidebar, ispettore, responsive, profilo Pubblico |
| `src/ui_web/ui/globe.css` | nuovo | Marker, controlli, avanzamento, errore, didascalia |
| `src/ui_web/ui/panels.css` | nuovo | Scheda del sito, form, sezioni, tabelle, grafici, LROC, Mission Engine |
| `src/ui_web/ui/profiles.css` | nuovo | Scelta del profilo, Educatore, Pubblico |
| `src/ui_web/ui/shell.js` | nuovo | Viste, stati reali, contesto, orologio UTC |
| `src/ui_web/ui/globe-markers.js` | nuovo | Posizionamento dei marker sulla mesh, proiezione, selezione |
| `src/ui_web/ui/icon.svg` | nuovo | Favicon: risolve il 404 preesistente di `/favicon.ico` |
| `src/ui_web/vendor/three/examples/jsm/controls/OrbitControls.js` | nuovo | Copia identica da `node_modules` (D-F5). SHA-256 `3d79d07e…5f2b`, uguale alla baseline del passo 0 |

**Non modificati:**

- `app.py`, `mission.js`, `science.js`, `science_api.py`, `mission_runner.py`;
- i moduli `src/*.py`, i dati e i test.

Gli hash di `mission.js` e `science.js` coincidono con la baseline del passo 0.

I vecchi blocchi `<style>` inline restano come fallback. I nuovi fogli li sovrascrivono sotto `[data-ui="v2"]`. Il test del passo 1 richiede che `</style>` preceda i `<link>`.

## 3. Backup e rollback

**Backup incrementale** (prima di ogni modifica): `backups/F9_ui_impl_20261115-012724/`

- contiene `index.html` e `main.js` originali e `SHA256SUMS`;
- i backup precedenti (`F9_ui_step1_*`, F9 completo, UI-only, passo 0) non sono stati toccati.

Gli altri file di questa fase sono tutti nuovi.

| Rollback | Procedura |
|---|---|
| Un singolo foglio (shell, globe, panels, profiles) | Rimuovere la sua riga `<link>`: la UI degrada graficamente e resta funzionante (id invariati) |
| Navigazione per viste e stati dell'header | Rimuovere `<script src="/ui/shell.js">`: tutte le sezioni tornano visibili insieme |
| Marker | In `main.js` togliere l'import di `globe-markers.js` e la chiamata `globeSitesReady(...)` |
| Globo e grafici | `cp backups/F9_ui_impl_20261115-012724/main.js src/ui_web/main.js` |
| Markup | `cp backups/F9_ui_impl_20261115-012724/index.html src/ui_web/index.html` |
| Tutta questa fase | I due `cp` precedenti, poi rimuovere `ui/shell.css`, `ui/globe.css`, `ui/panels.css`, `ui/profiles.css`, `ui/shell.js`, `ui/globe-markers.js`, `ui/icon.svg` e `vendor/three/examples/jsm/controls/` |

Dopo il rollback di `main.js` va ripristinato anche `index.html`, perché il nuovo markup non ha più `.right .metric:last-child`. È il caso inverso che non funziona: `main.js` vecchio con `index.html` nuovo.

## 4. Marker: come è calcolata la posizione (nessuna coordinata inventata)

1. Le coordinate arrivano solo da `GET /api/sites`. Valori usati:

   | Sito | Latitudine | Longitudine E |
   |---|---|---|
   | Shackleton | −89,7668° | −171,8700° |
   | Nobile | −85,44° | 37,37° |

2. Per collocarle sul modello si cerca il **vertice della mesh la cui coordinata UV corrisponde a quella lat/lon**. Si assume la convenzione della texture equirettangolare NASA CGI Moon Kit: longitudine 0° al centro, nord in alto, origine UV glTF in alto a sinistra.

   Il marker sta quindi sul punto della superficie dove la texture mostra quella posizione. Nessun valore è codificato nel frontend.
3. La verifica automatica `northIsUp()` conferma che il nord della texture è a +Y (nessun avviso in console). Visivamente, Shackleton e Connecting Ridge cadono sul punto di convergenza polare.

**Limite.** Il frame del GLB rispetto al DEM resta **non validato** (F4 §7). I marker sono coerenti con la texture, non certificati geodeticamente.

## 5. Test e verifiche

| Verifica | Esito |
|---|---|
| Suite completa `python -m pytest -q` | **432 passed**, 0 failed (§5.1) |
| Avvio del server | `python src/ui_web/app.py --no-browser --port 8794` da `/tmp`: 200 su `/`, `/ui/*.css|js|svg`, `/vendor/three/examples/jsm/controls/OrbitControls.js` |
| Catture: 4 profili × 4 larghezze (1440, 1024, 768, 390) | 16/16: **0 errori e 0 avvisi in console, nessun overflow orizzontale**, GLB `LOADED` in Pubblico e Pianificatore |
| Caricamento del globo e avanzamento | `LOADED`; l'elemento di avanzamento si nasconde a fine caricamento |
| Marker | 3/3 creati; selezione iniziale Shackleton |
| Click sul marker Nobile | `#site` = Nobile, scheda = Nobile, coordinate −85,44°, 37,37° (dall'API), `aria-pressed` = true |
| `select` → marker | Shackleton evidenziato |
| Tastiera | Canvas focusabile, frecce e `+` gestiti. Tab reale: focus ciano 2 px su "Cambia profilo" e sulle voci della sidebar |
| 6 viste | Ognuna mostra solo le sue sezioni; Rover → `rover-plan`, Confronto → `site-comparison`, Terreno → `dem-audit` |
| Effemeridi (JPL Horizons via backend, rete) | `CONNECTED · JPL`; header "calcolate (JPL)" con indicatore verde; 49 campioni; Sole 1,52–1,62°, Terra −3,70/−1,10°, 0 finestre (dati reali del periodo) |
| RF | Margine 9,37 dB |
| Termica | 376,57 K finale |
| Audit DEM | "RISULTATO REALE" da `src.data_quality.audit_raster` |
| LROC | Report caricato (primary 4.180.749) |
| Mission Engine | 5 report elencati |
| Profilo ricordato (D-F3) | Dopo il ricaricamento si riapre "planner"; "Cambia profilo" lo dimentica e torna alla scelta |
| Reduced motion | Con `prefers-reduced-motion: reduce`: niente rotazione automatica, niente smorzamento, voli immediati, transizioni CSS azzerate (base.css) |
| Errori HTTP | Nessuno (risolto anche il 404 di `/favicon.ico`) |
| Hash scientifici | **164/164 identici** alla lista del passo 1: `src/*.py`, `data/`, `de421.bsp`, `mission_config*.json`, test |

### 5.1 Pytest

- **Suite completa: 432 passed, 0 failed**, 7262 warning: le stesse deprecazioni della baseline (410 del passo 0 + 22 del passo 1). Durata 105 s. Output in `pytest_impl.txt`.
- **Test Web UI rieseguiti dopo l'ultima correzione CSS** (`static_assets`, `app`, `f5`): **72 passed**.

## 6. Screenshot prima e dopo

Artefatti fuori dal progetto: `~/Lunar-South-Pole-Planner_backups/F9_impl_screens_20261115-013347/`

| Elemento | Contenuto |
|---|---|
| `screenshots/` | 16 PNG + `capture_summary.json` + `public_390_fixed.png` |
| `before_after/` | 16 composizioni affiancate (baseline del passo 0 a sinistra, dopo a destra) |
| `check_*.png` | Viste con dati reali: Nobile, Solare dopo le effemeridi, Terra con RF, Rover con termica, Terreno, Stato |
| `capture.mjs`, `checks_impl.mjs`, `focus_check.mjs`, `public390.mjs` | Script riproducibili (CDP, nessuna dipendenza installata) |
| `checks_impl.json` | Esiti delle verifiche funzionali |
| `sci_hashes_impl.txt` | Hash dei file scientifici |
| `SHA256SUMS_screenshots.txt` | Hash delle catture |

Differenza in pixel rispetto alla baseline (soglia 24/255): è attesa ed elevata, perché il layout è stato ridisegnato.

| Profilo | 1440 | 1024 | 768 | 390 |
|---|---|---|---|---|
| Scelta profilo | 9,9 % | 7,5 % | 6,2 % | 12,1 % |
| Pubblico | 23,7 % | 26,3 % | 36,1 % | 25,2 % |
| Educatore | 6,2 % | 9,6 % | 8,8 % | 13,9 % |
| Pianificatore | 12,8 % | 15,0 % | 20,9 % | 28,6 % |

**Pubblico a 390 px.** La prima cattura mostrava il canvas nero e il pannello fuori dalla vista, ed è stata corretta (`profiles.css`, layout mobile del profilo Pubblico).

La riverifica ha dato: canvas 390×464, pannello in flusso sotto il globo, nessun overflow, nessuna eccezione (`public_390_fixed.png`). La cattura `public_390.png` della tabella è quella precedente la correzione.

## 7. Funzionalità non integrate o lasciate invariate

- **Timeline unica Sole/Terra con bande GO** (proposta §5.1). Richiede di unire due canvas in un nuovo disegno; restano i due grafici esistenti, uno per vista, ristilizzati.
- **Pill GO / NO-GO nella tabella delle finestre.** Il contenuto delle righe è generato da `renderOperationalWindows`. Cambiarne il markup avrebbe toccato la logica di rendering: è rimasto com'è, colorato solo tramite `.window-ok`.
- **Etichette dei grafici.** Le etichette temporali mostrano solo l'ora (01:41 → 01:41 su 48 h): è il formato preesistente di `drawEphemerisChart`, non cambiato.
- **Stringhe di stato interne in inglese** (`LOADED`, `READY`, `CONNECTED · JPL`, `WAITING FOR DATA`, `RISULTATO REALE`…). Sono generate da `main.js`, `mission.js` e `science.js` e alcune sono usate da test o script di cattura. Nell'header sono tradotte; nei pannelli restano originali.
- **Grafici vuoti prima del calcolo.** Lo spazio del canvas resta vuoto finché non si calcolano le effemeridi: nessun dato simulato.
- **Rendering on-demand completo:** non implementato. Il loop continua, ma si sospende in background.
- **Accessibilità.** L'alternativa testuale del canvas è un `aria-label` più la lista dei marker e del `select`. Non c'è un `<details>` con i dati dei grafici.

## 8. Problemi residui

1. Marker coerenti con la texture ma **non validati geodeticamente** (§4).
2. La luce è indicativa e fissa nel riferimento del modello: con la rotazione automatica la parte illuminata cambia rispetto alla vista. È dichiarato nella didascalia.
3. Modalità `--desktop` (QtWebEngine) non verificata, perché manca un display.
4. I CSS inline storici restano nel file (circa 330 righe) come fallback sovrascritto. Rimuoverli è un passo di pulizia separato, che richiede di adattare `test_index_links_v2_stylesheets` (richiede un `</style>` prima dei `<link>`).
5. Accessibilità WCAG AA non verificata con `design:accessibility-review`. Il contrasto dei token è quello già calcolato nella proposta (testo secondario ≈ 7:1).

## 9. Integrità scientifica

- Nessuna modifica ad algoritmi, formule, calcoli, DEM, raster, SPICE, Horizons, dati o risultati di missione, endpoint, contratti API o Mission Engine.
- **164/164 file scientifici con hash identico** alla baseline.
- `app.py`, `science_api.py`, `mission_runner.py`, `mission.js` e `science.js` non sono stati modificati.
- Nessuna funzionalità o componente eliminato. Nessuna dipendenza installata. Nessun commit o push.

---

Il lavoro si ferma qui: serve una nuova autorizzazione per qualsiasi passo successivo.
