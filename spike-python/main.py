"""CLIConductor Spike — Python + FastAPI

完整链路：HTTP API → Worker spawn → cbc stdout 流 → WebSocket 广播
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pathlib import Path

from fastapi.responses import HTMLResponse

app = FastAPI()

# ────────────────────────────────────────────
# Worker
# ────────────────────────────────────────────

CBC_PATH = r"D:\node_npm\node_global\cbc.cmd"


@dataclass
class Worker:
    worker_id: str
    name: str
    status: str = "idle"  # idle | running | done | error
    process: asyncio.subprocess.Process | None = None
    session_id: str | None = None
    history: list[dict] = field(default_factory=list)


workers: dict[str, Worker] = {}
_next_id = 1


async def create_worker(name: str) -> Worker:
    global _next_id
    worker_id = f"worker-{_next_id}"
    _next_id += 1

    process = await asyncio.create_subprocess_exec(
        CBC_PATH,
        "-p",
        "--output-format", "stream-json",
        "--input-format", "stream-json",
        "-y",
        stdout=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    w = Worker(worker_id=worker_id, name=name, status="idle", process=process)
    workers[worker_id] = w
    await broadcast({"type": "worker.spawned", "workerId": worker_id, "name": name, "status": "idle"})

    asyncio.create_task(_read_stdout(w))
    return w


async def _read_stdout(w: Worker):
    """逐行读取 cbc stdout，解析事件，广播"""
    async for line in w.process.stdout:
        line_str = line.decode("utf-8", errors="replace").rstrip("\n")
        if not line_str:
            continue
        try:
            event = json.loads(line_str)
        except json.JSONDecodeError:
            continue

        t = event.get("type")

        # 提取 session_id
        if t == "system" and event.get("subtype") == "init":
            w.session_id = event.get("session_id")

        # 收集对话历史
        if t == "assistant":
            for b in event.get("message", {}).get("content", []) or []:
                if b.get("type") == "text":
                    w.history.append({"role": "assistant", "content": b["text"]})
                elif b.get("type") == "thinking":
                    w.history.append({"role": "thinking", "content": b["thinking"]})
                elif b.get("type") == "tool_use":
                    w.history.append({"role": "tool", "content": f"{b['name']}({json.dumps(b.get('input', {}))})"})

        # 任务完成
        if t == "result":
            w.status = "error" if event.get("is_error") else "done"
            await broadcast({
                "type": "worker.result",
                "workerId": w.worker_id,
                "status": w.status,
                "result": event.get("result"),
                "sessionId": w.session_id,
                "history": w.history,
            })
            # 重置为 idle，准备下一轮（继续循环等待 stdin）
            w.status = "idle"
            continue

        await broadcast({"type": "worker.stream", "workerId": w.worker_id, "event": event})


async def send_task(worker_id: str, text: str) -> str | None:
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"
    if not w.process or w.process.returncode is not None:
        return "Worker process dead"

    w.status = "running"
    w.history.append({"role": "user", "content": text})

    msg = json.dumps({
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": text}],
        },
    })
    w.process.stdin.write((msg + "\n").encode())
    await w.process.stdin.drain()

    await broadcast({"type": "worker.status", "workerId": worker_id, "status": "running"})
    return None


async def kill_worker(worker_id: str) -> str | None:
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"
    if w.process:
        w.process.kill()
    workers.pop(worker_id, None)
    await broadcast({"type": "worker.destroyed", "workerId": worker_id})
    return None


# ────────────────────────────────────────────
# WebSocket
# ────────────────────────────────────────────

ws_clients: set[WebSocket] = set()


async def broadcast(data: dict):
    dead = set()
    for ws in ws_clients:
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    ws_clients.difference_update(dead)


# ────────────────────────────────────────────
# HTTP Routes
# ────────────────────────────────────────────

DASHBOARD_FILE = Path(__file__).parent / "index.html"


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_FILE.read_text(encoding="utf-8")


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(ws)


@app.post("/api/spawn")
async def api_spawn(data: dict):
    name = data.get("name", "default")
    w = await create_worker(name)
    return {"workerId": w.worker_id, "name": w.name, "status": w.status}


@app.get("/api/list")
async def api_list():
    return {
        "workers": [
            {"workerId": w.worker_id, "name": w.name, "status": w.status, "sessionId": w.session_id}
            for w in workers.values()
        ]
    }


@app.post("/api/task")
async def api_task(data: dict):
    worker_id = data.get("workerId")
    text = data.get("text")
    err = await send_task(worker_id, text)
    if err:
        return {"error": err}
    return {"workerId": worker_id, "status": "running"}


@app.post("/api/kill/{worker_id}")
async def api_kill(worker_id: str):
    err = await kill_worker(worker_id)
    if err:
        return {"error": err}
    return {"workerId": worker_id, "status": "killed"}


# ────────────────────────────────────────────
# Entry
# ────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8767, log_level="info")
