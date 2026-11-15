# F9 — Proposta di redesign della Web UI: Mission Control

Data: 2026-11-15 · Fase 1, solo analisi e progettazione. **Nessun file modificato** a parte la creazione di questo documento.
Skill usata: `frontend-design:frontend-design`, con piano, revisione rispetto ai default "generati" e autocritica.

Fonti analizzate:

- `src/ui_web/index.html` (891 righe: 7 blocchi `<style>` inline e 2 `<script>` inline);
- `main.js` (836), `mission.js` (361), `science.js` (212), `app.py` (whitelist statica);
- i test `tests/test_web_ui_*.py`;
- il GLB `Moon_NASA_LRO_8k_Topo_Small.glb`;
- uno screenshot headless della schermata iniziale (Chromium, 1440×900).

Backup pre-restyling: `~/Lunar-South-Pole-Planner_backups/F9_20261115-004220/` (report F9 backup).

---

## 1. Analisi dell'interfaccia attuale

### 1.1 Struttura

| Area | Implementazione | Osservazioni |
|---|---|---|
| Header | `<header>` 65 px: brand, "● SYSTEM ONLINE", "NASA LRO DATASET · WEBGL VIEWPORT", pulsante `#changeProfile` | Gli stati sono **testo statico**: "SYSTEM ONLINE" e "LIVE RENDER" non derivano da nessun controllo reale |
| Scelta profilo | `#profileHome`: 3 card (Pubblico, Educatore, Pianificatore di missione); classe sul `body` (`profile-home`, `public-mode`, `educator-mode`) | Mostrata a ogni caricamento: `showProfileHome()` è sempre chiamata |
| Educatore | `#educatorHome`: 4 card statiche numerate "01 · ILLUMINAZIONE"… | Contenuto placeholder: "saranno collegate progressivamente" |
| Planner | `<main>` a griglia 3×3: `.left` (configurazione), `.center` (globo), `.right` (telemetria), `#missionSplitter` (ridimensionamento verticale), `.bottom` (grafici, analytics, finestre, Mission Engine, Science Tools, LROC, RF, termica) | Il pannello `.bottom` è **una colonna di scroll unica** con 7 sezioni eterogenee: è il punto più debole della gerarchia |
| Pubblico | Stesso `<main>`: il globo è a tutto schermo e il pannello `#publicMissionPanel` è sovrapposto | Riusa `.center` e nasconde gli altri pannelli |

### 1.2 CSS

- 7 blocchi `<style>` aggiunti in tempi diversi, circa 215 regole. Molte regole si sovrascrivono a vicenda:
  - `main{grid-template-rows}` è ridefinito 3 volte;
  - ci sono due `@media(max-width:1000px)` consecutivi.
- **Token parziali:** `:root` definisce solo 7 variabili. Il resto è hardcoded con circa 45 colori distinti, molti quasi identici: `#263b50`, `#2b4053`, `#2a4054`, `#24394c`; `#8295a9`, `#8196a9`, `#91a8bb`, `#9aafc2`, `#9cafc1`.
- **Tipografia:** `13px Inter, Segoe UI, Arial`. Inter non è caricato, quindi il font effettivo è quello di sistema. Le dimensioni vanno da 9 a 23 px senza una scala.
- **CSS morto:** `.home-screen`, `#openHome`, `.home-*` e `#homeError` non hanno elementi corrispondenti nell'HTML.
- **Accessibilità:**
  - nessun `prefers-reduced-motion`;
  - nessuno stile `:focus-visible`, e `.mission-splitter:focus{outline:none}` rimuove il focus;
  - molti testi a 9–10 px;
  - il canvas del globo non ha alternative accessibili.
- **Responsive:**
  - due breakpoint (1000 e 900/700 px);
  - `body{overflow:hidden}` su desktop;
  - sotto 1000 px la griglia diventa 210 px + 1fr: su mobile il pannello di configurazione resta stretto e affiancato al globo.

### 1.3 Linguaggio visivo (dallo screenshot e dal codice)

Lo stile attuale mostra quasi tutti i segnali tipici dei template:

- etichette in maiuscolo spaziato sopra ogni blocco;
- metadati uniti da "·";
- "→" in coda ai link;
- tag "01 / SETUP", "02 / STATUS", "03 / ANALYSIS", che non sono una sequenza reale;
- card identiche con lo stesso bordo `#263b50` e lo stesso radius;
- gradienti decorativi;
- lingua mista: "ELEVATION MINIMA", "UPDATE VISUALIZATION", "RUN ANALYSIS".

La base cromatica (navy e ciano) va però nella direzione richiesta: va disciplinata, non ribaltata.

### 1.4 Globo 3D (`main.js` 1–143)

| Aspetto | Stato attuale |
|---|---|
| Modello | GLB 81,5 MB: 1 mesh `Sphere` con 2 021 340 vertici e 3 047 424 indici. Raggio da 0,980 a 0,995: **la topografia è nella geometria**. 1 materiale PBR con **una sola texture colore 8k JPEG** (`Moon_8k_Color_v001`); niente normal map |
| Luci | `HemisphereLight` 1,15 + direzionale "sole" 3,0 da (−4, 3, 5) + rim blu 0,25. **L'emisferica appiattisce le ombre**: il rilievo della geometria si legge poco |
| Rendering | ACES filmic, esposizione 1,10, sRGB, pixel ratio ≤ 2. Stelle: 1800 punti casuali |
| Controlli | Trascinamento personalizzato (rotazione del gruppo), rotella per lo zoom (z 4,5–15), doppio click per il reset. **Rotazione automatica continua** anche con reduced motion. Nessun controllo da tastiera. `OrbitControls` non è vendorizzato, ma esiste in `node_modules/three/examples/jsm/controls/` (stessa r186) |
| Inquadratura | Camera sull'equatore: **il polo sud, che è il soggetto del progetto, è quasi invisibile** |
| Marker | **Nessuno.** La selezione del sito aggiorna solo testi (`#targetName`, `#siteLabel`, `#coords`) |
| Caricamento | `onProgress` non usato: l'utente aspetta 81 MB senza indicazione di avanzamento |
| Frame | Il frame del GLB **non è validato** rispetto alla griglia DEM (report F4 §7). Lat/lon globali possono essere proiettati sulla sfera, ma la convenzione di longitudine della texture va verificata |

