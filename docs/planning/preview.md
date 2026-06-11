# 项目速览 (Preview)

> Agent 集群操控系统 — 主 Agent 操控多个 CLI 子 Agent 并行工作。

---

## 一句话

用一个 AI（主 Agent）调度管理多个 AI CLI（CodeBuddy Code、Copilot CLI 等），让它们像团队一样分工协作。

---

## 当前进度

```
Phase 0  初始化           ████████████ ✅
Phase 1  技术验证          ████████████ ✅  2026-06-11 完成
Phase 2  最小可行系统       ░░░░░░░░░░░░ ⏳  下一步
Phase 3  可视化 + 扩展      ░░░░░░░░░░░░ 📋
Phase 4  完整集群          ░░░░░░░░░░░░ 📋
```

---

## 架构（三句话）

```
用户 → 消息网关 → 主 Agent → 调度器 → 适配器 → CLI 进程
```

1. **消息网关** — 统一多入口（CLI/Web/QQ），归一化为标准消息
2. **主 Agent + 调度器** — 拆分任务，分发到子 Agent
3. **适配器 + 进程管理** — 每种 CLI 一个适配器，用 OS 进程原语统一控制

---

## 关键技术决策

| 决策 | 方案 | 淘汰的方案 |
|------|------|-----------|
| 多轮对话 | spawn 独立进程 + stream-json + --resume | --bg 管道多轮（失败） |
| 进程管理 | OS 原语 (PID/kill/wait) | 依赖 CLI 自身 ps/logs（不可移植） |
| 跨 CLI 兼容 | 适配器模式，差异仅命令行参数 | — |
| Session 管理 | 自定义 sessions.json + PID | CLI 自带 session 管理（不统一） |
| 记忆隔离 | 子 Agent 独立 workdir | 共享目录 MEMORY.md（会泄露） |
| Windows 操控 | node-pty (bash 包装) | tmux（Windows 不可用） |

---

## 适配器统一接口

```typescript
interface AgentAdapter {
  spawn(name, workdir): { pid, sessionId }
  execute(sessionId, task): TaskResult
  continue(sessionId, task): TaskResult
  status(sessionId): AgentStatus
  destroy(sessionId): void
  list(): AgentSnapshot[]
}
```

## CLI 厂商差异（已掌握）

| | CodeBuddy Code | Copilot CLI |
|--|---------------|-------------|
| 非交互调用 | `-p --stream-json` | `-p --silent --yolo` |
| 上下文恢复 | `--resume <id>` | `--continue` / `--resume` |
| 输出格式 | SSE 流 | JSONL |
| 后台进程管理 | 有 --bg（不需要，OS 层补齐） | 无（OS 层补齐） |
| 跨目录 Session | ❌ 绑定 --cwd | 待验证 |
| Session 过期机制 | ❌ 不可永久保留 | 待验证 |
| 原生 Session 删除 | ❌ 无 | 待验证 |

> **结论**：调度器和适配器不能依赖 CLI 自身能力管理 session 生命周期，需在 OS 层（进程管理 + sessions.json）统一补齐。详见 [项目总览 - CLI 差异章节](./planning/project-overview.md#cli-差异与调度注意事项)。

---

## 目录结构

```
MyAgentsPlan/
├── docs/
│   ├── planning/      → 项目计划 + 总览
│   ├── architecture/  → 架构设计 + 进程控制方案
│   └── analysis/      → 外部项目分析 (OpenClaw/CAO)
├── experiments/       → 5 个已完成的 Phase 1 实验
├── packages/          → monorepo 源码 (Phase 2 开始写)
├── sessions/          → 子 Agent 独立 workdir
└── logs/              → 运行日志
```

---

## 下一步（Phase 2）

1. `packages/core/src/session-manager.ts` — Session 注册表 + PID 管理
2. `packages/adapters/cbc-adapter/src/adapter.ts` — CBC 适配器实现
3. `packages/core/src/task-queue.ts` — 任务队列
4. 端到端：启动 2 个子 cbc，并行派发任务

---

## 参考文档

- [项目总览](./planning/project-overview.md) — 完整任务清单 + 实验结论
- [架构设计](./architecture/agent-cluster-architecture.md) — 详细分层设计
- [进程控制方案](./architecture/shell-process-control.md) — OS 原语统一管理
- [实验索引](../../experiments/) — 全部 Phase 1 实验报告
