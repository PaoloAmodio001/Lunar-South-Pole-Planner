"""Build English submission figures from REAL project data only (read-only access).

Inputs (all inside the project, never modified):
  data/terrain/official-lola/Site0{1,4,6}_final_adj_5mpp_surf.tif   LOLA 5 m/px DEMs (NASA GSFC PGDA)
  reports/validation/horizons_reference_20261115T0000.json           recorded NASA/JPL Horizons output
  reports/validation/ephemeris_validation_20261115T0000.json         local DE421 vs Horizons comparison
  reports/validation/terrain_cross_validation.json (+ p5_*.json)     LOLA vs LROC horizon/illumination
Output: submission/assets/*.png
"""
import json, sys
from datetime import datetime
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds
from pyproj import Transformer
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import LightSource

ROOT = Path(sys.argv[1])
OUT = ROOT / "submission" / "assets"
OUT.mkdir(parents=True, exist_ok=True)

BG = "#0B1324"; PANEL = "#111B30"; INK = "#E6ECF5"; MUTED = "#8FA0BA"; GRID = "#25324D"
SUN = "#F5B942"; EARTH = "#4FC3F7"; THIRD = "#C792EA"
SITE_COL = {"Shackleton": SUN, "Connecting Ridge": EARTH, "Nobile": THIRD}

plt.rcParams.update({
    "font.family": "Liberation Sans", "font.size": 18, "text.color": INK,
    "axes.facecolor": PANEL, "figure.facecolor": BG, "axes.edgecolor": GRID,
    "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "savefig.facecolor": BG,
})

SITES = {  # src/astronomy.py SITES (planetocentric lat, east lon)
    "Shackleton": (-89.7668, -171.87, "Site04"),
    "Connecting Ridge": (-89.4632, -137.49, "Site01"),
    "Nobile": (-85.4381, 37.36667, "Site06"),
}


