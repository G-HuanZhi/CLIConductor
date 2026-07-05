# CLIConductor Dashboard 外网访问方案

## 当前状态

Dashboard 运行在 **FastAPI + Uvicorn**，绑定 `127.0.0.1:8767`，仅本机可访问。

```python
# main.py 当前配置
config = uvicorn.Config(app, host="127.0.0.1", port=8767, ...)
```

Dashboard 使用 HTTP API + WebSocket (`/ws`) 实时通信，因此方案须同时支持 WebSocket 代理。

---

## 方案总览

| 方案 | 难度 | 成本 | 安全性 | 公网 | 适用场景 |
|------|------|------|--------|------|----------|
| A. 绑定 0.0.0.0 | 极低 | 免费 | 低 | 需端口转发 | 局域网访问 |
| B. Nginx/Caddy 反代 | 中 | 免费 | 高 | 需服务器 | 生产环境 |
| C. Cloudflare Tunnel | 低 | 免费 | 高 | 原生支持 | 推荐首选 |
| D. frp 内网穿透 | 中 | 需VPS | 中 | 原生支持 | 自建穿透 |
| E. ngrok | 极低 | 免费/付费 | 中 | 原生支持 | 开发调试 |
| F. Tailscale Funnel | 低 | 免费 | 高 | 原生支持 | 已用 Tailscale |
| G. ZeroTier | 低 | 免费 | 高 | 需客户端 | 固定设备间 |
| H. SSH 反向隧道 | 中 | 免费 | 高 | 需中转VPS | 临时访问 |

---

## 方案 A：绑定 0.0.0.0（局域网访问）

### 原理

将 `host` 从 `127.0.0.1` 改为 `0.0.0.0`，使服务监听所有网络接口。

### 实施

```python
# main.py
config = uvicorn.Config(app, host="0.0.0.0", port=8767, ...)
```

### 使用方式

- 局域网其他设备访问：`http://<本机局域网IP>:8767`
- 查看本机 IP：`ipconfig`（Windows）或 `ifconfig`/`ip a`（Linux）

### 优点

- 零外部依赖，改动一行代码
- 适合同一 Wi-Fi / 局域网下的多设备访问

### 缺点

- 无加密（HTTP 明文传输）
- 无法从互联网访问（除非配置路由器端口转发 + 动态 DNS）
- 防火墙可能阻止（Windows 首次启动会弹窗授权）

### 适用场景

- 同局域网内用手机 / 平板 / 另一台电脑观察 Dashboard
- 仅内网使用，不需要公网访问

---

## 方案 B：Nginx / Caddy 反向代理

### 原理

在公网服务器上部署 Nginx 或 Caddy，作为反向代理转发请求到内网机器。

### 架构

```
外网用户 → Nginx/Caddy (公网VPS, HTTPS) → CLIConductor (内网, 8767)
```

### Nginx 示例配置

```nginx
server {
    listen 443 ssl;
    server_name dashboard.your-domain.com;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # HTTP API
    location / {
        proxy_pass http://内网IP:8767;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket
    location /ws {
        proxy_pass http://内网IP:8767;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
```

### Caddy 示例配置（更简洁）

```caddyfile
dashboard.your-domain.com {
    reverse_proxy 内网IP:8767
}
```

Caddy 自动申请和管理 Let's Encrypt 证书。

### 优点

- 生产级方案，性能高，稳定可靠
- 自定义域名、HTTPS、认证、限流等全部可控
- Nginx/Caddy 均可添加 HTTP Basic Auth 保护

### 缺点

- 需要一台有公网 IP 的 VPS（月费约 30-50 元）
- 需要配置域名 DNS 解析
- 内网机器需能连接到 VPS（通常用 frp 或 VPN 打通）

### 适用场景

- 正式上线，长期运行
- 需要自定义域名
- 对安全性和可靠性要求高

---

## 方案 C：Cloudflare Tunnel（推荐首选）

### 原理

Cloudflare 提供免费隧道服务（原名 Argo Tunnel），在本地运行 `cloudflared` 守护进程，与 Cloudflare 边缘节点建立持久连接。外部流量经 Cloudflare 转发到本地。

### 架构

