# CLIConductor

> 中间层，让 Meta-Agent 调度管理多个 cbc 进程，同时人类可随时观察、插话、接管任意进程。

**技术栈**：Python 3.14 + FastAPI + WebSocket

---

## 当前进度

| Phase | 目标 | 状态 |
|:-----|------|:----:|
| Phase 1 | Meta-Agent 操控多个 Worker + 人类观察/插话/接管 | 进行中 |

### 已实现功能

| 功能 | 说明 |
|------|------|
| Worker 生命周期 | spawn / list / kill / restart / branch / interrupt |
| Session 独立管理 | Session（UUID 持久化）与 Worker（运行时进程）分离，kill 不删 Session |
| 设置面板 | 一次性提交 model/mode/think/effort，自动 spawn |
| 对话历史持久化 | 磁盘 `s.history` 为 ground truth，replay 期间不重建不覆盖，cbc --resume 仅恢复内部状态 |
| cbc 集成 | stdin stream-json 长驻进程，多轮对话 |
| 任务队列 | 每个 Worker 独立 asyncio.Queue，一次一条写入 stdin |
| Session 持久化 | `data/sessions/ses_<uuid>.json`，每次 result 保存 |
| 重启恢复 Session | 启动时自动加载所有 Session（不自动 spawn Worker，按需 spawn）|
| Dashboard | 左栏 Session 列表 + 聊天式消息区（用户右、助手左、thinking 可折叠）|
| 用户注入 | Dashboard 输入 → WS → Worker 队列 |
| 接管模式 | 后端打开 PowerShell 运行交互式 `cbc --resume` |
| 优雅关闭 + 进程树清理 | 退出时 `taskkill /F /T` 杀整棵进程树，不残留孤儿 node.exe |
| 请求日志 | `[HH:MM:SS] METHOD /path → 200`，环境变量 `CLICONDUCTOR_LOG_SKIP` 可过滤特定路径 |
| Meta-Agent 通道 | `/ws/agent` 端点，Agent 实时接收事件 + 派发任务 |
| 命令来源辨别 | `send_task()` 含 `source` 参数（agent/user），两套独立 WS 通道 |

### API 总览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | Dashboard HTML |
| GET | `/favicon.ico` | SVG favicon |
| WS | `/ws` | Dashboard WebSocket（观察 + user_inject） |
| WS | `/ws/agent` | Meta-Agent WebSocket（事件流 + 命令）|
| GET | `/api/models` | 支持模型列表 + 默认模型 |
| GET | `/api/sessions` | 列出所有 Session（含 history、workerStatus）|
| POST | `/api/sessions` | 创建 Session |
| GET | `/api/sessions/{id}` | 获取单个 Session 详情 |
| PATCH | `/api/sessions/{id}` | 更新 Session 设置（无 worker 时） |
| DELETE | `/api/sessions/{id}` | 删除 Session + kill Worker |
| POST | `/api/spawn` | 为 Session 创建 Worker（可指定 setting）|
| POST | `/api/task` | 发任务（workerId 或 sessionId）|
| GET | `/api/list` | 列出运行中的 Worker |
| POST | `/api/kill/{worker_id}` | 销毁 Worker（不删 Session）|
| POST | `/api/worker/{id}/settings` | 一次性提交 model/mode/think/effort |
| POST | `/api/worker/{id}/restart` | 重启 cbc 进程 |
| POST | `/api/worker/{id}/interrupt` | 中断当前任务 |
| POST | `/api/worker/{id}/takeover` | 打开交互式 PowerShell |
| POST | `/api/worker/{id}/switch-model` | （已弃用）由 settings 替代 |
| POST | `/api/worker/{id}/switch-mode` | （已弃用）由 settings 替代 |
| POST | `/api/worker/{id}/switch-thinking` | （已弃用）由 settings 替代 |
| POST | `/api/worker/{id}/rename` | 重命名 Session |
| POST | `/api/worker/{id}/branch` | 从当前 Session 分支 |

---

## 快速开始

```bash
# 1. 虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动
python main.py
# → http://localhost:8767
```

## 架构

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

## 目录结构

```
CLIConductor/
├── main.py                  入口
├── src/
│   ├── __init__.py
│   ├── server.py            FastAPI 路由 + WS + 日志中间件
│   ├── worker.py            Worker 管理 + 历史持久化 + 进程树清理
│   └── session.py           Session 存储（UUID key）
├── index.html               Dashboard（单页）
├── static/                  CSS + JS（从 ts/ 编译）
│   ├── css/styles.css
│   └── js/app.js
├── data/
│   ├── sessions/            Session JSON 文件
│   └── workdirs/            Worker 工作目录
├── requirements.txt
├── docs/
│   ├── plans&overviews/
│   │   ├── global.md
│   │   ├── current.md
│   │   └── myTODO.md
│   └── references/
│       ├── dionysusc-reference.md
│       └── cbc-thinking-mode.md
└── TODO.md
```

## 日志控制

```
# 请求日志示例
[17:30:05] POST  /api/worker/worker-1/settings  → 200

# 跳过特定路径（环境变量）
CLICONDUCTOR_LOG_SKIP=/api/sessions,/ws  python main.py
```

## 关键设计

### Worker 与 Session 分离

- **Worker** — 运行时 cbc 进程，持有 session_id 引用。kill 后 Worker 消失。
- **Session** — 持久化数据（UUID `ses_<16hex>`），独立的 Worker 生命周期。

### cbc 集成模式（长驻进程）

```bash
cbc -p --output-format stream-json --input-format stream-json -y
```

### 消息队列（stdin 互斥）

```
Agent 任务 ──→ asyncio.Queue (FIFO) ──→ consumer ──→ cbc.stdin.write()
用户注入 ──→                                         result → 取下一条
```

### 设置面板

```
打开面板 → 同步服务器状态
修改 model/mode/think/effort → 状态差异时出现 Apply 按钮
Send / Restart → 自动合并未提交的设置
```

### 命名约定

| 术语 | 定义 |
|------|------|
| **Meta-Agent** | 具有与 Worker 交互权限的上层 AI Agent（如 CodeBuddy）。通过 `/ws/agent` 通道操作。 |
| **Worker** | 一个运行中的 cbc 子进程。进程终止后不删除 Session。 |
| **Session** | 持久话会话。UUID 管理，含 cbc_session_id、history、last_result 等。 |
| **Human** | 人类用户。通过 Dashboard 观察/注入/接管。来源标记为 `"user"`。 |
