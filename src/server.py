"""CLIConductor — FastAPI routes + WebSocket."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from . import worker
from . import session as sess
from .adapters import get_adapter

# ── logging ──

def _log(msg: str):
    """Print with HH:MM:SS prefix."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


# Comma-separated path prefixes to skip in request logging.
# e.g. CLICONDUCTOR_LOG_SKIP=/api/sessions,/ws
_LOG_SKIP = [
    p.strip()
    for p in os.environ.get("CLICONDUCTOR_LOG_SKIP", "").split(",")
    if p.strip()
]


# ── lifespan ──


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load all saved sessions (don't auto-spawn Workers).
    Shutdown: kill all child processes."""
    sessions = sess.list_all()
    if sessions:
        _log(f"[CLIConductor] Loaded {len(sessions)} sessions from disk")
    yield
    await worker.shutdown_all()
    _log("[CLIConductor] All workers shut down")


app = FastAPI(title="CLIConductor", lifespan=lifespan)

ws_clients: set[WebSocket] = set()
agent_clients: set[WebSocket] = set()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WORKDIRS_DIR = DATA_DIR / "workdirs"
DASHBOARD_FILE = Path(__file__).resolve().parent.parent / "index.html"


async def broadcast(data: dict):
    dead = set()
    for ws in list(ws_clients):
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    ws_clients.difference_update(dead)
    dead_a = set()
    for ws in list(agent_clients):
        try:
            await ws.send_json(data)
        except Exception:
            dead_a.add(ws)
    agent_clients.difference_update(dead_a)


worker.set_broadcaster(broadcast)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every API request with method, path, and status code.

    Set CLICONDUCTOR_LOG_SKIP=comma,separated,path,prefixes to skip specific
    endpoints from being logged.
    """
    path = request.url.path
    response = await call_next(request)
    if not any(path.startswith(p) for p in _LOG_SKIP):
        status = response.status_code
        _log(f"{request.method}  {path}  → {status}")
    return response


# ── helpers ──

def _session_to_api(s: sess.Session):
    """Convert Session to API response dict."""
    w = worker.find_worker_by_session(s.id)
    return {
        "id": s.id,
        "name": s.name,
        "cbcSessionId": s.cbc_session_id,
        "model": s.model or worker.DEFAULT_MODEL,
        "permissionMode": s.permission_mode,
        "alwaysThinkingEnabled": s.always_thinking_enabled,
        "effort": s.effort,
        "maxThinkingTokens": s.max_thinking_tokens,
        "workdir": s.workdir,
        "history": s.history,
        "lastResult": s.last_result,
        "createdAt": s.created_at,
        "updatedAt": s.updated_at,
        "workerStatus": w.status if w else None,
        "workerId": w.worker_id if w else None,
    }


def _check_session_name(name: str) -> str | None:
    """Return error if name is taken, None otherwise."""
    for s in sess.list_all():
        if s.name == name:
            return f"Session name '{name}' already exists"
    return None


def _resolve_workdir(workdir_name: str) -> Path:
    """Resolve a workdir name to a Path under WORKDIRS_DIR, creating it."""
    workdir = WORKDIRS_DIR / workdir_name
    workdir.mkdir(parents=True, exist_ok=True)
    return workdir


def _build_session_params(data: dict) -> dict:
    """Extract session creation parameters from request data, with defaults."""
    name = data.get("name", "default")
    workdir_name = data.get("workdir") or name
    return {
        "name": name,
        "model": data.get("model") or worker.DEFAULT_MODEL,
        "permission_mode": data.get("permissionMode") or None,
        "always_thinking_enabled": data.get("alwaysThinkingEnabled", False),
        "effort": data.get("effort", ""),
        "max_thinking_tokens": data.get("maxThinkingTokens", 16000),
        "workdir": str(_resolve_workdir(workdir_name)),
    }


def _apply_session_updates(s: sess.Session, data: dict):
    """Apply model/mode/thinking/effort fields from data to a Session (in-place)."""
    if "model" in data:
        s.model = data["model"]
    if "permissionMode" in data:
        s.permission_mode = data["permissionMode"] or None
    if "alwaysThinkingEnabled" in data:
        s.always_thinking_enabled = data["alwaysThinkingEnabled"]
    if "effort" in data:
        s.effort = data["effort"]
    if "maxThinkingTokens" in data:
        s.max_thinking_tokens = data["maxThinkingTokens"]


# ── Dashboard & favicon ──

@app.get("/favicon.ico")
async def favicon():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#58a6ff"/><text x="16" y="22" font-size="18" text-anchor="middle" fill="#fff" font-family="monospace" font-weight="bold">C</text></svg>'
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_FILE.read_text(encoding="utf-8")


# ── WebSocket: Dashboard ──

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")
            if msg_type == "user_inject":
                session_id = msg.get("sessionId")
                text = msg.get("text")
                if session_id and text:
                    w = worker.find_worker_by_session(session_id)
                    if w:
                        err = await worker.send_task(w.worker_id, text, source="user")
                        if err:
                            await broadcast({"type": "error", "message": err})
                    else:
                        # auto-spawn worker for this session
                        result = await worker.create_worker(session_id)
                        if isinstance(result, str):
                            await broadcast({"type": "error", "message": result})
                        else:
                            err = await worker.send_task(result.worker_id, text, source="user")
                            if err:
                                await broadcast({"type": "error", "message": err})
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(ws)


# ── WebSocket: Main Agent ──

@app.websocket("/ws/agent")
async def ws_agent_endpoint(ws: WebSocket):
    await ws.accept()
    agent_clients.add(ws)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")

            if msg_type == "task":
                session_id = msg.get("sessionId")
                text = msg.get("text")
                if session_id and text:
                    w = worker.find_worker_by_session(session_id)
                    if not w:
                        result = await worker.create_worker(session_id)
                        if isinstance(result, str):
                            await ws.send_json({"type": "error", "message": result})
                        else:
                            w = result
                    err = await worker.send_task(w.worker_id, text, source="agent")
                    if err:
                        await ws.send_json({"type": "error", "message": err})

            elif msg_type == "spawn":
                params = _build_session_params(msg)
                s = sess.create(**params)
                result = await worker.create_worker(s.id)
                if isinstance(result, str):
                    await ws.send_json({"type": "error", "message": result})
                else:
                    await ws.send_json({
                        "type": "worker.spawned",
                        "sessionId": s.id,
                        "workerId": result.worker_id,
                        "name": s.name,
                        "status": "idle",
                        "model": s.model,
                    })

            elif msg_type == "kill":
                session_id = msg.get("sessionId") or msg.get("workerId")
                w = worker.find_worker_by_session(session_id)
                if w:
                    err = await worker.kill_worker(w.worker_id)
                    if err:
                        await ws.send_json({"type": "error", "message": err})

            elif msg_type == "list":
                sessions = sess.list_all()
                await ws.send_json({
                    "type": "session.list",
                    "sessions": [_session_to_api(s) for s in sessions],
                })

    except WebSocketDisconnect:
        pass
    finally:
        agent_clients.discard(ws)


# ── Session API ──

@app.get("/api/sessions")
async def api_list_sessions():
    """List all sessions (includes worker status if active)."""
    sessions = sess.list_all()
    return {"sessions": [_session_to_api(s) for s in sessions]}


@app.post("/api/sessions")
async def api_create_session(data: dict):
    """Create a new Session (no worker spawned)."""
    params = _build_session_params(data)
    name = params["name"]
    err = _check_session_name(name)
    if err:
        return {"error": err}

    s = sess.create(**params)
    await broadcast({
        "type": "session.created",
        "sessionId": s.id,
        "name": s.name,
    })
    return _session_to_api(s)


@app.get("/api/sessions/{session_id}")
async def api_get_session(session_id: str):
    s = sess.get(session_id)
    if not s:
        return {"error": "Session not found"}
    return _session_to_api(s)


@app.patch("/api/sessions/{session_id}")
async def api_update_session(session_id: str, data: dict):
    """Update session-level settings (model/mode/thinking/effort) without spawning a worker."""
    s = sess.get(session_id)
    if not s:
        return {"error": "Session not found"}
    _apply_session_updates(s, data)
    sess.save(s)
    await broadcast({
        "type": "session.updated",
        "sessionId": s.id,
    })
    return _session_to_api(s)


@app.delete("/api/sessions/{session_id}")
async def api_delete_session(session_id: str):
    """Delete a session and its worker if running."""
    w = worker.find_worker_by_session(session_id)
    if w:
        await worker.kill_worker(w.worker_id)
    sess.delete(session_id)
    await broadcast({
        "type": "session.deleted",
        "sessionId": session_id,
    })
    return {"sessionId": session_id, "status": "deleted"}


@app.get("/api/models")
async def api_models():
    return {"models": worker.SUPPORTED_MODELS, "default": worker.DEFAULT_MODEL}


@app.get("/api/adapter/config")
async def api_adapter_config():
    """Return default adapter configuration (models, effort values, permission modes).
    Frontend uses this to dynamically render selects.
    """
    a = get_adapter("cbc")
    return {
        "models": a.supported_models,
        "defaultModel": a.default_model,
        "effortValues": list(a.effort_values),
        "permissionModes": a.permission_modes,
    }


# ── Spawn (create worker for a session) ──

@app.post("/api/spawn")
async def api_spawn(data: dict):
    """Spawn a Worker for a Session.

    If session_id is provided, use that Session.
    Otherwise, create a new Session first.
    """
    session_id = data.get("sessionId")
    if session_id:
        s = sess.get(session_id)
        if not s:
            return {"error": f"Session {session_id} not found"}
        # 杀掉已有的 worker（避免多个 worker 跑同一 session）
        existing = worker.find_worker_by_session(session_id)
        if existing:
            await worker.kill_worker(existing.worker_id)
        # apply settings from request if provided
        _apply_session_updates(s, data)
        sess.save(s)
    else:
        params = _build_session_params(data)
        name = params["name"]
        err_name = _check_session_name(name)
        if err_name:
            return {"error": err_name}
        s = sess.create(**params)
        session_id = s.id

    result = await worker.create_worker(session_id)
    if isinstance(result, str):
        return {"error": result}

    w = result
    return {
        "workerId": w.worker_id,
        "sessionId": session_id,
        "name": s.name,
        "status": w.status,
        "model": s.model or worker.DEFAULT_MODEL,
    }


@app.post("/api/task")
async def api_task(data: dict):
    """Send a task to a Worker by worker_id or session_id.

    Auto-spawns a worker (with --resume if session has cbc_session_id)
    if the session exists but has no live worker — consistent with the
    WS /ws and /ws/agent endpoints. Worker death is common (server restart,
    cbc crash), so we recover transparently instead of erroring.
    """
    worker_id = data.get("workerId")
    session_id = data.get("sessionId")

    # Resolve worker_id from session_id
    if not worker_id and session_id:
        w = worker.find_worker_by_session(session_id)
        if w:
            worker_id = w.worker_id

    # No worker found — try to auto-spawn for this session
    if not worker_id and session_id:
        s = sess.get(session_id)
        if not s:
            return {"error": f"Session {session_id} not found"}
        result = await worker.create_worker(session_id)
        if isinstance(result, str):
            return {"error": f"Worker auto-spawn failed: {result}"}
        worker_id = result.worker_id
        await broadcast({
            "type": "worker.spawned",
            "workerId": worker_id,
            "sessionId": session_id,
            "name": s.name,
            "status": "idle",
            "model": s.model or worker.DEFAULT_MODEL,
            "reason": "auto-spawned by /api/task",
        })

    if not worker_id:
        return {"error": "workerId or sessionId required"}

    text = data.get("text")
    if not text:
        return {"error": "text is required"}

    err = await worker.send_task(worker_id, text, source="agent")
    if err:
        # Worker died between resolve and send (race). Kill the corpse,
        # auto-spawn+resume a fresh one, retry the task once.
        if session_id and err in ("Worker not found", "Worker process dead"):
            old = worker.find_worker_by_session(session_id)
            if old:
                await worker.kill_worker(old.worker_id)
            s = sess.get(session_id)
            if s:
                result = await worker.create_worker(session_id)
                if not isinstance(result, str):
                    worker_id = result.worker_id
                    err = await worker.send_task(worker_id, text, source="agent")
        if err:
            return {"error": err}

    w = worker.get_worker(worker_id)
    return {
        "workerId": worker_id,
        "sessionId": w.session_id if w else session_id,
        "status": "queued",
    }


@app.post("/api/kill/{worker_id}")
async def api_kill(worker_id: str):
    """Kill a Worker process. Does NOT delete the Session."""
    err = await worker.kill_worker(worker_id)
    if err:
        return {"error": err}
    return {"workerId": worker_id, "status": "killed"}


@app.get("/api/list")
async def api_list():
    """List running workers (not sessions)."""
    return {
        "workers": [
            {
                "workerId": w.worker_id,
                "sessionId": w.session_id,
                "status": w.status,
            }
            for w in worker.list_workers()
        ]
    }


# ── Worker actions ──

@app.post("/api/worker/{worker_id}/restart")
async def api_restart(worker_id: str):
    err = await worker.restart_worker(worker_id)
    if err:
        return {"error": err}
    return {"workerId": worker_id, "status": "restarted"}


@app.post("/api/worker/{worker_id}/settings")
async def api_worker_settings(worker_id: str, data: dict):
    """Apply model/mode/thinking settings to a session and respawn the worker once.

    This endpoint consolidates the deprecated switch-model, switch-mode, and
    switch-thinking endpoints.  Accepted fields:

        model                  — model name (str or None)
        permissionMode         — permission mode (str or None)
        alwaysThinkingEnabled  — enable thinking (bool)
        effort                 — effort level (low/medium/high/xhigh)
    """
    w = worker.get_worker(worker_id)
    if not w:
        return {"error": "Worker not found"}
    s = sess.get(w.session_id)
    if not s:
        return {"error": "Session not found"}

    # update session fields first …
    _apply_session_updates(s, data)
    sess.save(s)

    # … then build extra args from the updated session and respawn once
    extra_args: list[str] = []
    if "model" in data:
        extra_args.extend(["--model", data["model"]])
    if "permissionMode" in data:
        extra_args.extend(["--permission-mode", data["permissionMode"] or ""])
    extra_args.extend(worker.effort_args(s))

    err = await worker.respawn_worker(worker_id, extra_args if extra_args else None)
    if err:
        return {"error": err}

    return {
        "workerId": worker_id,
        "sessionId": s.id,
        "model": s.model,
        "permissionMode": s.permission_mode,
        "alwaysThinkingEnabled": s.always_thinking_enabled,
        "effort": s.effort,
        "status": "settings applied",
    }


# ─── Deprecated endpoints (kept for backward compatibility) ───

@app.post("/api/worker/{worker_id}/switch-model")
async def api_switch_model(worker_id: str, data: dict):
    """Deprecated — use POST /api/worker/{worker_id}/settings instead."""
    model = data.get("model")
    if not model:
        return {"error": "model is required"}
    err = await worker.respawn_worker(worker_id, ["--model", model])
    if err:
        return {"error": err}
    # update session model
    w = worker.get_worker(worker_id)
    if w:
        s = sess.get(w.session_id)
        if s:
            s.model = model
            sess.save(s)
    return {"workerId": worker_id, "model": model, "status": "switched"}


@app.post("/api/worker/{worker_id}/switch-mode")
async def api_switch_mode(worker_id: str, data: dict):
    """Deprecated — use POST /api/worker/{worker_id}/settings instead."""
    mode = data.get("permissionMode")
    if not mode:
        return {"error": "permissionMode is required"}
    err = await worker.respawn_worker(worker_id, ["--permission-mode", mode])
    if err:
        return {"error": err}
    w = worker.get_worker(worker_id)
    if w:
        s = sess.get(w.session_id)
        if s:
            s.permission_mode = mode
            sess.save(s)
    return {"workerId": worker_id, "permissionMode": mode, "status": "switched"}


@app.post("/api/worker/{worker_id}/switch-thinking")
async def api_switch_thinking(worker_id: str, data: dict):
    """Deprecated — use POST /api/worker/{worker_id}/settings instead."""
    w = worker.get_worker(worker_id)
    if not w:
        return {"error": "Worker not found"}
    s = sess.get(w.session_id)
    if not s:
        return {"error": "Session not found"}
    _apply_session_updates(s, data)
    sess.save(s)
    err = await worker.respawn_worker(worker_id)
    if err:
        return {"error": err}
    return {
        "workerId": worker_id,
        "alwaysThinkingEnabled": s.always_thinking_enabled,
        "effort": s.effort,
        "maxThinkingTokens": s.max_thinking_tokens,
        "status": "switched",
    }


@app.post("/api/worker/{worker_id}/rename")
async def api_rename(worker_id: str, data: dict):
    new_name = data.get("name")
    if not new_name:
        return {"error": "name is required"}

    err = _check_session_name(new_name)
    if err:
        return {"error": err}

    # resolve session: prefer live worker, fallback to sessionId in body
    session_id = None
    w = worker.get_worker(worker_id)
    if w:
        session_id = w.session_id
    else:
        session_id = data.get("sessionId") or worker_id

    s = sess.get(session_id)
    if not s:
        return {"error": "Session not found"}

    old_name = s.name
    s.name = new_name
    sess.save(s)
    await broadcast({
        "type": "session.renamed",
        "sessionId": s.id,
        "oldName": old_name,
        "newName": new_name,
    })
    return {"sessionId": s.id, "name": new_name, "status": "renamed"}


@app.post("/api/worker/{worker_id}/branch")
async def api_branch(worker_id: str, data: dict):
    w = worker.get_worker(worker_id)
    if not w:
        return {"error": "Worker not found"}

    orig = sess.get(w.session_id)
    if not orig or not orig.cbc_session_id:
        return {"error": "Session not ready for branching"}

    name = data.get("name") or f"{orig.name}-branch"
    new_session = sess.create(name, model=orig.model,
                              permission_mode=orig.permission_mode,
                              always_thinking_enabled=orig.always_thinking_enabled,
                              effort=orig.effort,
                              max_thinking_tokens=orig.max_thinking_tokens,
                              workdir=orig.workdir)

    result = await worker.branch_worker(worker_id, new_session.id)
    if isinstance(result, str):
        sess.delete(new_session.id)
        return {"error": result}

    return {
        "workerId": result.worker_id,
        "sessionId": new_session.id,
        "name": new_session.name,
        "status": "idle",
        "parentSessionId": w.session_id,
    }


@app.post("/api/worker/{worker_id}/interrupt")
async def api_interrupt(worker_id: str):
    err = await worker.interrupt_worker(worker_id)
    if err:
        return {"error": err}
    return {"workerId": worker_id, "status": "interrupted"}


@app.post("/api/worker/{worker_id}/takeover")
async def api_takeover(worker_id: str):
    import subprocess

    w = worker.get_worker(worker_id)
    if not w:
        return {"error": "Worker not found"}
    s = sess.get(w.session_id)
    if not s:
        return {"error": "Session not found"}
    if not s.cbc_session_id:
        return {"error": "Worker has no cbc session yet"}

    # check adapter supports takeover
    adapter_cmd = w.adapter.takeover_command(s)
    if not adapter_cmd:
        return {"error": f"Adapter '{w.adapter.name}' does not support takeover"}

    # restart worker to free session, then mark held
    err = await worker.restart_worker(worker_id)
    if err:
        return {"error": err}

    w.status = "held"
    await broadcast({
        "type": "worker.status",
        "sessionId": w.session_id,
        "workerId": w.worker_id,
        "status": "held",
    })

    try:
        proc = subprocess.Popen(
            ["powershell.exe", "-NoExit", "-Command",
             " ".join(adapter_cmd)],
            cwd=s.workdir,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        w.takeover_pid = proc.pid
    except FileNotFoundError:
        return {"error": "powershell.exe not found"}
    except OSError as e:
        return {"error": str(e)}

    return {
        "workerId": worker_id,
        "sessionId": w.session_id,
        "cbcSessionId": s.cbc_session_id,
        "takeoverPid": w.takeover_pid,
        "status": "takeover started",
    }

# ── Static files (CSS, JS) ──
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
