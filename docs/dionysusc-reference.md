# DionysusC 架构分析 — CLIConductor 参考文档

> 分析日期：2026-06-26
> 目的：理解 DionysusC 的 CLI 进程管理方案，为 CLIConductor 重构提供参考

---

## 一、项目概况

DionysusC 是一个带 Live2D 二次元皮肤的 **CLI Agent 桌面客户端**。它包装了 Kimi Code、Claude Code、Codex、OpenCode、CodeBuddy 等命令行编程助手，提供统一的 GUI 交互体验。

**本质**：CLI 进程管理器 + 前端 GUI。核心逻辑是 Python FastAPI 后端通过 `asyncio` 子进程调用外部 CLI，从 stdout 解析结构化输出，传递给 React 前端。

---

## 二、架构全貌

```
┌──────────────────────────────────────────────────────┐
│                    Electron Shell                     │
│                                                       │
│  ┌──────────────────┐    ┌─────────────────────────┐ │
│  │  React 前端      │    │  Python FastAPI 后端     │ │
│  │  (localhost:5173) │◄──►│  (localhost:8765)       │ │
│  │                   │ WS │                          │ │
│  │  PixiJS + Live2D │    │  ┌─────────────────┐    │ │
│  │  Zustand 状态管理 │    │  │ SessionManager  │    │ │
│  │  Tailwind CSS    │    │  │ (中心调度器)     │    │ │
│  └──────────────────┘    │  └───────┬─────────┘    │ │
│                           │          │               │ │
│                           │  ┌───────▼────────┐     │ │
│                           │  │ AdapterRegistry │     │ │
│                           │  └───────┬────────┘     │ │
│                           │          │               │ │
│                           │  ┌───────▼────────┐     │ │
│                           │  │GenericCLIAdapter│     │ │
│                           │  │ ┌─────────────┐ │     │ │
│                           │  │ │  Strategy   │ │     │ │
│                           │  │ │ Kimi/Claude │ │     │ │
│                           │  │ │ /Codex/...  │ │     │ │
│                           │  │ └─────────────┘ │    │ │
│                           │  └───────┬────────┘     │ │
│                           │          │               │ │
│                           │  asyncio subprocess     │ │
│                           │  "kimi -p 'text'"       │ │
│                           └──────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

---

## 三、核心机制详解

### 3.1 单次调用 + Session ID 续接

**不使用长驻进程。每次用户消息都重新 spawn**：

```python
# 第一轮
process = await asyncio.create_subprocess_exec(
    "kimi", "-p", "帮我重构 auth 模块",
    "--output-format", "stream-json",
    stdout=PIPE, stdin=PIPE
)
process.stdin.close()  # 立即关闭，告诉 CLI "没有更多输入了"

# 从输出中提取 session_id
session_id = extract_session_id(output)

# 第二轮：带上 session_id 保持上下文
process = await asyncio.create_subprocess_exec(
    "kimi", "-p", "改用 JWT 方案",
    "-S", session_id,  # ← 不同 CLI 用不同参数名
    "--output-format", "stream-json",
    stdout=PIPE, stdin=PIPE
)
```

**各 CLI 的 Session ID 参数对照**：

| CLI | Session ID 参数 | 来源字段 |
|-----|----------------|---------|
| Kimi Code | `-S <id>` | `meta.session.resume_hint.session_id` |
| CodeBuddy Code | `--resume <id>` | `system.init.session_id` |
| Claude Code | `--continue --session-id <id>` | `session_id` |
| Codex | `--thread <id>` | `thread_id` |
| OpenCode | `--session <id>` | `session_id` / `sessionID` |

### 3.2 Strategy 模式 — 核心设计

**三层抽象**：

```
IAgentAdapter (抽象接口)
    └── GenericCLIAdapter (进程管理，各 CLI 通用)
            └── CLIAdapterStrategy (每 CLI 策略)
                    ├── KimiStrategy
                    ├── CodeBuddyStrategy
                    ├── ClaudeStrategy
                    ├── CodexStrategy
                    └── OpenCodeStrategy