def hillshade_crop(site, half=6000.0, target=900):
    lat, lon, tag = SITES[site]
    path = ROOT / f"data/terrain/official-lola/{tag}_final_adj_5mpp_surf.tif"
    with rasterio.open(path) as ds:
        tr = Transformer.from_crs("+proj=longlat +R=1737400 +no_defs", ds.crs, always_xy=True)
        x, y = tr.transform(lon, lat)
        b = ds.bounds
        l, r = max(b.left, x - half), min(b.right, x + half)
        bo, t = max(b.bottom, y - half), min(b.top, y + half)
        win = from_bounds(l, bo, r, t, ds.transform)
        step = max(1, int(round(win.width / target)))
        z = ds.read(1, window=win, out_shape=(int(win.height // step), int(win.width // step)))
    z = np.where(np.isfinite(z), z, np.nanmedian(z))
    res = 5.0 * step
    hs = LightSource(azdeg=315, altdeg=25).hillshade(z, vert_exag=2, dx=res, dy=res)
    gy, gx = np.gradient(z, res)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    return dict(z=z, hs=hs, slope=slope, extent=(l, r, bo, t), x=x, y=y, res=res, path=path.name)


# 1. Hero: Shackleton rim hillshade (LOLA Site04), no axes -----------------------------
h = hillshade_crop("Shackleton", half=8000, target=1400)
fig = plt.figure(figsize=(8, 8), dpi=200)
ax = fig.add_axes([0, 0, 1, 1]); ax.axis("off")
ax.imshow(h["hs"], cmap="gray", extent=h["extent"], vmin=0.05, vmax=1.0)
fig.savefig(OUT / "hero_shackleton_lola_hillshade.png"); plt.close(fig)

# 2. Three candidate sites (LOLA hillshade + elevation tint) ----------------------------
fig, axes = plt.subplots(1, 3, figsize=(15, 5.6), dpi=170)
for ax, name in zip(axes, SITES):
    c = hillshade_crop(name, half=6000, target=700)
    l, r, bo, t = c["extent"]
    ext_km = ((l - c["x"]) / 1e3, (r - c["x"]) / 1e3, (bo - c["y"]) / 1e3, (t - c["y"]) / 1e3)
    ax.imshow(c["hs"], cmap="gray", extent=ext_km, vmin=0.05, vmax=1.0)
    ax.imshow(c["z"], cmap="cividis", alpha=0.35, extent=ext_km)
    ax.plot(0, 0, marker="o", ms=12, mfc="none", mec=SITE_COL[name], mew=2.5)
    ax.plot(0, 0, marker="+", ms=8, color=SITE_COL[name], mew=2)
    ax.set_title(f"{name}  ·  {c['path'].split('_')[0]}", color=INK, fontsize=15, pad=10)
    ax.set_xlabel("km from site (polar stereographic X)"); ax.grid(False)
    lat, lon, _ = SITES[name]
    ax.text(0.02, 0.03, f"{lat:.4f}°, {lon:.2f}°E\nslope median {np.nanmedian(c['slope']):.1f}° (25 m grid)",
            transform=ax.transAxes, fontsize=11, color=INK,
            bbox=dict(facecolor=BG, alpha=0.75, edgecolor="none", pad=4))
axes[0].set_ylabel("km from site (Y)")
fig.tight_layout(); fig.savefig(OUT / "sites_lola_three_panels.png"); plt.close(fig)

# 3/4. Horizons Sun & Earth elevation (recorded output) --------------------------------
hz = json.loads((ROOT / "reports/validation/horizons_reference_20261115T0000.json").read_text())
stats = {}
for target, fname, title in (("Sun", "horizons_sun_elevation.png", "Sun elevation, geometric horizon (JPL Horizons)"),
                             ("Earth", "horizons_earth_elevation.png", "Earth elevation, geometric horizon (JPL Horizons)")):
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=170)
    for site in SITES:
        rows = hz[f"{site}:{target}"]
        t = [datetime.fromisoformat(r["time_utc"]) for r in rows]
        e = np.array([r["elevation_deg"] for r in rows])
        ax.plot(t, e, color=SITE_COL[site], lw=2.4, label=site, marker="o", ms=3)
        stats[f"{site}:{target}"] = dict(n=len(e), min=float(e.min()), max=float(e.max()),
                                         frac_above_0=float((e > 0).mean()))
    ax.axhline(0, color=INK, lw=1, ls="--", alpha=0.6)
    ax.set_ylim(top=8.2 if target == "Sun" else 12.5)
    ax.set_ylabel("elevation (deg)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    ax.set_title(title, color=INK, fontsize=21, loc="left", pad=12)
    ax.legend(frameon=False, loc="upper left", ncol=3, fontsize=16)
    fig.tight_layout(); fig.savefig(OUT / fname); plt.close(fig)

# 5. Terrain horizon LOLA vs LROC at one cross-validation point -------------------------
cv = json.loads((ROOT / "reports/validation/terrain_cross_validation.json").read_text())
pts = {p["point"]: p for p in cv["points"]}
P = 5
fig, ax = plt.subplots(figsize=(10, 5.6), dpi=170)
for src, col, lab in (("lola", SUN, "LOLA 5 m/px (laser altimetry)"), ("lroc", EARTH, "LROC NAC DTM 2 m/px (stereo)")):
    d = json.loads((ROOT / f"reports/validation/terrain_cross_validation/p{P}_{src}.json").read_text())
    az = [s["grid_azimuth_deg"] for s in d["samples"]]
    el = [s["horizon_elevation_deg"] for s in d["samples"]]
    ax.plot(az, el, color=col, lw=2.2, label=lab)
p = pts[P]
ax.set_xlim(0, 360); ax.set_xlabel("azimuth in raster-grid frame (deg)"); ax.set_ylabel("terrain horizon elevation (deg)")
ax.set_title(f"DEM horizon, Shackleton rim point {P}, observer 2 m",
             color=INK, fontsize=21, loc="left", pad=12)
ax.legend(frameon=False, loc="upper right", fontsize=16)
fig.tight_layout(); fig.savefig(OUT / "terrain_horizon_lola_vs_lroc.png"); plt.close(fig)

# 6. Sun-visible fraction LOLA vs LROC for all compared points --------------------------
fig, ax = plt.subplots(figsize=(10, 5.6), dpi=170)
ids = [p["point"] for p in cv["points"]]
x = np.arange(len(ids)); w = 0.38
ax.bar(x - w / 2, [p["sun_visible_fraction"]["lola"] * 100 for p in cv["points"]], w, color=SUN, label="LOLA")
ax.bar(x + w / 2, [p["sun_visible_fraction"]["lroc"] * 100 for p in cv["points"]], w, color=EARTH, label="LROC NAC")
ax.set_xticks(x, [f"P{i}" for i in ids]); ax.set_ylabel("time Sun visible (%)")
ax.set_ylim(0, 100); ax.grid(axis="x", visible=False); ax.set_axisbelow(True)
ax.set_title("Sun above terrain horizon, 28 days, Shackleton rim", color=INK, fontsize=21, loc="left", pad=12)
ax.legend(frameon=False, loc="upper left", ncol=2, fontsize=16)
s = cv["summary"]
fig.tight_layout(); fig.savefig(OUT / "sun_visibility_lola_vs_lroc.png"); plt.close(fig)

ev = json.loads((ROOT / "reports/validation/ephemeris_validation_20261115T0000.json").read_text())
stats["ephemeris_validation_max_elev_err_deg"] = max(r["elevation_deg"]["max_abs"] for r in ev["results"])
stats["ephemeris_validation_max_az_err_deg"] = max(r["azimuth_deg"]["max_abs"] for r in ev["results"])
stats["ephemeris_all_within_tolerance"] = ev["all_within_tolerance"]
stats["terrain_cv_summary"] = s
(OUT / "figure_stats.json").write_text(json.dumps(stats, indent=2))
print(json.dumps(stats, indent=2))
