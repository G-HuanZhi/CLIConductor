# CLIConductor Adapter 抽象设计文档

**制定日期**: 2026-07-01
**配套文档**: [fix-plan-2026-07-01.md](./fix-plan-2026-07-01.md)（阶段 2）
**实施模型**: DeepSeek-V4-Pro（按本文档照单实施）
**目标**: 把 cbc 特有逻辑从 `worker.py` 抽离到 `CbcAdapter`，建立可扩展的 `CliAdapter` 协议，使后续接入第二个 CLI 工具（claude-cli / gemini-cli / codex-cli 等）只需新增一个 adapter 文件。

---

## 一、当前代码的 cbc 耦合点盘点

实施前必须先看清"哪些是 cbc 特有的、哪些是通用的"。逐行扫 `src/worker.py`：

### 1.1 cbc 特有（必须迁到 CbcAdapter）

| 位置 | 内容 | cbc 特有点 |
|---|---|---|
| `worker.py:18-19` | `CBC_PATH` 环境变量 | 路径变量名 `CLICONDUCTOR_CBC_PATH` |
| `worker.py:20` | `DEFAULT_MODEL = "deepseek-v4-flash"` | cbc 的默认模型 |
| `worker.py:22-29` | `SUPPORTED_MODELS` 列表 | cbc 支持的模型清单 |
| `worker.py:64-66` | `_base_args()` | `["cbc", "-p", "--output-format", "stream-json", "--input-format", "stream-json", "-y"]` —— 全是 cbc 特有 flag |
| `worker.py:70-76` | `_thinking_args(s)` | `--settings '{"alwaysThinkingEnabled": false}'` —— cbc 特有的 settings JSON 协议 |
| `worker.py:79-83` | `_effort_args(s)` | `--effort <level>` —— cbc 特有 flag（其他 CLI 可能叫 `--thinking-budget`） |
| `worker.py:418-448` | `_spawn_process` 内的 args 拼装 | `--model` / `--permission-mode` / `--resume` / `--fork-session` 全是 cbc 特有 |
| `worker.py:117-126` | `_read_stdout` 里的 `system/init` 事件解析 | `event.get("session_id")` 写入 `s.cbc_session_id`，字段名 `session_id` 是 cbc 协议 |
| `worker.py:127-144` | `assistant` 事件 content 块解析 | `b.get("type") == "text"/"thinking"/"tool_use"` 是 cbc stream-json 协议 |
| `worker.py:145-184` | `result` 事件解析 | `event.get("is_error")` / `event.get("result")` 是 cbc 字段名 |
| `worker.py:254-262` | `_consumer` 写 stdin 的消息格式 | `{"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}` 是 cbc stream-json 输入协议 |
| `worker.py:322-364` | `_kill_takeover_terminal` | 命令 `cbc --resume {cbc_session_id}` 是 cbc 特有 |
| `worker.py:431-432` | `--resume s.cbc_session_id` | cbc 特有 flag |
| `worker.py:568-572` | branch 的 `--fork-session` | cbc 特有 flag |

### 1.2 通用（留在 worker.py 或迁到协议基类）

| 位置 | 内容 | 通用理由 |
|---|---|---|
| `worker.py:32-42` | `Worker` dataclass | 任何 CLI 都需要进程、队列、状态 |
| `worker.py:45-59` | `workers` dict / `_bcast` / `set_broadcaster` | 进程管理与广播与 CLI 无关 |
| `worker.py:86-96` | `_next_worker_id` | ID 生成与 CLI 无关 |
| `worker.py:99-100` | `_session(w)` | session 访问与 CLI 无关 |
| `worker.py:105-209` | `_read_stdout` 的整体框架 | "读行 → 解析 → 处理" 框架通用，但"解析"和"处理"是 adapter 职责 |
| `worker.py:212-272` | `_consumer` 的整体框架 | "取队列项 → 写 stdin" 框架通用，但"写 stdin 的字节格式"是 adapter 职责 |
| `worker.py:277-319` | `create_worker` 流程 | 创建 → 注册 → 起任务 → 广播，与 CLI 无关 |
| `worker.py:367-393` | `_kill_process_tree` | `taskkill /F /T` 是 Windows 通用进程树杀法 |
| `worker.py:396-415` | `kill_worker` | 与 CLI 无关 |
| `worker.py:451-458` | `_restart_tasks` | 与 CLI 无关 |
| `worker.py:461-537` | `restart_worker` / `respawn_worker` | 重启流程与 CLI 无关，但 spawn 走 adapter |
| `worker.py:540-599` | `branch_worker` | branch 流程与 CLI 无关，但 fork flag 是 adapter 职责 |
| `worker.py:602-623` | `interrupt_worker` / `send_task` | 与 CLI 无关 |
| `worker.py:626-658` | `get_worker` / `list_workers` / `find_worker_by_session` / `shutdown_all` | 与 CLI 无关 |

### 1.3 cbc 特有但留在 worker.py 的"_replaying 状态机"