Asset disponibili:

- il GLB (unica risorsa grafica servita);
- `data/terrain/lunar_texture_preview.png` (2048×1024, equirettangolare, non servita);
- i PNG dei profili d'orizzonte in `data/terrain/` (non serviti);
- `vendor/three`: core, `GLTFLoader`, utils.

### 1.5 Collegamento al backend

| Frontend | Endpoint | Note |
|---|---|---|
| `main.js` | `GET /api/sites`, `GET /api/ephemerides`, `POST /api/communications/link-budget`, `POST /api/thermal/simulate`, `GET /api/terrain/lroc-quality` | Fetch diretti; grafici su `<canvas>` disegnati a mano (`drawEphemerisChart`, `drawThermalChart`) |
| `mission.js` | `/api/mission/configs|validate|run|status|runs|reports` | Polling. Usa `textContent`/DOM, nessun `innerHTML` |
| `science.js` | `/api/science/rasters|dem-audit|terrain|horizon|rover-plan|site-comparison` | Pannelli `data-sci-pane` |

Il redesign **non tocca alcun endpoint né contratto**: cambia solo presentazione e interazione.

### 1.6 Vincoli imposti dai test (da rispettare)

| Test | Vincolo |
|---|---|
| `test_web_ui_app.py` | L'`index.html` contiene l'importmap `"three": "/vendor/three/build/three.module.js"` e `src="/main.js"`. `main.js` contiene `from 'three'` e `from 'three/addons/loaders/GLTFLoader.js'` e non contiene `node_modules`. I percorsi non in whitelist rispondono 404 |
| `test_web_ui_f5.py` | `main.js` contiene `fetch('/api/sites'` e "Analytics non forniti dal server"; non contiene coordinate letterali dei siti, `calculateMissionAnalytics`, `drawChart`, `charts()`. `<select id="site">` contiene esattamente i nomi di `SITES` |
| `test_web_ui_f3.py`, `test_web_ui_mission.py`, `test_web_ui_science.py` | `id="missionReports"`, `id="missionEngineSection"`, `id="scienceSection"`, `src="/mission.js"`, `/science.js` contiene `/api/science/`, `/mission.js` contiene `/api/mission/reports` |

---

## 2. Architettura grafica proposta

### 2.1 Soggetto, pubblico, compito

- **Soggetto:** la pianificazione di operazioni al polo sud lunare, dove il Sole resta a pochi gradi sopra l'orizzonte, la luce è sempre radente, le ombre sono lunghissime e la Terra è bassa sull'orizzonte.
- **Pubblico principale:** il pianificatore, che lavora sui numeri. Pubblici secondari: pubblico generale ed educatori.
- **Compito primario:** scegliere un sito e un periodo e capire **quando** Sole e Terra sono entrambi utilizzabili, cioè quando c'è una finestra operativa, insieme ai vincoli del terreno.

### 2.2 Concetto: "luce radente"

L'identità nasce dal fenomeno che definisce il soggetto.

1. **Il globo è inquadrato dal polo sud,** non dall'equatore, ed è illuminato da una sola luce radente quasi perpendicolare all'asse polare. Rilievi e crateri polari diventano leggibili, e questo è l'unico elemento "audace" dell'interfaccia.
2. **Il colore è un codice, non una decorazione.**
   - Nei dati, il Sole ha sempre lo stesso tono solare chiaro e la Terra sempre lo stesso ciano: grafici, marker, legende e valori numerici.
   - Gli stati usano il vocabolario reale del controllo missione: **GO / NO-GO**, applicato alle finestre operative. Lì ha un significato preciso: Sole ≥ soglia **e** Terra ≥ soglia.
3. **Tutto il resto è silenzioso:** antracite, filetti sottili, testo chiaro. Il blu serve solo all'azione primaria; il ciano a selezione, focus e dati della Terra.

### 2.3 Principi

- **Una sola cosa memorabile:** il globo polare in luce radente. Pannelli e controlli non competono con lui: niente gradienti, niente bagliori, niente animazioni d'ingresso.
- **Stato reale o nessuno stato.** Ogni indicatore deriva da un controllo vero: server raggiungibile, avanzamento del GLB, età dei dati, stato del job del Mission Engine. "SYSTEM ONLINE" statico viene eliminato.
- **Struttura = informazione.** Bordi e separatori delimitano gruppi funzionali reali. La numerazione esiste solo dove c'è una sequenza (le fasi del Mission Engine).
- **Testo in italiano, in minuscolo normale,** con verbi d'azione ("Calcola le finestre", non "UPDATE VISUALIZATION"). Il maiuscolo è riservato a GO / NO-GO e alle sigle (UTC, DEM, LROC).
- **Provenienza visibile:** ogni risultato scientifico mostra modulo e raster (dato già fornito dal backend), in uno stile secondario ma sempre presente.

