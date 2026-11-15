# Other (non-NASA) Resources

These resources are used by the official application or by the submission build. Legacy-only dependencies are listed separately at the end.

## Software libraries used by the official application

| Resource | Version | URL | Use |
|---|---|---|---|
| Python | 3.14.8 | https://www.python.org/ | Language and runtime, including the standard-library HTTP server and scrypt hashing |
| NumPy | 2.5.4 | https://numpy.org/ | Numerical arrays in all science modules |
| rasterio | 1.5.2 | https://rasterio.readthedocs.io/ | Reading GeoTIFF/PDS rasters (LOLA, LROC) |
| pyproj (PROJ) | 3.8.0 | https://pyproj4.github.io/pyproj/ | Lunar polar stereographic ↔ geographic transforms (`lunar_geometry.py`) |
| matplotlib | 3.11.2 | https://matplotlib.org/ | Report plots (orchestrator) and the submission figures |
| Requests | 2.34.2 | https://requests.readthedocs.io/ | HTTPS calls to the Horizons API |
| Skyfield | 1.55 | https://rhodesmill.org/skyfield/ | Offline ephemeris with the SPICE kernels (`local_ephemeris.py`) |
| three.js | r186 (vendored) | https://threejs.org/ | 3D globe in the browser |
| pytest | 9.1.1 | https://docs.pytest.org/ | Test suite |
| PySide6 (optional) | 6.12.0 | https://doc.qt.io/qtforpython-6/ | Optional desktop window (`--desktop`), not verified on a real display |

## Scientific references cited by the project

- Barker, M. K., Mazarico, E., Neumann, G. A., Smith, D. E., Zuber, M. T., Head, J. W. (2021). *Improved LOLA elevation maps for south pole landing sites: Error estimates and their impact on illumination conditions.* Planetary and Space Science 203, 105119. https://doi.org/10.1016/j.pss.2020.105119
- Mazarico, E., Neumann, G. A., Smith, D. E., Zuber, M. T., Torrence, M. H. (2011). *Illumination conditions of the lunar polar regions using LOLA topography.* Icarus 211(2), 1066–1081. https://doi.org/10.1016/j.icarus.2010.10.030
- Oberst, J., et al. (2010). *Apollo 17 landing site topography from LROC NAC stereo data — first analysis and results.* 41st LPSC, abstract #2051. https://www.lpi.usra.edu/meetings/lpsc2010/pdf/2051.pdf (cited in the LROC DTM README)

The author lists for Barker et al. and Mazarico et al. are given from standard bibliographic records. The project's README copies cite them as "Barker et al." and "Mazarico, E., et al.". **Please confirm the author lists before publication.**

## Non-NASA data producers

- **German Aerospace Center (DLR), Institute of Planetary Research** produced the `NAC_DTM_ESALL_SR12` DTM from LROC NAC stereo images. The DTM was funded by the ESA Lunar Lander project and is distributed through the NASA PDS LROC archive by the LROC team (Arizona State University). See `data/terrain/reference-lroc/NAC_DTM_ESALL_SR12.LBL`.

## Optional companion project

- **P-System** is a separate distributed-ledger project used, optionally, to certify mission records (`src/psystem_adapter.py`). It is not part of this repository and is expected at `~/Github P-system` or `$PSYSTEM_HOME`. The integration is experimental. **Human confirmation needed:** its public URL and licence, if it is to be cited.

## Tools used only to build the submission package

| Tool | Use |
|---|---|
| python-pptx 0.6.18 (https://python-pptx.readthedocs.io/) | Writes the `.pptx` |
| Google Chrome (headless) | Prints the HTML version of the deck to PDF (LibreOffice was not available) |
| Pillow (https://python-pillow.org/) | Image cropping for the title slide |
| Liberation Sans font | Metric-compatible substitute for Arial when rendering the PDF and figures |
| Claude Code (Anthropic) | AI assistant that drafted the materials (see `AI_USAGE_DISCLOSURE.md`) |

## Legacy-only dependencies (NOT used by the official application)

Streamlit, pandas, Plotly, Panda3D, panda3d-gltf, trimesh and pyglet appear in `requirements-legacy.txt` and are used only by the archived interfaces in `legacy/`. The stand-alone Plotly HTML exports in `reports/visualization/` embed bundled third-party JavaScript, including MapLibre and map-tile URLs. They are archived outputs and are not served by the official application.