`_replaying` 标志（`worker.py:41, 127, 153, 187, 225, 300, 493`）是 cbc `--resume` 重放机制的产物。

**关键决策**：是否把 replay 逻辑也抽到 adapter？

**决定：第一版不抽，留在 worker.py 作为"可选行为"**。理由：
1. replay 是 cbc 的特有机制（其他 CLI 不一定有 `--resume`）
2. 但 `_replaying` 标志的状态机渗在 `_read_stdout` / `_consumer` 里，强行抽出会让协议复杂化
3. 第一版先让 adapter 通过 `supports_resume: bool` 声明能力，worker.py 根据 session 是否有 `cbc_session_id` 判断是否进入 replay 模式
4. 等第二个 adapter 实现时（如果它也有 replay 概念）再升级协议

---

## 二、Adapter 协议设计

### 2.1 协议选型：`Protocol`（结构化子类型）

理由：
- Python `typing.Protocol` 是鸭子类型，adapter 不需要继承基类
- 测试时可以用 Mock 实现，无需继承真实 adapter
- 不强制 ABC 的 `metaclass=ABCMeta` 限制

### 2.2 协议方法集

设计原则：**协议只管"参数构造"和"事件解析"，不管"流程编排"**。流程编排（create/kill/restart）留在 worker.py。

```python
# src/adapters/base.py
from __future__ import annotations
from typing import Protocol, runtime_checkable
from src.session import Session


@runtime_checkable
class CliAdapter(Protocol):
    """CLI 工具适配器协议。

    每种 CLI 工具（cbc / claude-cli / gemini-cli / ...）实现此协议，
    worker.py 通过协议接口调用，不感知具体工具。

    设计原则：
    - 协议只管"参数构造"和"事件解析"
    - 流程编排（create/kill/restart/branch）留在 worker.py
    - adapter 实例应是无状态的（除了配置常量），可被多 worker 共享
    """

    # ── 元信息 ──

    @property
    def name(self) -> str:
        """适配器名称，如 'cbc' / 'claude'。用于 session.adapter 字段。"""
        ...

    @property
    def default_model(self) -> str:
        """该 CLI 工具的默认模型。"""
        ...

    @property
    def supported_models(self) -> list[str]:
        """该 CLI 工具支持的模型清单。"""
        ...

    @property
    def supports_resume(self) -> bool:
        """是否支持 --resume 恢复会话。影响 _replaying 状态机是否启用。"""
        ...

    @property
    def supports_fork(self) -> bool:
        """是否支持 fork 分支。影响 branch_worker 是否可用。"""
        ...

    # ── 进程启动 ──

    def base_args(self) -> list[str]:
        """启动 CLI 进程的基础参数（不含 model/thinking/resume 等可选参数）。

        例如 cbc 返回 ['D:\\...\\cbc.cmd', '-p', '--output-format', 'stream-json',
                       '--input-format', 'stream-json', '-y']
        """
        ...

    def model_args(self, s: Session) -> list[str]:
        """返回 --model 等模型相关参数。"""
        ...

    def thinking_args(self, s: Session) -> list[str]:
        """返回思考模式相关参数。"""
        ...

    def effort_args(self, s: Session) -> list[str]:
        """返回 effort 级别参数（如有）。"""
        ...

    def permission_mode_args(self, s: Session) -> list[str]:
        """返回权限模式参数（如有）。"""
        ...

    def resume_args(self, s: Session) -> list[str]:
        """返回会话恢复参数。

        若 session 没有 cbc_session_id 或 adapter 不支持 resume，返回 []。
        """
        ...

    def fork_args(self) -> list[str]:
        """返回 fork 分支参数（如 cbc 的 --fork-session）。

        若 adapter 不支持 fork，返回 []。
        """
        ...

    def build_spawn_args(self, s: Session,
                          extra_args: list[str] | None = None) -> list[str]:
        """组装完整的 spawn 参数列表。

        默认实现（adapter 可覆盖）：
            args = base_args() + model_args() + permission_mode_args()
                   + effort_args() + thinking_args() + resume_args()
            if extra_args: args.extend(extra_args)
            return args

        之所以放在协议里而非 worker.py，是因为不同 CLI 的参数顺序可能不同
        （cbc 的 --resume 必须在 --fork-session 前）。
        """
        ...

    # ── stdin 消息编码 ──

    def encode_user_message(self, text: str) -> bytes:
        """把用户文本编码成 CLI 进程 stdin 接受的字节流（不含尾部换行）。

        cbc 的格式：
            {"type": "user", "message": {"role": "user",
             "content": [{"type": "text", "text": text}]}}
        """
        ...

    # ── stdout 事件解析 ──

    def parse_event(self, line: str) -> dict | None:
        """解析 CLI stdout 的一行，返回事件 dict 或 None（无法解析/空行时）。

        cbc: json.loads(line)，失败返回 None
        其他 CLI 可能需要先剥离 ANSI 转义再解析
        """
        ...

    def event_type(self, event: dict) -> str:
        """返回事件的类型字符串（cbc: event['type']，如 'system'/'assistant'/'result'）。"""
        ...

    def is_init_event(self, event: dict) -> bool:
        """是否是初始化事件（包含 session_id / model 等启动信息）。"""
        ...

    def extract_session_id(self, event: dict) -> str | None:
        """从 init 事件提取 CLI 工具内部的 session ID（cbc: event['session_id']）。

        返回 None 表示该事件不含 session_id。
        """
        ...

    def extract_model(self, event: dict) -> str | None:
        """从 init 事件提取模型名（cbc: event['model']）。

        返回 None 表示该事件不含 model。
        """
        ...

    def is_assistant_event(self, event: dict) -> bool:
        """是否是 assistant 消息事件。"""
        ...

    def extract_assistant_blocks(self, event: dict) -> list[dict]:
        """从 assistant 事件提取消息块，统一格式：
            [{"role": "assistant"|"thinking"|"tool", "content": str}, ...]

        cbc: 遍历 event['message']['content']，把
              {"type": "text", "text": ...}     → {"role": "assistant", "content": text}
              {"type": "thinking", "thinking":...} → {"role": "thinking", "content": thinking}
              {"type": "tool_use", "name":..., "input":...}
                → {"role": "tool", "content": f"{name}({json.dumps(input)})"}
        """
        ...

    def is_result_event(self, event: dict) -> bool:
        """是否是结果事件（任务完成）。"""
        ...

    def is_result_error(self, event: dict) -> bool:
        """结果事件是否表示错误。"""
        ...

    def extract_result_text(self, event: dict) -> str | None:
        """从 result 事件提取最终文本（可能为 None）。

        cbc: event.get('result')
        """
        ...

    # ── takeover 命令构造（cbc 特有，但通过协议暴露）──

    def takeover_command(self, s: Session) -> list[str]:
        """返回 takeover 模式启动新终端的命令（不含 shell 包装）。

        cbc: ['cbc', '--resume', s.cbc_session_id]
        返回空列表表示该 adapter 不支持 takeover。
        """
        ...
```

