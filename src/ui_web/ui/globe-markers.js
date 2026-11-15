// F9 · Marker dei siti sul globo (modulo ES servito da /ui/).
// Rollback: in main.js togliere l'import di questo modulo e la chiamata a createSiteMarkers().
//
// Le coordinate arrivano SOLO da /api/sites (passate da main.js come dati, mai letterali).
// La posizione sul modello non viene "inventata": si cerca il vertice della mesh la cui
// coordinata di texture (UV) corrisponde a lat/lon (F10.1: interpolazione baricentrica nel
// triangolo UV che la contiene, fallback al vertice più vicino), con la convenzione della texture
// equirettangolare NASA CGI Moon Kit (longitudine 0° al centro, nord in alto, UV glTF con
// origine in alto a sinistra). Il marker poggia quindi sul punto della superficie dove la
// texture mostra quella latitudine/longitudine. Convenzione da validare: F4 §7, F9 §6.
import * as THREE from 'three';

const DEG = Math.PI / 180;

function findMesh(object) {
  let found = null;
  object.traverse(o => { if (!found && o.isMesh && o.geometry?.attributes?.uv) found = o; });
  return found;
}

/** Coordinata UV (convenzione sopra) corrispondente a lat/lon. Nessuna conversione sferica in XYZ. */
export function latLonToUv(latDeg, lonEastDeg) {
  const lon = ((lonEastDeg + 180) % 360 + 360) % 360 - 180; // normalizza in [-180, 180)
  return { u: (lon + 180) / 360, v: (90 - latDeg) / 180 };
}

/** Distanza angolare (gradi) tra il punto UV (u, v) e lat/lon, con la convenzione della texture. */
function uvSeparationDeg(u, v, latDeg, lonEastDeg) {
  const lat = (90 - v * 180) * DEG, lon = (u * 360 - 180) * DEG;
  const lat0 = latDeg * DEG, lon0 = lonEastDeg * DEG;
  const c = Math.sin(lat0) * Math.sin(lat) + Math.cos(lat0) * Math.cos(lat) * Math.cos(lon - lon0);
  return Math.acos(Math.min(1, Math.max(-1, c))) / DEG;
}

/** Vertice la cui UV è più vicina a lat/lon (metodo F9, conservato come riferimento e fallback). */
function nearestVertex(uv, latDeg, lonEastDeg) {
  let best = Infinity, index = -1;
  for (let i = 0; i < uv.count; i++) {
    const s = uvSeparationDeg(uv.getX(i), uv.getY(i), latDeg, lonEastDeg);
    if (s < best) { best = s; index = i; }
  }
  return { index, separationDeg: best };
}

/** Punto più vicino a (0,0) sul triangolo 2D a-b-c (Ericson, Real-Time Collision Detection §5.1.5): restituisce [λa, λb, λc]. */
function closestBarycentric(ax, ay, bx, by, cx, cy) {
  const abx = bx - ax, aby = by - ay, acx = cx - ax, acy = cy - ay;
  const d1 = -(abx * ax + aby * ay), d2 = -(acx * ax + acy * ay);
  if (d1 <= 0 && d2 <= 0) return [1, 0, 0];
  const d3 = -(abx * bx + aby * by), d4 = -(acx * bx + acy * by);
  if (d3 >= 0 && d4 <= d3) return [0, 1, 0];
  const vc = d1 * d4 - d3 * d2;
  if (vc <= 0 && d1 >= 0 && d3 <= 0) { const w = d1 / (d1 - d3); return [1 - w, w, 0]; }
  const d5 = -(abx * cx + aby * cy), d6 = -(acx * cx + acy * cy);
  if (d6 >= 0 && d5 <= d6) return [0, 0, 1];
  const vb = d5 * d2 - d1 * d6;
  if (vb <= 0 && d2 >= 0 && d6 <= 0) { const w = d2 / (d2 - d6); return [1 - w, 0, w]; }
  const va = d3 * d6 - d5 * d4;
  if (va <= 0 && d4 - d3 >= 0 && d5 - d6 >= 0) { const w = (d4 - d3) / ((d4 - d3) + (d5 - d6)); return [0, 1 - w, w]; }
  const den = 1 / (va + vb + vc), v = vb * den, w = vc * den;
  return [1 - v - w, v, w];
}

/**
 * F10.1 · Punto della mesh, nello spazio UV, corrispondente a (u0, v0), con coordinate baricentriche.
 *
 * 1. Se un triangolo contiene (u0, v0) in UV, si usano le sue coordinate baricentriche: è esattamente
 *    l'interpolazione con cui la GPU campiona la texture, quindi P = λa·Pa + λb·Pb + λc·Pc mostra la
 *    lat/lon richiesta (scarto nullo a meno dell'arrotondamento). Tra più triangoli (bordi, cucitura)
 *    si sceglie quello in cui il punto è più interno (max min λ).
 * 2. Se nessun triangolo lo contiene (F10.1: vicino al polo sud la mappa UV della mesh non copre
 *    l'intero rettangolo [0,1]², quindi parte della texture non è mostrata da alcun triangolo),
 *    si prende il punto più vicino sul bordo di un triangolo, cioè il punto *visualizzato* più vicino.
 *    La distanza è misurata nella metrica locale equirettangolare del sito
 *    (Δu·360·cos lat0, Δv·180, con Δu ricondotto in [−0,5; 0,5] per la cucitura).
 * Nessuna conversione sferica lat/lon → XYZ: la posizione deriva solo dai vertici della mesh.
 */
