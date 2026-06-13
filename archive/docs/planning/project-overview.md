# 项目总览 — Markdown 版

> **主要文档**：[project-overview.html](./project-overview.html)（HTML 版，包含完整交互式内容）。
> 本文档内容与 HTML 版保持同步。

---

## 一句话

用一个 AI（主 Agent）调度管理多个 AI CLI（CodeBuddy Code、Copilot CLI 等），让它们像团队一样分工协作。

---

## 架构

```
用户 → 消息网关 → 主 Agent → 调度器 → 适配器 → CLI 进程
```

1. **消息网关** — 统一多入口（CLI/Web/QQ），归一化为标准消息
2. **主 Agent + 调度器** — 拆分任务，分发到子 Agent
3. **适配器 + 进程管理** — 每种 CLI 一个适配器，用 OS 进程原语统一控制

---

## 当前进度

```
Phase 0  初始化           ████████████ ✅ 100%
Phase 1  实验验证          ████████████ ✅ 100%（16 项实验）
Phase 2  最小可行系统      ░░░░░░░░░░░░ ⏳ 0%
Phase 3  扩展和可视化      ░░░░░░░░░░░░ 📋 待开始
Phase 4  完整集群          ░░░░░░░░░░░░ 📋 待开始
```

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

## CLI 厂商差异

| 维度 | CodeBuddy Code | Copilot CLI |
|------|---------------|-------------|
| 非交互调用 | `-p --stream-json` | `-p --silent --yolo` |
| 上下文恢复 | `--resume <id>` | `--continue` / `--resume` |
| 输出格式 | SSE 流 | JSONL |
| 后台进程管理 | 有 --bg（不需要，OS 层补齐） | 无（OS 层补齐） |
| 跨目录 Session | ❌ 绑定 --cwd | 待验证 |
| Session 过期机制 | ❌ 不可永久保留 | 待验证 |
| 原生 Session 删除 | ❌ 无 | 待验证 |

> **结论**：调度器和适配器不能依赖 CLI 自身能力管理 session 生命周期，需在 OS 层（进程管理 + sessions.json）统一补齐。

---

## Phase 0：项目初始化 ✅

| 任务 | 产出 |
|------|------|
| 终端/CLI 概念学习 | [terminal-cli-concepts.md](../architecture/terminal-cli-concepts.md) |
| Agent 集群架构设计 | [agent-cluster-architecture.md](../architecture/agent-cluster-architecture.md) |
| 外部资源收集 | [resource-index.md](../resource-index.md) |
| 项目结构初始化 | monorepo 目录 + package.json |
| CAO 源码研究 | [cao-analysis.md](../analysis/cao-analysis.md) |
| OpenClaw 架构分析 | [openclaw-architecture.md](../analysis/openclaw-architecture.md) |

---

## Phase 1：持久化 Session 操控实验 ✅（16 项实验）

### 方案对比

| 方案 | 可行性 | 跨 CLI | 复杂度 | 推荐度 |
|------|--------|--------|--------|--------|
| **A: --bg 后台 Worker** | ❌ 不可行 | 差 | 中 | 淘汰 |
| **B: PTY 终端操控** | ⚠️ 有条件 | 好 | 高 | 备选 |
| **C: --resume 独立进程** | ✅ 可行 | 中 | 低 | 可用 |
| **D: child_process.spawn** | ✅ 可行 | 好 | 中 | **首选** |

### 首选方案：Shell / child_process 通用进程控制（方案D）

**思路**：上移一层到 OS 级别，不依赖 CLI 自己的 --bg/ps/logs，用操作系统原语统一管理所有 CLI 进程。

| 操作 | CBC 结果 | Copilot 结果 | 报告 |
|------|---------|-------------|------|
| 后台启动 | ✅ | ✅ | [s5](../experiments/01-cbc-persistent/s5-shell-control-cbc.md) |
| PID 追踪 | ✅ | ✅ | [s5](../experiments/01-cbc-persistent/s5-shell-control-cbc.md) |
| 多 Worker 并行 | ✅ | ✅ | [s5](../experiments/01-cbc-persistent/s5-shell-control-cbc.md) |
| --resume 上下文 | ✅ | ✅ | [s3](../experiments/01-cbc-persistent/s3-resume-capability.md) |

核心代码（详见 [shell-process-control.md](../architecture/shell-process-control.md)）：

```typescript
class ProcessManager {
  spawn(name, cmd, args) {
    const child = spawn(cmd, args);
    const id = `${name}-${Date.now()}`;
    this.workers.set(id, { pid: child.pid, process: child });
    child.on('exit', code => this.onExit(id, code));
    return id;
  }
  isAlive(id) {
    try { process.kill(this.workers.get(id).pid, 0); return true; }
    catch { return false; }
  }
  kill(id) { this.workers.get(id)?.process.kill(); }
}
```

