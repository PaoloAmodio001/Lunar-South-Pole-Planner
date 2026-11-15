// Last updated: 2026-11-15
// Sessione e raggiungibilità del backend, condivise da dashboard e Lunar Mission Control.
// - Solo nelle pagine della sezione riservata Pianificatori di missione (/dashboard,
//   /mission-control) una risposta 401 o una sessione assente portano al login. La
//   piattaforma pubblica (/, profili, Lunar Mission Control pubblico) non reindirizza mai.
// - Il pulsante "Esci" ([data-auth-only]) compare solo con una sessione valida.
// - Un errore di rete su una richiesta al backend (fetch rifiutata: TypeError, in Firefox
//   "NetworkError when attempting to fetch resource") significa backend non raggiungibile:
//   si emette 'lmc:backend' {available:false} e si interroga /api/health ogni 5 s finché
//   il backend torna; allora si emette 'lmc:backend' {available:true}.
// Nessun token è visibile qui: il cookie di sessione è HttpOnly.
(() => {
  'use strict';
  if (window.lmcSession) return;
  const nativeFetch = window.fetch.bind(window);
  let backendAvailable = null;
  let pollTimer = null;
  let redirecting = false;
  const RESERVED_PAGE = /^\/(dashboard|mission-control)\/?$/.test(location.pathname);

  function showAuthOnly(authenticated) {
    document.querySelectorAll('[data-auth-only]').forEach(node => { node.hidden = !authenticated; });
  }

  function emit(available, detail = {}) {
    const changed = backendAvailable !== available;
    backendAvailable = available;
    if (changed) window.dispatchEvent(new CustomEvent('lmc:backend', { detail: { available, ...detail } }));
  }

  function isOwnApi(input) {
    try {
      const url = new URL(typeof input === 'string' ? input : input.url, location.href);
      return url.origin === location.origin;
    } catch (_) { return false; }
  }

  function goToLogin(expired) {
    if (redirecting || !RESERVED_PAGE) return;
    redirecting = true;
    const next = location.pathname + location.search;
    location.assign(`/login?next=${encodeURIComponent(next)}${expired ? '&expired=1' : ''}`);
  }

  async function probe() {
    try {
      const r = await nativeFetch('/api/health', { cache: 'no-store' });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      emit(true);
      stopPolling();
      showAuthOnly(!!data.authenticated);
      if (data.auth_enabled && !data.authenticated) goToLogin(true);
      return true;
    } catch (_) {
      emit(false, { reason: 'network' });
      return false;
    }
  }

  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(() => { if (!document.hidden) probe(); }, 5000);
  }
  function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

  window.fetch = async (input, init) => {
    let response;
    try {
      response = await nativeFetch(input, init);
    } catch (err) {
      if (isOwnApi(input) && !(err && err.name === 'AbortError')) {
        emit(false, { reason: 'network', message: String(err && err.message || err) });
        startPolling();
        const wrapped = new Error('Backend Lunar Mission Control non raggiungibile');
        wrapped.code = 'backend_unreachable';
        wrapped.cause = err;
        throw wrapped;
      }
      throw err;
    }
    if (isOwnApi(input)) {
      emit(true);
      if (response.status === 401) {
        let code = 'auth_required';
        try { code = (await response.clone().json()).error_code || code; } catch (_) {}
        goToLogin(code === 'session_expired');
      }
    }
    return response;
  };

  window.lmcSession = {
    get backendAvailable() { return backendAvailable; },
    reservedPage: RESERVED_PAGE,
    probe,
    rawFetch: nativeFetch
  };
  document.addEventListener('visibilitychange', () => { if (!document.hidden && backendAvailable === false) probe(); });
})();