export function findUvTriangle(geometry, u0, v0) {
  const uv = geometry.attributes.uv;
  const index = geometry.index;
  const triCount = index ? index.count / 3 : uv.count / 3;
  const EPS = 1e-9;
  const lat0 = (90 - v0 * 180) * DEG;
  const ku = Math.max(360 * Math.cos(lat0), 1e-6), kv = 180;
  const wrap = du => du - Math.round(du);
  let inside = null, closest = null;
  for (let t = 0; t < triCount; t++) {
    const ia = index ? index.getX(3 * t) : 3 * t;
    const ib = index ? index.getX(3 * t + 1) : 3 * t + 1;
    const ic = index ? index.getX(3 * t + 2) : 3 * t + 2;
    const va = uv.getY(ia), vb = uv.getY(ib), vc = uv.getY(ic);
    // scarto rapido in v: fuori dal triangolo e più lontano del miglior candidato
    const dvMin = Math.max(Math.min(va, vb, vc) - v0, v0 - Math.max(va, vb, vc), 0) * kv;
    if (inside || (closest && dvMin >= closest.dist)) { if (dvMin > 0) continue; }
    const ua = uv.getX(ia), ub = uv.getX(ib), uc = uv.getX(ic);
    if (dvMin === 0 && u0 >= Math.min(ua, ub, uc) - EPS && u0 <= Math.max(ua, ub, uc) + EPS) {
      const det = (vb - vc) * (ua - uc) + (uc - ub) * (va - vc);
      if (Math.abs(det) >= 1e-14) {
        const la = ((vb - vc) * (u0 - uc) + (uc - ub) * (v0 - vc)) / det;
        const lb = ((vc - va) * (u0 - uc) + (ua - uc) * (v0 - vc)) / det;
        const lc = 1 - la - lb;
        const m = Math.min(la, lb, lc);
        if (m >= -EPS && (!inside || m > inside.minLambda)) inside = { triangle: t, vertices: [ia, ib, ic], lambda: [la, lb, lc], minLambda: m, inside: true, dist: 0 };
      }
    }
    if (inside) continue;
    // coordinate locali (metrica del sito) relative al punto cercato
    const ax = wrap(ua - u0) * ku, ay = (va - v0) * kv;
    const bx = wrap(ub - u0) * ku, by = (vb - v0) * kv;
    const cx = wrap(uc - u0) * ku, cy = (vc - v0) * kv;
    if (closest && Math.min(Math.abs(ax), Math.abs(bx), Math.abs(cx)) > closest.dist &&
        Math.sign(ax) === Math.sign(bx) && Math.sign(bx) === Math.sign(cx)) continue;
    const l = closestBarycentric(ax, ay, bx, by, cx, cy);
    const px = l[0] * ax + l[1] * bx + l[2] * cx, py = l[0] * ay + l[1] * by + l[2] * cy;
    const dist = Math.hypot(px, py);
    if (!closest || dist < closest.dist) closest = { triangle: t, vertices: [ia, ib, ic], lambda: l, minLambda: Math.min(...l), inside: false, dist };
  }
  return inside || closest;
}

/**
 * Posizione del sito sul modello.
 * Metodo (F10.1): interpolazione baricentrica nel triangolo UV che contiene lat/lon ('barycentric');
 * se il punto cade in una zona UV non coperta dalla mesh, punto visualizzato più vicino sul triangolo
 * più vicino ('barycentric-closest'). Fallback: vertice più vicino (F9), solo se la mesh non ha triangoli.
 * Restituisce {position (mondo), separationDeg, method, nearestVertexSeparationDeg, triangle, lambda} oppure null.
 * separationDeg è la distanza angolare tra lat/lon richiesta e lat/lon della texture nel punto scelto.
 */
