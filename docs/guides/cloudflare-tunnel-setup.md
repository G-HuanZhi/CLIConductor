# Cloudflare Tunnel — CLIConductor + QQ Bridge 外网访问指南

> **方案 C 实施指南** | 目标：在 Windows 上通过 Cloudflare Tunnel 让 Dashboard 可公网访问，同时保持 QQ Bridge 正常运行。

---

## 1. 架构全景

### 当前架构（仅本机）

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│  QQ 用户     │     │  你自己      │     │  Meta-Agent     │
│              │     │  (Dashboard) │     │  (CodeBuddy CLI) │
└──────┬───────┘     └──────┬───────┘     └────────┬─────────┘
       │                    │                      │
       ▼                    ▼                      ▼
┌──────────────┐     ┌─────────────────────────────────────────┐
│  QQ Server   │     │        本机 Windows (127.0.0.1)          │
└──────┬───────┘     │                                          │
       │             │  :3001                                    │
       ▼             │  NapCat ←── WS ──→ NoneBot2 (:8080)    │
┌──────────┐        │    │                   │                  │
│  NapCat  │        │    │           qq-bridge/plugin.py        │
│  (QQ协议) │        │    │                   │                  │
└────┬─────┘        │    │           HTTP API  │                  │
     │ WS           │    └───────────────────┐  │                  │
     ▼              │                        ▼  ▼                  │