```

**通用部分（GenericCLIAdapter ~210 行）**：
- `create_subprocess_exec` 启动进程
- `readline()` 逐行读取 stdout
- `process.kill()` 中断 / 终止
- 超时检测（默认 120s）
- 崩溃重试（最多 3 次）
- stdin 关闭技巧

**策略部分（每个 Strategy ~130 行）**：
- `build_args(text, session_id, mode)` → 构造 CLI 参数
- `handle_line(line)` → 解析 stdout 行为 `AgentEvent`
- `extract_session_id(event)` → 提取 Session ID

### 3.3 中断机制

```python
def interrupt():
    self._process.kill()     # SIGKILL / TerminateProcess
    await wait(5)            # 最多等 5 秒
```

简单粗暴但有效。因为进程是一次性的，kill 了下次 `--resume` 就能恢复。不需要复杂的信号协商。

### 3.4 事件管道 + 多路消费

```python
# SessionManager 中的事件流
async for event in adapter.send(user_message):
    companion_engine.on_event(event)   # → Live2D 表情/台词
    todo_tracker.on_event(event)       # → Todo 列表更新
    yield websocket_packet(event)      # → 前端渲染
```

一个事件流，三个消费者并行观察，互不耦合。这对 CLIConductor 的 Dashboard 实时观察有直接参考价值。

### 3.5 stdin 关闭技巧

```python
if process.stdin is not None:
    process.stdin.close()
    await process.stdin.wait_closed()
```

大多数 CLI 检测到 stdin 开着就会等待更多输入。直接关闭 stdin 告诉它"没更多了，开始执行吧"。

---

## 四、代码量参考

| 模块 | 文件 | 行数 |
|------|------|------|
| GenericCLIAdapter | `agent_adapters/generic_cli.py` | ~210 |
| Strategy 基类 | `agent_adapters/strategy.py` | ~80 |
| 每个具体 Strategy | `strategies/{name}.py` | ~130 |
| SessionManager | `session/manager.py` | ~860 |
| WebSocket Handler | `websocket/handler.py` | ~180 |
| Session Store (SQLite) | `session/store.py` | ~200 |
| **核心逻辑合计** | | **~2100** |

---

## 五、DionysusC 的局限（CLIConductor 要超越的）

| 局限 | 具体表现 | CLIConductor 的目标 |
|------|---------|-------------------|
| **单会话** | 一次只能一个 Agent 在跑 | 多个 Worker 并行 |
| **无自动调度** | 必须用户发消息才执行 | Agent 主动派发任务 |
| **无介入机制** | 进程在跑时用户无法操作 | 随时介入任意 Worker |
| **无 CLI 入口** | 只有 GUI，无命令行控制 | CLI 入口 + Dashboard 双通道 |
| **Python** | 后端用 Python | TypeScript + Node |

---

## 六、对 CLIConductor 的启发

### 可以直接借鉴的

1. **Strategy 模式** — 已验证是管理多 CLI 的正确抽象，和 CLIConductor archive 的 `AgentAdapter` 接口几乎一致
2. **单次 spawn + Session ID** — 比长驻 PTY 更简单、更可靠，和 Phase 1 实验结论一致
3. **stdin 关闭技巧** — 可复制用于 Node.js 的 `child_process.spawn`
4. **事件管道** — 做 Dashboard 实时观察时参考这个模式

### 架构简化方向

DionysusC 证明了**不需要长驻 PTY 进程**。由此可以简化 CLIConductor 的设计：

- Worker 不需要是长驻进程，每次任务一个 spawn 调用
- "介入"可以更轻量：Agent 下一轮 `--resume` 之前插入用户消息
- PTY 只在需要完整交互终端时才启动（`cbc --resume <id>` 不带 `-p`）

### 一个更简洁的 Worker 模型

```
Worker:
  - 不持有长驻进程
  - state: { sessionId, workDir, adapterType, status }
  - execute(task): spawn cbc -p --stream-json --resume <id> task
  - observe(): Dashboard 实时渲染事件流
  - intervene(userMessage): 在下一轮 execute 前注入用户消息
  - takeover(): spawn cbc --resume <id> (交互模式 PTY)
```

---

## 七、关键文件索引

| 文件 | 关注点 |
|------|--------|
| `D:\project\DionysusC\backend\dionysus_server\agent_adapters\generic_cli.py` | 进程生命周期管理 |
| `D:\project\DionysusC\backend\dionysus_server\agent_adapters\strategy.py` | Strategy 接口定义 |
| `D:\project\DionysusC\backend\dionysus_server\agent_adapters\strategies\codebuddy.py` | CodeBuddy Strategy 实现 |
| `D:\project\DionysusC\backend\dionysus_server\session\manager.py` | 统筹调度逻辑 |