### 2.4 Revisione del piano rispetto ai default

| Prima idea (default) | Perché è un default | Scelta finale |
|---|---|---|
| Sfondo near-black con un solo accento ciano acido | Tratto n. 2 dell'elenco dei default; il brief chiede invece navy e antracite | Due fondi distinti (navy per lo spazio attorno al globo, antracite per i pannelli). Ciano desaturato e usato poco; blu solo per l'azione primaria |
| Etichette in maiuscolo spaziato sopra ogni campo (come oggi) | Template chrome | Etichette in minuscolo normale, peso medio; maiuscolo solo per GO / NO-GO |
| Monospace per le etichette dei dati | Template chrome | Una sola famiglia con **cifre tabulari** (`font-variant-numeric: tabular-nums`) per l'allineamento dei numeri |
| Griglia di card identiche per le metriche | Kit SaaS | Metriche come **righe di una tabella di telemetria**: etichetta a sinistra, valore e unità allineati a destra. Le card restano solo dove raggruppano un contesto (pannello) |
| Hero "numero grande + etichetta piccola + gradiente" | Default dichiarato | L'apertura è il globo stesso, già orientato sul polo |
| Tag "01 / SETUP", "02 / STATUS" | Falsa sequenza | Rimossi |
| Animazioni d'ingresso dei pannelli | Generico | Un solo movimento: il volo della camera verso il sito selezionato, che risponde a un'azione dell'utente. Con reduced motion diventa un salto immediato |
| Font tecnico "spaziale" (Space Grotesk, Orbitron, Barlow Condensed) | Cliché del tema spazio | **Archivo** variabile (asse larghezza 62–125): vedi §4 |

---

## 3. Palette

### 3.1 Base (6 valori)

| Nome | HEX | Ruolo |
|---|---|---|
| Abisso | `#0A1322` | Fondo dello stage del globo e della pagina (navy profondo) |
| Antracite | `#191D23` | Fondo dei pannelli: sidebar, ispettore, timeline |
| Antracite rilievo | `#22272E` | Controlli, righe selezionate, campi di input |
| Filetto | `#323A44` | Bordi, separatori, griglie dei grafici |
| Testo | `#E7ECF1` | Testo primario |
| Testo secondario | `#9AA6B2` | Etichette, unità, provenienza (contrasto ≈ 7:1 su Antracite) |

### 3.2 Accenti e codici semantici

| Nome | HEX | Uso esclusivo |
|---|---|---|
| Blu segnale | `#2F6FDB` | Riempimento dell'azione primaria; testo bianco (contrasto ≈ 4,9:1) |
| Ciano | `#5CCFE6` | Selezione, focus (`outline` 2 px), marker selezionato, **dati Terra** |
| Luce solare | `#EAD9A7` | **Solo dati Sole**: traccia, valori, icona |
| GO | `#4CC38A` | Finestra operativa / esito valido |
| Attenzione | `#E3B341` | Avvisi, dati parziali, soglia non soddisfatta da uno dei due astri |
| NO-GO / errore | `#F0605D` | Errori, nessuna finestra, NO-GO |
| Inattivo | `#7D8995` | Stato sconosciuto o non calcolato (≥ 4,5:1 su Antracite) |

Classi LROC, già colorate oggi:

| Classe | Colore |
|---|---|
| primary | `#5CCFE6` (ciano) |
| interpolated | `#E3B341` |
| unresolved | `#A68BE0` |
| invalid | `#56616D` |

Tutte le coppie testo/fondo vanno verificate a WCAG 2.1 AA (4,5:1 per il testo normale, 3:1 per gli elementi grafici) con `design:accessibility-review` prima dell'implementazione.
Lo stato non è mai codificato **solo** dal colore: c'è sempre anche l'etichetta GO / NO-GO o un'icona.

---

## 4. Tipografia e spaziatura

### 4.1 Carattere

**Archivo** (Omnibus-Type, licenza SIL OFL), variabile con assi `wght` 100–900 e `wdth` 62–125. Una sola famiglia, usata in modo attivo:

| Ruolo | Impostazioni | Dove |
|---|---|---|
| Nome del sito (display) | `wdth 125`, `wght 600`, 34 px | Ispettore del sito: il nome largo, quasi da cartografia, è l'unico tratto tipografico "forte" |
| Titoli di sezione | `wdth 100`, `wght 600`, 17 px | Intestazioni dei pannelli |
| Testo e controlli | `wdth 100`, `wght 400`, 14 px | Body |
| Etichette dense, intestazioni di tabella | `wdth 75`, `wght 500`, 12 px | Tabelle delle finestre, griglie dei parametri: la larghezza condensata fa stare più colonne senza ridurre il corpo |
| Valori numerici | `tabular-nums`, `wght 500` | Telemetria, tabelle, assi dei grafici |

- **Font fallback:** `"Segoe UI Variable", system-ui, sans-serif`.
- **Self-hosting obbligatorio**, perché l'app deve funzionare offline: `woff2` locali (vedi §10, decisione D-F1).

### 4.2 Scala

La scala è modulare in rapporto 1,2 (≈ terza minore, come suggerisce Bringhurst) e arrotondata: **12 · 14 · 17 · 20 · 24 · 34** px.

- **Interlinea:** 1,5 per il body; 1,25 per i titoli; 1,2 per i valori.
- **Lunghezza di riga:** ≤ 72 caratteri nei testi esplicativi (pannelli di aiuto, profilo Educatore).
- **Corpo minimo:** 12 px. Spariscono i 9–10 px attuali.

### 4.3 Spaziatura e forme

