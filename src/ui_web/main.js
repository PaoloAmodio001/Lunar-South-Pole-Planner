// Last updated: 2026-11-15 (F9: vista polare, luce radente indicativa, OrbitControls, marker, avanzamento)
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { createSiteMarkers, northIsUp } from '/ui/globe-markers.js';

const canvas = document.querySelector('#viewport');
const message = document.querySelector('#message');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
const scene = new THREE.Scene();
scene.background = new THREE.Color('#070d16');

const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 1000);
const INITIAL_DISTANCE = 8.4;
// Vista iniziale dal polo sud: asse polare = Y del modello (verificato al caricamento con northIsUp).
const POLAR_VIEW = new THREE.Spherical(INITIAL_DISTANCE, THREE.MathUtils.degToRad(152), THREE.MathUtils.degToRad(25));
const HEMISPHERE_VIEW = new THREE.Spherical(9.2, THREE.MathUtils.degToRad(92), THREE.MathUtils.degToRad(18));
camera.position.setFromSpherical(POLAR_VIEW);

let renderer = null;
try {
  renderer = new THREE.WebGLRenderer({canvas, antialias:true, alpha:false});
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  document.querySelector('#webglStatus').textContent = 'READY';
} catch (err) {
  console.error(err);
  document.querySelector('#webglStatus').textContent = 'NON DISPONIBILE';
  document.querySelector('#webglStatus').className = 'warn';
}

// Illuminazione INDICATIVA: una luce radente quasi perpendicolare all'asse polare, per rendere
// leggibile il rilievo della geometria. NON rappresenta la posizione reale del Sole (che l'API
// non fornisce al globo): la didascalia #globeLightNote lo dichiara nell'interfaccia.
scene.add(new THREE.HemisphereLight(0x9fb8d0, 0x1a2230, 0.42));
const grazingLight = new THREE.DirectionalLight(0xfff1dc, 3.8);
grazingLight.position.set(7, -0.45, 3.2); // circa 3° sotto il piano equatoriale: radente al polo sud
scene.add(grazingLight);
const earthshine = new THREE.DirectionalLight(0x5ccfe6, 0.14);
earthshine.position.set(-5, -1.5, -4);
scene.add(earthshine);

const stars = new THREE.BufferGeometry();
const positions = [];
for (let i=0;i<1800;i++) {
  const r=30+Math.random()*100;
  const a=Math.random()*Math.PI*2, z=Math.random()*2-1;
  const q=Math.sqrt(1-z*z);
  positions.push(r*q*Math.cos(a),r*z,r*q*Math.sin(a));
}
stars.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
scene.add(new THREE.Points(stars,new THREE.PointsMaterial({color:0x9cb9d7,size:0.055,transparent:true,opacity:0.6})));

const root = new THREE.Group();
scene.add(root);
let moon = null;

// Controlli: OrbitControls r186 vendorizzato (D-F5). Nessun pan; zoom limitato.
const controls = renderer ? new OrbitControls(camera, canvas) : null;
if (controls) {
  controls.enableDamping = !reducedMotion.matches;
  controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.minDistance = 4.2;
  controls.maxDistance = 15;
  controls.minPolarAngle = 0.05;
  controls.maxPolarAngle = Math.PI - 0.05;
  controls.rotateSpeed = 0.6;
  controls.autoRotate = !reducedMotion.matches;
  controls.autoRotateSpeed = 0.25; // rotazione attorno all'asse polare: il polo resta inquadrato
  controls.addEventListener('start', () => { controls.autoRotate = false; });
  reducedMotion.addEventListener?.('change', e => { controls.autoRotate = !e.matches && controls.autoRotate; controls.enableDamping = !e.matches; });
}

// --- Volo della camera (immediato con reduced motion) ---
let flight = null;
function flyTo(spherical) {
  if (!controls) return;
  const from = new THREE.Spherical().setFromVector3(camera.position);
  const to = spherical.clone();
  to.phi = THREE.MathUtils.clamp(to.phi, controls.minPolarAngle, controls.maxPolarAngle);
  if (reducedMotion.matches) { camera.position.setFromSpherical(to); controls.update(); return; }
  let dTheta = to.theta - from.theta;
  dTheta = Math.atan2(Math.sin(dTheta), Math.cos(dTheta));
  flight = { from, dTheta, to, t0: performance.now(), ms: 650 };
}
function stepFlight(now) {
  if (!flight) return;
  const k = Math.min(1, (now - flight.t0) / flight.ms);
  const e = 1 - Math.pow(1 - k, 3);
  const s = new THREE.Spherical(
    flight.from.radius + (flight.to.radius - flight.from.radius) * e,
    flight.from.phi + (flight.to.phi - flight.from.phi) * e,
    flight.from.theta + flight.dTheta * e);
  camera.position.setFromSpherical(s);
  if (k >= 1) flight = null;
}
function resetView() { if (controls) controls.autoRotate = false; flyTo(POLAR_VIEW); }

// --- Caricamento del modello con avanzamento reale (onProgress) ---
const loader = new GLTFLoader();
const modelUrl = '/data/terrain/global/Moon_NASA_LRO_8k_Topo_Small.glb';
const progressBox = document.querySelector('#globeProgress');
const progressBar = document.querySelector('#globeProgressBar');
const progressText = document.querySelector('#globeProgressText');
const globeError = document.querySelector('#globeError');
const modelStatus = document.querySelector('#modelStatus');

