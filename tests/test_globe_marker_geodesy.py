"""F10.1 · Corrispondenza coordinate-marker sul globo 3D.

Esegue il codice reale di ``src/ui_web/ui/globe-markers.js`` (in Node, sul GLB reale) e verifica
in modo indipendente, in Python, che il punto scelto per ciascun sito:

* stia su un triangolo della mesh (combinazione convessa dei suoi vertici, nessuna conversione sferica);
* abbia una coordinata di texture (UV) che corrisponde alla lat/lon sorgente;
* migliori, o almeno non peggiori, lo scarto del metodo F9 (vertice più vicino).

Le coordinate sono solo quelle di ``src.astronomy.SITES``. Le soglie in km sono limiti di
regressione costruiti sui valori misurati in F10.1 (0,30 / 0,81 / 0,00 km), non precisioni geodetiche.
"""
import json
import math
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np
import pytest

from src.astronomy import SITES

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GLB = PROJECT_ROOT / "data" / "terrain" / "global" / "Moon_NASA_LRO_8k_Topo_Small.glb"
MARKERS_JS = PROJECT_ROOT / "src" / "ui_web" / "ui" / "globe-markers.js"
RUNNER = PROJECT_ROOT / "tests" / "js" / "globe_markers_geodesy.mjs"
THREE = PROJECT_ROOT / "src" / "ui_web" / "node_modules" / "three" / "build" / "three.module.js"
MOON_RADIUS_KM = 1737.4

pytestmark = pytest.mark.skipif(
    not (GLB.exists() and THREE.exists() and shutil.which("node")),
    reason="richiede il GLB, node e src/ui_web/node_modules/three",
)


def _km(deg):
    return math.radians(deg) * MOON_RADIUS_KM


def _uv_separation_deg(u, v, lat0, lon0):
    lat, lon = math.radians(90 - v * 180), math.radians(u * 360 - 180)
    a, b = math.radians(lat0), math.radians(lon0)
    c = math.sin(a) * math.sin(lat) + math.cos(a) * math.cos(lat) * math.cos(lon - b)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


@pytest.fixture(scope="module")
def glb():
    data = GLB.read_bytes()
    json_len = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + json_len])
    bin0 = 20 + json_len + 8

    def accessor(i, n, dtype):
        a = gltf["accessors"][i]
        bv = gltf["bufferViews"][a["bufferView"]]
        off = bin0 + bv.get("byteOffset", 0) + a.get("byteOffset", 0)
        arr = np.frombuffer(data, dtype, a["count"] * n, off)
        return arr.reshape(-1, n) if n > 1 else arr

    prim = gltf["meshes"][0]["primitives"][0]
    return {
        "P": accessor(prim["attributes"]["POSITION"], 3, np.float32).astype(np.float64),
        "UV": accessor(prim["attributes"]["TEXCOORD_0"], 2, np.float32).astype(np.float64),
        "I": accessor(prim["indices"], 1, np.uint32).reshape(-1, 3),
        "nodes": gltf["nodes"],
    }


@pytest.fixture(scope="module")
def located():
    sites = [{"name": n, "lat": lat, "lon": lon} for n, (lat, lon) in SITES.items()]
    proc = subprocess.run(
        ["node", str(RUNNER), str(GLB), json.dumps(sites)],
        capture_output=True, text=True, timeout=120, cwd=PROJECT_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    return {s["name"]: s for s in json.loads(proc.stdout)["sites"]}


def test_glb_node_has_no_transform(glb):
    # La posizione mondo dipende solo da scala/centratura di main.js: il nodo GLB non deve ruotare.
    node = glb["nodes"][0]
    assert not {"matrix", "rotation", "translation", "scale"} & set(node)


def test_all_sites_located_with_barycentric_method(located):
    assert set(located) == set(SITES)
    for name, r in located.items():
        assert r["method"] in ("barycentric", "barycentric-closest"), name


@pytest.mark.parametrize("name", list(SITES))
def test_point_lies_on_its_mesh_triangle(located, glb, name):
    r = located[name]
    tri = glb["I"][r["triangle"]]
    lam = np.array(r["lambda"])
    assert lam.min() >= -1e-9 and abs(lam.sum() - 1) < 1e-9
    expected = lam @ glb["P"][tri]
    assert np.allclose(expected, r["position"], atol=1e-6)
    assert r["distanceFromTriangle"] < 1e-9


@pytest.mark.parametrize("name", list(SITES))
def test_texture_coordinate_matches_source(located, glb, name):
    lat, lon = SITES[name]
    r = located[name]
    tri = glb["I"][r["triangle"]]
    lam = np.array(r["lambda"])
    uv = glb["UV"][tri].copy()
    uv[:, 0] += np.round(uv[0, 0] - uv[:, 0])  # stessa falda della cucitura u = 0/1
    u, v = lam @ uv
    sep_py = _uv_separation_deg(u, v, lat, lon)
    assert abs(sep_py - r["separationDeg"]) < 1e-6
    assert _km(sep_py) < 1.0, f"{name}: {_km(sep_py):.3f} km"


def test_nobile_is_inside_a_triangle_exactly(located):
    r = located["Nobile"]
    assert r["method"] == "barycentric"
    assert _km(r["separationDeg"]) < 1e-3


@pytest.mark.parametrize("name", list(SITES))
def test_not_worse_than_nearest_vertex(located, name):
    r = located[name]
    assert r["separationDeg"] <= r["nearestVertexSeparationDeg"] + 1e-12


@pytest.mark.parametrize("name", ["Shackleton", "Connecting Ridge"])
def test_polar_sites_improve_over_nearest_vertex(located, name):
    r = located[name]
    assert r["separationDeg"] < 0.25 * r["nearestVertexSeparationDeg"]


def test_marker_points_are_in_southern_hemisphere(located):
    for r in located.values():
        assert r["position"][1] < -0.98  # +Y = nord (F10 §1)


def test_marker_module_uses_no_spherical_conversion():
    src = MARKERS_JS.read_text(encoding="utf-8")
    assert "findUvTriangle" in src and "closestBarycentric" in src
    for forbidden in ("setFromSpherical", "setFromSphericalCoords", "Spherical("):
        assert forbidden not in src