### 2.3 关键设计决策

#### Q1: 为什么 `build_spawn_args` 放协议里，而不是 worker.py 拼装？

不同 CLI 的参数顺序敏感。cbc 的 `--resume <sid>` 必须在 `--fork-session` 前；其他 CLI 可能有不同顺序要求。让 adapter 自己拼装更安全。

#### Q2: 为什么用一堆 `is_xxx_event` / `extract_xxx` 而不是统一返回结构化 Event 对象？

第一版保守，避免引入新的类型系统。等第二个 adapter 实现后，如果发现解析逻辑重复，再升级为返回 `dataclass Event`。

#### Q3: `_replaying` 状态机怎么处理？

留在 worker.py。adapter 通过 `supports_resume` 声明能力：
- `supports_resume = True` 且 session 有 `cbc_session_id` → `create_worker` 设置 `_replaying=True`
- `supports_resume = False` → 永远不进入 replay 模式

worker.py 的 `_read_stdout` 仍然按现有逻辑处理 replay（跳过 append、跳过广播、result 时清标志）。

#### Q4: branch_worker 怎么处理？

留在 worker.py，但 spawn 时通过 `adapter.fork_args()` 拿 fork 参数：
- adapter `supports_fork = True` → `fork_args()` 返回 `["--fork-session"]`
- adapter `supports_fork = False` → `fork_args()` 返回 `[]`，branch_worker 提前返回错误

#### Q5: takeover 怎么处理？

留在 worker.py，但通过 `adapter.takeover_command(s)` 拿命令。adapter 不支持时返回 `[]`，worker.py 提前报错。

#### Q6: `cbc_session_id` 字段名要不要也抽象？

**第一版不抽象**。Session 的 `cbc_session_id` 字段虽然名字带 cbc，但语义是"CLI 工具内部 session ID"。为了不破坏现有磁盘数据格式，保留字段名。等接入第二个 adapter 时如果有冲突再迁移（迁移成本：一次 `data/sessions/*.json` 字段重命名脚本）。

#### Q7: Session 需要加 `adapter: str` 字段吗？

**需要**。`Session` dataclass 加 `adapter: str = "cbc"` 字段。`create_worker` 根据 `s.adapter` 从注册表拿对应 adapter 实例。

但**老 session 文件没有这个字段**，`Session(**data)` 构造时会用默认值 `"cbc"`，向后兼容。

---

## 三、文件结构设计

```
src/
├── adapters/
│   ├── __init__.py       # 导出 CliAdapter 协议 + 注册表
│   ├── base.py           # CliAdapter Protocol 定义
│   ├── registry.py       # adapter 注册表 + get_adapter()
│   └── cbc.py            # CbcAdapter 实现
├── worker.py             # 改造后：只保留流程编排，通过 adapter 调用
├── session.py            # 加 adapter 字段（默认 "cbc"）
└── server.py             # 不变（已无 cbc 直接调用，只通过 worker.* 间接调用）
```

