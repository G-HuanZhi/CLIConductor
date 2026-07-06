# Resume From CLI — 将 cbc 的可恢复 Session 导入 CLIConductor

**制定日期**: 2026-07-05
**关联文档**: [cbc reference](../references/cbc-reference.md)
**目标**: 导入 cbc CLI 中已存在的交互式 session，在 CLIConductor 中重建完整历史，使其和本地创建的 session 别无二致。

---

## 一、背景

用户在日常开发中会用 `cbc` 直接交互（打开终端对话），这些 session 的历史保存在 `~/.codebuddy/projects/<project-id>/` 下。目前已积累 60+ 个 session，但 CLIConductor 完全看不到它们。

目标是让 CLIConductor 能够列出这些外部 session、导入历史、并在 worker 中通过 `--resume` 恢复上下文继续对话。

---

## 二、cbc Session 存储机制

### 2.1 存储路径

```
~/.codebuddy/
├── projects/
│   └── <project-id>/              # 如 d-project-CLIConductor
│       ├── <session-id>.jsonl     # 完整对话历史（JSON Lines）
│       └── <session-id>.meta.json # 元数据（forkedFrom, forkedAt）
├── history.jsonl                  # 全局对话历史（供 /resume 使用）
├── file-history/                  # /rewind 所用的文件快照
└── sessions/                      # 活跃 session 数据
```

`<project-id>` 是项目路径的 sanitized 形式（如 `d-project-CLIConductor`）。

### 2.2 JSONL 事件格式

每行一个 JSON 对象，已知事件类型：

| 类型 | 说明 | 关键字段 |
|---|---|---|
| `message` | 用户或助手消息 | `role` (user/assistant), `message.content` |
| `reasoning` | 思考链 | `reasoning`, `providerData` |
| `function_call` | 工具调用 | `name`, `args`, `callId` |
| `function_call_result` | 工具结果 | `callId`, `output` |
| `custom-title` | 自定义标题 | — |
| `file-history-snapshot` | 文件快照（/rewind 用） | — |

### 2.3 .meta.json 格式

```json
{
  "forkedFrom": "74f4e9cb-bb29-4b79-a552-20478b3658bc",
  "forkedAt": 1783182834820
}
```

### 2.4 获取 Session 列表的方式

**方式 A — 文件系统直接读（推荐）**：
- 遍历 `~/.codebuddy/projects/<project-id>/` 下的所有 `.jsonl` 文件
- 读取对应的 `.meta.json` 获取元数据
- 从第一条和最后一条 JSONL 行提取摘要信息（首条消息、时间戳）

**方式 B — cbc HTTP API（需 cbc 在运行）**：
- `GET /api/v1/sessions?cwd=D:\project\CLIConductor`
- 返回该 workspace 下所有 session 列表
- 需要 `X-CodeBuddy-Request: 1` header
- 需要 cbc 在后台运行 (`cbc --serve`)

**方式 C — cbc 交互式选择器（无法程序化）**：
- `cbc --resume` 打开 TUI 选择器
- 有摘要、消息数、耗时、git branch
- 仅交互式，无法被程序调用

### 2.5 `--resume` 的完整行为

```
cbc --resume <session-id> "新的提示词"
cbc --resume <session-id> -p "新的提示词"
```

- 反序列化完整历史，恢复所有上下文
- 保留工具调用和结果
- 使用原始对话的 model 和配置
- 在 headless 模式 (`-p --output-format stream-json`) 下同样可用

### 2.6 `--replay-user-messages`（未文档化）

```
cbc --replay-user-messages
```

根据 `--help` 描述："Re-emit user messages from stdin back on stdout for acknowledgment (only works with --input-format=stream-json and --output-format=stream-json)"

这是一个调试/回放标志，在从 stdin 发送用户消息时，将用户消息回显到 stdout。用于在非交互模式下确认用户的输入已被接收。**与我们的需求无关**（我们不需要回显，需要的是 `--resume` 恢复上下文）。

---

## 三、探索结论

### 3.1 什么参数可以获取可 resume 的 cbc session ID？