### 废案（A/B/C，保留备查）

#### 方案A：--bg 后台 Worker 模式 — ❌ 不可行

| CLI | 测试项 | 结果 | 报告 |
|-----|--------|------|------|
| CodeBuddy Code | --bg 后台持久 | 不支持 — 任务完成即退出 | [s1](../experiments/01-cbc-persistent/s1-stream-json-multiturn.md) |
| CodeBuddy Code | 管道多轮 stream-json | 失败 — 进程 hang | [s1](../experiments/01-cbc-persistent/s1-stream-json-multiturn.md) |
| CodeBuddy Code | attach 接入会话 | 有条件 — 需要 TTY | [s2](../experiments/01-cbc-persistent/s2-bg-attach-behavior.md) |
| Copilot CLI | --bg 及等价功能 | 不存在 — & 是云端委托 | [s4](../experiments/01-cbc-persistent/s4-copilot-bg.md) |

> 结论：--bg 方案不可行。CBC 的 --bg 是 fire-and-forget 而非持久进程。

#### 方案B：PTY 终端操控 — ⚠️ 备选保留

| 实验 | 结果 | 报告 |
|------|------|------|
| tmux 操控 | Windows 不可用 | [t1](../experiments/02-pty-control/t1-tmux-sendkeys.md) |
| node-pty + powershell | 可用 | [t2](../experiments/02-pty-control/pty-experiment-summary.md) |
| node-pty + codebuddy --print | 需 bash 包装 | [t2-v2](../experiments/02-pty-control/pty-experiment-summary.md) |
| ANSI 输出清洗 | stripAnsi 有效 | [t3](../experiments/02-pty-control/pty-experiment-summary.md) |
| E01 — PTY 启动交互式 cbc | ✅ TUI 捕获 + 文本发送 | [e01](../experiments/02-pty-control/pty-experiment-summary.md) |
| E02 — / 指令通过 PTY | ✅ /help /model /clear 可用 | [e02](../experiments/02-pty-control/pty-experiment-summary.md) |
| E03 — 特殊按键 (Tab/Ctrl+C) | ✅ Tab thinking 切换；Ctrl+C 可发送 | [e03](../experiments/02-pty-control/pty-experiment-summary.md) |
| E04 — 多轮 PTY 对话 | ✅ 发送通过（AI 回复超时） | [e04](../experiments/02-pty-control/pty-experiment-summary.md) |

> 结论：核心 I/O 路径已验证，已可用于无 --resume CLI 的适配器开发。

#### 方案C：stream-json + --resume（独立进程）— ✅ 可行

| 测试 | 结果 | 报告 |
|------|------|------|
| 单轮 stream-json | 完美 | [s1](../experiments/01-cbc-persistent/s1-stream-json-multiturn.md) |
| --resume 上下文 | 上下文完全保持 | [s3](../experiments/01-cbc-persistent/s3-resume-capability.md) |
| --fork-session 分支 | 分支正常（auto memory 泄露） | [s3](../experiments/01-cbc-persistent/s3-resume-capability.md) |
| 并行 2 Worker | W1=111, W2=222 各自正确 | [s5](../experiments/01-cbc-persistent/s5-shell-control-cbc.md) |

> 结论：方案C 可行，--resume 机制在方案D 中作为底层技术被保留。

### 多实例并发

| 实验 | 结论 | 报告 |
|------|------|------|
| 两个 cbc 并发 | 正常，无冲突 | [c1](../experiments/03-concurrent/c1-multi-instance.md) |
| MEMORY.md 并发写入 | 需独立 workdir 隔离 | [c2](../experiments/03-concurrent/c1-multi-instance.md) |

### Phase 1 核心结论

- **多轮对话**：`spawn + stream-json + --resume`（方案 D）✅
- **进程管理**：OS 原语 (PID/kill -0/kill) ✅
- **输出解析**：stream-json 结构化输出 ✅（--print 模式）
- **PTY 交互式控制** ✅ TUI 捕获 / 文本发送 / /指令 / Tab 键均验证通过
- **Windows PTY 路径**：bash wrapper 方式 ✅
- **记忆隔离**：每个子 Agent 独立 `sessions/<agent-id>/` workdir ✅
- **Session 管理**：自定义 sessions.json + PID 追踪 ✅

---

## Phase 2：最小可行系统 ⏳

> 基于 Phase 1 结论（方案D），实现 session-manager → cbc-adapter → task-queue → CLI 入口 的完整链路。
> PTY 路径已完成核心验证，无 --resume 的 CLI 适配器可基于 PTY 方案开发。

