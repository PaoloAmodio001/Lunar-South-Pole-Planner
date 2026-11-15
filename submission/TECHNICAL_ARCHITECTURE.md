# Technical Architecture

Based on the code as of 2026-11-15. Paths are relative to the repository root.

## 1. Overview

```
 DATA                         SCIENCE MODULES (src/)            MISSION ENGINE                 WEB UI (src/ui_web/)
 ─────────────────────        ─────────────────────────         ─────────────────────          ─────────────────────────
 NASA/JPL Horizons API ─────► astronomy.py ────────────────┐    mission_orchestrator.py        app.py  (stdlib HTTP, :8765)
 (live HTTPS)                 site_comparison.py           │    (JSON config, CLI + Web)  ───►  ├─ /            public globe
                              mission_planning.py (windows)│     ├─ step functions             ├─ Educators     public
 NAIF SPICE + DE421 ────────► local_ephemeris.py ──────────┤     ├─ solar_energy_engine.py     ├─ /dashboard    login
 (local files)                ephemeris_validation.py      │     ├─ mission_decision_engine.py └─ /mission-control login
                                                           ├───► ├─ mission_report.py         science_api.py (thin wrappers)
 LOLA 5 m/px DEMs (PGDA) ───► data_quality, terrain_metrics│     └─ psystem_adapter.py (exp.)  mission_runner.py (subprocess)
 LROC NAC DTM SR12 (PDS) ───► terrain_horizon, horizon_    │                                   auth.py (scrypt, sessions)
                              analysis, illumination_      │    reports/mission/,              main.js + three.js r186
                              analysis, contact_windows,   │    reports/web_runs/<id>/         (vendored), globe-markers.js
                              terrain_cross_validation,    │
                              lola_lroc_quality, lroc_     │
                              quality_mask, rover_planning,│
                              rover_energy, multi_rover,   │
                              descent_hazard_detection     │
 communications.py, thermal_model.py (analytic) ───────────┘
 NASA SVS Moon GLB ──────────────────────────────────────────────────────────────────────────► 3D globe (visual only)
```

## 2. Components

### 2.1 Web server — `src/ui_web/app.py`

- Python standard library `http.server` with an explicit route whitelist and static routes (no directory listing). Binds to `127.0.0.1:8765` by default (`--host`, `--port`, `--no-browser`, `--desktop`).
- **Public:** `/`, `/api/health`, `/api/sites`, `/api/ephemerides`, `/api/services`, static assets.
- **Protected** (`PROTECTED_PATHS` / `PROTECTED_PREFIXES`): `/dashboard`, `/mission-control`, `/api/auth/session`, `/api/mission/*`, `/api/science/*`, `/api/communications/*`, `/api/thermal/*`, `/api/terrain/*`.
- `/api/ephemerides` calls Horizons twice (Sun `10` and Earth `399`) at 1-hour steps for up to 720 hours. It aligns the timestamps, computes the windows (`mission_planning.find_operational_windows`) and their ranking, and returns classified errors (`timeout`, `dns`, `connection`, `http`, `upstream_error`, `invalid_response`, `data`).
- At most 2 science computations run concurrently. Further requests get HTTP 503.

### 2.2 Authentication — `src/ui_web/auth.py`, `auth_admin.py`

- scrypt password hashes and server-side sessions, stored outside the repository (`~/.config/lunar-mission-control/` or `$LUNAR_AUTH_DIR`).
- Idle and absolute session expiry, and limits on login attempts.
- The first administrator account is created only through a web form while the user store is empty.
- HTTP only: use an HTTPS reverse proxy with `LUNAR_COOKIE_SECURE=1` beyond loopback.

### 2.3 Science API — `src/ui_web/science_api.py`

Thin wrappers with no algorithms of their own. Rasters come from a fixed server-side catalogue (`lola_site04` → `Site04_final_adj_5mpp_surf.tif`, `lroc_nac_sr12` → `NAC_DTM_ESALL_SR12.TIF`, not used for route planning); the browser can never supply file paths. Endpoints: `dem-audit`, `terrain`, `horizon`, `rover-plan`, `site-comparison`, `rasters`.

### 2.4 Mission Engine — `src/mission_orchestrator.py`

- Runs from the CLI (`python -m src.mission_orchestrator mission_config.example.json`) or from the Web UI (`mission_runner.py` starts it as a subprocess and writes to `reports/web_runs/<id>/`).
- Steps (`mission_config.example.json`, **enabled** in the example config marked ✔):
  - ✔ rover path, ✔ LOLA–LROC quality, ✔ descent hazard detection, ✔ site selection, ✔ mission report, plus the always-run decision step.
  - Disabled: astronomy (horizons/local), illumination, local site analysis, confidence validation, data quality, horizon, visibility, site assessment, lunar geometry, descent risk map, energy, solar energy, fleet, fleet on DEM, journal, P-System.
