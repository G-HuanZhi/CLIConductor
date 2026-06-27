# 技术栈最终对比：Python+FastAPI vs Node.js+Express

> 基于两端 spike 实战、架构推演、未来扩展场景的综合分析。  
> 阅读本文前建议先看 `tech-stack-analysis.md`（基础评分）和 `spike-comparison-plan.md`（试验记录）。

---

## 一、已完成的对照试验

### 试验 5：添加 restart 端点

同时在 Python 和 Node.js 两端实现 `POST /api/worker/:id/restart`：

- kill 旧进程 → spawn 新进程 → 重新挂载 stdout reader → 广播事件

**收获**：

| | Python (asyncio) | Node.js (EventEmitter) |
|---|---|---|
| stdout reader 复用 | `_read_stdout` 从第一天就是独立函数，零重构 | 原本内联在 `createWorker`，需抽成 `setupWorkerIO`（+45 行） |
| 清理机制 | `task.cancel()` 显式干净 | 旧 `close` 事件回调异步触发，覆盖新进程状态 |
| 产生的 bug | 0 | 1（陈旧 close handler）— 需加 `w.process !== child` guard |

**核心发现**：Python 的 async/await 鼓励结构化生命周期管理 — 创建、取消、退出每一步显式可见。Node.js 的事件驱动更简洁，但在进程替换边界会产生潜藏 bug，需要防御式编程。

---

## 二、后续开发差异面（按层级）

### 2.1 API 层 — 网关与路由

| | Python + FastAPI | Node.js + Express |
|---|---|---|
| 请求校验 | Pydantic 一行搞定，运行时自动 422 | 需额外 zod / express-validator |
| API 文档 | **自动** `/docs` Swagger，零成本 | swagger-jsdoc 手动注解 |
| 中间件链 | `Depends()` 依赖注入，洋葱模型 | Express middleware 手动编排 |
| WebSocket 路由 | FastAPI 原生 `WebSocket` endpoint | ws 库手动 path 分发 |
| gRPC | grpcio（成熟） | gRPC-js（可用，社区弱） |

**结论**：越多接口、越多中间件、越多协议，FastAPI 的**结构性优势**越突出。

### 2.2 实时流 — WebSocket 反压

| 场景 | Python | Node.js |
|---|---|---|
| 单个 client 慢 | `await ws.send_json()` 让出事件循环 | `ws.send()` 同步，可能阻塞事件循环 |
| 多 Worker 竞速 | asyncio 自动交错 | 需要手动 check `bufferedAmount` |

**结论**：2-5 个 Worker 差距不大。Python asyncio 在这个场景更安全。

### 2.3 多 Worker 并发

| | Python | Node.js |
|---|---|---|
| 并发模型 | `create_task` + asyncio（Windows: `SelectorEventLoop`） | event loop + stream pipe（内部缓冲成熟） |
| 2-5 Worker | 无压力 | 无压力 |
| 10+ Worker | 可能有 pipe 缓冲问题 | 更成熟 |

**结论**：CLIConductor 目标 2-5 Worker，两边都够用。

### 2.4 PTY 终端接管

| | Python | Node.js |
|---|---|---|
| Windows PTY | winpty 绑定弱，需绕路 | **node-pty** — 成熟、ConPTY 原生 |
| 接管实现 | 可能需要调 node-pty 子进程做代理 | 直接 `pty.spawn()` |

**结论**：这是 **Node.js 最大的生态优势**。Python 能做但多一层胶水。

### 2.5 持久化与存储

| | Python | Node.js |
|---|---|---|
| SQLite async | aiosqlite（成熟） | better-sqlite3（同步，极快） |
| JSON 文件 | aiofiles | fs/promises |
| Schema 迁移 | Alembic（重型） | drizzle（轻量） |

**结论**：差异不大，一个小库覆盖需求。

### 2.6 测试

| | Python | Node.js |
|---|---|---|
| 异步测试 | pytest + pytest-asyncio | vitest + supertest |
| WebSocket 测试 | `websockets.connect()` 直接测 | ws mock 需自搭 |
| 开发体验 | fixture 强大但学习成本高 | vitest watch mode 即时反馈 |

**结论**：vitest 日常更快，pytest fixture 适合复杂场景。

### 2.7 异步调试

