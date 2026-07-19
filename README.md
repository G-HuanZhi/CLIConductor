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
| Worker 生命周期 | spawn / list / kill / restart / branch |
| Session 独立管理 | Session（UUID 持久化）与 Worker（运行时进程）分离，kill 不删 Session |
| cbc 集成 | stdin stream-json 长驻进程，多轮对话 |
| 任务队列 | 每个 Worker 独立 asyncio.Queue，一次一条写入 stdin |
| 配置切换 | `/settings` 统一接口切换模型/权限模式/思考模式/effort，kill + --resume 保留历史 |
| Session 持久化 | `data/sessions/ses_<uuid>.json`，每次 result 保存 |
| 重启恢复 Session | 启动时自动加载所有 Session（不自动 spawn Worker，按需 spawn）|
| 中断任务 | interrupt 端点：kill + --resume 重启 |
| Dashboard | 左栏 Session 列表 + 聊天式消息区（用户右、助手左、thinking 可折叠）|
| 用户注入 | Dashboard 输入 → WS → Worker 队列 |
| 接管模式 | 后端打开 PowerShell 运行交互式 `cbc --resume`，Worker 进入 held 态 |
| 优雅关闭 | lifespan handler：退出时 kill 所有子进程 |
| 默认模型 | `deepseek-v4-flash`，Session 级别可配置 |
| Meta-Agent 通道 | `/ws/agent` 端点，Agent 实时接收事件 + 派发任务 |
| 命令来源辨別 | `send_task()` 含 `source` 参数（agent/user），两套独立 WS 通道 |
| cbc 重放去重 | `--resume` 重放事件不重复追加到 history |
| 状态灯即时更新 | WS 事件 → 本地 modelData 立即更新 → 异步 API 同步 |

### API 总览

#### Session 管理

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| GET | `/api/sessions` | — | 列出所有 Session（含 history、workerStatus）|
| POST | `/api/sessions` | `{name, model?, permissionMode?, ...}` | 创建 Session（不 spawn Worker）|
| GET | `/api/sessions/{session_id}` | — | 获取单个 Session 详情 |
| PATCH | `/api/sessions/{session_id}` | `{model?, permissionMode?, alwaysThinkingEnabled?, effort?, maxThinkingTokens?}` | 更新 Session 级配置（不 spawn Worker）|
| DELETE | `/api/sessions/{session_id}` | — | 删除 Session + kill 关联 Worker |

#### Worker 管理

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| POST | `/api/spawn` | `{sessionId, model?, permissionMode?, ...}` | 为 Session 创建 Worker |
| POST | `/api/task` | `{text, sessionId \| workerId, source?}` | 发任务（自动 auto-spawn）|
| POST | `/api/kill/{worker_id}` | — | 销毁 Worker 进程（不删 Session）|
| GET | `/api/list` | — | 列出运行中的 Worker |
| POST | `/api/worker/{worker_id}/restart` | — | 重启 cbc 进程 |
| POST | `/api/worker/{worker_id}/interrupt` | — | 中断当前任务（kill + --resume）|
| POST | `/api/worker/{worker_id}/takeover` | — | 打开交互式 PowerShell + Worker 切 held 态 |
| POST | `/api/worker/{worker_id}/settings` | `{model?, permissionMode?, alwaysThinkingEnabled?, effort?, maxThinkingTokens?}` | **统一设置接口**：修改模型/权限模式/思考模式 + respawn |
| POST | `/api/worker/{worker_id}/rename` | `{name}` | 重命名 Session |
| POST | `/api/worker/{worker_id}/branch` | `{name?}` | 从当前 Session fork 新分支 |
| GET | `/api/models` | — | 支持模型列表 + 默认模型 |

> **已废弃接口**（建议迁移到 `/settings`）：
> - `POST /api/worker/{worker_id}/switch-model` → 改用 `/settings`
> - `POST /api/worker/{worker_id}/switch-mode` → 改用 `/settings`
> - `POST /api/worker/{worker_id}/switch-thinking` → 改用 `/settings`

#### WebSocket

| 路径 | 用途 | 消息（Client -> Server） | 事件（Server -> Client） |
|------|------|--------------------------|--------------------------|
| `/ws` | Dashboard（人类观察 + 注入）| `user_inject`：`{sessionId, text}` | `worker.spawned`, `worker.status`, `worker.stream`, `worker.result`, `worker.crashed`, `worker.destroyed`, `session.created/updated/renamed/deleted`, `error` |
| `/ws/agent` | Meta-Agent 通道 | `task` / `spawn` / `kill` / `list` | `worker.spawned`, `session.list`, `error` + 所有广播事件 |

