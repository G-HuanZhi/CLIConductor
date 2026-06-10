# CAO (CLI Agent Orchestrator) 分析

> 目标：评估 CAO 是否可以作为本项目的基础，还是需要自己实现。
> 分析日期：2026-06-11

---

## 一、CAO 是什么

AWS Labs 开源的多 CLI Agent 层级编排框架。把多个 AI CLI 工具（Claude Code、Codex、Gemini CLI 等）组织为一个由 Supervisor Agent 指挥的团队。

**一句话**：一个 Python 程序，通过 tmux 管理多个 AI CLI 终端进程，Supervisor Agent 通过 MCP 协议向 Worker Agent 派发任务并收集结果。

---

## 二、核心能力

| 能力 | 说明 |
|------|------|
| **层级编排** | Supervisor Agent 创建、协调、管理多个 Worker Agent（tmux 终端隔离） |
| **三种协作模式** | Handoff（同步等结果）、Assign（异步派发）、Send Message（多轮对话） |
| **跨 CLI 编排** | 同一工作流中 Supervisor 用 Kiro，Worker 用 Claude Code、另一 Worker 用 Codex |
| **长对话支持** | 每个 Worker 是真实的 CLI 终端进程，保持完整上下文和记忆 |
| **Web Dashboard** | React + Tailwind，查看所有 session 状态、终端监控 |
| **定时任务** | Flow 机制支持 cron 语法，"每天早上 9 点运行代码审查" |
| **Headless 模式** | CI/CD 中无人值守运行 |
| **人工干预** | 用户可以 attach 到任意 tmux session 介入指导 |
| **MCP 协议** | Agent 间通信使用标准化 MCP 协议 |
| **插件系统** | Observer 模式，可扩展 Discord/Slack 通知等 |

---

## 三、架构设计

```
                    用户 / 外部系统
                         │
              ┌──────────┼──────────┐
              │          │           │
         ┌────▼───┐ ┌───▼────┐ ┌───▼──────┐
         │cao CLI │ │Web UI  │ │cao-ops   │
         │(命令)   │ │:9889   │ │MCP Server│
         └────┬───┘ └───┬────┘ └───┬──────┘
              │         │          │
              └─────────┼──────────┘
                        │
                ┌───────▼──────┐
                │  FastAPI     │  ← 后端 API（唯一入口）
                │  (uvicorn)   │
                └───────┬──────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
   ┌────▼────┐   ┌──────▼──────┐  ┌─────▼─────┐
   │ Session │   │  Terminal   │  │   Inbox   │  ← 服务层
   │ Service │   │  Service    │  │  Service  │
   └────┬────┘   └──────┬──────┘  └─────┬─────┘
        │               │               │
   ┌────▼────┐   ┌──────▼──────┐  ┌─────▼─────┐
   │ tmux    │   │  Provider   │  │  SQLite   │  ← 基础设施层
   │ Client  │   │  Adapters   │  │  Database │
   └─────────┘   └─────────────┘  └───────────┘
```

### 关键设计特点

| 特点 | 说明 |
|------|------|
| **统一入口** | CLI、Web、MCP 都通过 FastAPI 操作，内部逻辑一致 |
| **tmux 隔离** | 每个 Agent 在独立 tmux window 中运行，完全隔离 |
| **日志驱动状态检测** | 通过 watchdog 监控 tmux pipe-pane 日志判断 Agent 是否完成响应（IDLE/PROCESSING/COMPLETED/ERROR） |
| **SQLite 持久化** | 终端状态、消息队列、session 记录都落在 SQLite |
| **14 天数据保留** | 自动清理超过 14 天的日志和数据库记录 |

---

## 四、Agent 间通信机制

CAO 使用 **MCP (Model Context Protocol)** 实现 Agent 间通信：

```
Supervisor Agent (tmux window 1)
    │
    │ 调用 MCP 工具 handoff("profile", "任务描述")
    │
    ▼
cao-mcp-server (stdio 协议)
    │
    │ 创建新 tmux window
    │ 启动 Worker CLI，注入 CAO_TERMINAL_ID
    │ 发送任务
    │
    ▼
Worker Agent (tmux window 2)
    │
    │ 执行完成，调用 send_message 返回结果
    │
    ▼
消息写入 SQLite inbox
    │
    │ Inbox Watcher 检测到 Supervisor IDLE
    │
    ▼
Supervisor 收到结果
```

### 三种协作模式

| 模式 | 行为 | 适用场景 |
|------|------|---------|
| **Handoff** | 创建 Worker，发送任务，等待完成，获取输出 | 单一明确任务 |
| **Assign** | 创建 Worker，发送任务，不等待 | 并行处理多个不相关任务 |
| **Send Message** | 向已有 Worker 发送消息 | 多轮对话、追加指令 |