```
外网用户 → Cloudflare CDN (HTTPS) → cloudflared 守护进程 → CLIConductor (localhost:8767)
```

无需公网 IP，无需端口转发，Cloudflare 自动处理 DNS、HTTPS、DDoS 防护。

### 实施步骤

**1. 安装 cloudflared**

```bash
# Windows (PowerShell 管理员)
winget install Cloudflare.cloudflared

# macOS
brew install cloudflared

# Linux
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared
sudo mv cloudflared /usr/local/bin/
```

**2. 登录 Cloudflare**

```bash
cloudflared tunnel login
```

浏览器会打开 Cloudflare 授权页面，选择要使用的域名。

**3. 创建隧道**

```bash
cloudflared tunnel create cliconductor
```

这会在 Cloudflare DNS 中创建一条 `UUID.cfargotunnel.com` 的 CNAME 记录。

**4. 配置隧道**

创建 `config.yml`：

```yaml
tunnel: <TUNNEL_UUID>
credentials-file: C:\Users\<user>\.cloudflared\<TUNNEL_UUID>.json

ingress:
  - hostname: dashboard.your-domain.com
    service: http://localhost:8767
  - service: http_status:404
```

**5. 设置 DNS**

```bash
cloudflared tunnel route dns cliconductor dashboard.your-domain.com
```

**6. 运行隧道**

```bash
cloudflared tunnel run cliconductor
```

或安装为 Windows 服务：

```bash
cloudflared service install
```

### WebSocket 支持

Cloudflare Tunnel 原生支持 WebSocket，无需额外配置。CLIConductor 的 `/ws` 和 `/ws/agent` 均可直接使用。

### 安全加固（可选）

在 Cloudflare Dashboard → Zero Trust → Access 添加：

- **一次性 PIN 码**：访问前需输入发送到邮箱的验证码
- **Google/GitHub OAuth**：仅允许指定邮箱登录
- **IP 白名单**：限制来源 IP

无需修改任何 CLIConductor 代码，完全在 Cloudflare 侧配置。

### 优点

- **完全免费**，无需 VPS
- 自动 HTTPS（Let's Encrypt 边缘证书）
- Cloudflare CDN 加速 + DDoS 防护
- 无需公网 IP，无需路由器端口转发
- 原生 WebSocket 支持
- 可一键启用 Zero Trust 认证
- 支持 Windows 服务，开机自启

### 缺点

- 依赖 Cloudflare 服务（可用性极高，但非自主可控）
- 流量经过 Cloudflare（注意隐私）
- 免费版有限速（通常够用）

### 适用场景

- **最推荐的通用方案**
- 个人项目、小团队、临时演示
- 需要 HTTPS + 安全认证但不想管理服务器

---

## 方案 D：frp 内网穿透

### 原理

frp（Fast Reverse Proxy）是一款开源内网穿透工具。需要一台有公网 IP 的 VPS 运行 frp 服务端（frps），内网机器运行 frp 客户端（frpc）。

### 架构

```
外网用户 → VPS (frps, 公网IP:自定义端口) → 内网机器 (frpc) → CLIConductor (localhost:8767)
```

### frps 配置（VPS 上）

```ini
# frps.toml
bindPort = 7000
vhostHTTPPort = 8080
```

### frpc 配置（本地 Windows）

```ini
# frpc.toml
serverAddr = "你的VPS的IP"
serverPort = 7000

[[proxies]]
name = "dashboard"
type = "http"
localPort = 8767
customDomains = ["dashboard.your-domain.com"]
```

WebSocket 支持：

```ini
[[proxies]]
name = "dashboard-ws"
type = "tcp"
localPort = 8767
remotePort = 8767
```

### 优点

- 自主可控，数据不过第三方
- 支持 TCP/HTTP/HTTPS/WebSocket/UDP
- 开源，活跃维护

### 缺点

- 需要一台公网 VPS（月费约 30-50 元）
- 需自行配置 SSL 证书
- 需要一定的运维能力

### 适用场景

- 有 VPS 且希望自主可控
- 对隐私要求高，不愿流量经过第三方
- 多个内网服务需要统一暴露

---

## 方案 E：ngrok

### 原理

