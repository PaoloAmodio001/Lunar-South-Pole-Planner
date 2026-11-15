// F4 — Strumenti scientifici: interfaccia sottile sugli endpoint /api/science/*.
// Mostra solo l'output reale dei moduli originali, con provenienza e avvertenze.
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const root = $('scienceSection');
  if (!root) return;
  // Strumento dei Pianificatori di missione: attivo solo in /mission-control (sessione
  // verificata dal server); sulla piattaforma pubblica non interroga API riservate.
  if (window.lmcSession && !window.lmcSession.reservedPage) return;

  const rasterSelect = $('sciRaster');
  const stateTag = $('sciState');
  const out = $('sciResult');
  const buttons = root.querySelectorAll('[data-sci-tool]');
  const panes = root.querySelectorAll('[data-sci-pane]');
  let tool = 'dem-audit';
  let busy = false;

  const el = (tag, text, cls) => {
    const n = document.createElement(tag);
    if (text !== undefined && text !== null) n.textContent = String(text);
    if (cls) n.className = cls;
    return n;
  };
  const num = id => {
    const v = $(id).value.trim();
    if (v === '') return undefined;
    const n = Number(v);
    if (!Number.isFinite(n)) throw new Error(`Valore non numerico: ${id}`);
    return n;
  };
  const int = id => {
    const n = num(id);
    if (n === undefined || !Number.isInteger(n)) throw new Error(`Serve un intero: ${id}`);
    return n;
  };
  const fmt = v => (typeof v === 'number') ? (Number.isInteger(v) ? String(v) : v.toFixed(4))
    : (v === null || v === undefined ? '—' : (typeof v === 'boolean' ? (v ? 'sì' : 'no') : String(v)));

  function selectTool(name) {
    tool = name;
    buttons.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.sciTool === name)));
    panes.forEach(p => { p.hidden = p.dataset.sciPane !== name; });
    $('sciRasterRow').hidden = name === 'site-comparison';
  }
  buttons.forEach(b => b.addEventListener('click', () => selectTool(b.dataset.sciTool)));

  async function loadRasters() {
    try {
      const r = await fetch('/api/science/rasters', { cache: 'no-store' });
      const data = await r.json();
      rasterSelect.replaceChildren();
      for (const item of data.rasters || []) {
        const o = el('option', `${item.label}${item.available ? ` · ${item.rows}×${item.cols}` : ' — NON PRESENTE'}`);
        o.value = item.id; o.disabled = !item.available;
        rasterSelect.appendChild(o);
      }
    } catch (e) {
      stateTag.textContent = 'CATALOGO NON DISPONIBILE';
    }
  }

  function payload() {
    const raster_id = rasterSelect.value;
    switch (tool) {
      case 'dem-audit': return { raster_id };
      case 'terrain': return { raster_id, row: int('sciTRow'), col: int('sciTCol'), radius_pixels: int('sciTRadius') };
      case 'horizon': return { raster_id, row: int('sciHRow'), col: int('sciHCol'),
        observer_height_m: num('sciHHeight'), azimuth_step_deg: num('sciHStep'), max_distance_m: num('sciHDist') };
      case 'rover-plan': {
        const p = { raster_id, start_rc: [int('sciRSr'), int('sciRSc')], goal_rc: [int('sciRGr'), int('sciRGc')],
          max_slope_deg: num('sciRSlope'), energy_wh_per_m: num('sciREpm') };
        const budget = num('sciRBudget');
        if (budget !== undefined) p.energy_budget_wh = budget;
        if ($('sciREnergy').checked) {
          p.energy = {};
          for (const [key, id] of [['mass_kg', 'sciEMass'], ['rolling_resistance_coefficient', 'sciECrr'],
            ['drivetrain_efficiency', 'sciEEff'], ['auxiliary_power_w', 'sciEAux'],
            ['mission_duration_hours', 'sciEHours'], ['battery_capacity_wh', 'sciEBatt'],
            ['reserve_percent', 'sciEReserve']]) {
            const v = num(id);
            if (v !== undefined) p.energy[key] = v;   // i campi vuoti restano mancanti: il server li segnala
          }
        }
        return p;
      }
      case 'site-comparison': {
        const d = $('sciCDate').value;
        if (!d) throw new Error('Seleziona la data di inizio.');
        return { start_utc: `${d}T00:00:00+00:00`, hours: int('sciCHours') };
      }
    }
    throw new Error('Strumento sconosciuto.');
  }

  function table(rows) {
    const wrap = el('div', null, 'windows-table-wrap mission-table-wrap');
    const t = el('table', null, 'windows-table');
    const tb = el('tbody');
    for (const [k, v] of rows) {
      const tr = el('tr'); tr.append(el('td', k), el('td', fmt(v))); tb.appendChild(tr);
    }
    t.appendChild(tb); wrap.appendChild(t); return wrap;
  }
  const scalars = obj => Object.entries(obj || {}).filter(([, v]) => v === null || typeof v !== 'object');
  const list = items => { const ul = el('ul', null, 'mission-list'); for (const i of items) ul.appendChild(el('li', i)); return ul; };

  function plot(points, xLabel, yLabel, opts = {}) {
    const canvas = el('canvas', null, 'thermal-chart');
    canvas.width = 640; canvas.height = 220;
    requestAnimationFrame(() => {
      const ctx = canvas.getContext('2d');
      const W = canvas.width, H = canvas.height, P = 34;
      const xs = points.map(p => p[0]), ys = points.map(p => p[1]).filter(Number.isFinite);
      if (!ys.length) return;
      let [x0, x1] = [Math.min(...xs), Math.max(...xs)], [y0, y1] = [Math.min(...ys), Math.max(...ys)];
      if (x1 === x0) x1 = x0 + 1; if (y1 === y0) y1 = y0 + 1;
      const X = x => P + (x - x0) / (x1 - x0) * (W - 2 * P);
      const Y = y => opts.invertY ? P + (y - y0) / (y1 - y0) * (H - 2 * P) : H - P - (y - y0) / (y1 - y0) * (H - 2 * P);
      ctx.strokeStyle = '#263b50'; ctx.strokeRect(P, P, W - 2 * P, H - 2 * P);
      ctx.fillStyle = '#8295a9'; ctx.font = '10px sans-serif';
      ctx.fillText(`${yLabel}  [${y0.toFixed(2)} … ${y1.toFixed(2)}]`, P, P - 8);
      ctx.fillText(`${xLabel}  [${x0.toFixed(1)} … ${x1.toFixed(1)}]`, P, H - 8);
      ctx.strokeStyle = '#5be7f5'; ctx.lineWidth = 1.5; ctx.beginPath();
      let started = false;
      for (const [x, y] of points) {
        if (!Number.isFinite(y)) { started = false; continue; }   // nessuna interpolazione sui dati mancanti
        if (!started) { ctx.moveTo(X(x), Y(y)); started = true; } else ctx.lineTo(X(x), Y(y));
      }
      ctx.stroke();
    });
    return canvas;
  }

  function render(data) {
    out.replaceChildren();
    const prov = data.provenance || {};
    out.appendChild(el('div',
      `Fonte: ${prov.module}.${prov.function}${prov.raster ? ` · raster ${prov.raster}` : ''} · ${prov.computed_utc} · ${prov.result_type}`,
      'window-notice'));
    if ((data.notes || []).length) out.appendChild(list(data.notes));
    const res = data.result || {};

    if (tool === 'horizon') {
      const samples = res.samples || [];
      out.appendChild(el('div', 'PROFILO D\'ORIZZONTE (elevazione dell\'orizzonte per azimut di griglia)', 'label'));
      out.appendChild(plot(samples.map(s => [s.grid_azimuth_deg, s.horizon_elevation_deg]), 'azimut griglia °', 'elevazione orizzonte °'));
      const valid = samples.map(s => s.horizon_elevation_deg).filter(Number.isFinite);
      out.appendChild(table([
        ...scalars(res.observer), ...scalars(res.sampling),
        ['campioni azimutali', samples.length],
        ['orizzonte max °', valid.length ? Math.max(...valid) : null],
        ['orizzonte medio °', valid.length ? valid.reduce((a, b) => a + b, 0) / valid.length : null],
        ['georeference_validated', res.georeference_validated],
      ]));
      out.appendChild(list(res.warnings || []));
    } else if (tool === 'rover-plan') {
      const plan = res.plan || {};
      out.appendChild(el('div', 'PERCORSO ROVER (riga/colonna DEM)', 'label'));
      const path = plan.path_rc || [];
      if (path.length) out.appendChild(plot(path.map(([r, c]) => [c, r]), 'colonna', 'riga', { invertY: true }));
      out.appendChild(table([...scalars(plan), ['celle nel percorso', path.length]]));
      if (plan.warning) out.appendChild(list([plan.warning]));
      const en = res.energy_assessment;
      out.appendChild(el('div', 'STIMA ENERGETICA (rover_energy)', 'label'));
      if (!en) {
        out.appendChild(el('div', 'Non calcolata: abilitare la stima e fornire i parametri reali del rover.', 'window-notice'));
      } else {
        out.appendChild(table([...scalars(en), ...Object.entries(en.energy_wh || {})]));
        out.appendChild(list([...(en.assumptions || []), ...(en.warnings || [])]));
      }
    } else if (tool === 'site-comparison') {
      out.appendChild(el('div', res.interpretation || '', 'window-notice'));
      for (const site of res.sites || []) {
        out.appendChild(el('div', site.site, 'label'));
        out.appendChild(table(scalars(site)));
      }
    } else {
      out.appendChild(table(scalars(res)));
      const warnings = res.warnings || (res.warning ? [res.warning] : []);
      if (warnings.length) out.appendChild(list(warnings));
    }
    const details = el('details', null, 'mission-details');
    details.appendChild(el('summary', 'Output completo del modulo (JSON)'));
    details.appendChild(el('pre', JSON.stringify(res, null, 2), 'mission-pre'));
    out.appendChild(details);
  }

  $('sciRun').addEventListener('click', async () => {
    if (busy) return;
    let body;
    try { body = payload(); } catch (e) { stateTag.textContent = 'INPUT NON VALIDO'; out.replaceChildren(el('div', e.message, 'engineering-result mission-error')); return; }
    busy = true; $('sciRun').disabled = true;
    stateTag.textContent = 'CALCOLO IN CORSO';
    out.replaceChildren(el('div', 'Calcolo in corso nel modulo scientifico originale…', 'engineering-result'));
    try {
      const r = await fetch(`/api/science/${tool}`, { method: 'POST', cache: 'no-store',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
      stateTag.textContent = 'RISULTATO REALE';
      render(data);
    } catch (e) {
      stateTag.textContent = 'NON DISPONIBILE';
      out.replaceChildren(el('div', e.message, 'engineering-result mission-error'));
    } finally {
      busy = false; $('sciRun').disabled = false;
    }
  });

  $('sciCDate').value = new Date().toISOString().slice(0, 10);
  selectTool('dem-audit');
  loadRasters();
})();
