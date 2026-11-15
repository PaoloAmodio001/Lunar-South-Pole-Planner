// F9 · Shell della dashboard: navigazione per aree, barra di stato con stati reali, orologio UTC.
// Solo presentazione: non calcola nulla e non chiama endpoint scientifici.
// Rollback: rimuovere <script src="/ui/shell.js"> da index.html (le sezioni restano tutte visibili).
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const main = document.querySelector('main');
  if (!main) return;

  // --- Navigazione: una vista mostra solo le sezioni con data-views corrispondente ---
  const TITLES = {
    solar: 'Illuminazione solare',
    earth: 'Comunicazione con la Terra',
    terrain: 'Analisi del terreno',
    rover: 'Missione rover',
    compare: 'Confronto dei siti',
    status: 'Stato della missione'
  };
  // Le viste rover e confronto riusano gli strumenti di science.js (stesso pulsante, stessa logica).
  const TOOL_FOR_VIEW = { rover: 'rover-plan', compare: 'site-comparison' };
  const TERRAIN_TOOLS = ['dem-audit', 'terrain', 'horizon'];
  const navButtons = document.querySelectorAll('.shell-nav [data-nav]');

  function currentTool() {
    const b = document.querySelector('[data-sci-tool][aria-pressed="true"]');
    return b ? b.dataset.sciTool : null;
  }
  function clickTool(name) {
    const b = document.querySelector(`[data-sci-tool="${name}"]`);
    if (b && currentTool() !== name) b.click();
  }

  function showView(view, { focus = false } = {}) {
    if (!TITLES[view]) view = 'solar';
    main.dataset.view = view;
    navButtons.forEach(b => {
      if (b.dataset.nav === view) b.setAttribute('aria-current', 'true');
      else b.removeAttribute('aria-current');
    });
    const title = $('workspaceTitle');
    if (title) title.textContent = TITLES[view];
    if (TOOL_FOR_VIEW[view]) clickTool(TOOL_FOR_VIEW[view]);
    else if (view === 'terrain' && !TERRAIN_TOOLS.includes(currentTool())) clickTool('dem-audit');
    try { localStorage.setItem('lspp.view', view); } catch (_) {}
    // I grafici canvas si ridisegnano sull'evento resize già gestito da main.js.
    requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
    if (focus) {
      const bottom = document.querySelector('.panel.bottom');
      bottom?.scrollTo?.({ top: 0 });
      if (window.matchMedia('(max-width: 767px)').matches) bottom?.scrollIntoView({ block: 'start' });
    }
  }
  navButtons.forEach(b => b.addEventListener('click', () => showView(b.dataset.nav, { focus: true })));

  let savedView = null;
  try { savedView = localStorage.getItem('lspp.view'); } catch (_) {}
  // science.js è caricato con defer prima di questo script: i pulsanti strumento esistono già.
  showView(savedView || 'solar');

  // --- Barra di stato: rispecchia elementi che il codice esistente aggiorna con dati reali ---
  function stateOf(el) {
    if (!el) return 'unknown';
    if (el.classList.contains('good')) return 'ok';
    if (el.classList.contains('warn')) {
      return /ERROR|ERRORE|NON/i.test(el.textContent) ? 'error' : 'busy';
    }
    return 'unknown';
  }
  const LABELS = {
    LOADED: 'caricato', LOADING: 'in caricamento', 'LOAD ERROR': 'errore di caricamento',
    WAITING: 'non calcolate', READY: 'non calcolate', CALCULATING: 'calcolo in corso',
    'CONNECTED · JPL': 'calcolate (JPL)', ERROR: 'errore'
  };
  function mirror(sourceId, textId, dotId) {
    const src = $(sourceId), text = $(textId), dot = $(dotId);
    if (!src || !text || !dot) return;
    const sync = () => {
      const raw = src.textContent.trim();
      text.textContent = LABELS[raw] || raw.toLowerCase();
      let state = stateOf(src);
      if (sourceId === 'ephemerisStatus' && (raw === 'WAITING' || raw === 'READY')) state = 'unknown';
      if (raw === 'CALCULATING') state = 'busy';
      dot.dataset.state = state;
    };
    new MutationObserver(sync).observe(src, { childList: true, characterData: true, subtree: true, attributes: true, attributeFilter: ['class'] });
    sync();
  }
  mirror('modelStatus', 'hdrModel', 'hdrModelDot');
  mirror('ephemerisStatus', 'hdrEphem', 'hdrEphemDot');

  // Server: verifica reale (una richiesta a /api/sites, endpoint di sola lettura già usato dalla UI).
  async function checkServer() {
    const text = $('hdrServer'), dot = $('hdrServerDot');
    try {
      const r = await fetch('/api/sites', { cache: 'no-store' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      text.textContent = 'raggiungibile';
      dot.dataset.state = 'ok';
    } catch (e) {
      text.textContent = 'non raggiungibile';
      dot.dataset.state = 'error';
    }
  }
  checkServer();
  setInterval(() => { if (!document.hidden) checkServer(); }, 60000);

  // Contesto corrente: sito, durata e inizio UTC presi dai campi di configurazione.
  function updateContext() {
    const ctx = $('shellContext');
    if (!ctx) return;
    const site = $('site')?.value || '';
    const hours = $('duration')?.value || '';
    const start = $('date')?.value ? $('date').value.replace('T', ' ') : '';
    ctx.textContent = site ? `${site}, ${hours} h dal ${start} UTC` : '';
  }
  ['site', 'duration', 'date'].forEach(id => $(id)?.addEventListener('change', updateContext));
  $('apply')?.addEventListener('click', updateContext);
  setTimeout(updateContext, 0);

  // Orologio UTC
  const clock = $('hdrClock');
  function tick() { if (clock) { const d = new Date(); clock.textContent = d.toISOString().slice(11, 19); clock.dateTime = d.toISOString(); } }
  tick();
  setInterval(tick, 1000);
})();
