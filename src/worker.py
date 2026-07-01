"""Worker — runtime cbc process management.

Worker is ephemeral: kill it, the Worker is gone.
All persistent data lives in Session (session.py).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime

from . import session as _sess
from .adapters import get_adapter, CliAdapter

_DEFAULT_ADAPTER = get_adapter("cbc")

# Backward-compatible shortcuts (server.py references these)
DEFAULT_MODEL = _DEFAULT_ADAPTER.default_model
SUPPORTED_MODELS = _DEFAULT_ADAPTER.supported_models


@dataclass
class Worker:
    worker_id: str
    session_id: str           # Session UUID (ses_<hex>)
    adapter: CliAdapter       # CLI tool adapter instance
    status: str = "idle"      # idle | running | held | error
    process: asyncio.subprocess.Process | None = None
    _stdout_task: asyncio.Task | None = None
    _consume_task: asyncio.Task | None = None
    queue: asyncio.Queue | None = None
    _replaying: bool = False  # true during cbc --resume event replay
    takeover_pid: int | None = None  # PID of takeover PowerShell terminal


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


# ── helpers (public API for server.py) ──

def effort_args(s: _sess.Session) -> list[str]:
    """Return default adapter's effort CLI args (exposed for server.py)."""
    return _DEFAULT_ADAPTER.effort_args(s)


# ── helpers (internal) ──


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
    adapter = w.adapter
    async for line in w.process.stdout:
        line_str = line.decode("utf-8", errors="replace").rstrip("\n")
        if not line_str:
            continue
        event = adapter.parse_event(line_str)
        if event is None:
            continue

        # 提取 session_id + model 并写入 Session
        if adapter.is_init_event(event):
            s = _session(w)
            if s:
                sid = adapter.extract_session_id(event)
                if sid:
                    s.cbc_session_id = sid
                model = adapter.extract_model(event)
                if model and not s.model:
                    s.model = model
                _sess.save(s)

        # 收集对话历史（replay 期间跳过，避免重复追加）
        if adapter.is_assistant_event(event) and not w._replaying:
            s = _session(w)
            if s:
                for b in adapter.extract_assistant_blocks(event):
                    s.history.append(b)
                _sess.save(s)

        # 任务完成 → 保存 Session + last_result
        if adapter.is_result_event(event):
            s = _session(w)
            is_error = adapter.is_result_error(event)
            w.status = "error" if is_error else "done"

            # replay 结束：标记完成，不保存（history 无变化）
            if w._replaying:
                w._replaying = False
                w.status = "idle"
                continue

            if s:
                result_text = adapter.extract_result_text(event)
                s.last_result = {
                    "status": w.status,
                    "result": result_text,
                    "cbc_session_id": s.cbc_session_id,
                    "timestamp": datetime.now().isoformat(),
                }
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
                "result": adapter.extract_result_text(event),
            })
            w.status = "idle"
            continue

        # replay 期间不广播 stream 事件
        if not w._replaying:
            await _bcast({
                "type": "worker.stream",
                "workerId": w.worker_id,
                "sessionId": w.session_id,
                "event": event,
            })

    # stdout EOF — 进程退出了
    w.status = "error"
    code = w.process.returncode if w.process else "unknown"
    print(f"[Worker {w.worker_id}] {adapter.name} 进程退出，返回码 {code}")
    await _bcast({
        "type": "worker.crashed",
        "workerId": w.worker_id,
        "sessionId": w.session_id,
        "returncode": code,
    })
    # 从 workers dict 移除尸体——否则 find_worker_by_session 会返回这个死 worker，
    # 后续 send_task 才报 'process dead'，晚了一步
    workers.pop(w.worker_id, None)


# ── consumer ──