| | Python | Node.js |
|---|---|---|
| 调试工具 | pdb / VSCode 集成 | `--inspect` + Chrome DevTools |
| Stack trace | asyncio trace 折叠严重，难读 | async stack trace (Node 16+) 改善明显 |

**结论**：多 Worker 并发调试 node.js **体验好得多**。

### 2.8 类型系统

| | Python | Node.js |
|---|---|---|
| 接口定义 | dataclass + 可选 mypy | TypeScript 编译时强制 |
| 重构安全 | 改名字不一定全量报错 | 编译不过，漏不了 |
| Worker 状态 | `str` 枚举不精确 | `"idle" \| "running" \| "done" \| "error"` |

**结论**：Interface 越复杂，TS 的类型安全**价值越大**。

### 2.9 打包分发

| | Python | Node.js |
|---|---|---|
| 单 exe | PyInstaller（含 Python 运行时） | pkg / nexe（含 Node 运行时） |
| 实际情况 | cbc 已是 Node 进程，打包 Python exe 内嵌 Node 略显奇怪 | 全栈 Node，工具链单一 |

**结论**：没有决定性的赢家。

---

## 三、关键分歧点

### 3.1 Live2D / 复杂前端

如果 Dashboard 升级为 SPA + WebGL（Live2D 角色动画）：

| | Python 后端 | Node.js 后端 |
|---|---|---|
| 类型共享 | `openapi-typescript` 生成 TS 类型（构建步骤） | **直接 import** 同仓库 type |
| 事件协议演进 | 改 Pydantic → 重新生成 → 前端漏了不报错 | 改 TS type → 前后端同时编译报错 |
| Monorepo | 跨语言工具链混合 | pnpm workspace 天然一体 |

**前端越复杂，前后端同语言的"类型共享红利"越大。**

### 3.2 cbc 生态一致性

- **Python**：系统同时跑 Python 进程（服务器）+ Node 进程（cbc Workers），两套运行时、两套调试工具、两套错误格式
- **Node.js**：全链路 Node.js → 一个调试器看所有进程、错误格式统一

这不是致命问题，但运维时会多一层心智负担。

---

## 四、按 Phase 推演

### Phase 1 MVP（当前）

- 2 Worker，完整 observe/inject/restart 链路
- 简单 Dashboard HTML

→ **两边都能胜任**。Python 在子进程管理上更干净（已证），Node.js 开发更快。

### Phase 2 扩展

- Dashboard 升级为富交互（可能含 Live2D）
- 多 CLI 适配器（F6）
- Worker 崩溃自动恢复（F8）
- 会话持久化（F2）

→ **分水岭**。如果上 Live2D，Node.js 的前后端同构优势开始显现。如果不做 Live2D，差距不大。

### Phase 3 规模化

- 消息网关（HTTP + WS + QQ/微信统一入口）
- 全局记忆系统（F9）
- 可能的多协议网关
- 长期稳定运行

→ **两极化**。网关层 Python 更优，前端层 Node.js 更优。谁更重要取决于你的重心。

---

## 五、综合画像

| 维度 | Python 优势 | Node.js 优势 | 对你的重要度 |
|---|---|---|---|
| API 开发速度 | FastAPI 自动校验+文档 | — | 中（接口不多） |
| 接口演化安全 | — | 编译时类型检查 | 中高 |
| 实时流反压 | asyncio 天然非阻塞 | — | 中 |
| PTY 终端接管 | — | node-pty 生态 | **高**（Phase 1 需求） |
| 子进程管理 | cancel 干净（已验证） | 事件模型需防守 | 中高 |
| 异步调试 | — | Chrome DevTools | 中 |
| 类型建模 | — | Discriminated union | 中 |
| 前后端同构 | — | 零成本类型共享 | **高**（若有 Live2D） |
| 生态一致性 | — | 全栈 Node（cbc 同语言）| 中 |
| 网关/中间件 | Depends 洋葱模型 | — | 低（Phase 3 远） |

---

## 六、决策框架

最终选择取决于你对以下三个问题的权重分配：

1. **PTY 接管**有多重要？（node-pty → Node.js）
2. **Live2D / 复杂前端**有多确定？（同构类型 → Node.js）
3. **API 网关复杂度和长期维护**？（FastAPI → Python）

如果前两项权重高 → **Node.js**  
如果第三项权重高 → **Python**  
如果三项差不多 → **Node.js**（因为后端 Node.js 也能写，但前端 Python 写不了）
