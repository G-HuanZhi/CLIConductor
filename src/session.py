"""Session persistence — save/load worker sessions as JSON files.

Future: migrate to SQLite by replacing the three public functions below
with a SessionStore abstraction.
"""

from __future__ import annotations

import json
from pathlib import Path

SESSION_DIR = Path(__file__).resolve().parent.parent / "data" / "sessions"


def _path(worker_id: str) -> Path:
    return SESSION_DIR / f"{worker_id}.json"


def save_session(worker_id: str, session_id: str | None,
                 history: list[dict], model: str | None,
                 permission_mode: str | None, name: str, workdir: str):
    """Persist a worker's session data to disk."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "worker_id": worker_id,
        "name": name,
        "workdir": workdir,
        "session_id": session_id,
        "model": model,
        "permission_mode": permission_mode,
        "history": history,
        "updated_at": __import__("datetime").datetime.now().isoformat(),
    }
    _path(worker_id).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_all_sessions() -> list[dict]:
    """Load all saved sessions from disk.

    Returns list of dicts, each with keys:
      worker_id, name, workdir, session_id, model, permission_mode, history
    """
    if not SESSION_DIR.exists():
        return []
    sessions = []
    for f in sorted(SESSION_DIR.iterdir()):
        if f.suffix == ".json":
            try:
                sessions.append(json.loads(f.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                pass
    return sessions


def delete_session(worker_id: str):
    path = _path(worker_id)
    if path.exists():
        path.unlink()
