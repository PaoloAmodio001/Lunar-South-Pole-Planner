// Last updated: 2026-11-15
// Dashboard MISSION PLANNERS: stato reale di backend, JPL Horizons e sessione.
(() => {
  'use strict';
  const $ = id => document.getElementById(id);

  function set(dotId, textId, state, text) {
    const dot = $(dotId), node = $(textId);
    if (dot) dot.dataset.state = state;
    if (node) node.textContent = text;
  }

  const JPL_KIND = {
    timeout: 'nessuna risposta entro il timeout',
    dns: 'DNS non risolto (rete o DNS locale)',
    connection: 'connessione non riuscita',
    http: 'errore HTTP del servizio',
    invalid_response: 'risposta non valida'
  };

  function backendDown() {
    set('svcBackendDot', 'svcBackend', 'error', 'Non raggiungibile: il server Python non è in esecuzione. Avviarlo con ./start.sh (ricontrollo automatico ogni 5 s).');
    set('hdrServerDot', 'hdrServer', 'error', 'non raggiungibile');
    for (const [dot, text] of [['svcJplDot', 'svcJpl'], ['svcSessionDot', 'svcSession']]) {
      set(dot, text, 'unknown', 'Non verificabile senza backend.');
    }
    set('controlDot', 'controlState', 'error', 'backend non raggiungibile');
  }

  let loading = false;
  async function refresh(force = false) {
    if (loading) return;
    loading = true;
    const button = $('refreshServices');
    if (button) button.disabled = true;
    try {
      let response;
      try {
        response = await fetch(`/api/services${force ? '?refresh=1' : ''}`, { cache: 'no-store' });
      } catch (_) {
        backendDown();
        return;
      }
      if (response.status === 401) return; // session.js reindirizza al login
      let data;
      try { data = await response.json(); } catch (_) { data = null; }
      if (!response.ok || !data || data.status !== 'ok') {
        set('svcBackendDot', 'svcBackend', 'error', `Risposta non valida dal backend (HTTP ${response.status}).`);
        return;
      }
      set('svcBackendDot', 'svcBackend', 'ok', 'Raggiungibile.');
      set('hdrServerDot', 'hdrServer', 'ok', 'raggiungibile');
      set('controlDot', 'controlState', 'ok', 'disponibile');

      const jpl = data.jpl_horizons || {};
      if (jpl.available) {
        set('svcJplDot', 'svcJpl', 'ok', `Disponibile${jpl.api_version ? ` (API ${jpl.api_version})` : ''}. Le effemeridi possono essere calcolate.`);
      } else {
        set('svcJplDot', 'svcJpl', 'error', `Non disponibile: ${JPL_KIND[jpl.kind] || jpl.kind || 'stato sconosciuto'}. ${jpl.detail || ''} Le effemeridi non vengono sostituite con dati dimostrativi.`);
      }

      const session = data.session || {};
      const idle = session.idle_timeout_minutes;
      set('svcSessionDot', 'svcSession', 'ok',
        session.user ? `Utente ${session.user}${idle ? ` · scadenza dopo ${Math.round(idle)} min di inattività` : ''}` : 'Autenticazione disattivata (uso locale/test).');
      const user = $('sessionUser');
      if (user) user.textContent = session.user ? `Accesso come ${session.user}` : '';
      const checked = $('servicesChecked');
      if (checked) checked.textContent = `Verificato alle ${new Date().toISOString().slice(11, 19)} UTC`;
    } finally {
      loading = false;
      if (button) button.disabled = false;
    }
  }

  $('refreshServices')?.addEventListener('click', () => refresh(true));
  window.addEventListener('lmc:backend', e => { if (e.detail.available) refresh(); else backendDown(); });
  refresh();
  setInterval(() => { if (!document.hidden) refresh(); }, 60000);

  const clock = $('hdrClock');
  const tick = () => { if (clock) { const d = new Date(); clock.textContent = d.toISOString().slice(11, 19); clock.dateTime = d.toISOString(); } };
  tick();
  setInterval(tick, 1000);
})();
