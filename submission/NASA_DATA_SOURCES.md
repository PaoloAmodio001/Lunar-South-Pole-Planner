# NASA Data and Resources

This document lists every NASA resource found in the project. Each resource is classified by how the project uses it:

| Classification | Meaning |
|---|---|
| **DIRECTLY INTEGRATED** | The code reads the data from a file in the repository or queries the service at run time |
| **INTEGRATED: OPTIONAL / CLI ONLY** | The code uses it, but only through the Mission Engine or a command-line tool, not in the default Web UI flow |
| **REFERENCED ONLY** | Cited in code comments, documentation or UI links. The software does not load the data |
| **NOT USED BY THE OFFICIAL APP** | Present in the repository but used only by archived (legacy) interfaces or by video-production scripts |

The classification comes from reading the source code (`src/`, `src/ui_web/`) and `mission_config.example.json` on 2026-11-15. URLs were checked on the same date.

---

## 1. NASA/JPL Horizons System (API) — DIRECTLY INTEGRATED

- **Official name:** JPL Horizons On-Line Ephemeris System, Horizons API (Solar System Dynamics, NASA Jet Propulsion Laboratory)
- **Official URLs:**
  - Service: https://ssd.jpl.nasa.gov/horizons/
  - API endpoint used by the code: https://ssd.jpl.nasa.gov/api/horizons.api
  - API documentation: https://ssd-api.jpl.nasa.gov/doc/horizons.html
- **How it is used:** Live HTTPS queries (`EPHEM_TYPE=OBSERVER`, `CENTER='coord@301'`, `COORD_TYPE=GEODETIC`, `QUANTITIES='4,20'`) return the apparent azimuth, elevation and range of the Sun (`10`) and Earth (`399`) seen from a point on the Moon. The Web UI uses them to plot Sun and Earth elevation and to find operational windows where both are above user thresholds (1-hour steps). They also feed the site comparison tool. Horizons is the reference for validating the offline ephemeris (section 4).
- **Relevant files:**
  - `src/astronomy.py`: `HORIZONS_URL`, `query_observations`, `probe_horizons`, error classification
  - `src/ui_web/app.py`: `GET /api/ephemerides` (public) and Horizons status in `/api/services`
  - `src/site_comparison.py`: `POST /api/science/site-comparison`
  - `src/ephemeris_validation.py`: Horizons vs local SPICE comparison
  - `src/mission_orchestrator.py`: `astronomy` step (`source: "horizons"`; **disabled** in `mission_config.example.json`)
- **Recorded evidence:** `reports/validation/horizons_reference_20261115T0000.json` (3 sites × Sun/Earth, 14 days, 6-hour steps) and `tests/data/horizons_three_sites_20261115.json`.
- **Requires network access.** The Web UI never substitutes demonstration data when Horizons is unreachable. It shows a classified error instead.

## 2. LOLA high-resolution topography for lunar south pole sites (NASA GSFC PGDA) — DIRECTLY INTEGRATED

- **Official name:** *High-Resolution LOLA Topography for Lunar South Pole Sites*, NASA Goddard Space Flight Center Planetary Geodesy Data Archive (PGDA). Derived from the Lunar Orbiter Laser Altimeter (LOLA) on NASA's Lunar Reconnaissance Orbiter (LRO).
- **Official URLs:**
  - Product page: https://pgda.gsfc.nasa.gov/products/78
  - Data directory: https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/
  - README: https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/README
  - Reference paper: Barker, M. K., et al. (2021), *Improved LOLA elevation maps for south pole landing sites: Error estimates and their impact on illumination conditions*, Planetary and Space Science 203, 105119. https://doi.org/10.1016/j.pss.2020.105119
  - Site numbering: Mazarico, E., et al. (2011), Icarus 211, 1066–1081. https://doi.org/10.1016/j.icarus.2010.10.030
- **Files in the repository** (`data/terrain/official-lola/`, polar stereographic, 5 m/pixel, MOON_ME/DE421 frame):
  - `Site04_final_adj_5mpp_surf.tif`: Shackleton rim elevation. This is the main DEM.
  - `Site04_final_adj_5mpp_ldec.tif`: LOLA returns per pixel.
  - `Site04_final_adj_5mpp_toterr.tif`: total elevation uncertainty (RMS).
  - `Site01_final_adj_5mpp_surf.tif`: Connecting Ridge elevation.
  - `Site06_final_adj_5mpp_surf.tif`: Nobile rim 1 elevation.
  - `Clones/Site04/`: clone DEMs.
  - `metadata/LOLA_5mpp_README`: a copy of the PGDA README.
  - The point clouds `data/terrain/source/Site0{1,4,6}_final_adj.xyzi` are present but are not read by the official application.
