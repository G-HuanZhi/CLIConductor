# Phase 1 — 最小完整功能开发计划

> 最后更新：2026-06-28
> 目标：主 Agent 操控 2 个 Worker + 人类随时观察/插话/接管

---

## 一、当前状态（已完成）

| 功能 | 状态 |
|------|:----:|
| 项目重构为模块化（`src/worker.py`, `src/server.py`, `src/session.py`） | ✅ |
| Worker 生命周期（spawn / list / kill / restart / branch） | ✅ |
| cbc stdin stream-json 集成 | ✅ |
| 消息队列（asyncio.Queue + consumer 循环，一次一条） | ✅ |
| 中断机制（`/interrupt` 端点 → kill + --resume 重启） | ✅ |
| Session 持久化（JSON 文件，每次 result 保存） | ✅ |
| Dashboard 增强（状态面板、对话日志、注入、控制按钮） | ✅ |
| Worker 独立工作目录（`data/workdirs/{name}/`） | ✅ |
| 10 个 API 端点（spawn / list / task / kill / restart / switch-model / switch-mode / rename / branch / interrupt） | ✅ |
| WebSocket 双向通信（支持 `user_inject` 消息） | ✅ |

**验证结果**：
- spawn → worker 启动 → 捕获 sessionId → 发 task → 执行 → 返回 result → 保存 session ✅
- 双 Worker 并行 ✅
- 消息队列有顺序执行 ✅
- interrupt 端点正确检测运行状态 ✅
- branch 从已有 session 派生新 Worker ✅

---

## 二、待完成

### Milestone A — Agent-主通道 & 主 Worker 恢复

| 任务 | 描述 | 优先级 |
|------|------|:------:|
| A1 | 主 Agent 专用 WS 端点（`/ws/agent`），Agent 可订阅所有事件并派发任务 | 高 |
| A2 | **重启时恢复 Worker**：启动时从 `data/sessions/` 读取保存的 worker 记录，自动重建 cbc 进程（`--resume <sid>`） | 高 |
| A3 | 优雅关闭信号处理（SIGINT/SIGTERM → kill 所有子进程） | 中 |
| A4 | 按 name 过滤 spawn（目前不存在同名 worker 时不会报错，只是创建同名目录） | 低 |

### Milestone B — Dashboard 完善

| 任务 | 描述 | 优先级 |
|------|------|:------:|
| B1 | 接管模式：显示 session ID + 复制 `cbc --resume <sid>` 命令（已做） | ✅ |
| B2 | 切换模型时在 Dashboard 显示状态变化 | 低 |
| B3 | 多 Worker 对比视图优化 | 低 |

### Milestone C — 可靠性与健壮性

| 任务 | 描述 | 优先级 |
|------|------|:------:|
| C1 | Worker 进程崩溃自动检测（`_read_stdout` 在 EOF 时触发） | 中 |
| C2 | Worker 进程崩溃自动恢复（用保存的 session 重启） | 中 |
| C3 | 防止多余的 WS 连接积累（已有 `dead` set 清理） | ✅ |
| C4 | API 错误响应规范化（统一返回 `{"error": "..."}`） | ✅ |

---

## 三、下一步开发建议

**立即启动** → **A1 + A2 + A3**（核心链路闭环）

```
首先：
  A2: 重启恢复 Worker → 系统重启后 Worker 自动恢复

同时：
  A1: Agent WS 端点 → 主 Agent 通过 WS 实时接收事件 + 派发任务
  
然后：
  A3: 优雅关闭 → Ctrl+C 不残留子进程
```

## 四、API 总览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | Dashboard（静态 HTML） |
| WS | `/ws` | Dashboard WebSocket |
| POST | `/api/spawn` | 创建 Worker |
| GET | `/api/list` | 列出所有 Worker |
| POST | `/api/task` | 向 Worker 发任务 |
| POST | `/api/kill/{worker_id}` | 销毁 Worker |
| POST | `/api/worker/{worker_id}/restart` | 重启 cbc 进程 |
| POST | `/api/worker/{worker_id}/interrupt` | 中断当前任务 |
| POST | `/api/worker/{worker_id}/switch-model` | 切换模型 |
| POST | `/api/worker/{worker_id}/switch-mode` | 切换权限模式 |
| POST | `/api/worker/{worker_id}/rename` | 重命名 |
| POST | `/api/worker/{worker_id}/branch` | 从当前会话分支 |

## 五、当前代码结构

```
CLIConductor/
├── main.py                 入口（from src.server import app）
├── src/
│   ├── __init__.py
│   ├── server.py           FastAPI 路由 + WS
│   ├── worker.py           Worker 类 + 生命周期管理
│   └── session.py          Session 持久化
├── index.html              Dashboard 单页
├── data/
│   ├── sessions/           Session JSON 文件
│   └── workdirs/           Worker 工作目录
├── requirements.txt        fastapi, uvicorn, websockets
├── target.md              项目目标
├── notes.md               研究笔记
└── docs/                  文档
```
