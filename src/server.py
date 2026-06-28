"""CLIConductor — FastAPI routes + WebSocket."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from . import worker
from . import session as sess

app = FastAPI(title="CLIConductor")

# ── WebSocket ──
ws_clients: set[WebSocket] = set()
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WORKDIRS_DIR = DATA_DIR / "workdirs"
DASHBOARD_FILE = Path(__file__).resolve().parent.parent / "index.html"


async def broadcast(data: dict):
    dead = set()
    for ws in ws_clients:
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    ws_clients.difference_update(dead)


# Install broadcaster into worker module
worker.set_broadcaster(broadcast)


# ── Dashboard ──

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_FILE.read_text(encoding="utf-8")


# ── WebSocket ──

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


# ── API routes ──

@app.post("/api/spawn")
async def api_spawn(data: dict):
    name = data.get("name", "default")
    workdir = WORKDIRS_DIR / name
    workdir.mkdir(parents=True, exist_ok=True)
    w = await worker.create_worker(name, str(workdir))
    return {"workerId": w.worker_id, "name": w.name, "status": w.status, "workdir": w.workdir}


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