┌──────────┐        │              CLIConductor (:8767)           │
│ NoneBot2 │        │              FastAPI + Dashboard             │
│ (:8080)  │        │                      │                       │
└────┬─────┘        │               Worker │  → cbc 进程          │
     │              │                      ▼                       │
     │ HTTP         │              Session Persistence             │
     ▼              │              (data/sessions/*.json)          │
┌────────────┐     └─────────────────────────────────────────┘
│ qq-bridge/ │
│ plugin.py  │
└────────────┘
```

### 加上 Cloudflare Tunnel 后

```
                               Cloudflare CDN
                              (cloudflare.com)
                                    │
                            HTTPS   │   Zero Trust Access
                      ┌─────────────┴─────────────┐
                      │                           │
                      ▼                           ▼
              外网手机/平板                    你的笔记本
           dashboard.your-domain.com      (不在本机局域网)
                      │                           │
                      └───────────┬───────────────┘
                                  │
                        Cloudflare Tunnel
                        (cloudflared 守护进程)
                                  │
                    ┌─────────────┴─────────────┐
                    │    本机 Windows           │
                    │                           │
                    │  cloudflared ──→ localhost:8767
                    │                           │
                    │  CLIConductor (:8767)     │ ← Dashboard + API
                    │  NoneBot2     (:8080)     │ ← QQ Bridge 框架
                    │  NapCat       (:3001)     │ ← QQ 协议端
                    └───────────────────────────┘
```

**关键理解**：
- Cloudflare Tunnel 只暴露 CLIConductor Dashboard（`localhost:8767`），不暴露 QQ 相关端口
- QQ Bridge（NapCat → NoneBot2 → plugin.py → CLIConductor）全程走 localhost，不受影响
- 你从公网访问 Dashboard 就像在本地浏览器打开一样

---

## 2. 你要做的事情（总览）

| # | 步骤 | 耗时 | 说明 |
|---|------|------|------|
| 1 | 注册 Cloudflare + 添加域名 | 10 min | 需要你拥有一个域名 |
| 2 | 安装 cloudflared | 2 min | `winget install` |
| 3 | 创建隧道 + 配置 DNS | 5 min | 命令行操作 |
| 4 | 修改 CLIConductor bind | 1 min | 改一行代码 |
| 5 | 配置防火墙 | 2 min | PowerShell 一条命令 |
| 6 | 启动隧道 + 验证 | 3 min | 浏览器验证 |
| 7 | 设置开机自启 | 2 min | Windows 服务 |

**总耗时约 25 分钟**（不含域名准备时间）。

---

## 3. 前置条件

### 3.1 你需要一个域名

- 可以在 Cloudflare 注册（约 $10/年），也可以将已有域名 NS 记录指向 Cloudflare
- 在 Cloudflare Dashboard 中添加你的域名，等待 DNS 生效

### 3.2 Cloudflare 账号

- 注册 [cloudflare.com](https://cloudflare.com)（免费）
- 登录 Dashboard

---

## 4. 具体步骤

### 步骤 1：安装 cloudflared

PowerShell（管理员）：

```powershell
winget install Cloudflare.cloudflared
```

验证安装：

```powershell
cloudflared --version
# 应输出：cloudflared version 2024.x.x
```

### 步骤 2：登录 Cloudflare

```powershell
cloudflared tunnel login
```

这会自动打开浏览器，跳转到 Cloudflare 授权页面。选择你的域名，点击 Authorize。

证书会自动保存到：
```
C:\Users\<你的用户名>\.cloudflared\cert.pem
```

### 步骤 3：创建隧道

```powershell
cloudflared tunnel create cliconductor
```

输出示例：
```
Tunnel credentials written to C:\Users\...\.cloudflared\<UUID>.json
Created tunnel cliconductor with id <UUID>
```

**记下 UUID**，之后会用到。 fa87468c-4d93-4042-85fd-6182d2a22b65

### 步骤 4：配置隧道规则

创建配置文件。打开 PowerShell（普通用户即可）：

```powershell
mkdir -Force $env:USERPROFILE\.cloudflared
notepad $env:USERPROFILE\.cloudflared\config.yml
```

填入以下内容（替换 `<TUNNEL_UUID>` 为上一步的 UUID）：

```yaml
tunnel: fa87468c-4d93-4042-85fd-6182d2a22b65
credentials-file: C:\Users\14709\.cloudflared\fa87468c-4d93-4042-85fd-6182d2a22b65.json

ingress:
  # Dashboard + API + WebSocket
  - hostname: cliconductor.ablaze.dpdns.org
    service: http://localhost:8767

  # 可选：如果以后需要调试 QQ Bridge
  # - hostname: qqbridge.你的域名.com
  #   service: http://localhost:8080

  # 兜底：拒绝其他请求
  - service: http_status:404
```

### 步骤 5：设置 DNS 记录

```powershell
cloudflared tunnel route dns cliconductor cliconductor.ablaze.dpdns.org
```

这会在 Cloudflare DNS 中自动创建一条 CNAME 记录：
```
dashboard  CNAME  <TUNNEL_UUID>.cfargotunnel.com
```

### 步骤 6：修改 CLIConductor 绑定地址

编辑 `main.py`，将 host 改为允许外部访问：

```python
# main.py — 修改前
config = uvicorn.Config(app, host="127.0.0.1", port=8767, ...)

# main.py — 修改后
config = uvicorn.Config(app, host="0.0.0.0", port=8767, ...)
```

> **为什么要改？** Cloudflare Tunnel（cloudflared）在本机运行，理论上 `127.0.0.1` 也能连。但 `0.0.0.0` 可以让你在同一局域网的手机/平板上直接用 IP 访问，更灵活。如果只想隧道访问，不改也可以。

### 步骤 7：配置 Windows 防火墙

PowerShell（管理员）：

```powershell
New-NetFirewallRule -DisplayName "CLIConductor" -Direction Inbound -LocalPort 8767 -Protocol TCP -Action Allow
```

如果只通过隧道路由，这步可以跳过——cloudflared 访问 `localhost:8767` 不走防火墙入站规则。但如果要局域网直接访问，这一步必须执行。

### 步骤 8：启动 CLIConductor + QQ Bridge + Tunnel

**终端 1 — CLIConductor**（先启动这个）：

```powershell
cd D:\project\CLIConductor-qq
python main.py
```

输出：
```
[HH:MM:SS] CLIConductor starting on 0.0.0.0:8767
[HH:MM:SS] [CLIConductor] Loaded X sessions from disk
```

**终端 2 — QQ Bridge**（NoneBot2 + plugin）：

```powershell
cd D:\project\CLIConductor-qq\qq-bridge
python bot.py
```

输出：
```
[QQ Bridge] CLIConductor 已连接，支持 X 个模型
[QQ Bridge] 默认模型: deepseek-v4-flash
```

**终端 3 — Cloudflare Tunnel**：

```powershell
cloudflared tunnel run cliconductor
```

输出：
```
INF Starting tunnel tunnelID=<UUID>
INF Registered tunnel connection
INF Connection <ID> registered with protocol: quic
```

### 步骤 9：验证

在浏览器访问 `https://dashboard.你的域名.com`，应该看到 CLIConductor Dashboard。

**功能验证清单**：

- [ ] Dashboard 页面正常加载
- [ ] 左侧 Session 列表显示
- [ ] 可以创建新 Session
- [ ] 发送消息能看到流式回复（WebSocket 正常）
- [ ] WebSocket 实时更新（worker.stream 事件正常到达）
- [ ] QQ Bridge 正常工作（QQ 上发消息能收到回复）

---

## 5. 开机自启（可选）

### 5.1 CLIConductor 设为 Windows 服务

用 NSSM（Non-Sucking Service Manager）或 Task Scheduler。

**推荐用 Task Scheduler**（Windows 自带）：

PowerShell（管理员）：

```powershell
$action = New-ScheduledTaskAction -Execute "python" -Argument "D:\project\CLIConductor-qq\main.py"
$trigger = New-ScheduledTaskTrigger -AtLogon
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "CLIConductor" -Action $action -Trigger $trigger -Principal $principal -Settings $settings
```

### 5.2 Cloudflare Tunnel 设为 Windows 服务

```powershell
cloudflared service install
```

配置文件路径已注册，服务会自动读取 `C:\Users\<用户名>\.cloudflared\config.yml`。

**管理服务**：
```powershell
# 启动
sc start cloudflared

# 停止
sc stop cloudflared

# 查看状态
sc query cloudflared
```

---

## 6. 安全加固（强烈建议）

Cloudflare Dashboard → Zero Trust → Access → Applications → Add Application：

1. **选择 Self-hosted**
2. Application domain：`dashboard.你的域名.com`
3. Policy name：`Require Email OTP`
4. Action：`Allow`
5. Configure rules：
   - Selector：`Emails`
   - Value：你的邮箱

现在访问 Dashboard 时，Cloudflare 会先要求输入邮箱，收到一次性 PIN 码后才能进入。公网访问的安全性问题解决。

---

## 7. 端口与协议总结

| 服务 | 端口 | 协议 | 绑定 | 对外暴露 | 用途 |
|------|------|------|------|---------|------|
| CLIConductor | 8767 | HTTP + WS | `0.0.0.0` | 通过 Cloudflare Tunnel | Dashboard + API |
| NoneBot2 | 8080 | HTTP | `127.0.0.1` | 不暴露 | QQ Bridge 框架 |
| NapCat | 3001 | WS | `127.0.0.1` | 不暴露 | QQ 协议连接 |
| Cloudflare Tunnel | 动态 | QUIC | — | Cloudflare CDN | 公网入口 |

**关键**：外网用户只看到 `dashboard.你的域名.com:443`（标准 HTTPS），背后的 8767 / WebSocket 全部由 Cloudflare 处理。

---

## 8. QQ Bridge 注意事项

**QQ Bridge 不需要任何改动。** 原因：

1. NapCat 连接 QQ 服务器走的是对外连接（outbound），不是监听端口
2. NoneBot2 连接 NapCat 走 `127.0.0.1:3001`（本机 ws）
3. qq-bridge/plugin.py 连接 CLIConductor 走 `127.0.0.1:8767`（本机 HTTP）
4. 所有 QQ 流量：QQ 用户 → QQ 服务器 → NapCat → NoneBot2 → CLIConductor，全程不经过 Cloudflare Tunnel

**唯一可能的影响**：如果你从手机通过隧道访问 Dashboard 进行 takeover（接管 Worker），后续 QQ Bridge 发消息时该 Worker 的状态已经变了。这属于多入口竞争的正常情况，plugin.py 每次请求前会重新检查 session 状态。

---

## 9. 故障排查

| 问题 | 检查项 |
|------|--------|
| 浏览器访问 502 | `cloudflared tunnel run` 输出是否显示 `Unable to reach the origin service`？检查 CLIConductor 是否启动，端口是否正确 |
| WebSocket 不工作 | Cloudflare Tunnel 原生支持 WS，无需额外配置。检查 `cloudflared` 版本 ≥ 2023.x |
| 手机访问白屏 | DNS 是否生效？`nslookup dashboard.你的域名.com` 是否返回 Cloudflare IP？ |
| QQ 发消息没响应 | 检查 NoneBot2 终端输出，CLIConductor 终端是否收到 `/api/task` 请求 |
| Tunnel 连接频繁断开 | 可能网络不稳定或 Windows 电源管理导致。设为服务后会更稳定 |

### 快速诊断

```powershell
# 检查 CLIConductor 是否运行
curl http://localhost:8767/api/models

# 检查 cloudflared 状态
cloudflared tunnel list

# 检查 DNS 解析
nslookup dashboard.你的域名.com
```

---

## 10. 完整启动命令（备忘）

每次要用时的启动顺序：

```powershell
# 终端 1
cd D:\project\CLIConductor-qq
python main.py

# 终端 2
cd D:\project\CLIConductor-qq\qq-bridge
python bot.py

# 终端 3
cloudflared tunnel run cliconductor
```

或一步到位（`start` 开新窗口）：

```powershell
start "CLIConductor" cmd /k "cd /d D:\project\CLIConductor-qq && python main.py"
start "QQ Bridge" cmd /k "cd /d D:\project\CLIConductor-qq\qq-bridge && python bot.py"
start "Tunnel" cmd /k "cloudflared tunnel run cliconductor"
```

如果已安装为服务，重启电脑后 CLIConductor（Task Scheduler）和 cloudflared（Windows 服务）会自动启动，只需手动启动 QQ Bridge。

---

## 11. 补充：同时更新主 worktree 的 main.py

`qq-adapter` 分支的 `main.py` 已改为 `host="0.0.0.0"`（因为刚刚 merge 了 main）。当你 push qq-adapter 后，主 worktree 也会跟着更新。

如果主 worktree（`D:\project\CLIConductor`）也需要同样的改动，可以直接在那里改 `main.py`：

```python
# main.py
config = uvicorn.Config(app, host="0.0.0.0", port=8767, ...)
```

也可以用环境变量统一管理（推荐，更优雅）：

```python
# main.py
import os
host = os.environ.get("CLICONDUCTOR_HOST", "127.0.0.1")
port = int(os.environ.get("CLICONDUCTOR_PORT", "8767"))
config = uvicorn.Config(app, host=host, port=port, ...)
```

这样默认仍是安全的 `127.0.0.1`，需要外网访问时设置环境变量即可，不用改代码。