| Elemento | Valori |
|---|---|
| Unità base | 4 px. Scala: 4 · 8 · 12 · 16 · 24 · 32 · 48 |
| Padding | Pannelli 16 px; righe di telemetria 8 × 12 px; gap tra gruppi 24 px |
| Raggi di curvatura | Gerarchici, non uniformi: input e pulsanti 3 px; pannelli 6 px; pill GO / NO-GO 2 px; marker circolari |
| Ombre | Nessuna sui pannelli. La profondità viene solo dal contrasto Abisso / Antracite e dai filetti |
| Focus | `outline: 2px solid #5CCFE6; outline-offset: 2px` su tutti gli elementi interattivi, splitter compreso |

---

## 5. Layout della dashboard (profilo Pianificatore)

### 5.1 Desktop ≥ 1280 px

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│ Lunar South Pole Planner      Shackleton · 48 h dal 15/11 10:00 UTC    ● server ok  │  barra di stato 48 px
├────────────┬───────────────────────────────────────────────────┬───────────────────┤
│ SIDEBAR    │                                                   │ ISPETTORE (380 px) │
│ 232 px     │                                                   │                   │
│            │              GLOBO (stage, fondo Abisso)          │ Shackleton         │
│ ◎ Siti     │                                                   │ lat/lon da API    │
│ ☀ Finestre │        vista dal polo sud, luce radente           │ ───────────────── │
│ ⌁ Comunic. │        marker dei 3 siti (pulsanti DOM)           │ contenuto della   │
│ ◒ Termica  │                                                   │ sezione attiva:   │
│ ▦ Terreno  │                                                   │ parametri,        │
│ ◫ LROC     │   [+] [−] [⟲ polo] [⟲ reset]   caricamento 63 %    │ risultati,        │
│ ⚙ Motore   │                                                   │ provenienza       │
│ ▤ Report   ├───────────────────────────────────────────────────┤                   │
│            │ TIMELINE  Sole ─── Terra ─── │GO│  │GO│   NO-GO    │                   │
│ profilo ▾  │ 0°┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │                   │
└────────────┴───────────────────────────────────────────────────┴───────────────────┘
```

**Barra di stato (48 px).**

- A sinistra: il nome del prodotto.
- Al centro: il **contesto corrente** (sito, durata, inizio UTC), che sostituisce i sottotitoli decorativi.
- A destra: gli stati reali (server, età delle effemeridi) e l'orologio UTC.
- Il cambio profilo si sposta in fondo alla sidebar.

**Sidebar (232 px, comprimibile a 64 px).** Navigazione per *area di lavoro*, non per pannello tecnico:

| Voce | Contenuto | Pannello attuale |
|---|---|---|
| Siti | Selezione del sito e configurazione della missione | `.left` |
| Finestre operative | Effemeridi, analytics, tabella delle finestre | `.bottom`: grafici, analytics, windows |
| Comunicazioni | Link budget RF | `.bottom` |
| Termica | Simulazione termica | `.bottom` |
| Terreno | Science Tools | `#scienceSection` |
| Qualità LROC | | `#lrocQualitySection` |
| Mission Engine | | `#missionEngineSection` |
| Report | Report e export | |

L'elemento attivo ha un filetto ciano di 2 px a sinistra e testo primario. Le icone sono SVG inline monocromatici; l'etichetta è sempre presente in forma estesa.

**Stage.**

- Il globo occupa tutto lo spazio centrale.
- I controlli della camera sono pulsanti reali, in basso a sinistra.
- L'avanzamento del caricamento GLB è reale, in basso a destra, e scompare a caricamento finito.

**Ispettore (380 px).**

- In alto, sempre visibile: la *scheda del sito selezionato* (nome largo, coordinate da `/api/sites`, ultimo esito GO / NO-GO se calcolato).
- Sotto: il contenuto della sezione scelta nella sidebar.
- Scroll indipendente.

**Timeline (160 px, ridimensionabile).**

- Elevazione di Sole e Terra sullo stesso asse temporale, con l'orizzonte 0° come linea piena e le soglie tratteggiate.
- Le finestre operative appaiono come **bande GO**.
- Il passaggio del mouse mostra un cursore sincronizzato sui due astri e il valore nell'ispettore.
- Sostituisce i due canvas separati `#chart1` e `#chart2`, che restano nel DOM e vengono riusati (§8).
- Il ridimensionamento riusa la logica di `#missionSplitter`, con lo stesso id e lo stesso ruolo `separator`.

**Allineamento:** tutto allineato a sinistra; i numeri allineati a destra nelle colonne. Nessun contenuto centrato, tranne la schermata di scelta del profilo.

### 5.2 Tablet 768–1279 px

- La sidebar si comprime a 64 px, solo icone con `aria-label` e tooltip.
- L'ispettore diventa un **drawer** sovrapposto allo stage (360 px), apribile e chiudibile.
- La timeline resta sotto lo stage.

### 5.3 Mobile < 768 px

```
┌──────────────────────────┐
│ barra stato (contesto)   │
├──────────────────────────┤
│ GLOBO (55 vh)            │
├──────────────────────────┤
│ timeline (compatta)      │
├──────────────────────────┤
│ ispettore (flusso)       │
├──────────────────────────┤
│ nav inferiore: 5 voci +  │
│ "Altro"                  │
└──────────────────────────┘
```

- Su mobile `body` scorre normalmente.
- Target di tocco ≥ 44 px.
- Margine laterale di 16 px.

### 5.4 Profili