export function locateOnModel(model, latDeg, lonEastDeg) {
  const mesh = findMesh(model);
  if (!mesh) return null;
  const geometry = mesh.geometry;
  const uv = geometry.attributes.uv;
  const pos = geometry.attributes.position;
  const nearest = nearestVertex(uv, latDeg, lonEastDeg);
  if (nearest.index < 0) return null;
  mesh.updateWorldMatrix(true, false);
  const { u, v } = latLonToUv(latDeg, lonEastDeg);
  const hit = findUvTriangle(geometry, u, v);
  if (hit) {
    const local = new THREE.Vector3(), p = new THREE.Vector3();
    let uu = 0, vv = 0;
    const u0 = uv.getX(hit.vertices[0]);
    hit.vertices.forEach((i, k) => {
      local.addScaledVector(p.fromBufferAttribute(pos, i), hit.lambda[k]);
      const ui = uv.getX(i);
      uu += hit.lambda[k] * (ui + Math.round(u0 - ui)); // stessa falda della cucitura del primo vertice
      vv += hit.lambda[k] * uv.getY(i);
    });
    const separationDeg = uvSeparationDeg(uu, vv, latDeg, lonEastDeg);
    // Garanzia: il nuovo metodo non è mai peggiore del vertice più vicino.
    if (separationDeg <= nearest.separationDeg) {
      return {
        position: local.applyMatrix4(mesh.matrixWorld),
        separationDeg,
        method: hit.inside ? 'barycentric' : 'barycentric-closest',
        nearestVertexSeparationDeg: nearest.separationDeg,
        triangle: hit.triangle,
        lambda: hit.lambda,
      };
    }
  }
  const position = new THREE.Vector3().fromBufferAttribute(pos, nearest.index).applyMatrix4(mesh.matrixWorld);
  return { position, separationDeg: nearest.separationDeg, method: 'nearest-vertex', nearestVertexSeparationDeg: nearest.separationDeg, triangle: null, lambda: null };
}

/** Verifica di coerenza: il vertice con UV v≈0 (riga superiore = nord) deve stare a +Y. */
export function northIsUp(model) {
  const mesh = findMesh(model);
  if (!mesh) return null;
  const uv = mesh.geometry.attributes.uv, pos = mesh.geometry.attributes.position;
  let minV = Infinity, idx = -1;
  for (let i = 0; i < uv.count; i++) { const v = uv.getY(i); if (v < minV) { minV = v; idx = i; } }
  mesh.updateWorldMatrix(true, false);
  const p = new THREE.Vector3().fromBufferAttribute(pos, idx).applyMatrix4(mesh.matrixWorld);
  return p.y > 0;
}

/**
 * Crea i marker HTML (pulsanti) sovrapposti al canvas.
 * @param {object} o
 * @param {HTMLElement} o.layer contenitore posizionato sopra il canvas
 * @param {THREE.Object3D} o.model modello lunare caricato
 * @param {Array<{name:string, lat:number, lon:number}>} o.sites siti da /api/sites
 * @param {(name:string)=>void} o.onSelect
 */
export function createSiteMarkers({ layer, model, sites, onSelect }) {
  layer.replaceChildren();
  const markers = [];
  for (const s of sites) {
    const hit = locateOnModel(model, s.lat, s.lon);
    if (!hit) continue;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'globe-marker';
    button.dataset.site = s.name;
    button.setAttribute('aria-pressed', 'false');
    button.setAttribute('aria-label', `${s.name}, latitudine ${s.lat.toFixed(2)}°, longitudine ${s.lon.toFixed(2)}° E`);
    const dot = document.createElement('span');
    dot.className = 'globe-marker-dot';
    const label = document.createElement('span');
    label.className = 'globe-marker-label';
    label.textContent = s.name;
    button.append(dot, label);
    button.addEventListener('click', () => onSelect(s.name));
    layer.append(button);
    button.dataset.method = hit.method;
    markers.push({ name: s.name, button, position: hit.position, normal: hit.position.clone().normalize(), separationDeg: hit.separationDeg, method: hit.method, nearestVertexSeparationDeg: hit.nearestVertexSeparationDeg });
  }

  const v = new THREE.Vector3(), toCam = new THREE.Vector3();
  let selectedName = null;
  function update(camera, width, height) {
    const placed = [];
    // Il marker selezionato si posiziona per primo: le etichette vicine si nascondono (resta il punto).
    const ordered = [...markers].sort((a, b) => (b.name === selectedName) - (a.name === selectedName));
    for (const m of ordered) {
      toCam.copy(camera.position).sub(m.position);
      const facing = m.normal.dot(toCam.normalize()) > 0.05;
      v.copy(m.position).project(camera);
      const inside = v.z < 1 && Math.abs(v.x) <= 1.05 && Math.abs(v.y) <= 1.05;
      m.button.hidden = !(facing && inside);
      if (!m.button.hidden) {
        const x = (v.x * 0.5 + 0.5) * width, y = (-v.y * 0.5 + 0.5) * height;
        m.button.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;
        const crowded = placed.some(p => Math.abs(p.x - x) < 110 && Math.abs(p.y - y) < 22);
        m.button.classList.toggle('label-hidden', crowded);
        placed.push({ x, y });
      }
    }
  }
  function select(name) {
    selectedName = name;
    for (const m of markers) {
      const on = m.name === name;
      m.button.classList.toggle('is-selected', on);
      m.button.setAttribute('aria-pressed', String(on));
    }
  }
  function direction(name) {
    const m = markers.find(x => x.name === name);
    return m ? m.normal.clone() : null;
  }
  return { markers, update, select, direction };
}
