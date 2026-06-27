# Phase 1 — 最小完整功能计划

> 目标：主 Agent 操控 2 个 Worker + 你随时观察/插话/接管

---

## 一、MVP 目标

```
主 Agent 说："Worker-1 做任务 A，Worker-2 做任务 B"
  → Worker-1 启动 cbc → 实时流式输出 → 结果返回
  → Worker-2 启动 cbc → 实时流式输出 → 结果返回
  → 你在 Dashboard 看到一切

你觉得 Worker-1 方向不对
  → 在 Dashboard 打一行字："换个方案"
  → Worker-1 收到，调整方向继续

你需要完全接管 Worker-2
  → 打开交互终端 → 直接操控 cbc → 完成 → 退出接管
```

---

## 二、范围边界

### 做什么

| 功能 | 具体行为 |
|------|---------|
| Worker 管理 | spawn / list / kill（命令行 + Dashboard） |
| Agent 派发任务 | Agent 通过 API 向 Worker 发任务（文本），Worker 内部转成 cbc stdin 消息 |
| 实时观察 | Dashboard 显示 Worker 的对话历史、当前状态、实时输出 |
| 插话 | Dashboard 输入框 → 消息注入到 Worker 的 stdin 队列 |
| 接管 | 通过 PTY 打开交互终端，连接 Worker 的 cbc session |
| Session 存储 | 保存 session_id 和对话历史到本地文件 |

### 不做什么

| 不做 | 理由 |
|------|------|
| 自动任务拆分 | 主 Agent 自己决定谁做什么，项目只提供通道 |
| 多 CLI 适配器 | 只做 CodeBuddy Code |
| 信息网关（QQ/微信） | Phase 2 |
| 全局记忆 | Phase 2 |
| 登录/多用户 | 本地单用户 |
| 异常恢复/重试 | 手动 kill + spawn 即可 |

---

## 三、架构

```
┌─────────────────────────────────────────────────────────┐
│                    CLIConductor Server                    │
│                                                          │
│  ┌──────────────┐     ┌───────────────────────┐         │
│  │  HTTP API    │     │  WebSocket Server      │         │
│  │  /spawn      │     │  /ws (Dashboard)       │         │
│  │  /list       │     │  /ws/agent (主Agent)   │         │
│  │  /kill       │     └───────────┬───────────┘         │
│  └──────┬───────┘                 │                      │
│         │                         │                      │
│  ┌──────▼─────────────────────────▼──────────────────┐  │
│  │              Session Manager                       │  │
│  │  ┌──────────────────────────────────────────────┐ │  │
│  │  │  registry: Map<string, WorkerState>           │ │  │
│  │  │  eventBus: EventEmitter                       │ │  │
│  │  │  broadcast(): 事件推给所有 WS 客户端          │ │  │
│  │  └──────────────────────────────────────────────┘ │  │
│  │                                                    │  │
│  │  ┌─────────────────┐    ┌─────────────────────┐   │  │
│  │  │  Worker-1        │    │  Worker-2            │   │  │
│  │  │  ┌─────────────┐ │    │  ┌─────────────────┐ │   │  │
│  │  │  │messageQueue │ │    │  │  messageQueue   │ │   │  │
│  │  │  │(Agent+用户) │ │    │  │  (Agent+用户)   │ │   │  │
│  │  │  └──────┬──────┘ │    │  └──────┬──────────┘ │   │  │
│  │  │  ┌──────▼──────┐ │    │  ┌──────▼──────────┐ │   │  │
│  │  │  │ cbcAdapter  │ │    │  │  cbcAdapter     │ │   │  │
│  │  │  │ (Strategy)  │ │    │  │  (Strategy)     │ │   │  │
│  │  │  └──────┬──────┘ │    │  └──────┬──────────┘ │   │  │
│  │  │  ┌──────▼──────┐ │    │  ┌──────▼──────────┐ │   │  │
│  │  │  │ cbc 进程    │ │    │  │  cbc 进程        │ │   │  │
│  │  │  │ (长驻)      │ │    │  │  (长驻)          │ │   │  │
│  │  │  └─────────────┘ │    │  └─────────────────┘ │   │  │
│  │  └─────────────────┘    └─────────────────────┘   │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Dashboard HTTP                                   │  │
│  │  GET / → 静态 HTML (xterm.js + 对话面板)         │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 四、关键组件设计

### 4.1 Worker

```
Worker:
  id: string
  name: string
  workdir: string
  status: "idle" | "running" | "error" | "dead"

  cbcProcess: ChildProcess (长驻，stdin stream-json 模式)
  messageQueue: Message[] (Agent 任务 + 用户注入)
  sessionId: string (cbc 的 session_id)
  history: Message[] (对话历史)
  outputStream: Readline (逐行读取 cbc stdout)

  send(text): 往 messageQueue 推一条消息
  destroy(): kill 进程 + 清理
