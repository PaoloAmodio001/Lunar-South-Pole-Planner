# F7 — Documentazione

Data: 2026-11-15 · Inizio 00:25:31 · Fine ≈ 00:28 · **Tempo impiegato ≈ 3 minuti** (limite 30)

## 1. Specifica originale e obiettivi

Fonte: `docs/technical_reports/WEB_UI_CONSOLIDATION_AUDIT_2026-11-14.md`.

- §8, riga F7: "README unico con solo `python src/ui_web/app.py`; vecchi README in `docs/history/`".
- §5: archiviare in `docs/history/` i file `README_V3…V10.md`, `README.txt`, `README_IMPLEMENTATION.md` e `IMPLEMENTATION_V11.md`. Il loro contenuto va unificato nel README.

| Obiettivo | Stato |
|---|---|
| README unico con un solo comando di avvio ufficiale | Fatto |
| Vecchi README archiviati in `docs/history/` | Fatto (11 file) |
| Requisiti, venv e installazione coerenti con F6 (browser, dev, desktop, legacy) | Fatto |
| Host, porta, `--no-browser`, `--desktop` e variabili d'ambiente | Fatto, verificati sul codice e con `--help` |
| Struttura del progetto e componenti | Fatto |
| Funzionalità scientifiche integrate (solo quelle PASS o integrate in F4) | Fatto |
| Dati inclusi e funzionamento offline | Fatto, con indicazione di cosa è verificato |
| Test | Fatto |
| Limitazioni note e funzionalità parziali (F4 e F5 = PARTIAL) | Fatto |

## 2. File

| File | Azione |
|---|---|
| `README.md` | Riscritto. Prima conteneva 2 righe (solo il titolo). |
| `README.txt`, `README_IMPLEMENTATION.md`, `README_V3.md`…`README_V10.md`, `IMPLEMENTATION_V11.md` | Spostati in `docs/history/` con `mv`, senza `git mv` per non toccare l'indice git. Contenuto invariato, verificato con SHA-256. |
| `reports/web_ui_consolidation/F7_DOCUMENTATION.md` | Nuovo (questo report) |

Backup dei 12 file prima delle modifiche: `backups/f7_documentation_20261115-002610/`, con il file `SHA256SUMS`.
La verifica `sha256sum -c` sugli 11 file spostati risulta tutta OK.

Non ho modificato codice, configurazioni, dati, requirements o i report F0–F6.

## 3. Contenuti del README

1. **Avvio rapido**: venv, `pip install -r requirements.txt`, `python src/ui_web/app.py`.
2. **Requisiti**: Python 3.14, l'unica versione verificata; browser con WebGL; rete per Horizons; npm non necessario.
3. **Installazione**: tabella dei quattro file requirements definiti in F6.
4. **Avvio**:
   - opzioni `--host`, `--port`, `--no-browser`, `--desktop`;
   - variabili `LUNAR_UI_HOST`, `LUNAR_UI_PORT`, `LUNAR_UI_NO_BROWSER`;
   - codici di uscita 2 (porta occupata) e 3 (`--desktop` senza PySide6);
   - avviso per host non loopback.
5. **Interfaccia**:
   - i tre profili, con i nomi reali della pagina;
   - globo, effemeridi, comunicazioni, termica, qualità LROC, Mission Engine;
   - Science Tools, con endpoint e modulo per ciascuno;
   - CLI dell'orchestratore.
6. **Dati**: inclusi nel repository, catalogo fisso e funzionamento offline (cosa funziona senza rete e cosa no).
7. **Struttura del progetto** e **interfacce legacy** (destinate a F8).
8. **Test**: comando e ultimo risultato (410 passed, F6).
9. **Limitazioni note**: residui di F4 e F5, orizzonte lento, percorsi assoluti, `--desktop` non provato, nessun test e2e, nessuna autenticazione.

Funzionalità dichiarate **non** integrate perché F4 o F5 sono PARTIAL:

- scoring sito DEM + effemeridi;
- analisi locale per sito;
- diagnostica di illuminazione;
- ranking finestre;
- multi-rover/P-System;
- proiezione dei risultati sul globo 3D;
- effemeridi offline;
- export lato server;
- unificazione della ricerca finestre.

## 4. Comandi e affermazioni verificati

| Verifica | Risultato |
|---|---|
| `python src/ui_web/app.py --help` | Opzioni `--host`, `--port`, `--no-browser`, `--desktop` presenti |
| Variabili d'ambiente e valori predefiniti | Confermati in `parse_args()` (`app.py`) |
| Porta occupata (seconda istanza su 8765) | Messaggio con la porta alternativa, `exit=2` |
| `--desktop` senza PySide6 → exit 3 | Verificato in F6 (venv pulito) |
| `python -m src.mission_orchestrator --help` | Usage `config` confermato |
| Endpoint citati | Presenti in `app.py` e `science_api.py` |
| Nomi dei profili | Letti da `index.html` (PUBBLICO, EDUCATORE, PIANIFICATORE DI MISSIONE) |
| Catalogo config del Mission Engine | Solo `example` (`mission_runner.CONFIG_CATALOG`) |
| Step disabilitati nella configurazione di esempio | `astronomy=false`, `illumination=false` (letti dal JSON) |
| 2 calcoli contemporanei nei Science Tools | `BoundedSemaphore(2)` in `science_api.py` |
| Percorsi e file citati nel README | Tutti esistenti (49 controllati, nessuno mancante) |
| Riferimenti ai vecchi README nel codice | Nessuno: lo spostamento non rompe import né test |

## 5. Punti non completati

1. **Mission Engine offline.** Il funzionamento senza rete con la configurazione di esempio è dedotto dalla configurazione (step di rete disabilitati), non provato con la rete scollegata. Il README lo dichiara.
2. **Test non rieseguiti.** In F7 non ho rieseguito i test: ho modificato solo documentazione e spostato file `.md`/`.txt` non referenziati. Il README riporta il risultato F6 (410 passed).
3. **`SCIENCE_STATUS.txt` obsoleto.** Il file in radice è superato (dice "da implementare" per pendenze, orizzonte e simili, che ora sono integrati). Non è elencato nella specifica F7 e non l'ho toccato. Va valutato se archiviarlo in `docs/history/`.
4. **Spostamenti non registrati da git.** Con `mv` git vede 11 file eliminati e la cartella `docs/` non tracciata. Al momento del commit va aggiunto `docs/history/` in modo esplicito.
5. **README storici.** Il loro contenuto utile (moduli scientifici, funzioni Tkinter) è riassunto nel README solo per la parte oggi valida. I dettagli restano consultabili in `docs/history/`.

## 6. Verdetto

**PASS.** Gli obiettivi della specifica F7 sono raggiunti: README unico con il solo comando ufficiale e vecchi README archiviati in `docs/history/`. I comandi e i percorsi documentati sono verificati, e le funzionalità parziali sono dichiarate come tali.