`src/adapters/__init__.py`:
```python
from .base import CliAdapter
from .registry import register, get_adapter, list_adapters
from .cbc import CbcAdapter

# 启动时注册内置 adapter
register("cbc", CbcAdapter())

__all__ = ["CliAdapter", "register", "get_adapter", "list_adapters", "CbcAdapter"]
```

---

## 四、CbcAdapter 实现骨架

```python
# src/adapters/cbc.py
from __future__ import annotations

import json
import os
from src.session import Session


class CbcAdapter:
    """cbc (CodeBuddy CLI) 适配器。"""

    # ── 元信息 ──
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

    # ── 路径（从环境变量读）──
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

    def fork_args(self) -> list[str]:
        return ["--fork-session"]

    def build_spawn_args(self, s: Session,
                          extra_args: list[str] | None = None) -> list[str]:
        # 注意参数顺序：model/mode/effort/thinking 在前，resume 在后，
        # extra_args（如 fork-session）放最后
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
        msg = json.dumps({
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": text}],
            },
        })
        return msg.encode("utf-8")

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
        blocks = []
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

    # ── takeover 命令 ──
    def takeover_command(self, s: Session) -> list[str]:
        if not s.cbc_session_id:
            return []
        return ["cbc", "--resume", s.cbc_session_id]
```

**注意**：
- `CbcAdapter` 不继承 `CliAdapter`（Protocol 是结构化子类型，鸭子匹配即可）
- 类属性 `name` / `default_model` 等用 `class attr` 而非 `@property`，更简洁
- 实例无状态（除了配置常量），可全局共享单例

---

## 五、worker.py 改造映射表

| 当前代码（worker.py 行号） | 改造后 |
|---|---|
| `CBC_PATH = os.environ.get(...)` (18-19) | 删除，迁到 `CbcAdapter._CBC_PATH` |
| `DEFAULT_MODEL = "deepseek-v4-flash"` (20) | 删除，迁到 `CbcAdapter.default_model` |
| `SUPPORTED_MODELS = [...]` (22-29) | 删除，迁到 `CbcAdapter.supported_models` |
| `_base_args()` (64-66) | 删除，调用 `w.adapter.base_args()` |
| `_thinking_args(s)` (70-76) | 删除，调用 `w.adapter.thinking_args(s)` |
| `_effort_args(s)` (79-83) | 删除，调用 `w.adapter.effort_args(s)` |
| `_spawn_process` 内的 args 拼装 (425-435) | 改为 `args = w.adapter.build_spawn_args(s, extra_args)` |
| `_read_stdout` 里 `system/init` 解析 (117-126) | 改为 `if w.adapter.is_init_event(event): sid = w.adapter.extract_session_id(event); ...` |
| `_read_stdout` 里 `assistant` 解析 (127-144) | 改为 `if w.adapter.is_assistant_event(event): for b in w.adapter.extract_assistant_blocks(event): s.history.append(b); ...` |
| `_read_stdout` 里 `result` 解析 (145-184) | 改为 `if w.adapter.is_result_event(event): is_error = w.adapter.is_result_error(event); result_text = w.adapter.extract_result_text(event); ...` |
| `_consumer` 里 stdin 写入 (254-262) | 改为 `data = w.adapter.encode_user_message(text); w.process.stdin.write(data + b"\n"); await drain()` |
| `_kill_takeover_terminal` 里的 cbc 命令 (322-364) | takeover 命令通过 `w.adapter.takeover_command(s)` 拿，shell 拼接逻辑留在 worker.py（见 server.py 改造） |
| `branch_worker` 的 `--fork-session` (568-572) | 改为 `extra_args = w.adapter.fork_args()` |

---

## 六、server.py 改造点

`server.py` 目前对 `worker` 的引用都是间接的（`worker.DEFAULT_MODEL` / `worker.SUPPORTED_MODELS` / `worker._effort_args`），需要相应改造：

### 6.1 `worker.DEFAULT_MODEL` / `worker.SUPPORTED_MODELS` 的引用点

```python
# server.py 当前
"model": data.get("model") or worker.DEFAULT_MODEL,
"model": s.model or worker.DEFAULT_MODEL,
return {"models": worker.SUPPORTED_MODELS, "default": worker.DEFAULT_MODEL}
```

**改造方案**：在 `worker.py` 保留这两个常量作为"默认 adapter 的值"的快捷方式：

```python
# worker.py 顶部
from .adapters import get_adapter
_DEFAULT_ADAPTER = get_adapter("cbc")

# 向后兼容的快捷方式（server.py 仍可 worker.DEFAULT_MODEL 访问）
DEFAULT_MODEL = _DEFAULT_ADAPTER.default_model
SUPPORTED_MODELS = _DEFAULT_ADAPTER.supported_models
```

这样 `server.py` 完全不用改。未来如果要支持多 adapter 的 `/api/models` 端点，再改 server.py。

