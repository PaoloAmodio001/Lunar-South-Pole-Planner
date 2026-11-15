# legacy/ — componenti archiviati (fase F8)

L'**unica interfaccia ufficiale** è **`python src/ui_web/app.py`**.

Questa cartella contiene interfacce, visualizzatori e script legacy, conservati **solo per consultazione e recupero**.
**Nessuno è un entrypoint ufficiale** e nessuno è usato dalla Web UI, dal Mission Engine o dai test.
I file sono stati **spostati, non cancellati**, il 2026-11-15. Il contenuto è identico all'originale, verificato con SHA-256.

Specifica: `docs/technical_reports/WEB_UI_CONSOLIDATION_AUDIT_2026-11-14.md`, §5 e §8.
Report: `reports/web_ui_consolidation/F8_LEGACY_DECOMMISSIONING.md`.

## Contenuto

| Percorso attuale | Posizione originale | Componente |
|---|---|---|
| `tkinter/main.py` | `main.py` | Interfaccia Tkinter (ex `python main.py`) |
| `tkinter/lunar_native_viewer.py` | `src/lunar_native_viewer.py` | Viewer trimesh del GLB NASA, lanciato da `main.py` (pulsante "Luna NASA 3D") |
| `streamlit/app.py` | `app.py` | Interfaccia Streamlit (ex `streamlit run app.py`) |
| `panda3d/lunar_mission_3d.py` | `src/lunar_mission_3d.py` | Viewer Panda3D (ex `python -m src.lunar_mission_3d`) |
| `viewers/lunar_3d_app.py` | `src/lunar_3d_app.py` | Esploratore Plotly → HTML |
| `viewers/lunar_globe_3d.py` | `src/lunar_globe_3d.py` | Globo Plotly statico |
| `ui/` | `ui/` | Pagina e `model-viewer.min.js` di `lunar_3d_app.py` |
| `panda3d_model_checks/test_*_models.py` | radice | Script di prova Panda3D (non test pytest) |
| `patch_scripts/rebuild_lunar_ui.py`, `correggi_lunar_visual.py` | radice | Patch-script storici su `src/lunar_mission_3d.py` |
| `patch_scripts/install_*.py` | radice | Patch-script storici su `src/ui_web/index.html` |

Backup prima dello spostamento:

- `backups/f8_legacy_20261115-003023/`: viewer Plotly, `ui/`, script;
- `backups/f8b_legacy_20261115-003555/`: Tkinter, Streamlit, Panda3D, trimesh.

Ogni cartella contiene un archivio `.tar` e il file `SHA256SUMS`.

## Funzionalità NON migrate nella Web UI

Le funzioni seguenti esistevano solo in questi componenti. **Non sono disponibili nella Web UI** e non vanno presentate come tali.

| Funzione | Dove era disponibile | Stato |
|---|---|---|
| Scoring del sito con DEM + effemeridi (`site_assessment`, `mission_planning.score_site`) | Tkinter | Il modulo resta in `src/`; nessun endpoint Web |
| Diagnostica di illuminazione diretta (`illumination_analysis`) | Tkinter | Solo tramite configurazione del Mission Engine |
| Analisi locale per sito (LDEC/TOTERR) | — | Solo tramite configurazione del Mission Engine |
| Multi-rover e journal P-System | Tkinter | Solo tramite configurazione del Mission Engine |
| Viewer nativo del GLB NASA (trimesh) | Tkinter | Non migrato; la Web UI ha il proprio globo three.js |
| Effemeridi **offline** (Skyfield + SPICE + `de421.bsp`) | Streamlit | Non migrate: la Web UI usa JPL Horizons, quindi la rete. Decisione D2 aperta |
| Ranking delle finestre scienza/ingegneria (`mission_planner.rank_operational_windows`) | Panda3D | Il modulo resta in `src/`; nessun endpoint Web |
| Scena 3D Panda3D con i modelli di `data/models/nasa/` | Panda3D | Non migrata |

I moduli scientifici usati da questi componenti (`site_assessment`, `mission_planning`, `mission_planner`, `illumination_analysis`, `terrain_horizon`, …) **restano in `src/`**, invariati.

## Avvertenze

- **Non eseguire i patch-script.** Sovrascriverebbero file in uso, compreso `src/ui_web/index.html`.
- **I componenti non funzionano dalla nuova posizione senza adattamenti.** Importano `src.*` oppure calcolano la radice del progetto dalla propria posizione. Ad esempio, `main.py` cerca il viewer in `<cartella di main.py>/src/lunar_native_viewer.py`. Non li ho modificati per conservarli intatti.
- **Ripristino.** Per riusare un componente bisogna riportarlo nella posizione originale e installare le dipendenze legacy:

  ```bash
  mv legacy/tkinter/main.py ./main.py
  mv legacy/tkinter/lunar_native_viewer.py src/
  mv legacy/streamlit/app.py ./app.py
  mv legacy/panda3d/lunar_mission_3d.py src/
  mv legacy/viewers/lunar_3d_app.py legacy/viewers/lunar_globe_3d.py src/ && mv legacy/ui ui
  pip install -r requirements-legacy.txt   # Tkinter va installato a livello di sistema
  ```
