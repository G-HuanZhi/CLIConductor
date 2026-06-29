"""QQ Bridge — NoneBot2 插件，桥接 QQ 与 CLIConductor。

架构：
  QQ 用户 → NapCat (OneBot WS) → NoneBot2 → 本插件 → CLIConductor HTTP API → Worker

使用方式：
  1. 启动 NapCat（QQ 协议端）
  2. 启动 CLIConductor（python main.py）
  3. 启动本 bot：python bot.py
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass

import httpx
from nonebot import get_driver, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent, PrivateMessageEvent

# ── 配置 ──

CLICONDUCTOR_URL = os.getenv("CLICONDUCTOR_URL", "http://127.0.0.1:8767")
POLL_INTERVAL = 1.5
MAX_POLL_TIME = 120

# ── Session 映射管理 ──

_sessions: dict[str, "BridgeSession"] = {}
_pending: dict[str, asyncio.Event] = {}
_poll_tasks: dict[str, asyncio.Task] = {}


@dataclass
class BridgeSession:
    qq_user_id: str
    cli_session_id: str | None = None
    worker_id: str | None = None
    last_history_len: int = 0
    last_result_ts: str = ""
    created_at: float = 0.0

    def __post_init__(self):
        self.created_at = time.time()


# ── HTTP 调用 ──


async def _get(path: str) -> dict:
    url = f"{CLICONDUCTOR_URL}{path}"
    print(f"[QQ Bridge] GET {url}")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        print(f"[QQ Bridge] GET 失败: {type(e).__name__}: {e}")
        return {"error": str(e)}


async def _post(path: str, data: dict = None) -> dict:
    url = f"{CLICONDUCTOR_URL}{path}"
    print(f"[QQ Bridge] POST {url}")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, json=data or {})
            r.raise_for_status()
            return r.json()
    except Exception as e:
        print(f"[QQ Bridge] POST 失败: {type(e).__name__}: {e}")
        return {"error": str(e)}


# ── 轮询结果 ──

async def _poll_result(session_id: str, qq_user_id: str):
    session = _sessions.get(qq_user_id)
    if not session:
        return

    start = time.time()
    last_ts = session.last_result_ts

    while time.time() - start < MAX_POLL_TIME:
        await asyncio.sleep(POLL_INTERVAL)

        try:
            data = await _get(f"/api/sessions/{session_id}")
            if "error" in data:
                continue

            lr = data.get("lastResult") or {}

            new_ts = lr.get("timestamp", "") if lr else ""
            if new_ts and new_ts != last_ts:
                session.last_result_ts = new_ts
                session.last_history_len = len(data.get("history", []))
                evt = _pending.get(session_id)
                if evt:
                    evt.set()
                return

        except Exception:
            await asyncio.sleep(2)

    evt = _pending.get(session_id)
    if evt:
        evt.set()


async def _ensure_session(qq_user_id: str) -> str | None:
    session = _sessions.get(qq_user_id)
    if session and session.cli_session_id:
        data = await _get(f"/api/sessions/{session.cli_session_id}")
        if "error" not in data:
            return session.cli_session_id

    # 先查已有的 session（避免重复创建）
    existing = await _get("/api/sessions")
    if "sessions" in existing:
        for sess_data in existing["sessions"]:
            if sess_data.get("name", "").startswith(f"qq-{qq_user_id[-6:]}"):
                lr = sess_data.get("lastResult") or {}
                bridge = BridgeSession(
                    qq_user_id=qq_user_id,
                    cli_session_id=sess_data["id"],
                    worker_id=sess_data.get("workerId"),
                    last_result_ts=lr.get("timestamp", ""),
                    last_history_len=len(sess_data.get("history", [])),
                )
                _sessions[qq_user_id] = bridge
                # 如果没有 worker，spawn 一个
                if not bridge.worker_id:
                    result = await _post("/api/spawn", {"sessionId": bridge.cli_session_id})
                    if "error" not in result:
                        bridge.worker_id = result.get("workerId")
                return bridge.cli_session_id

    # 新建 session
    name = f"qq-{qq_user_id[-6:]}"
    s = await _post("/api/sessions", {"name": name})
    if "error" in s:
        print(f"[QQ Bridge] 创建 Session 失败: {s['error']}")
        return None
    cli_session_id = s["id"]

    result = await _post("/api/spawn", {"sessionId": cli_session_id})
    if "error" in result:
        print(f"[QQ Bridge] Spawn Worker 失败: {result['error']}")
        return None

    bridge = BridgeSession(
        qq_user_id=qq_user_id,
        cli_session_id=cli_session_id,
        worker_id=result.get("workerId"),
    )
    _sessions[qq_user_id] = bridge
    return cli_session_id


async def _send_and_wait(text: str, qq_user_id: str) -> str:
    session_id = await _ensure_session(qq_user_id)
    if not session_id:
        return "[CLIConductor] 无法创建会话"

    evt = asyncio.Event()
    _pending[session_id] = evt

    if session_id not in _poll_tasks or _poll_tasks[session_id].done():
        _poll_tasks[session_id] = asyncio.create_task(
            _poll_result(session_id, qq_user_id)
        )

    result = await _post("/api/task", {
        "sessionId": session_id,
        "text": text,
    })
    if "error" in result:
        del _pending[session_id]
        return f"[CLIConductor] 错误: {result['error']}"

    try:
        await asyncio.wait_for(evt.wait(), timeout=MAX_POLL_TIME + 5)
    except asyncio.TimeoutError:
        del _pending[session_id]
        return "[CLIConductor] 响应超时"

    del _pending[session_id]

    data = await _get(f"/api/sessions/{session_id}")
    if "error" in data:
        return "[CLIConductor] 无法获取响应"

    history = data.get("history", [])
    bridge = _sessions.get(qq_user_id)
    if bridge:
        bridge.last_history_len = len(history)

    for msg in reversed(history):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            lines = [l for l in content.split("\n") if not l.startswith("🔧")]
            return "\n".join(lines).strip() or "(tool call only)"

    return "[CLIConductor] 无响应"


# ── 消息处理器 ──

_msg_handler = on_message()


@_msg_handler.handle()
async def handle_message(bot: Bot, event: MessageEvent):
    if isinstance(event, GroupMessageEvent):
        bot_qq = int(bot.self_id)
        if bot_qq not in [seg.data.get("qq", 0) for seg in event.message if seg.type == "at"]:
            return

    qq_user_id = str(event.get_user_id())
    text = event.get_plaintext().strip()

    if not text:
        return

    await bot.send(event, "正在处理，请稍候…")

    response = await _send_and_wait(text, qq_user_id)

    MAX_LEN = 1500
    if len(response) <= MAX_LEN:
        await bot.send(event, response)
    else:
        for i in range(0, len(response), MAX_LEN):
            chunk = response[i : i + MAX_LEN]
            await bot.send(event, chunk)
            await asyncio.sleep(0.5)


# ── 生命周期钩子 ──

driver = get_driver()


@driver.on_startup
async def _startup():
    try:
        data = await _get("/api/models")
        models = data.get("models", [])
        print(f"[QQ Bridge] CLIConductor 已连接，支持 {len(models)} 个模型")
        print(f"[QQ Bridge] 默认模型: {data.get('default', 'unknown')}")
    except Exception as e:
        print(f"[QQ Bridge] 无法连接 CLIConductor: {e}")
        print("[QQ Bridge] 请确保 CLIConductor 已启动 (python main.py)")


@driver.on_shutdown
async def _shutdown():
    for task in _poll_tasks.values():
        task.cancel()
