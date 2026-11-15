# Validazione dell'identità geografica del sito — Report

- **Data:** 2026-11-14
- **Inizio:** 21:27:20 · **Fine verifiche:** 21:30:56 · **Report chiuso:** ~21:33
- **Tempo effettivo:** circa 6 minuti su 30
- **Esito: PASS** — tutti e cinque i criteri di completamento sono dimostrati (§8)

---

## 1. Problema iniziale

L'audit end-to-end (`reports/end_to_end_audit/END_TO_END_AUDIT_REPORT.md`, HIGH-1) aveva rilevato un'incoerenza:

- `mission_config.example.json` dichiarava **Connecting Ridge** in `astronomy.site`, `mission_report.site_name` e `local_site_analysis.site_name`. Anche il default dell'orchestratore per l'astronomia era "Connecting Ridge".
- Tutti i raster di terreno configurati sono però `Site04_final_adj_5mpp_*` e il DTM LROC `NAC_DTM_ESALL_SR12`.
- Con l'astronomia attiva, le effemeridi di un sito sarebbero state combinate con il terreno di un altro, senza alcun controllo.

La configurazione realmente usata è `mission_config.example.json`: è l'unica config nel repository e viene passata come argomento CLI a `python -m src.mission_orchestrator`.

## 2. Evidenze geografiche

### 2.1 Fonti
- **README LOLA** (`data/terrain/official-lola/metadata/LOLA_5mpp_README`):
  - coordinate X/Y in stereografica polare sud, in metri, frame MOON_ME (DE421);
  - pixel-registered (le coordinate indicano il centro dei pixel);
  - **Site01: Connecting ridge · Site04: Shackleton rim · Site06: Nobile rim 1** (numerazione di Mazarico et al. 2011).
- **Coordinate dei siti** (`src/astronomy.py::SITES`): "NASA Lunar Surface Data Book, 2025-03-18, Table A2.1-1; coordinates derived from PGDA south-pole LOLA DEMs". Latitudine e longitudine est, in gradi.
- **Trasformazione:** il CRS dichiarato da ogni raster è `+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +x_0=0 +y_0=0 +R=1737400 +units=m`. Per il passaggio lon/lat → x/y usa `src/lunar_geometry.geographic_to_projected` (pyproj, sfera R = 1 737 400 m). Nessuna trasformazione è stata inventata: si usa solo la definizione del CRS presente nei file.
- **Verifica indipendente della formula:** su sfera, ρ = 2R·tan(45° + φ/2), x = ρ·sin λ, y = ρ·cos λ. Coincide con pyproj entro 1 mm per tutti e tre i siti (test §6).

### 2.2 DEM Site04
| Proprietà | Valore |
|---|---|
| Dimensioni / risoluzione | 3200 × 3200 px, 5 m |
| Trasformazione affine | (5.0, 0.0, −9000.0, 0.0, −5.0, 1000.0) |
| Limiti proiettati | x [−9000, 7000] m, y [−15000, 1000] m |
| Centro | lat **−89,7668°**, lon E **−171,870°** |
| Angoli (lat, lon E) | NW (−89,7014, −83,66) · NE (−89,7668, 81,87) · SW (−89,4231, −149,04) · SE (−89,4541, 154,98) |

### 2.3 Posizione dei siti rispetto ai DEM (verifica incrociata)
| Sito (SITES) | lat, lon E | x, y (m) | Site01 (README: Connecting ridge) | Site04 (README: Shackleton rim) | Site06 (README: Nobile rim 1) | LROC SR12 |
|---|---|---|---|---|---|---|
| Shackleton | −89,7668, −171,87 | −1000,0; −7000,3 | fuori | **dentro, 0,3 m dal centro** (pixel 1600, 1599) | fuori | dentro (1,68 km dal centro) |
| Connecting Ridge | −89,4632, −137,49 | −10999,1; −11999,3 | **dentro, 1,1 m dal centro** | **fuori** (oltre il bordo ovest x = −9000 m; 11,18 km dal centro) | fuori | fuori |
| Nobile | −85,4381, 37,36667 | 84000,0; 110000,0 | fuori | fuori | **dentro, 0,0 m dal centro** | fuori |

**Conclusione.** Per tutti e tre i casi, ciascun sito cade nel centro esatto del DEM che il README gli attribuisce (scarto ≤ 1,1 m) e fuori dagli altri. L'identità **Site04 = Shackleton rim** è quindi dimostrata da due fonti indipendenti (README LOLA e coordinate del Data Book) più una verifica numerica, non dal solo nome del file. Il DEM non contiene Connecting Ridge.

## 3. File modificati

