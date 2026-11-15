# F9 — Backup completo e inventario delle Claude Skills

Data: 2026-11-15 · 00:41:54 → 00:45 (≈ 4 minuti)
Nessuna modifica a codice, grafica o configurazioni. Nessuna Skill o dipendenza installata. Nessun commit o push.
L'unico file creato nel progetto è questo report.

## VERDETTO: **PASS**

Ho creato e verificato due backup fuori dal progetto: uno completo e uno della sola UI. Ciascuno è stato estratto in una directory temporanea e confrontato con il manifest SHA-256, senza differenze.
L'inventario delle Skills è nella parte B.

---

# A. BACKUP

## A.1 Posizione e contenuto

Cartella del backup: **`~/Lunar-South-Pole-Planner_backups/F9_20261115-004220/`**, fuori dalla directory del progetto, sullo stesso disco (47 GB liberi).

| File | Dimensione | Contenuto |
|---|---|---|
| `project_full.tar.zst` | **3,1 GB** (3 312 911 110 byte) | Progetto completo, **1574 file** (≈ 3,4 GB non compressi) |
| `ui_original.tar.zst` | **35 MB** | UI originale, **1286 file** |
| `FILELIST_full.txt` / `FILELIST_ui.txt` | 96 KB / 88 KB | Elenco dei file |
| `SHA256SUMS_full.txt` / `SHA256SUMS_ui.txt` | 196 KB / 172 KB | Manifest SHA-256 di ogni file |
| `SHA256SUMS_archives.txt` | 4 KB | Hash dei due archivi |
| `RESTORE.md` | — | Istruzioni di ripristino completo e selettivo |

Hash degli archivi:

```
f8d824e139499bef65a1f14c7aa014bd6398a2439b4adad265e71f5427d78473  project_full.tar.zst
910a6072f20994301b253205063c2a93a948354a0fd2c76437ba181aadd94f8e  ui_original.tar.zst
```

Formato: `tar` compresso con zstd (livello 3, multithread). Gli archivi conservano permessi e date dei file.

## A.2 Backup completo: cosa include

Il backup include tutto il contenuto della directory del progetto, a prescindere da come lo classifica git, tranne le esclusioni elencate in A.3. In particolare:

- **File tracciati modificati:** `README.md`, `requirements.txt`. Lo stato delle eliminazioni e degli spostamenti F7/F8 è conservato tramite `.git/`.
- **File non tracciati:** `legacy/`, `docs/` (con `docs/history/` e `docs/technical_reports/`), `requirements-{dev,desktop,legacy}.txt`, i report F6–F8, `audit-reports/`, `reports/astronomical_orientation/`, `reports/end_to_end_audit/`, `reports/site_identity_validation/`, `data/terrain/processed/lroc_quality/` e `scripts/*.py` non tracciati.
- **Dati scientifici e risorse 3D:** tutto `data/` (727 MB: DEM LOLA, LROC, kernel SPICE, GLB del globo, `data/models/nasa/`), `de421.bsp`, `mission_config*.json`.
- **Repository git:** `.git/` (996 MB). In una copia estratta, `git status` mostra le stesse 45 voci del progetto (verificato).
- **Backup precedenti e archivi storici:** `backups/` (1,5 GB) e i circa 22 archivi `*.tar.gz` in radice (143 MB).
- **File ignorati da git ma presenti:** ad esempio `reports/web_runs/` e i file spuri `json`, `sys`, `np`, `rasterio`. Li ho inclusi perché non sono cache.

## A.3 Esclusioni (solo cache e ambienti rigenerabili)

