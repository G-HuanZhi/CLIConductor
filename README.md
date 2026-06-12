# Agent 集群操控系统 (MyAgentsPlan)

> 用一个 AI（主 Agent）调度管理多个**第三方** AI CLI（CodeBuddy Code、Copilot CLI、Claude Code 等），让它们像团队一样分工协作。

## 核心痛点

现有 AI Agent 框架（如 OpenClaw）只能管理"自己的" Agent，对第三方闭源 CLI 的控制深度不足——可以调用（如 `claude -p`），但缺乏多轮对话、进程生命周期管理、跨厂商统一抽象的能力。

MyAgentsPlan 通过 **OS 原语 + 适配器模式**，从 OS 层面建立对任意第三方 CLI 的深度控制通道，不要求 CLI 厂商配合。

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
用户 → 消息网关 → 主 Agent → 调度器 → 适配器 → CLI 进程（OS 原语管理）
```

1. **消息网关** — 统一多入口（CLI/Web/QQ），归一化为标准消息
2. **主 Agent + 调度器** — 拆分任务，分发到子 Agent，管理并发
3. **适配器 + OS 进程管理** — 每种 CLI 一个适配器，child_process.spawn + --resume 统一控制

### 核心差异化能力

| 控制深度 | 本系统 | 其他框架 |
|---------|--------|---------|
| 启动第三方 CLI | ✅ child_process.spawn | ✅ 单次 CLI 调用 |
| 多轮对话 | ✅ --resume | ❌ 每次新进程 |
| 进程生命周期管理 | ✅ PID 追踪 + kill -0 | ❌ |
| Session 归档重建 | ✅ 元数据 + 对话历史 | ❌ |
| 跨 CLI 统一管理 | ✅ 适配器模式 | ❌ 无抽象 |
| 无 -p CLI 操控 | ✅ PTY 备选 | ❌ |

## Phase 1 核心结论

| 决策 | 方案 | 淘汰的方案 |
|------|------|-----------|
| 多轮对话 | spawn + stream-json + --resume（方案D） | --bg 管道多轮（方案A，失败） |
| 进程管理 | OS 原语 (PID/kill -0/kill) | 依赖 CLI 自身 ps/logs |
| 跨 CLI 兼容 | 适配器模式 + CLIIdentity 能力矩阵 | — |
| Session 管理 | 自定义 sessions.json + PID + 三类策略（活跃保活/无价值放生/有价值归档） | CLI 自带 session 管理 |
| 记忆隔离 | 子 Agent 独立 workdir | 共享 MEMORY.md（泄露） |
| Windows PTY | node-pty + bash wrapper（备选） | tmux（Windows 不可用） |

## 文件导航

### 项目文档

| 文件 | 内容 |
|------|------|
| [docs/planning/project-overview.html](./docs/planning/project-overview.html) | **项目总览（主要文档）** — 完整进度、方案对比、实验结论 |
| [docs/planning/project-overview.md](./docs/planning/project-overview.md) | 项目总览 Markdown 精简版 |
| [docs/planning/preview.md](./docs/planning/preview.md) | 项目速览（一页总结） |

### 架构设计

| 文件 | 内容 |
|------|------|
| [docs/architecture/agent-cluster-architecture.md](./docs/architecture/agent-cluster-architecture.md) | **Agent 集群分层架构** — 详细设计、适配器接口、Session 管理 |
| [docs/architecture/shell-process-control.md](./docs/architecture/shell-process-control.md) | 通用 CLI 进程控制方案（ProcessManager） |
| [docs/architecture/tech-stack-control-layer.md](./docs/architecture/tech-stack-control-layer.md) | Shell · child_process · Node.js 关系说明 |
| [docs/architecture/terminal-cli-concepts.md](./docs/architecture/terminal-cli-concepts.md) | 终端/CLI 底层概念学习笔记 |

### 外部分析

| 文件 | 内容 |
|------|------|
| [docs/analysis/openclaw-architecture.md](./docs/analysis/openclaw-architecture.md) | **OpenClaw 架构分析** — 含完整对比 + 集成方案 |
| [docs/analysis/cao-analysis.md](./docs/analysis/cao-analysis.md) | CAO 项目分析 |
| [docs/resource-index.md](./docs/resource-index.md) | 外部资源索引 |

### 实验报告

| 文件 | 内容 |
|------|------|
| [experiments/experiment-index.md](./experiments/experiment-index.md) | **16 项实验索引** — 完整清单与结论 |

## 技术栈

- 主控：Node.js / TypeScript（monorepo）
- 进程管理：child_process.spawn（首选）
- PTY 备选：node-pty + bash wrapper
- 子 Agent：CodeBuddy Code、Copilot CLI、Claude Code、Aider 等
- 通信：stdin/stdout stream-json
- 未来集成：OpenClaw（Plugin / 母级管理）

## 原则

1. **适配器模式** — 每种 CLI 一个适配器，统一 `AgentAdapter` 接口
2. **OS 原语优先** — 不依赖 CLI 自身的进程管理能力
3. **Session 先注册再使用** — 没有"看不见"的 session
4. **入口和调度解耦** — 消息入口不关心谁执行
5. **不与 CLI 回收对抗** — 有价值的归档，无价值的放手
6. **先跑通再优化** — 文件系统 → SQLite → 消息队列
