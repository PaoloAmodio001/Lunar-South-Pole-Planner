# Project Details — Lunar South Pole Planner

> **Status:** research and education prototype. Outputs are preliminary diagnostics. The software is **not flight-certified, not operationally validated, and not qualified for mission decisions.**
>
> **Status labels in this document:**
> - **IMPLEMENTED:** in the code and reachable in the official application or its documented CLI
> - **PARTIAL:** implemented with documented gaps, or not reachable from the Web UI
> - **EXPERIMENTAL:** working prototype tested only locally
> - **NOT VERIFIED:** claimed somewhere but not confirmed during this audit
> - **FUTURE:** not implemented

## 1. What the application does

Near the lunar south pole the Sun stays within a degree or two of the horizon, and the Earth rises and sets with the Moon's libration. Whether a location is lit, and whether it can talk directly to Earth, therefore depends on local terrain as much as on orbital geometry. Lunar South Pole Planner brings the relevant NASA data together in one local tool:

- Sun and Earth positions from **NASA/JPL Horizons**
- terrain from **NASA LRO**: LOLA 5 m/px site DEMs from NASA GSFC PGDA, and an LROC NAC stereo DTM from the PDS archive

It turns these inputs into illumination, Earth-visibility, terrain and surface-mobility diagnostics for three candidate sites:

| Site | Latitude | East longitude | LOLA DEM |
|---|---|---|---|
| Shackleton rim | −89.7668° | −171.87° | PGDA Site04 |
| Connecting Ridge | −89.4632° | −137.49° | PGDA Site01 |
| Nobile rim 1 | −85.4381° | 37.36667° | PGDA Site06 |

It serves three audiences from one local web server:

- **Public:** a 3D Moon globe with the candidate sites and live Sun/Earth ephemerides. No login.
- **Educators:** a free seven-chapter course with three depth levels, printable activities and labs that use the public APIs. No login, no personal data.
- **Mission planners:** a login-protected dashboard and "Mission Control" with the science tools and the Mission Engine.

## 2. How it works

1. **Ephemerides.** `src/astronomy.py` queries the Horizons API for the topocentric apparent azimuth and elevation of the Sun and Earth from a lunar surface point (`coord@301`). `src/local_ephemeris.py` computes the same quantities offline with Skyfield, the NAIF SPICE kernels and DE421.
2. **Terrain.** Raster modules read the LOLA and LROC GeoTIFFs with rasterio:
   - DEM audit (`data_quality`)
   - slope and roughness (`terrain_metrics`)
   - horizon profiles with a curved-Moon model (`terrain_horizon`, `horizon_analysis`)
   - LOLA LDEC/TOTERR quality metrics (`lola_local_quality`)
   - LOLA–LROC comparison (`lola_lroc_quality`)
3. **Visibility.**
   - The Web UI finds *geometric* operational windows where the Sun and the Earth are both above user thresholds (`mission_planning.find_operational_windows`, 1-hour steps).
   - `contact_windows.py` finds *terrain-aware* windows. It combines a DEM horizon profile, the grid-to-north azimuth offset derived from the raster CRS (`lunar_geometry`) and the local ephemeris.
4. **Engineering estimates.**
   - First-order free-space RF link budget (`communications`)
   - Single-node transient thermal model (`thermal_model`)
   - Terrain-aware A* rover route (`rover_planning`)
   - Physics-based route energy estimate (`rover_energy`)
   - Multi-rover allocation on the DEM (`multi_rover`)
   - Preliminary solar-power and battery model (`solar_energy_engine`)
5. **Mission Engine.** `src/mission_orchestrator.py` chains the enabled steps from a JSON configuration. It writes reproducible JSON and Markdown reports, and `mission_decision_engine` aggregates them conservatively. The Web UI can validate and run the example configuration in a subprocess.
6. **Web UI.** `src/ui_web/app.py` is a standard-library HTTP server with a fixed route whitelist. It serves the vendored three.js globe and the frontends, and protects the planner APIs with a scrypt-based login. Every science response names its module and source raster.

## 3. Scientific and engineering objectives

