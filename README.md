# Lunar South Pole Planner

**A locally run Python and web application that combines NASA/JPL Horizons ephemerides with NASA Lunar Reconnaissance Orbiter terrain data to study sunlight, Earth visibility, terrain and surface mobility at candidate lunar south pole sites.**

> **Status: research and education prototype.** All outputs are preliminary diagnostics. The software is **not flight-certified, not operationally validated and not qualified for mission decisions.** Every Web UI response names the module and the raster it comes from.

Prepared for the **NASA Space Apps Challenge 2026**. The submission package (summary, details, data sources, architecture, 7-slide deck, figures) is in [`submission/`](submission/).

A previous Italian version of this README is kept in [`docs/README_IT.md`](docs/README_IT.md).

---

## Contents

1. [Project overview](#1-project-overview)
2. [Mission and objectives](#2-mission-and-objectives)
3. [Main features](#3-main-features)
4. [Scientific data sources](#4-scientific-data-sources)
5. [Technical architecture](#5-technical-architecture)
6. [Terrain analysis](#6-terrain-analysis)
7. [Solar illumination and Earth visibility](#7-solar-illumination-and-earth-visibility)
8. [Energy estimation](#8-energy-estimation)
9. [Rover route planning](#9-rover-route-planning)
10. [3D visualization](#10-3d-visualization)
11. [Installation](#11-installation)
12. [Usage](#12-usage)
13. [Testing](#13-testing)
14. [Project structure](#14-project-structure)
15. [Limitations and scientific validation](#15-limitations-and-scientific-validation)
16. [NASA data acknowledgements](#16-nasa-data-acknowledgements)
17. [AI assistance disclosure](#17-ai-assistance-disclosure)
18. [License](#18-license)

---

## 1. Project overview

Near the lunar south pole the Sun stays within a degree or two of the horizon, and the Earth rises and sets as the Moon librates. Whether a location is lit, and whether it can communicate directly with Earth, depends on the local terrain as much as on orbital geometry.

Lunar South Pole Planner brings the relevant NASA data together in one local tool:

- **Sun and Earth positions** from the NASA/JPL Horizons API (live) or offline from NAIF SPICE kernels and DE421;
- **Terrain** from NASA LRO: 5 m/pixel LOLA site DEMs (NASA GSFC PGDA) and an LROC NAC stereo DTM of the Shackleton rim (NASA PDS).

It studies three candidate sites:

| Site | Latitude | East longitude | LOLA DEM |
|---|---|---|---|
| Shackleton rim | −89.7668° | −171.87° | PGDA Site04 |
| Connecting Ridge | −89.4632° | −137.49° | PGDA Site01 |
| Nobile rim 1 | −85.4381° | 37.36667° | PGDA Site06 |

Coordinates are defined in `src/astronomy.py` (`SITES`). Their cited source document is not yet verified (see [§15](#15-limitations-and-scientific-validation)).

One local web server serves three audiences:

- **Public:** a 3D Moon globe with the candidate sites and live Sun/Earth ephemerides. No login.
- **Educators:** a free seven-chapter course with three depth levels, printable activities and labs built on the public APIs. No login, no personal data.
- **Mission planners:** a login-protected dashboard and *Lunar Mission Control Planner* with the science tools and the Mission Engine.

## 2. Mission and objectives

- Quantify how often the Sun and the Earth are above the **geometric** horizon at each candidate site.
- Quantify how the **terrain** horizon changes that picture, using two independent NASA terrain products as a consistency check.
- Provide first-order engineering context for surface operations: slopes, rover routes and their energy cost, radio link margins and thermal behaviour.
- Keep every number traceable to its source data and module, and state explicitly what is not modelled.

## 3. Main features

Status labels: **Implemented** (reachable in the Web UI or a documented CLI) · **Partial** (documented gaps, or orchestrator/CLI only) · **Experimental** (tested locally only).

| Capability | Where | Status |
|---|---|---|
| Live Sun/Earth elevation and azimuth from Horizons, operational windows, ranking, classified errors | Web UI, public (`/api/ephemerides`) | Implemented (needs network) |
| 3D globe with the three candidate sites | Web UI, public | Implemented; marker geodetic check Partial |
| Educators section (7 chapters, 3 levels, labs on public APIs) | Web UI, public | Implemented |
| DEM audit, slope/roughness, horizon profile, A* rover route and energy, LROC quality summary | Web UI, planner (login) | Implemented; inputs are DEM row/column |
| Geometric site comparison (Sun/Earth) | Web UI, planner | Implemented (needs network) |
| Free-space RF link budget; single-node thermal model | Web UI, planner | Implemented (first-order models) |
| Mission Engine run of the example configuration | Web UI, planner, and CLI | Implemented |
| Offline Sun/Earth ephemeris (Skyfield + SPICE), validated against Horizons | Mission Engine / CLI | Implemented; not in the Web UI |
| Terrain-aware illumination and Earth-contact windows | Mission Engine / CLI | Partial |
| LOLA vs LROC horizon and Sun-visibility cross-validation | CLI | Implemented |
| Solar energy engine and mission decision engine | Mission Engine | Partial (preliminary, not validated) |
| Multi-rover fleet planning on the DEM | Mission Engine | Partial (routes and assignments, no time sequencing) |
| Descent-hazard diagnostic raster | Mission Engine | Partial (prototype) |
| Single login for the planner section (scrypt, sessions, rate limiting) | Web UI | Implemented; no automated tests |
| P-System mission-record certification | Mission Engine | Experimental; needs a separate P-System installation |

## 4. Scientific data sources

Full details, URLs, file lists and the integration status of each resource are in [`submission/NASA_DATA_SOURCES.md`](submission/NASA_DATA_SOURCES.md).

| Resource | Files / endpoint | Use |
|---|---|---|
| **NASA/JPL Horizons API** | `https://ssd.jpl.nasa.gov/api/horizons.api` | Live topocentric Sun and Earth azimuth/elevation from a lunar surface point |
| **LOLA high-resolution south pole site DEMs** (NASA GSFC PGDA, product 78) | `data/terrain/official-lola/` (Site01, Site04, Site06 at 5 m/px; Site04 LDEC and TOTERR) | Main terrain source |
| **LROC NAC DTM `NAC_DTM_ESALL_SR12`** (NASA PDS, LROC) | `data/terrain/reference-lroc/` (2 m/px DTM, confidence raster, PDS3 label) | Independent second DEM over the Shackleton rim |
| **NAIF SPICE generic kernels + JPL DE421** | `de421.bsp`, `data/terrain/kernels/` | Offline ephemeris |
| **NASA SVS "Moon 3D Models for Web, AR, and Animation"** (SVS 14959) | `data/terrain/global/Moon_NASA_LRO_8k_Topo_Small.glb` | 3D globe (visual only) |

All of these files are already in the repository. The largest single file is 78 MB, below GitHub's 100 MB per-file limit. Files under `data/terrain/processed/` are masks and audits derived by this project, not NASA products. The original download pages are listed in `submission/NASA_DATA_SOURCES.md` for anyone who wants to re-download or verify them.

The project does **not** use Diviner, LAMP, Mini-RF, LEND, published illumination or PSR maps, DSN schedules, or any NASA API other than Horizons.

## 5. Technical architecture

```
 DATA                         SCIENCE MODULES (src/)            MISSION ENGINE                 WEB UI (src/ui_web/)
 NASA/JPL Horizons API ─────► astronomy.py, site_comparison,    mission_orchestrator.py        app.py (stdlib HTTP, :8765)
 NAIF SPICE + DE421 ────────► local_ephemeris.py               ├ solar_energy_engine.py       ├ /                public
 LOLA DEMs (PGDA) ──────────► data_quality, terrain_metrics,   ├ mission_decision_engine.py   ├ Educators        public
 LROC NAC DTM (PDS) ────────► terrain_horizon, horizon_        ├ mission_report.py            ├ /dashboard       login
                              analysis, illumination_analysis, └ psystem_adapter.py (exp.)    └ /mission-control login
                              contact_windows, rover_planning,                                science_api.py, mission_runner.py,
                              rover_energy, multi_rover, ...    reports/mission/,             auth.py, three.js r186 (vendored)
 NASA SVS Moon GLB ─────────────────────────────────────────────────────────────────────────► 3D globe (visual only)
```

- **Web server** (`src/ui_web/app.py`): Python standard library `http.server` with an explicit route whitelist and fixed static routes. No web framework. Binds to `127.0.0.1:8765` by default.
- **Public routes:** `/`, `/api/health`, `/api/sites`, `/api/ephemerides`, `/api/services`, static assets.
- **Protected routes** (`PROTECTED_PATHS` / `PROTECTED_PREFIXES` in `app.py`): `/dashboard`, `/mission-control`, `/api/auth/session`, `/api/mission/*`, `/api/science/*`, `/api/communications/*`, `/api/thermal/*`, `/api/terrain/*`.
- **Authentication** (`src/ui_web/auth.py`, `auth_admin.py`): scrypt password hashes and server-side sessions, stored **outside** the repository (`~/.config/lunar-mission-control/` or `$LUNAR_AUTH_DIR`). Idle and absolute session expiry, login-attempt limits. There are no default credentials.
- **Science API** (`src/ui_web/science_api.py`): thin wrappers around the science modules. Rasters come from a fixed server-side catalogue; the browser can never supply file paths. At most 2 science computations run at once; further requests get HTTP 503.
- **Mission Engine** (`src/mission_orchestrator.py`): chains the steps enabled in a JSON configuration and writes JSON and Markdown reports with run IDs, an artifact inventory and an event journal.
- **Frontend:** vanilla JavaScript, HTML and CSS, with three.js r186 vendored in `src/ui_web/vendor/three/`. No npm build step.

More detail: [`submission/TECHNICAL_ARCHITECTURE.md`](submission/TECHNICAL_ARCHITECTURE.md) and [`docs/MISSION_PLANNERS.md`](docs/MISSION_PLANNERS.md) (Italian).

## 6. Terrain analysis

All raster modules read the GeoTIFFs with rasterio. The DEMs use a south polar stereographic projection.

| Analysis | Module | Notes |
|---|---|---|
| DEM audit (metadata, NoData, statistics) | `data_quality.py` | Web UI: `POST /api/science/dem-audit` |
| Local slope and roughness | `terrain_metrics.py` | Sampled by DEM row/column; no geographic assumption. Web UI: `POST /api/science/terrain` |
| Horizon profile | `terrain_horizon.py`, `horizon_analysis.py` | Rays from the observer cell; spherical-Moon correction when the CRS is recognised as lunar. Web UI: `POST /api/science/horizon` |
| LOLA local quality (LDEC returns, TOTERR uncertainty) | `lola_local_quality.py` | Mission Engine |
| LOLA vs LROC comparison and LROC quality mask | `lola_lroc_quality.py`, `lroc_quality_mask.py` | Mission Engine; summary in the Web UI (`/api/terrain/lroc-quality`) |
| Descent-hazard diagnostic | `descent_hazard_detection.py` | Prototype, Mission Engine |

Profile azimuths are in the raster-grid frame. `lunar_geometry.grid_azimuth_offset` converts them to true north before they are compared with ephemerides.

## 7. Solar illumination and Earth visibility

- **Geometric windows (Web UI).** `/api/ephemerides` queries Horizons for the Sun (`10`) and the Earth (`399`) at 1-hour steps for up to 720 hours. `mission_planning.find_operational_windows` finds intervals where both are above user thresholds. Errors are classified (timeout, DNS, connection, HTTP, upstream, invalid response, data). The UI never shows demonstration data in place of real data.
- **Offline ephemeris.** `src/local_ephemeris.py` computes the same topocentric quantities with Skyfield, DE421 and the lunar PA kernels in the `MOON_ME_DE421` frame (valid 1900–2050).
- **Terrain-aware windows (Mission Engine / CLI).** `src/contact_windows.py` combines a DEM horizon profile, the grid-to-north azimuth offset and the local ephemeris. It finds illumination windows and Earth-contact windows (the latter optionally with a link budget).
- **Direct-illumination diagnostics.** `src/illumination_analysis.py` (Mission Engine).

## 8. Energy estimation

- **Rover traverse energy** (`src/rover_energy.py`): a preliminary physics-based estimate covering rolling resistance, positive gravitational work while climbing (g = 1.62 m/s²), drivetrain losses and auxiliary load. It does not credit downhill regeneration or solar generation. In the Web UI it runs only when **all** rover parameters are supplied.
- **Solar Energy Engine** (`src/solar_energy_engine.py`, optional `solar_energy` step): photovoltaic production, consumption by category, battery state of charge and deficits over time. It reuses the astronomy, illumination and (if present) rover-energy reports. Hardware parameters have no defaults; if they are missing, the report is marked partial. The report declares `model_validation.scientifically_validated = false`. Details: [`docs/solar_energy_engine.md`](docs/solar_energy_engine.md) (Italian).
- **Mission Decision Engine** (`src/mission_decision_engine.py`): aggregates the step results conservatively and separates geometrically favourable windows from energetically sustainable ones.

## 9. Rover route planning

- **Single rover** (`src/rover_planning.py`): terrain-aware A* over the DEM grid, with anisotropic pixel spacing, local DEM gradients, NoData barriers and a slope limit. The output includes path, distance, maximum slope and cells expanded, and is labelled `preliminary`. Web UI: `POST /api/science/rover-plan`, with start and goal as DEM row/column. Only the LOLA raster is used for routing.
- **Multi-rover** (`src/multi_rover.py`, `plan_fleet_on_dem`, Mission Engine step `multi_rover_dem`): A* routes for several rovers with energy budgets, route-overlap checks and Earth contact at the destination. It produces routes and assignments only; there is no time sequencing.
- `src/route_quality.py` and `src/plot_rover_route.py` provide route quality checks and plots.

## 10. 3D visualization

- The Web UI globe (`src/ui_web/main.js`, three.js r186) loads the NASA SVS LRO-based Moon model and places the three site markers by UV lookup (`src/ui_web/ui/globe-markers.js`).
- **Analysis results are not projected onto the globe**, because the model's frame has not been validated against the DEM grid. The geodetic check of the markers is **Partial** (`reports/web_ui_consolidation/F10_GEODETIC_VALIDATION.md`). Results are shown in 2D charts.
- Static figures generated from real project data (LOLA hillshades, horizon and Sun-visibility comparisons, Horizons elevation plots) are in [`submission/assets/`](submission/assets/) and `reports/`.
- Earlier viewers (Panda3D, Plotly, trimesh) are archived in `legacy/` and are not official entry points.

## 11. Installation

Tested on Linux with **Python 3.14.8**, the only version verified. A modern browser with WebGL is needed for the globe. npm is not needed.

```bash
git clone https://github.com/PaoloAmodio001/Lunar-South-Pole-Planner.git
cd Lunar-South-Pole-Planner
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Note: the repository includes about 870 MB of NASA terrain data, so the clone is large.

| File | Content | When needed |
|---|---|---|
| `requirements.txt` | requests, numpy, rasterio, pyproj, matplotlib, skyfield | Always |
| `requirements-dev.txt` | + pytest | Running the tests |
| `requirements-desktop.txt` | + PySide6 (~670 MB) | Only for `--desktop` (not verified on a real display) |
| `requirements-legacy.txt` | + Streamlit, Plotly, Panda3D, trimesh, … | Only for the archived interfaces in `legacy/` |

The optional P-System integration also needs `cryptography` in the planner venv and a separate P-System installation (`~/Github P-system` or `$PSYSTEM_HOME`). P-System is not part of this repository.

## 12. Usage

### Start the platform

```bash
./start.sh                  # checks the venv and dependencies, then starts the server
./start.sh --no-browser --port 9000
```

`start.sh` passes all arguments to `src/ui_web/app.py`, which can also be run directly: `.venv/bin/python src/ui_web/app.py`. It works from any working directory.

- Public platform: <http://127.0.0.1:8765/>
- Mission planners: <http://127.0.0.1:8765/dashboard>

The server runs in the foreground. Stop it with `Ctrl+C`.

| Option | Environment variable | Effect |
|---|---|---|
| `--host HOST` | `LUNAR_UI_HOST` | Listen address (default `127.0.0.1`) |
| `--port PORT` | `LUNAR_UI_PORT` | TCP port (default `8765`) |
| `--no-browser` | `LUNAR_UI_NO_BROWSER=1` | Do not open the browser |
| `--desktop` | — | Open in a PySide6 window (optional) |
| — | `LUNAR_AUTH_DIR` | User and session store (default `~/.config/lunar-mission-control`) |
| — | `LUNAR_SESSION_IDLE_MINUTES`, `LUNAR_SESSION_MAX_HOURS` | Idle (30 min) and absolute (12 h) session expiry |
| — | `LUNAR_COOKIE_SECURE=1` | `Secure` cookies, for use behind an HTTPS reverse proxy |

### First administrator account

There are no default credentials. On first start, the Mission Planners page shows a **Create administrator account** form (password of at least 12 characters). The form is available only while the user store is empty. Further management from the terminal:

```bash
.venv/bin/python src/ui_web/auth_admin.py add-user <name>
.venv/bin/python src/ui_web/auth_admin.py passwd <name>
.venv/bin/python src/ui_web/auth_admin.py remove-user <name>
```

### Mission Engine (CLI)

```bash
.venv/bin/python -m src.mission_orchestrator mission_config.example.json
```

Reports go to `reports/mission/`, which is overwritten on every run. Runs started from the Web UI are written to `reports/web_runs/<id>/`, which git ignores. In the example configuration the rover path, LOLA–LROC quality, descent-hazard detection, site selection and mission report steps are enabled; astronomy, illumination, solar energy, fleet, journal and P-System are disabled.

### Validation tools (CLI)

```bash
.venv/bin/python -m src.ephemeris_validation --start 2026-11-15T00:00                   # local SPICE vs Horizons (network)
.venv/bin/python -m src.terrain_cross_validation --start 2026-11-15T00:00 --days 28     # LOLA vs LROC
```

### Offline operation

Without network access, the DEM audit, terrain, horizon, rover route, LROC quality, link budget and thermal tools all work, and so does the Mission Engine with the example configuration. Live ephemerides, the operational windows and the site comparison need Horizons. The Web UI has no offline ephemeris fallback.

A step-by-step demo is in [`submission/DEMONSTRATION_SCRIPT.md`](submission/DEMONSTRATION_SCRIPT.md).

## 13. Testing

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q          # testpaths = tests (pytest.ini)
```

- The suite has 38 test files with 309 `test_` functions (counted from the source; parametrised cases add more collected tests).
- The Web UI tests are in `tests/test_web_ui_*.py`. Recorded Horizons responses for offline tests are in `tests/data/`.
- **The suite was not re-run for this repository update.** The last recorded full run (2026-11-15) reported 494 passed and 0 failed, but that report is no longer in the repository. Some code changed later the same day. Run the suite to obtain a current result.
- There are no automated tests for the login, and no browser end-to-end tests.

## 14. Project structure

```
start.sh                      Single launcher (venv + dependency check + server)
mission_config.example.json   Example Mission Engine configuration
requirements*.txt, pytest.ini Dependencies and test configuration
src/
  ui_web/                     Web server, auth, science API, Mission Engine runner,
                              frontend (index.html, main.js, mission.js, science.js,
                              dashboard.*, login.html, session.js, ui/), vendored three.js
  astronomy.py                Horizons client and candidate sites
  local_ephemeris.py          Offline Sun/Earth ephemeris (Skyfield + SPICE)
  ephemeris_validation.py     Local vs Horizons comparison (CLI)
  contact_windows.py          Terrain-aware illumination and Earth-contact windows
  terrain_*.py, horizon_analysis.py, data_quality.py, lola_*.py, lroc_*.py
                              Terrain, horizon and data-quality modules
  rover_planning.py, rover_energy.py, multi_rover.py, route_quality.py
                              Rover routing and energy
  solar_energy_engine.py, mission_decision_engine.py
                              Energy budget and decision aggregation
  communications.py, thermal_model.py
                              First-order link budget and thermal model
  mission_orchestrator.py, mission_report.py
                              Mission Engine (also CLI)
  psystem_adapter.py, psystem_cluster.py
                              Experimental P-System integration
data/                         NASA terrain, kernels, globe and 3D models (see §4)
de421.bsp                     JPL DE421 planetary ephemeris
tests/                        pytest suite and recorded test data
reports/                      Stored outputs; reports/validation/ holds the validation evidence
audit-reports/                LOLA/LROC audit outputs (2026-11-14)
scripts/                      LOLA/LROC diagnostic and horizon-report scripts
docs/                         Module docs (Italian), technical reports, README history
legacy/                       Archived interfaces (Tkinter, Streamlit, Panda3D, Plotly); not official
submission/                   NASA Space Apps 2026 submission package
```

## 15. Limitations and scientific validation

### Validation evidence stored in the repository

| Check | Result | Source |
|---|---|---|
| Local SPICE ephemeris vs Horizons (3 sites × Sun/Earth, 14 days, 6-h steps) | Max elevation difference 1.36 × 10⁻⁵°; all samples within the 0.01° tolerance | `reports/validation/ephemeris_validation_20261115T0000.json` |
| LOLA vs LROC terrain horizon (10 points on the Shackleton rim, 6 skipped; 28 days) | Horizon RMS difference: median 0.71°, worst 4.40°. Sun-visible fraction agreement: median 99.9%, worst 95.5% | `reports/validation/terrain_cross_validation.json` |
| Globe marker geodesy | Partial | `reports/web_ui_consolidation/F10_GEODETIC_VALIDATION.md` |
| LOLA/LROC data quality | Assessment report | `docs/technical_reports/LOLA_LROC_QUALITY_ASSESSMENT_2026-11-14.md` |

### Known limitations

- **No ground-truth validation.** Illumination is validated component by component (ephemeris against Horizons, LOLA horizon against LROC). It has not been compared with published illumination maps or in-situ data. Horizons are limited to the profile distance.
- **Coordinate frames.** Several tools work in DEM row/column or raster-grid azimuth. The globe model frame is not validated, so results are not projected onto it.
- **Web UI vs Mission Engine.** Terrain-aware windows, the offline ephemeris and the solar, fleet, decision and P-System engines are reachable only through the orchestrator or CLI. The example configuration has most of them disabled.
- **First-order models.** Free-space link budget (Earth as a point, no ground-station schedule); single-node thermal model; preliminary rover and solar energy models that need user-supplied hardware parameters.
- **Data coverage.** Three sites. The LROC DTM covers only the Shackleton rim (about 5 × 5 km).
- **Site coordinate source.** `src/astronomy.py` cites a "NASA Lunar Surface Data Book, Rev. baseline, 2025-03-18, Table A2.1-1". That edition could not be found publicly, so the citation is unverified. The coordinates do fall inside the matching PGDA LOLA DEMs.
- **Engineering maturity.** HTTP only; use an HTTPS reverse proxy with `LUNAR_COOKIE_SECURE=1` beyond `127.0.0.1`. Only Python 3.14.8 has been tested. The horizon computation takes about 6–9 s and cannot be cancelled. `reports/web_runs/` grows without automatic clean-up. Stored reports contain absolute local paths. `--desktop` has not been verified on a real display.
- **P-System.** Tested only with real local processes on one machine. Behaviour over real Earth–Moon links is not verified.

## 16. NASA data acknowledgements

This project uses publicly available NASA data and services. NASA does not endorse this project.

- **NASA/JPL Horizons** On-Line Ephemeris System, Solar System Dynamics Group, Jet Propulsion Laboratory.
- **LOLA** high-resolution south pole site topography, NASA Goddard Space Flight Center Planetary Geodesy Data Archive (PGDA). Barker, M. K., et al. (2021), *Planetary and Space Science* 203, 105119, https://doi.org/10.1016/j.pss.2020.105119. Site numbering: Mazarico, E., et al. (2011), *Icarus* 211, 1066–1081, https://doi.org/10.1016/j.icarus.2010.10.030.
- **LROC NAC DTM** `NAC_DTM_ESALL_SR12`, Lunar Reconnaissance Orbiter Camera, NASA Planetary Data System (DTM produced by DLR; GeoTIFF by the LROC team, Arizona State University).
- **NAIF SPICE** generic kernels and the **JPL DE421** planetary ephemeris, NASA Navigation and Ancillary Information Facility.
- **Moon 3D model** from NASA's Scientific Visualization Studio (SVS 14959, based on LRO data; colour map from the CGI Moon Kit, SVS 4720). Credit: NASA's Goddard Space Flight Center.
- The **Lunar Reconnaissance Orbiter** mission, NASA Goddard Space Flight Center.

No NASA logos or insignia are used. Third-party software: three.js r186 (MIT, `src/ui_web/vendor/three/LICENSE`), Archivo font (SIL OFL, `src/ui_web/ui/fonts/OFL.txt`). Other references are in [`submission/OTHER_RESOURCES.md`](submission/OTHER_RESOURCES.md).

## 17. AI assistance disclosure

The repository history contains commits co-authored by **Claude (Anthropic) through Claude Code**, an AI coding assistant. The submission documents in `submission/`, this README and `REPOSITORY_UPDATE_REPORT.md` were drafted with the same assistant from the project's code and data. See [`submission/AI_USAGE_DISCLOSURE.md`](submission/AI_USAGE_DISCLOSURE.md). The exact share of AI-assisted code still has to be confirmed by the author.

The running application contains **no AI or machine-learning model**. Its results come from deterministic code operating on NASA data. No AI-generated images are used.

## 18. License

**No license file is present in this repository.** Until the author adds one, default copyright applies and no reuse rights are granted. Bundled third-party components keep their own licenses (three.js: MIT; Archivo font: SIL OFL 1.1). The NASA data files keep the terms set by their original providers.