### 6.2 `worker._effort_args(s)` 的引用点

`server.py:557` 有 `extra_args.extend(worker._effort_args(s))`，在 `api_worker_settings` 里。

**改造方案**：改为公开 API：
```python
# worker.py 加一个公开函数
def effort_args(s: _sess.Session) -> list[str]:
    """公开 API：返回默认 adapter 的 effort args。"""
    return _DEFAULT_ADAPTER.effort_args(s)
```

server.py 把 `worker._effort_args` 改为 `worker.effort_args`（去掉下划线）。

### 6.3 `api_takeover` 的 cbc 命令拼接

`server.py:734` 当前：
```python
cmd = f'cd "{s.workdir}"; cbc --resume {s.cbc_session_id}'
```

**改造方案**：
```python
w = worker.get_worker(worker_id)
adapter_cmd = w.adapter.takeover_command(s) if w else []
if not adapter_cmd:
    return {"error": "Adapter does not support takeover"}
# 用 subprocess.Popen 的 cwd 参数，避免 shell 注入
proc = subprocess.Popen(
    ["powershell.exe", "-NoExit", "-Command",
     " ".join(adapter_cmd)],
    cwd=s.workdir,
    creationflags=subprocess.CREATE_NEW_CONSOLE,
)
```

这同时修复了 review 报告里的 1.5 shell 注入问题。

---

## 七、Session 改造

### 7.1 加 `adapter` 字段

```python
# src/session.py
@dataclass
class Session:
    id: str
    name: str
    cbc_session_id: str | None = None
    adapter: str = "cbc"   # ← 新增，默认 cbc，向后兼容老 session 文件
    model: str | None = None
    # ... 其余不变
```

### 7.2 `to_dict` 加 `adapter` 字段

```python
def to_dict(self) -> dict:
    return {
        "id": self.id,
        "name": self.name,
        "cbc_session_id": self.cbc_session_id,
        "adapter": self.adapter,   # ← 新增
        "model": self.model,
        # ... 其余不变
    }
```

### 7.3 向后兼容

老 session 文件没有 `adapter` 字段，`Session(**data)` 时会用 dataclass 默认值 `"cbc"`，自动兼容。无需迁移脚本。

---

## 八、worker.py 改造后的关键代码骨架

### 8.1 Worker dataclass 加 adapter 字段

```python
from .adapters import get_adapter

@dataclass
class Worker:
    worker_id: str
    session_id: str
    adapter: CliAdapter       # ← 新增，持有 adapter 实例
    status: str = "idle"
    process: asyncio.subprocess.Process | None = None
    _stdout_task: asyncio.Task | None = None
    _consume_task: asyncio.Task | None = None
    queue: asyncio.Queue | None = None
    _replaying: bool = False
    takeover_pid: int | None = None
```

### 8.2 `create_worker` 通过 session.adapter 拿实例

```python
async def create_worker(session_id: str) -> Worker | str:
    s = _sess.get(session_id)
    if not s:
        return f"Session {session_id} not found"

    old = find_worker_by_session(session_id)
    if old:
        await kill_worker(old.worker_id)

    adapter = get_adapter(s.adapter)   # ← 新增
    worker_id = await _next_worker_id()

    proc = await _spawn_process(session_id, adapter=adapter)  # 传 adapter
    if isinstance(proc, str):
        return proc

    resuming = bool(s.cbc_session_id) and adapter.supports_resume  # ← 新增条件
    w = Worker(worker_id=worker_id, session_id=session_id,
               adapter=adapter,                          # ← 新增
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
        "model": s.model or adapter.default_model,   # ← 改为 adapter
    })

    _sess.save(s)
    return w
```

### 8.3 `_spawn_process` 接受 adapter 参数

```python
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
```

### 8.4 `_read_stdout` 改造

```python
async def _read_stdout(w: Worker):
    adapter = w.adapter
    async for line in w.process.stdout:
        line_str = line.decode("utf-8", errors="replace").rstrip("\n")
        if not line_str:
            continue
        event = adapter.parse_event(line_str)
        if event is None:
            continue

        # init 事件
        if adapter.is_init_event(event):
            s = _session(w)
            if s:
                cbc_sid = adapter.extract_session_id(event)
                if cbc_sid:
                    s.cbc_session_id = cbc_sid
                model = adapter.extract_model(event)
                if model and not s.model:
                    s.model = model
                _sess.save(s)

        # assistant 事件
        if adapter.is_assistant_event(event) and not w._replaying:
            s = _session(w)
            if s:
                for b in adapter.extract_assistant_blocks(event):
                    s.history.append(b)
                _sess.save(s)

        # result 事件
        if adapter.is_result_event(event):
            s = _session(w)
            is_error = adapter.is_result_error(event)
            w.status = "error" if is_error else "done"

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

        if not w._replaying:
            await _bcast({
                "type": "worker.stream",
                "workerId": w.worker_id,
                "sessionId": w.session_id,
                "event": event,
            })

    # stdout EOF
    w.status = "error"
    code = w.process.returncode if w.process else "unknown"
    print(f"[Worker {w.worker_id}] {adapter.name} 进程退出，返回码 {code}")
    await _bcast({
        "type": "worker.crashed",
        "workerId": w.worker_id,
        "sessionId": w.session_id,
        "returncode": code,
    })
    workers.pop(w.worker_id, None)
```

