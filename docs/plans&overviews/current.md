# Phase 1 — 当前开发计划

> 最后更新：2026-06-28
> 目标：Meta-Agent 操控多个 Worker + 人类随时观察/插话/接管

---

## 一、当前状态（已完成）

| 功能 | 状态 |
|------|:----:|
| 项目重构为模块化（`src/worker.py`, `src/server.py`, `src/session.py`） | ✅ |
| Worker 生命周期（spawn / list / kill / restart / branch） | ✅ |
| Session 独立管理（UUID 持久化，死 Worker 不删 Session） | ✅ |
| Worker/Session 概念分离 | ✅ |
| cbc stdin stream-json 集成（长驻进程） | ✅ |
| 消息队列（asyncio.Queue + consumer 循环，一次一条） | ✅ |
| 中断机制（`/interrupt` 端点 → kill + --resume 重启） | ✅ |
| Session 持久化（JSON 文件，每次 result 保存） | ✅ |
| Dashboard 重写（左栏 session 列表 + 聊天式消息区） | ✅ |
| Worker 独立工作目录（`data/workdirs/{name}/`） | ✅ |
| 全部 API 端点（session/spawn/list/task/kill/restart/switch-model/switch-mode/rename/branch/interrupt/takeover） | ✅ |
| WebSocket 双向通信（`/ws` + `/ws/agent` 双通道） | ✅ |
| 命令来源辨別（`source` 参数 + 独立 WS 通道） | ✅ |
| 优雅关闭（lifespan handler，kill 所有子进程） | ✅ |
| cbc --resume 重放去重（_replaying 标志） | ✅ |
| Dashboard 无 Worker 自动 spawn | ✅ |
| 状态灯即时更新（本地 modelData + 异步服务端同步） | ✅ |
| Favicon | ✅ |

---

## 二、API 总览（当前）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | Dashboard（单页 HTML） |
| GET | `/favicon.ico` | SVG favicon |
| WS | `/ws` | Dashboard WebSocket（user_inject） |
| WS | `/ws/agent` | Meta-Agent WebSocket（task/spawn/kill/list）|
| GET | `/api/models` | 支持模型列表 |
| GET | `/api/sessions` | 列出所有 Session（含 history、workerStatus）|
| POST | `/api/sessions` | 创建 Session |
| GET | `/api/sessions/{id}` | 获取单个 Session |
| DELETE | `/api/sessions/{id}` | 删除 Session + kill Worker |
| POST | `/api/spawn` | 为 Session 创建 Worker（可带 model/mode）|
| POST | `/api/task` | 发任务（workerId 或 sessionId）|
| GET | `/api/list` | 列出运行中的 Worker |
| POST | `/api/kill/{worker_id}` | 销毁 Worker（不删 Session）|
| POST | `/api/worker/{id}/restart` | 重启 cbc 进程 |
| POST | `/api/worker/{id}/switch-model` | 切换模型 |
| POST | `/api/worker/{id}/switch-mode` | 切换权限模式 |
| POST | `/api/worker/{id}/rename` | 重命名 Session |
| POST | `/api/worker/{id}/branch` | 从当前 Session 分支 |
| POST | `/api/worker/{id}/interrupt` | 中断当前任务 |
| POST | `/api/worker/{id}/takeover` | 打开交互式 PowerShell + held |

---

## 三、当前代码结构

```
CLIConductor/
├── main.py                  入口（from src.server import app）
├── src/
│   ├── __init__.py
│   ├── server.py            FastAPI 路由 + WS（~380 行）
│   ├── worker.py            Worker 数据类 + 生命周期管理（~430 行）
│   └── session.py           Session 存储（UUID key，独立持久化）
├── index.html               Dashboard 单页（两栏：session 列表 + 聊天区）
├── data/
│   ├── sessions/            Session JSON 文件（ses_<uuid>.json）
│   └── workdirs/            Worker 工作目录
├── requirements.txt         fastapi, uvicorn, websockets
├── docs/
│   ├── plans&overviews/     规划文档
│   │   ├── global.md        全局规划（目标/架构/路线图/命名约定）
│   │   ├── current.md       当前 Phase 1 计划（本文件）
│   │   └── myTODO.md        个人 TODO（不动）
│   └── references/          参考资料
│       └── dionysusc-reference.md
├── notes.md                 综合研究笔记（已归档至 global）
├── devNote.md               协作笔记
└── target.md                项目目标（已归档至 global）
```

---

## 四、TODOs（当前不处理，记录待将来决策）

| # | 事项 | 说明 |
|---|------|------|
| 1 | 中间输出实时保存 | 目前只在 result 时保存 session。将来可能需要在 stream 事件时也增量保存，防止中途崩溃丢数据 |
| 2 | 按价值选择存储策略 | 目前全量保存 history。将来可能有选择性策略：有价值 session 存完整 history，普通 session 只存元数据 |
| 3 | History 加载分页 | 目前全量加载。如果对话过长时分批加载，减少传输和渲染压力 |
| 4 | Workdir 清理机制 | 目前 kill Worker 不删 workdir。将来需要清理无效的临时工作目录 |
| 5 | 权限控制 | 目前通过 `source` 参数和独立 WS 通道辨别命令来源，未实现真正的权限限制 |
| 6 | 崩溃自动恢复 | Worker 进程崩溃后自动检测并恢复 |

---

## 五、QQ 集成（开发中）

### 架构

```
QQ 用户 → NapCat（OneBot v11 WS 协议端）
        → NoneBot2（Python 框架）
          → CLIConductor QQ Plugin
            → CLIConductor HTTP API
              → Worker → cbc
```

### 实现方式

| 组件 | 用途 |
|------|------|
| [NapCat](https://github.com/NapNeko/NapCatQQ) | QQ 协议实现，作为 OneBot v11 WebSocket 服务端 |
| [NoneBot2](https://github.com/nonebot/nonebot2) | 异步 Python 聊天机器人框架 |
| `nonebot-adapter-onebot` | NoneBot2 的 OneBot v11 适配器 |
| `qq-bridge/` | CLIConductor 自带 NoneBot2 插件 + 配置 |

### 工作流程

1. 用户在 QQ 中向 bot 发消息
2. NapCat 接收 → 通过 WS 转发给 NoneBot2
3. 插件收到消息 → 查 QQ→Session 映射
4. 无映射 → `POST /api/sessions` 创建 Session → `POST /api/spawn` 启动 Worker
5. `POST /api/task {sessionId, text}` → 任务入队
6. 轮询 `GET /api/sessions/{id}` → 检测 last_result 更新
7. 结果通过 QQ 消息返回给用户

### 文件结构

```
CLIConductor/
├── qq-bridge/
│   ├── bot.py                  # NoneBot2 入口 + 主插件
│   ├── .env                    # NoneBot2 配置
│   └── requirements.txt        # 依赖
```

### TODO

- [ ] NapCat 安装与配置文档
- [ ] NoneBot2 插件基础框架（消息接收 + API 调用）
- [ ] Session 映射管理（QQ 用户 ↔ CLIConductor Session）
- [ ] 任务结果轮询与回传
- [ ] 并发消息处理（多用户同时使用）