ngrok 是最知名的内网穿透工具，在本地运行客户端，自动分配一个公网 URL 指向本地服务。

### 实施

```bash
# 下载 ngrok 并注册免费账户获取 authtoken
ngrok config add-authtoken <your-token>

# 启动隧道
ngrok http 8767
```

输出：
```
Forwarding  https://xxxx-xxx-xxx.ngrok-free.app -> http://localhost:8767
```

### 优点

- 极简，一条命令启动
- 自动 HTTPS
- 有 Web 界面查看请求/响应
- 免费版足够开发调试

### 缺点

- 免费版域名随机变化，每次重启不同
- 免费版有带宽和时间限制
- 固定域名需付费（$8/月起）
- 数据经过 ngrok 服务器

### 适用场景

- 快速临时分享给他人
- 开发阶段调试 webhook
- 临时演示

---

## 方案 F：Tailscale Funnel

### 原理

如果已经在使用 Tailscale 组网（mesh VPN），可直接开启 Funnel 功能将本地服务暴露到公网。

### 实施

```bash
# 启用 HTTPS 证书
tailscale cert your-node.tailnet-name.ts.net

# 开启 Funnel
tailscale funnel 8767
```

### 优点

- 集成在 Tailscale 内，无需额外工具
- 自动 HTTPS
- 可结合 Tailscale ACL 控制访问权限

### 缺点

- Funnel 有速率限制
- 域名访问较慢（需通过 Tailscale DERP 中继）
- 仅限已使用 Tailscale 的场景

### 适用场景

- 已在使用 Tailscale 的用户
- 偶尔需要外网访问

---

## 方案 G：ZeroTier（虚拟局域网）

### 原理

ZeroTier 创建虚拟局域网，所有加入的设备获得虚拟 IP，互访如同内网。

### 实施

1. 在 zerotier.com 创建网络
2. 各设备安装 ZeroTier 客户端并加入网络
3. 在本机授权新设备
4. 访问 `http://<本机ZeroTier虚拟IP>:8767`

### 优点

- 完全免费（最多 25 设备）
- P2P 直连，延迟低
- 安装后无需任何配置
- 不影响公网暴露，安全性好

### 缺点

- 每台设备需安装客户端
- 不适合给无关人员临时访问
- 假设 host 改为 `0.0.0.0` 或 ZeroTier 虚拟 IP

### 适用场景

- 自己的多台设备间互访（台式机、笔记本、手机）
- 小团队内部使用
- 不需要暴露到公网

---

## 方案 H：SSH 反向隧道

### 原理

SSH -R 参数可将远程端口映射到本地。

### 实施

```bash
# 需要一台有公网IP的VPS
ssh -R 8767:localhost:8767 user@your-vps-ip -N
```

VPS 上访问 `http://localhost:8767` 即可，或配合 Nginx 反代暴露。

### 优点

- 利用已有 SSH 工具，无需额外软件
- 加密传输
- 适合临时一次性访问

### 缺点

- 需要 VPS（有公网 IP）
- 连接不稳定时容易断开（可配合 autossh）
- WebSocket 稳定性一般
- 不适合长期使用

### 适用场景

- 临时远程调试
- 已有 VPS，仅需短暂访问

---

## 推荐方案

### 按场景推荐

| 你的需求 | 推荐方案 | 理由 |
|----------|----------|------|
| 同一 WiFi 下用手机查看 | **A. 绑定 0.0.0.0** | 零配置，立即可用 |
| 长期公网访问 + 自定义域名 | **C. Cloudflare Tunnel** | 免费、自动化、安全 |
| 已用 ZeroTier 多设备 | **G. ZeroTier** | 仅需 host 改为 0.0.0.0 |
| 有 VPS 想自主可控 | **B. Nginx 反代 + frp** | 自己掌控所有环节 |
| 临时分享给朋友看 | **E. ngrok** | 一条命令，立即生成公网链接 |
| 多设备私有访问 | **G. ZeroTier** | 安全、低延迟 |

### 组合推荐（最佳实践）

**日常开发 + 偶尔外网访问：**

```
第一步：A. 0.0.0.0 + C. Cloudflare Tunnel
```

