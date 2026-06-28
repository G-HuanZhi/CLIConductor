# CLIConductor 全局规划

> 最后更新：2026-06-28

---

## 一、项目目标

### 一句话

通过一个 Meta-Agent 调度管理多个第三方 AI CLI 进程（Worker），同时人类可随时观察、插话、接管任意子进程。

**"Meta-Agent" 定义**：具有与 Worker 交互权限和能力的上层 Agent（如 CodeBuddy Code），通过专用 WS 通道（`/ws/agent`）读取事件流、派发任务、管理 Worker 生命周期。

### 角色与关系

```
人类 (1人, 本地PC)
  ├─ Dashboard（WS + HTTP）观察/注入/接管
  │
Meta-Agent (外部 AI, 如 CodeBuddy)
  ├─ /ws/agent 通道：事件流 + 命令派发
  │
CLIConductor（中间件）
  ├─ Session Manager + Worker 池
  ├─ Worker-1 ── cbc (stdin stream-json 长驻)
  ├─ Worker-2 ── cbc
  └─ Worker-N ── cbc
```

### 核心价值

- **统一管理** — CLI 的输入/输出/特殊命令（`/model`）/ session 被统一封装
- **随时介入** — 不止看到 Agent 跑，还能插话、接管（kill + --resume）
- **Session 可控** — 所有子 CLI session 可追踪、可持久化、可恢复
- **命令来源辨別** — `send_task()` 含 `source` 参数（`"agent"` / `"user"`），两套独立 WS 通道，为后续权限分离预留

---

## 二、架构总览

```
         Meta-Agent                   人类
    (CodeBuddy 等)              (Dashboard)
          │                          │
    /ws/agent 通道              /ws + HTTP
    （事件流 + 命令）          （观察 + 注入 + 接管）
          │                          │
          └──────────┬───────────────┘
                     │
            ┌────────▼────────┐
            │  CLIConductor    │
            │  (FastAPI 服务)   │
            │                   │
            │  Session Manager │
            │  ├─ Worker-1     │── cbc (stream-json 长驻)
            │  ├─ Worker-2     │── cbc (stream-json 长驻)
            │  └─ Worker-N     │── ...
            │                   │
            │  Event Bus       │─── WS 广播
            │  Session Store   │─── JSON 持久化
            └──────────────────┘
```

### 核心机制

#### cbc 集成模式（长驻进程）

```bash
cbc -p --output-format stream-json --input-format stream-json -y
```

- stdin：持续写入 JSON 格式的 user 消息
- stdout：逐行解析 stream-json 事件（thinking / text / tool_use / result）
- `-y`：跳过所有权限确认
- 进程不退出，result 事件后继续等待下一条 stdin

#### 消息队列（stdin 互斥）

```
Agent 任务 ──→ asyncio.Queue (FIFO) ──→ consumer ──→ cbc.stdin.write()
用户注入 ──→                                         result → 取下一条
```

- 同一时间只有一人在说话
- result 事件是切换信号
- takeover 后状态变 held，拒绝所有输入

#### 特殊命令处理

cbc 的 `/model`、`/branch`、Shift+Tab 等无法通过 stdin stream-json 发送。解决方案：kill + `--resume <session_id>` + CLI 参数重启。

| 命令 | CLI 等效 | 实现方式 |
|------|---------|---------|
| `/model` | `--model <model>` | kill + --resume + --model 重启 |
| Shift+Tab | `--permission-mode <mode>` | kill + --resume + --mode 重启 |
| `/branch` | `--resume <sid> --fork-session` | 新建 Worker + 新 Session |
| `/rename` | 无（cbc 无 name 概念） | CLIConductor 自维护 Session name |

---

## 三、功能路线图

### Phase 1 — 最小完整功能（进行中）

| 功能 | 状态 |
|------|:----:|
| Worker 管理（spawn / list / kill / restart / branch） | ✅ |
| Session 独立管理（UUID 持久化，kill 不删 Session） | ✅ |
| Meta-Agent 任务派发（HTTP API + /ws/agent → 消息队列 → cbc stdin） | ✅ |
| Dashboard 实时观察（WebSocket 事件推送 + 聊天式 UI） | ✅ |
| 用户插话（Dashboard 输入 → WS 注入 Worker 队列） | ✅ |
| 用户接管（`cbc --resume <cbcSessionId>` 原生终端） | ✅ |
| Session 持久化（JSON 文件，UUID key，独立生命周期） | ✅ |
| Worker/Session 概念分离 | ✅ |
| cbc --resume 重放去重（_replaying 标志） | ✅ |
| 中断任务（kill + --resume 重启） | ✅ |
| 优雅关闭（lifespan handler） | ✅ |
| 命令来源辨别（agent / user，独立 WS 通道） | ✅ |

