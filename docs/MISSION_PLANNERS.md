# Mission Planners — architettura, autenticazione e avvio

Ultimo aggiornamento: 2026-11-15

La piattaforma è pubblica. L'unica sezione riservata è **Pianificatori di missione**
(dashboard **MISSION PLANNERS**, `/dashboard`), protetta da **un unico sistema di login**
(`src/ui_web/auth.py`). Comprende **Lunar Mission Control Planner** (`/mission-control`);
eventuali altri pianificatori aggiunti alla sezione vanno protetti dallo stesso login,
aggiungendo i loro percorsi a `PROTECTED_PATHS`/`PROTECTED_PREFIXES` in `src/ui_web/app.py`.

Homepage, profili Pubblico ed Educatore e le API che usano restano accessibili senza account.

> Il 2026-11-15 è stato rimosso **Lunar Site Explorer** (copia importata da
> `ReetzZz/Lunar-south-pole-planner`, gateway sulla porta 8766, login del progetto
> importato). Backup completo in `backups/single-auth-remove-explorer-20261115-122831/`.

## Avvio

```bash
./start.sh                 # controlla venv e dipendenze, avvia il server
./start.sh --no-browser    # gli argomenti passano a src/ui_web/app.py
```

Parte un solo processo, il server su `127.0.0.1:8765`, che serve la piattaforma
pubblica, la sezione riservata e le API. Il browser apre `http://127.0.0.1:8765/`.

| Opzione | Variabile | Effetto |
|---|---|---|
| `--port` | `LUNAR_UI_PORT` | Porta del server (predefinita 8765) |
| `--host` | `LUNAR_UI_HOST` | Indirizzo di ascolto (predefinito 127.0.0.1) |
| `--no-browser` | `LUNAR_UI_NO_BROWSER=1` | Non apre il browser |

Il server resta in primo piano. Se si chiude il terminale, la piattaforma si
ferma. Le pagine già aperte mostrano allora "backend non raggiungibile" e
riprendono da sole quando il server torna attivo.

## Rotte (porta 8765)

La protezione è applicata **lato server** in `Handler.require_session`
(`is_protected_path`), prima di servire pagine o API.

| Percorso | Accesso | Contenuto |
|---|---|---|
| `/`, `/index.html` | pubblico | Homepage, profili Pubblico/Educatore, globo. Il profilo Pianificatore porta a `/dashboard` |
| `/login`, `POST /auth/login`, `POST /auth/setup` | pubblico | Pagina di accesso, invio credenziali, primo amministratore (solo con archivio vuoto) |
| `POST /auth/logout` | pubblico | Revoca la sessione (se presente) e riporta a `/` |
| `/api/health` | pubblico | `{"backend":"ok","authenticated":…}`, nessun dato scientifico |
| `/api/sites`, `/api/ephemerides` | pubblico | API della piattaforma pubblica |
| `/api/services` | pubblico, dettagli con sessione | Backend e JPL Horizons (cache 60 s; `refresh=1` e dati di sessione solo con sessione) |
| `/ui/*`, `/vendor/three/*`, script, modello 3D | pubblico | Asset statici della whitelist |
| `/dashboard` | **sessione** | Ingresso della sezione Pianificatori di missione e stato dei servizi |
| `/mission-control` | **sessione** | Lunar Mission Control Planner |
| `/api/auth/session` | **sessione** | Utente della sessione |
| `/api/mission/*`, `/api/science/*`, `/api/communications/*`, `/api/thermal/*`, `/api/terrain/*` | **sessione** | API dei pianificatori (Mission Engine, strumenti scientifici, link budget, termica, report LROC) |

Senza sessione valida, solo sui percorsi riservati:

- le pagine reindirizzano a `/login?next=…` e, dopo l'accesso, tornano alla pagina richiesta;
- le API rispondono `401` con `error_code` uguale a `auth_required` o `session_expired`.

`src/ui_web/session.js` riporta al login (avviso "sessione scaduta") solo nelle
pagine riservate `/dashboard` e `/mission-control`; nella piattaforma pubblica non
reindirizza mai e mostra il pulsante **Esci** solo con una sessione attiva.
`mission.js`, `science.js` e il pannello LROC di `main.js` interrogano le API
riservate solo in `/mission-control`.

## Autenticazione

Modulo: `src/ui_web/auth.py`. Gestione utenti: `src/ui_web/auth_admin.py`.
Usa solo la libreria standard Python: nessuna dipendenza aggiunta.

