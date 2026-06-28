# CLIConductor

> 中间层，让主 Agent 调度管理多个 cbc 进程，同时人类可随时观察、插话、接管任意进程。

**技术栈**：Python 3.14 + FastAPI + WebSocket

---

## 当前进度

| Phase | 目标 | 状态 |
|:-----|------|:----:|
| Phase 1 | Agent 操控 2 个 Worker + 人类观察/插话/接管 | 进行中 |

### 已实现功能

| 功能 | 说明 |
|------|------|
| Worker 生命周期 | spawn / list / kill / restart / branch |
| cbc 集成 | stdin stream-json 长驻进程，多轮对话 |
| 任务队列 | 每个 Worker 独立 asyncio.Queue，一次一条写入 stdin |
| 模型切换 | switch-model / switch-mode，kill + --resume 保留历史 |
| Session 持久化 | 每次 result 自动保存 JSON 到 `data/sessions/` |
| 重启恢复 | 服务器启动时自动 `--resume` 恢复所有 Worker |
| 中断任务 | interrupt 端点：kill + --resume 重启 |
| Dashboard | 实时事件流、对话日志、状态灯、per-worker 控制面板 |
| 用户注入 | Dashboard 输入 → WS → Worker 队列 |
| 接管模式 | 后端打开 PowerShell 运行交互式 `cbc --resume`，Worker 进入 held 态 |
| 优雅关闭 | lifespan handler：退出时 kill 所有子进程 |
| 默认模型 | `deepseek-v4-flash`，spawn 时可指定 model / mode / workdir |
| 主 Agent 通道 | `/ws/agent` 端点，Agent 实时接收事件 + 派发任务 |
| `lastResult` | 每次任务完成保存 {status, result, timestamp}，API 可查 |

### API 总览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | Dashboard（单页 HTML） |
| WS | `/ws` | Dashboard WebSocket（观察 + user_inject） |
| WS | `/ws/agent` | 主 Agent WebSocket（事件流 + task/spawn/kill/list）|
| GET | `/api/models` | 获取支持模型列表 + 默认模型 |
| GET | `/api/list` | 列出所有 Worker（含 lastResult） |
| POST | `/api/spawn` | 创建 Worker `{name, model?, permissionMode?, workdir?}` |
| POST | `/api/task` | 发任务 `{workerId, text}` |
| POST | `/api/kill/{id}` | 销毁 Worker |
| POST | `/api/worker/{id}/restart` | 重启 cbc 进程 |
| POST | `/api/worker/{id}/interrupt` | 中断当前任务 |
| POST | `/api/worker/{id}/takeover` | 打开交互式 PowerShell + held |
| POST | `/api/worker/{id}/switch-model` | 切换模型 `{model}` |
| POST | `/api/worker/{id}/switch-mode` | 切换权限模式 `{permissionMode}` |
| POST | `/api/worker/{id}/rename` | 重命名 `{name}` |
| POST | `/api/worker/{id}/branch` | 从当前 session 分支出新 Worker |

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
        主 Agent                   你（人类）
    (CodeBuddy 等)              (Dashboard / CLI)
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
├── main.py                  入口（from src.server import app）
├── src/
│   ├── __init__.py
│   ├── server.py            FastAPI 路由 + WS
│   ├── worker.py            Worker 类 + 生命周期管理
│   └── session.py           Session JSON 持久化
├── index.html               Dashboard 单页
├── target.md                项目目标定义
├── notes.md                 研究笔记
├── requirements.txt         fastapi, uvicorn, websockets
├── docs/
│   ├── global_plan.md       全局规划 + 路线图
│   ├── first_plan.md        Phase 1 详细计划
│   ├── known-issues.md      已知限制
│   └── ...                  技术分析文档
└── experiments/             实验脚本
```

## 关键设计

### cbc 集成模式

每个 Worker 对应一个长驻 cbc 进程：

```
cbc -p --output-format stream-json --input-format stream-json -y
```

- stdin：持续写入 JSON 格式的 user 消息
- stdout：逐行解析 stream-json 事件（thinking / text / tool_use / result）
- `-y`：跳过所有权限确认（包括信任目录提示）
- 进程不退出，result 事件后继续等待下一条 stdin

### 消息队列

```
Agent 任务 ──→ asyncio.Queue (FIFO) ──→ consumer ──→ cbc.stdin.write()
用户注入 ──→                                         result → 取下一条
```

- 一次一条，等 result 后才取下一条
- 用户注入（source="user"）和 Agent 任务走同一队列
- takeover 后状态变 held，拒绝所有输入，直到 restart

### 特殊命令处理

cbc 的 /model、/branch、Shift+Tab 等无法通过 stream-json stdin 发送。解决：kill + `--resume <session_id>` + CLI 参数重启。

| 命令 | 实现方式 |
|------|---------|
| `/model` | `--model <model>` + respawn |
| Shift+Tab | `--permission-mode <mode>` + respawn |
| `/branch` | `--resume <sid> --fork-session` + spawn |
| `/rename` | CLIConductor 自维护 name 字段 |
