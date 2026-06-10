# 外部资源索引

> 搜索范围：GitHub、B站、技术博客、Awesome List
> 更新时间：2026-06-10

---

## 一、核心标杆项目（架构直接对标）

与我们的"主 Agent 操控多个子 CLI + session 追踪"需求**高度吻合**的项目。

| 项目 | 链接 | Stars | 描述 | 核心技术 | 相关点 |
|------|------|-------|------|---------|--------|
| **CLI Agent Orchestrator (CAO)** | [awslabs/cli-agent-orchestrator](https://github.com/awslabs/cli-agent-orchestrator) | 688 | AWS 开源的多 CLI agent 层级编排框架。Supervisor agent + 专用 worker agent，tmux session 隔离 | Python, FastAPI, tmux, MCP | 架构 90% 相同：层级编排、tmux隔离、handoff/assign 模式 |
| **Claude Squad** | [GitHub](https://github.com/search?q=claude-squad) | 7.7k | tmux-based harness，多个 Claude Code session 并行 | tmux, Claude Code | PTY session 管理 + 多 agent 并行，直接可用套路 |
| **cmux** | [GitHub](https://github.com/search?q=cmux) | 21.5k | 开源平台，并行运行多个 agent | tmux, 多 agent | Session 管理 + 并行编排的成熟方案 |
| **Superset** | [GitHub](https://github.com/search?q=superset+terminal) | 11.6k | 专为 coding agent 设计的终端，编排并行 session | Terminal, PTY | 终端级 agent 编排 |
| **Herdr** | 搜索结果 | — | PTY agent multiplexer | PTY, agent 多路复用 | 最贴合"CLI 操控 CLI + session 追踪" |
| **OpenClaw (Claw)** | [GitHub](https://github.com/search?q=openclaw) | 130k+ | MIT 开源 AI Agent 执行网关，多 Agent 集群 + 多渠道接入 | Node.js, Gateway, Pi Agent | 多入口 + 多 Agent + 白盒记忆，架构高度一致 |
| **PATAPIM** | [GitHub](https://github.com/search?q=patapim) | — | 9 终端网格 IDE，同时运行多个 CLI coding agent | Terminal grid | 终端多路复用的极致方案 |
| **agent-of-empires** | [GitHub](https://github.com/search?q=agent-of-empires) | 2.5k | TUI/Web UI 管理多个 agent，Rust + tmux + git worktree | Rust, tmux | TUI + tmux 组合，session 可追踪 |

### CAO 详细分析（最值得研究）

```
与我们项目架构对比：

CAO                          我们的设计
─────                        ─────────
Supervisor Agent          →  主 Agent (Brain)
Worker Agent (隔离tmux)    →  子 CLI (PTY/tmux)
Handoff (同步)             →  execute()
Assign (异步并行)           →  任务队列
Send Message (直接通信)     →  continue()
MCP Server 通信            →  stdout/stdin JSON / socket
Python + FastAPI           →  Node.js + TypeScript (灵活)
支持 Claude Code, Q CLI    →  支持 CBC, Claude, Aider, Shell
Apache 2.0                 →  Apache 2.0 兼容

差异：
- CAO 不支持 CodeBuddy Code → 我们可以贡献 CBC 适配器
- CAO 用 MCP 通信 → 我们可用更轻量的 stdin/stdout
- CAO 有 Web UI → 我们可以参考其设计
```

**建议**：深入研究 CAO 源码，评估是基于 CAO 写 CBC 适配器插件，还是借鉴架构自己实现。

---

## 二、Session 管理器 / 终端多路复用

直接解决"操控多个终端 session"的技术项目。

| 项目 | 链接 | Stars | 描述 |
|------|------|-------|------|
| **ntm (Named Tmux Manager)** | [GitHub](https://github.com/search?q=ntm+tmux) | 342 | 命名 tmux 管理，spawn + tile + 协调 agent 跨 tmux pane |
| **amux (mixpeek)** | [GitHub](https://github.com/search?q=amux+mixpeek) | 226 | Agent 多路复用器，支持数十个并行 session + Web Dashboard |
| **amux (andyrewlee)** | [GitHub](https://github.com/search?q=amux) | 122 | TUI 并行运行多个 coding agent |
| **agent-deck** | [GitHub](https://github.com/search?q=agent-deck) | 2.7k | 统一 TUI，管理 Claude/Gemini/OpenCode/Codex 等 session |
| **pty-mgr** | [kollaborai/pty-mgr](https://github.com/kollaborai/pty-mgr) | — | PTY session 管理器，程序化控制，捕获渲染屏幕输出（非原始字节） |
| **node-terminal** | [MCP Market](https://mcpmarket.com/zh/server/node-terminal) | — | AI agent 程序化控制多终端 session，跨平台，实时通信 |
| **node-pty** | [npm](https://www.npmjs.com/package/node-pty) | — | Node.js PTY 库，fork pseudoterminals，本项目**基础依赖** |
| **tmux-core** | 搜索结果 | — | tmux 编程 SDK，程序化操控 tmux session |
| **Toad** | [GitHub](https://github.com/search?q=toad+agent+orchestrator) | 3.2k | Agent 编排器，并行 CLI coding session |
| **Crystal** | [GitHub](https://github.com/search?q=crystal+codex+claude) | 3.1k | 并行 git worktree 中执行多个 Codex & Claude Code session |
| **CliDeck** | [GitHub](https://github.com/search?q=clideck) | 105 | WhatsApp 风格浏览器 Dashboard，管理多个 CLI agent |
| **vibe-kanban** | [GitHub](https://github.com/search?q=vibe-kanban) | 26.9k | Kanban 界面管理 AI coding agent |

---

## 三、Agent 编排 / 多 Agent 框架

通用的多 Agent 协作框架，提供架构模式参考。

| 项目 | 链接 | 描述 | 相关度 |
|------|------|------|--------|
| **Agent Swarm** | 搜索结果 | Docker 化 agent 集群，CLI/API 双重控制 | 高 — 集群概念直接对应 |
| **OpenAI Swarm** | [openai/swarm](https://github.com/openai/swarm) | OpenAI 的轻量多 agent 编排实验框架，handoff 模式 | 中 — 提供 agent 间交接的模式参考 |
| **LangGraph Supervisor** | [LangGraph](https://github.com/langchain-ai/langgraph) | 分层 supervisor 模式，supervisor 调度 worker | 高 — supervisor-worker 模式完全一致 |
| **CrewAI** | [crewAI](https://github.com/crewAIInc/crewAI) | 角色化多 agent 协作，每个 agent 有明确的 role/goal | 中 — 角色分配思路可借鉴 |
| **Microsoft AutoGen** | [microsoft/autogen](https://github.com/microsoft/autogen) | 事件驱动的多 agent 对话框架 | 中 — 通信模式参考 |
| **AWS Multi-Agent Orchestrator** | [awslabs/multi-agent-orchestrator](https://github.com/awslabs/multi-agent-orchestrator) | AWS 的意图分类路由式多 agent 系统 | 中 — 路由/分发模式 |
| **OpenCastle** | [GitHub](https://github.com/search?q=opencastle+multi-agent) | 48 | 将 6 个 assistant 转为 19 个协调的 specialist | 中 |
| **AgentWrapper** | 搜索结果 | 并行 agent + git worktree 隔离 | 高 — worktree 隔离方案 |
| **AI-Coding-Orchestrator** | 搜索结果 | 智能 agent 分配 | 高 — 任务分配逻辑 |
| **Relay** | [GitHub](https://github.com/search?q=relay+MCP+orchestrator) | 4 | 本地优先的 MCP 编排器：分类→分解→分发 | 高 — 与我们的调度器设计一致 |
| **pi-builder** | [GitHub](https://github.com/search?q=pi-builder) | 5 | 将任意 CLI agent 封装在单一接口后，capability 路由 | 高 — **适配器模式**的现成实现 |
| **Bernstein** | [GitHub](https://github.com/search?q=bernstein+orchestrator) | 559 | 确定性 Python 编排器：spawn 并行 agent，验证，自动 commit | 中 — 验证 + 自动化流程 |
| **ORCH** | [GitHub](https://github.com/search?q=ORCH+task+queue) | 74 | CLI 编排器，类型化任务队列 + 状态机 + TUI | 中 — 任务队列设计参考 |
| **AgentPipe** | [GitHub](https://github.com/search?q=agentpipe) | 133 | CLI/TUI 多 agent 对话共享房间 | 中 — agent 间通信 |

---

## 四、Agent 基础设施 / 工具链

沙箱、路由、浏览器自动化、MCP 服务器、安全等辅助工具。

| 项目 | 链接 | Stars | 描述 | 与我们的关系 |
|------|------|-------|------|-------------|
| **AgentsRoom** | [agentsroom.dev](https://agentsroom.dev/) | — | 多 agent 并行管理 IDE，自带 CLI agent，手机端控制 | 多入口操控（含移动端） |
| **AgentsMesh** | [GitHub](https://github.com/search?q=agentsmesh) | 2.2k | AI Agent 工作平台，PTY sandbox + Kanban | PTY 隔离 + 任务管理 |
| **agent-terminal** | [GitHub](https://github.com/search?q=agent-terminal) | 10 | 无头终端自动化，node-pty 驱动 | **node-pty 操控终端的参考实现** |
| **Untether** | [GitHub](https://github.com/search?q=untether+telegram) | 50 | Telegram 桥接 6 个 CLI agent，语音/文字远程控制 | **多入口（含聊天软件）的现成方案** |
| **gate4agent** | [GitHub](https://github.com/search?q=gate4agent) | 7 | Rust 通用传输库，为 CLI agent 提供统一通信层 | 跨 agent 通信层 |
| **claude-code-router** | [GitHub](https://github.com/search?q=claude-code-router) | 34.8k | Claude Code 路由到不同 provider/endpoint | 路由模式参考 |
| **claude-flow** | [GitHub](https://github.com/search?q=claude-flow) | 58.5k | 部署多 agent swarm 协调工作流 | Swarm 编排模式 |
| **OpenWork** | [GitHub](https://github.com/search?q=openwork) | 15.9k | 开源 Claude Cowork 替代，本地桌面应用 | 本地多 agent 协作 |
| **LinkShell** | [liutianjie.github.io/LinkShell](https://liutianjie.github.io/LinkShell/) | — | 手机远程接管 AI 终端 Agent Workspace | 远程 PTY 接入 |
| **tunnel-shell** | [PyPI](https://pypi.org/project/tunnel-shell/) | — | Agent-first 远程终端，持久 PTY session + AI 友好输出解析 | PTY + 输出解析 |
| **PTY-MCP** | [MCP World](https://www.mcpworld.com/zh/detail/03bef4ec1899a8af10a6427b14690ee5) | — | Rust PTY 多协议控制服务器，持久化终端状态 | PTY 服务化 |
| **CodeMachine-CLI** | [GitHub](https://github.com/search?q=codemachine-cli) | 2.5k | 多 agent CLI 本地编码工作流 | 多 agent CLI |
| **Roo Code CLI** | [GitHub](https://github.com/search?q=roo-code-cli) | 24.2k | 多模式 agent（architect/code/debug/orchestrator） | Orchestrator 模式 |
| **Dexto** | [GitHub](https://github.com/search?q=dexto) | 631 | agent harness，CLI/Web/API 模式 + sub-agent spawn | 子 agent 管理 |

---

## 五、B站视频 / 教程

| 标题 | 链接 | 类型 | 相关度 |
|------|------|------|--------|
| **omas — Agent 时代的 Shell 控制台** | [BV1ByE362EDa](https://www.bilibili.com/video/BV1ByE362EDa/) | Agent Shell 终端实操 | 高 — 直接涉及 agent 管控终端 Shell |
| **TRAE、Qoder、CodeBuddy 横评** | [BV151pezFEZz](https://www.bilibili.com/video/BV151pezFEZz/) | CodeBuddy 能力实测 | 高 — 了解 CBC 的 agent 能力边界 |
| **CodeBuddy 介绍与快速入门** | [BV1vnksBPE1E](https://www.bilibili.com/video/BV1vnksBPE1E/) | CodeBuddy 教程 | 高 — CBC 基础 |
| **CodeBuddy 国内版和国际版安装教程** | [BV1jdm9BhEPN](https://www.bilibili.com/video/BV1jdm9BhEPN/) | CodeBuddy 安装 | 高 — 安装配置 |
| **Agent实战 CLI构建命令行工具** | [课程](https://www.bilibili.com/cheese/play/ss893126504) | CLI agent 开发 | 高 — CLI + Agent 集成 |
| **全748集 AI Agent智能体搭建** | [BV1pxEj6NEAx](https://www.bilibili.com/video/BV1pxEj6NEAx/) | Agent 综合教程 | 中 — 覆盖面广 |
| **AI大模型Agent项目实战课** | [课程](https://www.bilibili.com/cheese/play/ss183206372) | Agent 开发 | 中 — 多 agent 协作部分 |
| **10分钟用CodeBuddy生成APP** | [BV1bRBkBFE7x](https://www.bilibili.com/video/BV1bRBkBFE7x/) | CodeBuddy 实操 | 中 — 了解 CBC workflow |
| **CodeBuddy + MCP 开发一条龙** | [BV1LQpBzrEb2](https://www.bilibili.com/video/BV1LQpBzrEb2/) | CodeBuddy MCP | 中 — MCP 扩展 |

---

## 六、技术文章 / 指南

| 标题 | 链接 | 内容 | 相关度 |
|------|------|------|--------|
| **PTY原理与应用实践** | [kelefat.com](https://www.kelefat.com/posts/understanding-and-using-pty/) | PTY 原理 + Python 实战，含远程交互服务器开发 | 高 — PTY 底层知识 |
| **Claude Code 多Agent组队开发** | [知乎](https://zhuanlan.zhihu.com/p/2004486603343671752) | 多agent 协作实践与踩坑 | 高 — 实操经验 |
| **多Agent编排：让AI团队协同工作** | [clawpk.net](https://clawpk.net/tutorials/40-multi-agent-orchestration) | 管道/广播/投票/分层四种协作模式 | 高 — 编排模式 |
| **OpenClaw 多Agent配置教程** | [heyuan110.com](https://www.heyuan110.com/zh/posts/ai/2026-02-23-openclaw-multi-agent-guide/) | OpenClaw 路由绑定、Agent通信 | 高 — 路由与通信 |
| **OpenClaw 架构分析** | [本地: openclaw-architecture.md](./analysis/openclaw-architecture.md) | OpenClaw 六大核心模块、多Agent协作、任务流程详解 | 高 — 本地深度分析 |
| **CAO 官方博客** | [AWS Blog](https://aws.amazon.com/blogs/opensource/introducing-cli-agent-orchestrator-transforming-developer-cli-tools-into-a-multi-agent-powerhouse/) | CAO 设计理念与架构 | 极高 — 理念介绍 |
| **CAO DeepWiki** | [deepwiki.com](https://deepwiki.com/awslabs/cli-agent-orchestrator) | CAO 深度文档 | 极高 — 源码级理解 |
| **How to Run Multiple AI Agents in Single Terminal** | [stoicsoft](https://stoicsoft.github.io/1devtool/2026/03/26/how-to-run-multiple-ai-agents-single-terminal-workspace.html) | 单终端运行多 agent 实操 | 高 — 实操 | 
| **多Agent协作架构模式实战** | [dev.to](https://dev.to/jiade/duo-agentxie-zuo-jia-gou-mo-shi-shi-zhan-cong-fen-ceng-gui-hua-dao-dong-tai-bian-pai-de-wan-zheng-zhi-nan-467a) | 分层规划到动态编排 | 高 — 架构模式 |
| **Supervisor与Swarm架构详解** | [知乎](https://zhuanlan.zhihu.com/p/1944689022464164000) | Supervisor vs Swarm 对比 | 中 |
| **V2EX 讨论** | [v2ex.com/t/1194580](https://www.v2ex.com/t/1194580) | 远程机多Agent并行"集中管理/会话跟踪"痛点 | 极高 — **需求完全一致** |
| **CAO 中文介绍** | [AgentPark](https://www.agentpark.fun/zh/projects/cli-agent-orchestrator) | CAO 中文概览 | 高 |

---

## 七、参考列表 / Awesome 合集

| 资源 | 链接 | 内容 |
|------|------|------|
| **awesome-cli-coding-agents** | [bradAGI/awesome-cli-coding-agents](https://github.com/bradAGI/awesome-cli-coding-agents) | **必读**。80+ CLI coding agent + 25 session manager + 19 orchestrator 的完整索引 |
| **Awesome CLI — Coding Agents** | [awesome-cli.com](https://www.awesome-cli.com/collections/coding-agents) | CLI agent 精选集合 |

---

## 八、对我们的启发与选型建议

### 8.1 有现成的轮子，不需要从零造

| 需求 | 现成方案 | 建议 |
|------|---------|------|
| Agent 层级编排 | CAO (AWS) | 最值得深入研究，可贡献 CBC 适配器 |
| 多 session PTY 管理 | ntm / pty-mgr / Claude Squad | 直接用或参考 |
| 多入口接入 (QQ/Web等) | Untether (Telegram) / CliDeck (Web) | 参考实现 |
| 适配不同 CLI | pi-builder / CAO adapter pattern | 遵循适配器接口设计 |

### 8.2 技术选型建议

```
层级编排引擎  →  研究 CAO 源码，评估是贡献适配器还是自己实现
PTY/Session管理 →  node-pty + tmux（组合使用，根据场景选择）
                   - 简单场景：直接 node-pty spawn
                   - 需要 detach/reattach：tmux
                   - 输出解析：参考 pty-mgr 的屏幕渲染输出方案
Agent 间通信   →  初期：stdin/stdout JSON 流
                  中期：本地 Unix Socket / MCP
                  后期：消息队列
Web 管理界面   →  参考 CliDeck / AgentsRoom 的设计
多入口适配    →  参考 Untether (Telegram桥接) 的模式
```

### 8.3 一句话总结

> **CAO + awesome-cli-coding-agents 列表 = 最应该深入研究的内容。**
> 前者提供了架构蓝图（层级编排 + tmux 隔离 + 适配器模式），后者提供了完整的生态地图。
> 当前阶段核心问题是：**直接给 CAO 写 CBC 适配器，还是借鉴 CAO 自己实现？**

---

> 索引维护：发现新项目后追加到对应分类。重点追踪 awesome-cli-coding-agents 的更新。