### 8.5 `_consumer` 改造

```python
async def _consumer(w: Worker):
    adapter = w.adapter
    while True:
        item = await w.queue.get()
        if item is None:
            break

        text = item["text"]
        source = item.get("source", "agent")
        w._replaying = False

        s = _session(w)
        if s:
            s.history.append({"role": "user", "content": text})
            _sess.save(s)

        if w.process is None or w.process.returncode is not None:
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
        data = adapter.encode_user_message(text)
        w.process.stdin.write(data + b"\n")
        await w.process.stdin.drain()

        await _bcast({
            "type": "worker.status",
            "workerId": w.worker_id,
            "sessionId": w.session_id,
            "status": "running",
            "source": source,
        })
```

### 8.6 `restart_worker` / `respawn_worker` / `branch_worker` 改造

这三个函数都需要传 adapter 给 `_spawn_process`：

```python
# restart_worker
proc = await _spawn_process(w.session_id, adapter=w.adapter)

# respawn_worker
proc = await _spawn_process(w.session_id, adapter=w.adapter, extra_args=extra_args)

# branch_worker
extra_args = w.adapter.fork_args() if w.adapter.supports_fork else []
if not extra_args:
    return f"Adapter {w.adapter.name} does not support fork"
new_id = await _next_worker_id()
proc = await _spawn_process(new_session_id, adapter=w.adapter, extra_args=extra_args)
```

`restart_worker` 里设置 `_replaying` 也要加条件：
```python
s = _sess.get(w.session_id)
w._replaying = bool(s and s.cbc_session_id) and w.adapter.supports_resume
```

---

## 九、注册表实现

```python
# src/adapters/registry.py
from __future__ import annotations
from .base import CliAdapter

_adapters: dict[str, CliAdapter] = {}


def register(name: str, adapter: CliAdapter) -> None:
    """注册一个 adapter 实例。重名覆盖。"""
    _adapters[name] = adapter


def get_adapter(name: str) -> CliAdapter:
    """按名取 adapter。不存在时抛 KeyError。"""
    if name not in _adapters:
        raise KeyError(
            f"Adapter '{name}' not registered. Available: {list(_adapters.keys())}"
        )
    return _adapters[name]


def list_adapters() -> list[str]:
    """返回已注册的 adapter 名清单。"""
    return list(_adapters.keys())
```

---

## 十、实施步骤（DS 按此顺序执行）

### 步骤 1：创建 adapters 目录和文件
- 创建 `src/adapters/__init__.py`（先空文件，最后填充）
- 创建 `src/adapters/base.py`（CliAdapter Protocol）
- 创建 `src/adapters/registry.py`（注册表）
- 创建 `src/adapters/cbc.py`（CbcAdapter 实现）

**验证**：`python -c "from src.adapters import CbcAdapter; print(CbcAdapter().name)"` 输出 `cbc`

**commit**：`feat(adapters): add CliAdapter protocol and CbcAdapter implementation`

### 步骤 2：Session 加 adapter 字段
- `src/session.py` 的 `Session` dataclass 加 `adapter: str = "cbc"`
- `to_dict()` 加 `"adapter": self.adapter`

**验证**：`python -c "from src.session import Session; s = Session(id='x', name='y'); print(s.adapter)"` 输出 `cbc`

**commit**：`feat(session): add adapter field (default 'cbc', backward compatible)`

### 步骤 3：worker.py 引入 adapter
- 顶部 `from .adapters import get_adapter, CliAdapter`
- 顶部加 `_DEFAULT_ADAPTER = get_adapter("cbc")`
- 保留 `DEFAULT_MODEL` / `SUPPORTED_MODELS` 作为向后兼容常量（值取自 `_DEFAULT_ADAPTER`）
- 加公开函数 `effort_args(s)` 返回 `_DEFAULT_ADAPTER.effort_args(s)`
- `Worker` dataclass 加 `adapter: CliAdapter` 字段
- `create_worker` 里 `adapter = get_adapter(s.adapter)`，传给 `Worker`
- `_spawn_process` 接受 `adapter` 参数，用 `adapter.build_spawn_args(s, extra_args)`
- 删除 `_base_args` / `_thinking_args` / `_effort_args`（迁到 CbcAdapter 了）
- 删除 `CBC_PATH` 常量（迁到 CbcAdapter 了）

**验证**：
- `python -c "from src.worker import DEFAULT_MODEL; print(DEFAULT_MODEL)"` 输出 `deepseek-v4-flash`
- `python tests/test_worker_history.py` 全部通过（test 文件里的 mock 不依赖 adapter，但需要更新 Worker 构造）