- 局域网直接用 IP 访问
- 外网通过 Cloudflare Tunnel + Zero Trust 认证
- 改动最小，安全性最高

**仅自己多设备使用：**

```
G. ZeroTier
```

- 笔记本、台式机、手机全部加入 ZeroTier 网络
- 完全私有，不暴露公网

---

## 通用前置改动（所有方案都需要）

无论选哪种方案，都需要将 CLIConductor 绑定地址从 `127.0.0.1` 改为 `0.0.0.0`（方案 A 的改动）：

```python
# main.py
config = uvicorn.Config(app, host="0.0.0.0", port=8767, ...)
```

> **例外**：方案 C（Cloudflare Tunnel）、方案 E（ngrok）、方案 F（Tailscale Funnel）绑 `127.0.0.1` 也能工作，因为隧道客户端运行在本机。但为了统一和灵活性，建议统一改为 `0.0.0.0`。

### 可选增强：环境变量配置 host/port

```python
host = os.environ.get("CLICONDUCTOR_HOST", "0.0.0.0")
port = int(os.environ.get("CLICONDUCTOR_PORT", "8767"))
config = uvicorn.Config(app, host=host, port=port, ...)
```

这样无需修改代码即可灵活切换环境。

---

## 安全注意事项

1. **绝不将 8767 端口直接暴露到公网**（fastapi/uvicorn 不是为直接面向公网设计的）
2. **始终在前面加一层反代或隧道**（Nginx/Caddy/Cloudflare Tunnel）
3. **启用认证**：
   - Cloudflare Zero Trust Access（最简单）
   - Nginx `auth_basic`（最轻量）
   - FastAPI 中间件鉴权（如需要更细粒度）
4. **HTTPS 必须**：公网访问必须用 HTTPS，方案 B/C/D/E/F 均自动支持
5. **防火墙规则**：Windows 防火墙默认阻止外部连接，改为 `0.0.0.0` 后需手动允许

   ```powershell
   # PowerShell 管理员运行
   New-NetFirewallRule -DisplayName "CLIConductor" -Direction Inbound -LocalPort 8767 -Protocol TCP -Action Allow
   ```

---

## WebSocket 使用分析（是否可以替换）

### 当前 WebSocket 架构

CLIConductor 有 **两个 WebSocket 端点**，共用一个 `broadcast()` 函数向所有连接的客户端广播事件：

| 端点 | 客户端池 | 连接方 | 来源文件 |
|------|---------|--------|---------|
| `/ws` | `ws_clients` | Dashboard 浏览器 | `ts/app.ts:102` |
| `/ws/agent` | `agent_clients` | 外部 Meta-Agent | 外部系统 |

**关键设计**：`broadcast()` 将所有 worker/session 生命周期事件**同时发送给所有 ws_clients 和 agent_clients**，不做定向分发。

```python
# src/server.py:61-75
async def broadcast(data: dict):
    dead = set()
    for ws in list(ws_clients):         # → 所有 Dashboard 客户端
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    ws_clients.difference_update(dead)
    for ws in list(agent_clients):      # → 所有 Meta-Agent 客户端
        ...
```

---

### 事件清单（Server → Client）

共 **17 种**广播事件，全部经由 `broadcast()` 发出：

