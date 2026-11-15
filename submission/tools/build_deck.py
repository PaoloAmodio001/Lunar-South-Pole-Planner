"""Build the 7-slide submission deck as PPTX (python-pptx) and as HTML (printed to PDF by Chrome)
from ONE slide specification, so both outputs share geometry and text.

usage: python build_deck.py <project_root>
"""
import html, json, sys
from pathlib import Path
from PIL import Image

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

ROOT = Path(sys.argv[1]); SUB = ROOT / "submission"; A = SUB / "assets"
W, H = 13.333, 7.5
FONT = "Arial"
C = dict(bg="0B1324", panel="111B30", panel2="16233F", ink="E6ECF5", muted="9AABC4", grid="25324D",
         sun="F5B942", earth="4FC3F7", violet="C792EA", ok="7BD88F", warn="F5B942", part="FF9E64")
ST = json.loads((A / "figure_stats.json").read_text())

# hero crop (fills right part of title slide)
hero = Image.open(A / "hero_shackleton_lola_hillshade.png")
hw = int(hero.height * 5.9 / 7.5)
hero.crop(((hero.width - hw) // 2 + 120, 0, (hero.width - hw) // 2 + 120 + hw, hero.height)).save(A / "hero_title_crop.png")

# ------------------------------------------------------------------ primitives
def box(x, y, w, h, fill=C["panel"], r=0.12, line=None):
    return dict(k="box", x=x, y=y, w=w, h=h, fill=fill, r=r, line=line)

def P(text, size=15, color=C["ink"], bold=False, italic=False, after=4, runs=None, bullet=False):
    return dict(text=text, size=size, color=color, bold=bold, italic=italic, after=after, runs=runs, bullet=bullet)

def txt(x, y, w, h, paras, align="l", anchor="t"):
    return dict(k="txt", x=x, y=y, w=w, h=h, paras=paras, align=align, anchor=anchor)

def img(path, x, y, w=None, h=None, alt=""):
    im = Image.open(path); ar = im.height / im.width
    if w is not None and h is None: h = w * ar
    if h is not None and w is None: w = h / ar
    return dict(k="img", path=str(path), x=x, y=y, w=w, h=h, alt=alt)

def arrow(x, y, w, h, fill=C["muted"]):
    return dict(k="arrow", x=x, y=y, w=w, h=h, fill=fill)

def title(t, kicker):
    return [txt(0.6, 0.38, 12.1, 0.32, [P(kicker.upper(), 12, C["sun"], bold=True)]),
            txt(0.6, 0.66, 12.1, 0.75, [P(t, 30, C["ink"], bold=True)])]

def footer(n, src):
    return [txt(0.6, 7.05, 10.8, 0.3, [P(src, 10, C["muted"])]),
            txt(12.1, 7.05, 0.63, 0.3, [P(f"{n} / 7", 10, C["muted"])], align="r")]

def chip(x, y, w, label, color):
    return [box(x, y, w, 0.34, fill=C["panel2"], r=0.5),
            txt(x, y, w, 0.34, [P(label, 11, color, bold=True, after=0)], align="c", anchor="m")]

def stat(x, y, w, big, label, color):
    return [txt(x, y, w, 0.62, [P(big, 30, color, bold=True, after=0)]),
            txt(x, y + 0.64, w, 0.62, [P(label, 12, C["muted"], after=0)])]

slides = []
emax = ST["ephemeris_validation_max_elev_err_deg"]
cv = ST["terrain_cv_summary"]

# ------------------------------------------------------------------ 1 title / intro
s = [img(A / "hero_title_crop.png", W - 5.9, 0, 5.9, 7.5, alt="LOLA DEM hillshade of the Shackleton crater rim"),
     box(W - 5.9, 6.92, 5.9, 0.58, fill=C["bg"], r=0),
     txt(W - 5.75, 7.0, 5.6, 0.35, [P("LOLA 5 m/px DEM, Shackleton rim (PGDA Site04): hillshade rendered from project data",
                                     10, C["ink"])], align="r"),
     txt(0.6, 0.6, 6.6, 0.35, [P("NASA SPACE APPS CHALLENGE 2026", 13, C["sun"], bold=True)]),
     txt(0.6, 1.05, 6.8, 1.6, [P("Lunar South Pole Planner", 42, C["ink"], bold=True, after=0)]),
     txt(0.6, 2.7, 6.6, 1.2, [P("An open, local tool that combines NASA/JPL Horizons ephemerides with NASA LRO terrain "
                                "models to show when Sun and Earth are visible at candidate south-polar sites.", 17, C["muted"])])]
s += stat(0.6, 4.25, 2.0, "3", "candidate sites with LOLA 5 m/px terrain", C["sun"])
s += stat(2.8, 4.25, 2.1, "2", "independent NASA LRO terrain models (LOLA, LROC NAC)", C["earth"])
s += stat(5.1, 4.25, 2.2, "1.4e-5°", "max Sun/Earth elevation gap, local DE421 vs Horizons", C["violet"])
s += [txt(0.6, 6.2, 6.8, 0.75, [P("Team: P-System Space Group  ·  Research and education prototype: "
                                  "not flight-certified and not operationally validated", 11, C["muted"])])]
slides.append(dict(items=s, notes=(
    "Lunar South Pole Planner is a local Python and web application. It pulls Sun and Earth positions from NASA/JPL Horizons, "
    "reads NASA LRO terrain models (LOLA 5 m per pixel and an LROC NAC stereo DTM) and turns them into illumination, "
    "Earth-visibility and terrain diagnostics for three candidate sites: Shackleton rim, Connecting Ridge and Nobile rim. "
    f"The 1.4e-5 degree figure comes from reports/validation/ephemeris_validation_20261115T0000.json. "
    "Everything shown is a preliminary diagnostic, not a certified mission product.")))

# ------------------------------------------------------------------ 2 challenge
s = title("At the south pole, a few degrees decide everything", "The exploration challenge")
cards = [
    (C["sun"], "1.0°–1.6°", "Grazing sunlight",
     "Sun elevation above the geometric horizon at Shackleton and Connecting Ridge over 14 days (JPL Horizons, Nov 2026). "
     "Any rim or hill can block it."),
    (C["earth"], "−3.9°–+6.0°", "Earth low on the horizon",
     "Earth elevation at the same two sites over the same window: direct-to-Earth contact comes and goes."),
    (C["violet"], "21–59%", "Terrain decides, not geometry",
     "Share of 28 days with the Sun above the DEM horizon at 10 Shackleton-rim test points, although it never sets geometrically."),
    (C["part"], "26°", "Steep, uncertain ground",
     "Median slope in a 12 × 12 km LOLA window around Shackleton (25 m grid). LOLA and LROC horizons differ by up to 4.4° RMS at one test point."),
]
for i, (col, big, head, body) in enumerate(cards):
    cx = 0.6 + (i % 2) * 6.15; cy = 1.65 + (i // 2) * 2.55
    s += [box(cx, cy, 5.95, 2.35),
          txt(cx + 0.3, cy + 0.2, 5.4, 0.6, [P(big, 28, col, bold=True, after=0)]),
          txt(cx + 0.3, cy + 0.82, 5.4, 0.4, [P(head, 17, C["ink"], bold=True, after=0)]),
          txt(cx + 0.3, cy + 1.25, 5.4, 1.05, [P(body, 14, C["muted"], after=0)])]
s += footer(2, "Sources: reports/validation/horizons_reference_20261115T0000.json; terrain_cross_validation.json; "
               "LOLA Site04 DEM. Figures computed for this submission from project files.")
slides.append(dict(items=s, notes=(
    "Near the pole the Sun stays within a degree or two of the horizon, so local relief decides whether a spot is lit. "
    "The Earth also hangs near the horizon and moves above and below it with the lunar libration cycle, which drives "
    "direct-to-Earth communication opportunities. The numbers on this slide come from the project's recorded Horizons output "
    "and from the LOLA/LROC cross-validation run of 15 November 2026. The 21 to 59 percent range is the LOLA/LROC "
    "Sun-visible fraction over 28 days at 10 test points on the Shackleton rim.")))

# ------------------------------------------------------------------ 3 illumination
s = title("Solar illumination: the Sun is up, the terrain decides", "Solar illumination analysis")
s += [img(A / "horizons_sun_elevation.png", 0.6, 1.6, w=6.0, alt="Sun elevation chart, three sites"),
      img(A / "sun_visibility_lola_vs_lroc.png", 6.73, 1.6, w=6.0, alt="Sun visibility LOLA vs LROC")]
s += [box(0.6, 4.95, 12.13, 1.95),
      txt(0.9, 5.1, 5.7, 1.75, [
          P("How it works", 15, C["sun"], bold=True, after=6),
          P("Horizon profile from the DEM (observer 2 m, 2° azimuth steps, curved-Moon geometry)", 13, C["ink"], bullet=True, after=3),
          P("Sun position from JPL Horizons or offline Skyfield + NAIF SPICE (DE421)", 13, C["ink"], bullet=True, after=3),
          P("Grid-to-north azimuth offset derived from the raster CRS", 13, C["ink"], bullet=True, after=0)]),
      txt(6.9, 5.1, 5.7, 1.75, [
          P("What the evidence shows", 15, C["sun"], bold=True, after=6),
          P(f"LOLA and LROC give the same Sun-visible fraction to a median {cv['median_sun_visibility_agreement']*100:.1f}% "
            f"(worst {cv['worst_sun_visibility_agreement']*100:.1f}%)", 13, C["ink"], bullet=True, after=3),
          P("Not yet compared with published illumination maps or in-situ data", 13, C["ink"], bullet=True, after=3),
          P("Terrain-aware windows run from the Mission Engine CLI; the Web UI shows geometric windows", 13, C["ink"], bullet=True, after=0)])]
s += footer(3, "Charts built for this submission from reports/validation/*.json (NASA/JPL Horizons; LOLA PGDA DEM; LROC NAC DTM SR12).")
slides.append(dict(items=s, notes=(
    "Left: the Sun's elevation above the geometric horizon from NASA/JPL Horizons for the three sites. "
    "Right: the fraction of 28 days in which the Sun is above the terrain horizon, computed with the project's horizon model "
    "on two independent NASA terrain products, LOLA laser altimetry and the LROC NAC stereo DTM. The two agree closely, "
    "which is a consistency check between datasets, not a validation against measured illumination. "
    "The Web UI ephemeris panel shows geometric windows; terrain-aware windows are produced by src/contact_windows.py "
    "through the Mission Engine and the validation CLI.")))

# ------------------------------------------------------------------ 4 earth visibility
s = title("Earth visibility and communication opportunities", "Earth line-of-sight")
s += [img(A / "horizons_earth_elevation.png", 0.6, 1.6, w=7.4, alt="Earth elevation chart, three sites")]
px = 8.3
s += [box(px, 1.6, 4.43, 5.25)]
s += stat(px + 0.3, 1.8, 3.9, f"{ST['Shackleton:Earth']['frac_above_0']*100:.0f}%",
          "of 6-h samples with Earth above the geometric horizon at Shackleton and Connecting Ridge (14 days)", C["earth"])
s += stat(px + 0.3, 3.2, 3.9, f"{ST['Nobile:Earth']['frac_above_0']*100:.0f}%", "at Nobile, farther from the pole", C["violet"])
s += [txt(px + 0.3, 4.25, 3.9, 2.55, [
    P("Operational windows: Sun AND Earth above user thresholds, 1-h steps (Web UI)", 13, C["ink"], bullet=True, after=4),
    P("First-order free-space link budget (Web UI)", 13, C["ink"], bullet=True, after=4),
    P("Earth blocked by DEM horizon: Mission Engine only", 13, C["ink"], bullet=True, after=4),
    P("Earth treated as a point; no ground-station schedule", 13, C["muted"], bullet=True, after=0)])]
s += footer(4, "Chart: NASA/JPL Horizons API output recorded in reports/validation/horizons_reference_20261115T0000.json.")
slides.append(dict(items=s, notes=(
    "Earth elevation from Horizons for the same 14 days. At the two near-pole sites the Earth is below the geometric horizon "
    "for about a fifth of the samples in this window; at Nobile, farther from the pole, almost never. "
    "The Web UI combines Sun and Earth thresholds into operational windows and offers a free-space link-budget calculator. "
    "Terrain blocking of the Earth is computed by contact_windows.py in the Mission Engine, not yet in the Web UI. "
    "Ground-station availability and real antenna patterns are not modelled.")))

# ------------------------------------------------------------------ 5 sites
s = title("Candidate landing and infrastructure locations", "Candidate sites")
s += [img(A / "sites_lola_three_panels.png", (W - 11.0) / 2, 1.45, w=11.0, alt="LOLA hillshades of the three candidate sites")]
rows = [("Site", "Lat / East lon", "LOLA 5 m/px DEM", "LROC NAC DTM overlap", "3D globe marker check"),
        ("Shackleton rim", "−89.7668°, −171.87°", "Site04 + LDEC + TOTERR", "Yes (SR12, 2 m/px)", "PASS at mesh resolution"),
        ("Connecting Ridge", "−89.4632°, −137.49°", "Site01", "No", "PARTIAL (possible ~4.6 km offset)"),
        ("Nobile rim 1", "−85.4381°, 37.37°", "Site06", "No", "PASS at mesh resolution")]
cw = [2.2, 2.3, 2.45, 2.45, 2.73]; ty = 5.72; rh = 0.31
for ri, row in enumerate(rows):
    xx = 0.6
    for ci, cell in enumerate(row):
        col = C["muted"] if ri == 0 else (C["ink"] if ci else [C["sun"], C["earth"], C["violet"]][ri - 1])
        if ri and ci == 4: col = C["part"] if "PARTIAL" in cell else C["ok"]
        s.append(txt(xx, ty + ri * rh, cw[ci], rh, [P(cell, 11 if ri == 0 else 12, col, bold=(ri == 0 or ci == 0), after=0)]))
        xx += cw[ci]
s += footer(5, "Coordinates: src/astronomy.py (cited there to NASA Lunar Surface Data Book, 2025). Marker check: reports/web_ui_consolidation/F10_GEODETIC_VALIDATION.md.")
slides.append(dict(items=s, notes=(
    "The three sites are the ones hard-coded in src/astronomy.py, each matched to a NASA GSFC PGDA LOLA 5 m per pixel DEM. "
    "Only Shackleton is covered by the LROC NAC DTM, so the cross-dataset checks apply there only. "
    "For infrastructure and surface operations the planner offers DEM slope and roughness, a terrain-aware A* rover route "
    "with a preliminary energy estimate, multi-rover allocation, and a descent-hazard diagnostic. "
    "The globe-marker check compares the 3D globe markers with the LOLA DEMs; Connecting Ridge shows a possible offset "
    "of a few kilometres that the globe mesh cannot resolve.")))

# ------------------------------------------------------------------ 6 architecture
s = title("Software architecture and implementation", "Technical implementation")
cols = [
    ("DATA", C["sun"], ["LOLA 5 m/px DEMs (PGDA)", "LROC NAC DTM SR12 (PDS)", "JPL Horizons API (live)",
                        "NAIF SPICE kernels + DE421", "LRO-based Moon GLB"]),
    ("SCIENCE MODULES", C["earth"], ["DEM audit, slope, roughness", "Horizon + illumination", "Contact windows",
                                     "Link budget, thermal node", "Rover A*, energy, fleet"]),
    ("MISSION ENGINE", C["violet"], ["JSON-configured orchestrator", "Solar energy engine", "Decision engine",
                                     "Reports + run journal", "P-System sync (exp.)"]),
    ("WEB UI", C["ok"], ["Public 3D globe (three.js)", "Educators section", "Planner dashboard (login)",
                         "Mission Control tools", "Local server :8765"]),
]
bw, gap, by = 2.68, 0.47, 1.6
for i, (head, col, items) in enumerate(cols):
    bx = 0.6 + i * (bw + gap)
    s += [box(bx, by, bw, 3.2),
          txt(bx + 0.22, by + 0.2, bw - 0.4, 0.4, [P(head, 14, col, bold=True, after=0)]),
          txt(bx + 0.22, by + 0.7, bw - 0.35, 2.8, [P(t, 13, C["ink"], after=7) for t in items])]
    if i < 3:
        s.append(arrow(bx + bw + 0.08, by + 1.6, gap - 0.16, 0.36))
s += [box(0.6, 5.05, 12.13, 1.8, fill=C["panel2"]),
      txt(0.9, 5.25, 5.9, 1.5, [
          P("Stack", 14, C["sun"], bold=True, after=4),
          P("Python 3.14 · numpy · rasterio · pyproj · matplotlib · requests · Skyfield", 13, C["ink"], after=3),
          P("Standard-library HTTP server and scrypt login · vanilla JS · three.js r186 bundled", 13, C["ink"], after=0)]),
      txt(7.0, 5.25, 5.6, 1.5, [
          P("Engineering practice", 14, C["sun"], bold=True, after=4),
          P("309 pytest functions in 38 files; last recorded full run 494 passed (15 Nov 2026)", 13, C["ink"], after=3),
          P("Every API answer names its module and source raster", 13, C["ink"], after=0)])]
s += footer(6, "P-System integration is experimental and tested with local processes only. Test counts from documentation/REPORT_TEST.md; not re-run for this submission.")
slides.append(dict(items=s, notes=(
    "Data flows left to right. Real NASA inputs feed thin science modules; each module documents what it does not model. "
    "The Mission Engine chains them from a JSON configuration and writes reproducible reports. The Web UI is a local "
    "standard-library server with a public globe and an Educators section, plus a login-protected planner dashboard. "
    "P-System, a separate distributed-ledger project by the same team, can optionally certify mission records; this is "
    "experimental and has only been tested with local processes on one machine.")))

# ------------------------------------------------------------------ 7 impact
s = title("Scientific relevance, impact and next steps", "Impact and future development")
cols = [
    ("Why it matters", C["sun"], [
        "Sunlight and Earth line-of-sight drive power, thermal and communications design near the pole",
        "Makes NASA ephemerides and LRO terrain usable without GIS or SPICE expertise",
        "Free Educators section with labs on live Horizons data"]),
    ("Known limits", C["part"], [
        "Preliminary diagnostics: not flight-certified, not operationally validated",
        "Illumination not yet checked against published maps or in-situ data",
        "Energy and thermal models are first-order; three sites only"]),
    ("Next steps", C["ok"], [
        "Terrain-aware Sun/Earth windows inside the Web UI",
        "Compare with published LOLA illumination studies (Mazarico 2011; Barker 2021)",
        "More PGDA sites, HTTPS deployment, browser end-to-end tests"]),
]
for i, (head, col, items) in enumerate(cols):
    bx = 0.6 + i * 4.11
    s += [box(bx, 1.65, 3.91, 4.0),
          txt(bx + 0.3, 1.85, 3.4, 0.45, [P(head, 18, col, bold=True, after=0)]),
          txt(bx + 0.3, 2.45, 3.4, 3.7, [P(t, 14, C["ink"], bullet=True, after=10) for t in items])]
s += [txt(0.6, 6.0, 12.13, 0.55, [P("Open data in, transparent diagnostics out: every number on these slides can be traced to a file in the project.",
                                      15, C["ink"], italic=True, after=0)])]
s += footer(7, "Lunar South Pole Planner · NASA Space Apps Challenge 2026")
slides.append(dict(items=s, notes=(
    "Impact: at the south pole, sunlight and Earth visibility shape where to land, where to put power and comms "
    "infrastructure, and when to drive. The planner lets students and planners explore those questions on real NASA data. "
    "Limits are stated openly. Next steps: bring terrain-aware windows into the Web UI, compare results with published LOLA "
    "illumination studies, add more of the PGDA south-pole sites, and harden the deployment with HTTPS and browser tests.")))

# ================================================================== PPTX renderer
def rgb(h): return RGBColor.from_string(h)
prs = Presentation(); prs.slide_width = Inches(W); prs.slide_height = Inches(H)
prs.core_properties.title = "Lunar South Pole Planner — NASA Space Apps Challenge 2026"
prs.core_properties.author = "P-System Space Group"
prs.core_properties.last_modified_by = "P-System Space Group"
prs.core_properties.comments = ""
blank = prs.slide_layouts[6]
AL = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}
AN = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}
from pptx.oxml.ns import qn
from lxml import etree

def set_bullet(p, on):
    pPr = p._p.get_or_add_pPr()
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum"):
        for e in pPr.findall(qn(tag)): pPr.remove(e)
    if on:
        pPr.set("marL", str(int(Inches(0.22)))); pPr.set("indent", str(-int(Inches(0.22))))
        bu = etree.SubElement(pPr, qn("a:buChar")); bu.set("char", "•")
    else:
        etree.SubElement(pPr, qn("a:buNone"))

for spec in slides:
    sl = prs.slides.add_slide(blank)
    bg = sl.background.fill; bg.solid(); bg.fore_color.rgb = rgb(C["bg"])
    for it in spec["items"]:
        X, Y, Wd, Ht = (Inches(it[k]) for k in ("x", "y", "w", "h"))
        if it["k"] == "box":
            sh = sl.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, X, Y, Wd, Ht)
            sh.adjustments[0] = min(0.5, it["r"] / min(it["w"], it["h"]))
            sh.fill.solid(); sh.fill.fore_color.rgb = rgb(it["fill"]); sh.line.fill.background(); sh.shadow.inherit = False
        elif it["k"] == "arrow":
            sh = sl.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, X, Y, Wd, Ht)
            sh.fill.solid(); sh.fill.fore_color.rgb = rgb(it["fill"]); sh.line.fill.background(); sh.shadow.inherit = False
        elif it["k"] == "img":
            pic = sl.shapes.add_picture(it["path"], X, Y, Wd, Ht)
            pic._element.nvPicPr.cNvPr.set("descr", it["alt"])
        elif it["k"] == "txt":
            tb = sl.shapes.add_textbox(X, Y, Wd, Ht); tf = tb.text_frame
            tf.word_wrap = True; tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
            tf.vertical_anchor = AN[it["anchor"]]
            for i, pp in enumerate(it["paras"]):
                p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                p.alignment = AL[it["align"]]; p.space_after = Pt(pp["after"]); set_bullet(p, pp["bullet"])
                r = p.add_run(); r.text = pp["text"]
                f = r.font; f.name = FONT; f.size = Pt(pp["size"]); f.bold = pp["bold"]; f.italic = pp["italic"]
                f.color.rgb = rgb(pp["color"])
    sl.notes_slide.notes_text_frame.text = spec["notes"]
