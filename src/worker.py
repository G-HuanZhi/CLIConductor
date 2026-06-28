"""Worker — lifecycle management for cbc child processes."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime

from . import session as _sess

CBC_PATH = r"D:\node_npm\node_global\cbc.cmd"
DEFAULT_MODEL = "deepseek-v4-flash"

# Supported models (from `cbc --help` --model flag, manual list)
SUPPORTED_MODELS = [
    "glm-5.2", "glm-5.1", "glm-5.0", "glm-5.0-turbo", "glm-5v-turbo", "glm-4.7",
    "minimax-m3", "minimax-m2.7",
    "kimi-k2.7", "kimi-k2.6", "kimi-k2.5",
    "hy3-preview",
    "deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v3-2-volc",
    "custom-local:deepseek-v4-pro",
]


@dataclass
class Worker:
    worker_id: str
    name: str
    workdir: str
    status: str = "idle"  # idle | running | done | error
    process: asyncio.subprocess.Process | None = None
    session_id: str | None = None
    history: list[dict] = field(default_factory=list)
    model: str | None = None
    permission_mode: str | None = None
    last_result: dict | None = None  # {status, result, sessionId, timestamp}
    _stdout_task: asyncio.Task | None = None
    _consume_task: asyncio.Task | None = None
    queue: asyncio.Queue | None = None


workers: dict[str, Worker] = {}

# ── broadcast hook (set by server.py so worker.py doesn't depend on WebSocket) ──
_broadcast: callable = lambda data: None  # no-op default


def set_broadcaster(fn: callable):
    global _broadcast
    _broadcast = fn


# ── base spawn args ──

def _base_args() -> list[str]:
    return [CBC_PATH, "-p", "--output-format", "stream-json",
            "--input-format", "stream-json", "-y"]


async def _read_stdout(w: Worker):
    """逐行读取 cbc stdout → 解析事件 → 广播"""
    async for line in w.process.stdout:
        line_str = line.decode("utf-8", errors="replace").rstrip("\n")
        if not line_str:
            continue
        try:
            event = json.loads(line_str)
        except json.JSONDecodeError:
            continue

        t = event.get("type")

        # 提取 session_id + model
        if t == "system" and event.get("subtype") == "init":
            w.session_id = event.get("session_id")
            if event.get("model") and not w.model:
                w.model = event.get("model")

        # 收集对话历史
        if t == "assistant":
            for b in event.get("message", {}).get("content", []) or []:
                if b.get("type") == "text":
                    w.history.append({"role": "assistant", "content": b["text"]})
                elif b.get("type") == "thinking":
                    w.history.append({"role": "thinking", "content": b["thinking"]})
                elif b.get("type") == "tool_use":
                    w.history.append({
                        "role": "tool",
                        "content": f"{b['name']}({json.dumps(b.get('input', {}))})",
                    })

        # 任务完成 → 保存 session + lastResult + 通知 consumer 继续
        if t == "result":
            is_error = event.get("is_error", False)
            w.status = "error" if is_error else "done"
            w.last_result = {
                "status": w.status,
                "result": event.get("result"),
                "sessionId": w.session_id,
                "timestamp": datetime.now().isoformat(),
            }
            _sess.save_session(w.worker_id, w.session_id, w.history,
                               w.model, w.permission_mode, w.name, w.workdir,
                               last_result=w.last_result)
            await _broadcast({
                "type": "worker.result",
                "workerId": w.worker_id,
                "status": w.status,
                "result": event.get("result"),
                "sessionId": w.session_id,
                "history": w.history,
            })
            # 重置状态为 idle，等待下一条队列消息
            w.status = "idle"
            continue

        await _broadcast({
            "type": "worker.stream",
            "workerId": w.worker_id,
            "event": event,
        })


async def _consumer(w: Worker):
    """从队列取消息 → 写入 stdin，一次一条"""
    while True:
        item = await w.queue.get()
        if item is None:
            break  # shutdown signal

        text = item["text"]
        source = item.get("source", "agent")  # agent | user

        if w.process is None or w.process.returncode is not None:
            continue

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

        await _broadcast({
            "type": "worker.status",
            "workerId": w.worker_id,
            "status": "running",
            "source": source,
        })


# ── lifecycle ──

async def _next_worker_id() -> str:
    """返回最小的未占用 worker ID（复用被 kill 释放的序号）"""
    used: set[int] = set()
    for wid in workers:
        try:
            used.add(int(wid.rsplit("-", 1)[-1]))
        except (ValueError, IndexError):
            pass
    n = 1
    while n in used:
        n += 1
    return f"worker-{n}"


async def create_worker(name: str, workdir: str,
                        extra_args: list[str] | None = None) -> Worker:
    worker_id = await _next_worker_id()

    process = await asyncio.create_subprocess_exec(
        *_base_args(), *(extra_args or []),
        stdout=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=workdir,
    )

    w = Worker(worker_id=worker_id, name=name, workdir=workdir,
               status="idle", process=process, queue=asyncio.Queue())
    workers[worker_id] = w

    w._stdout_task = asyncio.create_task(_read_stdout(w))
    w._consume_task = asyncio.create_task(_consumer(w))

    await _broadcast({
        "type": "worker.spawned",
        "workerId": worker_id,
        "name": name,
        "status": "idle",
        "workdir": workdir,
    })
    return w


async def kill_worker(worker_id: str) -> str | None:
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"

    # stop consumer
    if w._consume_task:
        w._consume_task.cancel()
    if w._stdout_task:
        w._stdout_task.cancel()

    if w.process:
        try:
            w.process.kill()
        except ProcessLookupError:
            pass

    workers.pop(worker_id, None)
    await _broadcast({"type": "worker.destroyed", "workerId": worker_id})
    return None


async def _spawn_process(extra_args: list[str] | None = None,
                         session_id: str | None = None,
                         workdir: str | None = None) -> asyncio.subprocess.Process:
    args = _base_args()
    if session_id:
        args.extend(["--resume", session_id])
    if extra_args:
        args.extend(extra_args)
    return await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=workdir,
    )


async def _restart_tasks(w: Worker):
    """停旧任务，起新 consumer + stdout reader"""
    if w._stdout_task:
        w._stdout_task.cancel()
    if w._consume_task:
        w._consume_task.cancel()

    # 新进程需要新 queue（旧 queue 的消息已无效）
    w.queue = asyncio.Queue()
    w._stdout_task = asyncio.create_task(_read_stdout(w))
    w._consume_task = asyncio.create_task(_consumer(w))


async def restart_worker(worker_id: str) -> str | None:
    """不改变配置，单纯重启 cbc 进程"""
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"

    if w.process:
        try:
            w.process.kill()
        except ProcessLookupError:
            pass

    w.process = await _spawn_process(session_id=w.session_id, workdir=w.workdir)
    w.status = "idle"
    await _restart_tasks(w)

    await _broadcast({
        "type": "worker.restarted",
        "workerId": worker_id,
        "name": w.name,
        "status": "idle",
        "sessionId": w.session_id,
    })
    return None


async def respawn_worker(worker_id: str, extra_args: list[str] | None = None) -> str | None:
    """kill + --resume + 新参数，保留对话历史（用于 /model, /mode 切换）"""
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"

    session_id = w.session_id
    if w.process:
        try:
            w.process.kill()
        except ProcessLookupError:
            pass

    w.process = await _spawn_process(extra_args=extra_args,
                                     session_id=session_id,
                                     workdir=w.workdir)
    w.status = "idle"
    await _restart_tasks(w)

    await _broadcast({
        "type": "worker.reconfigured",
        "workerId": worker_id,
        "name": w.name,
        "status": "idle",
        "sessionId": session_id,
    })
    return None


async def branch_worker(worker_id: str, name: str | None = None) -> Worker | str:
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"
    if not w.session_id:
        return "Worker has no session yet"

    new_id = await _next_worker_id()
    new_name = name or f"{w.name}-branch"

    extra_args = ["--resume", w.session_id, "--fork-session"]
    if w.model:
        extra_args.extend(["--model", w.model])
    if w.permission_mode:
        extra_args.extend(["--permission-mode", w.permission_mode])

    process = await asyncio.create_subprocess_exec(
        *_base_args(), *extra_args,
        stdout=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=w.workdir,
    )

    new_w = Worker(worker_id=new_id, name=new_name, workdir=w.workdir,
                   status="idle", process=process,
                   model=w.model, permission_mode=w.permission_mode,
                   queue=asyncio.Queue())
    workers[new_id] = new_w
    new_w._stdout_task = asyncio.create_task(_read_stdout(new_w))
    new_w._consume_task = asyncio.create_task(_consumer(new_w))

    await _broadcast({
        "type": "worker.spawned",
        "workerId": new_id,
        "name": new_name,
        "status": "idle",
        "parentWorkerId": worker_id,
        "parentSessionId": w.session_id,
        "workdir": w.workdir,
    })
    return new_w


async def rename_worker(worker_id: str, new_name: str) -> str | None:
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"
    old_name = w.name
    w.name = new_name
    await _broadcast({
        "type": "worker.renamed",
        "workerId": worker_id,
        "oldName": old_name,
        "newName": new_name,
    })
    return None


async def interrupt_worker(worker_id: str) -> str | None:
    """中断 Worker 当前任务：kill 当前 cbc 进程 + --resume 重启，保留历史"""
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"
    if w.status != "running":
        return "Worker is not running"

    return await restart_worker(worker_id)


async def send_task(worker_id: str, text: str, source: str = "agent") -> str | None:
    """向 Worker 队列推一条消息"""
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"
    if w.status == "held":
        return "Worker is held (takeover mode). Restart first."
    if w.process is None or w.process.returncode is not None:
        return "Worker process dead"
    if w.queue is None:
        return "Worker queue not ready"

    await w.queue.put({"text": text, "source": source})
    return None


def get_worker(worker_id: str) -> Worker | None:
    return workers.get(worker_id)


def list_workers() -> list[Worker]:
    return list(workers.values())


# ── restore & shutdown (for server lifecycle) ──


async def restore_worker_from_session(session: dict) -> Worker | None:
    """Restore a worker from saved session data.

    *session* dict keys: worker_id, name, workdir, session_id,
    model, permission_mode, history.
    """
    worker_id = session.get("worker_id")
    name = session.get("name", "restored")
    workdir = session.get("workdir", "")
    session_id = session.get("session_id")
    model = session.get("model") or DEFAULT_MODEL
    permission_mode = session.get("permission_mode")
    history = session.get("history", [])
    last_result = session.get("last_result")

    if not session_id:
        return None  # no session to resume

    extra_args = ["--model", model]
    if permission_mode:
        extra_args.extend(["--permission-mode", permission_mode])

    try:
        process = await asyncio.create_subprocess_exec(
            *_base_args(), *(extra_args or []),
            "--resume", session_id,
            stdout=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=workdir or None,
        )
    except FileNotFoundError:
        return None
    except OSError:
        return None

    w = Worker(worker_id=worker_id, name=name, workdir=workdir,
               status="idle", process=process,
               session_id=session_id, model=model,
               permission_mode=permission_mode,
               last_result=last_result,
               history=history.copy(), queue=asyncio.Queue())
    workers[worker_id] = w

    w._stdout_task = asyncio.create_task(_read_stdout(w))
    w._consume_task = asyncio.create_task(_consumer(w))

    await _broadcast({
        "type": "worker.restored",
        "workerId": worker_id,
        "name": name,
        "status": "idle",
        "sessionId": session_id,
        "model": model,
        "workdir": workdir,
    })
    return w


async def shutdown_all():
    """Kill all child processes and cancel tasks."""
    ids = list(workers.keys())
    for wid in ids:
        w = workers.get(wid)
        if not w:
            continue
        # cancel consumer first
        if w._consume_task:
            w._consume_task.cancel()
        if w._stdout_task:
            w._stdout_task.cancel()
        # kill process
        if w.process:
            try:
                w.process.kill()
            except ProcessLookupError:
                pass
    workers.clear()