- **Nessuna credenziale predefinita.** Finché l'archivio utenti è vuoto, `/login` mostra solo il modulo **Crea account amministratore** (nome utente, password, conferma). Il modulo invia a `POST /auth/setup`, che:
  - funziona solo con archivio vuoto; dopo il primo account reindirizza al login senza creare nulla;
  - verifica e scrive sotto un lock esclusivo (thread + `flock` su `users.lock`), quindi richieste concorrenti non possono creare due amministratori;
  - non sovrascrive mai un `users.json` presente ma illeggibile;
  - richiede `Origin` valido e un token CSRF double-submit (cookie `lmc_setup_csrf`, `HttpOnly`, `SameSite=Strict`, `Path=/auth/setup`, 30 minuti);
  - valida lato server nome utente, lunghezza password, conferma e password diversa dal nome;
  - dopo la creazione apre una sessione con il normale `AuthManager.login`.

  Il primo account non si può creare da terminale: `auth_admin.py add-user` funziona solo quando esiste già un account.
- **Password.** Sono salvate solo come hash `scrypt` (N=2¹⁵, r=8, p=1, sale casuale di 16 byte). Il confronto avviene a tempo costante. La lunghezza minima è di 12 caratteri.
- **Archivio fuori dal repository.** Si trova in `$LUNAR_AUTH_DIR` oppure in `~/.config/lunar-mission-control/`:
  - `users.json`: utenti;
  - `sessions.json`: solo lo SHA-256 dei token, mai i token stessi.

  Directory con permessi `0700`, file con `0600`.
- **Cookie di sessione.** Il cookie `lmc_session` ha gli attributi `HttpOnly`, `SameSite=Strict` e `Path=/`. Con `LUNAR_COOKIE_SECURE=1` (dietro HTTPS) si aggiunge `Secure`. Il JavaScript non vede mai token o password.
- **Scadenze.**
  - Inattività: 30 minuti (`LUNAR_SESSION_IDLE_MINUTES`).
  - Assoluta: 12 ore (`LUNAR_SESSION_MAX_HOURS`).

  Le sessioni sopravvivono al riavvio del server. Il cambio password o la rimozione dell'utente le invalidano subito.
- **Limite dei tentativi.** Dopo 5 errori in 15 minuti, l'indirizzo IP e il nome utente vengono bloccati per 15 minuti.
- **CSRF.** Le richieste `POST` sono accettate solo se l'header `Origin` corrisponde alla piattaforma.

### Gestione utenti

```bash
python src/ui_web/auth_admin.py add-user <nome>     # aggiunge un utente (non il primo); password senza eco
python src/ui_web/auth_admin.py passwd <nome>       # cambia la password e revoca le sessioni
python src/ui_web/auth_admin.py remove-user <nome>  # rimuove l'utente
python src/ui_web/auth_admin.py revoke <nome>       # chiude le sessioni dell'utente
python src/ui_web/auth_admin.py list | where
```

Per le installazioni automatizzate esiste `--password-stdin`. La password non
va mai passata come argomento.

## Stati degli errori delle effemeridi

| Situazione | Backend → UI | Stato mostrato |
|---|---|---|
| Processo Python spento o connessione interrotta | fetch rifiutata (in Firefox: `NetworkError`) | `BACKEND OFFLINE`. Nuova verifica ogni 5 s e nuova richiesta automatica quando il backend torna. |
| JPL non risponde in tempo | 504 `jpl_timeout` | `JPL UNAVAILABLE`. Verifica ogni 60 s e nuova richiesta automatica quando JPL torna. |
| DNS o rete del server verso JPL | 503 `jpl_unreachable` | `JPL UNAVAILABLE`, come sopra |
| JPL risponde con un errore HTTP | 502 `jpl_http_error` | `JPL UNAVAILABLE`, come sopra |
| JPL segnala un errore nella richiesta | 502 `jpl_rejected` | `INVALID DATA` |
| Risposta non JSON o senza blocco di effemeridi | 502 `jpl_invalid_response` | `INVALID DATA` |
| Parametri non validi | 400 `invalid_request` | `ERROR` |
| Sessione scaduta | 401 `session_expired` | ritorno al login |
| Dati disponibili | 200 | `CONNECTED · JPL` |

In nessun caso vengono mostrati dati astronomici dimostrativi.
