// F1 — Integrazione Web UI → Mission Orchestrator.
// Mostra solo ciò che il motore ha realmente prodotto (mission_report.json).
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const root = $('missionEngineSection');
  if (!root) return;
  // Strumento dei Pianificatori di missione: attivo solo in /mission-control (sessione
  // verificata dal server); sulla piattaforma pubblica non interroga API riservate.
  if (window.lmcSession && !window.lmcSession.reservedPage) return;

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


  async function renderDecisionPanel(res) {
    const artifact = (res.artifacts || []).find(
      item => item.key === 'mission_decision' && item.downloadable && item.url
    );
    if (!artifact) return;

    const section = el('section', null, 'analytics-section');
    section.appendChild(heading('MISSION DECISION ENGINE'));
    section.appendChild(el(
      'div',
      'Caricamento della valutazione preliminare…',
      'window-notice'
    ));
    results.appendChild(section);

    try {
      const { ok, data } = await api(artifact.url);
      if (!ok || !data || data.schema !== 'lunar-mission-decision/1.0') {
        throw new Error('Report non disponibile o schema non riconosciuto.');
      }

      if (!section.isConnected) return;

      section.replaceChildren();
      section.appendChild(heading('MISSION DECISION ENGINE'));

      const decision = data.mission_decision || {};
      const quality = data.data_quality || {};
      const sources = data.data_sources || {};
      const cards = el('div', null, 'analytics-grid');

      const card = (label, value, detail) => {
        const node = el('div', null, 'analytics-card');
        node.append(
          el('small', label),
          el('strong', String(value ?? '—')),
          el('span', detail || '—')
        );
        return node;
      };

      const labels = {
        preliminary_environmental_candidates_available:
          'CANDIDATI AMBIENTALI PRELIMINARI',
        geometric_candidates_only:
          'SOLO CANDIDATI GEOMETRICI',
        no_geometric_candidate_in_available_samples:
          'NESSUN CANDIDATO GEOMETRICO',
        insufficient_astronomical_data:
          'DATI ASTRONOMICI INSUFFICIENTI'
      };

      const energyLabels = {
        within_configured_battery_budget: 'ENTRO BUDGET',
        exceeds_configured_battery_budget: 'BUDGET SUPERATO',
        not_evaluated: 'NON VALUTATO'
      };

      cards.append(
        card(
          'CLASSIFICAZIONE',
          labels[decision.classification] || decision.classification || 'NON DISPONIBILE',
          'Valutazione preliminare, non certificata'
        ),
        card(
          'CANDIDATI GEOMETRICI',
          decision.geometric_candidate_samples ?? 0,
          `Campioni comuni: ${data.sample_count ?? 0}`
        ),
        card(
          'CANDIDATI AMBIENTALI',
          decision.environmental_candidate_samples ?? 0,
          'Evidenze preliminari favorevoli'
        ),
        card(
          'EVIDENZE INCOMPLETE',
          decision.incomplete_environmental_samples ?? 0,
          'Campioni senza evidenze ambientali complete'
        ),
        card(
          'BUDGET ENERGETICO',
          energyLabels[decision.energy_status] || decision.energy_status || 'NON VALUTATO',
          decision.energy_within_budget === true
            ? 'Stima entro il budget configurato'
            : decision.energy_within_budget === false
              ? 'Stima oltre il budget configurato'
              : 'Dati energetici non disponibili'
        ),
        card(
          'QUALITÀ DEI DATI',
          Object.values(quality).reduce(
            (sum, value) => sum + (typeof value === 'number' ? value : 0), 0
          ),
          'Righe non utilizzabili nei report'
        )
      );

      section.appendChild(cards);

      section.appendChild(heading('DISPONIBILITÀ DEI REPORT'));

      const sourceList = el('ul', null, 'mission-list');
      for (const name of ['astronomy', 'illumination', 'visibility', 'energy']) {
        const source = sources[name] || {};
        const status = source.available ? 'DISPONIBILE' : 'NON DISPONIBILE';
        const detail = source.error ? ` — ${source.error}` : '';
        sourceList.appendChild(el(
          'li',
          `${name.toUpperCase()}: ${status}${detail}`
        ));
      }
      section.appendChild(sourceList);

      section.appendChild(heading('DETTAGLIO QUALITÀ DATI'));

      const qualityRows = [
        ['Righe astronomiche non valide', quality.invalid_astronomy_rows],
        ['Righe illuminazione non valide', quality.invalid_illumination_rows],
        ['Righe visibilità non valide', quality.invalid_visibility_rows],
        ['Campioni astronomici comuni', quality.common_astronomical_samples]
      ];

      section.appendChild(table(
        ['INDICATORE', 'VALORE'],
        qualityRows.map(([name, value]) => [name, value ?? '—'])
      ));

      // MISSION TIMELINE INTERACTIVE
      section.appendChild(heading('MISSION TIMELINE'));

      const timelineSamples = Array.isArray(data.samples)
        ? [...data.samples].sort(
            (a, b) => Date.parse(a.time_utc) - Date.parse(b.time_utc)
          )
        : [];

      const timeline = el('div', null, 'mission-timeline');
      timeline.style.display = 'flex';
      timeline.style.flexDirection = 'column';
      timeline.style.gap = '12px';

      const legend = el('div', null, 'window-notice');
      legend.textContent =
        'Verde: favorevole · Grigio: non favorevole (osservato) · Ambra: evidenza incompleta · Barra stretta ambra: lacuna temporale rispetto al passo configurato';
      timeline.appendChild(legend);

      const tracks = [
        {
          key: 'geometric',
          label: 'GEOMETRIA SOLE / TERRA',
          predicate: sample => sample.geometric_constraints_met === true
        },
        {
          key: 'environmental',
          label: 'AMBIENTE PRELIMINARE',
          predicate: sample => sample.environmental_candidate === true
        }
      ];

      const detail = el(
        'div',
        'Seleziona un campione sulla timeline per visualizzarne i dettagli.',
        'window-notice'
      );

      if (!timelineSamples.length) {
        timeline.appendChild(el(
          'div',
          'Nessun campione temporale disponibile.',
          'window-notice'
        ));
      } else {
        // Passo configurato dichiarato dal report: mai dedotto dai campioni.
        const continuity = (data.mission_windows || {}).temporal_continuity || {};
        const declaredStep = Number(continuity.expected_step_seconds);
        const referenceStep =
          Number.isFinite(declaredStep) && declaredStep > 0 ? declaredStep : null;
        const declaredTolerance = Number(continuity.step_tolerance_factor);
        const stepTolerance =
          Number.isFinite(declaredTolerance) && declaredTolerance >= 1
            ? declaredTolerance
            : 1;

        if (referenceStep === null) {
          timeline.appendChild(el(
            'div',
            'Passo temporale atteso non disponibile nel report: lacune e continuità non determinabili.',
            'window-notice'
          ));
        }

        for (const track of tracks) {
          const group = el('div', null, 'timeline-track');
          const label = el('div', track.label, 'label');
          const strip = el('div', null, 'timeline-strip');

          strip.style.display = 'flex';
          strip.style.width = '100%';
          strip.style.minHeight = '30px';
          strip.style.gap = '2px';
          strip.style.alignItems = 'stretch';

          let previousTime = null;

          timelineSamples.forEach((sample, index) => {
            const timestamp = Date.parse(sample.time_utc);
            const validTime = Number.isFinite(timestamp);

            if (
              previousTime !== null &&
              validTime &&
              referenceStep !== null &&
              (timestamp - previousTime) / 1000 > referenceStep * stepTolerance
            ) {
              const gap = el('div', null, 'timeline-gap');
              gap.title =
                `Lacuna temporale: intervallo superiore al passo configurato (${referenceStep} s)`;
              gap.style.flex = '0 0 5px';
              gap.style.background = '#d97706';
              gap.style.borderRadius = '3px';
              strip.appendChild(gap);
            }

            const favorable = track.predicate(sample);
            const incomplete =
              sample.classification === 'incomplete_environmental_evidence';

            const segment = el('button', '', 'timeline-segment');
            segment.type = 'button';
            segment.style.flex = '1 1 0';
            segment.style.minWidth = '3px';
            segment.style.minHeight = '30px';
            segment.style.padding = '0';
            segment.style.border = '1px solid rgba(255,255,255,.2)';
            segment.style.borderRadius = '3px';
            segment.style.cursor = 'pointer';

            segment.style.background = favorable
              ? '#16a34a'
              : incomplete
                ? '#d97706'
                : validTime
                  ? '#64748b'
                  : '#9ca3af';

            segment.title =
              `${sample.time_utc || 'Tempo sconosciuto'} · ` +
              `${track.label} · ` +
              `${favorable ? 'Favorevole' : incomplete ? 'Incompleto' : 'Non favorevole'}`;

            segment.addEventListener('click', () => {
              detail.textContent = [
                `Campione ${index + 1}/${timelineSamples.length}`,
                `UTC: ${sample.time_utc || '—'}`,
                `Sole: ${fmt(sample.sun_elevation_deg, 2)}°`,
                `Terra: ${fmt(sample.earth_elevation_deg, 2)}°`,
                `Geometria: ${sample.geometric_constraints_met ? 'favorevole' : 'non favorevole'}`,
                `Sole visibile: ${
                  sample.estimated_direct_sun_visible === true
                    ? 'sì'
                    : sample.estimated_direct_sun_visible === false
                      ? 'no' : 'sconosciuto'
                }`,
                `Terreno Sole: ${sample.terrain_visibility?.sun || 'sconosciuto'}`,
                `Terreno Terra: ${sample.terrain_visibility?.earth || 'sconosciuto'}`,
                `Evidenze complete: ${sample.environmental_evidence_complete ? 'sì' : 'no'}`,
                `Classificazione: ${sample.classification || '—'}`
              ].join(' | ');
            });

            strip.appendChild(segment);

            if (validTime) previousTime = timestamp;
          });

          group.append(label, strip);
          timeline.appendChild(group);
        }

        timeline.appendChild(detail);

        const endpoints = el(
          'div',
          `Inizio: ${timelineSamples[0].time_utc || '—'} · Fine: ${timelineSamples[timelineSamples.length - 1].time_utc || '—'} · Campioni: ${timelineSamples.length}` +
            ` · Passo atteso: ${referenceStep !== null ? `${referenceStep} s` : 'N/D'}` +
            ` · Lacune temporali: ${continuity.temporal_gap_count ?? 'N/D'}` +
            ` · Continuità: ${continuity.continuity_status || 'not_determinable'}`,
          'window-notice'
        );
        timeline.appendChild(endpoints);
      }

      section.appendChild(timeline);

      section.appendChild(heading('CAMPIONI TEMPORALI'));
      const samples = Array.isArray(data.samples) ? data.samples : [];

      if (samples.length) {
        const visibleSamples = samples.slice(0, 30);

        section.appendChild(table(
          [
            'TEMPO UTC',
            'SOLE °',
            'TERRA °',
            'GEOMETRIA',
            'SOLE VISIBILE',
            'VISIBILITÀ TERRENO',
            'EVIDENZE',
            'CLASSIFICAZIONE'
          ],
          visibleSamples.map(sample => [
            sample.time_utc || '—',
            fmt(sample.sun_elevation_deg, 2),
            fmt(sample.earth_elevation_deg, 2),
            sample.geometric_constraints_met ? 'OK' : 'NO',
            sample.estimated_direct_sun_visible === true
              ? 'SÌ'
              : sample.estimated_direct_sun_visible === false
                ? 'NO' : 'SCONOSCIUTO',
            `Sole: ${sample.terrain_visibility?.sun || '—'} · Terra: ${sample.terrain_visibility?.earth || '—'}`,
            sample.environmental_evidence_complete === true
              ? 'COMPLETE'
              : 'INCOMPLETE',
            sample.classification || '—'
          ])
        ));

        if (samples.length > visibleSamples.length) {
          section.appendChild(el(
            'div',
            `Visualizzati ${visibleSamples.length} di ${samples.length} campioni. Il report JSON contiene tutti i dati.`,
            'window-notice'
          ));
        }
      } else {
        section.appendChild(el(
          'div',
          'Nessun campione astronomico comune disponibile.',
          'window-notice'
        ));
      }

      section.appendChild(heading('MISSION WINDOWS'));

      const missionWindows = data.mission_windows || {};

      const intelligence = missionWindows.intelligence || {};
      const bestEnvironmental = intelligence.best_environmental_window;
      const bestGeometric = intelligence.best_geometric_window;
      const interruptions = intelligence.temporal_interruptions || {};

      const describeBestWindow = window => {
        if (!window) return 'Nessuna finestra disponibile';
        return `${Number(window.observed_span_minutes || 0).toFixed(1)} min · ${window.sample_count ?? 0} campioni`;
      };

      const intelligenceCards = el('div', null, 'analytics-grid');
      intelligenceCards.append(
        card(
          'MIGLIORE FINESTRA AMBIENTALE',
          describeBestWindow(bestEnvironmental),
          bestEnvironmental
            ? `${bestEnvironmental.start_utc} → ${bestEnvironmental.end_utc}`
            : 'Nessuna opportunità preliminare rilevata'
        ),
        card(
          'MIGLIORE FINESTRA GEOMETRICA',
          describeBestWindow(bestGeometric),
          bestGeometric
            ? `${bestGeometric.start_utc} → ${bestGeometric.end_utc}`
            : 'Nessuna finestra geometrica rilevata'
        ),
        card(
          'INTERRUZIONI TEMPORALI',
          (interruptions.geometric || 0) + (interruptions.environmental || 0),
          `Geometriche: ${interruptions.geometric ?? 0} · Ambientali: ${interruptions.environmental ?? 0}`
        ),
        card(
          'RAPPORTO AMBIENTALE / GEOMETRICO',
          intelligence.environmental_to_geometric_window_ratio == null
            ? 'N/D'
            : `${(intelligence.environmental_to_geometric_window_ratio * 100).toFixed(1)}%`,
          `${intelligence.environmental_window_count ?? 0} finestre ambientali su ${intelligence.geometric_window_count ?? 0} geometriche`
        )
      );

      section.appendChild(heading('MISSION WINDOW INTELLIGENCE'));
      section.appendChild(intelligenceCards);\n
      const temporal = missionWindows.temporal_intelligence || {};
      const geometricTemporal = temporal.geometric || {};
      const environmentalTemporal = temporal.environmental || {};

      const temporalCards = el('div', null, 'analytics-grid');

      const percent = value =>
        value == null ? 'N/D' : `${Number(value).toFixed(1)}%`;

      const minutes = value =>
        value == null ? 'N/D' : `${Number(value).toFixed(1)} min`;

      temporalCards.append(
        card(
          'CAMPIONI GEOMETRICI FAVOREVOLI',
          percent(temporal.geometric_favorable_sample_percent),
          `${temporal.geometric_favorable_samples ?? 0} su ${temporal.sample_count ?? 0}`
        ),
        card(
          'CAMPIONI AMBIENTALI FAVOREVOLI',
          percent(temporal.environmental_favorable_sample_percent),
          `${temporal.environmental_favorable_samples ?? 0} su ${temporal.sample_count ?? 0}`
        ),
        card(
          'TEMPO OSSERVATO GEOMETRICO',
          minutes(geometricTemporal.observed_span_minutes),
          `${geometricTemporal.window_count ?? 0} finestre`
        ),
        card(
          'TEMPO OSSERVATO AMBIENTALE',
          minutes(environmentalTemporal.observed_span_minutes),
          `${environmentalTemporal.window_count ?? 0} finestre`
        ),
        card(
          'INTERRUZIONE GEOMETRICA PIÙ LUNGA',
          minutes(geometricTemporal.longest_interruption_minutes),
          `${geometricTemporal.interruption_count ?? 0} interruzioni`
        ),
        card(
          'INTERRUZIONE AMBIENTALE PIÙ LUNGA',
          minutes(environmentalTemporal.longest_interruption_minutes),
          `${environmentalTemporal.interruption_count ?? 0} interruzioni`
        )
      );

      section.appendChild(heading('MISSION TEMPORAL INTELLIGENCE'));
      section.appendChild(temporalCards);

      section.appendChild(el(
        'div',
        temporal.duration_interpretation ||
          'Statistiche basate sui campioni temporali disponibili.',
        'window-notice'
      ));


      const formatWindows = (items) => {
        if (!Array.isArray(items) || !items.length) {
          return [['—', 'Nessuna finestra disponibile', '—', '—', '—', '—']];
        }

        return items.map((window, index) => [
          `#${index + 1}`,
          window.start_utc || '—',
          window.end_utc || '—',
          `${Number(window.observed_span_minutes || 0).toFixed(1)} min`,
          window.sample_count ?? '—',
          window.single_sample ? 'SINGOLO CAMPIONE' : 'MULTICAMPIONE'
        ]);
      };

      section.appendChild(heading('FINESTRE GEOMETRICHE'));
      section.appendChild(table(
        ['FINESTRA', 'INIZIO UTC', 'FINE UTC', 'DURATA OSSERVATA', 'CAMPIONI', 'CONTINUITÀ'],
        formatWindows(missionWindows.geometric)
      ));

      section.appendChild(heading('FINESTRE AMBIENTALI PRELIMINARI'));
      section.appendChild(table(
        ['FINESTRA', 'INIZIO UTC', 'FINE UTC', 'DURATA OSSERVATA', 'CAMPIONI', 'CONTINUITÀ'],
        formatWindows(missionWindows.environmental)
      ));

      // Distinzione tra finestre geometriche ed energeticamente sostenibili.
      const solarSummary = data.solar_energy_summary || {};
      section.appendChild(heading('FINESTRE GEOMETRICHE ENERGETICAMENTE SOSTENIBILI'));
      if (!solarSummary.available) {
        section.appendChild(el(
          'div',
          'Sostenibilità energetica non valutata: report del Solar Energy Engine non disponibile.',
          'window-notice'
        ));
      } else {
        section.appendChild(el(
          'div',
          `Stato: ${solarSummary.energy_sustainability_status || '—'} · ` +
            `Campioni geometrici: ${solarSummary.geometric_samples ?? '—'} · ` +
            `di cui sostenibili: ${solarSummary.geometric_and_energy_sustainable_samples ?? '—'} · ` +
            `non determinabili: ${solarSummary.geometric_samples_energy_not_determinable ?? '—'} · ` +
            `Report solare: ${solarSummary.report_status || '—'} (modello non validato)`,
          'window-notice'
        ));
        section.appendChild(table(
          ['FINESTRA', 'INIZIO UTC', 'FINE UTC', 'DURATA OSSERVATA', 'CAMPIONI', 'CONTINUITÀ'],
          formatWindows(missionWindows.energy_sustainable)
        ));
      }

      section.appendChild(el(
        'div',
        'Le durate rappresentano l’intervallo tra il primo e l’ultimo campione osservato. Non sono stime di continuità fisica né finestre operative certificate.',
        'window-notice'
      ));

      section.appendChild(el(
        'div',
        `Metodo: ${missionWindows.method || 'informazione non disponibile'}`,
        'window-notice'
      ));

      section.appendChild(heading('LIMITAZIONI SCIENTIFICHE'));
      const limitations = el('ul', null, 'mission-list');
      fillList(
        limitations,
        Array.isArray(data.limitations) ? data.limitations : [],
        'Nessuna informazione disponibile.'
      );
      section.appendChild(limitations);

      section.appendChild(el(
        'div',
        `Sicurezza operativa certificata: NO. Risultati esclusivamente preliminari.`,
        'window-notice'
      ));

      const reportLink = el('a', 'Apri report completo mission_decision_report.json');
      reportLink.href = artifact.url;
      reportLink.target = '_blank';
      reportLink.rel = 'noopener';
      section.appendChild(reportLink);

    } catch (error) {
      if (!section.isConnected) return;
      section.appendChild(el(
        'div',
        `Decision Engine: ${error.message}`,
        'engineering-result mission-error'
      ));
    }
  }

  // ------------------------------------------------------------------ //
  // Solar Energy Engine: grafici temporali costruiti solo dai valori del
  // report (nessun ricalcolo, nessuna interpolazione).
  // ------------------------------------------------------------------ //
  const SVG_NS = 'http://www.w3.org/2000/svg';
  const svgEl = (tag, attrs = {}) => {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    return node;
  };

  // series: [{label, color, segments: [[[tMs, value], ...], ...], dash}]
  // refLines: [{value, label, color}] · bands: [{start, end, color, title}]
  function timeChart({ title, unit, series, refLines = [], bands = [], tMin, tMax }) {
    const W = 800, H = 230, L = 64, R = 12, T = 14, B = 34;
    const values = [];
    for (const s of series) for (const seg of s.segments) for (const [, v] of seg) values.push(v);
    for (const r of refLines) if (Number.isFinite(r.value)) values.push(r.value);

    const wrap = el('div', null, 'solar-chart');
    wrap.style.marginTop = '10px';
    wrap.appendChild(el('div', title, 'label'));

    if (!values.length || !(tMax > tMin)) {
      wrap.appendChild(el('div', 'Dati insufficienti per il grafico.', 'window-notice'));
      return wrap;
    }

    let vMin = Math.min(0, ...values);
    let vMax = Math.max(...values);
    if (vMax === vMin) vMax = vMin + 1;
    const pad = (vMax - vMin) * 0.05;
    vMax += pad;

    const x = t => L + (t - tMin) / (tMax - tMin) * (W - L - R);
    const y = v => T + (1 - (v - vMin) / (vMax - vMin)) * (H - T - B);

    const svg = svgEl('svg', {
      viewBox: `0 0 ${W} ${H}`, width: '100%', role: 'img',
      'aria-label': title,
    });
    svg.style.display = 'block';
    svg.style.height = 'auto';
    svg.style.background = '#0b121c';
    svg.style.border = '1px solid #1c2c3c';
    svg.style.borderRadius = '6px';

    for (const band of bands) {
      const x0 = x(Math.max(band.start, tMin));
      const x1 = x(Math.min(band.end, tMax));
      if (!(x1 > x0)) continue;
      const rect = svgEl('rect', {
        x: x0, y: T, width: x1 - x0, height: H - T - B, fill: band.color,
      });
      if (band.title) rect.appendChild(svgEl('title')).textContent = band.title;
      svg.appendChild(rect);
    }

    for (let i = 0; i <= 4; i++) {
      const v = vMin + (vMax - vMin) * i / 4;
      svg.appendChild(svgEl('line', {
        x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: '#1c2c3c', 'stroke-width': 1,
      }));
      const label = svgEl('text', {
        x: L - 6, y: y(v) + 3, 'text-anchor': 'end', fill: '#8295a9', 'font-size': 10,
      });
      label.textContent = `${v.toFixed(Math.abs(vMax) < 10 ? 2 : 0)} ${unit}`;
      svg.appendChild(label);
    }

    for (const [t, anchor] of [[tMin, 'start'], [(tMin + tMax) / 2, 'middle'], [tMax, 'end']]) {
      const label = svgEl('text', {
        x: x(t), y: H - 12, 'text-anchor': anchor, fill: '#8295a9', 'font-size': 10,
      });
      label.textContent = new Date(t).toISOString().replace('T', ' ').slice(0, 16) + ' UTC';
      svg.appendChild(label);
    }

    for (const ref of refLines) {
      if (!Number.isFinite(ref.value)) continue;
      svg.appendChild(svgEl('line', {
        x1: L, x2: W - R, y1: y(ref.value), y2: y(ref.value),
        stroke: ref.color, 'stroke-width': 1.5, 'stroke-dasharray': '6 4',
      }));
    }

    for (const s of series) {
      for (const seg of s.segments) {
        if (!seg.length) continue;
        const d = seg.map(([t, v], i) => `${i ? 'L' : 'M'}${x(t).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
        svg.appendChild(svgEl('path', {
          d, fill: 'none', stroke: s.color, 'stroke-width': 2,
          'stroke-dasharray': s.dash || 'none', 'vector-effect': 'non-scaling-stroke',
        }));
      }
    }
    wrap.appendChild(svg);

    const legend = el('div', null, 'window-notice');
    legend.style.display = 'flex';
    legend.style.flexWrap = 'wrap';
    legend.style.gap = '12px';
    const swatch = (color, text, dashed) => {
      const item = el('span');
      const mark = el('span');
      mark.style.display = 'inline-block';
      mark.style.width = '14px';
      mark.style.height = dashed === 'band' ? '8px' : '0';
      mark.style.borderTop = dashed === 'band' ? 'none' : `2px ${dashed ? 'dashed' : 'solid'} ${color}`;
      if (dashed === 'band') mark.style.background = color;
      mark.style.marginRight = '5px';
      mark.style.verticalAlign = 'middle';
      item.append(mark, document.createTextNode(text));
      return item;
    };
    for (const s of series) legend.appendChild(swatch(s.color, s.label, !!s.dash));
    for (const r of refLines) {
      if (Number.isFinite(r.value)) legend.appendChild(swatch(r.color, `${r.label} (${fmt(r.value, 1)} ${unit})`, true));
    }
    const bandLabels = new Map();
    for (const b of bands) if (b.legend) bandLabels.set(b.legend, b.color);
    for (const [text, color] of bandLabels) legend.appendChild(swatch(color, text, 'band'));
    wrap.appendChild(legend);
    return wrap;
  }

  // Segmenti a gradino (mantenimento di ordine zero, come nel report):
  // un valore null interrompe la linea invece di essere inventato.
  function stepSegments(intervals, valueOf) {
    const segments = [];
    let current = [];
    for (const item of intervals) {
      const v = valueOf(item);
      const t0 = Date.parse(item.start_utc), t1 = Date.parse(item.end_utc);
      const contiguous = current.length && current[current.length - 1][0] === t0;
      if (!Number.isFinite(v) || !Number.isFinite(t0) || !Number.isFinite(t1)) {
        if (current.length) segments.push(current);
        current = [];
        continue;
      }
      if (current.length && !contiguous) { segments.push(current); current = []; }
      current.push([t0, v], [t1, v]);
    }
    if (current.length) segments.push(current);
    return segments;
  }

  function pointSegments(samples, valueOf) {
    const segments = [];
    let current = [];
    for (const sample of samples) {
      const v = valueOf(sample);
      const t = Date.parse(sample.time_utc);
      if (!Number.isFinite(v) || !Number.isFinite(t)) {
        if (current.length) segments.push(current);
        current = [];
      } else {
        current.push([t, v]);
      }
    }
    if (current.length) segments.push(current);
    return segments;
  }

  async function renderSolarEnergyPanel(res) {
    const artifact = (res.artifacts || []).find(
      item => item.key === 'solar_energy' && item.downloadable && item.url
    );
    if (!artifact) return;

    const section = el('section', null, 'analytics-section');
    section.appendChild(heading('SOLAR ENERGY ENGINE'));
    section.appendChild(el('div', 'Caricamento del bilancio energetico…', 'window-notice'));
    results.appendChild(section);

    try {
      const { ok, data } = await api(artifact.url);
      if (!ok || !data || data.schema !== 'lunar-solar-energy-budget/1.0') {
        throw new Error('Report non disponibile o schema non riconosciuto.');
      }
      if (!section.isConnected) return;
      section.replaceChildren();
      section.appendChild(heading('SOLAR ENERGY ENGINE · BILANCIO ENERGETICO PRELIMINARE'));

      const summary = data.summary || {};
      const autonomy = data.autonomy || {};
      const quality = data.data_quality || {};
      const series = data.time_series || {};
      const samples = Array.isArray(series.samples) ? series.samples : [];
      const intervals = Array.isArray(series.intervals) ? series.intervals : [];
      const deficits = data.deficit_intervals || {};

      const statusLabels = {
        preliminary_estimate: 'STIMA PRELIMINARE',
        partial_missing_inputs: 'PARZIALE · INPUT MANCANTI',
        partial_incomplete_data: 'PARZIALE · DATI INCOMPLETI',
        not_computable: 'NON CALCOLABILE',
      };
      const sustainabilityLabels = {
        sustainable_in_evaluated_period: 'SOSTENIBILE NEL PERIODO',
        sustainable_in_partial_period: 'SOSTENIBILE (PERIODO PARZIALE)',
        reserve_violated: 'RISERVA VIOLATA',
        load_not_sustainable: 'CARICO NON SOSTENIBILE',
        not_evaluated: 'NON VALUTATA',
      };
      const wh = v => (typeof v === 'number' && Number.isFinite(v)) ? `${v.toFixed(1)} Wh` : 'N/D';
      const hours = v => (typeof v === 'number' && Number.isFinite(v)) ? `${v.toFixed(1)} h` : 'N/D';

      const card = (label, value, detail) => {
        const node = el('div', null, 'analytics-card');
        node.append(el('small', label), el('strong', String(value ?? '—')), el('span', detail || '—'));
        return node;
      };

      const cards = el('div', null, 'analytics-grid');
      cards.append(
        card('STATO DEL REPORT', statusLabels[data.status] || data.status || '—',
          'Modello non validato scientificamente'),
        card('SOSTENIBILITÀ', sustainabilityLabels[summary.sustainability] || summary.sustainability || '—',
          `Ore valutate: ${hours(summary.evaluated_hours)}`),
        card('PRODUZIONE UTILIZZABILE', wh(summary.production_wh_evaluated),
          'Intervalli con bilancio completo'),
        card('CONSUMO TOTALE', wh((summary.consumption_wh_by_category || {}).total),
          `Energia netta: ${wh(summary.net_energy_wh)}`),
        card('BATTERIA FINALE', wh(summary.final_soc_wh),
          typeof summary.final_soc_fraction === 'number'
            ? `${(summary.final_soc_fraction * 100).toFixed(1)} % della capacità` : 'Stato di carica N/D'),
        card('RISERVA', wh(summary.reserve_wh),
          `Margine minimo: ${wh(summary.min_reserve_margin_wh)}`),
        card('DEFICIT', `${(deficits.net_deficit || []).length} intervalli`,
          `Sotto riserva: ${(deficits.below_reserve || []).length} · Carico non servito: ${wh(summary.unmet_load_wh)}`),
        card('AUTONOMIA SOLO BATTERIA', hours(autonomy.battery_only_hours_from_final_soc_at_mean_load),
          `Al carico di picco: ${hours(autonomy.battery_only_hours_from_final_soc_at_peak_load)}`)
      );
      section.appendChild(cards);

      const missing = (data.missing_inputs || []).map(i => `MANCANTE · ${i.parameter} — ${i.reason}`);
      const invalid = (data.invalid_inputs || []).map(i => `NON VALIDO · ${i.parameter} — ${i.reason}`);
      if (missing.length || invalid.length) {
        section.appendChild(heading('INPUT MANCANTI O NON VALIDI (RISULTATI PARZIALI)'));
        const ul = el('ul', null, 'mission-list');
        fillList(ul, [...missing, ...invalid], '');
        section.appendChild(ul);
      }

      const times = samples.map(s => Date.parse(s.time_utc)).filter(Number.isFinite);
      const tMin = times.length ? Math.min(...times) : 0;
      const tMax = times.length ? Math.max(...times) : 0;

      const toBands = (runs, color, legend) => (Array.isArray(runs) ? runs : []).map(run => ({
        start: Date.parse(run.start_utc), end: Date.parse(run.end_utc), color, legend,
        title: `${legend}: ${run.start_utc} → ${run.end_utc}`,
      })).filter(b => Number.isFinite(b.start) && Number.isFinite(b.end));

      const gapBands = intervals
        .filter(i => i.status === 'temporal_gap')
        .map(i => ({ start: Date.parse(i.start_utc), end: Date.parse(i.end_utc),
          color: 'rgba(130,149,169,.18)', legend: 'Lacuna temporale', title: 'Lacuna temporale' }));

      section.appendChild(timeChart({
        title: 'POTENZA · PRODUZIONE UTILIZZABILE vs CONSUMO',
        unit: 'W', tMin, tMax,
        series: [
          { label: 'Produzione utilizzabile', color: '#76e5b0',
            segments: stepSegments(intervals, i => i.production_wh != null && i.duration_hours > 0
              ? i.production_wh / i.duration_hours : NaN) },
          { label: 'Consumo totale', color: '#f4b95f',
            segments: stepSegments(intervals, i => i.consumption_wh && i.duration_hours > 0
              ? i.consumption_wh.total / i.duration_hours : NaN) },
          { label: 'Trazione', color: '#c084fc', dash: '4 3',
            segments: stepSegments(intervals, i => i.consumption_wh && i.duration_hours > 0
              ? i.consumption_wh.traction / i.duration_hours : NaN) },
        ],
        bands: [
          ...toBands(deficits.net_deficit, 'rgba(244,185,95,.12)', 'Deficit netto'),
          ...gapBands,
        ],
      }));

      section.appendChild(timeChart({
        title: 'BATTERIA · STATO DI CARICA',
        unit: 'Wh', tMin, tMax,
        series: [
          { label: 'Stato di carica', color: '#5be7f5', segments: pointSegments(samples, s => s.soc_wh) },
        ],
        refLines: [
          { value: summary.reserve_wh, label: 'Riserva minima', color: '#f87171' },
          { value: summary.battery_capacity_wh, label: 'Capacità', color: '#8295a9' },
        ],
        bands: [
          ...toBands(deficits.below_reserve, 'rgba(248,113,113,.18)', 'Sotto riserva'),
          ...toBands(deficits.unmet_load, 'rgba(248,113,113,.35)', 'Carico non servito'),
          ...gapBands,
        ],
      }));

      section.appendChild(el(
        'div',
        `Integrazione: ${series.integration_method || '—'} · Passo atteso: ${series.expected_step_seconds ?? 'N/D'} s · ` +
          `Traccia batteria completa: ${quality.soc_trace_complete ? 'sì' : 'no'}` +
          (quality.soc_trace_break_utc ? ` (interrotta a ${quality.soc_trace_break_utc}: ${quality.soc_trace_break_reason})` : ''),
        'window-notice'
      ));

      section.appendChild(heading('CONSUMI PER CATEGORIA'));
      const categories = summary.consumption_wh_by_category || {};
      const categoryNames = {
        traction: 'Trazione', auxiliary: 'Ausiliari', science: 'Strumentazione scientifica',
        communications: 'Comunicazioni', thermal_control: 'Controllo termico', total: 'TOTALE',
      };
      section.appendChild(table(['CATEGORIA', 'ENERGIA'],
        Object.keys(categoryNames).filter(k => k in categories)
          .map(k => [categoryNames[k], wh(categories[k])])));

      section.appendChild(heading('INTERVALLI DI DEFICIT NETTO'));
      section.appendChild(table(['INIZIO UTC', 'FINE UTC', 'DURATA', 'DEFICIT'],
        (deficits.net_deficit || []).map(r => [r.start_utc, r.end_utc, hours(r.duration_hours), wh(r.energy_wh)])));

      section.appendChild(heading('QUALITÀ E COMPLETEZZA DEI DATI'));
      section.appendChild(table(['INDICATORE', 'VALORE'], [
        ['Campioni', quality.sample_count ?? '—'],
        ['Intervalli', quality.interval_count ?? '—'],
        ['Campioni con illuminazione', quality.samples_with_illumination ?? '—'],
        ['Campioni con distanza Horizons', quality.samples_with_horizons_distance ?? '—'],
        ['Lacune temporali', quality.temporal_gap_count ?? 'non determinabile'],
        ['Continuità verificabile', quality.continuity_verifiable ? 'sì' : 'no'],
        ['Stati degli intervalli', JSON.stringify(quality.interval_status_counts || {})],
      ]));

      section.appendChild(heading('GRANDEZZE NON VALUTATE E LIMITAZIONI'));
      const limits = el('ul', null, 'mission-list');
      fillList(limits, [...(data.not_evaluated || []), ...(data.limitations || [])], 'Nessuna informazione.');
      section.appendChild(limits);

      const link = el('a', 'Apri report completo solar_energy_budget.json');
      link.href = artifact.url; link.target = '_blank'; link.rel = 'noopener';
      section.appendChild(link);
    } catch (error) {
      if (!section.isConnected) return;
      section.appendChild(el('div', `Solar Energy Engine: ${error.message}`,
        'engineering-result mission-error'));
    }
  }

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
    renderDecisionPanel(res);
    renderSolarEnergyPanel(res);

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
