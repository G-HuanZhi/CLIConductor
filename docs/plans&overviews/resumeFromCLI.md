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

## 六、实操步骤

### Phase 1 — 后端核心

1. [x] **`src/adapters/cbc/sessions.py`** ← 已完成 (2026-07-05)
   - 实现 `list_cbc_sessions(cwd)` — 扫描 `~/.codebuddy/projects/`，实测 58 个 session
   - 实现 `parse_cbc_history(session_id, cwd)` — 解析 JSONL → CLIConductor history 格式
   - 正确处理 cbc 完整事件格式：`input_text`/`output_text`/`reasoning`/`function_call`/`function_call_result`
   - 跳过 `custom-title`、`file-history-snapshot`、`summary` 等内部事件

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
