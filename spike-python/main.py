"""CLIConductor Spike — Python + FastAPI

完整链路：HTTP API → Worker spawn → cbc stdout 流 → WebSocket 广播
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
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
            return

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

DASHBOARD = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>CLIConductor Spike (Python)</title>
<style>
  body{font-family:monospace;background:#111;color:#ff0;padding:20px}
  .worker{border:1px solid #333;margin:10px 0;padding:10px}
  .status{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}
  .idle{background:#888}.running{background:#0f0}.done{background:#0af}.error{background:#f00}
  pre{white-space:pre-wrap;max-height:300px;overflow-y:auto;background:#000;padding:10px}
  input,button{padding:5px;margin:3px;font-family:monospace}
  input{width:300px}
</style></head><body>
<h2>CLIConductor Spike (Python)</h2>
<div id="workers"></div>
<script>
const ws = new WebSocket('ws://' + location.host + '/ws');
ws.onmessage = e => {
  const d = JSON.parse(e.data);
  if (d.type === 'worker.spawned') drawWorker(d);
  else if (d.type === 'worker.stream') append(d.workerId, d.event);
  else if (d.type === 'worker.result') done(d.workerId, d.result);
  else if (d.type === 'worker.status') setStatus(d.workerId, d.status);
  else if (d.type === 'worker.destroyed') remove(d.workerId);
};
function spawn() {
  const name = document.getElementById('newName').value || 'default';
  fetch('/api/spawn', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})});
}
function send(id) {
  const text = document.getElementById('input-'+id).value;
  fetch('/api/task',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({workerId:id,text})});
}
function kill(id) { fetch('/api/kill/'+id,{method:'POST'}); }
function drawWorker(d) {
  const div = document.createElement('div'); div.className = 'worker'; div.id = 'w-'+d.workerId;
  div.innerHTML = '<b>'+d.name+'</b> <span id="st-'+d.workerId+'" class="status idle"></span> ('+d.workerId+') ' +
    '<button onclick="kill(\''+d.workerId+'\')">Kill</button><br>' +
    '<input id="input-'+d.workerId+'" placeholder="Task text..."> ' +
    '<button onclick="send(\''+d.workerId+'\')">Send</button>' +
    '<pre id="log-'+d.workerId+'"></pre>';
  document.getElementById('workers').appendChild(div);
}
function append(id,event) {
  const pre = document.getElementById('log-'+id); if(!pre) return;
  const t = event.type; let line = '';
  if (t === 'assistant') {
    for (const b of event.message?.content||[]) {
      if (b.type === 'text') line += '[TEXT] '+b.text+'\\n';
      if (b.type === 'thinking') line += '[THINK] '+b.thinking.slice(0,120)+'...\\n';
      if (b.type === 'tool_use') line += '[TOOL] '+b.name+'\\n';
    }
  } else if (t === 'system' && event.subtype === 'init') {
    line = '[INIT] session: '+event.session_id+' model: '+event.model+'\\n';
  }
  if (line) pre.textContent += line;
}
function done(id,result) {
  const pre = document.getElementById('log-'+id); if(pre) pre.textContent += '[DONE] '+JSON.stringify(result)+'\\n';
  setStatus(id,'done');
}
function setStatus(id,s) {
  const st = document.getElementById('st-'+id); if(st) {st.className='status '+s; st.title=s;}
}
function remove(id) {const el = document.getElementById('w-'+id); if(el) el.remove();}
</script>
<input id="newName" placeholder="Worker name"><button onclick="spawn()">Spawn</button>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD


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
