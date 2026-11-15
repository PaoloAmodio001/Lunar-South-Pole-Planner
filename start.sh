#!/usr/bin/env bash
# Last updated: 2026-11-15
# Avvio unico della piattaforma: sito pubblico (/) e sezione riservata Pianificatori
# di missione (/dashboard, Lunar Mission Control Planner). Tutti gli argomenti sono passati a
# src/ui_web/app.py (es. ./start.sh --no-browser --port 9000).
#
# Il server resta in primo piano: chiudendo questo terminale o premendo Ctrl+C la
# piattaforma si arresta e la pagina nel browser mostrerà "backend non raggiungibile".
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PY="${LUNAR_PYTHON:-$ROOT/.venv/bin/python}"
if [ ! -x "$PY" ]; then
  echo "[ERRORE] Ambiente virtuale non trovato ($PY)." >&2
  echo "         Crealo con:  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

if ! "$PY" -c "import requests, numpy, rasterio, pyproj, matplotlib" 2>/dev/null; then
  echo "[ERRORE] Dipendenze mancanti nel venv. Installa con:" >&2
  echo "         $PY -m pip install -r requirements.txt" >&2
  exit 1
fi

# Nessuna domanda nel terminale: se non esiste ancora un account, la pagina
# MISSION PLANNERS nel browser mostra il modulo "Crea account amministratore".
exec "$PY" src/ui_web/app.py "$@"