#### 页面

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | Dashboard 单页 HTML |
| GET | `/favicon.ico` | Inline SVG favicon |

---

## 立即开始使用

### 1. 环境准备

```bash
# 创建虚拟环境
python -m venv .venv

# 激活（Windows）
.venv\Scripts\activate
# 激活（macOS / Linux）
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置文件

```bash
# 复制示例配置（config.json 已在 .gitignore 中）
cp config.example.json config.json
```

`config.json` 中可修改的字段一览：

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `port` | `8767` | 服务端口 |
| `cbc.model` | `deepseek-v4-flash` | 默认模型（支持 deepseek / glm / minimax / kimi / hy3） |
| `cbc.permission_mode` | `bypassPermissions` | 权限模式（`default` / `acceptEdits` / `plan` / `dontAsk` 等） |
| `cbc.always_thinking_enabled` | `false` | 是否启用深度思考 |
| `cbc.effort` | `""` | 思考强度（`low` / `medium` / `high` / `max` 等） |
| `kimi.model` | `kimi-code/kimi-for-coding` | Kimi 默认模型 |

> 更多配置项说明见 `config.example.json` 中的中文注释。

### 3. 启动服务

**方式一：直接运行**

```bash
python main.py
# 浏览器打开 → http://localhost:8767
```

**方式二：使用启动脚本（含 Cloudflare Tunnel）**

```bat
# 一键启动服务 + 内网穿透（Tunnel 部署需要先配置，见下方 Tunnel 章节）
scripts\start_cliconductor.bat
```

停止服务：

```bat
scripts\stop_cliconductor.bat
```

启动后在浏览器打开 `http://localhost:8767`，即可看到 Dashboard。左边是 Session 列表，右边是聊天区，创建 Session → 点击 Spawn → 输入任务即可开始使用。

---

## Cloudflare Tunnel 公网部署

通过 Cloudflare Tunnel 将 CLIConductor 暴露到公网，无需公网 IP、无需配置路由器端口转发。适合与朋友分享、移动端访问、远程查看 worker 进度等场景。

### 前置条件

1. 拥有一个托管在 Cloudflare 的域名（免费方案即可）
2. 安装 `cloudflared`：

```powershell
# Windows（用 winget）
winget install Cloudflare.cloudflared

# macOS
brew install cloudflare/cloudflare/cloudflared

# Linux
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared
```

### 一次性配置（仅需一次）

**Step 1：登录 Cloudflare**

```bash
cloudflared tunnel login
```
浏览器会自动打开 Cloudflare 授权页面，选择域名完成授权。

**Step 2：创建隧道**

```bash
cloudflared tunnel create cliconductor
```
创建成功后会输出隧道 ID（如 `fa87468c-4d93-4042-85fd-6182d2a22b65`），并生成凭证文件 `~/.cloudflared/<ID>.json`。

**Step 3：配置 DNS 路由**

```powershell
# 将你的子域名指向本地端口（替换为你的实际域名和隧道 ID）
cloudflared tunnel route dns <隧道ID> cliconductor.yourdomain.com
```

**Step 4：编辑 cloudflared 配置文件**

编辑 `~/.cloudflared/config.yml`：

```yaml
tunnel: <你的隧道ID>
credentials-file: C:\Users\<你的用户名>\.cloudflared\<隧道ID>.json

ingress:
  - hostname: cliconductor.yourdomain.com
    service: http://localhost:8767
  - service: http_status:404
```

### 启动 Tunnel

**方式一：使用项目脚本（推荐）**

```bat
scripts\start_cliconductor.bat
```
该脚本会依次启动 FastAPI 服务和 cloudflared tunnel，PID 记录在 `data/process.pid` 中。

关闭服务：

```bat
scripts\stop_cliconductor.bat
```

**方式二：手动分别启动**

```bash
# 终端 1：启动 CLIConductor
python main.py

# 终端 2：启动 Tunnel
cloudflared tunnel run cliconductor
```

### 分享访问

启动后，任何人都可以通过以下地址访问你的 Dashboard：

```
https://cliconductor.yourdomain.com
```

打开页面即可创建 Session、启动 Worker、与他人共享同一个工作台。

> **安全提示**：Tunnel 会将本地服务完全暴露到公网。建议：
> - 仅在受信任的网络环境中长期运行
> - 可在 Cloudflare Zero Trust → Access 中配置访问策略（OTP 验证码、邮箱限制等）来保护 Dashboard

