# 项目总览 (Project Overview)

> **目标**：构建 Agent 集群操控系统，主 Agent 操控多个子 CLI，支持多轮长对话，session 可追踪。
> **当前阶段**：Phase 1 已完成 → 进入 Phase 2
> 其他文档：[架构设计](../architecture/agent-cluster-architecture.md) | [资源索引](../resource-index.md)

---

## 进度总览

```
Phase 0  初始化         ████████████ ✅ 100%
Phase 1  实验验证        ████████████ ✅ 100%
Phase 2  最小可行系统    ░░░░░░░░░░░░ ⏳ 0%
Phase 3  扩展和可视化    ░░░░░░░░░░░░ 📋 待开始
Phase 4  完整集群        ░░░░░░░░░░░░ 📋 待开始
```

---

## Phase 0：项目初始化 ✅

| 任务 | 成果 |
|------|------|
| 终端/CLI 概念学习 | [terminal-cli-concepts.md](../architecture/terminal-cli-concepts.md) |
| Agent 集群架构设计 | [agent-cluster-architecture.md](../architecture/agent-cluster-architecture.md) |
| 外部资源收集 | [resource-index.md](../resource-index.md) |
| 项目文件结构初始化 | monorepo 目录 + package.json |
| CAO 源码研究 | [cao-analysis.md](../analysis/cao-analysis.md) — 结论：不直接使用，借鉴架构 |

---

## Phase 1：持久化 Session 操控实验 ✅

> 核心目标：找到一种可靠方式，让主 Agent 能对子 CLI 进行多轮对话操控。
> `--print` 单次问答方案已废弃，所有子 CLI 方案必须支持多轮上下文。

### 1.1 CBC 内部机制验证

| 实验 | 结论 | 报告 |
|------|------|------|
| `--bg` + stream-json 多轮 | `--bg` 不持久；管道多轮失败 | [s1-stream-json-multiturn.md](../../experiments/01-cbc-persistent/s1-stream-json-multiturn.md) |
| `--bg` + `attach` 行为 | attach 依赖 TTY；直接读 log 文件更可靠 | [s2-bg-attach-behavior.md](../../experiments/01-cbc-persistent/s2-bg-attach-behavior.md) |
| `codebuddy resume` 能力 | **`--resume <session_id>` 完美保持多轮上下文** ✅ | [s3-resume-capability.md](../../experiments/01-cbc-persistent/s3-resume-capability.md) |
| Copilot CLI --bg 实验 | 无 --bg；`&` 是云端委托；`--continue` 可用 | [s4-copilot-bg.md](../../experiments/01-cbc-persistent/s4-copilot-bg.md) |
| **Shell 级进程控制方案** | **通用方案：OS 原语替代所有 --bg/ps/logs** ✅ | [s5-shell-control-cbc.md](../../experiments/01-cbc-persistent/s5-shell-control-cbc.md) |

### 1.2 PTY 操控方案验证

| 实验 | 结论 | 报告 |
|------|------|------|
| PTY 操控知识文档 | ANSI 序列全集 + 5个实战示例 | [pty-control-guide.md](../../experiments/02-pty-control/pty-control-guide.md) |
| tmux 操控终端 | Windows 不可用；改用 node-pty | [t1-tmux-sendkeys.md](../../experiments/02-pty-control/t1-tmux-sendkeys.md) |
| node-pty 启动子进程 | 可用；需 bash 包装 codebuddy | [t2-node-pty.js](../../experiments/02-pty-control/t2-node-pty.js) |
| 终端输出清洗 | stripAnsi 有效 | [t3-output-cleaner.js](../../experiments/02-pty-control/t3-output-cleaner.js) |

### 1.3 多实例并发测试

| 实验 | 结论 | 报告 |
|------|------|------|
| 两个 cbc 并发运行 | 正常，无冲突 | [c1-multi-instance.md](../../experiments/03-concurrent/c1-multi-instance.md) |
| 文件锁/资源冲突 | 同目录共享 MEMORY.md；需独立 workdir 隔离 | [c2-resource-conflicts.js](../../experiments/03-concurrent/c2-resource-conflicts.js) |

### Phase 1 核心结论

| 技术选型 | 方案 |
|---------|------|
| **多轮对话** | `spawn 独立进程 + stream-json + --resume <session_id>` |
| **进程管理** | **Shell 级 OS 原语 (PID/kill -0/wait)** — 不依赖 CLI 自身 --bg |
| **跨 CLI 兼容** | 所有 CLI 统一用 child_process.spawn，差异仅命令行参数 |
| **输出解析** | stream-json 结构化输出（无需 stripAnsi） |
| **记忆隔离** | 每个子 Agent 独立 `sessions/<agent-id>/` 工作目录 |
| **Session 管理** | 自定义 sessions.json + PID 追踪 |
| **架构文档** | [shell-process-control.md](../architecture/shell-process-control.md) |
| **技术栈说明** | [Shell · child_process · Node.js 关系](../architecture/tech-stack-control-layer.md) |

### Phase 1 方案对比：PTY vs child_process

两种方案都通过了 Phase 1 验证。以下是对比：