```

### 4.2 CBC Adapter (Strategy)

借鉴 DionysusC 的 `CodeBuddyStrategy`：

```
CbcAdapter:
  spawn(name, workdir):
    → spawn('cbc', ['-p', '--output-format', 'stream-json', '--input-format', 'stream-json', '-y'], options)
    → 返回 Worker 对象

  processOutput(line):
    → JSON.parse(line)
    → 识别 type: system.init (提取 session_id)
    → 识别 type: assistant (thinking/text/tool_use/tool_result)
    → 识别 type: result (任务完成/错误)
    → 标准化为统一事件

  buildMessage(text):
    → {"type":"user","message":{"role":"user","content":[{"type":"text","text":text}]}}
```

### 4.3 事件协议

统一事件类型（Worker → Dashboard / Agent）：

| 事件 | 触发时机 | payload |
|------|---------|---------|
| `worker.spawned` | Worker 创建 | `{ workerId, name, workdir }` |
| `worker.status` | 状态变化 | `{ workerId, status }` |
| `worker.stream` | cbc 输出一行 | `{ workerId, text/thinking/tool }` |
| `worker.result` | 任务结束 | `{ workerId, status, result }` |
| `worker.destroyed` | Worker 销毁 | `{ workerId }` |

Dashboard → Worker 的控制消息：

| 消息 | 作用 |
|------|------|
| `user_inject` | 用户插话，写入 Worker 的 messageQueue |
| `worker_takeover` | 请求接管 Worker |
| `worker_spawn` | 创建 Worker |
| `worker_kill` | 销毁 Worker |

### 4.4 Session 存储

```
data/
  sessions/
    worker-1.json  → { sessionId, createdAt, history: Message[] }
    worker-2.json  → { sessionId, createdAt, history: Message[] }
```

每个文件存储一个 Worker 的 session ID 和完整对话历史。

---

## 五、消息流

### Agent 派发任务

```
Agent → POST /api/task { workerId: "worker-1", text: "重构 auth 模块" }
  → SessionManager 找到 Worker
  → Worker.messageQueue.push(msg)
  → Worker 当前空闲 → 立即从队列取消息
  → CbcAdapter.buildMessage(text)
  → cbcProcess.stdin.write(jsonMsg + '\n')
  → 逐行读取 cbcProcess.stdout
  → 每行通过 eventBus 推给 WebSocket
  → Agent 和 Dashboard 同时收到实时流
  → result 事件 → 任务完成
  → Worker 从队列取下一条
```

### 用户插话

```
Dashboard 输入框
  → WS 发送 { type: "user_inject", workerId: "worker-1", text: "换个方案" }
  → Worker.messageQueue.push(msg)（排到 Agent 消息后面）
  → 等当前任务完成 → 取下一条（用户的消息）
  → Agent 收到通知："用户对 worker-1 说：换个方案"
  → Agent 决定下一步
```

### 用户接管

```
Dashboard "接管" 按钮
  → WS 发送 { type: "worker_takeover", workerId: "worker-2" }
  → SessionManager 标记 Worker 为 "接管中"
  → Agent 暂不向该 Worker 发新任务
  → 启动 PTY: spawn('cbc', ['--resume', sessionId])  ← 等交互模式
  → 用户通过 xterm.js 直接操控
  → "退出接管" → kill PTY → Worker 恢复 normal
  → Agent 可继续派发任务
```

---

## 六、CLI 入口命令（最小）

```bash
# 启动服务
npx tsx src/index.ts

