// F10.1 · Esegue il codice reale di src/ui_web/ui/globe-markers.js sul GLB reale, senza browser.
// Uso: node tests/js/globe_markers_geodesy.mjs <file.glb> '<json [{name,lat,lon}]>'
// Stampa JSON con, per ogni sito, il risultato di locateOnModel() e i controlli indipendenti.
// Il GLB è letto in sola lettura (parsing del contenitore glTF binario, nessuna modifica).
import { readFileSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, resolve } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const uiWeb = resolve(here, '../../src/ui_web');
// Stessa istanza di three usata da globe-markers.js (risolta da src/ui_web/node_modules).
const threeUrl = pathToFileURL(resolve(uiWeb, 'node_modules/three/build/three.module.js')).href;
const THREE = await import(threeUrl);
// src/ui_web/package.json dichiara CommonJS: il modulo ES del browser viene importato come
// data: URL con l'unica sostituzione dello specificatore 'three' (nel browser lo risolve l'importmap).
const markersSrc = readFileSync(resolve(uiWeb, 'ui/globe-markers.js'), 'utf8');
if (!markersSrc.includes("from 'three'")) throw new Error("import di 'three' non trovato in globe-markers.js");
const markers = await import('data:text/javascript;base64,' +
  Buffer.from(markersSrc.replace("from 'three'", `from '${threeUrl}'`)).toString('base64'));

const [glbPath, sitesJson] = process.argv.slice(2);
const sites = JSON.parse(sitesJson);
const buf = readFileSync(glbPath);
if (buf.toString('ascii', 0, 4) !== 'glTF') throw new Error('non è un GLB');
const jsonLen = buf.readUInt32LE(12);
const gltf = JSON.parse(buf.toString('utf8', 20, 20 + jsonLen));
const bin = 20 + jsonLen + 8;
function accessor(i) {
  const a = gltf.accessors[i], bv = gltf.bufferViews[a.bufferView];
  const off = buf.byteOffset + bin + (bv.byteOffset || 0) + (a.byteOffset || 0);
  const n = { SCALAR: 1, VEC2: 2, VEC3: 3 }[a.type];
  const T = a.componentType === 5125 ? Uint32Array : Float32Array;
  return { array: new T(buf.buffer.slice(off, off + a.count * n * T.BYTES_PER_ELEMENT)), itemSize: n };
}
const prim = gltf.meshes[0].primitives[0];
const geometry = new THREE.BufferGeometry();
const P = accessor(prim.attributes.POSITION), UV = accessor(prim.attributes.TEXCOORD_0), I = accessor(prim.indices);
geometry.setAttribute('position', new THREE.BufferAttribute(P.array, 3));
geometry.setAttribute('uv', new THREE.BufferAttribute(UV.array, 2));
geometry.setIndex(new THREE.BufferAttribute(I.array, 1));
const mesh = new THREE.Mesh(geometry);
const model = new THREE.Group();
model.add(mesh);

const out = [];
for (const s of sites) {
  const t0 = Date.now();
  const hit = markers.locateOnModel(model, s.lat, s.lon);
  const ms = Date.now() - t0;
  const r = { name: s.name, lat: s.lat, lon: s.lon, ms, method: hit?.method ?? null };
  if (hit) {
    r.position = hit.position.toArray();
    r.separationDeg = hit.separationDeg;
    r.nearestVertexSeparationDeg = hit.nearestVertexSeparationDeg;
    r.triangle = hit.triangle;
    r.lambda = hit.lambda;
    if (hit.triangle !== null) {
      // Controllo indipendente: il punto deve stare sul piano del triangolo 3D e dentro di esso.
      const v = [0, 1, 2].map(k => new THREE.Vector3().fromBufferAttribute(geometry.attributes.position, geometry.index.getX(3 * hit.triangle + k)));
      const tri = new THREE.Triangle(...v);
      const p = hit.position.clone();
      const closest = tri.closestPointToPoint(p, new THREE.Vector3());
      r.distanceFromTriangle = closest.distanceTo(p);
      r.triangleVertices = v.map(x => x.toArray());
      r.uvVertices = [0, 1, 2].map(k => { const i = geometry.index.getX(3 * hit.triangle + k); return [geometry.attributes.uv.getX(i), geometry.attributes.uv.getY(i)]; });
    }
  }
  out.push(r);
}
const target = markers.latLonToUv(-89.7668, -171.87);
console.log(JSON.stringify({ sites: out, uvShackleton: target }));