function setProgress(loaded, total) {
  if (!progressBox) return;
  progressBox.hidden = false;
  const mb = (loaded / 1048576).toFixed(1);
  if (total) {
    const pct = Math.min(100, Math.round(loaded / total * 100));
    progressBar?.setAttribute('aria-valuenow', String(pct));
    progressBox.style.setProperty('--progress', `${pct}%`);
    progressText.textContent = `Modello LRO ${pct} % · ${mb} di ${(total / 1048576).toFixed(1)} MB`;
  } else {
    progressBar?.removeAttribute('aria-valuenow');
    progressText.textContent = `Modello LRO · ${mb} MB ricevuti`;
  }
}

let markerSet = null;
let siteList = null;
function buildMarkers() {
  if (!moon || !siteList) return;
  const layer = document.querySelector('#globeMarkers');
  if (!layer) return;
  markerSet = createSiteMarkers({
    layer, model: moon, sites: siteList,
    onSelect: name => {
      const select = document.querySelector('#site');
      select.value = name;
      select.dispatchEvent(new Event('change'));
    }
  });
  markerSet.select(document.querySelector('#site').value);
}
function focusSite(name) {
  if (!markerSet) return;
  markerSet.select(name);
  const dir = markerSet.direction(name);
  if (!dir || !controls) return;
  controls.autoRotate = false;
  const s = new THREE.Spherical().setFromVector3(dir);
  s.radius = Math.min(camera.position.length(), 7.2);
  s.phi = Math.min(s.phi, Math.PI - THREE.MathUtils.degToRad(24)); // inclinazione per vedere il bordo
  flyTo(s);
}
// Chiamata dalla sezione dei siti più sotto, quando /api/sites risponde.
function globeSitesReady(list) { siteList = list; buildMarkers(); }

let modelLoading = false;
function loadModel() {
  // F11: niente caricamenti doppi (doppio clic su "Riprova") né secondo modello in scena.
  if (!renderer || modelLoading || moon) return;
  modelLoading = true;
  globeError && (globeError.hidden = true);
  modelStatus.textContent = 'LOADING';
  modelStatus.className = 'warn';
  setProgress(0, 0);
  loader.load(modelUrl, gltf => {
    modelLoading = false;
    moon = gltf.scene;
    const box = new THREE.Box3().setFromObject(moon);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const extent = Math.max(size.x,size.y,size.z);
    if (!extent) throw new Error('Il modello lunare ha dimensioni nulle');
    moon.scale.setScalar(4.5/extent);
    moon.position.set(-center.x*moon.scale.x,-center.y*moon.scale.y,-center.z*moon.scale.z);
    moon.traverse(obj => {
      if (obj.isMesh) {
        obj.castShadow = false;
        obj.receiveShadow = true;
        if (obj.material) {
          obj.material.side = THREE.FrontSide;
          const materials = Array.isArray(obj.material) ? obj.material : [obj.material];
          for (const material of materials) {
            if ('roughness' in material) material.roughness = 0.97;
            if ('metalness' in material) material.metalness = 0;
            for (const key of ['map','normalMap','roughnessMap','metalnessMap','aoMap','emissiveMap']) {
              const texture = material[key];
              if (!texture) continue;
              texture.minFilter = THREE.LinearMipmapLinearFilter;
              texture.magFilter = THREE.LinearFilter;
              texture.generateMipmaps = true;
              texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
              texture.needsUpdate = true;
            }
            material.needsUpdate = true;
          }
        }
      }
    });
    root.add(moon);
    const up = northIsUp(moon);
    if (up === false) console.warn('Convenzione UV inattesa: il nord della texture non è a +Y. Marker da verificare.');
    if (progressBox) progressBox.hidden = true;
    modelStatus.textContent='LOADED';
    modelStatus.className='good';
    message.textContent='Modello lunare caricato. Trascina per ruotare, rotella o +/− per lo zoom.';
    buildMarkers();
    if (markerSet) focusSite(document.querySelector('#site').value);
  }, xhr => setProgress(xhr.loaded, xhr.lengthComputable ? xhr.total : 0), err => {
    modelLoading = false;
    console.error(err);
    if (progressBox) progressBox.hidden = true;
    modelStatus.textContent='LOAD ERROR';
    modelStatus.className='warn';
    message.textContent='Il modello lunare non è stato caricato. Controlla la connessione al server e riprova.';
    if (globeError) globeError.hidden = false;
  });
}
document.querySelector('#globeRetry')?.addEventListener('click', loadModel);
loadModel();
if (!renderer && globeError) {
  globeError.hidden = false;
  globeError.querySelector('p').textContent = 'WebGL non è disponibile in questo browser: il globo non può essere mostrato. I pannelli di analisi restano utilizzabili.';
  globeError.querySelector('button').hidden = true;
}