**注意**：`tests/test_worker_history.py` 里 `_setup_worker` 创建 Worker 时需要传 `adapter`：
```python
from src.adapters import CbcAdapter
def _setup_worker(session_id: str, replaying: bool = False):
    w = worker.Worker(
        worker_id="worker-test",
        session_id=session_id,
        adapter=CbcAdapter(),   # ← 新增
        status="idle",
        process=MagicMock(),
        queue=asyncio.Queue(),
        _replaying=replaying,
    )
    ...
```

**commit**：`refactor(worker): inject CliAdapter into Worker, route spawn through adapter`

### 步骤 4：`_read_stdout` 改造
- 把 `event.get("type")` 改为 `adapter.event_type(event)`
- `system/init` 解析改为 `adapter.is_init_event` / `extract_session_id` / `extract_model`
- `assistant` 解析改为 `adapter.is_assistant_event` / `extract_assistant_blocks`
- `result` 解析改为 `adapter.is_result_event` / `is_result_error` / `extract_result_text`
- 注意：`_replaying` 逻辑保留在 worker.py，不变

**验证**：`python tests/test_worker_history.py` 全部通过

**commit**：`refactor(worker): route stdout event parsing through adapter`

### 步骤 5：`_consumer` 改造
- 把手搓的 `json.dumps({"type": "user", ...})` 改为 `adapter.encode_user_message(text)`
- 加 `data + b"\n"` 而不是 `(msg + "\n").encode()`

**验证**：`python tests/test_worker_history.py` 全部通过

**commit**：`refactor(worker): route stdin message encoding through adapter`

### 步骤 6：`restart_worker` / `respawn_worker` / `branch_worker` 改造
- 三处 `_spawn_process` 调用都加 `adapter=w.adapter`
- `restart_worker` 的 `_replaying` 设置加 `and w.adapter.supports_resume`
- `branch_worker` 的 `--fork-session` 改为 `w.adapter.fork_args()`

**验证**：
- `python tests/test_worker_history.py` 全部通过
- `python -c "from src.server import app; print('import OK')"`

**commit**：`refactor(worker): route restart/respawn/branch through adapter`

### 步骤 7：server.py 微调
- `worker._effort_args` 改为 `worker.effort_args`（去掉下划线）
- `api_takeover` 改用 `w.adapter.takeover_command(s)` + `cwd=s.workdir`（同时修 shell 注入）

**验证**：
- `python -c "from src.server import app; print('import OK')"`
- 启动服务，dashboard 能加载

**commit**：`refactor(server): use worker.effort_args public API + fix takeover shell injection`

### 步骤 8：最终验证
- 跑全部测试：`python tests/test_worker_history.py`
- 启动服务手动测试：
  - 创建 session → spawn → 发任务 → 收到回复
  - restart worker
  - branch worker
  - rename session（无 worker 也能改）
  - takeover（PowerShell 终端正常打开）

### 步骤 9：文档同步
- 在 `docs/fix-plan-2026-07-01.md` 阶段 2 的验收标准打勾

---

## 十一、验收标准

实施完成后必须满足：

- [ ] `src/adapters/` 目录建立，包含 `base.py` / `registry.py` / `cbc.py` / `__init__.py`
- [ ] `CbcAdapter` 实现全部协议方法
- [ ] `grep -n "cbc" src/worker.py` 仅在注释中出现（不再有硬编码 cbc 字样）
  - 例外：`cbc_session_id` 字段名保留（向后兼容磁盘格式）
  - 例外：注释里提到 cbc 是允许的
- [ ] `grep -n "_base_args\|_thinking_args\|_effort_args" src/worker.py` 无匹配（已迁到 adapter）
- [ ] `grep -n "CBC_PATH" src/worker.py` 无匹配（已迁到 CbcAdapter）
- [ ] `python tests/test_worker_history.py` 全部通过
- [ ] `python -c "from src.server import app"` 无报错
- [ ] `Worker` dataclass 有 `adapter: CliAdapter` 字段
- [ ] `Session` dataclass 有 `adapter: str = "cbc"` 字段
- [ ] 老 session 文件（无 adapter 字段）能正常加载，`s.adapter == "cbc"`
- [ ] 手动测试 cbc 全流程：spawn / task / restart / branch / takeover / kill
- [ ] 每个 commit 都能独立通过测试

---

## 十二、风险与回滚

### 12.1 风险点

1. **Worker 加 adapter 字段后，tests 里的 `_setup_worker` 需要同步改**
   - 缓解：步骤 3 明确指出 test 文件需要更新
   - 已在测试代码里标注修改点

2. **`build_spawn_args` 的参数顺序与原 _spawn_process 不一致可能导致 cbc 启动失败**
   - 原 `_spawn_process` 顺序：base → model → permission_mode → effort → thinking → resume → extra
   - CbcAdapter.build_spawn_args 顺序：base → model → permission_mode → effort → thinking → resume → extra
   - **一致**，无风险