---

## 五、支持的 CLI Agent（Provider）

| Provider | CLI 命令 | 认证方式 |
|----------|---------|---------|
| Kiro CLI | `kiro` | AWS credentials（默认） |
| Claude Code | `claude` | Anthropic API key |
| Codex CLI | `codex` | OpenAI API key |
| Gemini CLI | `gemini` | Google AI API key |
| Kimi CLI | `kimi` | Moonshot API key |
| Copilot CLI | `copilot` | GitHub auth |
| Hermes Agent | `hermes` | Hermes auth |
| OpenCode CLI | `opencode` | Per-model API key（实验性） |
| Q CLI | `q` | AWS credentials（已弃用，迁移至 Kiro） |

**注意：没有 CodeBuddy Code 的 Provider。** 如果要用 CAO，需要自己写 CBC Provider 适配器。

---

## 六、技术栈

| 层面 | 技术 | 说明 |
|------|------|------|
| 语言 | Python 3.10+ | mypy 静态类型 |
| Web 框架 | FastAPI + Uvicorn | 端口 9889 |
| 数据库 | SQLite | terminals, inbox_messages, sessions |
| 终端管理 | tmux 3.3+ | Session 隔离 + PTY 访问 |
| Agent 协议 | MCP (stdio) | handoff/assign/send_message |
| 前端 | React + Vite + Tailwind | 内嵌 wheel 包中 |
| 包管理 | uv | Astral 的快速 Python 包管理器 |
| 状态检测 | watchdog | 文件系统监听 pipe-pane 日志 |
| 测试 | pytest (511 tests, 84% coverage) | + CI/CD (CodeQL, Trivy) |

---

## 七、核心限制

| 限制 | 影响 | 对我们项目的影响 |
|------|------|----------------|
| **依赖 tmux** | Linux/macOS only | **严重** — 我们主要开发环境是 Windows |
| **无 Windows 原生支持** | 需要 WSL2 | 增加环境复杂度（但 psmux 可缓解，见第十一节） |
| **无 CBC Provider** | 不能直接操控 cbc | 必须自己写适配器 |
| **仅本地运行** | 不能跨机器编排 | Phase 2-3 够用，Phase 4 受限 |
| **14 天数据保留** | 自动清理旧数据 | 如果需要长期审计，需要自己保存 |
| **日志驱动状态检测** | 可能有延迟 | 不如 API 直接获知状态可靠 |
| **Provider 需要手动适配** | 每加一个 CLI 都要写适配器 | 如果我们自己实现，也一样 |
| **Python 技术栈** | 与我们的 Node.js/TS 不一致 | 增加技术维护成本 |

---

## 八、评估：用 CAO 还是自己实现

### 我们项目的核心需求

- ✅ 主 Agent 操控多个子 CLI
- ✅ 子 CLI 支持长对话（多轮上下文）
- ✅ Session 可追踪
- ✅ 各 CLI 适配器统一接口
- ✅ 支持 CodeBuddy Code（我们自己用的工具）
- ⚠️ 主要工作在 **Windows + Git Bash** 环境
- 🔮 未来目标：QQ Bot 等多渠道入口、分布式集群

### 与 CAO 的契合度分析

| 需求 | CAO 满足吗？ | 评估 |
|------|-------------|------|
| 层级编排 | ✅ 完美 | Supervisor-Worker 模式完全一致 |
| 长对话支持 | ✅ | tmux 中运行真实 CLI 进程，保持完整上下文 |
| Session 追踪 | ✅ | SQLite + tmux 命名，完整索引 |
| 适配器模式 | ✅ 模式一致 | Provider 适配器架构就是我们要的 |
| CodeBuddy Code | ❌ **不满足** | 必须自己写 Provider |
| Windows 环境 | ❌ **不满足** | 需要 WSL2，增加复杂度 |
| 进程内操控 | ❌ | CAO 只能操控 tmux 中运行的 CLI，不能操控当前父进程中的子 CLI |
| Node.js 生态 | ❌ | Python 技术栈，与现有技术栈不一致 |
| 多入口（QQ Bot等） | ❌ | CAO 只是本地编排，不是消息网关 |

### 一次关键差异：操控方式

CAO 的架构假设：
```
CAO Server (Python) → tmux → CLI 终端（独立进程）
```

我们的核心运作方式却是：
```
外层 cbc（用户正在对话的这个）→ Bash 工具 / PTY → 内层 cbc
```

**CAO 依赖外部 tmux，而我们更倾向于在当前父进程内部通过 PTY 做进程级操控**。两者的架构理念不同：
- CAO：外部编排器 + tmux 终端池（无头服务器模式）
- 我们：当前 Agent 内生操控 + 轻量级进程管理（Agent Native 模式）