| Profilo | Proposta |
|---|---|
| **Scelta del profilo** | Si apre sul globo polare in luce radente, a tutto schermo e sfocato al 20 %. Sopra, tre scelte presentate come elenco verticale con nome, una frase e il pulsante "Apri", non come tre card identiche. Il profilo scelto viene ricordato in `localStorage` (in try/catch); "Cambia profilo" resta nella sidebar |
| **Pubblico** | Stage a tutto schermo, marker cliccabili, pannello flottante con i 3 siti e i parametri (`#publicMissionPanel` restilizzato) ed esito in linguaggio semplice ("Sole e Terra visibili insieme per 31 ore su 48") |
| **Educatore** | Le 4 lezioni restano 4 voci, ma qui la numerazione è legittima perché è un percorso. Ogni lezione evidenzia un fenomeno sul globo (luce radente, Terra bassa); i contenuti restano quelli attuali |
| **Pianificatore** | Layout del §5.1 |

---

## 6. Globo lunare 3D

| Aspetto | Proposta | Note di affidabilità |
|---|---|---|
| **Inquadratura** | Vista iniziale dal polo sud: polo verso il centro, inclinazione di circa 25° per vedere il bordo e lo spazio. Pulsanti "Vista polo" ed "Emisfero intero" | Solo orientamento della camera e del gruppo; il modello non cambia |
| **Illuminazione** | Una luce direzionale "Sole" **radente**, quasi perpendicolare all'asse polare, alta pochi gradi rispetto al piano equatoriale. L'emisferica scende da 1,15 a circa 0,15, così la topografia della geometria produce ombre leggibili. Debole luce "terrestre" bluastra (`#5CCFE6` a 0,05–0,1) dal lato opposto per non avere nero assoluto. ACES ed esposizione da tarare con screenshot comparativi | **Illustrativa.** L'azimut reale del Sole sul globo richiederebbe il punto subsolare, che l'API non fornisce, e non si aggiunge nessun endpoint. Va dichiarato nella UI ("illuminazione indicativa") |
| **Texture** | Texture 8k esistente nel GLB, filtraggio anisotropo come oggi | Nessun nuovo asset |
| **Controlli** | Vendorizzare `OrbitControls.js` r186 da `node_modules` in `vendor/three/examples/jsm/controls/` (copia senza modifiche come in F0; il prefisso `/vendor/three/` lo serve già). Rotazione con smorzamento, zoom con limiti, nessun pan. **Tastiera:** frecce per ruotare, `+`/`−` per lo zoom, `Home` per tornare al polo. Rotazione automatica **disattivata** di default e sempre spenta con `prefers-reduced-motion` | Cambia il modello di interazione (oggi ruota il gruppo, OrbitControls muove la camera). I marker devono seguire la camera (§6, Marker) |
| **Marker dei siti** | Coordinate solo da `GET /api/sites` (vincolo F5). Proiezione lat/lon sulla sfera; il raggio locale si legge con un raycast sulla mesh, così il marker non "galleggia". Sono **pulsanti HTML sovrapposti**, posizionati a ogni frame dalla proiezione 3D → schermo: focusabili, con nome accessibile, cliccabili. Nascosti quando sono sul lato non visibile (prodotto scalare normale·camera < 0). Stile: cerchio di 10 px con filetto; il selezionato è ciano pieno con anello. Etichetta col nome del sito accanto | **Rischio di posizionamento:** la convenzione di longitudine della texture NASA va **verificata** prima del rilascio (§10). Finché non è verificata, la UI mostra "posizione indicativa". Vicino al polo l'errore in longitudine sposta poco Shackleton (−89,77°, ≈ 0,23° dal polo) e Connecting Ridge (−89,46°), ma molto Nobile (−85,44°, ≈ 4,6° dal polo; valori da `astronomy.SITES`) |
| **Selezione** | Click su un marker, su un elemento della lista o nel `<select id="site">` (sincronizzati): la camera vola al sito (600 ms, ease-out; immediato con reduced motion) e l'ispettore mostra la scheda del sito | `#site` resta la fonte di verità del valore, come oggi (`main.js` `update()`) |
| **Informazioni del sito** | Nome, lat/lon, data del calcolo, ultimo esito (finestre, % di visibilità simultanea da `summarize_ephemerides`), link "Calcola finestre" | Solo dati già restituiti dalle API |
| **Caricamento** | Avanzamento reale (`GLTFLoader` `onProgress`, 81,5 MB). Opzionale: mentre si carica il GLB, sfera provvisoria con `lunar_texture_preview.png` (2048×1024) | La sfera provvisoria richiede di servire un PNG: decisione D-F2 |
| **Alternativa accessibile** | Lista testuale dei siti nell'ispettore, equivalente ai marker. Il canvas ha `role="img"` e `aria-label` che descrive la vista | |
| **Prestazioni** | Rendering **on demand** (solo quando la camera si muove o c'è un'animazione) invece del loop continuo. Pausa con `document.hidden`. Pixel ratio ≤ 2 come oggi | Meno consumo; nessun cambio visivo |
| **Integrazione con i pannelli** | Lo stage non ha cornice: il globo "sborda" sotto la barra di stato e sotto la timeline semitrasparente (Antracite al 92 %). L'ispettore è un pannello solido separato da un filetto | |

**Esclusi** dalla proposta, perché fuori scope o non validati:

- proiezione di percorsi rover, orizzonti o raster sul globo: il frame GLB↔DEM non è validato (F4 §7);
- posizione reale del Sole o della Terra sul globo.

---

## 7. Organizzazione dei pannelli scientifici