- Quantify how much of the time the Sun and the Earth are above the **geometric** horizon at each candidate site.
- Quantify how the **terrain** horizon changes that picture, using two independent NASA terrain products as a consistency check.
- Give first-order engineering context for surface operations: slopes, rover routes and their energy cost, link margins, and thermal behaviour.
- Keep every number traceable to its source data and module, and state explicitly what is not modelled.

## 4. NASA data and resources actually used

Full details, URLs and classification are in [`NASA_DATA_SOURCES.md`](NASA_DATA_SOURCES.md).

| Resource | Status in the project |
|---|---|
| NASA/JPL Horizons API | **Directly integrated**, live queries |
| LOLA high-resolution south pole site DEMs (NASA GSFC PGDA, LRO) | **Directly integrated**, local GeoTIFFs |
| LROC NAC DTM `NAC_DTM_ESALL_SR12` (LRO, NASA PDS) | **Directly integrated**, local GeoTIFF and PDS3 files |
| NAIF SPICE generic kernels + JPL DE421 | **Integrated**, in the Mission Engine and CLI tools only |
| NASA SVS LRO-based Moon GLB model | **Directly integrated**, for visualisation only |
| NASA Lunar Surface Data Book | **Referenced** for site coordinates. Edition **NOT VERIFIED** |
| LRO, Artemis and Horizons web pages | **Referenced**, as links in the Educators section |

## 5. Programming languages and technologies

- **Python 3.14** (only 3.14.8 has been tested): numpy, rasterio, pyproj, matplotlib, requests, Skyfield (used by the offline ephemeris; listed in `requirements.txt`).
- **JavaScript** (no framework, no build step) with **three.js r186** vendored in the repository. **HTML/CSS**.
- Python standard library for the HTTP server, the scrypt password hashing and the sessions. No web framework.
- **pytest** for the test suite: 309 test functions in 38 files.
- Optional: PySide6 desktop window (not verified on a real display); a P-System integration (experimental, section 6).

## 6. Main capabilities and their status

| Capability | Where | Status |
|---|---|---|
| Live Sun/Earth elevation and azimuth from Horizons, operational windows, ranking, error classification | Web UI (public API `/api/ephemerides`) | **IMPLEMENTED** (needs network) |
| 3D globe with the three candidate sites | Web UI | **IMPLEMENTED**. Marker geodetic check **PARTIAL** (Connecting Ridge has a possible ~4.6 km offset); results are not projected onto the globe |
| Educators section (7 chapters, 3 levels, labs on public APIs) | Web UI | **IMPLEMENTED** |
| DEM audit, slope/roughness, horizon profile, A* rover route and energy, LROC quality summary | Web UI (planner, login) | **IMPLEMENTED**. Inputs are DEM row/column, not geographic coordinates |
| Geometric site comparison (Sun/Earth) | Web UI (planner) | **IMPLEMENTED** (needs network) |
| Free-space link budget; single-node thermal model | Web UI (planner) | **IMPLEMENTED**, first-order models |
| Mission Engine run from the Web UI (example config, read-only) | Web UI (planner) | **IMPLEMENTED** |
| Offline Sun/Earth ephemeris (Skyfield + SPICE DE421), validated against Horizons | Mission Engine / CLI | **IMPLEMENTED**. Not in the Web UI |
| Terrain-aware illumination and Earth-contact windows | Mission Engine / CLI | **PARTIAL**. Not in the Web UI; not compared with published illumination maps |
| LOLA vs LROC horizon and Sun-visibility cross-validation | CLI | **IMPLEMENTED** (10 points on the Shackleton rim; 6 skipped) |
| Solar energy engine, mission decision engine | Mission Engine | **PARTIAL**. Preliminary and not validated; hardware parameters must be supplied; disabled in the example config |
| Multi-rover fleet planning on the DEM | Mission Engine | **PARTIAL**. Routes and assignments only, no time sequencing; disabled in the example config |
| Descent-hazard diagnostic raster | Mission Engine | **PARTIAL**. Labelled a prototype in the code |
| Single login for the planner section (scrypt, sessions, rate limiting) | Web UI | **IMPLEMENTED**. HTTP only; the login has no automated tests |
| P-System mission-record certification | Mission Engine | **EXPERIMENTAL**. Tested with real local P-System processes on one machine only; disabled by default; needs a separate P-System installation |
| Site scoring with DEM + ephemerides, science/engineering window ranking | Legacy interfaces only | **Not in the official app** |