| # | 事件类型 | 发出位置 | 触发条件 | 关键数据 |
|---|---------|---------|---------|---------|
| 1 | `worker.stream` | `worker.py:_read_stdout()` | cbc 每输出一行 JSON | `{event: <cbc原始事件>}` |
| 2 | `worker.result` | `worker.py:_read_stdout()` | cbc 输出 `result` 事件 | `{status, result}` |
| 3 | `worker.result` | `worker.py:_consumer()` | 发送任务时 worker 已死 | `{status: "error", result}` |
| 4 | `worker.spawned` | `worker.py:create_worker()` | 新 worker 进程创建 | `{workerId, name, model}` |
| 5 | `worker.spawned` | `worker.py:branch_worker()` | 分支 worker 创建 | `{workerId, parentWorkerId}` |
| 6 | `worker.spawned` | `server.py:/api/spawn` | API 创建 worker | `{workerId, name, model}` |
| 7 | `worker.spawned` | `server.py:/api/task` | 发送任务时自动创建 | `{workerId, reason}` |
| 8 | `worker.destroyed` | `worker.py:kill_worker()` | worker 被杀死 | `{workerId}` |
| 9 | `worker.restarted` | `worker.py:restart_worker()` | worker 重启 | `{workerId, status}` |
| 10 | `worker.reconfigured` | `worker.py:respawn_worker()` | worker 重配置（换模型/模式） | `{workerId, status}` |
| 11 | `worker.status` | `worker.py:_consumer()` | 任务已派发到 cbc | `{status: "running"}` |
| 12 | `worker.status` | `server.py:/takeover` | 用户接管 worker | `{status: "held"}` |
| 13 | `worker.crashed` | `worker.py:_read_stdout()` | cbc 进程异常退出 | `{returncode}` |
| 14 | `session.created` | `server.py:/api/sessions` | 新建 session | `{sessionId, name}` |
| 15 | `session.updated` | `server.py:/api/sessions` | 更新 session | `{sessionId}` |
| 16 | `session.deleted` | `server.py:/api/sessions` | 删除 session | `{sessionId}` |
| 17 | `session.renamed` | `server.py:/api/rename` | 重命名 session | `{sessionId, oldName, newName}` |

### 事件清单（Client → Server）

| 端点 | 事件类型 | 发送方 | 用途 |
|------|---------|--------|------|
| `/ws` | `user_inject` | Dashboard | 用户输入消息发送到 worker |
| `/ws/agent` | `task` | Meta-Agent | 外部系统发送任务给 worker |
| `/ws/agent` | `spawn` | Meta-Agent | 创建 session + worker |
| `/ws/agent` | `kill` | Meta-Agent | 杀死 worker |
| `/ws/agent` | `list` | Meta-Agent | 列出所有 session |

---

### 哪些事件真正依赖 WebSocket？

#### 强依赖 WebSocket（实时流式推送）

| 事件 | 原因 |
|------|------|
| `worker.stream` | **核心**。cbc 输出是逐行流式的，用户需要实时看到 AI 思考/回答过程。每秒可能产生数十条事件。 |

#### 弱依赖 WebSocket（通知 / 状态同步）

| 事件 | 当前行为 | 可否替换 |
|------|---------|---------|
| `worker.result` | Dashboard 显示 `[DONE]`/`[ERROR]` | 可轮询，但实时性下降 |
| `worker.status` | Dashboard 更新顶部状态栏 | 可轮询，延迟可接受 |
| `worker.spawned/destroyed/restarted/reconfigured/crashed` | Dashboard 刷新 session 列表 | **完全可轮询**，Dashboard 已经维护 `/_setLocalWorker()` 状态 |
| `session.*` (created/updated/deleted/renamed) | Dashboard 刷新 session 列表 | **完全可轮询**，Dashboard 仅调用 `refreshSessions()` |

#### 不需要 WebSocket（已有 HTTP 等价接口）

| Client→Server 事件 | 已有 HTTP API |
|--------------------|---------------|
| Dashboard `user_inject` | `POST /api/task` |
| Meta-Agent `task` | `POST /api/task` |
| Meta-Agent `spawn` | `POST /api/spawn` |
| Meta-Agent `kill` | `POST /api/kill/{id}` |
| Meta-Agent `list` | `GET /api/sessions` |

---

### 替换方案对比

| 方案 | 改动量 | `worker.stream` 支持 | 浏览器兼容 | 适合 |
|------|--------|---------------------|-----------|------|
| **保持 WebSocket** | 无 | 完美 | 所有现代浏览器 | 当前最优 |
| **SSE (Server-Sent Events)** | 中 | 原生流式 | EventSource API | 可替代 server→client |
| **SSE + HTTP POST** | 大 | 流式 + 独立提交 | EventSource + fetch | 完全去掉 WS |
| **纯轮询 (Polling)** | 大 | 差（高延迟/高负载） | 所有浏览器 | 不推荐 |
| **gRPC 流** | 极大 | 流式 | 需 grpc-web | 太重 |

---

### SSE 方案评估

