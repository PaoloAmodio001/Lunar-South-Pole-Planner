# Repository Update Report — Lunar South Pole Planner

Date: 2026-11-15 · Purpose: prepare the public repository for NASA Space Apps Challenge 2026 evaluation.
When the report was written, nothing had been committed, staged, pushed or published. **Update (2026-11-15):** the author later authorised publication. The commits are listed in [§12](#12-publication-record).

## 1. Initial state

| Item | Value |
|---|---|
| Directory | `/home/paolo/Lunar-South-Pole-Planner` |
| Branch / remote | `main`, `origin` = `https://github.com/PaoloAmodio001/Lunar-South-Pole-Planner.git` |
| Sync with `origin/main` | In sync: 0 unpushed commits (HEAD `f056381`). Everything newer exists only in the working tree. |
| Modified tracked files | 21 (`README.md`, `mission_config.example.json`, 7 modules in `src/`, 10 Web UI files, 4 tests): +3562 / −138 lines |
| Untracked files | 108, including 7 new science modules, auth/login/dashboard, Educators UI, `start.sh`, 3 docs, 3 test files + data, `reports/validation/`, `submission/`, `video/` and two presentation files at the root |
| Tracked content | 295 files, about 867 MB (mostly NASA terrain data, already on GitHub). Largest file 77.7 MB (< 100 MB GitHub limit). |
| Conflicts | None. There are no merge or rebase operations in progress. |
| License | No `LICENSE` file |

## 2. Backup

`backups/repo-update-20261115-223139/` (the `backups/` folder is git-ignored) contains:

- copies of `README.md`, `.gitignore`, all `requirements*.txt`, `pytest.ini`, `start.sh`, `mission_config.example.json`, `SCIENCE_STATUS.txt`;
- copies of `submission/*.md` and `docs/*.md`;
- `working-tree.diff` (all uncommitted changes to tracked files), `git-status.txt`, `untracked-files.txt`;
- `untracked-files.tar.gz`: all untracked files except the `.pptx`/`.pdf` decks, which are unchanged on disk.

## 3. Files updated

| File | Change |
|---|---|
| `README.md` | Rewritten in English with the 18 required sections. Content comes from the code, `mission_config.example.json`, the stored validation reports and the audited `submission/` docs. The numbers quoted were re-checked against the JSON reports. |
| `.gitignore` | Added: `*.key`, `*.pem`, `reports/psystem_local/` (the P-System local cluster writes private keys there); `*.db`, `*.sqlite*`; editor/OS files; `video/`; the two root presentation drafts. The presentation rule was removed later, at the author's request (see §12). |
| `requirements.txt` | Added `skyfield==1.55`. `src/local_ephemeris.py` imports it at run time (used by `contact_windows`, `terrain_cross_validation`, `ephemeris_validation` and `astronomy.source="local"`). Before this change it was listed only in the dev requirements. Same version as installed in `.venv`. |
| `requirements-dev.txt` | `skyfield` line replaced by a comment, because it is now inherited from `requirements.txt`. |
| `submission/TECHNICAL_ARCHITECTURE.md`, `submission/PROJECT_DETAILS.md` | Removed references to `documentation/REPORT_TEST.md`, which no longer exists in the repository (a copy is in the system Trash). Updated the skyfield dependency note. |
| `submission/NASA_DATA_SOURCES.md` | Updated the skyfield dependency note. |

No scientific code, algorithm, data file, model or test was modified.

## 4. Files added

| File | Content |
|---|---|
| `docs/README_IT.md` | The previous Italian README, preserved. It has a header note, links adjusted for its new location, and the dead `documentation/REPORT_INTEGRAZIONE.md` reference replaced by a note. |
| `REPOSITORY_UPDATE_REPORT.md` | This report |

## 5. Ready to be added to the repository (currently untracked, not ignored)

After the `.gitignore` update, `git add -A` would add **76 new files (about 17.8 MB)** plus the modified tracked files, all of them project work:

- `src/`: `contact_windows.py`, `ephemeris_validation.py`, `local_ephemeris.py`, `mission_decision_engine.py`, `psystem_cluster.py`, `solar_energy_engine.py`, `terrain_cross_validation.py`
- `src/ui_web/`: `auth.py`, `auth_admin.py`, `dashboard.html`, `dashboard.js`, `login.html`, `session.js`, `ui/educator.css`, `ui/educator.js`, `ui/portal.css`
- `start.sh`, `docs/EDUCATORS.md`, `docs/MISSION_PLANNERS.md`, `docs/solar_energy_engine.md`, `docs/README_IT.md`
- `tests/test_local_ephemeris_and_windows.py`, `tests/test_multi_rover_dem.py`, `tests/test_psystem_integration.py` (skips when P-System is absent), `tests/data/horizons_three_sites_20261115.json`
- `reports/validation/`: the validation evidence cited in the README
- `submission/`: the complete Space Apps package (docs, deck `.pptx` + `.pdf`, figures, rebuild tools)
- `REPOSITORY_UPDATE_REPORT.md`, plus the modified tracked files listed in §1 and §3

## 6. Files excluded and why (all still on disk)

| Excluded | Reason |
|---|---|
| `.venv/`, `__pycache__/`, `.pytest_cache/`, `node_modules/` | Environment and caches (already ignored) |
| `backups/` (3.2 GB), `*.bak*`, `*.before-*`, `*.backup-*`, root `np`, `rasterio` | Local backups and accidental files (already ignored) |
| `logs/`, `*.log`, `reports/web_runs/` | Logs and per-run Web UI output (already ignored) |
| `*.key`, `*.pem`, `reports/psystem_local/` | Private keys written by `src/psystem_cluster.py` (new rule) |
| `*.db`, `*.sqlite*` | Local databases (new rule). The auth store already lives outside the repo, in `~/.config/lunar-mission-control/`. |
| `video/` (27 MB) | Video work in progress: Blender scripts with a hard-coded `/home/...` path, generated `.npy`/`.png` data, render previews, fonts, and an Earth image whose provenance is not recorded. Not part of the submission. |
| `LUNAR_P_SYSTEM_PRESENTATION.pdf`, `P-System Space Group · with P-System technology (1).pptx` | Presentation drafts at the root. The `(1)` file name suggests a browser-download duplicate. The official deck is in `submission/`. **Update:** published at the author's request in commit `6a546c9`, under their original file names. The two `.gitignore` lines were removed. The `.pptx` was later renamed to `P-System Space Group · with P-System technology.pptx`. |

Large datasets: the NASA terrain data (about 870 MB) is **already tracked and pushed**. No file exceeds GitHub's limit, so nothing was removed or untracked. The download sources are documented in `submission/NASA_DATA_SOURCES.md` and summarised in README §4.

## 7. Documentation updated

- README: English, complete (overview → license), with status labels and limitations.
- The submission docs were kept and corrected where they were inaccurate (dead file reference, dependency note).
- The module docs `docs/MISSION_PLANNERS.md`, `docs/EDUCATORS.md` and `docs/solar_energy_engine.md` stay **in Italian**. The README marks them as such.

## 8. Checks performed and results

| Check | Method | Result |
|---|---|---|
| Git state, remote, sync | `git status`, `git rev-list` | OK, see §1 |
| Secrets / credentials | Regex scan of every untracked file and of the working-tree diff (API keys, tokens, private-key headers, AWS/GitHub/OpenAI key patterns, hard-coded passwords) | **None found.** Matches were only variable names such as `api_token` and `csrf_token`. No `.key`/`.pem`/`.db` file is tracked. |
| Personal data | Search for the author's e-mail in untracked files | Not found. The author's name appears in the root presentation PDF, which the author later chose to publish (`6a546c9`). |
| Absolute local paths | grep for `/home/` | Found in `reports/validation/terrain_cross_validation/*.json` and in 1 tracked file. This is already documented as a known limitation; the files were not edited because they are evidence. |
| Internal links | Every relative link and in-page anchor in `README.md`, `docs/README_IT.md`, `submission/*.md` resolved on disk | All resolve |
| Dependencies vs imports | Third-party imports in `src/`, `tests/`, `scripts/` compared with the requirements files | Found and fixed the missing `skyfield`. `qgis` (`src/style_descent_risk_map.py`, a QGIS-console script) and `PySide6` (optional) are not in `requirements.txt` by design. `submission/tools` needs `python-pptx`, `Pillow` and `lxml`, which are documented in `SUBMISSION_CHECKLIST.md`. |
| Large files | `du` of tracked and untracked files | Largest 77.7 MB; to be added: 17.8 MB |
| Documentation matches the code | Module docstrings, routes, config flags and validation JSON read directly | README claims checked: rover slope limit, multi-rover overlaps, contact-window link budget, enabled config steps, three.js r186, ephemeris max difference 1.355 × 10⁻⁵°, LOLA/LROC agreement 0.9985 |
| Test inventory | `grep` | 38 test files, 309 `test_` functions. The P-System integration test skips when P-System is absent. |
| **Test suite execution** | — | **Not run.** The project's standing rules forbid pytest, lint, `py_compile` and live server checks. The README says the suite was not re-run for this update. |
| **Application start / UI** | — | **Not run**, for the same reason. The installation instructions were checked by reading `start.sh` and `app.py`, not by a clean install. |

## 9. Problems still present

1. **No LICENSE.** Without one, the public repository grants no reuse rights. The author must choose a license (e.g. MIT, Apache-2.0); this cannot be decided on their behalf.
2. **Test result is not current.** The last recorded run (494 passed) predates later changes, and its report is no longer in the repo. Run `.venv/bin/python -m pytest -q` before quoting a number.
3. **The login has no automated tests, and there are no browser end-to-end tests.**
4. **No UI screenshots exist.** The app was not run. `submission/DEMONSTRATION_SCRIPT.md` lists the five to capture.
5. **Unconfirmed items** (already listed in `submission/SUBMISSION_CHECKLIST.md`): team name, Space Apps challenge, extent of AI use in the code, the Lunar Surface Data Book citation, and the GLB provenance (SVS 14959).
6. **Tracked dev artefacts** at the root (`.descent_integration_check.json`, `.mission_audit_20261028.json`, `SCIENCE_STATUS.txt`, which is outdated and has literal `\n`). They were left tracked because untracking needs a git operation; consider removing them in the commit.
7. **The module docs are in Italian** (`docs/MISSION_PLANNERS.md`, `docs/EDUCATORS.md`, `docs/solar_energy_engine.md`, technical reports). The README is in English.
8. **`src/style_descent_risk_map.py`** imports `qgis` and runs only inside QGIS. It is not documented as such in its file.
9. The clone is about 870 MB because the terrain data is committed. This is acceptable for GitHub, but slow.

## 10. Incomplete activities

- Running the test suite and starting the app (excluded by the standing rules, see §8).
- A clean-venv installation test of `requirements.txt` on a fresh machine.
- Translating the Italian module docs.
- Screenshots and video.

## 11. Publication readiness (as assessed before publication)

**Ready for review, not yet for publication.** The repository content is organised, documented and checked for secrets. Before publishing, the author should:

1. Review `git status` and the new `README.md`.
2. Decide on the two root presentation files (§6) and add a `LICENSE` (§9.1).
3. Optionally run the test suite and capture screenshots.
4. Give **explicit authorisation** for the commit and push, which were not performed.

Suggested commands, for after authorisation only:

```bash
git add -A
git status            # review: no .venv, backups, video, keys or presentation drafts
git commit -m "Update repository for NASA Space Apps 2026: full source, English README, submission package"
git push origin main
```

## 12. Publication record

All commits below were pushed to `origin/main` on 2026-11-15 at the author's explicit request.

| Commit | Content |
|---|---|
| `ed112fe` | Full project update: 77 files added and 24 modified (source code, auth, Educators section, `start.sh`, new science modules, `reports/validation/`, `submission/`, English README, both reports). `.gitignore` was respected, so `.venv/`, `backups/`, `video/`, caches and key material were not published. |
| `6a546c9` | The two root presentations (`LUNAR_P_SYSTEM_PRESENTATION.pdf`, `P-System Space Group · with P-System technology (1).pptx`) and the matching `.gitignore` change |
| `655100d` | This report and `REPOSITORY_COMPLETENESS_AUDIT.md`, updated to match what was published |
| next commit | `.pptx` renamed to `P-System Space Group · with P-System technology.pptx` (`(1)` suffix removed) |

**Still open after publication:**
1. No `LICENSE`.
2. The test suite was not run.
3. No UI screenshots exist.
4. `video/` is still excluded.
5. `SCIENCE_STATUS.txt` is outdated.
6. There is no source URL for P-System.