- **文件系统扫描**是最可靠的方式：读 `~/.codebuddy/projects/<project-id>/` 下的 JSONL 文件即可获取所有 session ID
- cbc 内建的 HTTP API `/api/v1/sessions?cwd=<path>` 可以返回更丰富的元数据，但需要 cbc 在运行
- 对于 CLIConductor 这种 cbc 子进程管理器，**文件系统扫描是正确方案**——CLIConductor 启动 cbc 子进程，不依赖 cbc 的 HTTP API

### 3.2 怎么利用 replay 健壮地重建历史？

- **不需要 `--replay-user-messages`**。这个标志是用于 stdin/stdout 回显确认的，与历史重建无关
- 正确的做法：直接解析 JSONL 文件，将 cbc 的 internal event 类型映射为 CLIConductor 的 history 格式
- 然后用 `--resume <session-id>` 启动 cbc worker，cbc 会自行恢复上下文

---

## 四、实现设计

### 4.1 整体架构

```
                     ┌──────────────────────────┐
                     │    CLIConductor Server    │
                     └──────────────────────────┘
                              │          │
                     ┌────────┘          └──────────┐
                     ▼                              ▼
            ┌───────────────┐              ┌─────────────────┐
            │ GET /api/cbc/ │              │ POST /api/cbc/   │
            │ sessions      │              │ sessions/import  │
            └───────────────┘              └─────────────────┘
                     │                              │
                     ▼                              ▼
            ┌───────────────┐              ┌─────────────────┐
            │ scan filesystem│             │ parse JSONL      │
            │ ~/.codebuddy/  │             │ → CLIConductor   │
            │ projects/**/*.jsonl           │ session.history  │
            └───────────────┘              │ → save session   │
                                           │ → broadcast WS   │
                                           └─────────────────┘
```

### 4.2 文件结构（已实现）

```
src/adapters/
├── __init__.py              # re-exports from subpackages
├── base.py                  # CliAdapter protocol
├── registry.py              # register/get_adapter/list_adapters
└── cbc/
    ├── __init__.py           # from .adapter import CbcAdapter
    ├── adapter.py            # CbcAdapter 类（原 cbc.py）
    └── sessions.py           # ← 新建：list_cbc_sessions + parse_cbc_history
```

将来接 ClaudeAdapter 时：
```
src/adapters/claude/
├── __init__.py
├── adapter.py
└── sessions.py   # 扫 ~/.claude/sessions/，格式不同但接口一致
```

### 4.3 模块设计

#### `src/cbc_sessions.py`

**`list_cbc_sessions(project_cwd: str) -> list[dict]`**

扫描 `~/.codebuddy/projects/` 下匹配 `project_cwd` 的目录，返回所有 session 摘要：

```python
def list_cbc_sessions(project_cwd: str = None) -> list[dict]:
    """Return list of cbc sessions with metadata.

    Each entry:
    {
        "session_id": "uuid",
        "project_dir": "d-project-CLIConductor",
        "title": "Auto-extracted from first message or custom-title",
        "message_count": 42,
        "first_timestamp": "2026-07-01T10:00:00",
        "last_timestamp": "2026-07-01T12:30:00",
        "model": "deepseek-v4-pro",       # from providerData
        "forked_from": "other-session-id", # from .meta.json, optional
    }
    """
```

**实现细节**：
- 遍历 `~/.codebuddy/projects/` 下的所有子目录
- 筛选项目目录名包含 `project_cwd`（sanitized 匹配）
- 对每个 `.jsonl` 文件：
  - 读取第一行获取起始时间戳和会话信息
  - 读取最后一行获取结束时间戳
  - 统计总行数 = message_count
  - 提取 `custom-title` 或首条 user message 作为 title
  - 从 `providerData.model` 提取模型名
- 读取对应的 `.meta.json` 获取 fork 关系

**`parse_cbc_history(session_id: str, project_cwd: str) -> list[dict]`**

解析单个 session 的 JSONL，转为 CLIConductor history 格式：

```python
def parse_cbc_history(session_id: str, project_cwd: str) -> list[dict]:
    """Parse cbc session JSONL to CLIConductor history format.

    Returns list of history blocks:
    [
        {"role": "user", "content": "user message"},
        {"role": "thinking", "content": "thinking block"},
        {"role": "assistant", "content": "assistant reply"},
        {"role": "tool", "content": "tool call: Bash\ncmd: ls"},
    ]
    """
```

