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
    model: str | None = None
    permission_mode: str | None = None
    _stdout_task: asyncio.Task | None = None


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

    w._stdout_task = asyncio.create_task(_read_stdout(w))
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


async def restart_worker(worker_id: str) -> str | None:
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"

    # 停旧进程
    if w.process:
        try:
            w.process.kill()
        except ProcessLookupError:
            pass

    # 取消旧的 stdout reader
    if w._stdout_task:
        w._stdout_task.cancel()

    # 起新进程（保留 session 以保留对话历史）
    args = [CBC_PATH, "-p", "--output-format", "stream-json", "--input-format", "stream-json", "-y"]
    if w.session_id:
        args.extend(["--resume", w.session_id])

    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    w.process = process
    w.status = "idle"
    # history 由 cbc --resume 恢复，stdout 流会重新输出历史事件

    w._stdout_task = asyncio.create_task(_read_stdout(w))

    await broadcast({
        "type": "worker.restarted",
        "workerId": worker_id,
        "name": w.name,
        "status": "idle",
        "sessionId": w.session_id,
    })
    return None


async def respawn_worker(worker_id: str, extra_args: list[str] | None = None) -> str | None:
    """kill 旧进程后用 --resume + 新参数重启，保留对话历史"""
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"

    session_id = w.session_id

    if w.process:
        try:
            w.process.kill()
        except ProcessLookupError:
            pass
    if w._stdout_task:
        w._stdout_task.cancel()

    args = [CBC_PATH, "-p", "--output-format", "stream-json", "--input-format", "stream-json", "-y"]
    if session_id:
        args.extend(["--resume", session_id])
    if extra_args:
        args.extend(extra_args)

    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    w.process = process
    w.status = "idle"

    w._stdout_task = asyncio.create_task(_read_stdout(w))

    await broadcast({
        "type": "worker.reconfigured",
        "workerId": worker_id,
        "name": w.name,
        "status": "idle",
        "sessionId": session_id,
    })
    return None


async def branch_worker(worker_id: str, name: str | None = None) -> Worker | str:
    """从已有 worker 的会话分支出一个新 worker（新 sessionId + 旧历史）"""
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"
    if not w.session_id:
        return "Worker has no session yet"

    global _next_id
    new_id = f"worker-{_next_id}"
    _next_id += 1
    new_name = name or f"{w.name}-branch"

    args = [CBC_PATH, "-p", "--output-format", "stream-json",
            "--input-format", "stream-json", "-y",
            "--resume", w.session_id, "--fork-session"]
    if w.model:
        args.extend(["--model", w.model])
    if w.permission_mode:
        args.extend(["--permission-mode", w.permission_mode])

    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    new_w = Worker(worker_id=new_id, name=new_name, status="idle", process=process,
                   model=w.model, permission_mode=w.permission_mode)
    workers[new_id] = new_w
    new_w._stdout_task = asyncio.create_task(_read_stdout(new_w))

    await broadcast({
        "type": "worker.spawned",
        "workerId": new_id,
        "name": new_name,
        "status": "idle",
        "parentWorkerId": worker_id,
        "parentSessionId": w.session_id,
    })
    return new_w


async def rename_worker(worker_id: str, new_name: str) -> str | None:
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"

    old_name = w.name
    w.name = new_name
    await broadcast({
        "type": "worker.renamed",
        "workerId": worker_id,
        "oldName": old_name,
        "newName": new_name,
    })
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
            {"workerId": w.worker_id, "name": w.name, "status": w.status,
             "sessionId": w.session_id, "model": w.model, "permissionMode": w.permission_mode}
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


@app.post("/api/worker/{worker_id}/restart")
async def api_restart(worker_id: str):
    err = await restart_worker(worker_id)
    if err:
        return {"error": err}
    return {"workerId": worker_id, "status": "restarted"}


@app.post("/api/worker/{worker_id}/switch-model")
async def api_switch_model(worker_id: str, data: dict):
    model = data.get("model")
    if not model:
        return {"error": "model is required"}
    err = await respawn_worker(worker_id, ["--model", model])
    if err:
        return {"error": err}
    w = workers[worker_id]
    w.model = model
    return {"workerId": worker_id, "model": model, "status": "switched"}


@app.post("/api/worker/{worker_id}/switch-mode")
async def api_switch_mode(worker_id: str, data: dict):
    mode = data.get("permissionMode")
    if not mode:
        return {"error": "permissionMode is required"}
    err = await respawn_worker(worker_id, ["--permission-mode", mode])
    if err:
        return {"error": err}
    w = workers[worker_id]
    w.permission_mode = mode
    return {"workerId": worker_id, "permissionMode": mode, "status": "switched"}


@app.post("/api/worker/{worker_id}/rename")
async def api_rename(worker_id: str, data: dict):
    new_name = data.get("name")
    if not new_name:
        return {"error": "name is required"}
    err = await rename_worker(worker_id, new_name)
    if err:
        return {"error": err}
    return {"workerId": worker_id, "name": new_name, "status": "renamed"}


@app.post("/api/worker/{worker_id}/branch")
async def api_branch(worker_id: str, data: dict):
    name = data.get("name")
    result = await branch_worker(worker_id, name)
    if isinstance(result, str):
        return {"error": result}
    return {"workerId": result.worker_id, "name": result.name, "status": "idle",
            "parentWorkerId": worker_id}


# ────────────────────────────────────────────
# Entry
# ────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8767, log_level="info")