out_pptx = SUB / "Lunar_South_Pole_Planner_NASA_2026.pptx"
prs.save(out_pptx)

# ================================================================== HTML renderer (for PDF)
css = f"""@page {{ size: {W}in {H}in; margin: 0 }}
* {{ box-sizing: border-box; margin: 0; padding: 0 }}
body {{ background: #{C['bg']}; font-family: Arial, 'Liberation Sans', sans-serif }}
.s {{ position: relative; width: {W}in; height: {H}in; overflow: hidden; background: #{C['bg']}; page-break-after: always }}
.a {{ position: absolute }}
.t {{ display: flex; flex-direction: column }}
p {{ line-height: 1.17; white-space: pre-wrap }}
p.b {{ padding-left: 0.22in; text-indent: -0.22in }}
p.b::before {{ content: '•'; display: inline-block; width: 0.22in; text-indent: 0 }}
"""
parts = []
for spec in slides:
    h = []
    for it in spec["items"]:
        pos = f"left:{it['x']}in;top:{it['y']}in;width:{it['w']}in;height:{it['h']}in"
        if it["k"] == "box":
            h.append(f'<div class="a" style="{pos};background:#{it["fill"]};border-radius:{it["r"]}in"></div>')
        elif it["k"] == "arrow":
            h.append(f'<svg class="a" style="{pos}" viewBox="0 0 100 100" preserveAspectRatio="none">'
                     f'<polygon points="0,25 50,25 50,0 100,50 50,100 50,75 0,75" fill="#{it["fill"]}"/></svg>')
        elif it["k"] == "img":
            h.append(f'<img class="a" style="{pos}" src="{Path(it["path"]).as_uri()}" alt="{html.escape(it["alt"])}">')
        elif it["k"] == "txt":
            jc = {"t": "flex-start", "m": "center", "b": "flex-end"}[it["anchor"]]
            ta = {"l": "left", "c": "center", "r": "right"}[it["align"]]
            ps = "".join(
                f'<p class="{"b" if pp["bullet"] else ""}" style="font-size:{pp["size"]}pt;color:#{pp["color"]};'
                f'font-weight:{"bold" if pp["bold"] else "normal"};font-style:{"italic" if pp["italic"] else "normal"};'
                f'margin-bottom:{pp["after"]}pt;text-align:{ta}">{html.escape(pp["text"])}</p>' for pp in it["paras"])
            h.append(f'<div class="a t" style="{pos};justify-content:{jc}">{ps}</div>')
    parts.append(f'<section class="s">{"".join(h)}</section>')
(SUB / "tools" / "deck_print.html").write_text(f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Lunar South Pole Planner — NASA Space Apps Challenge 2026</title><style>{css}</style></head>"
                                      f"<body>{''.join(parts)}</body></html>")
print(out_pptx, len(prs.slides._sldIdLst))