**映射规则**（已实测验证）：

| cbc JSONL type | content 格式 | CLIConductor role | 内容提取方式 |
|---|---|---|---|
| `message` (user) | `content[type=input_text].text` | `user` | 提取 `input_text` 的 text |
| `message` (assistant) | `content[type=output_text].text` | `assistant` | 提取 `output_text` 的 text |
| `reasoning` | `content[0].text` (list of dict) | `thinking` | 提取 content list 中所有 text |
| `function_call` | `name` + `args`/`input` 字段 | `tool` | `"tool call: {name}\nargs: {args}"` |
| `function_call_result` | `name` + `output` (dict/str) | `tool` | `"tool result: {name}\n{output[:500]}"` |
| `custom-title` | — | **跳过** | 元数据，不放入 history |
| `file-history-snapshot` | — | **跳过** | 内部事件，不放入 history |
| `summary` | — | **跳过** | 压缩标记，不放入 history |

**注意**：
- `summary` 是 cbc compact 后的标记事件，不放入 history
- 工具结果截断到 500 字符避免过长
- `function_call` 的 args 字段可能为空 `{}`（compact session），此时显示为 `args: {}`

#### `src/server.py` 新增端点

**`GET /api/cbc/sessions?cwd=<path>`**

返回可导入的 cbc session 列表。

```python
@app.get("/api/cbc/sessions")
async def api_cbc_sessions(cwd: str = None):
    sessions = cbc_sessions.list_cbc_sessions(cwd)
    return {"sessions": sessions}
```

**`POST /api/cbc/sessions/import`**

导入指定的 cbc session 到 CLIConductor：

```python
@app.post("/api/cbc/sessions/import")
async def api_cbc_sessions_import(data: dict):
    session_id = data.get("session_id")
    name = data.get("name", f"cbc-{session_id[:8]}")
    
    # 1. 解析历史
    history = cbc_sessions.parse_cbc_history(session_id, ...)
    
    # 2. 创建 CLIConductor Session
    s = sess.create(
        name=name,
        cbc_session_id=session_id,  # 标记外源 session
        history=history,
    )
    
    # 3. 广播
    await broadcast({"type": "session.created", ...})
    return s.to_dict()
```

**`POST /api/cbc/sessions/import` — 完整流程**

当需要**立即创建 worker 并恢复上下文**时：

```python
@app.post("/api/cbc/sessions/import")
async def api_cbc_sessions_import(data: dict):
    session_id = data.get("session_id")
    
    # 1. 解析历史 → CLIConductor 格式
    history = cbc_sessions.parse_cbc_history(session_id, ...)
    
    # 2. 创建 session（带历史 + cbc 回链）
    s = sess.create(name=..., cbc_session_id=session_id, history=history)
    
    # 3. 创建 worker —— CbcAdapter 的 resume_args 会自动加 --resume
    #    因为 s.cbc_session_id 已设置
    worker_id = await worker.create_worker(s.id)
    
    # 4. cbc 启动时会用 --resume <session_id> 自动恢复上下文
    #    worker.py 的 _read_stdout 会正常处理 stdout 事件
    
    return {"sessionId": s.id, "workerId": worker_id, "name": s.name}
```

**为什么用 `--resume` 而不是直接喂历史？**

- `--resume` 让 cbc 自行反序列化完整历史，包括工具调用结果
- 我们只需在 CLIConductor 侧同步记录历史用于 UI 展示
- 避免重复实现 cbc 的消息编解码逻辑

#### `src/adapters/cbc.py` — resume_args 已有

现有代码 `CbcAdapter.resume_args(s)` 已经处理了 `--resume`：

```python
def resume_args(self, s: Session) -> list[str]:
    if s.cbc_session_id:
        return ["--resume", s.cbc_session_id]
    return []
```

**无需修改 adapter。** 只要 session 的 `cbc_session_id` 被正确设置，worker 启动时就会自动附加 `--resume`。

### 4.4 前端改动

在 index.html 的 session 列表中增加一个"Import from cbc"按钮（或在 New Session 旁加下拉）：

