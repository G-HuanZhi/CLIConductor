"""CLIConductor — FastAPI routes + WebSocket."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from . import worker
from . import session as sess

# ── lifespan ──


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: restore workers from saved sessions.
    Shutdown: kill all child processes."""
    restored = await _restore_workers()
    if restored:
        print(f"[CLIConductor] Restored {len(restored)} workers from session files")
    yield
    await worker.shutdown_all()
    print("[CLIConductor] All workers shut down")


app = FastAPI(title="CLIConductor", lifespan=lifespan)

# ── WS client sets ──
ws_clients: set[WebSocket] = set()     # Dashboard
agent_clients: set[WebSocket] = set()  # Main Agent

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WORKDIRS_DIR = DATA_DIR / "workdirs"
DASHBOARD_FILE = Path(__file__).resolve().parent.parent / "index.html"

# ── startup helpers ──


async def _restore_workers() -> list[str]:
    """Restore workers from saved session JSON files."""
    sessions = sess.load_all_sessions()
    restored_ids: list[str] = []
    for s in sessions:
        w = await worker.restore_worker_from_session(s)
        if w:
            restored_ids.append(w.worker_id)
    return restored_ids


# ── broadcast (dashboard + agent) ──


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


# Install broadcaster into worker module
worker.set_broadcaster(broadcast)


# ── Dashboard ──

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
                worker_id = msg.get("workerId")
                text = msg.get("text")
                if worker_id and text:
                    err = await worker.send_task(worker_id, text, source="user")
                    if err:
                        await broadcast({"type": "error", "message": err})
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(ws)


# ── WebSocket: Main Agent ──

@app.websocket("/ws/agent")
async def ws_agent_endpoint(ws: WebSocket):
    """Dedicated WebSocket endpoint for the main Agent.

    Agent receives all events (worker.spawned, worker.stream,
    worker.result, etc.) and can send task commands:

        {"type": "task", "workerId": "worker-1", "text": "do something"}

    Also supports: spawn, kill, list via WS.
    """
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
                worker_id = msg.get("workerId")
                text = msg.get("text")
                if worker_id and text:
                    err = await worker.send_task(worker_id, text, source="agent")
                    if err:
                        await ws.send_json({"type": "error", "message": err})

            elif msg_type == "spawn":
                name = msg.get("name", "agent-worker")
                model = msg.get("model") or worker.DEFAULT_MODEL
                workdir = WORKDIRS_DIR / name
                workdir.mkdir(parents=True, exist_ok=True)
                w = await worker.create_worker(
                    name, str(workdir),
                    extra_args=["--model", model],
                )
                await ws.send_json({
                    "type": "worker.spawned",
                    "workerId": w.worker_id, "name": w.name,
                    "status": w.status, "workdir": w.workdir, "model": model,
                })

            elif msg_type == "kill":
                worker_id = msg.get("workerId")
                if worker_id:
                    err = await worker.kill_worker(worker_id)
                    if not err:
                        sess.delete_session(worker_id)

            elif msg_type == "list":
                wl = worker.list_workers()
                await ws.send_json({
                    "type": "worker.list",
                    "workers": [
                        {
                            "workerId": w.worker_id, "name": w.name,
                            "status": w.status, "sessionId": w.session_id,
                            "model": w.model,
                            "permissionMode": w.permission_mode,
                        }
                        for w in wl
                    ],
                })

    except WebSocketDisconnect:
        pass
    finally:
        agent_clients.discard(ws)


# ── API routes ──

@app.post("/api/spawn")
async def api_spawn(data: dict):
    name = data.get("name", "default")
    model = data.get("model") or worker.DEFAULT_MODEL
    workdir = WORKDIRS_DIR / name
    workdir.mkdir(parents=True, exist_ok=True)
    w = await worker.create_worker(
        name, str(workdir),
        extra_args=["--model", model],
    )
    return {
        "workerId": w.worker_id, "name": w.name,
        "status": w.status, "workdir": w.workdir, "model": model,
    }


@app.get("/api/models")
async def api_models():
    return {"models": worker.SUPPORTED_MODELS, "default": worker.DEFAULT_MODEL}


@app.get("/api/list")
async def api_list():
    return {
        "workers": [
            {
                "workerId": w.worker_id, "name": w.name, "status": w.status,
                "sessionId": w.session_id, "model": w.model,
                "permissionMode": w.permission_mode, "workdir": w.workdir,
            }
            for w in worker.list_workers()
        ]
    }


@app.post("/api/task")
async def api_task(data: dict):
    worker_id = data.get("workerId")
    text = data.get("text")
    err = await worker.send_task(worker_id, text, source="agent")
    if err:
        return {"error": err}
    return {"workerId": worker_id, "status": "queued"}


@app.post("/api/kill/{worker_id}")
async def api_kill(worker_id: str):
    err = await worker.kill_worker(worker_id)
    if err:
        return {"error": err}
    sess.delete_session(worker_id)
    return {"workerId": worker_id, "status": "killed"}


@app.post("/api/worker/{worker_id}/restart")
async def api_restart(worker_id: str):
    err = await worker.restart_worker(worker_id)
    if err:
        return {"error": err}
    return {"workerId": worker_id, "status": "restarted"}


@app.post("/api/worker/{worker_id}/switch-model")
async def api_switch_model(worker_id: str, data: dict):
    model = data.get("model")
    if not model:
        return {"error": "model is required"}
    err = await worker.respawn_worker(worker_id, ["--model", model])
    if err:
        return {"error": err}
    w = worker.get_worker(worker_id)
    if w:
        w.model = model
    return {"workerId": worker_id, "model": model, "status": "switched"}


@app.post("/api/worker/{worker_id}/switch-mode")
async def api_switch_mode(worker_id: str, data: dict):
    mode = data.get("permissionMode")
    if not mode:
        return {"error": "permissionMode is required"}
    err = await worker.respawn_worker(worker_id, ["--permission-mode", mode])
    if err:
        return {"error": err}
    w = worker.get_worker(worker_id)
    if w:
        w.permission_mode = mode
    return {"workerId": worker_id, "permissionMode": mode, "status": "switched"}


@app.post("/api/worker/{worker_id}/rename")
async def api_rename(worker_id: str, data: dict):
    new_name = data.get("name")
    if not new_name:
        return {"error": "name is required"}
    err = await worker.rename_worker(worker_id, new_name)
    if err:
        return {"error": err}
    return {"workerId": worker_id, "name": new_name, "status": "renamed"}


@app.post("/api/worker/{worker_id}/branch")
async def api_branch(worker_id: str, data: dict):
    name = data.get("name")
    result = await worker.branch_worker(worker_id, name)
    if isinstance(result, str):
        return {"error": result}
    return {
        "workerId": result.worker_id, "name": result.name, "status": "idle",
        "parentWorkerId": worker_id,
    }


@app.post("/api/worker/{worker_id}/interrupt")
async def api_interrupt(worker_id: str):
    err = await worker.interrupt_worker(worker_id)
    if err:
        return {"error": err}
    return {"workerId": worker_id, "status": "interrupted"}
