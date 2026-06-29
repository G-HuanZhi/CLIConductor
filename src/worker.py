"""Worker — runtime cbc process management.

Worker is ephemeral: kill it, the Worker is gone.
All persistent data lives in Session (session.py).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from . import session as _sess

CBC_PATH = r"D:\node_npm\node_global\cbc.cmd"
DEFAULT_MODEL = "deepseek-v4-flash"

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
    session_id: str           # Session UUID (ses_<hex>)
    status: str = "idle"      # idle | running | held | error
    process: asyncio.subprocess.Process | None = None
    _stdout_task: asyncio.Task | None = None
    _consume_task: asyncio.Task | None = None
    queue: asyncio.Queue | None = None
    _replaying: bool = False  # true during cbc --resume event replay


workers: dict[str, Worker] = {}

_broadcast: callable = None


def set_broadcaster(fn: callable):
    global _broadcast
    _broadcast = fn


async def _bcast(data: dict):
    if _broadcast is not None:
        r = _broadcast(data)
        if hasattr(r, "__await__"):
            await r


# ── helpers ──

def _base_args() -> list[str]:
    return [CBC_PATH, "-p", "--output-format", "stream-json",
            "--input-format", "stream-json", "-y"]


async def _next_worker_id() -> str:
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


def _session(w: Worker) -> _sess.Session | None:
    return _sess.get(w.session_id)


# ── stdout reader ──

async def _read_stdout(w: Worker):
    async for line in w.process.stdout:
        line_str = line.decode("utf-8", errors="replace").rstrip("\n")
        if not line_str:
            continue
        try:
            event = json.loads(line_str)
        except json.JSONDecodeError:
            continue

        t = event.get("type")

        # 提取 cbc_session_id + model 并写入 Session
        if t == "system" and event.get("subtype") == "init":
            s = _session(w)
            if s:
                cbc_sid = event.get("session_id")
                if cbc_sid:
                    s.cbc_session_id = cbc_sid
                if event.get("model") and not s.model:
                    s.model = event.get("model")
                _sess.save(s)

        # 收集对话历史（replay 期间跳过，避免重复追加）
        if t == "assistant" and not w._replaying:
            s = _session(w)
            if s:
                for b in event.get("message", {}).get("content", []) or []:
                    if b.get("type") == "text":
                        s.history.append({"role": "assistant", "content": b["text"]})
                    elif b.get("type") == "thinking":
                        s.history.append({"role": "thinking", "content": b["thinking"]})
                    elif b.get("type") == "tool_use":
                        s.history.append({
                            "role": "tool",
                            "content": f"{b['name']}({json.dumps(b.get('input', {}))})",
                        })

        # 任务完成 → 保存 Session + last_result
        if t == "result":
            s = _session(w)
            is_error = event.get("is_error", False)
            w.status = "error" if is_error else "done"

            # replay 结束：标记完成，不保存（history 无变化）
            if w._replaying:
                w._replaying = False
                w.status = "idle"
                continue

            if s:
                s.last_result = {
                    "status": w.status,
                    "result": event.get("result"),
                    "cbc_session_id": s.cbc_session_id,
                    "timestamp": __import__("datetime").datetime.now().isoformat(),
                }
                # cbc 有时只在 result 事件里给出最终文本（不在 assistant 事件里），
                # 这种情况下 history 会缺最后一条 assistant 消息，导致 dashboard 和
                # QQ bridge 都拿不到回复。这里补一下，避免重复。
                result_text = event.get("result")
                if isinstance(result_text, str) and result_text.strip():
                    last = s.history[-1] if s.history else None
                    if not (last and last.get("role") == "assistant"
                            and last.get("content") == result_text):
                        s.history.append({"role": "assistant", "content": result_text})
                _sess.save(s)

            await _bcast({
                "type": "worker.result",
                "workerId": w.worker_id,
                "sessionId": w.session_id,
                "status": w.status,
                "result": event.get("result"),
            })
            w.status = "idle"
            continue

        await _bcast({
            "type": "worker.stream",
            "workerId": w.worker_id,
            "sessionId": w.session_id,
            "event": event,
        })

    # stdout EOF — 进程退出了
    w.status = "error"
    code = w.process.returncode if w.process else "unknown"
    print(f"[Worker {w.worker_id}] cbc 进程退出，返回码 {code}")
    await _bcast({
        "type": "worker.crashed",
        "workerId": w.worker_id,
        "sessionId": w.session_id,
        "returncode": code,
    })


# ── consumer ──

async def _consumer(w: Worker):
    while True:
        item = await w.queue.get()
        if item is None:
            break

        text = item["text"]
        source = item.get("source", "agent")

        # 先把用户消息记进 history 并落盘——不管进程死活都该记，
        # 否则 worker 崩溃 / server 重启会丢用户消息
        s = _session(w)
        if s:
            s.history.append({"role": "user", "content": text})
            _sess.save(s)

        if w.process is None or w.process.returncode is not None:
            # 进程已死，别静默丢任务——记到 last_result 并广播，
            # 让 polling 的 bot / dashboard 能看到失败原因而不是等满 120s
            if s:
                s.last_result = {
                    "status": "error",
                    "result": f"Worker process dead (returncode={w.process.returncode if w.process else 'none'})",
                    "cbc_session_id": s.cbc_session_id,
                    "timestamp": __import__("datetime").datetime.now().isoformat(),
                }
                _sess.save(s)
            await _bcast({
                "type": "worker.result",
                "workerId": w.worker_id,
                "sessionId": w.session_id,
                "status": "error",
                "result": "Worker process dead",
            })
            continue

        w.status = "running"

        msg = json.dumps({
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": text}],
            },
        })
        w.process.stdin.write((msg + "\n").encode())
        await w.process.stdin.drain()

        await _bcast({
            "type": "worker.status",
            "workerId": w.worker_id,
            "sessionId": w.session_id,
            "status": "running",
            "source": source,
        })


# ── lifecycle ──

async def create_worker(session_id: str) -> Worker | str:
    """Spawn a cbc process for the given Session UUID.

    Returns Worker on success, error string on failure.
    """
    s = _sess.get(session_id)
    if not s:
        return f"Session {session_id} not found"

    worker_id = await _next_worker_id()

    resuming = bool(s.cbc_session_id)

    extra_args = ["--model", s.model or DEFAULT_MODEL]
    if s.permission_mode:
        extra_args.extend(["--permission-mode", s.permission_mode])

    spawn_args = _base_args() + extra_args
    if s.cbc_session_id:
        spawn_args += ["--resume", s.cbc_session_id]

    try:
        process = await asyncio.create_subprocess_exec(
            *spawn_args,
            stdout=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=s.workdir or None,
        )
    except FileNotFoundError:
        return f"cbc not found at: {CBC_PATH}"
    except OSError as e:
        return f"OS error: {e}"

    w = Worker(worker_id=worker_id, session_id=session_id,
               status="idle", process=process, queue=asyncio.Queue(),
               _replaying=resuming)
    workers[worker_id] = w
    w._stdout_task = asyncio.create_task(_read_stdout(w))
    w._consume_task = asyncio.create_task(_consumer(w))

    await _bcast({
        "type": "worker.spawned",
        "workerId": worker_id,
        "sessionId": session_id,
        "name": s.name,
        "status": "idle",
        "model": s.model or DEFAULT_MODEL,
    })

    # 持久化 session（记录 workdir 等）
    _sess.save(s)
    return w


async def kill_worker(worker_id: str) -> str | None:
    """Kill the Worker process. Does NOT touch the Session."""
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"

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
    await _bcast({
        "type": "worker.destroyed",
        "workerId": worker_id,
        "sessionId": w.session_id,
    })
    return None


async def _spawn_process(session_id: str,
                         extra_args: list[str] | None = None
                         ) -> asyncio.subprocess.Process | str:
    s = _sess.get(session_id)
    if not s:
        return f"Session {session_id} not found"

    args = _base_args()
    if s.cbc_session_id:
        args.extend(["--resume", s.cbc_session_id])
    if s.model:
        args.extend(["--model", s.model])
    if s.permission_mode:
        args.extend(["--permission-mode", s.permission_mode])
    if extra_args:
        # extra_args 可能包含覆盖 --model, --permission-mode
        args.extend(extra_args)

    try:
        return await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=s.workdir or None,
        )
    except FileNotFoundError:
        return f"cbc not found at: {CBC_PATH}"
    except OSError as e:
        return f"OS error spawning cbc: {e}"


async def _restart_tasks(w: Worker):
    if w._stdout_task:
        w._stdout_task.cancel()
    if w._consume_task:
        w._consume_task.cancel()
    w.queue = asyncio.Queue()
    w._stdout_task = asyncio.create_task(_read_stdout(w))
    w._consume_task = asyncio.create_task(_consumer(w))


async def restart_worker(worker_id: str) -> str | None:
    """Restart the cbc process for a Worker. Preserves session."""
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"

    # always clear held status
    w.status = "idle"

    # kill existing process regardless of state
    if w.process:
        try:
            w.process.kill()
        except ProcessLookupError:
            pass
        except Exception:
            pass
        w.process = None

    # cancel stale tasks
    if w._consume_task:
        w._consume_task.cancel()
    if w._stdout_task:
        w._stdout_task.cancel()

    proc = await _spawn_process(w.session_id)
    if isinstance(proc, str):
        return f"Spawn failed ({w.session_id}): {proc}"
    w.process = proc
    w.status = "idle"
    # if session has cbc_session_id, --resume was used → enter replay mode
    s = _sess.get(w.session_id)
    w._replaying = bool(s and s.cbc_session_id)
    await _restart_tasks(w)

    s = _session(w)
    await _bcast({
        "type": "worker.restarted",
        "workerId": worker_id,
        "sessionId": w.session_id,
        "name": s.name if s else worker_id,
        "status": "idle",
    })
    return None


async def respawn_worker(worker_id: str, extra_args: list[str] | None = None) -> str | None:
    """Kill + re-spawn with extra args (model/mode switch)."""
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"

    if w.process:
        try:
            w.process.kill()
        except ProcessLookupError:
            pass

    proc = await _spawn_process(w.session_id, extra_args)
    if isinstance(proc, str):
        return proc
    w.process = proc
    w.status = "idle"
    await _restart_tasks(w)

    await _bcast({
        "type": "worker.reconfigured",
        "workerId": worker_id,
        "sessionId": w.session_id,
        "status": "idle",
    })
    return None


async def branch_worker(worker_id: str, new_session_id: str) -> Worker | str:
    """Fork a new Worker from an existing one's session.

    new_session_id must already exist (created by session.create()).
    """
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"

    s = _sess.get(new_session_id)
    if not s:
        return "New session not found"

    # inherit model/mode from original session
    orig = _sess.get(w.session_id)
    if orig:
        if not s.model:
            s.model = orig.model
        if not s.permission_mode:
            s.permission_mode = orig.permission_mode

    extra_args = ["--model", s.model or DEFAULT_MODEL,
                  "--resume", s.cbc_session_id or "",
                  "--fork-session"]
    if s.permission_mode:
        extra_args.extend(["--permission-mode", s.permission_mode])

    new_id = await _next_worker_id()
    process = await asyncio.create_subprocess_exec(
        *_base_args(), *extra_args,
        stdout=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=s.workdir or None,
    )

    new_w = Worker(worker_id=new_id, session_id=new_session_id,
                   status="idle", process=process, queue=asyncio.Queue())
    workers[new_id] = new_w
    new_w._stdout_task = asyncio.create_task(_read_stdout(new_w))
    new_w._consume_task = asyncio.create_task(_consumer(new_w))

    _sess.save(s)

    await _bcast({
        "type": "worker.spawned",
        "workerId": new_id,
        "sessionId": new_session_id,
        "name": s.name,
        "status": "idle",
        "parentWorkerId": worker_id,
    })
    return new_w


async def interrupt_worker(worker_id: str) -> str | None:
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"
    if w.status != "running":
        return "Worker is not running"
    return await restart_worker(worker_id)


async def send_task(worker_id: str, text: str, source: str = "agent") -> str | None:
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


def find_worker_by_session(session_id: str) -> Worker | None:
    for w in workers.values():
        if w.session_id == session_id:
            return w
    return None


async def shutdown_all():
    ids = list(workers.keys())
    for wid in ids:
        w = workers.get(wid)
        if not w:
            continue
        if w._consume_task:
            w._consume_task.cancel()
        if w._stdout_task:
            w._stdout_task.cancel()
        if w.process:
            try:
                w.process.kill()
            except ProcessLookupError:
                pass
    workers.clear()
