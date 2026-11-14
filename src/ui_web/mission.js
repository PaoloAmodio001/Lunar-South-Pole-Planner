// F1 — Integrazione Web UI → Mission Orchestrator.
// Mostra solo ciò che il motore ha realmente prodotto (mission_report.json).
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const root = $('missionEngineSection');
  if (!root) return;

  const select = $('missionConfigSelect');
  const fileInput = $('missionConfigFile');
  const validateBtn = $('missionValidate');
  const runBtn = $('missionRun');
  const stateTag = $('missionState');
  const statusText = $('missionStatusText');
  const validationList = $('missionValidation');
  const results = $('missionResults');

  let uploaded = null;        // {config, filename}
  let pollTimer = null;
  let currentRun = null;

  const el = (tag, text, cls) => {
    const node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = String(text);
    if (cls) node.className = cls;
    return node;
  };
  const fmt = (v, digits = 2) => (typeof v === 'number' && Number.isFinite(v))
    ? v.toFixed(digits) : (v === null || v === undefined ? '—' : String(v));
  const fillList = (list, items, empty) => {
    list.replaceChildren();
    if (!items || !items.length) { list.appendChild(el('li', empty)); return; }
    for (const item of items) list.appendChild(el('li', item));
  };

  const STATE_LABELS = {
    running: 'IN ESECUZIONE',
    completed: 'COMPLETATA',
    completed_with_errors: 'COMPLETATA CON ERRORI',
    failed: 'FALLITA',
  };

  function selectedPayload() {
    if (select.value === '__upload__') {
      if (!uploaded) throw new Error('Seleziona un file JSON di configurazione.');
      return { config: uploaded.config, filename: uploaded.filename };
    }
    return { config_id: select.value };
  }

  async function api(url, options = {}) {
    const response = await fetch(url, { cache: 'no-store', ...options });
    let data = null;
    try { data = await response.json(); } catch (_) { /* corpo non JSON */ }
    return { ok: response.ok, status: response.status, data: data || {} };
  }

  async function loadConfigs() {
    const { ok, data } = await api('/api/mission/configs');
    select.replaceChildren();
    if (ok) {
      for (const cfg of data.configs || []) {
        const option = el('option', cfg.label + (cfg.available ? '' : ' — NON DISPONIBILE'));
        option.value = cfg.id;
        option.disabled = !cfg.available;
        select.appendChild(option);
      }
    }
    const upload = el('option', 'Carica file JSON…');
    upload.value = '__upload__';
    select.appendChild(upload);
  }

  select.addEventListener('change', () => {
    fileInput.hidden = select.value !== '__upload__';
    validationList.replaceChildren();
  });

  fileInput.addEventListener('change', async () => {
    uploaded = null;
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;
    try {
      if (file.size > 256 * 1024) throw new Error('File troppo grande (max 256 KB).');
      uploaded = { config: JSON.parse(await file.text()), filename: file.name };
      statusText.textContent = `File caricato: ${file.name}. Verificare la configurazione prima dell'avvio.`;
    } catch (error) {
      statusText.textContent = `File non utilizzabile: ${error.message}`;
    }
  });

  function showValidation(validation) {
    validationList.replaceChildren();
    if (!validation) return;
    for (const e of validation.errors || []) validationList.appendChild(el('li', `ERRORE · ${e}`, 'mission-error'));
    for (const w of validation.warnings || []) validationList.appendChild(el('li', `AVVISO · ${w}`));
    const active = (validation.sections || []).filter(s => s.active).map(s => s.name);
    const inactive = (validation.sections || []).filter(s => !s.active).map(s => s.name);
    if (active.length) validationList.appendChild(el('li', `Sezioni attive: ${active.join(', ')}`));
    if (inactive.length) validationList.appendChild(el('li', `Sezioni disabilitate (non verranno eseguite): ${inactive.join(', ')}`));
    const si = validation.site_identity;
    if (si) validationList.appendChild(el('li',
      `Identità del sito: ${si.status}${si.site ? ' · ' + si.site : ''}` +
      `${si.rasters_checked ? ' · raster verificati: ' + si.rasters_checked.length : ''}`));
    if (validation.valid) validationList.appendChild(el('li', 'Configurazione valida.', 'mission-ok'));
  }

  validateBtn.addEventListener('click', async () => {
    let payload;
    try { payload = selectedPayload(); } catch (e) { statusText.textContent = e.message; return; }
    validateBtn.disabled = true;
    stateTag.textContent = 'VALIDAZIONE';
    try {
      const { ok, data } = await api('/api/mission/validate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!ok) throw new Error(data.error || 'Validazione non riuscita.');
      showValidation(data.validation);
      stateTag.textContent = data.validation.valid ? 'CONFIG VALIDA' : 'CONFIG NON VALIDA';
      statusText.textContent = data.validation.valid
        ? 'Configurazione valida: la missione può essere avviata.'
        : 'Correggere gli errori prima dell\'avvio.';
    } catch (error) {
      stateTag.textContent = 'ERRORE';
      statusText.textContent = error.message;
    } finally {
      validateBtn.disabled = false;
    }
  });

  runBtn.addEventListener('click', async () => {
    let payload;
    try { payload = selectedPayload(); } catch (e) { statusText.textContent = e.message; return; }
    runBtn.disabled = true;
    try {
      const { status, data } = await api('/api/mission/runs', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (status === 409) {
        statusText.textContent = `Una missione è già in esecuzione (${data.running_id}). Monitoraggio in corso.`;
        return track(data.running_id);
      }
      if (status !== 202) {
        if (data.validation) showValidation(data.validation);
        throw new Error(data.error || `Avvio non riuscito (HTTP ${status}).`);
      }
      if (data.validation) showValidation(data.validation);
      track(data.run_id);
    } catch (error) {
      stateTag.textContent = 'AVVIO NON RIUSCITO';
      statusText.textContent = error.message;
      runBtn.disabled = false;
    }
  });

  function track(runId) {
    currentRun = runId;
    clearTimeout(pollTimer);
    poll();
  }

  async function poll() {
    if (!currentRun) return;
    const { ok, data } = await api(`/api/mission/runs/${currentRun}`).catch(
      e => ({ ok: false, data: { error: e.message } }));
    if (!ok) {
      stateTag.textContent = 'STATO NON DISPONIBILE';
      statusText.textContent = data.error || 'Impossibile leggere lo stato.';
      runBtn.disabled = false;
      return;
    }
    const run = data.run;
    stateTag.textContent = STATE_LABELS[run.state] || run.state.toUpperCase();
    if (run.state === 'running') {
      runBtn.disabled = true;
      statusText.textContent = `${run.progress} Tempo trascorso: ${fmt(run.elapsed_s, 1)} s · ID ${run.id}`;
      pollTimer = setTimeout(poll, 1000);
      return;
    }
    runBtn.disabled = false;
    loadReports();
    statusText.textContent = `Esecuzione ${run.id} terminata (${run.finished_utc}). ` +
      `Stato del motore: ${run.engine_status || 'nessun report'} · exit code ${run.exit_code}.`;
    renderResults(run);
  }

  function table(headers, rows) {
    const wrap = el('div', null, 'windows-table-wrap mission-table-wrap');
    const t = el('table', null, 'windows-table');
    const thead = el('thead'); const tr = el('tr');
    for (const h of headers) tr.appendChild(el('th', h));
    thead.appendChild(tr); t.appendChild(thead);
    const tbody = el('tbody');
    for (const row of rows) {
      const r = el('tr');
      for (const cell of row) {
        const td = el('td');
        if (cell instanceof Node) td.appendChild(cell); else td.textContent = cell;
        r.appendChild(td);
      }
      tbody.appendChild(r);
    }
    if (!rows.length) {
      const r = el('tr'); const td = el('td', 'Nessun dato.', 'empty-windows');
      td.colSpan = headers.length; r.appendChild(td); tbody.appendChild(r);
    }
    t.appendChild(tbody); wrap.appendChild(t);
    return wrap;
  }

  function heading(text) { return el('div', text, 'label'); }

  function renderResults(run) {
    results.replaceChildren();
    if (run.state === 'failed') {
      results.appendChild(heading('ESECUZIONE FALLITA'));
      results.appendChild(el('div', run.failure_reason || 'Motivo non disponibile.', 'engineering-result mission-error'));
      const out = (run.stdout_tail || '') + (run.stderr_tail ? '\n--- stderr ---\n' + run.stderr_tail : '');
      if (out.trim()) results.appendChild(el('pre', out, 'mission-pre'));
    }
    const res = run.result;
    if (!res) return;

    const grid = el('div', null, 'analytics-grid');
    const card = (label, value, sub) => {
      const c = el('div', null, 'analytics-card');
      c.append(el('small', label), el('strong', value), el('span', sub || ''));
      return c;
    };
    const ok = res.steps.filter(s => s.status === 'success').length;
    const failed = res.steps.filter(s => s.status === 'failed').length;
    const si = res.site_identity || {};
    grid.append(
      card('STATO MOTORE', res.engine_status, `run_id motore ${res.engine_run_id || '—'}`),
      card('SITO', si.site || 'non dichiarato', `identità: ${si.status || '—'}`),
      card('STEP ESEGUITI', `${ok} OK · ${failed} FALLITI`, `${res.not_executed.length} sezioni non eseguite`),
      card('CONFIGURAZIONE', run.config_label, `sha256 ${String(run.config_sha256).slice(0, 12)}…`),
    );
    results.appendChild(grid);

    results.appendChild(heading('STEP DEL MOTORE'));
    results.appendChild(table(['STEP', 'ESITO', 'STATO RISULTATO', 'ERRORE'],
      res.steps.map(s => [s.name, s.status, s.result_status || '—', s.error || '—'])));

    if (res.not_executed.length) {
      results.appendChild(heading('SEZIONI NON ESEGUITE'));
      const ul = el('ul', null, 'mission-list');
      fillList(ul, res.not_executed.map(n => `${n.name} — ${n.reason}`), '');
      results.appendChild(ul);
    }

    const sr = res.site_ranking || {};
    results.appendChild(heading('RANKING TOPOGRAFICO (site_selection)'));
    if (!sr.available) {
      results.appendChild(el('div', sr.reason || 'Ranking non disponibile.', 'window-notice'));
    } else {
      results.appendChild(el('div',
        `${sr.ranking_method} · Idonei: ${sr.eligible_count} · Esclusi: ${sr.rejected_count} · ` +
        `Soglie: pendenza ≤ ${fmt(sr.thresholds?.max_slope_deg, 1)}°, rugosità ≤ ${fmt(sr.thresholds?.max_roughness_m, 1)} m, ` +
        `copertura ≥ ${fmt(sr.thresholds?.min_valid_fraction, 2)}`, 'window-notice'));
      results.appendChild(table(
        ['#', 'CANDIDATO', 'RIGA/COL', 'SCORE', 'PENDENZA', 'RUGOSITÀ', 'SLOPE P95 °', 'RUGOSITÀ m', 'CLASSE TERRENO', 'METRICHE ESCLUSE'],
        sr.top_candidates.map(c => [
          c.rank, c.name, `${c.grid_row}/${c.grid_col}`, fmt(c.score_0_100),
          fmt(c.components_0_100?.slope), fmt(c.components_0_100?.roughness),
          fmt(c.terrain_metrics?.slope_p95_deg), fmt(c.terrain_metrics?.roughness_plane_residual_std_m),
          c.terrain_class || '—', (c.missing_metrics || []).join(', ') || '—',
        ])));
      results.appendChild(heading('QUALITÀ DATI LOLA · DIAGNOSTICA SEPARATA (NON INCIDE SULLO SCORE)'));
      results.appendChild(el('div',
        `lola_quality_validation.affects_score = ${sr.lola_quality_affects_score}`, 'window-notice'));
      results.appendChild(table(['#', 'CANDIDATO', 'STATO LOLA', 'FRAZIONE CELLE CON RITORNI'],
        sr.top_candidates.map(c => [c.rank, c.name, c.lola_quality?.status || '—',
          typeof c.lola_quality?.positive_return_fraction === 'number'
            ? `${(c.lola_quality.positive_return_fraction * 100).toFixed(1)} %` : '—'])));
      const ul = el('ul', null, 'mission-list');
      fillList(ul, sr.warnings, 'Nessun avviso.');
      results.appendChild(ul);
    }

    const otherSteps = Object.entries(res.step_results || {});
    if (otherSteps.length) {
      results.appendChild(heading('RISULTATI DEGLI ALTRI STEP (valori del motore)'));
      for (const [name, result] of otherSteps) {
        const details = el('details', null, 'mission-details');
        details.appendChild(el('summary', `${name} · ${result.status || ''}`));
        details.appendChild(el('pre', JSON.stringify(result, null, 2), 'mission-pre'));
        results.appendChild(details);
      }
    }

    results.appendChild(heading('AVVISI DEL MOTORE'));
    const warn = el('ul', null, 'mission-list');
    fillList(warn, [...(res.warnings || []), ...(run.validation_warnings || [])], 'Nessun avviso.');
    results.appendChild(warn);

    results.appendChild(heading('REPORT E FILE PRODOTTI'));
    const files = el('ul', null, 'mission-list');
    const reportItem = el('li');
    const reportLink = el('a', `mission_report.json — ${res.report_path}`);
    reportLink.href = res.report_url; reportLink.target = '_blank'; reportLink.rel = 'noopener';
    reportItem.appendChild(reportLink); files.appendChild(reportItem);
    for (const a of res.artifacts) {
      const li = el('li');
      if (a.downloadable) {
        const link = el('a', `${a.key} — ${a.path}`);
        link.href = a.url; link.target = '_blank'; link.rel = 'noopener';
        li.appendChild(link);
      } else {
        li.textContent = `${a.key} — ${a.path} (fuori dalla cartella dell'esecuzione: non scaricabile)`;
      }
      files.appendChild(li);
    }
    results.appendChild(files);

    const cfg = el('details', null, 'mission-details');
    cfg.appendChild(el('summary', `Configurazione utilizzata (${run.config_path})`));
    cfg.appendChild(el('pre', JSON.stringify(res.configuration, null, 2), 'mission-pre'));
    results.appendChild(cfg);
  }

  async function loadReports() {
    const list = $('missionReports');
    if (!list) return;
    const { ok, data } = await api('/api/mission/reports').catch(() => ({ ok: false, data: {} }));
    list.replaceChildren();
    if (!ok) { list.appendChild(el('li', 'Elenco report non disponibile.')); return; }
    const reports = data.reports || [];
    if (!reports.length) { list.appendChild(el('li', 'Nessun report prodotto dalla Web UI.')); return; }
    for (const r of reports) {
      const li = el('li');
      const open = el('a', `${r.generated_utc || '—'} · ${r.site || 'sito non dichiarato'} · ` +
        `${r.engine_status || 'nessuno stato'} · ${r.config_label || ''}`);
      open.href = '#';
      open.addEventListener('click', ev => { ev.preventDefault(); track(r.run_id); });
      const json = el('a', ' [mission_report.json]');
      json.href = r.report_url; json.target = '_blank'; json.rel = 'noopener';
      li.append(open, json, el('span', ` · ${r.artifacts.length} artefatti`));
      list.appendChild(li);
    }
  }

  async function init() {
    loadReports();
    await loadConfigs().catch(() => {});
    const { ok, data } = await api('/api/mission/runs').catch(() => ({ ok: false, data: {} }));
    if (!ok) return;
    if (data.running_id) {
      statusText.textContent = 'Missione già in esecuzione: monitoraggio ripreso.';
      track(data.running_id);
    } else if ((data.runs || []).length) {
      const last = data.runs[0];
      statusText.textContent = `Ultima esecuzione: ${last.id} (${STATE_LABELS[last.state] || last.state}).`;
      track(last.id);
    }
  }

  init();
})();