### 结论：建议自己实现

**不建议直接使用 CAO**，原因按优先级排列：

1. **Windows 兼容性** — CAO 强行依赖 tmux，Windows 需要 WSL2，增加了不必要的环境复杂度。即使我们能跑 WSL2，也无法利用 Windows 原生 PTY 生态（node-pty）。

2. **操控方式不匹配** — CAO 是外部编排器（独立进程），无法满足"当前 cbc 作为主 Agent 操控子 cbc"的场景。我们需要的是一个可以在 **cbc 内部通过 Bash 工具调用的轻量级 PTY 管理器**，而不是一个独立的 tmux 编排服务。

3. **额外适配成本** — 用 CAO 需要：写 CBC Provider（Python）+ 桥接 CAO 到我们的 cbc 进程 + 在 Windows 下处理 WSL2/tmux 兼容。总成本可能超过自己实现。

4. **技术栈碎片化** — 项目统一 Node.js/TypeScript。引入 Python 服务增加维护负担。

5. **架构理念不同** — CAO 的目标是"独立 tmux 编排服务"，我们的目标是"Agent Native PTY 操控"。虽然 Supervisor-Worker 模式一致，但底层操控机制完全不同。

### 建议路径

```
借鉴 CAO 的架构思想，用 Node.js/TypeScript 自己实现：

借鉴点：
  ✅ Supervisor-Worker 层级模型（架构核心）
  ✅ Handoff / Assign / Send Message 三种协作模式（通信模式）
  ✅ Provider Adapter 接口设计（适配器模式）
  ✅ Session 状态机（IDLE/PROCESSING/COMPLETED/ERROR）
  ✅ SQLite 持久化 session 数据（简单可靠）
  ✅ Inbox 消息队列（Agent 间异步通信）

替换点：
  🔄 tmux → node-pty（Windows 原生兼容，优先方案）
  🔄 备选终端层：psmux（Windows 原生 tmux 兼容，处理 session/window/pane 管理，见第十节）
  🔄 MCP → stdin/stdout JSON 流（更轻量）
  🔄 Python/FastAPI → TypeScript（统一技术栈）
  🔄 独立编排服务 → 嵌入式 PTY 管理器（Agent Native）
  🔄 日志驱动状态检测 → 进程级信号/回调（更可靠）
```

---


## 九、CAO 代码结构速览

```
cli-agent-orchestrator/
├── src/cli_agent_orchestrator/
│   ├── api/                  # FastAPI 端点
│   ├── cli/commands/         # Click CLI 命令
│   ├── mcp_server/           # Agent 间 MCP 工具（handoff/assign/send_message）
│   ├── ops_mcp_server/       # 外部管理 MCP 工具
│   ├── services/             # 业务逻辑（session/terminal/inbox/flow）
│   ├── clients/              # 基础设施（tmux.py / database.py）
│   ├── providers/            # CLI 适配器（base.py + 各 CLI 实现）
│   ├── models/               # Pydantic/SQLAlchemy 数据模型
│   └── agent_store/          # 内置 Agent 角色定义（Markdown + YAML frontmatter）
├── web/                      # React + Vite 前端源码
├── test/                     # 511 个测试
└── docs/                     # 文档
```

**核心抽象**：`BaseProvider` 类定义了每个 CLI 适配器必须实现的接口：launch（启动）、detect prompt（等待 Agent 就绪）、handle tool-specific quirks（处理各 CLI 的怪异行为）。

---

## 十、psmux：Windows 端 tmux 的替代可能性