- **How it is used:** DEM audit, slope and roughness, horizon profiles with a curved-Moon model, terrain-aware illumination and Earth-contact windows, A* rover routing, multi-rover planning, descent-hazard diagnostics, site selection, and LDEC/TOTERR local quality metrics.
- **Relevant files:** `src/ui_web/science_api.py` (fixed raster catalogue), `src/terrain_horizon.py`, `src/horizon_analysis.py`, `src/terrain_metrics.py`, `src/data_quality.py`, `src/rover_planning.py`, `src/multi_rover.py`, `src/contact_windows.py`, `src/terrain_cross_validation.py`, `src/lola_local_quality.py`, `src/lola_lroc_quality.py`, `src/descent_hazard_detection.py`, `mission_config.example.json`.

## 3. LROC NAC Digital Terrain Model NAC_DTM_ESALL_SR12 (NASA PDS archive) — DIRECTLY INTEGRATED

- **Official name:** *Shackleton Crater Rim Potential Landing Site for ESA Lunar Lander DTM*, product `NAC_DTM_ESALL_SR12`. Data set `LRO-L-LROC-5-RDR-V1.0`, volume `LROLRC_2001`, from the Lunar Reconnaissance Orbiter Camera (LROC) Narrow Angle Camera. This is a NASA Planetary Data System (PDS3) product. The DTM was produced by DLR from LROC NAC stereo images, and the LROC team at Arizona State University generated the GeoTIFF version.
- **Official URLs:**
  - Product page (LROC team): https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_DTM_ESALL_SR12
  - PDS Imaging Node, LROC RDR archive: https://pds.mcp.nasa.gov/data/index.html#/data/store/img/lunar_reconnaissance_orbiter/pds4/lroc/lro-l-lroc-5-rdr/LROLRC_2001/DATA/SDP/NAC_DTM/ (the older `lroc.sese.asu.edu` links in the bundled README now redirect)
- **Files in the repository:**
  - `data/terrain/reference-lroc/NAC_DTM_ESALL_SR12.TIF` and `.LBL` (2 m/pixel DTM and PDS3 label)
  - `data/terrain/reference-lroc/quality/NAC_DTM_ESALL_SR12_CONF.TIF` and `NAC_DTM_ESALL_SR12_README.TXT`
  - `data/terrain/reference-lroc/source-check/NAC_DTM_ESALL_SR12_CONF_original.IMG` (original PDS3 confidence raster)
  - Files under `data/terrain/processed/` are project-derived masks and audits, not NASA products.
- **How it is used:** An independent second DEM over the Shackleton rim. The project compares LOLA and LROC elevations, horizon profiles and Sun-visibility fractions, builds an LROC quality mask, and uses it as an optional Science-tool raster in the Web UI.
- **Relevant files:** `src/ui_web/science_api.py`, `src/terrain_cross_validation.py`, `src/lola_lroc_quality.py`, `src/lroc_quality_mask.py`, `src/confidence_validation.py`, `mission_config.example.json` (`lola_lroc_quality`, `descent_hazard_detection`).
- **Coverage limit:** It covers only the Shackleton rim area (about 5 × 5 km). It has no overlap with Connecting Ridge or Nobile.

## 4. NAIF SPICE generic kernels and JPL DE421 planetary ephemeris — INTEGRATED: OPTIONAL / CLI ONLY

- **Official name:** NASA Navigation and Ancillary Information Facility (NAIF) SPICE generic kernels, and the JPL Development Ephemeris DE421.
- **Official URLs (each file was checked in the listing):**
  - `de421.bsp`: https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/a_old_versions/
  - `moon_pa_de421_1900-2050.bpc`: https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/
  - `pck00008.tpc`: https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/a_old_versions/
  - `moon_080317.tf`: https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/
  - NAIF home: https://naif.jpl.nasa.gov/naif/