function resize(){
 const w=canvas.clientWidth,h=canvas.clientHeight;
 if(!w||!h||!renderer)return;
 renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(canvas);
resize();

// Comandi della camera (pulsanti) e tastiera sul canvas.
function zoomBy(factor) {
  if (!controls) return;
  const d = THREE.MathUtils.clamp(camera.position.length() * factor, controls.minDistance, controls.maxDistance);
  camera.position.setLength(d);
}
function orbitBy(dTheta, dPhi) {
  if (!controls) return;
  controls.autoRotate = false;
  const s = new THREE.Spherical().setFromVector3(camera.position);
  s.theta += dTheta;
  s.phi = THREE.MathUtils.clamp(s.phi + dPhi, controls.minPolarAngle, controls.maxPolarAngle);
  camera.position.setFromSpherical(s);
}
document.querySelector('#globeZoomIn')?.addEventListener('click', () => zoomBy(0.85));
document.querySelector('#globeZoomOut')?.addEventListener('click', () => zoomBy(1 / 0.85));
document.querySelector('#globePolar')?.addEventListener('click', resetView);
document.querySelector('#globeHemisphere')?.addEventListener('click', () => { if (controls) controls.autoRotate = false; flyTo(HEMISPHERE_VIEW); });
canvas.tabIndex = 0;
canvas.addEventListener('keydown', e => {
  const step = THREE.MathUtils.degToRad(5);
  const map = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
  if (map[e.key]) { orbitBy(...map[e.key]); e.preventDefault(); }
  else if (e.key === '+' || e.key === '=') { zoomBy(0.85); e.preventDefault(); }
  else if (e.key === '-') { zoomBy(1 / 0.85); e.preventDefault(); }
  else if (e.key === 'Home' || e.key === '0') { resetView(); e.preventDefault(); }
});
canvas.addEventListener('dblclick', resetView);

const markerLayer = document.querySelector('#globeMarkers');
function animate(now){
 requestAnimationFrame(animate);
 if (!renderer || document.hidden) return;
 stepFlight(now);
 controls?.update();
 renderer.render(scene,camera);
 if (markerSet && markerLayer) markerSet.update(camera, canvas.clientWidth, canvas.clientHeight);
}
requestAnimationFrame(animate);

// Coordinate dei siti: unica fonte src.astronomy.SITES tramite /api/sites (F5).
let sites = {};
fetch('/api/sites', {cache: 'no-store'})
 .then(r => r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`)))
 .then(data => {
  sites = Object.fromEntries((data.sites || []).map(s => [s.name, [s.latitude_deg, s.longitude_east_deg]]));
  update();
  globeSitesReady((data.sites || []).map(s => ({ name: s.name, lat: s.latitude_deg, lon: s.longitude_east_deg })));
 })
 .catch(() => { document.querySelector('#coords').textContent = 'coordinate non disponibili'; });
const site = document.querySelector('#site');
function update(){
 const name=site.value;
 const coords=sites[name];
 document.querySelector('#targetName').textContent=name;
 document.querySelector('#siteLabel').textContent='TARGET: '+name.toUpperCase();
 document.querySelector('#coords').textContent=coords
  ? `${coords[0].toFixed(2)}°, ${coords[1].toFixed(2)}°` : 'Loading…';
 const duration=Math.max(1,Math.min(720,Number(document.querySelector('#duration').value)||48));
 document.querySelector('#durationValue').textContent=duration;
 document.querySelector('#scienceValue').textContent=document.querySelector('#science').value+' / 5';
 document.querySelector('#engineeringValue').textContent=document.querySelector('#engineering').value+' / 5';
 document.querySelector('#elevationValue').textContent=document.querySelector('#elevation').value+'°';
 const earthValue=document.querySelector('#earthElevationValue');
 if(earthValue) earthValue.textContent=document.querySelector('#earthElevation').value+'°';
}
document.querySelector('#apply').addEventListener('click',update);
site.addEventListener('change',update);
site.addEventListener('change',()=>focusSite(site.value));
document.querySelector('#reset').addEventListener('click',resetView);
const dateInput=document.querySelector('#date');
// Il campo è "inizio UTC" e il backend lo interpreta come UTC: il valore iniziale è
// l'ora UTC corrente (prima era l'ora locale etichettata come UTC, sfasata del fuso orario).
dateInput.value=new Date().toISOString().slice(0,16);
document.querySelector('#publicDate').value = dateInput.value;
update();

// I grafici vengono disegnati esclusivamente con campioni JPL reali.


// ===== REAL JPL HORIZONS DATA =====
const chart1 = document.querySelector('#chart1');
const chart2 = document.querySelector('#chart2');
const applyButton = document.querySelector('#apply');
const liveStatus = document.querySelector('#ephemerisStatus');
const chartNames = document.querySelectorAll('.graphname');

if (chartNames.length >= 2) {
  chartNames[0].textContent = 'Elevazione del Sole · JPL Horizons';
  chartNames[1].textContent = 'Elevazione della Terra · finestre operative';
}

if (liveStatus) liveStatus.textContent = 'READY';

// Classificazione degli errori delle effemeridi (codici dal backend, vedi app.py EPHEMERIS_ERRORS).
const EPHEMERIS_ERROR_TEXT = {
  backend_unreachable: ['BACKEND OFFLINE',
    'Backend Lunar Mission Control non raggiungibile: il server Python non è in esecuzione o la connessione è interrotta. Avvialo con ./start.sh: la richiesta verrà ripetuta automaticamente quando il backend torna disponibile.'],
  backend_invalid: ['BACKEND ERROR', 'Il backend ha restituito una risposta non leggibile'],
  backend_error: ['BACKEND ERROR', 'Errore interno del backend'],
  jpl_timeout: ['JPL UNAVAILABLE', 'Servizio NASA/JPL Horizons non disponibile (timeout)'],
  jpl_unreachable: ['JPL UNAVAILABLE', 'Servizio NASA/JPL Horizons non raggiungibile dal backend (rete o DNS)'],
  jpl_http_error: ['JPL UNAVAILABLE', 'Servizio NASA/JPL Horizons in errore'],
  jpl_rejected: ['INVALID DATA', 'Richiesta rifiutata da NASA/JPL Horizons'],
  jpl_invalid_response: ['INVALID DATA', 'Risposta astronomica non valida'],
  invalid_request: ['ERROR', 'Parametri non validi'],
  session_expired: ['ERROR', 'Sessione scaduta'],
  auth_required: ['ERROR', 'Autenticazione richiesta']
};
let ephemerisRecovery = null;

function classifyEphemerisError(err) {
  const code = err && err.code ? err.code : 'backend_error';
  const [status, label] = EPHEMERIS_ERROR_TEXT[code] || ['ERROR', 'Effemeridi non disponibili'];
  const detail = code === 'backend_unreachable' ? '' : (err && err.message ? `: ${err.message}` : '');
  return { code, status, text: `${label}${detail}` };
}

// Ripristino automatico: backend spento → riprova quando /api/health risponde;
// JPL non disponibile → controlla /api/services?refresh=1 ogni 60 s e riprova quando torna.
function scheduleEphemerisRecovery(code) {
  if (ephemerisRecovery) return;
  if (code === 'backend_unreachable') {
    ephemerisRecovery = { code };
    return; // gestito dall'evento lmc:backend
  }
  if (!['jpl_timeout', 'jpl_unreachable', 'jpl_http_error'].includes(code)) return;
  ephemerisRecovery = { code, timer: setInterval(async () => {
    if (document.hidden) return;
    try {
      const r = await fetch('/api/services?refresh=1', { cache: 'no-store' });
      const s = await r.json();
      if (s.jpl_horizons && s.jpl_horizons.available) {
        clearEphemerisRecovery();
        updateEphemerides();
      }
    } catch (_) { /* backend spento: se ne occupa lmc:backend */ }
  }, 60000) };
}
function clearEphemerisRecovery() {
  if (ephemerisRecovery && ephemerisRecovery.timer) clearInterval(ephemerisRecovery.timer);
  ephemerisRecovery = null;
}
window.addEventListener('lmc:backend', e => {
  if (e.detail.available && ephemerisRecovery && ephemerisRecovery.code === 'backend_unreachable') {
    clearEphemerisRecovery();
    updateEphemerides();
  }
});

function drawEphemerisChart(canvas, observations, field, threshold, color, windows = []) {
  const ctx = canvas.getContext('2d');
  const cssW = Math.max(100, canvas.clientWidth);
  const cssH = Math.max(80, canvas.clientHeight);
  const dpr = Math.min(window.devicePixelRatio || 1, 2);

  canvas.width = Math.round(cssW * dpr);
  canvas.height = Math.round(cssH * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);

  const left = 34, right = 8, top = 8, bottom = 22;
  const w = cssW - left - right, h = cssH - top - bottom;
  const values = observations.map(o => o[field]).filter(Number.isFinite);
  if (values.length < 2) {
    ctx.fillStyle = '#9AA6B2';
    ctx.font = '12px Archivo, system-ui, sans-serif';
    ctx.fillText('Dati insufficienti', left, top + 20);
    return;
  }

  const minY = Math.min(-10, Math.floor(Math.min(...values) / 10) * 10);
  const maxY = Math.max(10, Math.ceil(Math.max(...values) / 10) * 10);
  const x = i => left + i * w / (observations.length - 1);
  const y = v => top + (maxY - v) * h / (maxY - minY);

  // Evidenzia gli intervalli che soddisfano entrambe le soglie.
  for (const win of windows) {
    const start = observations.findIndex(o => o.time_utc === win.start_utc);
    const end = observations.findIndex(o => o.time_utc === win.end_utc);
    if (start >= 0 && end >= start) {
      ctx.fillStyle = 'rgba(76, 195, 138, 0.14)';
      ctx.fillRect(x(start), top, Math.max(2, x(end) - x(start)), h);
    }
  }

  ctx.font = '12px Archivo, system-ui, sans-serif';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let tick = Math.ceil(minY / 30) * 30; tick <= maxY; tick += 30) {
    const yy = y(tick);
    ctx.strokeStyle = '#323A44';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(left, yy); ctx.lineTo(cssW-right, yy); ctx.stroke();
    ctx.fillStyle = '#9AA6B2';
    ctx.fillText(`${tick}°`, left - 5, yy);
  }

  if (Number.isFinite(threshold) && threshold >= minY && threshold <= maxY) {
    ctx.save();
    ctx.setLineDash([4, 4]);
    ctx.strokeStyle = color;
    ctx.beginPath(); ctx.moveTo(left, y(threshold)); ctx.lineTo(cssW-right, y(threshold)); ctx.stroke();
    ctx.restore();
  }

  ctx.strokeStyle = color;
  ctx.lineWidth = 1.8;
  ctx.lineJoin = 'round';
  ctx.beginPath();
  observations.forEach((o, i) => {
    const v = o[field];
    if (!Number.isFinite(v)) return;
    if (i === 0) ctx.moveTo(x(i), y(v));
    else ctx.lineTo(x(i), y(v));
  });
  ctx.stroke();

  ctx.fillStyle = '#9AA6B2';
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
  ctx.fillText(observations[0].time_utc.slice(11, 16) + ' UTC', left, cssH - 5);
  ctx.textAlign = 'right';
  ctx.fillText(observations[observations.length - 1].time_utc.slice(11, 16) + ' UTC', cssW-right, cssH-5);
}




function renderMissionAnalytics(a) {
  const put = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  };
  const fmt = v => Number.isFinite(v) ? `${v.toFixed(2)}°` : '—';
  const statsText = s => s
    ? `min ${fmt(s.min)} · max ${fmt(s.max)} · media ${fmt(s.mean)}`
    : 'Dati non disponibili';

  const pct = value => Number.isFinite(value) ? `${value.toFixed(1)}%` : 'N/D';
  const count = value => Number.isFinite(value) ? value : 0;
  const valid = count(a.valid_sample_count);
  const sun = a.sun || {};
  const earth = a.earth || {};
  const simultaneous = a.simultaneous || {};
  const windows = a.operational_windows || {};

  put('analyticsStatus', `${valid}/${count(a.sample_count)} VALID SAMPLES`);
  put('sunStats', statsText(sun));
  put('earthStats', statsText(earth));
  put('sunPass', `${count(sun.passing_samples)}/${valid} campioni · ${pct(sun.passing_percent)} sopra soglia`);
  put('earthPass', `${count(earth.passing_samples)}/${valid} campioni · ${pct(earth.passing_percent)} sopra soglia`);
  put('combinedPass', pct(simultaneous.passing_percent));
  put('combinedCount', `${count(simultaneous.passing_samples)}/${valid} campioni simultanei`);
  put('analyticsWindowCount', String(count(windows.count)));
  put('analyticsWindowSpan', `${Number.isFinite(windows.total_sampled_span_hours) ? windows.total_sampled_span_hours.toFixed(1) : '—'} h di intervallo campionato totale`);
  put('analyticsDiagnosis', a.diagnosis || 'Diagnosi non disponibile.');
}

function renderOperationalWindows(data, observations, windows) {
  const tbody = document.querySelector('#operationalWindows');
  const count = document.querySelector('#windowCount');
  const notice = document.querySelector('#windowNotice');
  if (!tbody || !count || !notice) return;

  count.textContent = `${windows.length} WINDOWS`;
  notice.textContent = data.notice ||
    'Finestre geometriche preliminari: non verificano ostacoli, budget radio o sicurezza.';

  const fmtTime = value => {
    const d = new Date(value);
    return Number.isNaN(d.getTime())
      ? '—'
      : d.toISOString().slice(0, 16).replace('T', ' ');
  };

  if (!windows.length) {
    tbody.innerHTML =
      '<tr><td colspan="8" class="empty-windows">' +
      'Nessuna finestra soddisfa contemporaneamente entrambe le soglie nel periodo selezionato.' +
      '</td></tr>';
    return;
  }

  tbody.replaceChildren();
  windows.forEach((win, index) => {
    const tr = document.createElement('tr');
    const values = [
      String(index + 1),
      fmtTime(win.start_utc),
      fmtTime(win.end_utc),
      `${win.sampled_span_hours ?? Math.max(0, win.duration_samples - 1)} h · ${win.duration_samples} campioni`,
      `${Number(win.min_sun_elevation_deg).toFixed(2)}°`,
      `${Number(win.min_earth_elevation_deg).toFixed(2)}°`,
      win.ranking && Number.isFinite(win.ranking.score)
        ? `#${win.ranking.rank} · ${win.ranking.score.toFixed(1)}`
        : '—',
      'GEOMETRIC OK'
    ];

    values.forEach((value, i) => {
      const td = document.createElement('td');
      td.textContent = value;
      if (i === 6 && win.ranking) {
        td.title = `Scienza ${win.ranking.science_score.toFixed(1)} · Ingegneria ${win.ranking.engineering_score.toFixed(1)} · Durata ${win.ranking.duration_score.toFixed(1)}. ${win.ranking.score_method}`;
      }
      if (i === 7) td.className = 'window-ok';
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

async function updateEphemerides() {
  if (applyButton.disabled) return;

  const statusMessage = document.body.classList.contains('public-mode')
    ? document.querySelector('#publicMessage')
    : message;

  const site = document.querySelector('#site').value;
  const dateInput = document.querySelector('#date');
  const hours = Number(document.querySelector('#duration').value);
  const minSun = Number(document.querySelector('#elevation').value);
  const science = Number(document.querySelector('#science').value);
  const engineering = Number(document.querySelector('#engineering').value);
  const minEarth = Number(document.querySelector('#earthElevation').value);

  if (!dateInput.value) {
    statusMessage.textContent = 'Seleziona data e ora di inizio UTC.';
    dateInput.focus();
    return;
  }
  if (!Number.isInteger(hours) || hours < 1 || hours > 720 ||
      !Number.isFinite(minSun) || minSun < -90 || minSun > 90 ||
      !Number.isFinite(minEarth) || minEarth < -90 || minEarth > 90 ||
      !Number.isInteger(science) || science < 1 || science > 5 ||
      !Number.isInteger(engineering) || engineering < 1 || engineering > 5) {
    statusMessage.textContent = 'Controlla durata, soglia e priorità: valori fuori intervallo.';
    return;
  }

  const params = new URLSearchParams({
    site, start: dateInput.value, hours: String(hours),
    min_sun: String(minSun), min_earth: String(minEarth)
  });

  applyButton.disabled = true;
  applyButton.textContent = 'CALCULATING…';
  statusMessage.textContent = 'Richiesta effemeridi NASA/JPL Horizons…';
  if (liveStatus) liveStatus.textContent = 'CALCULATING';

  try {
    let response;
    try {
      response = await fetch(`/api/ephemerides?${params.toString()}`, {cache: 'no-store'});
    } catch (networkError) {
      const e = new Error(networkError.message);
      e.code = 'backend_unreachable';
      throw e;
    }
    let data;
    try {
      data = await response.json();
    } catch (_) {
      const e = new Error(`HTTP ${response.status}, contenuto non JSON`);
      e.code = 'backend_invalid';
      throw e;
    }
    if (!response.ok || data.status !== 'ok') {
      const e = new Error(data.error || `HTTP ${response.status}`);
      e.code = data.error_code || (response.status >= 500 ? 'backend_error' : 'invalid_request');
      throw e;
    }
    clearEphemerisRecovery();

    const observations = data.observations || [];
    if (observations.length < 2) {
      const e = new Error('Horizons ha restituito meno di due osservazioni.');
      e.code = 'jpl_invalid_response';
      throw e;
    }

    drawEphemerisChart(chart1, observations, 'sun_elevation_deg',
      data.thresholds.sun_elevation_deg, '#EAD9A7', data.windows);
    drawEphemerisChart(chart2, observations, 'earth_elevation_deg',
      data.thresholds.earth_elevation_deg, '#5CCFE6', data.windows);

    document.querySelector('#targetName').textContent = data.site;
    document.querySelector('#coords').textContent =
      `${data.latitude_deg.toFixed(4)}°, ${data.longitude_east_deg.toFixed(4)}°`;
    document.querySelector('#durationValue').textContent = data.duration_hours;
    document.querySelector('#scienceValue').textContent = `${science} / 5`;
    document.querySelector('#engineeringValue').textContent = `${engineering} / 5`;
    document.querySelector('#elevationValue').textContent = `${minSun}°`;
    document.querySelector('#earthElevationValue').textContent = `${minEarth}°`;
    document.querySelector('#siteLabel').textContent = `TARGET: ${data.site.toUpperCase()}`;

    if (liveStatus) {
      liveStatus.textContent = 'CONNECTED · JPL';
      liveStatus.className = 'good';
    }

    const windows = data.windows || [];
    // Analytics calcolati solo dal backend (src.mission_analytics), F5.
    const analytics = data.analytics;
    if (!analytics) {
      throw new Error('Analytics non forniti dal server: nessun ricalcolo lato client.');
    }

    if (analytics.schema &&
        analytics.schema !== 'lunar-ephemeris-analytics/1.0') {
      throw new Error(`Schema analytics non riconosciuto: ${analytics.schema}`);
    }

    data.analytics = analytics;
    data.science_priority = science;
    data.engineering_priority = engineering;
    window.lastEphemerides = data;

    renderMissionAnalytics(analytics);
    renderOperationalWindows(data, observations, windows);
    const summary = windows.length
      ? windows.map((win, i) =>
          `#${i+1} ${win.start_utc.slice(0,16).replace('T',' ')} – ` +
          `${win.end_utc.slice(0,16).replace('T',' ')} UTC`
        ).join(' | ')
      : 'Nessuna finestra soddisfa entrambe le soglie nel periodo selezionato.';

    statusMessage.textContent =
      `${data.source} · ${observations.length} campioni · ${windows.length} finestre geometriche. ` +
      summary + ' — Non include verifica ostacoli o budget radio.';
    document.querySelectorAll('.graphname')[0].textContent =
      `Elevazione del Sole · ${observations.length} campioni`;
    document.querySelectorAll('.graphname')[1].textContent =
      `Elevazione della Terra · ${windows.length} finestre`;
  } catch (err) {
    console.error('Ephemerides error:', err);
    const info = classifyEphemerisError(err);
    if (liveStatus) {
      liveStatus.textContent = info.status;
      liveStatus.className = 'warn';
    }
    const stale = window.lastEphemerides ? ' I grafici mostrano ancora l\'ultima richiesta riuscita.' : '';
    statusMessage.textContent = `Effemeridi non disponibili — ${info.text}. Nessun dato dimostrativo mostrato.${stale}`;
    scheduleEphemerisRecovery(info.code);
  } finally {
    applyButton.disabled = false;
    applyButton.textContent = 'UPDATE VISUALIZATION';
  }
}

applyButton.addEventListener('click', updateEphemerides);

// Selezione dei siti candidati.
const publicSiteButtons = document.querySelectorAll('.public-site');
const publicAnalyzeButton = document.querySelector('#publicAnalyze');
const publicMessage = document.querySelector('#publicMessage');

const publicDate = document.querySelector('#publicDate');
const publicDuration = document.querySelector('#publicDuration');
const publicSunElevation = document.querySelector('#publicSunElevation');
const publicEarthElevation = document.querySelector('#publicEarthElevation');

publicSiteButtons.forEach(button => {
  button.addEventListener('click', () => {
    publicSiteButtons.forEach(item => {
      const selected = item === button;
      item.classList.toggle('selected', selected);
      item.setAttribute('aria-pressed', String(selected));
    });

    site.value = button.dataset.publicSite;
    update();
    publicMessage.textContent = `Sito selezionato: ${site.value}.`;
  });
});

// Analisi attraverso il motore NASA/JPL già presente.
publicAnalyzeButton.addEventListener('click', async () => {
  if (publicAnalyzeButton.disabled) return;

  if (!publicDate.value) {
    publicMessage.textContent = 'Seleziona data e ora di inizio UTC.';
    publicDate.focus();
    return;
  }

  dateInput.value = publicDate.value;
  document.querySelector('#duration').value = publicDuration.value;
  document.querySelector('#elevation').value = publicSunElevation.value;
  document.querySelector('#earthElevation').value = publicEarthElevation.value;

  update();

  publicAnalyzeButton.disabled = true;
  publicAnalyzeButton.textContent = 'ANALISI NASA/JPL IN CORSO…';

  try {
    await updateEphemerides();
  } finally {
    publicAnalyzeButton.disabled = false;
    publicAnalyzeButton.textContent = 'ANALIZZA QUESTO SITO';
  }
});

// Apertura e chiusura della spiegazione.
const educationToggle = document.querySelector('#educationToggle');
const educationText = document.querySelector('#educationText');

educationToggle.addEventListener('click', () => {
  const expanded = !educationText.hidden;
  educationText.hidden = expanded;
  educationToggle.setAttribute('aria-expanded', String(!expanded));
  educationToggle.textContent = expanded
    ? 'SCOPRI COME FUNZIONA'
    : 'NASCONDI SPIEGAZIONE';
});

window.addEventListener('resize', () => {
  // Ridisegna i grafici solo dopo aver ricevuto dati reali.
  if (window.lastEphemerides) {
    const d = window.lastEphemerides;
    drawEphemerisChart(chart1, d.observations, 'sun_elevation_deg',
      d.thresholds.sun_elevation_deg, '#EAD9A7', d.windows);
    drawEphemerisChart(chart2, d.observations, 'earth_elevation_deg',
      d.thresholds.earth_elevation_deg, '#5CCFE6', d.windows);
  }
});



// ===== COMMUNICATION INTELLIGENCE =====
window.lastEngineeringModels = {};

function numericInput(id) {
  const value = Number(document.getElementById(id).value);
  if (!Number.isFinite(value)) throw new Error(`Valore non valido: ${id}`);
  return value;
}

function displayNumber(id, value, suffix = '') {
  document.getElementById(id).textContent =
    Number.isFinite(value) ? `${value.toFixed(2)}${suffix}` : 'N/D';
}

async function postModel(endpoint, payload) {
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
    cache: 'no-store'
  });
  const data = await response.json();
  if (!response.ok || data.status !== 'ok') {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data.result;
}

document.querySelector('#calculateRF').addEventListener('click', async () => {
  const button = document.querySelector('#calculateRF');
  const status = document.querySelector('#rfStatus');
  button.disabled = true;
  status.textContent = 'Calcolo del budget radio…';

  try {
    const payload = {
      distance_km: numericInput('rfDistance'),
      frequency_ghz: numericInput('rfFrequency'),
      transmit_power_dbm: numericInput('rfPower'),
      transmit_antenna_gain_dbi: numericInput('rfTxGain'),
      receive_antenna_gain_dbi: numericInput('rfRxGain'),
      system_losses_db: numericInput('rfLosses'),
      receiver_sensitivity_dbm: numericInput('rfSensitivity'),
      required_margin_db: numericInput('rfMargin')
    };
    const result = await postModel('/api/communications/link-budget', payload);
    window.lastEngineeringModels.rf = {inputs: payload, result};

    displayNumber('rfPathLoss', result.free_space_path_loss_db, ' dB');
    displayNumber('rfReceived', result.received_power_dbm, ' dBm');
    displayNumber('rfLinkMargin', result.link_margin_db, ' dB');
    document.querySelector('#rfCheck').textContent =
      result.margin_check === true ? 'PASS' :
      result.margin_check === false ? 'FAIL' : 'N/D';
    status.textContent =
      'Stima preliminare in spazio libero. Visibilità del terreno, puntamento, interferenze e prestazioni hardware non sono verificate.';
  } catch (error) {
    status.textContent = `Calcolo RF non riuscito: ${error.message}`;
  } finally {
    button.disabled = false;
  }
});

// ===== THERMAL INTELLIGENCE =====
function drawThermalChart(samples) {
  const canvas = document.querySelector('#thermalChart');
  const ctx = canvas.getContext('2d');
  const width = Math.max(100, canvas.clientWidth);
  const height = Math.max(100, canvas.clientHeight);
  const dpr = Math.min(window.devicePixelRatio || 1, 2);

  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const points = (Array.isArray(samples) ? samples : []).map((sample, index) => {
    const time = Number(sample.time_s ?? sample.elapsed_s ?? sample.time ?? index);
    const temperature = Number(sample.temperature_k ?? sample.temperature_K ?? sample.temperature);
    return {time, temperature};
  }).filter(p => Number.isFinite(p.time) && Number.isFinite(p.temperature));

  if (points.length < 2) {
    ctx.fillStyle = '#9AA6B2';
    ctx.font = '12px Archivo, system-ui, sans-serif';
    ctx.fillText('Campioni termici non disponibili nel formato atteso.', 8, 22);
    return;
  }

  const minT = Math.min(...points.map(p => p.temperature));
  const maxT = Math.max(...points.map(p => p.temperature));
  const minX = points[0].time;
  const maxX = points[points.length - 1].time;
  const pad = {left:42, right:10, top:10, bottom:22};
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const rangeT = Math.max(1e-9, maxT - minT);
  const rangeX = Math.max(1e-9, maxX - minX);

  ctx.strokeStyle = '#323A44';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad.top + plotH * i / 4;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width-pad.right, y); ctx.stroke();
  }

  ctx.strokeStyle = '#E3B341';
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((p, i) => {
    const x = pad.left + (p.time - minX) / rangeX * plotW;
    const y = pad.top + (maxT - p.temperature) / rangeT * plotH;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();

  ctx.fillStyle = '#9AA6B2';
  ctx.font = '12px Archivo, system-ui, sans-serif';
  ctx.fillText(`${maxT.toFixed(1)} K`, 3, 13);
  ctx.fillText(`${minT.toFixed(1)} K`, 3, height - 25);
  ctx.fillText('TEMPO (s)', pad.left, height - 5);
}

document.querySelector('#calculateThermal').addEventListener('click', async () => {
  const button = document.querySelector('#calculateThermal');
  const status = document.querySelector('#thermalStatus');
  button.disabled = true;
  status.textContent = 'Simulazione termica RK4 in corso…';

  try {
    const payload = {
      duration_s: numericInput('thDuration'),
      step_s: numericInput('thStep'),
      initial_temperature_k: numericInput('thInitial'),
      thermal_capacity_j_k: numericInput('thCapacity'),
      solar_flux_w_m2: numericInput('thFlux'),
      projected_area_m2: numericInput('thArea'),
      absorptivity: numericInput('thAbsorptivity'),
      emissivity: numericInput('thEmissivity'),
      radiator_area_m2: numericInput('thRadiator'),
      internal_power_w: numericInput('thPower'),
      environment_temperature_k: numericInput('thEnvironment'),
      illumination_fraction: numericInput('thIllumination'),
      conductive_coupling_w_k: numericInput('thCoupling'),
      sink_temperature_k: numericInput('thSink')
    };
    const result = await postModel('/api/thermal/simulate', payload);
    window.lastEngineeringModels.thermal = {inputs: payload, result};

    displayNumber('thFinal', result.final_temperature_k, ' K');
    displayNumber('thMin', result.min_temperature_k, ' K');
    displayNumber('thMax', result.max_temperature_k, ' K');
    document.querySelector('#thSamples').textContent =
      Array.isArray(result.samples) ? String(result.samples.length) : 'N/D';
    drawThermalChart(result.samples);

    status.textContent =
      'Simulazione preliminare a nodo singolo. Proprietà costanti e condizioni ambientali semplificate; non è una qualifica termica del veicolo.';
  } catch (error) {
    status.textContent = `Simulazione termica non riuscita: ${error.message}`;
  } finally {
    button.disabled = false;
  }
});


// Esporta il piano e le effemeridi realmente ricevute da JPL Horizons.
document.querySelector('#exportMission').addEventListener('click', () => {
  const data = window.lastEphemerides;
  if (!data || !Array.isArray(data.observations) || data.observations.length < 2) {
    message.textContent = 'Prima aggiorna la visualizzazione e attendi i dati NASA/JPL.';
    return;
  }

  const plan = {
    schema_version: 1,
    generated_at_utc: new Date().toISOString(),
    mission: {
      site: data.site,
      start_date_utc: data.start_utc,
      duration_hours: data.duration_hours,
      science_priority: data.science_priority,
      engineering_priority: data.engineering_priority,
      min_sun_elevation_deg: data.thresholds.sun_elevation_deg,
      min_earth_elevation_deg: data.thresholds.earth_elevation_deg
    },
    astronomy: {
      status: data.source,
      observations: data.observations,
      operational_windows: data.windows || [],
      window_count: (data.windows || []).length,
      step: data.step,
      window_constraints: data.thresholds,
      analytics: data.analytics || null
    },
    engineering_models: window.lastEngineeringModels || {},
    validation: {
      terrain_occlusion: 'not_verified',
      radio_line_of_sight: 'not_verified',
      landing_safety: 'not_verified',
      flight_qualification: 'not_qualified'
    },
    notice: data.notice || 'Piano preliminare: non certificato per uso operativo.'
  };

  const blob = new Blob([JSON.stringify(plan, null, 2) + '\n'], {
    type: 'application/json;charset=utf-8'
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  const safeSite = data.site.toLowerCase().replace(/[^a-z0-9]+/g, '_');
  link.href = url;
  link.download = `mission_${safeSite}_${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  message.textContent = 'Piano JSON esportato con effemeridi e finestre calcolate.';
});


// LROC quality report: visualizzazione diagnostica del report JSON.
async function loadLrocQuality() {
  const status = document.getElementById('lrocQualityStatus');
  const setText = (id, value) => {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
  };
  const number = value => Number(value || 0).toLocaleString('it-IT');
  const area = value => `${Number(value || 0).toFixed(6)} km²`;

  try {
    const response = await fetch('/api/terrain/lroc-quality', {
      headers: { 'Accept': 'application/json' },
      cache: 'no-store'
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();

    const counts = data.pixel_counts || {};
    const areas = data.area_km2 || {};
    const total = Number(data.valid_dtm_pixels || 0);
    const classes = [
      ['PRIMARY', 'lrocPrimary', 'lrocPrimaryArea', 'lrocBarPrimary'],
      ['INTERPOLATED', 'lrocInterpolated', 'lrocInterpolatedArea', 'lrocBarInterpolated'],
      ['UNRESOLVED', 'lrocUnresolved', 'lrocUnresolvedArea', 'lrocBarUnresolved'],
      ['INVALID', 'lrocInvalid', 'lrocInvalidArea', 'lrocBarInvalid']
    ];

    for (const [key, countId, areaId, barId] of classes) {
      const count = Number(counts[key] || 0);
      setText(countId, number(count));
      setText(areaId, area(areas[key]));
      const bar = document.getElementById(barId);
      if (bar) bar.style.width = `${Number(data.total_pixels) > 0
        ? count / Number(data.total_pixels) * 100 : 0}%`;
    }

    setText('lrocCoverage',
      `Pixel DTM validi: ${number(total)} / ${number(data.total_pixels)} · ` +
      `Codici CONF non risolti: ${(data.unresolved_confidence_codes_on_valid_dtm || []).join(', ') || 'nessuno'}`);

    const warningList = document.getElementById('lrocWarnings');
    if (warningList) {
      warningList.replaceChildren();
      for (const warning of (data.warnings || [])) {
        const item = document.createElement('li');
        item.textContent = warning;
        warningList.appendChild(item);
      }
    }

    if (status) status.textContent = 'REPORT LOADED';
  } catch (error) {
    if (status) status.textContent = 'REPORT UNAVAILABLE';
    setText('lrocCoverage', `Impossibile caricare il report LROC: ${error.message}`);
    const warningList = document.getElementById('lrocWarnings');
    if (warningList) {
      warningList.replaceChildren();
      const item = document.createElement('li');
      item.textContent = 'Verificare che il report JSON sia presente e che il server web sia attivo.';
      warningList.appendChild(item);
    }
  }
}

// Report LROC: pannello dei Pianificatori di missione (API riservata, solo /mission-control).
if (!window.lmcSession || window.lmcSession.reservedPage) loadLrocQuality();