| Sezione (sidebar) | Contenuto attuale | Riorganizzazione |
|---|---|---|
| **Siti** | `.left`: sito, inizio UTC, durata, soglie Sole e Terra, priorità scienza/ingegneria, pulsanti | Form in due gruppi: "Periodo" (inizio, durata) e "Soglie" (Sole, Terra). Le priorità vanno in un gruppo "Priorità (solo export)", perché **non sono usate nei calcoli** (audit §3.4): va detto. Azione primaria "Calcola le finestre" (`#apply`) |
| **Finestre operative** | Grafici `#chart1`/`#chart2`, analytics, tabella delle finestre | La timeline in basso mostra i dati. L'ispettore contiene: una riga di riepilogo (Sole: min/max e % sopra soglia; Terra: idem; simultanea), la **tabella delle finestre con pill GO** (inizio, fine, durata, elevazioni minime) e la diagnosi testuale (`#analyticsDiagnosis`) |
| **Comunicazioni** | RF link budget | Parametri in griglia con unità a destra del campo; risultato con il margine in evidenza e lo stato colorato (≥ 3 dB GO, 0–3 Attenzione, < 0 NO-GO) **solo se queste soglie sono già nel modulo**. Altrimenti si mostra solo il valore del margine (da verificare in `communications.py`, senza aggiungere soglie) |
| **Termica** | Parametri e `#thermalChart` | Stessa struttura; grafico restilizzato (§7.1) |
| **Terreno** (Science Tools) | `#scienceSection` | Selettore dello strumento come *segmented control* (`role="tablist"`); parametri dello strumento; risultato; **provenienza** (modulo, funzione, raster) sempre in fondo. Le coordinate di griglia sono etichettate "riga/colonna DEM" come oggi |
| **Qualità LROC** | `#lrocQualitySection` | La barra di distribuzione diventa l'elemento principale; le 4 classi in legenda con %, area e conteggio in tabella; l'avviso resta |
| **Mission Engine** | `#missionEngineSection` | Fasi **numerate** (qui la sequenza è reale): 1 Configurazione → 2 Validazione → 3 Esecuzione → 4 Risultati. Stato del job come pill. Risultati per step in tabella. Report e artifact come lista di download |
| **Report** | Export JSON client-side | Export e lista dei report (`#missionReports` resta in Mission Engine per i test; qui c'è un collegamento) |

### 7.1 Grafici

- **Canvas esistenti, solo restyling.** I colori si leggono dalle custom properties CSS (`getComputedStyle`), così grafici e UI condividono i token.
- **Assi:** testo secondario a 12 px con cifre tabulari; griglia `#323A44` a 1 px; orizzonte 0° come linea piena `#9AA6B2`; soglie tratteggiate del colore dell'astro.
- **Tracce:** Sole `#EAD9A7`, Terra `#5CCFE6`, spessore 1,5 px, nessun riempimento a gradiente.
- **Finestre GO:** bande verticali `#4CC38A` al 12 % con bordo superiore pieno.
- **Accessibilità:** ogni grafico ha accanto una tabella dei dati accessibile (`<details>` "Dati del grafico"), perché il canvas non è leggibile dagli screen reader.

---

## 8. Componenti da modificare e file

| Componente | File attuali | Tipo di intervento | Id e contratti da preservare |
|---|---|---|---|
| Token e base | `index.html` (`:root`, stili base) | Nuovo `tokens.css` + `base.css` | — |
| Shell: barra di stato, sidebar, stage, ispettore, timeline | `index.html` (`header`, `main`, `.left/.center/.right/.bottom`, splitter + script inline) | Nuova struttura HTML. Le sezioni esistenti vengono **spostate** nei contenitori nuovi senza rinominare id | Tutti gli id esistenti, in particolare `#missionSplitter` e `#changeProfile`. Le classi `.left/.center/.right/.bottom` sono usate dal CSS del profilo pubblico e da `main.js` (`liveStatus` con selettore `.right .metric:last-child…`): va sostituito con un id, con modifica minima e testata |
| Globo | `main.js` righe 1–143 | Luci, camera, OrbitControls, tastiera, render on demand, progress, reduced motion | Gli import `from 'three'` e `GLTFLoader` restano in `main.js` (test) |
| Marker e scheda del sito | Nuovo `globe-markers.js` (modulo ES importato da `main.js`) | Nuovo | `fetch('/api/sites'` resta in `main.js` (test F5); le coordinate passano al modulo come dati, mai come letterali |
| Grafici | `main.js` `drawEphemerisChart`, `drawThermalChart` | Solo colori e stile da token; timeline a tutta larghezza | `#chart1`, `#chart2`, `#thermalChart`; nessun `drawChart`/`charts()` |
| Analytics e finestre | `main.js` `renderMissionAnalytics`, `renderOperationalWindows` + HTML | Markup della tabella, pill GO | Id `#sunStats`, `#earthStats`, `#combinedPass`, … ; il messaggio "Analytics non forniti dal server" |
| RF e termica | `index.html` + `main.js` | Solo markup e CSS | `#calculateRF`, `#calculateThermal` e gli id dei campi |
| Science Tools | `index.html` `#scienceSection` + `science.js` | CSS; `role="tablist"` sul selettore (attributi ARIA, logica invariata) | `data-sci-tool`, `data-sci-pane`, tutti gli `#sci*` |
| Mission Engine | `index.html` `#missionEngineSection` + `mission.js` | CSS e markup delle fasi; logica di polling invariata | `#missionEngineSection`, `#missionReports`, `#mission*` |
| LROC | `index.html` + `main.js` `loadLrocQuality` | CSS | `#lroc*` |
| Profili | `index.html` (`#profileHome`, `#educatorHome`, `#publicMissionPanel`) + script inline profili | Markup e CSS; persistenza del profilo in `localStorage` (try/catch) | `[data-profile]`, `#educatorBack`, `#public*` |
| Copy | `index.html`, messaggi in `main.js`/`mission.js`/`science.js` | Italiano coerente, verbi d'azione | Le stringhe verificate dai test restano invariate |
| CSS morto | `.home-screen`, `#openHome`, `.home-*` | Rimozione (passo separato e reversibile) | — |
| Whitelist statica | `src/ui_web/app.py` `STATIC_ROUTES`/`CONTENT_TYPES` | **Solo se autorizzata (D-F1):** un prefisso `/ui/` per `src/ui_web/ui/**` limitato a `.css`, `.js`, `.woff2`, `.svg`, con la stessa protezione path-traversal del prefisso vendor, più i test | Nessun endpoint API toccato |

Nessuna modifica a `science_api.py`, `mission_runner.py`, ai moduli in `src/*.py`, ai dati o agli endpoint.

---

## 9. Modularizzazione e rollback per componente

### 9.1 Struttura dei file proposta

Richiede la decisione D-F1:

```
src/ui_web/
  index.html              ← solo markup + <link> ai fogli, importmap, <script> esistenti
  main.js                 ← globo + effemeridi (vincoli dei test)
  mission.js, science.js  ← invariati nella logica
  ui/
    tokens.css            ← palette, scala tipografica, spaziature (unica fonte)
    base.css              ← reset, tipografia, controlli, focus, reduced motion
    shell.css             ← barra di stato, sidebar, stage, ispettore, timeline, responsive
    globe.css             ← controlli della camera, marker, progress
    panels/
      sites.css  windows.css  comms.css  thermal.css
      science.css  lroc.css  engine.css  profiles.css
    globe-markers.js      ← marker DOM + proiezione + selezione
    fonts/Archivo[wdth,wght].woff2 (+ OFL.txt)
```

### 9.2 Regole

1. **Un componente = un file CSS = un `<link>` in `index.html`.** Per il rollback di un componente si commenta o si rimuove una riga, oppure si ripristina il file dal backup del passo.
2. **Selettori con prefisso per componente** (`.shell-…`, `.globe-…`, `.panel-windows …`) e nessun selettore di tipo globale fuori da `base.css`. Così si evitano le cascate che si annullano, come oggi con `main{…}` ridefinito 3 volte.
3. **Id invariati:** il JavaScript esistente continua a funzionare anche se un foglio viene rimosso. La UI degrada graficamente ma resta funzionante.
4. **Interruttore globale:** `<html data-ui="v2">`. Tutti i fogli nuovi sono scritti sotto `[data-ui="v2"]`. Tornare a `v1` richiede di ripristinare gli `<style>` inline originali dal backup UI-only, operazione che è un solo file (`index.html`).
5. **Un passo del piano (§11) = un backup datato** in `backups/F9_ui_<passo>_<timestamp>/` con `SHA256SUMS` + test + screenshot di confronto. Se l'utente autorizzerà i commit, ogni passo diventa un commit separato, quindi `git revert` per componente.
6. **Rollback totale:** `zstd -dc ui_original.tar.zst | tar -xf - src/ui_web` (backup F9). Per l'eventuale modifica alla whitelist si ripristina `app.py` dal backup completo.

---

## 10. Rischi tecnici e compatibilità

| Rischio | Impatto | Mitigazione |
|---|---|---|
| **D-F1: whitelist statica.** Fogli separati, font e moduli JS nuovi non vengono serviti senza aggiungere un prefisso a `app.py` | Senza questa modifica la modularizzazione del §9 non è possibile | Opzione A (consigliata): prefisso `/ui/` in sola lettura, estensioni limitate, test 404/traversal. Opzione B: tutto inline in `index.html` in blocchi `<style id="ui-…">` per componente e font di sistema. Rollback meno granulare, nessuna modifica al server |
| **Font offline.** Archivo va scaricato una volta (OFL) e servito in locale | Un nuovo asset di circa 100–150 KB | Richiede autorizzazione (nessuna dipendenza Python/npm). Fallback di sistema già definito |
| **Posizione dei marker** (convenzione di longitudine della texture NASA CGI Moon Kit, orientamento della mesh `Sphere`) | Un marker nel posto sbagliato è un errore scientifico visibile | Passo di validazione dedicato: reticolo lat/lon temporaneo + confronto visivo del bordo di Shackleton e di Nobile con la texture. Fino ad allora l'etichetta dice "posizione indicativa" |
| **Illuminazione illustrativa** scambiata per reale | Comunicazione fuorviante | Didascalia esplicita; nessun riferimento a date o effemeridi sul globo |
| **Test esistenti** su id e stringhe (§1.6) | Regressioni CI | Tabella dei vincoli come checklist; `pytest` a ogni passo |
| **Selettore fragile** `liveStatus` in `main.js` (`.right .metric:last-child …`) | Si rompe con il nuovo layout | Sostituirlo con un id, unica modifica logica non grafica, piccola e testata |
| **Splitter** (script inline legato alla griglia `main`) | Si rompe con il nuovo layout | Riusato per la timeline con lo stesso id e lo stesso ruolo ARIA; logica adattata alle nuove misure |
| **Prestazioni** GLB 81,5 MB, 2 milioni di vertici | Caricamento lento, GPU deboli | Progress reale, render on demand, pausa in background. La sfera provvisoria (D-F2) migliora la percezione |
| **Modalità `--desktop`** (QtWebEngine 6.12, basato su Chromium) | CSS moderno: `:has`, container query, `color-mix` | Supportati da Chromium recente; si usano solo con fallback, senza dipendere da `:has` per la logica |
| **Browser senza WebGL** | Globo assente | Messaggio esplicito nello stage + lista dei siti testuale: la UI resta usabile |
| **Profilo memorizzato** | Oggi la scelta del profilo appare sempre | Cambio di comportamento. Si memorizza in `localStorage` solo se l'utente lo approva; il pulsante "Cambia profilo" resta visibile |
| **Copy** | Le stringhe in inglese spariscono | Le stringhe richieste dai test restano; si aggiornano README e report |
| **Nessun test e2e con click** (Playwright assente) | Le regressioni d'interazione sfuggono | Screenshot Chromium headless a 4 larghezze per passo; Skill `run` / `claude-in-chrome` per click reali. Un parametro `?profile=planner` (solo frontend) permetterebbe screenshot di ogni profilo senza click |

---

## 11. Piano di implementazione

Ogni passo prevede: backup datato, modifica, `pytest`, screenshot a 1440/1024/768/390 px e confronto. I passi sono in ordine di dipendenza.

| # | Passo | Contenuto | Dipende da |
|---|---|---|---|
| 0 | Decisioni e baseline | D-F1 (whitelist), D-F2 (sfera provvisoria), D-F3 (profilo memorizzato), D-F4 (font). Screenshot baseline di tutti i profili | Autorizzazione |
| 1 | Infrastruttura | Prefisso `/ui/` + test (se D-F1 = A), cartella `ui/`, font, `tokens.css`, `base.css`, `data-ui="v2"` | 0 |
| 2 | Shell | Barra di stato con stati reali, sidebar, stage, ispettore, timeline + splitter, breakpoint, `liveStatus` con id | 1 |
| 3 | Globo | Camera polare, luce radente, OrbitControls vendorizzato, tastiera, render on demand, progress, reduced motion | 2 |
| 4 | Marker e scheda del sito | `globe-markers.js`, sincronizzazione con `#site`, volo della camera, **validazione della posizione** | 3 |
| 5 | Finestre operative | Timeline Sole/Terra con bande GO, tabella con pill, riepilogo, grafici da token | 2 |
| 6 | Pannelli tecnici | Comunicazioni, termica, Science Tools (tablist), LROC, Mission Engine (fasi) | 2 |
| 7 | Profili | Scelta del profilo, Pubblico, Educatore | 3, 4 |
| 8 | Copy e pulizia | Italiano coerente, verbi d'azione, rimozione del CSS morto | 2–7 |
| 9 | Qualità | `design:accessibility-review` (WCAG AA), `design:design-critique`, prova da tastiera, reduced motion, 4 larghezze, `--desktop` se c'è un display | 1–8 |
| 10 | Chiusura | Suite completa, aggiornamento di README e report F9 implementazione | 9 |

---

## 12. Stima dei tempi

| # | Parte | Stima |
|---|---|---|
| 0 | Decisioni e baseline | 0,5 h |
| 1 | Infrastruttura (whitelist + test, token, base, font) | 1,5–2 h |
| 2 | Shell e responsive | 3–4 h |
| 3 | Globo: camera, luci, controlli, prestazioni | 2–3 h |
| 4 | Marker, selezione, scheda del sito + validazione della posizione | 3–4 h |
| 5 | Finestre operative e grafici | 2–3 h |
| 6 | Pannelli tecnici (5 sezioni) | 3–4 h |
| 7 | Profili (scelta, Pubblico, Educatore) | 2–3 h |
| 8 | Copy e pulizia | 1–1,5 h |
| 9 | Accessibilità, critica, test visivi | 2–3 h |
| 10 | Chiusura, test, documentazione | 1–1,5 h |
| | **Totale** | **≈ 21–31 h (3–4 giornate)** |

Percorso minimo per una demo (passi 0–5 + 9 ridotto): circa 13–18 h.

---

## Decisioni richieste prima dell'implementazione

| Id | Decisione | Raccomandazione |
|---|---|---|
| **D-F1** | Aggiungere a `app.py` un prefisso statico `/ui/` (solo `.css/.js/.woff2/.svg`, con protezione traversal e test) | **Sì.** Abilita la modularizzazione e il rollback per componente. Non tocca API né contratti |
| **D-F2** | Servire `lunar_texture_preview.png` per una sfera provvisoria durante il caricamento | Facoltativo; utile in demo |
| **D-F3** | Memorizzare il profilo scelto (`localStorage`) | Sì, con "Cambia profilo" sempre visibile |
| **D-F4** | Scaricare e includere Archivo (OFL, ~100–150 KB woff2) | Sì; in alternativa font di sistema (meno identità) |
| **D-F5** | Vendorizzare `OrbitControls.js` r186 da `node_modules` (copia senza modifiche) | Sì; in alternativa si estendono i controlli attuali con tastiera |

## Verdetto: **PASS**

L'analisi copre struttura, CSS, JS, globo, API, asset, vincoli dei test e possibilità di modularizzazione. La proposta è definita in palette, tipografia, layout, globo, pannelli, file, rollback, rischi, piano e tempi.

Restano tre punti, che non impediscono la proposta:

- le **decisioni D-F1…D-F5**, che spettano all'utente;
- la **validazione della posizione dei marker**, prevista come passo esplicito (4);
- **lo screenshot della vista Pianificatore non è stato acquisito.** Senza click automatizzati non si apre; l'analisi di quella vista si basa sul codice.