3. **Session 加 adapter 字段，老 session 文件反序列化**
   - `Session(**data)` 时 data 没有 `adapter` 键 → 用 dataclass 默认值 `"cbc"`
   - 验证：写个临时脚本扫描 `data/sessions/*.json`，确认加载后 `s.adapter == "cbc"`

4. **`_replaying` 状态机保留在 worker.py，但 `supports_resume` 影响 `create_worker` 的初始 `_replaying` 值**
   - cbc: `supports_resume = True`，行为不变
   - 其他 adapter: `supports_resume = False`，永不进入 replay 模式
   - 但 `_read_stdout` 里 `if w._replaying: ...` 的逻辑仍会执行（只是永远进不去）
   - 无风险

5. **`api_takeover` 改用 `subprocess.Popen` 的 `cwd=` 参数后，PowerShell 启动行为可能变化**
   - 原本 `cd "workdir"; cbc --resume ...` 是 PowerShell 内部 cd
   - 改后 `Popen(..., cwd=s.workdir)` 是父进程设 cwd
   - 两者效果相同（PowerShell 继承父进程 cwd）
   - 验证：手动测试 takeover，确认 PowerShell 打开后 `pwd` 是 workdir

### 12.2 回滚策略

- 每步独立 commit，回滚到上一步即可
- 步骤 3（worker.py 大改）是最关键的，如果测试不过，回滚到步骤 2
- 如果步骤 7 后手动测试发现问题，可以单独回滚步骤 7（server.py 改动小且独立）

---

## 十三、未来扩展（不在本次范围）

### 13.1 第二个 adapter 实现模板

未来加 claude-cli adapter 时：

```python
# src/adapters/claude.py
class ClaudeAdapter:
    name = "claude"
    default_model = "claude-sonnet-4"
    supported_models = ["claude-sonnet-4", "claude-opus-4", ...]
    supports_resume = True  # claude --resume
    supports_fork = False

    def base_args(self):
        return [CLAUDE_PATH, "--output-format", "jsonl", "--input-format", "jsonl"]

    def thinking_args(self, s):
        if s.always_thinking_enabled:
            return ["--thinking"]
        return []

    # ... 实现其他协议方法

# src/adapters/__init__.py 加一行
from .claude import ClaudeAdapter
register("claude", ClaudeAdapter())
```

worker.py 完全不用改。

### 13.2 协议演进方向

- 第二个 adapter 实现后，如果发现 `extract_assistant_blocks` 的返回格式不够通用，升级为返回 `dataclass Event`
- 如果多个 adapter 都需要"任务进度"概念，加 `extract_progress(event) -> float | None`
- 如果需要 adapter 级别的配置（API key 等），加 `AdapterConfig` dataclass

### 13.3 server.py 多 adapter 支持演进

`/api/models` 当前返回默认 adapter 的模型清单。未来改为：
```python
@app.get("/api/models")
async def api_models(adapter: str = "cbc"):
    a = get_adapter(adapter)
    return {"models": a.supported_models, "default": a.default_model}
```

`/api/sessions` 创建时支持指定 adapter：
```python
def _build_session_params(data: dict) -> dict:
    return {
        "adapter": data.get("adapter") or "cbc",
        ...
    }
```

---

## 十四、附：阶段 1 完成状态确认

阶段 1 的 5 项前置清理已在 dev 分支完成（5 个 commits）：

```
5450990 refactor(worker): make create_worker and branch_worker reuse _spawn_process
cb4f469 refactor(server): extract Session field helpers, fix api_rename decoupling
fdf848b fix(worker): unify --model default value and align arg order
c2218ca fix(worker): make CBC_PATH configurable via env var
14701ed fix(worker): remove __import__ anti-pattern
```

阶段 1 验收：
- [x] spawn 路径收敛到 `_spawn_process` 单一入口
- [x] Session 字段提取/更新收敛到 `_build_session_params` / `_apply_session_updates`
- [x] `--model` 默认值统一
- [x] `__import__("datetime")` 清理
- [x] `CBC_PATH` 配置化

**阶段 1 完成，可以开始阶段 2。**

---

## 十五、本文档执行清单

实施者（DS-V4-Pro）按以下顺序执行，每步完成后 commit：

- [ ] 步骤 1：创建 `src/adapters/` 目录及文件
- [ ] 步骤 2：Session 加 `adapter` 字段
- [ ] 步骤 3：worker.py 引入 adapter（含 tests 更新）
- [ ] 步骤 4：`_read_stdout` 改造
- [ ] 步骤 5：`_consumer` 改造
- [ ] 步骤 6：`restart_worker` / `respawn_worker` / `branch_worker` 改造
- [ ] 步骤 7：server.py 微调（effort_args + takeover 修复）
- [ ] 步骤 8：最终验证（测试 + 手动）
- [ ] 步骤 9：文档同步

预计每步 1-3 个 commit，总计 8-12 个 commit。