| 模块 | 文件 | 内容 |
|------|------|------|
| 2.1 Session Manager | `packages/core/src/session-manager.ts` | 实例注册/注销、心跳、sessions.json、状态机 |
| 2.2 CbcAdapter | `packages/adapters/cbc-adapter/src/adapter.ts` | spawn/execute/continue/destroy/list/status |
| 2.3 任务队列 | `packages/core/src/task-queue.ts` | 文件系统队列，pending→running→done/failed |
| 2.4 CLI 入口 | `packages/main/src/index.ts` | spawn/ps/run 命令 |
| 2.5 端到端测试 | `tests/e2e/` | 2 子 cbc 并行派发任务 |

---

## Phase 3：扩展和可视化 📋

Web Dashboard (xterm.js)、其他 CLI 适配器（Claude Code / Aider / Shell）、多渠道入口（Web / QQ Bot）。

## Phase 4：完整集群 📋

消息队列、负载均衡、子 Agent 间协作、持久化记忆共享。

---

## CLI 差异与调度注意事项

> 不同 CLI 在 session 管理、工作目录隔离、生命周期等方面存在显著差异。调度器和适配器必须考虑这些差异。

### CBC 已知约束

| 维度 | 状态 | 应对 |
|------|------|------|
| 跨目录 Session | ❌ 绑定 --cwd | 追踪 `{ sessionId, workdir }` |
| 长闲置 Session | ❌ 可能过期 | 有价值则归档，无价值让 CBC 自己回收 |
| Session 删除 | ❌ 无原生接口 | OS 层 kill + 清理 sessions.json |
| Session 列表查询 | ❌ 有限 | 不依赖 CLI 自带列表 |

### Session 归档策略

**核心思路：不与 CLI 的 session 回收对抗，由主 Agent 统一接管管理。**

三种 session，三种处理：

| 类型 | 策略 | 负责方 |
|------|------|--------|
| **活跃 session** | 心跳保活 | 调度器 |
| **无价值 session** | 不处理，让 CLI 自己 GC | CLI（免费） |
| **有价值 session** | 主 Agent 显式标记后归档 | 主 Agent + 调度器 |

归档内容：

| 数据 | 短期意义 | 长期意义 | 存储 |
|------|---------|---------|------|
| Session 元数据 (sessionId, CLI类型, workdir, 标签, 摘要) | 高 — 快速索引/查询 | 中 — 不同CLI格式不同 | `sessions.json` |
| 完整对话历史 (messages[], 跨CLI通用) | 低 | 高 — 未来可能抛弃元数据 | `archive/{sessionId}.json` |

> **决策：当前阶段两者都存。** 短期靠元数据快速查询，长期靠对话历史实现跨 CLI session 迁移。

归档触发：主 Agent 显式调用 `markValuable(sessionId)`（非调度器启发式）。
重建流程：读取 `archive/` 中的对话历史 → 新 spawn → 注入历史。

### CLIIdentity 能力矩阵

```typescript
interface CLIIdentity {
  name: string
  capabilities: {
    crossDirResume: boolean     // --resume 是否跨目录有效
    sessionTTL: number | null   // session 过期时间（毫秒），null 表示永久
    nativeSessionDelete: boolean // 是否有原生 session 删除
    nativeSessionList: boolean  // 是否有原生 session 列表
  }
}
```

### 后续验证项

- [x] ~~CBC session 实际过期时间~~ → 策略已定：走归档+重建
- [ ] 其他 CLI（Claude Code / Aider）session 行为
- [ ] 跨目录 resume 精确边界

---

## 实验报告索引（16 项，全部完成）

```
experiments/
├── cbc-multi-cli-experiment.md       # 初始探索：--print vs --bg
├── 01-cbc-persistent/                # Phase 1.1 — CBC 持久化 session
│   ├── s1-stream-json-multiturn.md   # --bg + stream-json 多轮
│   ├── s2-bg-attach-behavior.md      # --bg + attach 行为
│   ├── s3-resume-capability.md       # --resume 能力探索（核心发现）
│   ├── s4-copilot-bg.md              # Copilot CLI --bg 等价能力
│   └── s5-shell-control-cbc.md       # Shell 级进程控制验证
├── 02-pty-control/                   # Phase 1.2 — PTY 操控
│   ├── pty-control-guide.md          # PTY 操控知识文档
│   ├── pty-experiment-summary.md     # PTY 全 I/O 操控总结
│   └── t1-tmux-sendkeys.md           # tmux 操控（Windows 不可用）
└── 03-concurrent/                    # Phase 1.3 — 多实例并发
    ├── c1-multi-instance.md          # 多实例并发 + 记忆隔离
    └── c1-multi-instance.md          # MEMORY.md 并发写入冲突
```

---

## 参考

- [HTML 总览（主要文档）](./project-overview.html)
- [架构设计](../architecture/agent-cluster-architecture.md)
- [进程控制方案](../architecture/shell-process-control.md)
- [实验索引](../../experiments/experiment-index.md)
