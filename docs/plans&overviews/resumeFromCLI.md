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

### 4.2 新增文件

```
src/
├── cbc_sessions.py          # 扫描 + 解析 cbc session（纯 Python，不引入新依赖）
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

**映射规则**：

| cbc JSONL type | cbc role | CLIConductor role | 内容构建方式 |
|---|---|---|---|
| `message` | `user` | `user` | `message.content` (text) |
| `message` | `assistant` | `assistant` | `message.content` (最后一条 text 块) |
| `reasoning` | — | `thinking` | `reasoning` 字段 |
| `function_call` | — | `tool` | `"tool call: {name}\nargs: {json.dumps(args)}"` |
| `function_call_result` | — | `tool` | `"tool result: {name}\n{output[:500]}"` |
| `custom-title` | — | **跳过** | 元数据，不放入 history |
| `file-history-snapshot` | — | **跳过** | 内部事件，不放入 history |

**注意**：
- 跳过 `file-history-snapshot` 和 `custom-title`（文档明确指出"既不是用户输入也不是助手回复"）
- 工具调用的 `function_call` 和 `function_call_result` 需要按 `callId` 配对展示
- `function_call_result` 的 content 截断到 500 字符避免过长

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

## 六、实操步骤

### Phase 1 — 后端核心

1. [ ] **创建 `src/cbc_sessions.py`**
   - 实现 `list_cbc_sessions(cwd)` — 扫描文件系统
   - 实现 `parse_cbc_history(session_id, cwd)` — 解析 JSONL → CLIConductor history

2. [ ] **添加 API 端点**
   - `GET /api/cbc/sessions?cwd=<path>` — 列出可导入 session
   - `POST /api/cbc/sessions/import` — 导入单个 session + 创建 worker

### Phase 2 — 前端

3. [ ] **添加导入入口**
   - Session 列表页面增加"Import"按钮或下拉
   - 展示候选 session 列表（模态框）
   - 点击导入后自动创建 session

### Phase 3 — 测试

4. [ ] **手动测试**
   - 用 cbc 创建一个本地 session
   - 刷新 CLIConductor，从导入列表中选择该 session
   - 验证历史完整、worker 正常启动、后续对话正常

---

## 七、参考

- cbc session 存储文档：`codebuddy-dir.md` §`projects/`
- cbc resume 文档：`common-workflows.md` §"Resume a conversation"
- cbc HTTP API：`http-api.md` §"Sessions"
- cbc SDK session 管理：`sdk-sessions.md`
- cbc CLI 参考：`cli-reference.md` §`--resume`
- cbc reference (CLIConductor)：`docs/references/cbc-reference.md` §1.6