| Esclusione | Dimensione | Perché si può escludere | Come rigenerarla |
|---|---|---|---|
| `.venv/` | 1,6 GB | Ambiente Python | `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt` (+ `requirements-desktop.txt` / `-legacy.txt` se servono) |
| `src/ui_web/node_modules/` | 23 MB | Pacchetti npm, non usati a runtime: three.js è già in `src/ui_web/vendor/three/` | `cd src/ui_web && npm ci` (c'è `package-lock.json`). **È comunque incluso nel backup della UI.** |
| `__pycache__/` (406 cartelle) | 72 MB | Bytecode Python | Python lo ricrea da solo |
| `.pytest_cache/` | piccola | Cache di pytest | pytest la ricrea da solo |

Nel progetto non ci sono link simbolici. Non ho trovato altre cache (`.mypy_cache`, `.ruff_cache`, `*.egg-info`, `.ipynb_checkpoints`).

## A.4 Backup della UI originale

Contenuto di `ui_original.tar.zst`:

- **`src/ui_web/` completo:**
  - `index.html`: HTML con **tutto il CSS inline** (non ci sono file `.css` separati);
  - `main.js`, `mission.js`, `science.js`;
  - i 5 file `main.js.before-*`;
  - `app.py`, `mission_runner.py`, `science_api.py`;
  - `package.json` e `package-lock.json`;
  - `vendor/three/` (three.js vendorizzato);
  - `node_modules/` (1264 file).
- **Risorse grafiche:** `data/terrain/global/Moon_NASA_LRO_8k_Topo_Small.glb`, l'unica risorsa grafica esterna caricata dalla UI (whitelist `STATIC_ROUTES` in `app.py`).

La UI non usa file separati per immagini, icone o font: i simboli dei profili sono caratteri Unicode in `index.html`.
`legacy/ui/`, la vecchia pagina Plotly, è nel backup completo.

## A.5 Verifica SHA-256

| Verifica | Risultato |
|---|---|
| Backup completo: estrazione in `~/Lunar-South-Pole-Planner_backups/F9_20261115-004220.verify_tmp` + `sha256sum -c SHA256SUMS_full.txt` | **1574/1574 OK**, file estratti = 1574 |
| Presenza di file chiave nella copia estratta: `legacy/tkinter/main.py`, `docs/history/README_V3.md`, `requirements-legacy.txt`, report F8, DEM Site04, `de421.bsp`, GLB, `.git/HEAD`, three.js | Tutti presenti |
| `git status --short` nella copia estratta | 45 voci, come nel progetto |
| Backup della UI: estrazione temporanea + `sha256sum -c SHA256SUMS_ui.txt` | **1286/1286 OK** |

Dopo la verifica ho rimosso le directory temporanee di estrazione: le avevo create io e contenevano solo copie.

## A.6 Ripristino

La procedura completa, con i comandi, è in **`~/Lunar-South-Pole-Planner_backups/F9_20261115-004220/RESTORE.md`**. In sintesi:

1. **Verifica degli archivi:** `sha256sum -c SHA256SUMS_archives.txt`.
2. **Ripristino completo in una nuova cartella** (consigliato): `zstd -dc project_full.tar.zst | tar -xf - -C <nuova cartella>`, poi `sha256sum -c`, ricreazione del venv e `pytest` (atteso: 410 passed).
3. **Ripristino completo al posto del progetto:** prima si rinomina la cartella attuale (`mv … .prev-<data>`), poi si estrae.
4. **Ripristino selettivo:** `zstd -dc project_full.tar.zst | tar -xf - ./<percorso>`. Nel backup completo i percorsi iniziano con `./`; si controllano in `FILELIST_full.txt`.
5. **Ripristino della sola UI:** prima una copia di sicurezza di `src/ui_web`, poi `zstd -dc ui_original.tar.zst | tar -xf - src/ui_web[/file]`. In questo archivio i percorsi **non** hanno il prefisso `./`.

---

# B. CLAUDE CODE SKILLS

## B.1 Dove si trovano

| Posizione | Esito |
|---|---|
| Progetto: `~/Lunar-South-Pole-Planner/.claude/skills/` | **Non esiste.** Nessuna Skill di progetto e nessuna directory `.claude/` |
| Utente: `~/.claude/skills/` | Contiene solo `synced/…/morning` (skill `anthropic-skills:morning`) |
| Plugin sincronizzati dall'account: `~/.claude/plugins/synced/…` | Plugin **attivi** in questa sessione: design, engineering, vercel, ngrok, 21st, omniout, you, mattpocock-skills e altri |
| Marketplace: `~/.claude/plugins/marketplaces/claude-plugins-official/` | Catalogo **scaricato ma non installato**. Nessun `installed_plugins.json` e nessun `enabledPlugins` in `~/.claude/settings.json`; queste Skills non risultano caricate nella sessione |
| Skills integrate in Claude Code (`run`, `claude-in-chrome`, `code-review`, `simplify`, `dataviz`, `artifact-design`, …) | Disponibili nella sessione. I loro SKILL.md non sono su disco: fanno parte del prodotto |

In totale su disco ci sono 199 file `SKILL.md`, considerando sia i plugin attivi sia il catalogo.

## B.2 Skills rilevanti, per area

"Disponibile" significa che la Skill compare nell'elenco delle Skills caricate in questa sessione e si può invocare subito.

### UI/UX e design

| Skill | Disponibile | Istruzioni (dal SKILL.md) | Utilità per il restyling |
|---|---|---|---|
| `design:design-critique` | ✅ | Feedback strutturato su usabilità, gerarchia e coerenza; input: URL, screenshot o descrizione | **Alta.** Critica della UI attuale prima e dopo il restyling |
| `design:design-system` | ✅ | `audit`, `document`, `extend`: incoerenze di naming, valori hardcoded, documentazione di varianti e stati | **Alta.** Audit del CSS inline (colori, spaziature, token) |
| `design:design-handoff` | ✅ | Specifiche di sviluppo: layout, design token, stati di interazione, **breakpoint responsive** | Media. Utile per fissare le specifiche prima di implementare |
| `design:ux-copy` | ✅ | Microcopy, messaggi d'errore, empty state, CTA | Media. Testi della UI in italiano |
| `design:user-research`, `design:research-synthesis` | ✅ | Pianificazione e sintesi della ricerca utente | Bassa per il restyling |
| `frontend-design` (plugin ufficiale) | ❌ **Non installato** | Direzione estetica, tipografia, scelte non "templated" | Sarebbe alta, ma serve un'**autorizzazione** per installarlo |
| `playground` (plugin ufficiale) | ❌ **Non installato** | Playground HTML interattivi per scegliere colori, layout e tipografia | Media; richiede installazione |
| `21st:21st-ui` | ✅ | Componenti **React/Tailwind** (shadcn) da 21st.dev tramite MCP | **Non adatta.** La UI è HTML/JS vanilla senza React né Tailwind |
| `vercel:shadcn`, `vercel:react-best-practices` | ✅ | shadcn/ui, controlli su file TSX | **Non adatte**, per lo stesso motivo |
| `artifact-design` | ✅ | Design di Artifact claude.ai | Non adatta alla UI del progetto. Utile solo per mockup o anteprime pubblicate come Artifact |

### CSS e responsive

Nessuna Skill è dedicata specificamente a CSS o al responsive design.

- `design:design-system` (audit dei valori hardcoded) e `design:design-handoff` (breakpoint responsive) coprono parte dell'esigenza.
- `frontend-design` coprirebbe la parte estetica, ma non è installata.

### Three.js / WebGL

**Nessuna Skill disponibile né presente nel catalogo** per three.js o WebGL. Per la documentazione aggiornata di three.js 0.186 è disponibile il server MCP **Context7** (strumenti `resolve-library-id` e `query-docs`), che non è una Skill.

### Accessibilità

| Skill | Disponibile | Istruzioni |
|---|---|---|
| `design:accessibility-review` | ✅ | Audit **WCAG 2.1 AA**: contrasto, navigazione da tastiera, touch target, screen reader. Input: URL, Figma o descrizione |

### Testing e verifica

| Skill | Disponibile | Istruzioni | Note per questo progetto |
|---|---|---|---|
| `engineering:testing-strategy` | ✅ | Piramide dei test e strategia per tipo di componente | Per pianificare test della UI |
| `mattpocock-skills:tdd` | ✅ | Red-green-refactor, test di integrazione | Per i test pytest della Web UI |
| `run` | ✅ | Avvia l'app e la guida per vedere una modifica funzionante | Utile per verificare il restyling con `python src/ui_web/app.py` |
| `claude-in-chrome` / `anthropic-skills:chrome-browser` / `anthropic-skills:built-in-browser` | ✅ | Automazione del browser: click, screenshot, console | Utili per controlli visivi e click reali. `claude-in-chrome` richiede l'estensione e i permessi per il sito |
| `vercel:verification` | ✅ | Verifica end-to-end browser → API → dati | Pensata per dev server Next/Vite; utile solo come checklist |
| `mattpocock-skills:prototype` | ✅ | Prototipo usa-e-getta per esplorare l'aspetto della UI | Per varianti di layout prima di toccare `index.html` |
| `code-review`, `simplify` | ✅ | Revisione del diff; pulizia del codice | Dopo il restyling |
| `mattpocock-skills:diagnosing-bugs` | ✅ | Ciclo di diagnosi | Per regressioni visive o di funzionamento |

Strumenti presenti sul sistema, senza installare nulla: `/usr/bin/chromium`, `google-chrome`, `firefox`, `node`, `npm` e `npx`.
**Playwright non è installato**: non ci sono test end-to-end con click simulati, come già segnalato in F1, F3 e F4.

## B.3 In sintesi: cosa si può usare subito per il restyling

1. **Analisi:** `design:design-critique`, `design:design-system audit`, `design:accessibility-review`.
2. **Specifica:** `design:design-handoff` (token e breakpoint), `design:ux-copy`.
3. **Implementazione:** nessuna Skill specifica per HTML/CSS vanilla o three.js. Si lavora direttamente, con Context7 per la documentazione di three.js.
4. **Verifica:** `run` + `claude-in-chrome` o `chrome-browser` (screenshot e click), `engineering:testing-strategy`, `mattpocock-skills:tdd`, poi `code-review`.

**Richiedono autorizzazione** (non installati): il plugin `frontend-design`, il plugin `playground` ed eventualmente Playwright come dipendenza di sviluppo.

---

## C. Problemi e note

1. **Il backup completo è nella stessa unità del progetto** (`/dev/nvme0n1p2`). Per proteggersi da un guasto del disco va copiato su un supporto esterno, ad esempio con `rsync -a ~/Lunar-South-Pole-Planner_backups/F9_20261115-004220 /media/...`.
2. **Il backup completo pesa 3,1 GB**, in gran parte backup e archivi storici (`backups/` 1,5 GB, `.git/` 1 GB). Li ho inclusi perché la richiesta escludeva solo cache e ambienti rigenerabili.
3. **`node_modules/`** è escluso dal backup completo ma incluso in quello della UI, così lo stato npm originale è comunque conservato.
4. **Stato non committato:** il backup fotografa lo stato attuale, comprese le modifiche F4–F8 non committate. Non sostituisce un commit.
5. **Skills integrate:** i loro SKILL.md non sono su disco; ne riporto le istruzioni come le descrive la sessione.
6. **Nessuna Skill per three.js, CSS o responsive:** il restyling del globo e del layout dovrà basarsi su competenze generali e sulla documentazione di Context7.
