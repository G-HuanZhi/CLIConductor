# CLIConductor 全局规划

> 最后更新：2026-06-28

---

## 一、项目目标

### 一句话

通过一个主 Agent 调度管理多个第三方 AI CLI 子 Agent（cbc），同时人类可随时观察、插话、接管任意子进程。

### 面向谁

| 维度 | 阶段一（Phase 1） | 长远 |
|------|:-----------:|:----:|
| 人类用户 | 1 人（PC 本地） | 开放信息网关，支持多人多端 |
| 主 Agent | 能读本项目 API/WS 事件的任何 Agent | 同左 |
| Worker 规模 | 2-5 个 cbc 进程 | 不限 |

### 核心价值

- **统一管理** — CLI 的输入/输出/特殊命令（`/model`）/ session 被统一封装
- **随时介入** — 不止看到 Agent 跑，还能插话、接管（kill + --resume）
- **session 可控** — 所有子 CLI session 可追踪、可持久化、可恢复

---

## 二、架构总览

```
                     你（人类）
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
    CLI 入口      Dashboard     信息网关（未来）
          │             │             │
          └─────────────┼─────────────┘
                        │
              ┌─────────▼─────────┐
              │  CLIConductor     │
              │  (Python FastAPI) │
              │                    │
              │  Session Manager  │
              │  ├─ Worker-1      │── cbc (stream-json)
              │  ├─ Worker-2      │── cbc (stream-json)
              │  └─ Worker-N      │── ...
              │                    │
              │  Event Bus        │─── WebSocket 广播
              └─────────┬─────────┘
                        │
              ┌─────────▼─────────┐
              │    主 Agent        │
              │  (CodeBuddy 等)    │
              │  读事件 → 派发任务  │
              └───────────────────┘
```

---

## 三、功能路线图

### Phase 1 — 最小完整功能（进行中）

| 功能 | 状态 |
|------|:----:|
| Worker 管理（spawn / list / kill / restart / branch） | ✅ |
| Agent 任务派发（HTTP API → 消息队列 → cbc stdin） | ✅ |
| Dashboard 实时观察（WebSocket 事件推送） | ✅ |
| 用户插话（Dashboard 输入 → WS 注入 Worker 队列） | ✅ |
| 用户接管（`cbc --resume <sessionId>` 原生终端） | ✅ |
| Session 持久化（JSON 文件） | ✅ |
| 中断任务（kill + --resume 重启） | ✅ |
| 主 Agent WS 通道 | 待完成 |
| 重启恢复 Worker | 待完成 |
| 优雅关闭 | 待完成 |

### Phase 2 — 扩展

| 功能 | 描述 |
|------|------|
| 多 CLI 适配器 | Claude Code / Copilot 等 |
| 崩溃自动恢复 | Worker 进程崩溃自动重启 |
| 信息网关 | QQ / 微信等多端接入 |
| 全局记忆 | 主 Agent 跨 Worker 的持久化记忆 |
| Session 归档 | 标记有价值 session，长期保留 |

### Phase 3+ — 完善

| 功能 |
|------|
| Worker 池自动分配 |
| Worker 间通信 |
| SQLite 替代 JSON 存储 |
| 无人值守长时间运行 |

---

## 四、核心设计原则

1. **从最小完整链路做起** — 一条完整的 Agent→Worker→Dashboard→用户介入链路先跑通
2. **不堵死长远路** — 接口预留扩展点，不提前写代码
3. **每个 Worker 独立 workdir** — 避免 memory 相互污染
4. **消息队列 + consumer 模式** — 确保 stdin 互斥写入，一次一条
5. **借鉴 DionysusC** — Strategy 模式、stream-json 解析、session ID 提取已验证

---

## 五、技术栈

| 技术 | 选择 | 状态 |
|------|------|:----:|
| 语言 | Python 3.14 | 锁定 |
| Web 框架 | FastAPI + uvicorn | 锁定 |
| 进程管理 | `asyncio.create_subprocess_exec` | 锁定 |
| CLI 连接 | `cbc -p --output-format stream-json --input-format stream-json -y` | 锁定 |
| 多轮对话 | stdin 持续写入（长驻进程） | 锁定 |
| 用户接管 | `cbc --resume <sessionId>`（原生终端） | 锁定 |
| 实时通信 | WebSocket（FastAPI） | 锁定 |
| 前端 | 增强单 HTML（原生 JS） | 锁定 |
| 存储 | JSON 文件 → 未来 SQLite | 演进 |

---

## 六、成功标准

| # | 标准 | 状态 |
|---|------|:----:|
| 1 | Agent 向 Worker-1 和 Worker-2 各派一个任务，两个同时执行 | ✅ |
| 2 | Dashboard 实时显示两个 Worker 的流式输出 | ✅ |
| 3 | Dashboard 向 Worker-1 注入消息，Worker-1 在后续对话中响应 | ✅ |
| 4 | 人类接管 Worker-2 的 cbc 终端，退出后 Agent 恢复控制 | ✅ |
| 5 | 系统重启后，Worker 的 session 可从本地存储恢复 | 待完成 |
| 6 | 主 Agent 通过专用 WS 通道接收事件 + 派发任务 | 待完成 |