SSE 是 WebSocket server→client 方向的天然替代品，但**仅单向**（server→client），client→server 方向需回归 HTTP。

#### 架构变化

```
当前 (WebSocket):
  Dashboard ←──WS双向──→ Server

SSE + HTTP:
  Dashboard ←──SSE── Server          # 接收 stream/result/status/session 事件
  Dashboard ──POST──→ /api/task      # 发送用户消息
  Dashboard ──GET───→ /api/sessions   # 刷新列表
```

#### 优势

- **浏览器原生支持**（EventSource API），无需自定义协议，无需处理重连（浏览器自动重连）
- **HTTP/2 多路复用**：多个 SSE 连接可共享一个 TCP 连接
- **CDN 友好**：Cloudflare/Akamai 等 CDN 原生支持 SSE 透传（部分 CDN 对 WebSocket 收费或限速）
- **自动 gzip**：SSE 文本流可以透明压缩（WebSocket 消息通常不压缩）
- **更简单的服务端**：不需要维护 `ws_clients` 集合，无需手动清理死连接
- **去除了 server→client 方向的广播耦合**：每个客户端自行管理连接和重连

#### 劣势

- **单向**：client→server 退化为 HTTP POST，每次需新建连接，延迟略增（影响极小，因为 Dashboard 只有发送消息时才写数据）
- **不再是一个连接干所有事**：从 1 个 WS → 1 个 SSE + 偶尔 HTTP POST
- **连接数**：每个浏览器 tab 多维持 1 个 SSE 长连接（代替原来的 1 个 WS 连接，实际持平）
- **IE 不兼容**（Edge 无此问题）

#### 改动清单

| 文件 | 改动 |
|------|------|
| `src/server.py` | 新增 `/events` SSE 端点，替换 `broadcast()` → 改为 `send_sse()`；保留或移除 `/ws` 和 `/ws/agent` |
| `ts/app.ts` | `new WebSocket(...)` → `new EventSource("/events")`；`ws.send()` → `fetch("/api/task", ...)` |
| `src/worker.py` | `broadcast()` 调用改为 `send_sse()` 调用，接口一致，改动很小 |

#### SSE 服务端示例

```python
# server.py — SSE endpoint
from fastapi.responses import StreamingResponse
import asyncio

_sse_queues: list[asyncio.Queue] = []

@app.get("/events")
async def sse_events():
    queue: asyncio.Queue = asyncio.Queue()
    _sse_queues.append(queue)
    async def event_generator():
        try:
            while True:
                data = await queue.get()
                yield f"data: {json.dumps(data)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _sse_queues.remove(queue)
    return StreamingResponse(event_generator(), media_type="text/event-stream")

# 替换 broadcast()
async def sse_broadcast(data: dict):
    for q in _sse_queues:
        await q.put(data)
```

#### Dashboard 客户端示例

```typescript
// 替换 WebSocket
const es = new EventSource('/events');
es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    onWsMessage(data);  // 现有处理逻辑完全复用
};

// 发送消息 → HTTP
async function sendViaHttp(text: string, sessionId: string) {
    await fetch('/api/task', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, sessionId }),
    });
}
```

---

### 结论

| 维度 | 结论 |
|------|------|
| **是否可以替换 WebSocket** | 可以，SSE + HTTP 可完全替代 |
| **是否建议替换** | 看部署目标。如果**外网访问方案选择路径依赖 WebSocket 支持弱的方案**（如某些反向代理、极低带宽场景），SSE 是更好的选择；否则保持 WS 改动最小 |
| **核心风险点** | `worker.stream` 是最关键的事件，必须有流式通道。SSE 和 WS 都可以胜任 |
| **建议** | 当前阶段**保持 WebSocket**，因为所选的外网方案（Cloudflare Tunnel / Nginx / frp）全部原生支持 WebSocket，没有替换的必要 |

**底线**：WebSocket 不是外网访问的障碍。Cloudflare Tunnel、Nginx、Caddy、ngrok、frp 均原生支持 WebSocket 代理。如果某个方案（如某些免费 CDN、严格的企业防火墙代理）不支持 WebSocket 透传，到时候再考虑切到 SSE 也为时不晚，因为 SSE 改动量不大且逻辑完全兼容。
