# Last updated: 2026-11-14
"""Radice del progetto e risoluzione dei percorsi relativi (F2).

Regola unica: un percorso relativo presente in una configurazione di missione
si intende relativo a PROJECT_ROOT, mai alla directory corrente del processo.
I percorsi assoluti restano invariati.
"""
from __future__ import annotations

from pathlib import Path

# src/paths.py -> src/ -> radice del progetto
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resolve_project_path(value, root: Path | None = None) -> Path | None:
    """Restituisce un Path assoluto; i relativi vengono ancorati a ``root``.

    ``None`` resta ``None``. Non verifica l'esistenza del file: un input
    mancante deve continuare a produrre l'errore del modulo che lo legge.
    """
    if value is None:
        return None
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (root if root is not None else PROJECT_ROOT) / path
