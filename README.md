# Agent 集群系统 (MyAgentsPlan)

> 通过一个主 Agent 操控管理多个子 CLI/IDE，支持多轮长对话，session 可追踪。

## 目标

1. 用户可通过 QQ、Web、邮件、CLI 等任意方式与主 Agent 交流
2. 主 Agent 将任务拆分，分发到多个子 CLI (cbc、Claude Code、Aider 等) 并行执行
3. 每个子 session 全程可追踪、可监控、可干预

## 当前阶段

Phase 1 — 持久化 Session 操控实验：验证多轮长对话的技术可行性（`--print` 已废弃）

## 文件导航

### 文档

| 文件 | 内容 |
|------|------|
| [docs/planning/beforeInit.md](./docs/planning/beforeInit.md) | 原始需求描述 |
| [docs/planning/preview.md](./docs/planning/preview.md) | 项目速览（一页总结） |
| [docs/planning/project-overview.md](./docs/planning/project-overview.md) | 项目总览（进度 + 实验结论） |
| [docs/architecture/agent-cluster-architecture.md](./docs/architecture/agent-cluster-architecture.md) | 架构设计方案 |
| [docs/architecture/shell-process-control.md](./docs/architecture/shell-process-control.md) | 通用 CLI 进程控制方案 |
| [docs/architecture/terminal-cli-concepts.md](./docs/architecture/terminal-cli-concepts.md) | 终端/CLI底层概念学习笔记 |
| [docs/analysis/openclaw-architecture.md](./docs/analysis/openclaw-architecture.md) | OpenClaw 架构分析 |
| [docs/analysis/cao-analysis.md](./docs/analysis/cao-analysis.md) | CAO 项目分析 |
| [docs/resource-index.md](./docs/resource-index.md) | 外部资源索引 |

### 其他目录

| 目录 | 内容 |
|------|------|
| [experiments/](./experiments/) | 实验记录 |
| [experiments/cbc-multi-cli-experiment.md](./experiments/cbc-multi-cli-experiment.md) | CBC 多 CLI 操控实验 |
| [experiments/02-pty-control/pty-control-guide.md](./experiments/02-pty-control/pty-control-guide.md) | PTY 操控 CLI 完整指南 |
| [packages/](./packages/) | monorepo 源码 |

## 技术栈（待定）

- 主控：Node.js / TypeScript
- PTY 操控：node-pty / tmux
- 子 Agent：CodeBuddy Code、Claude Code 等 CLI 工具
- 通信：stdin/stdout JSON 流 / Unix Socket / PTY

## 原则

1. **适配器模式** — 每种 CLI 一个适配器，统一接口
2. **Session 先注册再使用** — 没有"看不见"的 session
3. **入口和调度解耦** — 消息入口不关心谁执行
4. **先跑通再优化** — 文件系统 → SQLite → 消息队列