1. 点击后调用 `GET /api/cbc/sessions` 获取候选列表
2. 展示模态框/面板，列出可导入的 session（标题、消息数、时间）
3. 用户选择一个，调用 `POST /api/cbc/sessions/import`
4. 导入后自动选中新 session，开始展示历史

前端实现细节由适配阶段决定，核心是先打通后端链路。

---

## 五、风险与限制

| 风险 | 说明 | 应对 |
|---|---|---|
| JSONL 解析错误 | 部分行可能超长或格式异常 | 逐行 try/except，跳过坏行 |
| 大文件 | 长对话 JSONL 可能几十 MB | 只读首尾行获取元数据；完整解析时流式处理 |
| `history.jsonl` vs `projects/` | 两者都存历史，格式可能略有不同 | 优先读 `projects/` 下的 project-specific JSONL |
| `--resume` 需要 cbc session 未过期 | cbc 的 session 可能因清理机制被删除 | 先检查 JSONL 文件存在性 |
| 工具结果超大 | function_call_result 的 content 可能非常大 | 截断到 500 字符 |
| session 跨项目 | cbc session 可能属于不同的 project 目录 | `cwd` 参数允许指定目标项目 |

---

## 五-bis、Session 过滤策略（待决策）

并非所有 cbc session 都适合导入。以当前 `d-project-CLIConductor` 下 58 个 session 为例，需要过滤以下类别：

### 5.1 已在 CLIConductor 的 Session

CLIConductor 创建的 session 本身就由 cbc 子进程驱动，`cbc_session_id` 字段已经记录。导入时需跳过这些 session ID，避免重复。

**识别方式**：数据库/磁盘已有同名 `cbc_session_id` 的 Session 记录。

### 5.2 派生 Session（Fork / Branch）

使用 `/branch` 或 `/fork` 创建的 session 在 `.meta.json` 中有 `forkedFrom` 字段。这些是从另一个 session 分支出来的，历史与父 session 重叠。

**决策点**：默认隐藏（只列"根 session"）还是全部列出？前者更干净，后者给用户选择权。

### 5.3 空 / 废弃 Session

部分 session 的 JSONL 非常短（如 `947eba46` 仅 4 行），可能是误创建或只发了一条消息就放弃的。

**决策点**：设置最小消息数阈值（建议 ≥ 5 条才显示），或在前端标记"短对话"供用户判断。

### 5.4 其他 Workdir 的 Session

cbc 为每个 workdir 创建独立的 project 目录（如 `d-project-CLIConductor-dev-data-workdirs-session-1`）。这些 session 属于某个已被删除的 workdir，不应导入。

**识别方式**：`project_dir` 名包含 `-data-workdirs-` 后缀的跳过；或仅接受 `project_dir` 精确匹配主项目目录的。

### 5.5 时间衰减

不是所有历史 session 都有保留价值。可以按最后活跃时间排序，前端仅显示最近 N 个（如 30 个），或加入时间过滤。

### 建议的默认策略

```
列表 API 默认过滤条件：
1. 已在 CLIConductor 中的 session → 跳过
2. project_dir 不匹配主工作目录的（-data-workdirs- 后缀）→ 跳过
3. 消息数 < 5 → 跳过
4. 按最后时间戳倒序排列
5. 可带 ?all=1 查询参数绕过过滤（调试用）
```

**前端展示**：在候选列表中用 icon 区分"根 session"和"分支 session"，让用户知道来源。

---

## 六、实操步骤（详细实现方案）

### Phase 1 — 后端核心

#### 1.1 `src/adapters/cbc/sessions.py` ← 已完成 (2026-07-05) ✅

已完成内容见上方 Phase 1.1，不再重复。

#### 1.2 配置系统 — 新增 `src/config.py`

当前项目无集中配置系统。需要新增一个简单的配置文件，存储 session 过滤策略的参数。

**文件**: `src/config.py` (新建)

```python
"""CLIConductor configuration."""
import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent.parent / "config.json"

DEFAULT_CONFIG = {
    "cbc_import": {
        "min_message_count": 5,
        "max_sessions_shown": 30,
        "exclude_workdir_patterns": ["-data-workdirs-"],
        "project_dir_exact_match": False,  # 是否仅接受精确匹配的 project_dir
    }
}


def load_config():
    if not CONFIG_FILE.exists():
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
    # Deep merge with defaults
    return _deep_merge(DEFAULT_CONFIG, config)


def _deep_merge(base, override):
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
```

