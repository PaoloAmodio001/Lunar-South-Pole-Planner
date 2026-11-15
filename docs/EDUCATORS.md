# Sezione Educatori (pubblica)

Profilo «Educatore» della homepage `/`: nessun login, nessuna registrazione, nessun dato personale.
Le uniche preferenze salvate (capitolo e livello) restano nel `localStorage` del browser
(`lspp.edu.chapter`, `lspp.edu.level`).

## File

| File | Ruolo |
|------|-------|
| `src/ui_web/index.html` → `<section id="educatorHome">` | Contenuti: 7 capitoli, figure SVG inline |
| `src/ui_web/ui/educator.css` | Stili, tutti confinati in `#educatorHome`, solo token di `tokens.css` |
| `src/ui_web/ui/educator.js` | Navigazione, livelli, laboratori, stampa |

Nessuna modifica a `app.py`, autenticazione, database utenti o sezione Pianificatori:
`/ui/educator.*` è servito dalla rotta statica esistente `/ui/`.

## Capitoli

1. Perché esistono gli educatori di missione
2. Perché esplorare il polo sud (badge: Confermato / Da verificare / Obiettivo di programma)
3. Le sfide (9 schede, schemi Sole radente e librazione, calcolatore dell'ombra)
4. Laboratori interattivi (banco di prova live, laboratori 1–5, matrice decisionale)
5. Percorsi formativi (6 pubblici; il pulsante imposta il livello)
6. Attività pratiche (A1–A4 + rubrica di valutazione, stampabili)
7. Cooperazione e futuro (fonti ufficiali)

Livelli: `data-level` su `#educatorHome` (1 Base, 2 Intermedio, 3 Avanzato); gli elementi con
`data-level-min="2|3"` compaiono solo dal livello indicato.

## Riuso del motore di calcolo

I laboratori **non** duplicano calcoli astronomici:

- `/api/sites` (pubblica) → schema polare, matrice decisionale, scheda di lavoro.
- `/api/ephemerides` (pubblica, NASA/JPL Horizons) → banco di prova: si leggono solo
  `analytics.sun|earth|simultaneous.passing_percent`, `analytics.operational_windows`,
  `observations` (per i mini-grafici) e `thresholds`.
- «Apri nel 3D» precompila il pannello dell'Esploratore pubblico (`#publicDate`, `#publicDuration`,
  soglie, `.public-site`), attiva il profilo Pubblico tramite la card esistente e avvia `#publicAnalyze`.

La sezione non chiama API protette (`/api/mission/`, `/api/science/`, `/api/terrain/`, ...).
Sicurezza e interesse scientifico nella matrice sono valutazioni degli studenti, dichiarate come tali.

## Rollback

Ripristinare `index.html` dal backup `backups/educator-section-20261115-124319/` e rimuovere
`src/ui_web/ui/educator.css` e `src/ui_web/ui/educator.js`.