- **Files in the repository:** `de421.bsp` (project root) and `data/terrain/kernels/`.
- **How it is used:** Offline topocentric Sun and Earth positions from a lunar site, computed through Skyfield in the MOON_ME_DE421 frame. They are used in the Mission Engine (`astronomy.source = "local"`), in terrain-aware contact windows, in the LOLA/LROC cross-validation, and in the Horizons comparison. The Web UI ephemeris panel uses Horizons, not these kernels.
- **Relevant files:** `src/local_ephemeris.py`, `src/contact_windows.py`, `src/ephemeris_validation.py`, `src/terrain_cross_validation.py`.
- **Validation evidence:** `reports/validation/ephemeris_validation_20261115T0000.json`. Over 3 sites × Sun/Earth, 14 days in 6-hour steps, the maximum elevation difference from Horizons is 1.36 × 10⁻⁵°, and every sample is within the 0.01° tolerance.
- **Dependency note:** `skyfield==1.55` is listed in `requirements.txt` (added on 2026-11-15 during the repository update) and is installed in the project venv.

## 5. NASA SVS "Moon 3D Models for Web, AR, and Animation" (LRO-based globe) — DIRECTLY INTEGRATED (visualisation only)

- **Official name:** *Moon 3D Models for Web, AR, and Animation*, NASA Scientific Visualization Studio (SVS), NASA Goddard Space Flight Center. Built from LRO imagery and topography. The color map comes from the CGI Moon Kit (SVS 4720).
- **Official URLs:**
  - https://svs.gsfc.nasa.gov/14959/ (lists the file `Moon_NASA_LRO_8k_Topo_Small.glb`)
  - CGI Moon Kit: https://svs.gsfc.nasa.gov/4720
  - Requested credit: NASA's Goddard Space Flight Center
- **File:** `data/terrain/global/Moon_NASA_LRO_8k_Topo_Small.glb`. The file name matches the SVS listing. The repository does not record where or when the file was downloaded. **Human confirmation needed.**
- **How it is used:** The 3D globe in the Web UI (three.js), with markers for the candidate sites. Analysis results are **not** projected onto the globe, because the model's frame has not been validated against the DEM grid. The marker check in `reports/web_ui_consolidation/F10_GEODETIC_VALIDATION.md` is PARTIAL.
- **Relevant files:** `src/ui_web/app.py` (`STATIC_ROUTES`), `src/ui_web/main.js`, `src/ui_web/ui/globe-markers.js`.

## 6. NASA Lunar Surface Data Book — REFERENCED ONLY

- **Use:** A code comment in `src/astronomy.py` attributes the three site coordinates (`SITES`) to the *NASA Lunar Surface Data Book, Rev. baseline, 2025-03-18, Table A2.1-1; coordinates derived from PGDA south-pole LOLA DEMs*.
- **Verification status: NOT VERIFIED.** A public edition dated 2025-03-18, and the table it cites, could not be found online. The publicly indexed baseline is ACD-50044 (October 2022): https://ntrs.nasa.gov/citations/20220015275. **Human confirmation needed** of the exact document edition and table.
- The coordinates do fall inside the matching PGDA LOLA site DEMs (Site04, Site01, Site06), as shown on slide 5 of the deck.

## 7. Other NASA web pages — REFERENCED ONLY (links in the Educators section)

- Lunar Reconnaissance Orbiter mission site: https://lunar.gsfc.nasa.gov/ (`src/ui_web/index.html`)
- NASA Artemis program: https://www.nasa.gov/humans-in-space/artemis/ (`src/ui_web/index.html`)
- NASA/JPL Horizons home page: https://ssd.jpl.nasa.gov/horizons/ (`src/ui_web/index.html`)

## 8. Present in the repository but NOT USED BY THE OFFICIAL APP

| File(s) | Apparent origin | Used by |
|---|---|---|
| `data/models/nasa/*.glb` (LRO, Apollo Lunar Module, Astronaut, Gateway Core) | NASA 3D Resources (https://science.nasa.gov/3d-resources/). Provenance is not recorded in the repo | Archived legacy viewers only (`legacy/`) |
| `video/data/assets/earth_nasa_visible_earth.jpg` | NASA Visible Earth (by file name). Provenance is not recorded | Video-production scripts only |
| `data/terrain/source/*.xyzi` | PGDA LOLA point clouds | Not read by `src/` |

## What the project does NOT use

These datasets are **not** integrated. Do not list them as used:

- LOLA RDR/GDR products from the PDS Geosciences Node (the project uses the PGDA site DEMs instead)
- Diviner thermal data, LAMP, Mini-RF, LEND or any other LRO instrument data besides LOLA and LROC NAC
- Published illumination maps (for example PGDA illumination products), PSR maps or ice-detection data
- The NASA Deep Space Network schedule or ground-station data
- Any NASA API other than Horizons

## Data used in the submission figures

All figures in `submission/assets/` were generated for this submission by `submission/tools/make_figures.py`. That script only reads the files in sections 1–4. No image is AI-generated, and no NASA logo or insignia is used.