| 维度 | PTY 方案 (node-pty) | child_process 方案 (spawn) | 结论 |
|------|-------------------|--------------------------|------|
| **操控粒度** | 模拟键盘输入，可处理交互式 TUI | 传参数传输入，无法交互 | spawn 够用 |
| **输出格式** | 原始终端输出（含 ANSI） | stdout/stderr 纯字节流 | spawn 更干净 |
| **输出解析** | 需要 stripAnsi + 帧检测 | 直接读 stream-json | **spawn 更简单** |
| **多轮对话** | 持续写 stdin、读 stdout | 每次独立进程 + --resume | **spawn 更可控** |
| **进程管理** | 依赖 PTY 生命周期 | OS 原生 PID + signal | 两者等价 |
| **Windows 兼容** | 需 bash 包装，ConPTY 可能不稳定 | 原生支持 | **spawn 更可靠** |
| **代码量** | ~200 行 (ANSI 解析 + 帧管理) | ~50 行 (spawn + onData) | **spawn 更少** |
| **适用场景** | 必须交互的 TUI 程序 | 有 --resume 的 CLI | 本项目**

**决策**：Phase 2 以 **child_process.spawn** 为主方案。PTY 方案保留为备选，仅在遇到不支持 --resume 的 CLI 时启用。

> 详见 [shell-process-control.md](../architecture/shell-process-control.md) — 包含完整 Node.js 代码和 ProcessManager 实现。

---

## 待解决问题

### 阻塞性（Phase 2 前必须明确）

- [ ] **CodeBuddy --resume 的 session 过期时间？** — 多久不活动后 session 不可恢复？
- [ ] **session_id 跨工作目录有效吗？** — --resume 需要 --cwd 保持一致还是可迁移？
- [ ] **独立 workdir 能否真正隔离 MEMORY.md？** — 实测验证不同 workdir 下 auto memory 不互串
- [ ] **子 Agent 的输出何时结束？** — 需要可靠的"回复完成"判定：result 消息？连续静默？提示符？

### 重要（Phase 2 中需要解决）

- [ ] **并发数上限** — 同一台机器最多稳定运行几个 cbc？受 API rate limit 限制？
- [ ] **错误恢复** — 子 Agent 中途崩溃，父进程如何感知？sessions.json 如何标记 dead？
- [ ] **超时处理** — 某个子任务卡住不返回，超时策略？
- [ ] **stdout 缓冲问题** — spawn 的大输出会不会撑爆 buffer？需要流式还是累积？
- [ ] **Copilot CLI 的 session_id 提取** — --output-format json 输出中没有明确的 session_id 字段，如何追踪？
- [ ] **跨平台一致性** — Linux/macOS 上 spawn 行为与 Windows 是否有差异？

### 优化项（Phase 3+ 再做）

- [ ] PTY fallback —— 遇到无 --resume 的 CLI 时自动降级
- [ ] Sub-agent 间直接通信（Agent A 结果传给 Agent B，跳过主 Agent）
- [ ] 分布式部署 —— 子 Agent 跑在其他机器上
- [ ] 持久化记忆共享 —— 多个子 Agent 共享同一份上下文

---

## Phase 2：最小可行系统 ⏳

- [ ] **2.1 Session Manager** — [packages/core/src/session-manager.ts](../../packages/core/src/session-manager.ts)
  - 实例注册/注销、心跳监控、sessions.json 持久化
  - 状态机：starting → ready → busy → error → dead

- [ ] **2.2 CbcAdapter** — [packages/adapters/cbc-adapter/src/adapter.ts](../../packages/adapters/cbc-adapter/src/adapter.ts)
  - 实现统一接口：spawn / execute / continue / destroy / list / status
  - 基于 Phase 1 结论：stream-json + --resume

- [ ] **2.3 任务队列** — [packages/core/src/task-queue.ts](../../packages/core/src/task-queue.ts)
  - 文件系统队列 (tasks/ 目录)
  - 状态：pending → running → done / failed
  - 支持优先级、超时、重试

- [ ] **2.4 CLI 主控入口** — [packages/main/src/index.ts](../../packages/main/src/index.ts)
  - 命令：`agent-cluster spawn <name>`, `agent-cluster ps`, `agent-cluster run <task>`

- [ ] **2.5 端到端测试** — 启动 2 个子 cbc，派发任务，验证多轮上下文

---

## Phase 3：扩展和可视化 📋

- [ ] **3.1 Web Dashboard** — [packages/dashboard/](../../packages/dashboard/) (xterm.js)
- [ ] **3.2 其他 CLI 适配器** — Claude Code / Aider / Shell 适配器
- [ ] **3.3 多渠道入口** — Web 页面 / QQ Bot

---

## Phase 4：完整集群 📋

- [ ] **4.1 消息队列** — Redis / RabbitMQ 替代文件队列
- [ ] **4.2 负载均衡** — 根据子 agent 状态分发任务
- [ ] **4.3 子 agent 间协作** — agent A 结果传递给 agent B
- [ ] **4.4 持久化记忆共享** — MEMORY.md 级别

---

## 实验报告索引

```
experiments/
├── 01-cbc-persistent/              ← Phase 1.1
│   ├── s1-stream-json-multiturn.md   --bg + stream-json 多轮测试
│   ├── s2-bg-attach-behavior.md      --bg + attach 行为测试
│   ├── s3-resume-capability.md       --resume 能力探索
│   ├── s4-copilot-bg.md              Copilot CLI 无 --bg 验证
│   └── s5-shell-control-cbc.md       Shell 级进程控制验证
├── 02-pty-control/                 ← Phase 1.2
│   ├── pty-control-guide.md          PTY 操控 CLI 完整指南
│   ├── t1-tmux-sendkeys.js           tmux 操控 (Windows 不可用)
│   ├── t2-node-pty.js                node-pty 启动子进程
│   └── t3-output-cleaner.js          ANSI 输出清洗工具
└── 03-concurrent/                  ← Phase 1.3
    ├── c1-multi-instance.md          多实例并发测试
    └── c2-resource-conflicts.js      资源冲突测试
```