| File | Modifica |
|---|---|
| `src/lunar_geometry.py` | +90 righe: `SiteIdentityError` (sottoclasse di `ValueError`) e `validate_site_in_raster()`. Funzioni esistenti invariate. |
| `src/mission_orchestrator.py` | `validate_mission_site_identity(config)`, chiamata all'inizio di `run_mission_workflow()` prima di ogni step; esito registrato in `report["site_identity"]`. Il default astronomico è ora la costante `DEFAULT_ASTRONOMY_SITE`, con lo stesso valore di prima. |
| `mission_config.example.json` | 5 valori: `astronomy.site`, `local_site_analysis.site_name`, `mission_report.site_name` → "Shackleton"; `lunar_geometry.latitude_deg/longitude_east_deg` → −89,7668 / −171,87 (da `SITES`). Percorsi DEM invariati. |
| `tests/test_site_identity_validation.py` | **Nuovo**, 36 test. |

Nessuna modifica a raster, formule scientifiche, scoring o pesi, illuminazione, modelli fisici o UI. Nessun nuovo modulo. Nessun commit.

## 4. Backup

`backups/site-identity-validation-20261114-212825/` contiene:
- `src/lunar_geometry.py`, `src/mission_orchestrator.py`, `mission_config.example.json`;
- `tests/test_lunar_geometry.py`, `tests/test_mission_astronomy.py`;
- `SHA256SUMS`;
- `git_status_initial.txt` (stato Git iniziale: 26 voci più HEAD `3b74580`).

## 5. Correzione applicata

### 5.1 Configurazione
Le evidenze sono sufficienti (§2), quindi la config dichiara ora **Shackleton** in modo coerente con Site04. Le coordinate associate sono quelle documentate in `SITES`.

### 5.2 Controllo preventivo (`validate_mission_site_identity`)
Viene eseguito prima di creare la cartella di output e prima di qualunque step, quindi **prima di qualsiasi query a Horizons**.

1. Raccoglie i raster di terreno degli step che verranno eseguiti:
   - sempre: `site_selection`, `rover_path`, `descent_hazard_detection`, `lola_lroc_quality` (LOLA e LROC);
   - solo se `enabled`: `local_site_analysis`, `horizon_analysis`, `site_assessment`, `lunar_geometry`, `data_quality`.
2. Raccoglie i siti dichiarati: `astronomy.site` (default compreso, se attiva), `mission_report.site_name`, `local_site_analysis.site_name` (se attiva). Il riconoscimento ignora maiuscole e spazi, quindi varianti come "connecting ridge" non aggirano il controllo.
3. Blocca con `SiteIdentityError` se:
   - i siti noti dichiarati sono diversi tra loro;
   - l'astronomia è attiva insieme a raster di terreno ma il sito non ha coordinate note;
   - un sito dichiarato non cade dentro **ogni** raster attivo;
   - il CRS di un raster è assente, non proiettato o non basato sulla sfera lunare R = 1 737 400 m ± 1 m (trasformazione non verificabile);
   - la trasformazione fallisce o le coordinate non sono valide.
4. Se il raster manca: `FileNotFoundError`.

Gli errori **non** vengono convertiti in warning. `main()` stampa `Errore di configurazione: SiteIdentityError: [sezione.chiave] …` ed esce con codice 2. Non viene scritto alcun output.

**Configurazioni ancora ammesse** (comportamento invariato):
- astronomia senza raster di terreno (i test esistenti `test_mission_astronomy.py` usano solo Horizons simulato);
- config senza siti dichiarati;
- etichette libere non riconducibili a `SITES` (ad esempio "Candidato provvisorio");
- sezioni disattivate.

In tutti questi casi `site_identity.status = "not_applicable"`.

### 5.3 Prova end-to-end (output nello scratchpad)
| Configurazione | Esito |
|---|---|
| Nuova (`Shackleton`) | exit 0, `completed_preliminary`, 4 step `success`. `site_identity.status = validated`; distanza dal centro 0,3 m su LOLA Site04 e 1679,7 m su LROC. Il rapporto di stato riporta "Sito candidato: Shackleton". |
| Precedente (`Connecting Ridge`, dal backup) | exit 2, `SiteIdentityError: [site_selection.dem_path] Sito 'Connecting Ridge' … fuori dall'estensione del raster …Site04…`. Nessun output creato. |

## 6. Test

`tests/test_site_identity_validation.py` (36 test):

