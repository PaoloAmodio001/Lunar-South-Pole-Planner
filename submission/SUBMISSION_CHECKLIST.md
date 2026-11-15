# Submission Checklist — NASA Space Apps Challenge 2026

Prepared on 2026-11-15. ✅ = done and verified · ⚠️ = needs human action or confirmation · ❌ = not done.

## Automatic validation (performed)

| Check | Result |
|---|---|
| Project Summary is 50–200 words | ✅ 168 words (`PROJECT_SUMMARY.md`) |
| Presentation has ≤ 7 slides | ✅ 7 slides (PPTX and PDF) |
| PPTX file structure | ✅ passes the OOXML validator (schema, relationships, content types) |
| PDF exists and matches the PPTX | ✅ 7 pages, 16:9. Generated from the same slide specification (`tools/build_deck.py`) |
| URLs are complete | ✅ all external URLs are full `https://` links. The only `http://` links are the local server addresses `127.0.0.1:8765` in the demo script |
| NASA URLs checked online | ✅ Horizons API docs, PGDA product 78, NAIF kernel directories (each file), LROC SR12 product page, NASA SVS 14959 and 4720, NASA 3D Resources |
| NASA resources classified (integrated / CLI-only / referenced / unused) | ✅ `NASA_DATA_SOURCES.md` |
| Technical descriptions match the code | ✅ checked by reading the source and `mission_config.example.json` (not by running the app) |
| AI usage disclosed | ✅ `AI_USAGE_DISCLOSURE.md` (extent of AI use in the code needs ⚠️ confirmation) |
| No AI-generated images; no NASA logos or insignia | ✅ all figures are matplotlib renders of project data |
| No flight-certification or operational-validation claims | ✅ stated as a prototype on slide 1, in the summary and in the details |
| Existing application unchanged | ✅ SHA-256 of all 747 project files (outside `.venv`, `.git`, `backups`, `node_modules`, archives) is identical before and after. `git status` differs only by the new `submission/` folder |
| Backup before changes | ✅ `backups/nasa-submission-20261115-201943/project-before-submission.tar.gz` (1.6 GB, includes `.git` and data; excludes `.venv`, `backups/`, root `*.tar.gz` archives, `node_modules`), plus `sha256-before.txt` and `git-status.txt` |
| Nothing committed, pushed, uploaded or published | ✅ |

## Capability verification summary

| Capability | Status |
|---|---|
| Horizons integration (Sun/Earth az/el, windows) | ✅ VERIFIED in code and recorded output. Live run **NOT VERIFIED** during preparation |
| Offline SPICE ephemeris vs Horizons | ✅ VERIFIED (stored report, all within tolerance) |
| LOLA / LROC terrain integration | ✅ VERIFIED (code + data files + stored reports) |
| Terrain-aware Sun/Earth windows | ⚠️ PARTIAL: Mission Engine / CLI only |
| 3D globe site markers | ⚠️ PARTIAL (F10 geodetic validation) |
| Solar energy, decision engine, fleet, descent hazard | ⚠️ PARTIAL / preliminary |
| P-System integration | ⚠️ EXPERIMENTAL (local only) |
| Test suite | ⚠️ last recorded 494 passed. **NOT re-run**; the login has no tests |
| Web UI working end-to-end in a browser | ⚠️ **NOT VERIFIED** in this preparation |

## Requires human action or confirmation ⚠️

1. **Team name and members.** The deck says "P-System Space Group", taken from the existing `lunar.pptx`. Confirm it and add member names if the Space Apps form needs them.
2. **Challenge selection.** Pick the Space Apps 2026 challenge this project answers. The challenge statement was not available in the repository, so the materials do not name it.
3. **AI usage extent in the code.** Confirm or edit the suggested statement in `AI_USAGE_DISCLOSURE.md` §2.
4. **Site-coordinate source.** `src/astronomy.py` cites a "NASA Lunar Surface Data Book, Rev. baseline, 2025-03-18, Table A2.1-1". This edition could not be found online. Confirm the document.
5. **Globe model provenance.** Confirm that `Moon_NASA_LRO_8k_Topo_Small.glb` was downloaded from NASA SVS 14959, and credit "NASA's Goddard Space Flight Center".
6. **Live demo rehearsal.** Run `./start.sh`, follow `DEMONSTRATION_SCRIPT.md` and check every UI step.
7. **Screenshots.** Capture the five UI screenshots listed in `DEMONSTRATION_SCRIPT.md`, and optionally add one to the deck by replacing a chart on slide 3 or 5. They were not captured, because the app was not run during preparation.
8. **Re-run the test suite** if you want to quote a current test count: `.venv/bin/python -m pytest -q`.
9. **Repository / demo link** for the Space Apps project page: the repository is local only; no public URL is recorded.
10. **Review the citations' author lists** in `OTHER_RESOURCES.md`.
11. **Video** (if the challenge requires one): `video/` holds work-in-progress render scripts only. It is not part of this package.

## Package contents

```
submission/
├── PROJECT_SUMMARY.md
├── PROJECT_DETAILS.md
├── NASA_DATA_SOURCES.md
├── OTHER_RESOURCES.md
├── AI_USAGE_DISCLOSURE.md
├── TECHNICAL_ARCHITECTURE.md
├── DEMONSTRATION_SCRIPT.md
├── SUBMISSION_CHECKLIST.md
├── Lunar_South_Pole_Planner_NASA_2026.pptx
├── Lunar_South_Pole_Planner_NASA_2026.pdf
├── assets/      figures rendered from project data + figure_stats.json
└── tools/       make_figures.py, build_deck.py, deck_print.html (rebuild with the commands below)
```

Rebuild:

```bash
.venv/bin/python -I submission/tools/make_figures.py "$PWD"
python3 -I submission/tools/build_deck.py "$PWD"        # needs python-pptx, Pillow
google-chrome --headless=new --no-pdf-header-footer \
  --print-to-pdf=submission/Lunar_South_Pole_Planner_NASA_2026.pdf \
  "file://$PWD/submission/tools/deck_print.html"
```