**配置文件**: `config.json` (新建，在项目根目录)

```json
{
  "cbc_import": {
    "min_message_count": 5,
    "max_sessions_shown": 30,
    "exclude_workdir_patterns": ["-data-workdirs-"],
    "project_dir_exact_match": false
  }
}
```

**说明**: 配置文件放在项目根目录，由 `config.json` 加载。`_deep_merge` 确保新增字段有默认值、用户只覆盖他们关心的字段。无需环境变量或命令行参数，直接编辑 JSON 即可。

#### 1.3 API 端点 — `src/server.py`

在现有 `src/server.py` 中添加两个新端点。当前 server.py 无 Router 分层，直接追加即可。

**3.1 新增 import**（在现有 import 行之后新增一行）

```python
from .adapters.cbc import sessions as cbc_sessions
from .config import load_config
```

插入位置：`src/server.py` 第 18 行后（`from .adapters import get_adapter` 之后）。

**3.2 `GET /api/cbc/sessions?cwd=<path>[&all=1]`**

列出可导入的外部 cbc session。放在现有 `/api/list` (约第 545 行) 之后。

```python
@app.get("/api/cbc/sessions")
async def api_cbc_sessions(cwd: str = "", all: int = 0):
    """List external cbc sessions available for import."""
    config = load_config()
    filter_cfg = config.get("cbc_import", {})

    cwd = cwd or str(Path.cwd())
    all_sessions = cbc_sessions.list_cbc_sessions(cwd)

    if all:
        # Debug mode: return everything
        return {"sessions": all_sessions, "total": len(all_sessions)}

    # Filter 1: skip if already in CLIConductor
    existing_cbc_ids = set()
    for s in sess.list_all():
        if s.cbc_session_id:
            existing_cbc_ids.add(s.cbc_session_id)

    # Filter 2: skip non-main workdir sessions
    exclude_patterns = filter_cfg.get("exclude_workdir_patterns", [])
    if filter_cfg.get("project_dir_exact_match", False):
        import hashlib
        target_dir = _sanitize_project_dir(cwd)
    else:
        target_dir = None

    filtered = []
    for s in all_sessions:
        # Filter 1
        if s["session_id"] in existing_cbc_ids:
            continue
        # Filter 2
        if target_dir and s["project_dir"] != target_dir:
            continue
        if not target_dir and any(p in s["project_dir"] for p in exclude_patterns):
            continue
        # Filter 3: min message count
        if s["message_count"] < filter_cfg.get("min_message_count", 5):
            continue
        filtered.append(s)

    # Sort by last_timestamp desc
    filtered.sort(key=lambda x: x.get("last_timestamp", ""), reverse=True)

    # Limit
    max_shown = filter_cfg.get("max_sessions_shown", 30)
    total = len(filtered)
    filtered = filtered[:max_shown]

    return {
        "sessions": filtered,
        "total": total,
        "shown": len(filtered),
    }


def _sanitize_project_dir(cwd: str) -> str:
    """Mirror cbc's sanitize logic. Move to sessions.py later if needed."""
    import re
    p = cwd.replace(":", "")
    p = p.replace("\\", "-").replace("/", "-")
    p = re.sub(r"^[-]+", "", p)
    p = re.sub(r"[-]+", "-", p)
    return p.lower()
```

**3.3 `POST /api/cbc/sessions/import`**

导入指定的 cbc session，只创建 CLIConductor Session（不 spawn worker）。

```python
@app.post("/api/cbc/sessions/import")
async def api_cbc_sessions_import(data: dict):
    """Import a cbc session into CLIConductor (Session only, no worker)."""
    session_id = data.get("session_id")
    if not session_id:
        return {"error": "session_id is required"}

    cwd = data.get("cwd") or str(Path.cwd())

    # Check if already imported
    for s in sess.list_all():
        if s.cbc_session_id == session_id:
            return {"error": f"Session {session_id} already imported as {s.id}"}

    try:
        history = cbc_sessions.parse_cbc_history(session_id, cwd)
    except Exception as e:
        return {"error": f"Failed to parse session history: {e}"}

    name = data.get("name", "") or f"cbc-{session_id[:8]}"

    s = sess.create(
        name=name,
        cbc_session_id=session_id,
        history=history,
    )

    await broadcast({
        "type": "session.created",
        "sessionId": s.id,
        "name": s.name,
    })

    return _session_to_api(s)
```

