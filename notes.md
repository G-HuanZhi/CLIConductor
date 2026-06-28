# CLIConductor 重构研究笔记

> 最后更新：2026-06-28
> 状态：方案研究进行中
> 
> **2026-06-28 更新**：PTY 确认不需要。Agent 日常走 stdin stream-json，用户接管用 `cbc --resume <sid>` 原生终端。所有 PTY 代码已移至 `archive/packages/cbc-bridge/`。

---

## 一、项目背景

### 1.1 项目目标

```
主 Agent 调度管理多个第三方 AI CLI，
且用户可随时介入任何一个 CLI 进程——看到它、操控它、接管它。
```

| 能力 | 说明 |
|------|------|
| 自动调度 | Agent 启动 N 个子 CLI，派发任务，读取结果 |
| 随时介入 | 用户选择任意运行中的子 CLI，看到状态，可插入消息或直接接管终端 |

### 1.2 当前状态

| 维度 | 数量 |
|------|------|
| 产品代码 | 1 个文件 — `packages/cbc-bridge/server.js`（~117 行 WS+PTY 桥接）|
| 实验脚本 | 16 项，一次性代码 |
| 文档/报告 | ~15 份，约 3 万字 |
| npm script | 0 |
| tsconfig.json | 不存在 |
| 测试 | 0 |

**现状诊断**：文档极丰富，产品代码极少。处于从研究到工程的过渡阶段。

### 1.3 项目演化

| Phase | 目标 | 进度 |
|-------|------|:----:|
| Phase 0 | 项目初始化、概念学习 | 100% |
| Phase 1 | 16 项实验验证四种方案 | 100% |
| Phase 2 | 最小可行系统 | 0%（未启动）|
| Phase 3 | Web Dashboard、多适配器 | 待开始 |
| Phase 4 | 完整集群 | 待开始 |

**Phase 1 核心结论**：`child_process.spawn + --resume` 为首选，`node-pty` 为备选。

---

## 二、DionysusC 参考分析

### 2.1 项目概况

DionysusC 是一个带 Live2D 皮肤的 **CLI Agent 桌面客户端**。它包装了 Kimi Code、Claude Code、Codex、OpenCode、CodeBuddy 等命令行编程助手，提供统一的 GUI 交互体验。

**本质**：CLI 进程管理器 + 前端 GUI。核心是 Python FastAPI 后端通过 `asyncio` 子进程调用外部 CLI，从 stdout 解析结构化输出。

### 2.2 架构

```
Electron Shell
 ├── React 前端 (localhost:5173) ←─ WebSocket ─→ Python FastAPI 后端 (localhost:8765)
 │                                                    │
 │                                              SessionManager (中心调度器)
 │                                                    │
 │                                              AdapterRegistry
 │                                                    │
 │                                            GenericCLIAdapter
 │                                              └── Strategy (每 CLI 一个)
 │                                                    │
 │                                            asyncio.create_subprocess_exec
 │                                            "kimi -p 'text' --output-format stream-json"
```

### 2.3 核心机制

#### 单次调用 + Session ID 续接

不使用长驻进程，每次用户消息都重新 spawn：

```python
# 第一轮
process = await asyncio.create_subprocess_exec(
    "kimi", "-p", "帮我重构 auth 模块",
    "--output-format", "stream-json",
    stdout=PIPE, stdin=PIPE
)
process.stdin.close()  # 立即关闭 stdin

# 从输出中提取 session_id
session_id = extract_session_id(output)

# 第二轮
process = await asyncio.create_subprocess_exec(
    "kimi", "-p", "改用 JWT 方案",
    "-S", session_id,  # 保持上下文
    "--output-format", "stream-json",
    stdout=PIPE, stdin=PIPE
)
```

各 CLI 的 Session ID 参数：

| CLI | Session ID 参数 | 来源字段 |
|-----|----------------|---------|
| Kimi Code | `-S <id>` | `meta.session.resume_hint.session_id` |
| CodeBuddy Code | `--resume <id>` | `system.init.session_id` |
| Claude Code | `--continue --session-id <id>` | `session_id` |
| Codex | `--thread <id>` | `thread_id` |
| OpenCode | `--session <id>` | `session_id` / `sessionID` |

#### Strategy 模式

```
IAgentAdapter (抽象接口)
    └── GenericCLIAdapter (进程管理，各 CLI 通用) ~210 行
            └── CLIAdapterStrategy (每 CLI 策略) ~130 行
                    ├── KimiStrategy
                    ├── CodeBuddyStrategy
                    ├── ClaudeStrategy
                    ├── CodexStrategy
                    └── OpenCodeStrategy
```

- `build_args(text, session_id, mode)` — 构造 CLI 参数
- `handle_line(line)` — 解析 stdout 行为事件
- `extract_session_id(event)` — 提取 Session ID

**CLIConductor archive 里的 `AgentAdapter` 接口和这个几乎一模一样**，验证了设计方向。

#### CodeBuddy Strategy 解析细节

`cbc --output-format stream-json` 输出的 event 类型：

