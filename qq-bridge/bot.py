"""QQ Bot — NoneBot2 插件，桥接 QQ 与 CLIConductor。

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
POLL_INTERVAL = 1.5  # 轮询间隔（秒）
MAX_POLL_TIME = 120  # 最长等待结果时间（秒）

# ── Session 映射管理 ──

# qq_user_id -> BridgeSession
_sessions: dict[str, "BridgeSession"] = {}

# 等待结果的队列：session_id -> asyncio.Event
_pending: dict[str, asyncio.Event] = {}

# 轮询任务：session_id -> asyncio.Task
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

_http = httpx.AsyncClient(timeout=30)


async def _get(path: str) -> dict:
    r = await _http.get(f"{CLICONDUCTOR_URL}{path}")
    return r.json()


async def _post(path: str, data: dict = None) -> dict:
    r = await _http.post(f"{CLICONDUCTOR_URL}{path}", json=data or {})
    return r.json()


# ── 轮询结果 ──

async def _poll_result(session_id: str, qq_user_id: str):
    """轮询 CLIConductor 直到 last_result 更新，然后通知等待者。"""
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

            s = data.get("history", [])
            lr = data.get("lastResult") or {}

            # 检测新的 last_result
            new_ts = lr.get("timestamp", "") if lr else ""
            if new_ts and new_ts != last_ts:
                session.last_result_ts = new_ts
                session.last_history_len = len(s)

                # 通知等待者
                evt = _pending.get(session_id)
                if evt:
                    evt.set()
                return

            # 也检测 history 长度变化（stream 模式）
            if len(s) > session.last_history_len:
                session.last_history_len = len(s)
                evt = _pending.get(session_id)
                if evt:
                    evt.set()
                return

        except Exception:
            await asyncio.sleep(2)

    # 超时
    evt = _pending.get(session_id)
    if evt:
        evt.set()


async def _ensure_session(qq_user_id: str) -> str | None:
    """确保 QQ 用户有对应的 CLIConductor Session，返回 session_id。"""
    session = _sessions.get(qq_user_id)
    if session and session.cli_session_id:
        # 检查 session 是否还存在
        data = await _get(f"/api/sessions/{session.cli_session_id}")
        if "error" not in data:
            return session.cli_session_id
        # session 被删了，重新创建

    # 1. 创建 Session
    name = f"qq-{qq_user_id[-6:]}"
    s = await _post("/api/sessions", {"name": name})
    if "error" in s:
        return None
    cli_session_id = s["id"]

    # 2. Spawn Worker
    result = await _post("/api/spawn", {"sessionId": cli_session_id})
    if "error" in result:
        return None

    bridge = BridgeSession(
        qq_user_id=qq_user_id,
        cli_session_id=cli_session_id,
        worker_id=result.get("workerId"),
    )
    _sessions[qq_user_id] = bridge
    return cli_session_id


async def _send_and_wait(text: str, qq_user_id: str) -> str:
    """发送消息到 CLIConductor 并等待结果返回。"""
    session_id = await _ensure_session(qq_user_id)
    if not session_id:
        return "[CLIConductor] 无法创建会话"

    # 注册等待
    evt = asyncio.Event()
    _pending[session_id] = evt

    # 启动轮询（如果没有正在跑的）
    if session_id not in _poll_tasks or _poll_tasks[session_id].done():
        _poll_tasks[session_id] = asyncio.create_task(
            _poll_result(session_id, qq_user_id)
        )

    # 发送任务
    result = await _post("/api/task", {
        "sessionId": session_id,
        "text": text,
    })
    if "error" in result:
        del _pending[session_id]
        return f"[CLIConductor] 错误: {result['error']}"

    # 等待结果（带超时）
    try:
        await asyncio.wait_for(evt.wait(), timeout=MAX_POLL_TIME + 5)
    except asyncio.TimeoutError:
        del _pending[session_id]
        return "[CLIConductor] 响应超时"

    del _pending[session_id]

    # 获取最新消息
    data = await _get(f"/api/sessions/{session_id}")
    if "error" in data:
        return "[CLIConductor] 无法获取响应"

    history = data.get("history", [])
    bridge = _sessions.get(qq_user_id)
    if bridge:
        bridge.last_history_len = len(history)

    # 提取最后一条 assistant 消息
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            # 移除 tool call 的 🔧 行
            lines = [l for l in content.split("\n") if not l.startswith("🔧")]
            return "\n".join(lines).strip() or "(tool call only)"

    return "[CLIConductor] 无响应"


# ── 消息处理器 ──

_msg_handler = on_message()


@_msg_handler.handle()
async def handle_message(bot: Bot, event: MessageEvent):
    """处理所有 QQ 消息。"""
    # 只处理私聊和 @bot 的群消息
    if isinstance(event, GroupMessageEvent):
        # 检查是否 @了 bot
        bot_qq = int(bot.self_id)
        if bot_qq not in [seg.data.get("qq", 0) for seg in event.message if seg.type == "at"]:
            return

    qq_user_id = str(event.get_user_id())
    text = event.get_plaintext().strip()

    if not text:
        return

    # 发消息提示"正在处理"
    await bot.send(event, "正在处理，请稍候…")

    # 发送到 CLIConductor 并等待
    response = await _send_and_wait(text, qq_user_id)

    # 分段发送（QQ 消息长度限制）
    MAX_LEN = 1500
    if len(response) <= MAX_LEN:
        await bot.send(event, response)
    else:
        for i in range(0, len(response), MAX_LEN):
            chunk = response[i : i + MAX_LEN]
            await bot.send(event, chunk)
            await asyncio.sleep(0.5)


# ── 启动 ──

try:
    driver = get_driver()
except ValueError:
    driver = None


if driver:

    @driver.on_startup
    async def _startup():
        """启动时验证 CLIConductor 连接。"""
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
        """关闭时清理。"""
        for task in _poll_tasks.values():
            task.cancel()
        await _http.aclose()


# ── 主入口 ──

if __name__ == "__main__":
    import nonebot
    nonebot.init()
    nonebot.load_plugin(__name__)
    nonebot.run()