### Quantitative evidence available in the repository

| Result | Value | Source file |
|---|---|---|
| Local SPICE vs Horizons, max elevation difference (3 sites × Sun/Earth, 14 days, 6-h steps) | 1.36 × 10⁻⁵°, all samples within the 0.01° tolerance | `reports/validation/ephemeris_validation_20261115T0000.json` |
| LOLA vs LROC Sun-visible fraction agreement (10 points, 28 days) | median 99.9%, worst 95.5% | `reports/validation/terrain_cross_validation.json` |
| LOLA vs LROC horizon RMS difference | median 0.71°, worst 4.40° | same file |
| Sun elevation above the geometric horizon, Shackleton, 15–29 Nov 2026 | 1.29° to 1.62° | `reports/validation/horizons_reference_20261115T0000.json` |
| Earth above the geometric horizon, Shackleton / Connecting Ridge / Nobile (same window, 6-h samples) | 79% / 79% / 98% of samples | same file |
| Test suite | 494 passed, 0 failed (recorded 2026-11-15) | Earlier test report (no longer in the repository) |

The test result was **not re-run** for this submission. The README notes that the login and error-handling changes made on the same day have no automated tests, and that the suite was not run after those changes. Treat the test count as **last recorded**, not as current.

## 7. Limitations

- **Not validated against ground truth.** Illumination is validated by component: the ephemeris against Horizons, and the LOLA horizon against LROC. It has not been checked against published illumination maps (for example Mazarico et al. 2011; Barker et al. 2021) or in-situ measurements. Horizons are limited to the profile distance (a few km in the cross-validation).
- **Coordinate frames.** Several modules work in raster-grid azimuths or DEM row/column. The globe model's frame is not validated against the DEMs, so results are not projected onto the globe.
- **Web UI vs Mission Engine.** Terrain-aware windows, the offline ephemeris, the solar-energy, fleet and decision engines and P-System are reachable only through the orchestrator or CLI. The example configuration has most of these steps disabled.
- **Models are first-order.** The link budget is free-space only: Earth is treated as a point, with no ground-station schedule, pointing or terrain blockage of the RF path in the Web UI. The thermal model has a single node. The rover energy model uses a constant per-metre consumption plus slope work. The solar engine needs user-supplied hardware parameters.
- **Data coverage.** There are three sites, and the LROC DTM covers only the Shackleton rim.
- **Engineering maturity.** There are no browser end-to-end tests and no TLS (an HTTPS reverse proxy is required beyond `127.0.0.1`). Only Python 3.14.8 has been tested. Reports contain absolute local paths.
- **Network dependence.** Live ephemerides and site comparison need access to Horizons. There is no offline fallback in the Web UI.

## 8. Potential impact on lunar exploration

- **For mission and payload teams:** a quick, transparent first look at power (sunlight), communications (Earth line-of-sight) and mobility (slopes and routes) at south-polar sites. It is built only on public NASA data and keeps the source of every number visible. It is meant to complement, not replace, certified mission-analysis tools.
- **For education and outreach:** the Educators section and the public globe let students work with live NASA/JPL Horizons data and real LRO terrain. They show why polar lighting differs from the rest of the Moon, and why terrain makes it hard to choose a site.
- **For open science:** the cross-checks between independent sources (Horizons vs SPICE, LOLA vs LROC) make data consistency visible. The design can be extended to more PGDA sites and to published illumination products.

## 9. Future development (FUTURE: not implemented)

- Terrain-aware Sun/Earth windows and the offline ephemeris in the Web UI.
- Validation against published LOLA-based illumination studies and products.
- More PGDA south-pole sites (Site07, Site11, Site20, Site23, Haworth, Shoemaker, DM2).
- Geodetic registration of the globe model so results can be shown on it.
- HTTPS deployment, browser end-to-end tests and automated tests for the login.

## 10. Team

- Presented as **P-System Space Group** (from the project's existing presentation `lunar.pptx`). **Human confirmation needed** of the team name, member names and Space Apps team page.