### Phase 2 — 扩展

| 功能 | 描述 |
|------|------|
| 多 CLI 适配器 | Claude Code / Copilot 等 |
| 崩溃自动恢复 | Worker 进程崩溃自动重启 |
| 信息网关 | QQ / 微信等多端接入 |
| 全局记忆 | Meta-Agent 跨 Worker 的持久化记忆 |
| Session 归档 | 标记有价值 session，长期保留 |
| 中间输出实时保存 | stream 事件时增量保存，防崩溃丢数据 |

### Phase 3+ — 完善

| 功能 |
|------|
| Worker 池自动分配 |
| Worker 间通信 |
| SQLite 替代 JSON 存储 |
| 无人值守长时间运行 |

---

## 四、技术栈

| 技术 | 选择 | 状态 |
|------|------|:----:|
| 语言 | Python 3.14 | 锁定 |
| Web 框架 | FastAPI + uvicorn | 锁定 |
| 进程管理 | `asyncio.create_subprocess_exec` | 锁定 |
| CLI 连接 | `cbc -p --output-format stream-json --input-format stream-json -y`（长驻）| 锁定 |
| 多轮对话 | stdin 持续写入（长驻进程，单次 --resume 启动） | 锁定 |
| 用户接管 | `cbc --resume <cbcSessionId>`（原生 PowerShell）| 锁定 |
| 实时通信 | WebSocket（FastAPI）| 锁定 |
| 前端 | 单页 HTML（原生 JS，无框架）| 锁定 |
| 存储 | JSON 文件 → 未来 SQLite | 演进 |

---

## 五、核心设计原则

1. **从最小完整链路做起** — 一条完整的 Agent→Worker→Dashboard→用户介入链路先跑通
2. **不堵死长远路** — 接口预留扩展点，不提前写代码
3. **每个 Worker 独立 workdir** — 避免 memory 相互污染
4. **消息队列 + consumer 模式** — 确保 stdin 互斥写入，一次一条
5. **Worker 与 Session 分离** — Worker 是运行时进程，Session 是持久数据，kill 不删 Session
6. **命令来源辨別** — 源头标记（agent/user），为权限分离预留
7. **参考 DionysusC** — Strategy 模式、stream-json 解析、session ID 提取已验证

---

## 六、已知问题

### 6.1 cbc 特殊命令无法通过 stdin stream-json 发送

已在「特殊命令处理」节说明，通过 kill + --resume + CLI 参数重启实现。

### 6.2 多端注入互斥

当前通过 asyncio.Queue FIFO 天然保证。takeover 后 held 态禁止所有输入。

### 6.3 cbc 进程不存在时的启动回退

Dashboard 发消息时若 Workers 不存在，自动 spawn。Restart 按钮同理。

---

## 七、命名约定

| 术语 | 定义 |
|------|------|
| **Meta-Agent** | 具有与 Worker 交互权限和能力的上层 AI Agent（如 CodeBuddy Code）。通过 `/ws/agent` 通道读取事件流、派发任务、管理生命周期。区别于"人类用户"和"Worker（子 CLI 进程）"。 |
| **Worker** | 一个运行中的 cbc 子进程。持有一个 Session UUID，进程终止后不删除 Session。 |
| **Session** | 持久化会话。UUID 管理（`ses_<16hex>`），包含 cbc_session_id、history、last_result 等，独立于 Worker 生命周期。 |
| **Human** | 人类用户。通过 Dashboard（`/ws` 通道 + HTTP API）观察、插话、接管。命令来源标记为 `"user"`。 |

---

## 八、成功标准

| # | 标准 | 状态 |
|---|------|:----:|
| 1 | Meta-Agent 向 Worker-1 和 Worker-2 各派一个任务，两个同时执行 | ✅ |
| 2 | Dashboard 实时显示两个 Worker 的流式输出 | ✅ |
| 3 | Dashboard 向 Worker-1 注入消息，Worker-1 在后续对话中响应 | ✅ |
| 4 | 人类接管 Worker-2 的 cbc 终端，退出后 Agent 恢复控制 | ✅ |
| 5 | 系统重启后，Session 可从本地存储恢复，Worker 按需 spawn | ✅ |
| 6 | Meta-Agent 通过专用 WS 通道接收事件 + 派发任务 | ✅ |
| 7 | Worker 和 Session 概念分离，kill 不删 Session | ✅ |