async def _consumer(w: Worker):
    while True:
        item = await w.queue.get()
        if item is None:
            break

        text = item["text"]
        source = item.get("source", "agent")

        # 用户发新消息 → replay 阶段结束。即使 cbc 还在重放旧事件，
        # 后续 assistant 事件必须正常 append 到 history（否则回复丢失）。
        w._replaying = False

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
                    "timestamp": datetime.now().isoformat(),
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

        data = w.adapter.encode_user_message(text)
        w.process.stdin.write(data + b"\n")
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
    """Spawn a CLI process for the given Session UUID.

    Returns Worker on success, error string on failure.

    一个 session 同时只能有一个活 worker：如果已有旧 worker（哪怕状态是
    error），先杀掉移除，避免 find_worker_by_session 返回错的那个。
    """
    s = _sess.get(session_id)
    if not s:
        return f"Session {session_id} not found"

    # 杀掉同 session 的旧 worker（崩过留了 error 尸体 / 重复 spawn）
    old = find_worker_by_session(session_id)
    if old:
        await kill_worker(old.worker_id)

    adapter = get_adapter(s.adapter)
    worker_id = await _next_worker_id()

    proc = await _spawn_process(session_id, adapter=adapter)
    if isinstance(proc, str):
        return proc

    resuming = bool(s.cbc_session_id) and adapter.supports_resume
    w = Worker(worker_id=worker_id, session_id=session_id,
               adapter=adapter,
               status="idle", process=proc, queue=asyncio.Queue(),
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
        "model": s.model or adapter.default_model,
    })

    # 持久化 session（记录 workdir 等）
    _sess.save(s)
    return w


def _kill_takeover_terminal(w: Worker) -> bool:
    """杀掉 takeover 模式打开的 PowerShell 终端及其子进程树。

    返回 True 表示有 takeover_pid 被处理（不论是否成功杀掉）。

    关键：必须用 `taskkill /F /T /PID` 一次性强杀整棵树，绝不能先调
    `os.kill(pid, SIGTERM)`。在 Windows 上 os.kill(SIGTERM) 走的是
    TerminateProcess（强杀），会先把树根 powershell.exe 干掉，导致
    cmd.exe / node.exe 变成孤儿进程，随后的 taskkill /T 找不到树根
    就杀不到子进程——终端窗口和 cbc 子进程都会残留。这正是之前多次
    修复都失败的根本原因。
    """
    if not w.takeover_pid:
        return False
    pid = w.takeover_pid
    print(f"[Worker {w.worker_id}] 杀 takeover 终端 PID={pid}")
    try:
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/F", "/T"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            print(f"[Worker {w.worker_id}] taskkill OK: {result.stdout.strip()}")
        else:
            # taskkill 报错——可能是进程已自行退出，也可能是真的没杀掉。
            # 用 tasklist 确认 PID 是否还活着，便于排查。
            try:
                check = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                    capture_output=True, text=True, timeout=5,
                )
                if str(pid) in check.stdout:
                    print(f"[Worker {w.worker_id}] taskkill rc={result.returncode} "
                          f"({result.stderr.strip()}), 进程仍存活！")
                else:
                    print(f"[Worker {w.worker_id}] taskkill rc={result.returncode}, "
                          f"进程已不存在（可能已自行退出）")
            except Exception as ce:
                print(f"[Worker {w.worker_id}] tasklist 检查异常: {ce}")
    except Exception as e:
        print(f"[Worker {w.worker_id}] taskkill 异常: {e}")
    w.takeover_pid = None
    return True


def _kill_process_tree(w: Worker) -> None:
    """杀掉 worker 的 cbc 进程及其整棵子进程树。

    cbc.cmd 会 spawn node.exe 作为子进程。`w.process.kill()` 只杀 cbc.cmd
    本身（等价于 TerminateProcess），node.exe 变孤儿继续运行。
    必须用 `taskkill /F /T /PID` 一次性强杀整棵树。

    与 _kill_takeover_terminal 的区别：本函数杀的是 worker 自己的 cbc
    子进程；_kill_takeover_terminal 杀的是 takeover 模式打开的 PowerShell
    终端。两者独立，都需要调用。
    """
    if not w.process:
        return
    pid = w.process.pid
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True, timeout=5,
        )
    except Exception:
        # taskkill 失败（进程可能已退出）——回退到 .kill()，至少把 cbc.cmd 杀掉
        try:
            w.process.kill()
        except ProcessLookupError:
            pass
        except Exception:
            pass


async def kill_worker(worker_id: str) -> str | None:
    """Kill the Worker process. Does NOT touch the Session."""
    w = workers.get(worker_id)
    if not w:
        return "Worker not found"

    if w._consume_task:
        w._consume_task.cancel()
    if w._stdout_task:
        w._stdout_task.cancel()
    _kill_process_tree(w)
    _kill_takeover_terminal(w)

    workers.pop(worker_id, None)
    await _bcast({
        "type": "worker.destroyed",
        "workerId": worker_id,
        "sessionId": w.session_id,
    })
    return None