| type | 内容 | 处理 |
|------|------|------|
| `system.init` | session_id, model, tools 等 | 提取 session_id |
| `system.status` | 状态更新 | 忽略（内部消费）|
| `file-history-snapshot` | 文件历史快照 | 忽略 |
| `assistant` | content blocks: `thinking` / `text` / `tool_use` / `tool_result` | 解析为事件流 |
| `result` | 最终结果 + `is_error` 标志 | `agent_complete` 事件 |

#### 事件管道 + 多路消费

```python
async for event in adapter.send(user_message):
    companion_engine.on_event(event)   # → Live2D 表情
    todo_tracker.on_event(event)       # → Todo 列表
    yield websocket_packet(event)      # → 前端渲染
```

一个事件流，多个消费者并行观察。

#### stdin 关闭技巧

```python
process.stdin.close()
await process.stdin.wait_closed()
```

大多数 CLI 检测到 stdin 开着就会等待更多输入。关闭 stdin 告诉它"没有更多输入了，开始执行"。

#### 中断机制

```python
def interrupt():
    self._process.kill()
    await wait(5)
```

简单直接。因为进程是一次性的，kill 了下次 `--resume` 就能恢复。

### 2.4 代码量参考

| 模块 | 行数 |
|------|------|
| GenericCLIAdapter | ~210 |
| Strategy 基类 | ~80 |
| 每个具体 Strategy | ~130 |
| SessionManager | ~860 |
| WebSocket Handler | ~180 |
| Session Store (SQLite) | ~200 |
| **核心逻辑合计** | **~2100** |

### 2.5 DionysusC 验证了的 vs 没做到的

**已验证**：

- `spawn + stream-json + --resume` 架构在生产中可用
- Strategy 模式是管理多 CLI 的正确选择
- 事件管道 + 多路消费的模式好用
- 单次进程 + Session ID 续接比长驻 PTY 更稳定

**没有做的**（CLIConductor 的独有价值）：

| 能力 | 为什么需要 |
|------|----------|
| 多 Worker 并行 | Agent 同时调度多台 CLI |
| 自动任务调度 | 不仅响应用户，主动派发任务 |
| 用户介入 | 观察/注入/接管运行中的 Worker |
| CLI 入口 | 命令行操作（spawn/list/send/kill）|
| Worker 注册表 | 统一管理所有 Worker 状态 |

---

## 三、架构核心约束

### 3.1 cbc 的两种模式不可兼得

| 模式 | 启动参数 | 输出 | Agent 视角 | 人类视角 |
|------|---------|------|-----------|---------|
| 程序模式 | `cbc -p --output-format stream-json` | stream-json 行式 JSON | 结构化、好解析 | 无 TUI |
| 交互模式 | `cbc`（无参数）| 原始 TUI + ANSI | 原始文本、难解析 | 完整 TUI |

用户已确认：**需要结构化输出（stream-json）**，因此排除纯 PTY 交互模式。

### 3.2 三种方案对比

| | A: 纯 PTY | B: 程序为主+切换 | C: 程序+观察 |
|------|------|------|------|
| Agent 解析 | 差（TUI 文本）| 好（stream-json）| 好（stream-json）|
| 人类介入 | 实时直接 | 切换延迟 | 间接（注入消息）|
| 架构复杂度 | 低 | 高 | 中 |
| 结论 | **已排除** | 保留考虑 | 保留考虑 |

### 3.3 根目录代码 vs Archive 规划

**根目录**（`packages/cbc-bridge/server.js`）：
- node-pty 长驻交互进程
- 人类 + Agent 双控同一终端
- 单一 CLI 实例

**Archive 规划**：
- child_process.spawn 带参数
- Agent 调度多 CLI 实例
- 程序化接口 + PTY 备选

**本质差异**：根目录是"两个人用一台电脑"，Archive 是"一个人指挥多个工人"。

---

## 四、关键实验：stdin stream 模式

### 4.1 实验动机

问题：反复 `--resume` 每次都要冷启动，能否一个 cbc 进程处理多轮对话？

### 4.2 实验方法

```bash
cbc -p --output-format stream-json --input-format stream-json --replay-user-messages -y
```

通过 stdin 逐轮写入 JSON 格式的 user 消息，观察进程是否在每轮后保持存活。

### 4.3 实验结果

**成功。三轮对话，同一个进程，同一个 session_id，不退出。**

```
Session ID: b6fc1a81-5c77-468b-9dc4-c2b1929318b5
Turn 1: ~4593ms (含 thinking, 冷启动)
Turn 2: ~1761ms (cache 命中)
Turn 3: ~1870ms (cache 命中)
```

| 关键发现 | 详情 |
|---------|------|
| 进程不退出 | 每轮 `result` 事件后继续等待 stdin |
| Context 复用 | 60928 tokens 从 cache 命中，无需重新发送 |
| 无冷启动 | 第 2、3 轮延迟远低于第 1 轮 |
| 消息格式 | `{"type":"user","message":{"role":"user","content":[{"type":"text","text":"..."}]}}` |

### 4.4 实验结论

**每个 Worker 对应一个长驻的 cbc 进程。** 不需要反复 spawn + `--resume`。Agent 往 stdin 写 JSON 任务，stdout 读 JSON 结果。

