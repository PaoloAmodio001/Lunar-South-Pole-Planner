# AI Usage Disclosure

This disclosure covers the software and the submission materials. Where the extent of AI use cannot be established from the repository, this document says so.

## 1. Submission materials (this `submission/` folder)

The following were prepared with **Claude (Anthropic), model Claude Opus 5.5, running in Claude Code**, at the team's request on 2026-11-15:

| Item | AI role |
|---|---|
| `PROJECT_SUMMARY.md`, `PROJECT_DETAILS.md`, `NASA_DATA_SOURCES.md`, `OTHER_RESOURCES.md`, `TECHNICAL_ARCHITECTURE.md`, `DEMONSTRATION_SCRIPT.md`, `SUBMISSION_CHECKLIST.md`, this file | Drafted by the AI after it read the project's source code, configuration, documentation and stored reports. URLs were checked online by the AI on 2026-11-15. |
| `Lunar_South_Pole_Planner_NASA_2026.pptx` and `.pdf` | Layout, text and speaker notes written by the AI. Both files are built by `tools/build_deck.py`. |
| `assets/*.png` (all figures) | **Not AI-generated images.** The AI wrote the plotting script `tools/make_figures.py`, and matplotlib rendered the figures from real project data: LOLA/LROC rasters, recorded NASA/JPL Horizons output and validation JSON files. Every number shown can be recomputed by running the script. |

- **No AI-generated images** (diffusion or other generative imagery) are used anywhere in the submission.
- **No NASA logos, mission insignia or modified NASA branding** are used.
- Every factual claim in these materials was checked against the repository by the AI. The team still needs to review it (see `SUBMISSION_CHECKLIST.md`).

## 2. Application source code

The git history contains commits with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`: 10 occurrences across the repository history. This shows that an AI coding assistant (Claude, via Claude Code) helped develop the application.

**Human confirmation required:**
- the proportion of code and documentation written with AI assistance;
- whether any other AI tools were used;
- which parts were designed, reviewed and validated by team members.

> Suggested wording for the team to confirm or edit:
> "The team used Claude (Anthropic) through Claude Code as a coding assistant for implementation, refactoring, documentation and test writing. Design decisions, data selection and review of the results were made by the team. The scientific outputs come from deterministic code operating on NASA data, not from AI models."

## 3. What AI does NOT do in the running application

The application contains **no AI or ML model**. Ephemerides come from NASA/JPL Horizons or from deterministic SPICE computations. Terrain, visibility, routing and energy results come from explicit numerical algorithms in `src/`.