# 通过 API 操作
curl -X POST http://localhost:8765/api/spawn -d '{"name":"worker-1"}'
curl http://localhost:8765/api/list
curl -X POST http://localhost:8765/api/task -d '{"workerId":"worker-1","text":"重构 auth 模块"}'
curl -X POST http://localhost:8765/api/kill/worker-1
```

---

## 七、Dashboard 页面（最小）

```
┌─────────────────────────────────────────────────────────┐
│  CLIConductor                                            │
│  ┌─────────────────────────┐ ┌─────────────────────────┐│
│  │  Worker-1  [idle ●]     │ │  Worker-2  [running ◉]  ││
│  │                         │ │                         ││
│  │  对话记录                │ │  对话记录                ││
│  │  ┌──────────────────┐  │ │  ┌──────────────────┐   ││
│  │  │ user: 重构auth   │  │ │  │ user: 写测试      │   ││
│  │  │ assistant: ...   │  │ │  │ thinking: ...    │   ││
│  │  │ tool_use: read   │  │ │  │ text: ...        │   ││
│  │  └──────────────────┘  │ │  └──────────────────┘   ││
│  │                         │ │                         ││
│  │  [输入框] [发送]        │ │  [输入框] [发送]        ││
│  │  [接管]                 │ │  [接管]                 ││
│  └─────────────────────────┘ └─────────────────────────┘│
│                                                          │
│  [+ New Worker]                                          │
└─────────────────────────────────────────────────────────┘
```

---

## 八、技术实现（从 DionysusC 借鉴）

| 借鉴点 | 用在哪 |
|--------|--------|
| Strategy 模式 (GenericCLIAdapter + Strategy) | CbcAdapter |
| stream-json 逐行解析 | Worker 的输出读取 |
| session_id 提取 (system.init) | Worker 启动时自动捕获 |
| 事件管道 + 多路消费 | EventBus → Dashboard + Agent |
| AgentEvent 类型定义 | 统一事件协议 |

与本实验验证的差异：
| DionysusC | CLIConductor MVP |
|-----------|-----------------|
| 单次 spawn + --resume | 长驻 spawn + stdin 持续写 |
| 单 Worker | 多 Worker |
| 无介入 | 观察 + 插话 + 接管 |

---

## 九、开发顺序（推荐）

```
Milestone 1: 能跑一个 Worker
  ├── src/server.ts            HTTP + WS 服务
  ├── src/worker.ts            Worker 类 + spawn cbc
  ├── src/adapter.ts           CbcAdapter (stream-json 解析)
  └── src/index.ts             启动入口
  验证: curl POST /api/spawn → Worker 启动 → stdout 有 stream-json

Milestone 2: Agent 能发任务拿结果
  ├── 完善 Worker.send()
  └── 完善事件总线
  验证: curl POST /api/task → Worker 执行 → 返回 result

Milestone 3: Dashboard 实时观察
  ├── public/index.html        Dashboard 页面
  └── WS 事件推送
  验证: 打开浏览器 → 看到 Worker 实时输出

Milestone 4: 用户插话
  ├── 消息队列 (messageQueue)
  └── Dashboard 输入框 + user_inject 消息
  验证: Dashboard 输入消息 → Worker 显示在对话中

Milestone 5: 用户接管
  ├── PTY 接管功能 (node-pty)
  └── Dashboard 接管按钮
  验证: 点接管 → xterm.js 窗口 → 能操控 cbc

Milestone 6: 第二个 Worker
  验证: spawn worker-2 → 两个 Worker 并行跑
```

---

## 十、成功标准

| # | 标准 |
|---|------|
| 1 | 主 Agent 向 worker-1 发"写一个 hello world 函数"，Worker 执行并返回结果 |
| 2 | 同时向 worker-2 发另一个任务，两个 Worker 不冲突 |
| 3 | Dashboard 实时显示两个 Worker 的对话 |
| 4 | 在 Dashboard 输入"改成 async 版本"，Worker-1 收到并响应 |
| 5 | 点接管 → xterm.js 打开 → 能直接和 cbc 对话 |
| 6 | 退出接管 → Agent 继续控制 |