| 对比维度 | 之前认为的 | 实验验证的 |
|---------|----------|----------|
| 进程模型 | 每次任务 spawn + --resume | 一个长驻进程，stdin 持续写 |
| 启动开销 | 每轮冷启动 | 只在 Worker 创建时启动一次 |
| 上下文保持 | --resume 重新加载 | 进程内存保持 + cache 复用 |
| 多 Worker | 频繁 spawn 开销大 | 一个 Worker = 一个进程 |

---

## 五、推荐方案

### 5.1 方案概述：观察 + 注入 + 接管

基于 stdin stream 模式的验证和结构化输出的要求：

#### 第一层：Agent 控制（正常态）

```
Worker ── spawn ── cbc -p --output-format stream-json --input-format stream-json -y
  ├── Agent 往 stdin 写 JSON 任务
  ├── stdout 逐行解析为结构化事件
  └── 进程一直存活，不退出
```

#### 第二层：用户观察

```
Dashboard ── 显示 stream-json 解析后的事件流
  ├── 对话历史（thinking / text / tool_use / tool_result 分类）
  ├── Worker 状态（idle / running / error）
  └── 当前执行进度
```

#### 第三层：用户注入

```
用户在 Dashboard 输入消息
  → 转换为 stream-json 格式
  → 写入 cbc 的 stdin
  → cbc 处理用户消息并响应
```

#### 第四层：用户接管（未来）

```
用户需要完全自由操控时
  → 暂停 stdin 信道
  → 通过 PTY 或其他方式获得完整交互终端
```

### 5.2 核心设计问题：共享 stdin 互斥

长驻进程中，stdin 只有一个写入者。Agent 和用户不能同时写入。

**解决方案：消息队列 + 互斥锁**

```
Agent 任务 ──→ 消息队列 (FIFO) ──→ Worker.stdin.write()
用户注入 ──→                      │
                                   │
                    result 事件 = "轮到下一个人"
```

- 同一时间只有一人在说话
- result 事件是切换信号
- 队列保证顺序

### 5.3 架构总览

```
CLI 入口 (cliconductor spawn/list/send/kill)
       │
       ▼
Session Manager (Worker 注册表 + 消息队列)
       │
       ├── Worker-1 ── cbc (stdin stream-json 模式)
       ├── Worker-2 ── cbc (stdin stream-json 模式)
       └── Worker-N ── ...
       │
       ▼
Dashboard (Web 界面，可选)
  ├── 实时事件流展示
  ├── 消息注入通道
  └── Worker 状态总览
```

### 5.4 已确定的技术栈

| 技术 | 选择 | 理由 |
|------|------|------|
| 语言 | TypeScript | 用户明确要求 |
| 运行时 | Node.js | 实验已验证 |
| 进程管理 | `child_process.spawn` | Phase 1 结论，跨平台 |
| CLI 命令 | `cbc -p --output-format stream-json --input-format stream-json -y` | 本节实验验证 |
| 输出解析 | line-by-line JSON.parse | 实时流解析 |
| 多轮对话 | stdin 持续写入 | 本节实验验证 |
| PTY | `node-pty` (备选) | 接管模式需要 |

---

## 六、已确定的取舍

### 6.1 不做的（从原 Phase 2 砍掉）

| 砍掉 | 理由 |
|------|------|
| 消息网关 | 只需要 CLI 入口，其他渠道以后再说 |
| 任务队列 | Agent 顺序派发已足够 |
| 多 CLI 适配器 | 先只做 CBC，Strategy 接口预留扩展点 |
| E2E 测试 | 手动验证即可 |
| 会话归档重建 | Phase 3 |
| PTY 接管模式 | 观察+注入先满足核心需求 |

### 6.2 可复用资产

| 资产 | 位置 | 怎么用 |
|------|------|--------|
| stdin stream 实验 | `experiments/stdin-stream-mode.js` | 直接参考 spawn 参数和消息格式 |
| DionysusC Strategy | `D:\project\DionysusC\...\agent_adapters\` | Worker 的架构参考 |
| Archive ProcessManager | `archive/docs/architecture/shell-process-control.md` | PID 追踪、isAlive 等工具方法 |
| Archive AgentAdapter 接口 | `archive/docs/architecture/agent-cluster-architecture.md` | TypeScript 接口骨架 |
| server.js PTY 桥接 | `packages/cbc-bridge/server.js` | 接管模式的参考实现 |

---

## 七、待决策问题

| # | 问题 | 状态 |
|---|------|:----:|
| 1 | stdin stream 多轮可行？| ✅ 已验证 |
| 2 | 不需要 --resume？| ✅ 已验证（长驻进程替代）|
| 3 | 消息队列如何实现？内存 / 文件？| 待讨论 |
| 4 | Worker 消息格式统一协议？| 待讨论 |
| 5 | 目录结构？单包 / monorepo？| 待讨论 |
| 6 | MVP 第一个 CLI 命令是什么？| 待讨论 |
| 7 | 每个 Worker 需要独立 workdir？| 待讨论 |
