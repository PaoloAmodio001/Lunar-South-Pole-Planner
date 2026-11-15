/* Sezione Educatori (pubblica, nessun login).
 * - Navigazione per capitoli e livelli di approfondimento (preferenze in localStorage, sempre in try/catch).
 * - Laboratori: riusano le API pubbliche esistenti /api/sites e /api/ephemerides (NASA/JPL Horizons)
 *   e l'Esploratore pubblico (#publicMissionPanel di main.js). Nessun calcolo astronomico duplicato:
 *   qui si leggono soltanto i campi "analytics" e "observations" prodotti dal server.
 * - Non usa API protette (/api/mission/, /api/science/, ...) e non tocca autenticazione o sessioni. */
(() => {
  'use strict';

  const root = document.getElementById('educatorHome');
  if (!root) return;

  const $ = (sel, ctx = root) => ctx.querySelector(sel);
  const $$ = (sel, ctx = root) => Array.from(ctx.querySelectorAll(sel));
  const store = {
    get(key) { try { return localStorage.getItem(key); } catch (_) { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch (_) { /* opzionale */ } },
  };
  const SVG_NS = 'http://www.w3.org/2000/svg';
  function svgEl(name, attrs = {}, text) {
    const el = document.createElementNS(SVG_NS, name);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
    if (text !== undefined) el.textContent = text;
    return el;
  }
  function el(name, attrs = {}, text) {
    const node = document.createElement(name);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'className') node.className = v; else node.setAttribute(k, String(v));
    }
    if (text !== undefined) node.textContent = text;
    return node;
  }
  const fmtPct = value => (Number.isFinite(value) ? `${value.toLocaleString('it-IT', { maximumFractionDigits: 1 })}%` : '—');

  /* ---------------- Capitoli ---------------- */
  const chapters = $$('.edu-chapter');
  const order = chapters.map(c => c.dataset.chapter);
  const navButtons = $$('.edu-nav [data-edu-go]');
  const prev = $('#eduPrev');
  const next = $('#eduNext');
  let current = order[0];

  function showChapter(id, { scroll = true } = {}) {
    if (!order.includes(id)) id = order[0];
    current = id;
    chapters.forEach(c => { c.hidden = c.dataset.chapter !== id; });
    navButtons.forEach(b => {
      if (b.dataset.eduGo === id) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current');
    });
    const i = order.indexOf(id);
    prev.hidden = i === 0;
    next.hidden = i === order.length - 1;
    store.set('lspp.edu.chapter', id);
    if (id === 'why-south-pole') loadSites();
    if (id === 'labs') loadSites();
    if (scroll) {
      const target = chapters[i];
      // Su desktop scorre #educatorHome, su schermi stretti la pagina: scrollIntoView copre entrambi.
      target.scrollIntoView({ block: 'start', behavior: 'smooth' });
      const heading = target.querySelector('h2');
      if (heading) { heading.setAttribute('tabindex', '-1'); heading.focus({ preventScroll: true }); }
    }
  }
  $$('[data-edu-go]').forEach(b => b.addEventListener('click', () => {
    if (b.dataset.eduSetLevel) setLevel(b.dataset.eduSetLevel);
    showChapter(b.dataset.eduGo);
  }));
  prev.addEventListener('click', () => showChapter(order[Math.max(0, order.indexOf(current) - 1)]));
  next.addEventListener('click', () => showChapter(order[Math.min(order.length - 1, order.indexOf(current) + 1)]));

  /* ---------------- Livelli ---------------- */
  const levelButtons = $$('[data-edu-level]');
  function setLevel(level) {
    if (!['1', '2', '3'].includes(String(level))) level = '1';
    root.dataset.level = String(level);
    levelButtons.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.eduLevel === String(level))));
    store.set('lspp.edu.level', String(level));
  }
  levelButtons.forEach(b => b.addEventListener('click', () => setLevel(b.dataset.eduLevel)));

  /* ---------------- Strumento: lunghezza dell'ombra ---------------- */
  const shadowH = $('#eduShadowHeight');
  const shadowE = $('#eduShadowElev');
  function updateShadow() {
    const h = Number(shadowH.value);
    const e = Number(shadowE.value);
    $('#eduShadowElevOut').textContent = e.toLocaleString('it-IT');
    const out = $('#eduShadowResult');
    if (!(h > 0) || !(e > 0)) { out.textContent = '—'; return; }
    const len = h / Math.tan(e * Math.PI / 180);
    out.textContent = `${len.toLocaleString('it-IT', { maximumFractionDigits: len < 10 ? 2 : 0 })} m (${(len / h).toLocaleString('it-IT', { maximumFractionDigits: 1 })} volte l'altezza)`;
    // Schema: oggetto di altezza fissa, ombra in scala con limite visivo.
    const baseX = 26, groundY = 100, objH = 30;
    const shadePx = Math.min(270, objH / Math.tan(e * Math.PI / 180));
    $('#eduShadowShade').setAttribute('d', `M${baseX} ${groundY}H${baseX + shadePx}`);
    $('#eduShadowRay').setAttribute('d', `M20 ${groundY - objH} L${baseX + shadePx} ${groundY}`);
  }
  shadowH.addEventListener('input', updateShadow);
  shadowE.addEventListener('input', updateShadow);
  updateShadow();

  /* ---------------- Siti (API pubblica /api/sites) ---------------- */
  let sites = null;
  let sitesPromise = null;
  function loadSites() {
    if (sitesPromise) return sitesPromise;
    sitesPromise = fetch('/api/sites', { headers: { Accept: 'application/json' } })
      .then(r => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(data => {
        sites = (data.sites || []).filter(s => Number.isFinite(s.latitude_deg) && Number.isFinite(s.longitude_east_deg));
        drawPolarMap();
        buildMatrix();
        buildWorksheet();
        return sites;
      })
      .catch(err => {
        sitesPromise = null; // si riprova alla prossima apertura del capitolo
        const map = $('#eduPolarMap');
        map.replaceChildren(svgEl('text', { x: 160, y: 164, 'text-anchor': 'middle', 'font-size': 11, fill: '#F0605D' },
          'Siti non disponibili: server non raggiungibile.'));
        $('#eduMatrixBody').replaceChildren(rowMessage(6, `Elenco dei siti non disponibile (${err.message}).`));
        return null;
      });
    return sitesPromise;
  }
  function rowMessage(cols, text) {
    const tr = el('tr'); const td = el('td', { colspan: cols }, text); tr.append(td); return tr;
  }

  // Proiezione polare sud: 0° di longitudine in alto (faccia verso la Terra), 90° E a destra.
  function drawPolarMap() {
    const map = $('#eduPolarMap');
    // Scala radiale a radice quadrata: separa i siti vicinissimi al polo (dichiarato nella didascalia).
    const cx = 160, cy = 160, maxColat = 5.5, R = 135;
    const radius = colat => R * Math.sqrt(Math.min(Math.max(colat, 0), maxColat) / maxColat);
    const nodes = [svgEl('rect', { width: 320, height: 320, fill: '#0A1322' })];
    for (const ring of [1, 3, 5]) {
      const r = radius(ring);
      nodes.push(svgEl('circle', { cx, cy, r: r.toFixed(1), fill: 'none', stroke: '#323A44', 'stroke-dasharray': ring === 5 ? '0' : '3 4' }));
      nodes.push(svgEl('text', { x: (cx + r * 0.707 + 3).toFixed(1), y: (cy + r * 0.707 + 3).toFixed(1), 'font-size': 9, fill: '#7D8995' }, `${90 - ring}° S`));
    }
    nodes.push(svgEl('path', { d: `M${cx} ${cy - R}V${cy + R}M${cx - R} ${cy}H${cx + R}`, stroke: '#22272E' }));
    nodes.push(svgEl('text', { x: cx, y: 14, 'text-anchor': 'middle', 'font-size': 10, fill: '#5CCFE6' }, '0° · verso la Terra'));
    nodes.push(svgEl('text', { x: cx, y: 314, 'text-anchor': 'middle', 'font-size': 10, fill: '#7D8995' }, '180°'));
    nodes.push(svgEl('text', { x: 314, y: cy + 3, 'text-anchor': 'end', 'font-size': 10, fill: '#7D8995' }, '90° E'));
    nodes.push(svgEl('text', { x: 6, y: cy + 3, 'font-size': 10, fill: '#7D8995' }, '90° O'));
    nodes.push(svgEl('circle', { cx, cy, r: 2.5, fill: '#E7ECF1' }));
    nodes.push(svgEl('text', { x: cx + 5, y: cy + 14, 'font-size': 9, fill: '#9AA6B2' }, 'polo sud'));
    (sites || []).forEach((s, i) => {
      const colat = 90 + s.latitude_deg;
      const lon = s.longitude_east_deg * Math.PI / 180;
      const r = radius(colat);
      const x = cx + r * Math.sin(lon);
      const y = cy - r * Math.cos(lon);
      const right = x < cx + 40;
      nodes.push(svgEl('circle', { cx: x.toFixed(1), cy: y.toFixed(1), r: 5, fill: '#5CCFE6', stroke: '#0A1322', 'stroke-width': 2 }));
      const label = svgEl('text', { x: (x + (right ? 9 : -9)).toFixed(1), y: (y + 4 + (i % 2 ? 10 : 0)).toFixed(1), 'font-size': 11, fill: '#E7ECF1', 'text-anchor': right ? 'start' : 'end' });
      label.textContent = `${s.name} (${Math.abs(s.latitude_deg).toLocaleString('it-IT', { maximumFractionDigits: 2 })}° S)`;
      nodes.push(label);
    });
    map.replaceChildren(...nodes);
  }

  /* ---------------- Banco di prova (API pubblica /api/ephemerides) ---------------- */
  const form = $('#eduCompareForm');
  const startInput = $('#eduStart');
  const statusEl = $('#eduCompareStatus');
  const runBtn = $('#eduCompareRun');
  const results = new Map(); // nome sito -> analytics
  let lastSite = null;
  {
    const now = new Date();
    now.setUTCMinutes(0, 0, 0);
    startInput.value = now.toISOString().slice(0, 16);
  }
  function setStatus(text, state) {
    statusEl.textContent = text;
    if (state) statusEl.dataset.state = state; else delete statusEl.dataset.state;
  }
  function params() {
    return {
      start: startInput.value,
      hours: $('#eduHours').value,
      min_sun: $('#eduMinSun').value,
      min_earth: $('#eduMinEarth').value,
    };
  }

  function sparkline(observations, thresholds) {
    const w = 160, h = 40, pad = 3;
    const svg = svgEl('svg', { viewBox: `0 0 ${w} ${h}`, class: 'edu-spark', role: 'img', 'aria-label': 'Elevazione di Sole e Terra nel periodo' });
    const sun = observations.map(o => o.sun_elevation_deg);
    const earth = observations.map(o => o.earth_elevation_deg);
    const all = sun.concat(earth, [thresholds.sun_elevation_deg, thresholds.earth_elevation_deg]).filter(Number.isFinite);
    if (all.length < 2) return svg;
    let lo = Math.min(...all), hi = Math.max(...all);
    if (hi - lo < 1) { hi += .5; lo -= .5; }
    const n = observations.length;
    const X = i => pad + (w - 2 * pad) * (n > 1 ? i / (n - 1) : 0);
    const Y = v => h - pad - (h - 2 * pad) * (v - lo) / (hi - lo);
    const line = (vals, color) => {
      const d = vals.map((v, i) => (Number.isFinite(v) ? `${i ? 'L' : 'M'}${X(i).toFixed(1)} ${Y(v).toFixed(1)}` : '')).join('');
      return svgEl('path', { d, fill: 'none', stroke: color, 'stroke-width': 1.4 });
    };
    if (lo < 0 && hi > 0) svg.append(svgEl('path', { d: `M0 ${Y(0).toFixed(1)}H${w}`, stroke: '#323A44' }));
    svg.append(svgEl('path', { d: `M0 ${Y(thresholds.sun_elevation_deg).toFixed(1)}H${w}`, stroke: '#EAD9A7', 'stroke-dasharray': '2 3', opacity: .6 }));
    svg.append(svgEl('path', { d: `M0 ${Y(thresholds.earth_elevation_deg).toFixed(1)}H${w}`, stroke: '#5CCFE6', 'stroke-dasharray': '2 3', opacity: .6 }));
    svg.append(line(sun, '#EAD9A7'), line(earth, '#5CCFE6'));
    return svg;
  }

  function resultRow(name, data) {
    const a = data.analytics || {};
    const tr = el('tr');
    tr.append(el('th', { scope: 'row' }, name));
    tr.append(el('td', { className: 'edu-num' }, fmtPct(a.sun && a.sun.passing_percent)));
    tr.append(el('td', { className: 'edu-num' }, fmtPct(a.earth && a.earth.passing_percent)));
    tr.append(el('td', { className: 'edu-num' }, fmtPct(a.simultaneous && a.simultaneous.passing_percent)));
    const ow = a.operational_windows || {};
    tr.append(el('td', { className: 'edu-num' }, Number.isFinite(ow.count)
      ? `${ow.count} · ${Math.round(ow.total_sampled_span_hours || 0)} h` : '—'));
    const spark = el('td');
    spark.append(sparkline(data.observations || [], data.thresholds || {}));
    tr.append(spark);
    const act = el('td');
    const btn = el('button', { type: 'button', className: 'edu-secondary' }, 'Apri nel 3D');
    btn.addEventListener('click', () => openExplorer(name, { run: true }));
    act.append(btn);
    tr.append(act);
    return tr;
  }

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const list = sites || await loadSites();
    if (!list || !list.length) { setStatus('Nessun sito disponibile: verifica che il server sia attivo.', 'error'); return; }
    const p = params();
    const body = $('#eduCompareBody');
    body.replaceChildren();
    $('#eduCompareTable').hidden = false;
    runBtn.disabled = true;
    results.clear();
    let failures = 0;
    for (const [i, s] of list.entries()) {
      setStatus(`Calcolo con NASA/JPL Horizons: ${s.name} (${i + 1} di ${list.length})…`, 'busy');
      const query = new URLSearchParams({ site: s.name, ...p });
      try {
        const res = await fetch(`/api/ephemerides?${query}`, { headers: { Accept: 'application/json' } });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || data.status !== 'ok') throw new Error(data.error || `HTTP ${res.status}`);
        results.set(s.name, data.analytics || {});
        body.append(resultRow(s.name, data));
      } catch (err) {
        failures += 1;
        const tr = el('tr');
        tr.append(el('th', { scope: 'row' }, s.name));
        tr.append(el('td', { colspan: 6 }, `Calcolo non riuscito: ${err.message}`));
        body.append(tr);
      }
    }
    runBtn.disabled = false;
    lastSite = list[0].name;
    fillMatrixFromResults();
    if (failures === list.length) setStatus('Nessun risultato: JPL Horizons non è raggiungibile o i parametri non sono validi. Riprova più tardi.', 'error');
    else if (failures) setStatus(`Confronto completato con ${failures} errori. I risultati disponibili sono nella tabella.`, 'error');
    else setStatus('Confronto completato. Percentuali = ore campionate con l\'astro sopra la soglia indicata.', 'ok');
  });

  /* ---------------- Ponte verso l'Esploratore pubblico (main.js) ---------------- */
  function openExplorer(siteName, { run = false } = {}) {
    const p = params();
    const set = (id, v) => { const input = document.getElementById(id); if (input && v !== '' && v != null) input.value = v; };
    set('publicDate', p.start);
    set('publicDuration', p.hours);
    set('publicSunElevation', p.min_sun);
    set('publicEarthElevation', p.min_earth);
    const siteBtn = siteName && Array.from(document.querySelectorAll('.public-site'))
      .find(b => b.dataset.publicSite === siteName);
    if (siteBtn) siteBtn.click();
    // Riusa il selettore di profilo della homepage (stesso comportamento del pulsante «Pubblico»).
    const publicCard = document.querySelector('#profileHome [data-profile="public"]');
    if (publicCard) publicCard.click();
    if (run) {
      const analyze = document.getElementById('publicAnalyze');
      if (analyze) requestAnimationFrame(() => analyze.click());
    }
  }
  $$('[data-edu-explore]').forEach(b => b.addEventListener('click', () => {
    openExplorer(lastSite || (sites && sites[0] && sites[0].name) || null, { run: true });
  }));
  $$('[data-edu-scroll]').forEach(b => b.addEventListener('click', () => {
    const target = document.getElementById(b.dataset.eduScroll);
    if (target) target.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }));

  /* ---------------- Matrice decisionale (Laboratorio 4) ---------------- */
  const CRITERIA = [
    { key: 'energy', label: 'Energia' },
    { key: 'comms', label: 'Comunicazioni' },
    { key: 'safety', label: 'Sicurezza' },
    { key: 'science', label: 'Scienza' },
  ];
  function buildMatrix() {
    const body = $('#eduMatrixBody');
    if (!sites || !sites.length) { body.replaceChildren(rowMessage(6, 'Nessun sito disponibile.')); return; }
    body.replaceChildren(...sites.map(s => {
      const tr = el('tr', { 'data-site': s.name });
      tr.append(el('th', { scope: 'row' }, s.name));
      for (const c of CRITERIA) {
        const td = el('td');
        const input = el('input', { type: 'number', min: 1, max: 5, step: 0.1, value: 3, 'data-crit': c.key, 'aria-label': `${c.label} · ${s.name} (1–5)` });
        input.addEventListener('input', () => { input.classList.remove('edu-auto'); scoreMatrix(); });
        td.append(input);
        tr.append(td);
      }
      tr.append(el('td', { className: 'edu-num edu-score' }, '—'));
      return tr;
    }));
    fillMatrixFromResults();
  }
  function fillMatrixFromResults() {
    for (const [name, a] of results) {
      const tr = $$('#eduMatrixBody tr').find(r => r.dataset.site === name);
      if (!tr) continue;
      const fill = (crit, pct) => {
        if (!Number.isFinite(pct)) return;
        const input = tr.querySelector(`[data-crit="${crit}"]`);
        input.value = (1 + 4 * pct / 100).toFixed(1); // 0% → 1, 100% → 5
        input.classList.add('edu-auto');
        input.title = `Calcolato dal banco di prova: ${fmtPct(pct)} delle ore sopra soglia`;
      };
      fill('energy', a.sun && a.sun.passing_percent);
      fill('comms', a.earth && a.earth.passing_percent);
    }
    scoreMatrix();
  }
  function weights() {
    const w = {};
    $$('[data-weight]').forEach(r => {
      w[r.dataset.weight] = Number(r.value);
      const out = $(`[data-out="w-${r.dataset.weight}"]`);
      if (out) out.textContent = r.value;
    });
    return w;
  }
  function scoreMatrix() {
    const w = weights();
    const total = Object.values(w).reduce((a, b) => a + b, 0);
    let best = null;
    $$('#eduMatrixBody tr[data-site]').forEach(tr => {
      tr.classList.remove('edu-best');
      let sum = 0;
      for (const c of CRITERIA) {
        const v = Math.min(5, Math.max(1, Number(tr.querySelector(`[data-crit="${c.key}"]`).value) || 1));
        sum += w[c.key] * v;
      }
      const score = total > 0 ? sum / total : NaN;
      tr.querySelector('.edu-score').textContent = Number.isFinite(score) ? score.toFixed(2) : '—';
      if (Number.isFinite(score) && (!best || score > best.score)) best = { tr, score };
    });
    if (best) best.tr.classList.add('edu-best');
  }
  $$('[data-weight]').forEach(r => r.addEventListener('input', scoreMatrix));

  /* ---------------- Scheda di lavoro (Laboratorio 5) ---------------- */
  function buildWorksheet() {
    const body = $('#eduWorksheetBody');
    if (!sites) return;
    body.replaceChildren(...sites.map(s => {
      const tr = el('tr');
      tr.append(el('th', { scope: 'row' }, s.name));
      for (let i = 0; i < 4; i += 1) tr.append(el('td'));
      return tr;
    }));
  }

  /* ---------------- Stampa ---------------- */
  let reopen = [];
  window.addEventListener('beforeprint', () => {
    if (!document.body.classList.contains('educator-mode')) return;
    reopen = $$('details.edu-activity:not([open])');
    reopen.forEach(d => { d.open = true; });
  });
  window.addEventListener('afterprint', () => { reopen.forEach(d => { d.open = false; }); reopen = []; });
  $$('[data-edu-print]').forEach(b => b.addEventListener('click', () => window.print()));

  /* ---------------- Avvio ---------------- */
  setLevel(store.get('lspp.edu.level') || '1');
  showChapter(store.get('lspp.edu.chapter') || order[0], { scroll: false });
})();
