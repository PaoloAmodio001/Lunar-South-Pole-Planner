# Demonstration Script (about 5 minutes)

The demo runs on the team's computer with the application started locally. **Rehearse it once.** The live application was not run while this script was being written, so every UI step below follows the code and the README and **must be checked by the presenter**.

## Before the demo

```bash
cd Lunar-South-Pole-Planner
./start.sh            # opens http://127.0.0.1:8765/
```

- Make sure the computer has internet access. The ephemerides come live from NASA/JPL Horizons, and the UI shows a classified error, never fake data, if Horizons is unreachable.
- Log in once at `http://127.0.0.1:8765/dashboard` with the planner account. The first account, if none exists, is created through the web form.
- Keep `submission/Lunar_South_Pole_Planner_NASA_2026.pdf` open as a fallback.

## Script

| Time | Screen | What to say |
|---|---|---|
| 0:00–0:30 | Slide 1 (title) | "Lunar South Pole Planner combines NASA/JPL Horizons with NASA LRO terrain to show when the Sun and the Earth are visible at candidate south-pole sites. It is a research and education prototype, not a certified tool." |
| 0:30–1:00 | Slide 2 (challenge) | "At the pole the Sun stays one to two degrees above the horizon and the Earth rises and sets. Terrain decides what is actually lit or in contact." |
| 1:00–2:00 | **Live:** homepage `/` → Public profile → 3D globe | Rotate to the south pole and point out the three markers. "The globe is NASA SVS's LRO-based Moon model. Markers are checked against the LOLA DEMs; Connecting Ridge is still PARTIAL." |
| 2:00–2:45 | **Live:** select Shackleton → ephemerides / operational windows | "This is a live Horizons query. Here is the Sun elevation, here the Earth elevation, and here the windows where both are above the thresholds." Point out the source label "NASA/JPL Horizons". |
| 2:45–3:30 | **Live:** `/dashboard` → Mission Control → Science Tools → Horizon profile on LOLA Site04 | "Terrain horizon from the 5 m/px LOLA DEM. It takes about 6–9 seconds." Then show the rover A* route if time allows. |
| 3:30–4:15 | Slides 3–4 | "We checked our offline SPICE ephemeris against Horizons: within 1.4e-5 degrees. Two independent NASA terrain models, LOLA and LROC, agree on Sun visibility to a median 99.9%. Earth is above the geometric horizon 79% of the time at Shackleton in this 14-day window." |
| 4:15–4:40 | Slides 5–6 | Sites table and architecture. "Every API answer names its module and raster." |
| 4:40–5:00 | Slide 7 | Limitations and next steps: "not yet validated against published illumination maps; terrain-aware windows will move into the Web UI." |

## Fallbacks

- **Horizons unreachable:** show the error classification in the UI, then present slides 3–4. They come from recorded Horizons output.
- **Horizon tool slow:** move on; slide 3 shows the cross-validation result.
- **Do not demo** P-System, the solar energy engine or the fleet planner live. They are disabled in the example configuration and are experimental or partial.

## Screenshots still to capture (needed for a stronger deck and the Space Apps page)

None of the slides contain UI screenshots, because the application was not run during preparation. To add them, capture:

1. Homepage with the 3D globe and the three site markers.
2. Ephemeris panel for Shackleton with Sun/Earth elevation and operational windows.
3. Mission Control → Science Tools horizon profile (LOLA Site04).
4. Rover A* route result.
5. Educators section, chapter 4 (interactive labs).