async def _spawn_process(session_id: str,
                         adapter: CliAdapter,
                         extra_args: list[str] | None = None
                         ) -> asyncio.subprocess.Process | str:
    s = _sess.get(session_id)
    if not s:
        return f"Session {session_id} not found"

    args = adapter.build_spawn_args(s, extra_args)

    try:
        return await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=s.workdir or None,
        )
    except FileNotFoundError:
        return f"CLI executable not found (adapter={adapter.name})"
    except OSError as e:
        return f"OS error spawning {adapter.name}: {e}"


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

    # cancel stale tasks FIRST — before killing the process.
    # _read_stdout detects EOF on process death and calls workers.pop(),
    # which would remove the worker being restarted.  Cancelling first
    # means _read_stdout never sees the EOF.
    if w._consume_task:
        w._consume_task.cancel()
    if w._stdout_task:
        w._stdout_task.cancel()

    # kill takeover terminal if one was opened
    _kill_takeover_terminal(w)

    # kill existing cbc process tree（taskkill /F /T，避免 node.exe 孤儿）
    _kill_process_tree(w)
    w.process = None

    proc = await _spawn_process(w.session_id, adapter=w.adapter)
    if isinstance(proc, str):
        return f"Spawn failed ({w.session_id}): {proc}"
    w.process = proc
    w.status = "idle"
    # if session has cbc_session_id, --resume was used → enter replay mode
    s = _sess.get(w.session_id)
    w._replaying = bool(s and s.cbc_session_id) and w.adapter.supports_resume
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

    # cancel stale tasks FIRST — same race as restart_worker:
    # if we kill before cancelling, _read_stdout sees EOF and
    # pops the worker from workers dict during spawn.
    if w._consume_task:
        w._consume_task.cancel()
    if w._stdout_task:
        w._stdout_task.cancel()

    _kill_takeover_terminal(w)
    _kill_process_tree(w)

    proc = await _spawn_process(w.session_id, adapter=w.adapter, extra_args=extra_args)
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

    # inherit model/mode/thinking from original session
    orig = _sess.get(w.session_id)
    if orig:
        if not s.model:
            s.model = orig.model
        if not s.permission_mode:
            s.permission_mode = orig.permission_mode
        if not s.effort:
            s.effort = orig.effort
        s.always_thinking_enabled = s.always_thinking_enabled or orig.always_thinking_enabled
        if not s.max_thinking_tokens:
            s.max_thinking_tokens = orig.max_thinking_tokens

    # branch needs --fork-session from adapter
    extra_args = w.adapter.fork_args(s)
    if not w.adapter.supports_fork or not extra_args:
        return f"Adapter '{w.adapter.name}' does not support fork"

    new_id = await _next_worker_id()
    proc = await _spawn_process(new_session_id, adapter=w.adapter, extra_args=extra_args)
    if isinstance(proc, str):
        return proc

    new_w = Worker(worker_id=new_id, session_id=new_session_id,
                   adapter=w.adapter,
                   status="idle", process=proc, queue=asyncio.Queue())
    # 注意：branch 不设 _replaying（与 create_worker/restart_worker 不同）。
    # branch 的新 session history 为空，需要从 cbc --resume --fork-session
    # 的重放中填入历史，所以走正常 append 路径。主路径的 session 已有
    # 完整 history（磁盘 ground truth），replay 期间跳过 append 避免重复。
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
    """关闭所有 worker 的 cbc 进程树 + takeover 终端。

    必须用 _kill_process_tree / _kill_takeover_terminal（内部走 taskkill /F /T），
    不能只调 w.process.kill()——后者只杀 cbc.cmd，留下 node.exe 孤儿。
    """
    ids = list(workers.keys())
    for wid in ids:
        w = workers.get(wid)
        if not w:
            continue
        if w._consume_task:
            w._consume_task.cancel()
        if w._stdout_task:
            w._stdout_task.cancel()
        _kill_process_tree(w)
        _kill_takeover_terminal(w)
    workers.clear()