- Outputs: JSON/Markdown reports with run IDs, an artifact inventory and an event journal.

### 2.5 Ephemerides

| Source | Module | Used by |
|---|---|---|
| NASA/JPL Horizons API (live) | `astronomy.py` | Web UI, site comparison, orchestrator `astronomy` step |
| Skyfield + NAIF SPICE (DE421, `moon_pa_de421_1900-2050.bpc`, `moon_080317.tf`, `pck00008.tpc`), frame `MOON_ME_DE421`, valid 1900–2050 | `local_ephemeris.py` | `contact_windows`, `terrain_cross_validation`, orchestrator `astronomy.source="local"` |

Cross-check: `python -m src.ephemeris_validation --start 2026-11-15T00:00` → `reports/validation/ephemeris_validation_*.json`.

### 2.6 Terrain and visibility

- DEMs are in south polar stereographic projection (`+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +R=1737400`).
- Horizon profile: rays from the observer cell (configurable observer height and azimuth step) give the maximum elevation angle, with a spherical-Moon correction when the CRS is recognised as lunar (`terrain_horizon.py`).
- Profile azimuths are in the raster-grid frame. `lunar_geometry.grid_azimuth_offset` converts them to true north for comparison with ephemerides (`contact_windows.py`).
- Cross-validation: `python -m src.terrain_cross_validation --start 2026-11-15T00:00 --days 28` → `reports/validation/terrain_cross_validation.json`.

### 2.7 Frontend

`index.html`, `main.js`, `mission.js`, `science.js`, `dashboard.*`, `login.html`, `session.js`, `ui/*.css|js`. Vanilla JavaScript and three.js r186 vendored in `src/ui_web/vendor/three/`; no npm build. The globe loads `data/terrain/global/Moon_NASA_LRO_8k_Topo_Small.glb`, and site markers are placed by UV lookup (`ui/globe-markers.js`).

### 2.8 P-System integration (EXPERIMENTAL)

`psystem_adapter.py` (`MissionJournal`, `PSystemBridge`) and `psystem_cluster.py` publish mission records (Ed25519 identities, versions, digests, causal parents) to a committee of P-System nodes and verify the certificates. This needs a separate P-System installation. It is disabled by default and has been tested only with local processes on one machine. The behaviour over real Earth–Moon links is **not verified**.

## 3. Dependencies

| File | Content |
|---|---|
| `requirements.txt` | requests 2.34.2, numpy 2.5.4, rasterio 1.5.2, pyproj 3.8.0, matplotlib 3.11.2, skyfield 1.55 (offline ephemeris) |
| `requirements-dev.txt` | + pytest 9.1.1 |
| `requirements-desktop.txt` | + PySide6 6.12.0 (optional) |
| `requirements-legacy.txt` | Streamlit, Plotly, Panda3D, trimesh… (archived interfaces only) |

Runtime: Python 3.14.8 is the only version tested. Network access is required only for Horizons.

## 4. Repository layout (relevant parts)

```
start.sh                     single launcher (venv + dependency check + server)
src/                         science modules, Mission Engine
src/ui_web/                  server, auth, APIs, frontend, vendored three.js
data/terrain/official-lola/  LOLA PGDA DEMs (Site01, Site04, Site06)
data/terrain/reference-lroc/ LROC NAC DTM SR12 + confidence + PDS3 label
data/terrain/kernels/, de421.bsp   SPICE kernels
data/terrain/global/         NASA SVS Moon GLB
tests/                       38 pytest files, 309 test functions
reports/validation/          ephemeris and terrain cross-validation evidence
legacy/                      archived interfaces (not official entry points)
submission/                  this submission package
```

## 5. Verification status

| Item | Status | Evidence |
|---|---|---|
| Test suite | Last recorded run: 494 passed, 0 failed. **Not re-run for this submission.** | Earlier test report (no longer in the repository; the count cannot be re-checked from the repo) |
| Login and new error handling | No automated tests | `README.md` (Limitazioni) |
| Browser end-to-end tests | None | `README.md` |
| Ephemeris: local vs Horizons | PASS (max 1.36e-5° elevation) | `reports/validation/ephemeris_validation_20261115T0000.json` |
| Terrain: LOLA vs LROC | Consistent (median Sun-visibility agreement 99.9%) | `reports/validation/terrain_cross_validation.json` |
| Globe marker geodesy | PARTIAL | `reports/web_ui_consolidation/F10_GEODETIC_VALIDATION.md` |
| Web UI running live for this submission | **NOT VERIFIED.** The application was not started during submission preparation | — |