**3.4 注意事项**

- `_sanitize_project_dir` 可以先放在 server.py 底部，后续重构时移到 `sessions.py`（因为它和 `sessions.py._project_dir` 逻辑重复）。
- 导入端点不自动 spawn worker——用户看到历史后可手动点 Send 触发 spawn。
- `cwd` 参数在各端点间保持一致，默认用 `Path.cwd()`。

### Phase 2 — 前端

#### 2.1 TypeScript 源码位置

- 源文件: `ts/app.ts` (838 行)
- 编译输出: `static/js/app.js`
- HTML 模板: `index.html`

#### 2.2 新增 API 调用函数

在 `ts/app.ts` 中添加两个函数（放在 `refreshSessions()` 附近，约第 192 行后）：

```typescript
async function fetchCbcSessions(cwd: string = '') {
  const params = cwd ? `?cwd=${encodeURIComponent(cwd)}` : '';
  const resp = await fetch(`/api/cbc/sessions${params}`);
  const data = await resp.json();
  return data.sessions || [];
}

async function importCbcSession(sessionId: string, cwd: string = '') {
  const resp = await fetch('/api/cbc/sessions/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, cwd }),
  });
  return await resp.json();
}
```

#### 2.3 HTML 新增: Import 按钮 + 模态框

在 `index.html` 的 sidebar 中 "New Session" 按钮旁新增 Import 按钮，以及模态框结构。

**sidebar 区域修改**（`index.html` 第 10 行附近）：

```html
<div id="sidebar">
  <h1>CLIConductor</h1>
  <div style="display:flex; gap:4px; margin-bottom:8px;">
    <button id="newSessionBtn" title="New Session" style="flex:1;">+ New</button>
    <button id="importCbcBtn" title="Import from cbc">↓ Import</button>
  </div>
  <div id="sessionList"></div>
</div>
```

**模态框**（放在 `#inputRow` 之后、`#toast` 之前，约第 53 行）：

```html
<!-- Import Modal -->
<div id="importModal" style="display:none; position:fixed; inset:0;
  background:rgba(0,0,0,0.5); z-index:1000; align-items:center; justify-content:center;">
  <div style="background:var(--bg); border:1px solid var(--border);
    border-radius:8px; padding:20px; width:480px; max-height:70vh; display:flex; flex-direction:column;">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
      <b>Import cbc Session</b>
      <button id="closeImportModal" style="background:none; border:none; cursor:pointer; font-size:18px;">&times;</button>
    </div>
    <div id="cbcSessionList" style="flex:1; overflow-y:auto; max-height:50vh;"></div>
    <div style="margin-top:8px; font-size:12px; color:#888;" id="cbcSessionCount"></div>
  </div>
</div>
```

**样式补充**（追加到 `static/css/styles.css`）：

```css
.cbc-sess-item {
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  margin-bottom: 6px;
  cursor: pointer;
}
.cbc-sess-item:hover {
  background: var(--hover, #2a2a2a);
}
.cbc-sess-item .cbc-title {
  font-weight: 500;
}
.cbc-sess-item .cbc-meta {
  font-size: 12px;
  color: #888;
  margin-top: 2px;
}
```

#### 2.4 TypeScript: 模态框逻辑

在 `ts/app.ts` 的 `init()` 中添加事件绑定（约第 770 行，init 函数末尾）：