---

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
├── main.py                  入口（from src.server import app）
├── src/
│   ├── __init__.py
│   ├── server.py            FastAPI 路由 + WS
│   ├── worker.py            Worker 数据类 + 生命周期管理
│   └── session.py           Session 存储（UUID key）
├── index.html               Dashboard 单页（两栏：session 列表 + 聊天区）
├── data/
│   ├── sessions/            Session JSON 文件（ses_<uuid>.json）
│   └── workdirs/            Worker 工作目录
├── requirements.txt         fastapi, uvicorn, websockets
├── docs/
│   ├── plans&overviews/
│   │   ├── global.md        全局规划（目标/架构/路线图/命名约定）
│   │   ├── current.md       当前 Phase 1 计划
│   │   └── myTODO.md        个人 TODO
│   └── references/
│       └── dionysusc-reference.md
└── devNote.md               协作笔记
```

## 关键设计

### Worker 与 Session 分离

- **Worker** — 运行时 cbc 进程，持有 session_id 引用。kill 后 Worker 消失。
- **Session** — 持久化数据（UUID `ses_<16hex>`），含 history、model、cbc_session_id。独立于 Worker 生命周期。

### 多 Adapter 架构

CLIConductor 通过 `CliAdapter` 协议支持多种 CLI 工具。当前内置：

| Adapter | CLI 工具 | 进程模式 | 支持 resume | 支持 fork |
|---------|----------|----------|:-----------:|:---------:|
| `cbc` | CodeBuddy CLI | 长驻 stdin stream-json | ✅ | ✅ |
| `kimi` | Kimi Code CLI | wrapper 包装 `-p` 单轮调用 | ✅ | ✅（文件复制实现） |

cbc 集成模式：

```bash
cbc -p --output-format stream-json --input-format stream-json -y
```

Kimi 集成模式：

```bash
kimi -p <prompt> --output-format stream-json -S <session_id> -m <model>
```

Kimi 的 `-p` 模式是一次性进程，因此由 `src/adapters/kimi/wrapper.py` 作为长驻子进程，内部循环调用 Kimi 并转发 stream-json 事件。

### 消息队列（stdin 互斥）

```
Agent 任务 ──→ asyncio.Queue (FIFO) ──→ consumer ──→ adapter.stdin.write()
用户注入 ──→                                         result → 取下一条
```

### 特殊命令处理

cbc 的 /model、/branch 等无法通过 stdin stream-json 发送。方案：kill + `--resume <cbc_session_id>` + CLI 参数重启。

| 命令 | 实现方式 |
|------|---------|
| `/model` | `--model <model>` + respawn |
| Shift+Tab | `--permission-mode <mode>` + respawn |
| Thinking 模式 | `--always-thinking-enabled` / `--effort` / `--max-thinking-tokens` + respawn |
| `/branch` | `--resume <sid> --fork-session` + spawn |
| `/rename` | CLIConductor 自维护 Session name 字段 |

以上配置变更统一通过 `/settings` 接口下发，后端写 Session + kill/restart Worker。

### Kimi 会话导入

Kimi 会话存储在 `~/.kimi-code/sessions/<workspace>/<session>/`。CLIConductor 提供：

- `GET /api/kimi/workspaces` — 列出有会话的 workspace
- `GET /api/kimi/sessions?cwd=...` — 列出指定工作目录下的 Kimi 会话
- `POST /api/kimi/sessions/import` — 将 Kimi 会话导入为 CLIConductor Session（含 history 与 usage）

### Kimi 适配器说明

- **权限模式**：Kimi 的 `-p/--prompt` 模式不能和 `-y/--auto/--plan` 同时使用；实测 `-p` 模式下工具调用会被自动批准（包括 `rm` 等操作）。因此 CLIConductor 对 Kimi Worker 不额外传递权限参数。
- **fork**：Kimi CLI 目前没有稳定的 `--fork` 参数，因此通过复制会话目录 + 注册新 `session_id` 实现 fork。该实现依赖 Kimi 内部文件格式，属于最佳努力（best-effort）。

### 命名约定

| 术语 | 定义 |
|------|------|
| **Meta-Agent** | 具有与 Worker 交互权限和能力的上层 AI Agent（如 CodeBuddy Code）。通过 `/ws/agent` 通道操作。 |
| **Worker** | 一个运行中的 CLI 子进程（cbc / Kimi 等）。进程终止后不删除 Session。 |
| **Session** | 持久化会话。UUID 管理，含 cbc_session_id（对 Kimi 则存储 Kimi session id）、history、last_result 等。 |
| **Human** | 人类用户。通过 Dashboard 观察/注入/接管。来源标记为 `"user"`。 |
