"""cbc (CodeBuddy CLI) 适配器。"""

from __future__ import annotations

import json
import os
from src.session import Session


class CbcAdapter:
    """cbc (CodeBuddy CLI) 适配器。

    实现 CliAdapter 协议。实例无状态，可被多 worker 共享。
    """

    name = "cbc"
    default_model = "deepseek-v4-flash"
    supported_models = [
        "glm-5.2", "glm-5.1", "glm-5.0", "glm-5.0-turbo", "glm-5v-turbo", "glm-4.7",
        "minimax-m3", "minimax-m2.7",
        "kimi-k2.7", "kimi-k2.6", "kimi-k2.5",
        "hy3-preview",
        "deepseek-v4-pro", "deepseek-v4-flash", "deepseek-v3-2-volc",
        "custom-local:deepseek-v4-pro",
    ]
    supports_resume = True
    supports_fork = True

    _CBC_PATH = os.environ.get(
        "CLICONDUCTOR_CBC_PATH",
        r"D:\node_npm\node_global\cbc.cmd",
    )

    # ── 进程启动 ──

    def base_args(self) -> list[str]:
        return [self._CBC_PATH, "-p", "--output-format", "stream-json",
                "--input-format", "stream-json", "-y"]

    def model_args(self, s: Session) -> list[str]:
        return ["--model", s.model or self.default_model]

    def thinking_args(self, s: Session) -> list[str]:
        """cbc 的 alwaysThinkingEnabled 默认 true，关闭时需 --settings 覆盖。"""
        if not s.always_thinking_enabled:
            return ["--settings", '{"alwaysThinkingEnabled": false}']
        return []

    def effort_args(self, s: Session) -> list[str]:
        if s.always_thinking_enabled and s.effort:
            return ["--effort", s.effort]
        return []

    def permission_mode_args(self, s: Session) -> list[str]:
        if s.permission_mode:
            return ["--permission-mode", s.permission_mode]
        return []

    def resume_args(self, s: Session) -> list[str]:
        if s.cbc_session_id:
            return ["--resume", s.cbc_session_id]
        return []

    def fork_args(self, s: Session | None = None) -> list[str]:
        """返回 fork 参数。若 session 没有 cbc_session_id，需要显式 --resume。"""
        if s and not s.cbc_session_id:
            return ["--resume", "", "--fork-session"]
        return ["--fork-session"]

    def build_spawn_args(self, s: Session,
                          extra_args: list[str] | None = None) -> list[str]:
        args = self.base_args()
        args.extend(self.model_args(s))
        args.extend(self.permission_mode_args(s))
        args.extend(self.effort_args(s))
        args.extend(self.thinking_args(s))
        args.extend(self.resume_args(s))
        if extra_args:
            args.extend(extra_args)
        return args

    # ── stdin 消息编码 ──

    def encode_user_message(self, text: str) -> bytes:
        return json.dumps({
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": text}],
            },
        }).encode("utf-8")

    # ── stdout 事件解析 ──

    def parse_event(self, line: str) -> dict | None:
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    def event_type(self, event: dict) -> str:
        return event.get("type", "")

    def is_init_event(self, event: dict) -> bool:
        return (event.get("type") == "system"
                and event.get("subtype") == "init")

    def extract_session_id(self, event: dict) -> str | None:
        return event.get("session_id")

    def extract_model(self, event: dict) -> str | None:
        return event.get("model")

    def is_assistant_event(self, event: dict) -> bool:
        return event.get("type") == "assistant"

    def extract_assistant_blocks(self, event: dict) -> list[dict]:
        blocks: list[dict] = []
        for b in event.get("message", {}).get("content", []) or []:
            if b.get("type") == "text":
                blocks.append({"role": "assistant", "content": b["text"]})
            elif b.get("type") == "thinking":
                blocks.append({"role": "thinking", "content": b["thinking"]})
            elif b.get("type") == "tool_use":
                blocks.append({
                    "role": "tool",
                    "content": f"{b['name']}({json.dumps(b.get('input', {}))})",
                })
        return blocks

    def is_result_event(self, event: dict) -> bool:
        return event.get("type") == "result"

    def is_result_error(self, event: dict) -> bool:
        return event.get("is_error", False)

    def extract_result_text(self, event: dict) -> str | None:
        return event.get("result")

    # ── takeover ──

    def takeover_command(self, s: Session) -> list[str]:
        if not s.cbc_session_id:
            return []
        return ["cbc", "--resume", s.cbc_session_id]
