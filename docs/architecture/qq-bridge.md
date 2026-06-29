# QQ 连接架构

> 最后更新：2026-06-29

---

## 一、整体链路

```
QQ 用户
  │
  ▼
腾讯 QQ 服务器
  │
  ▼
NapCat（协议端）                     ◀── 需要独立 QQ 小号登录
  │  OneBot v11 正向 WebSocket 服务端
  │  ws://127.0.0.1:3001
  ▼
NoneBot2（框架）                     ◀── qq-bridge/.venv
  │  Python 异步聊天机器人框架
  │  启动：python bot.py
  ├── bot.py         入口（driver.register_adapter + run）
  └── plugin.py      主插件（消息处理 + API 调用）
        │
        ▼
CLIConductor HTTP API               ◀── 本地 venv
  │  http://127.0.0.1:8767
  ├── POST /api/sessions    创建会话
  ├── POST /api/spawn       启动 Worker
  ├── POST /api/task        发任务
  └── GET  /api/sessions/{id} 轮询结果
        │
        ▼
Worker (cbc 进程) → 处理 → 结果
  │
  ▼
CLIConductor session 持久化
  │  data/sessions/ses_<uuid>.json
  │  history、lastResult
        │
        ▼
QQ Bridge 轮询 ←── GET /api/sessions/{id}
  │  检测 lastResult.timestamp 变化
  ▼
QQ 用户收到回复
```

## 二、组件详解

### 2.1 NapCat

- **角色**：QQ 协议实现，将 QQ 消息转换为 OneBot v11 标准事件
- **安装**：NapCat.Win 一键版，登录 QQ 小号
- **配置**：正向 WebSocket 服务端，主机 `127.0.0.1`，端口 `3001`
- **协议**：OneBot v11（WebSocket）

### 2.2 NoneBot2 + 插件

- **角色**：消息路由层，接收 OneBot 事件，调用 CLIConductor API
- **入口**：`qq-bridge/bot.py`（初始化 NoneBot + 注册适配器）
- **插件**：`qq-bridge/plugin.py`（消息处理和 API 调用）
- **配置**：`qq-bridge/.env`（DRIVER、WS URL、CLICONDUCTOR URL）

### 2.3 CLIConductor

- **角色**：Worker 管理中间件，为每个 QQ 用户创建独立的 Session + Worker
- **URL**：`http://127.0.0.1:8767`

---

## 三、消息处理流程

```
1. 用户发 QQ 消息
     │
2. NapCat 接收 → OneBot 事件 → WS 转发到 NoneBot2
     │
3. plugin._ensure_session(qq_user_id)
     ├── 查内存缓存 _sessions[qq_user_id]
     ├── 未命中 → GET /api/sessions 查已有 session
     │   └── 找到 → 复用，设置 last_result_ts
     ├── 未找到 → POST /api/sessions 创建（name=qq-<id>）
     └── 无 Worker → POST /api/spawn
     │
4. plugin._send_and_wait(text, qq_user_id)
     ├── POST /api/task {sessionId, text}
     ├── 启动背景轮询 _poll_result(session_id, qq_user_id)
     │   └── 每 1.5s GET /api/sessions/{id}
     │       └── 检测 lastResult.timestamp 变化 → 通知等待者
     ├── await evt.wait(timeout=120s)
     └── GET /api/sessions/{id} → 提取最新 assistant 消息
     │
5. 发送回复到 QQ
     └── await bot.send(event, response)
```

## 四、Session 映射

```
QQ user_id         →  BridgeSession
                         ├── cli_session_id  (ses_<16hex>)
                         ├── worker_id       (worker-N)
                         ├── last_result_ts  (用检测新结果的基线)
                         └── last_history_len

CLIConductor name   →  qq-<user_id后6位>
```

## 五、端口表

| 服务 | 端口 | 协议 |
|------|------|------|
| CLIConductor | 8767 | HTTP + WS |
| NoneBot2 (内置) | 8080 | HTTP（仅框架用）|
| NapCat | 3001 | WebSocket (OneBot v11) |

## 六、启动顺序

1. **NapCat**（先启动，保持后台运行）
2. **CLIConductor**：`python main.py`
3. **QQ Bridge**：`cd qq-bridge && .venv/Scripts/python bot.py`

## 七、已知限制

- 消息传递用轮询（1.5s 间隔），非 WebSocket 推流
- 只支持私聊 + 群聊 @bot
- Session 映射存内存，bot 重启后丢失（可从服务端恢复）
- 不支持多轮等待中的消息（一次只处理一条）
- 回复内容超过 1500 字符时分段发送