```typescript
// Import modal
const importCbcBtn = document.getElementById('importCbcBtn') as HTMLButtonElement;
const importModal = document.getElementById('importModal') as HTMLDivElement;
const closeImportModal = document.getElementById('closeImportModal') as HTMLButtonElement;
const cbcSessionList = document.getElementById('cbcSessionList') as HTMLDivElement;
const cbcSessionCount = document.getElementById('cbcSessionCount') as HTMLDivElement;

importCbcBtn.addEventListener('click', async () => {
  importModal.style.display = 'flex';
  cbcSessionList.innerHTML = '<div style="padding:12px; color:#888;">Loading...</div>';
  try {
    const sessions = await fetchCbcSessions();
    if (sessions.length === 0) {
      cbcSessionList.innerHTML = '<div style="padding:12px; color:#888;">No sessions to import.</div>';
      cbcSessionCount.textContent = '';
      return;
    }
    cbcSessionCount.textContent = `${sessions.length} session(s) found`;
    cbcSessionList.innerHTML = sessions.map((s: any) => {
      const ts = s.last_timestamp ? new Date(s.last_timestamp).toLocaleString() : '';
      const forkBadge = s.forked_from ? ' 🔀' : '';
      return `
        <div class="cbc-sess-item" data-session-id="${s.session_id}">
          <div class="cbc-title">${escapeHtml(s.title || 'Untitled')}${forkBadge}</div>
          <div class="cbc-meta">
            ${s.message_count} msgs · ${s.model || '?'} · ${ts}
          </div>
        </div>`;
    }).join('');

    // Click to import
    cbcSessionList.querySelectorAll('.cbc-sess-item').forEach(el => {
      el.addEventListener('click', async () => {
        const sid = (el as HTMLElement).dataset.sessionId!;
        (el as HTMLElement).style.opacity = '0.5';
        (el as HTMLElement).style.pointerEvents = 'none';
        const result = await importCbcSession(sid);
        if (result.error) {
          showToast(result.error);
          (el as HTMLElement).style.opacity = '1';
          (el as HTMLElement).style.pointerEvents = '';
          return;
        }
        importModal.style.display = 'none';
        await refreshSessions();
        selectSession(result.id);
        showToast('Session imported');
      });
    });
  } catch (e: any) {
    cbcSessionList.innerHTML = `<div style="padding:12px; color:#c00;">Error: ${e.message}</div>`;
  }
});

closeImportModal.addEventListener('click', () => {
  importModal.style.display = 'none';
});

// Click outside modal to close
importModal.addEventListener('click', (e) => {
  if (e.target === importModal) {
    importModal.style.display = 'none';
  }
});
```

#### 2.5 辅助函数

如果 `ts/app.ts` 还没有 `escapeHtml`：

```typescript
function escapeHtml(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
```

#### 2.6 编译

修改 `ts/app.ts` 后，需重新编译：

```bash
npx tsc -p ts/tsconfig.json
```

或者如果项目有构建脚本，执行对应的 build 命令。

### Phase 3 — 测试

#### 手动测试步骤

1. **准备**: 确保 `~/.codebuddy/projects/d-project-CLIConductor/` 下有历史 session JSONL 文件。
2. **启动**: `python main.py`
3. **验证**: 浏览器打开 http://127.0.0.1:8767
4. **列出**: 点击 sidebar 的 "↓ Import" 按钮 → 模态框应列出可导入 session
5. **过滤**: 验证消息数 < 5 的 session 不在列表中、已有 CLIConductor session 的 cbc session 不在列表中
6. **详情**: 验证每条显示 title、消息数、model、时间戳
7. **导入**: 点击一条 → 模态框关闭 → 左侧 session 列表新增该 session
8. **历史**: 选中新 session → 查看 messages 区域是否展示完整历史（含 user/assistant/thinking/tool 块）
9. **恢复**: 在 input 框输入消息并 Send → worker 应启动并带 `--resume` 参数 → 后续对话正常

#### API 测试（curl）

```bash
# 列出可导入 session
curl "http://127.0.0.1:8767/api/cbc/sessions"

# 列出全部（不过滤）
curl "http://127.0.0.1:8767/api/cbc/sessions?all=1"

# 导入指定 session
curl -X POST "http://127.0.0.1:8767/api/cbc/sessions/import" \
  -H "Content-Type: application/json" \
  -d '{"session_id": "your-session-uuid"}'
```

---

## 七、参考

- cbc session 存储文档：`codebuddy-dir.md` §`projects/`
- cbc resume 文档：`common-workflows.md` §"Resume a conversation"
- cbc HTTP API：`http-api.md` §"Sessions"
- cbc SDK session 管理：`sdk-sessions.md`
- cbc CLI 参考：`cli-reference.md` §`--resume`
- cbc reference (CLIConductor)：`docs/references/cbc-reference.md` §1.6
