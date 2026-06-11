# Agent 集群操控系统 (MyAgentsPlan)

> 用一个 AI（主 Agent）调度管理多个 AI CLI（CodeBuddy Code、Copilot CLI 等），让它们像团队一样分工协作。

## 目标

1. 用户可通过 QQ、Web、邮件、CLI 等任意方式与主 Agent 交流
2. 主 Agent 将任务拆分，分发到多个子 CLI 并行执行
3. 每个子 session 全程可追踪、可监控、可干预

## 当前进度

```
Phase 0  初始化           ████████████ ✅ 100%
Phase 1  实验验证          ████████████ ✅ 100%（16 项实验）
Phase 2  最小可行系统      ░░░░░░░░░░░░ ⏳ 0%
Phase 3  扩展和可视化      ░░░░░░░░░░░░ 📋 待开始
Phase 4  完整集群          ░░░░░░░░░░░░ 📋 待开始
```

## 架构

```
用户 → 消息网关 → 主 Agent → 调度器 → 适配器 → CLI 进程
```

1. **消息网关** — 统一多入口（CLI/Web/QQ），归一化为标准消息
2. **主 Agent + 调度器** — 拆分任务，分发到子 Agent
3. **适配器 + 进程管理** — 每种 CLI 一个适配器，用 OS 进程原语统一控制

## Phase 1 核心结论

| 决策 | 方案 | 淘汰的方案 |
|------|------|-----------|
| 多轮对话 | spawn 独立进程 + stream-json + --resume | --bg 管道多轮（失败） |
| 进程管理 | OS 原语 (PID/kill/wait) | 依赖 CLI 自身 ps/logs（不可移植） |
| 跨 CLI 兼容 | 适配器模式，差异仅命令行参数 | — |
| Session 管理 | 自定义 sessions.json + PID | CLI 自带 session 管理（不统一） |
| 记忆隔离 | 子 Agent 独立 workdir | 共享目录 MEMORY.md（会泄露） |
| Windows PTY | node-pty (bash 包装) | tmux（Windows 不可用） |

## 文件导航

### 项目文档

| 文件 | 内容 |
|------|------|
| [docs/planning/project-overview.html](./docs/planning/project-overview.html) | **项目总览（主要文档）** — 完整进度、方案对比、实验结论 |
| [docs/planning/project-overview.md](./docs/planning/project-overview.md) | 项目总览 Markdown 精简版 |
| [docs/planning/preview.md](./docs/planning/preview.md) | 项目速览（一页总结） |
| [docs/planning/beforeInit.md](./docs/planning/beforeInit.md) | 原始需求描述 |

### 架构设计

| 文件 | 内容 |
|------|------|
| [docs/architecture/agent-cluster-architecture.md](./docs/architecture/agent-cluster-architecture.md) | Agent 集群分层架构设计 |
| [docs/architecture/shell-process-control.md](./docs/architecture/shell-process-control.md) | 通用 CLI 进程控制方案（ProcessManager） |
| [docs/architecture/tech-stack-control-layer.md](./docs/architecture/tech-stack-control-layer.md) | Shell · child_process · Node.js 关系说明 |
| [docs/architecture/terminal-cli-concepts.md](./docs/architecture/terminal-cli-concepts.md) | 终端/CLI 底层概念学习笔记 |

### 外部分析

| 文件 | 内容 |
|------|------|
| [docs/analysis/openclaw-architecture.md](./docs/analysis/openclaw-architecture.md) | OpenClaw 架构分析 |
| [docs/analysis/cao-analysis.md](./docs/analysis/cao-analysis.md) | CAO 项目分析 |
| [docs/resource-index.md](./docs/resource-index.md) | 外部资源索引 |

### 实验报告

| 文件 | 内容 |
|------|------|
| [experiments/experiment-index.md](./experiments/experiment-index.md) | **实验索引** — 16 项实验的完整清单与结论 |
| [experiments/01-cbc-persistent/](./experiments/01-cbc-persistent/) | CBC 持久化 session 实验（s1~s5） |
| [experiments/02-pty-control/](./experiments/02-pty-control/) | PTY 终端操控实验（t1~t3, e01~e04） |
| [experiments/03-concurrent/](./experiments/03-concurrent/) | 多实例并发实验（c1~c2） |

### 源码

| 目录 | 内容 |
|------|------|
| [packages/core/](./packages/core/) | Session Manager、Task Queue |
| [packages/adapters/](./packages/adapters/) | CBC / Claude / Shell 适配器 |
| [packages/brain/](./packages/brain/) | 主 Agent 调度逻辑 |
| [packages/gateway/](./packages/gateway/) | 消息网关（多入口） |

## 技术栈

- 主控：Node.js / TypeScript（monorepo）
- 进程管理：child_process.spawn
- PTY 操控：node-pty + bash wrapper（备选方案）
- 子 Agent：CodeBuddy Code、Copilot CLI 等
- 通信：stdin/stdout stream-json

## 原则

1. **适配器模式** — 每种 CLI 一个适配器，统一 `AgentAdapter` 接口
2. **OS 原语优先** — 不依赖 CLI 自身的进程管理能力
3. **Session 先注册再使用** — 没有"看不见"的 session
4. **入口和调度解耦** — 消息入口不关心谁执行
5. **先跑通再优化** — 文件系统 → SQLite → 消息队列