[psmux](https://github.com/psmux/psmux) 是一个用 Rust 编写的 **Windows 原生终端复用器**，直接调用 Windows ConPTY API，支持 tmux 命令语言。它不是 tmux 的移植版，而是从零重新实现。

### 基本信息

| 项 | 值 |
|----|----|
| 语言 | Rust |
| 底层 API | Windows ConPTY（Console Pseudo-Teletype） |
| 命令兼容 | 92 个 tmux 命令，覆盖 ~90% 常用功能 |
| 配置兼容 | 直接读取 `~/.tmux.conf` |
| 主题支持 | Catppuccin、Dracula、Nord 等全部 tmux 主题 |
| 架构 | Client-Server（loopback TCP + AUTH 握手） |
| 安装 | `winget install psmux` / `cargo install psmux` |
| 系统要求 | Windows 10/11 + PowerShell 7+（推荐） |
| 性能 | 启动 <100ms，内存 ~10MB/会话 |

### 关键的编程操控能力

psmux 支持 tmux 的全部编程操控命令，这对 Agent 集群的方向至关重要：

| 命令 | 用途 | Agent 集群场景 |
|------|------|---------------|
| `send-keys` | 向指定窗格发送键盘输入 | 主 Agent 向子 CLI 发送任务 |
| `capture-pane -p` | 捕获指定窗格的文本输出 | 获取子 Agent 的响应内容 |
| `pipe-pane` | 管道输出到文件 | 日志采集 + 状态检测（类似 CAO 的 watchdog 机制） |
| `split-window` | 分割窗格 | 动态增减 Worker 终端 |
| `new-session -d` | 后台创建命名 session | 程序化启动 Worker 集群 |
| `display-message` | 格式化输出状态 | 查询 session/窗格状态 |

### psmux 如何改变 CAO 的 Windows 兼容性评估

CAO 的唯一阻塞性基础设施依赖是 tmux。psmux 提供了三种可能的集成路径：

```
路径 A：CAO + psmux（最小改动）
  CAO Server (Python) → psmux (替代 tmux) → CBC/Claude Code 终端
  问题：CAO 内部使用 tmux.py 调用 tmux 命令，psmux 命令行与 tmux 兼容
  风险：90% 命令兼容不保证 100%，边缘情况需要验证

路径 B：CAO 设计模式 + psmux 作为终端层（架构融合）
  Node.js/TS 编排核心 → psmux (send-keys/capture-pane) → CBC 终端
  优势：psmux 处理终端隔离和 PTY，编排逻辑用 Node.js
  问题：psmux 通过 TCP 控制，不是 JS API

路径 C：psmux 用于我们自己实现的终端管理（参考方案）
  我们的 TypeScript 编排器 → pspawn psmux send-keys/capture-pane → CBC 终端
  优势：Windows 原生、tmux 命令语言、完整编程接口
  劣势：额外进程依赖、通过子进程调用（非 JS 原生 API）
```

### psmux 的潜在问题

| 问题 | 说明 |
|------|------|
| **非 JS API** | 通过 spawn + 命令行参数操控，不能像 node-pty 那样直接内存操作 |
| **90% 兼容性** | 边缘 tmux 命令可能不兼容，需要实际测试 `capture-pane` 解析精度 |
| **额外进程** | psmux server 是独立进程，需要生命周期管理 |
| **Windows 专属** | 如果未来需要 Linux 部署，终端层不能只用 psmux |
| **生态较新** | 2025 年 11 月首次发布，社区和文档仍在建设中 |
| **Git Bash 兼容未知** | Git Bash 不是原生 Windows ConPTY 终端，psmux 在此环境下的表现需要实测 |

### psmux vs node-pty：终端层方案对比

| 维度 | psmux | node-pty |
|------|-------|----------|
| 操控方式 | CLI 子进程（`psmux send-keys`） | JS API（内存中操作） |
| 会话隔离 | 内置（sessions/windows/panes） | 需要自己管理 |
| 输出捕获 | `capture-pane`（现成） | `onData` 回调 |
| 多窗格管理 | 内置（split/layout） | 每个 PTY 独立管理 |
| 跨平台 | Windows only | Win/Mac/Linux |
| 集成复杂度 | 中等（spawn 子进程） | 低（require 使用） |
| 稳定性 | 较新，仍在快速迭代 | 成熟，Node.js 生态广泛使用 |

### 结论

psmux 的存在 **部分缓解了 Windows 无 tmux 的问题**，但并未从根本上改变"建议自己实现"的结论：

- **如果最终选择 CAO**：psmux 是关键前提，必须验证 psmux 能否完全替代 tmux 运行 CAO
- **如果自己实现**：psmux 是一个**备选终端层**，与 node-pty 并列。node-pty 优先（JS 原生 API、跨平台），psmux 适合需要完整会话管理（多窗格、布局、session attach）的场景

**建议**：Phase 1 实验中保留 node-pty 作为首选方案（已在 todolist.md 中），psmux 作为备选方案。完成 node-pty 实验后，如果需要更丰富的终端管理能力，再评估 psmux。

---

## 十一、下一步行动

1. **Phase 1 实验继续**（按 todolist.md 中的计划）
   - PTY 操控方案验证（node-pty、tmux）
   - 多实例并发测试
   - CBC stream-json / --bg 行为测试

2. **实现了自己的最小可行系统（Phase 2）后**，如果需要跨机器编排或支持更多 Agent，再重新评估是否需要引入 CAO 或类似的编排框架。

3. **psmux 留作备选**：node-pty 实验完成后，如有需要再评估 psmux 是否适合作为终端楼后端。

---


> 分析完成。核心结论：**借鉴 CAO 的 Supervisor-Worker 架构和 Provider 适配器模式，用 Node.js/TypeScript 自己实现。** 终端层优先 node-pty，psmux 作为备选增强方案。CAO 的核心价值在于它的架构思想和设计模式（层级编排、三种协作模式、状态机），而非它的具体实现（Python + tmux + MCP）。
