"""Session store — persistent, UUID-keyed, independent of Worker lifecycle.

Each session is stored as data/sessions/<id>.json.
The ID format is ses_<16-hex-chars> (e.g. ses_a1b2c3d4e5f67890).
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

SESSION_DIR = Path(__file__).resolve().parent.parent / "data" / "sessions"


def _path(session_id: str) -> Path:
    return SESSION_DIR / f"{session_id}.json"


def _new_id() -> str:
    return "ses_" + secrets.token_hex(8)


@dataclass
class Session:
    id: str
    name: str
    cbc_session_id: str | None = None
    adapter: str = "cbc"   # CLI adapter name, default "cbc" (backward compatible)
    model: str | None = None
    permission_mode: str | None = None
    always_thinking_enabled: bool = False
    effort: str = ""
    max_thinking_tokens: int = 16000
    workdir: str = ""
    history: list[dict] = field(default_factory=list)
    last_result: dict | None = None
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "cbc_session_id": self.cbc_session_id,
            "adapter": self.adapter,
            "model": self.model,
            "permission_mode": self.permission_mode,
            "always_thinking_enabled": self.always_thinking_enabled,
            "effort": self.effort,
            "max_thinking_tokens": self.max_thinking_tokens,
            "workdir": self.workdir,
            "history": self.history,
            "last_result": self.last_result,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ── in-memory cache ──
_cache: dict[str, Session] = {}


# ── CRUD ──

def create(name: str, model: str | None = None,
           permission_mode: str | None = None,
           always_thinking_enabled: bool = False,
           effort: str = "",
           max_thinking_tokens: int = 16000,
           workdir: str = "") -> Session:
    s = Session(
        id=_new_id(),
        name=name,
        model=model,
        permission_mode=permission_mode,
        always_thinking_enabled=always_thinking_enabled,
        effort=effort,
        max_thinking_tokens=max_thinking_tokens,
        workdir=workdir,
    )
    save(s)
    _cache[s.id] = s
    return s


def get(session_id: str) -> Session | None:
    if session_id in _cache:
        return _cache[session_id]
    path = _path(session_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        s = Session(**data)
        _cache[session_id] = s
        return s
    except (json.JSONDecodeError, OSError):
        return None


def save(s: Session):
    s.updated_at = datetime.now().isoformat()
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    _path(s.id).write_text(json.dumps(s.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    _cache[s.id] = s


def delete(session_id: str):
    path = _path(session_id)
    if path.exists():
        path.unlink()
    _cache.pop(session_id, None)


def list_all() -> list[Session]:
    if not SESSION_DIR.exists():
        return []
    sessions: list[Session] = []
    for f in sorted(SESSION_DIR.iterdir()):
        if f.suffix == ".json":
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                # 不要覆盖已缓存的 Session：worker 可能在 _read_stdout 里
                # 已经往内存 history append 了内容但还没 save，这里从磁盘
                # 重新加载会丢掉那部分（dashboard 每 5s 轮询 /api/sessions
                # 就会触发本函数）。已缓存时直接用内存版本。
                sid = data.get("id")
                if sid and sid in _cache:
                    sessions.append(_cache[sid])
                    continue
                s = Session(**data)
                _cache[s.id] = s
                sessions.append(s)
            except (json.JSONDecodeError, OSError):
                pass
    return sessions


def clear_cache():
    _cache.clear()
