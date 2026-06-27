# CLIConductor 全局规划

> 最后更新：2026-06-27

---

## 一、项目目标

### 一句话

通过一个主 Agent 操控管理多个第三方 CLI/IDE 子 Agent，实现跨厂商 Agent 集群。

### 面向谁

| 维度 | 阶段一（MVP） | 长远 |
|------|:-----------:|:----:|
| 人类用户 | 1 人（PC 本地） | 开放信息网关，支持多人多端 |
| 主 Agent | 能读本项目 API/事件的任何 Agent（纯 API / OpenClaw / CBC 等） | 同左 |
| Worker 规模 | 2-5 个子 CLI | 不限 |

### 核心价值

- **统一管理** — CLI 的输入/输出/特殊命令（`/model`）/ session 被统一封装
- **随时介入** — 不止看到 Agent 跑，还能插话、接管
- **session 可控** — 所有子 CLI session 可追踪、可归档、可重建

---

## 二、架构总览

```
                           你（人类）
                              │
          ┌───────────────────┼──────────────────┐
          ▼                   ▼                  ▼
    CLI 入口            Dashboard           信息网关
    (命令行控制)        (Web 终端)          (QQ/微信等)
          │                   │                  │
          └───────────────────┼──────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  CLIConductor     │
                    │  (Node.js 服务)    │
                    │                    │
                    │  Session Manager  │
                    │  ├─ Worker-1      │── cbc (stream-json)
                    │  ├─ Worker-2      │── cbc (stream-json)
                    │  └─ Worker-N      │── ...
                    │                    │
                    │  Adapter Layer   │
                    │  (Strategy 模式)  │
                    │                    │
                    │  Event Bus        │─── 事件管道
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │     主 Agent       │
                    │  (CodeBuddy 等)    │
                    │  读事件 → 发任务   │
                    └───────────────────┘
```

---

## 三、功能路线图

### Phase 1 — 最小完整功能（first_plan.md）

**主 Agent 操控 2 个 Worker + 你随时观察/插话/接管**

| 功能 | 描述 |
|------|------|
| Worker 管理 | spawn / list / kill |
| Agent 任务派发 | Agent 向 Worker 发任务，获取结构化结果 |
| 实时观察 | Dashboard 实时显示每个 Worker 的对话和事件 |
| 插话 | 在 Dashboard 输入消息，注入到 Worker 会话 |
| 接管 | 打开 PTY 交互终端，完全操控 Worker |
| Session 本地存储 | session ID 元数据 + 对话历史 |

### Phase 2 — 扩展

| 功能 | 描述 |
|------|------|
| 多 CLI 适配器 | Claude Code / Copilot 等 |
| 信息网关 | QQ / 微信等多端接入 |
| Session 归档重建 | 归档有价值 session，跨进程重建 |
| 全局记忆 | 主 Agent 跨 Worker 的持久化记忆 |

### Phase 3+ — 完善

| 功能 | 描述 |
|------|------|
| 负载均衡 | Worker 池自动分配 |
| 子 Agent 协作 | Worker 之间通信 |
| 消息队列 | 替代简单调度 |

---

## 四、核心设计原则

1. **从最小完整链路做起** — 一个主 Agent → 两个 Worker → 你能看能插能接管。这条链路先跑通。
2. **不堵死长远路** — 接口设计预留扩展点（Strategy 模式、事件协议通用化），但不提前写代码
3. **先实验验证** — 不确定的技术点先跑 50 行实验，不猜测
4. **借鉴 DionysusC** — Strategy 模式、事件管道、session ID 提取等已验证模式直接采用
5. **每个 Worker 独立 workdir** — 避免 memory 相互污染

---

## 五、技术栈（全局）

| 技术 | 选择 | 锁定 / 暂定 |
|------|------|:--:|
| 语言 | TypeScript | 锁定 |
| 运行时 | Node.js | 锁定 |
| 进程管理 | `child_process.spawn` | 锁定 |
| CLI 连接方式 | `cbc -p --output-format stream-json --input-format stream-json -y` | 锁定 |
| 多轮对话 | stdin 持续写入（不需要 --resume） | 锁定 |
| PTY | `node-pty`（接管模式） | 暂定 |
| Dashboard | Web + WebSocket + xterm.js | 暂定 |
| 前端 | React / 原生 HTML | 待定 |
| 存储 | 文件系统 → SQLite | 演进 |

---

## 六、不做的事

| 不做 | 理由 |
|------|------|
| 实现主 Agent 的"大脑"逻辑 | 主 Agent 是外部的（CodeBuddy / API），本项目只做管理中间件 |
| 任务自动拆分/调度 | Phase 1 主 Agent 手动派发，Phase 2+ 再考虑 |
| TypeScript monorepo 工程化 | 先用 tsx 单包跑 |
| 单元测试/E2E | 手动验证即可 |

---

## 七、成功标准

| Phase | 标准 |
|-------|------|
| Phase 1 | 主 Agent 向 2 个 Worker 各派 1 个任务，你看到实时输出，你插句话 Worker 能响应，你接管终端能操控 |
| Phase 2 | 多 CLI 适配器，多端入口 |
| Phase 3+ | 无人值守长时间运行 |