| # | Requisito | Test |
|---|---|---|
| 1 | Shackleton ↔ Site04 associati correttamente | `test_shackleton_is_at_center_of_site04`, `test_each_site_matches_its_readme_dem[3]` |
| 2 | Connecting Ridge fuori da Site04: errore esplicito | `test_connecting_ridge_outside_site04_is_explicit_error`, `test_site_outside_synthetic_raster` |
| 3 | Coordinate trasformate correttamente | `test_transform_matches_spherical_formula[3]` (formula analitica, 1 mm), `test_shackleton_projected_coordinates` |
| 4 | Coordinate non trasformabili | CRS assente; EPSG:3857, EPSG:4326, sfera con raggio errato; lat 95°, NaN, lon 720°; raster mancante |
| 5 | Sito e DEM incompatibili | `test_mission_report_site_incompatible_with_dem`, `test_declared_sites_must_agree`, `test_every_active_raster_is_checked`, `test_case_variants_cannot_bypass_check`, `test_previous_example_config_is_now_rejected` |
| 6 | Astronomia bloccata | Sito esplicito e default storico: `query_observations` mai chiamata, nessun output. Sito sconosciuto con DEM bloccato. CLI con exit 2. Caso coerente: Horizons interrogato con le coordinate di Shackleton. |
| 7 | Configurazioni valide non toccate | 6 configurazioni senza conflitto → `not_applicable`; sezioni disattivate ignorate; config di esempio → `validated` |

**Risultati:**
- Test nuovi e test direttamente interessati (`test_lunar_geometry`, `test_mission_astronomy`, `test_mission_orchestrator_journal`, `test_mission_orchestrator_lola_lroc`, `test_mission_report_journal`): **56/56 superati**.
- Suite completa: **186 superati, 0 falliti** (150 prima della sessione, più 36 nuovi).
- `py_compile` OK; `mission_config.example.json` è JSON valido.
- Durante la sessione, 3 test sono falliti per un errore nel test stesso: il punto di prova cadeva esattamente sul bordo tra due pixel. Le coordinate erano già corrette. Ho spostato il punto al centro del pixel; l'asserzione non è stata indebolita.

## 7. Integrità dei raster

Controllo SHA-256 prima e dopo: **OK** per tutti e sette i file:
- `Site04_*_{surf,ldec,toterr}.tif`;
- `Site01_*_surf.tif` e `Site06_*_surf.tif` (letti solo per la verifica incrociata);
- `NAC_DTM_ESALL_SR12.TIF` e `NAC_DTM_ESALL_SR12_CONF_original.IMG`.

## 8. Criteri di completamento

| Criterio | Stato | Evidenza |
|---|---|---|
| Identità del sito dimostrata | PASS | §2.3: tre siti, tre DEM, scarto ≤ 1,1 m, coerente con il README |
| Configurazione e DEM coerenti | PASS | `test_example_config_is_geographically_coherent`, prova end-to-end §5.3 |
| Coordinate validate | PASS | Formula analitica (§2.1) e `validate_site_in_raster` su ogni raster attivo |
| Astronomia bloccata con coordinate incompatibili | PASS | Test §6 n. 6 (nessuna chiamata a Horizons, exit 2) |
| Test pertinenti superati | PASS | 56/56 mirati, 186/186 suite completa |

## 9. Problemi residui

1. **Report generati in precedenza.** `reports/mission/mission_status_report.{md,json}` (run del 2026-10/11) riportano ancora "Connecting Ridge". Non li ho rigenerati per non sovrascrivere artefatti storici: lo farà il prossimo run dell'orchestratore. Anche i vecchi backup `mission_config.example.before-*.json` contengono il valore storico, per scelta.
2. **Frame orizzontale.** La coerenza tra le coordinate `SITES` e il frame MOON_ME del DEM è dimostrata dalla provenienza comune (PGDA) e dalla concordanza entro 1 m. Non esiste però una validazione esterna indipendente del frame: il flag `georeference_validated` di `locate_observer` resta `False`.
3. **Etichette libere** (non presenti in `SITES`): non vengono geolocalizzate e quindi non sono validate. Sono ammesse per compatibilità e risultano `not_applicable`.
4. **Default astronomico.** Resta "Connecting Ridge" per compatibilità del codice. Il controllo preventivo blocca il default se è incompatibile con i DEM configurati.
5. **Copertura del controllo.** Verifica che il sito cada *dentro* il raster, non che ne sia il centro. Un raster ampio che contiene più siti viene accettato per ciascuno di essi; con i dati attuali non accade.
6. **Fuori ambito** (vedi audit): altitudine 0 km nelle query Horizons, offset azimutale di griglia, orizzonte troncato.

## 10. Tempo impiegato

| Fase | Intervallo |
|---|---|
| Backup, stato Git, analisi della config | 21:27:20 – 21:28:30 |
| Verifica geografica incrociata (Site01, Site04, Site06, LROC) | 21:28:30 – 21:29 |
| Implementazione (`lunar_geometry`, orchestratore, config) | 21:29 – 21:30 |
| Test mirati, suite completa, prova end-to-end, checksum | 21:30 – 21:30:56 |
| Report | 21:31 – ~21:33 |
| **Totale** | **circa 6 minuti su 30** |
