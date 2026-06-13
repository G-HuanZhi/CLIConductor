# MyAgentsPlan

> 主 Agent + 用户**双控**同一个 CLI 进程的共享会话方案。

## 架构

```
你（原生终端 / PowerShell）── WebSocket ──┐
                                          ├── server.js (node-pty) ──→ cbc
我（Claw / OpenClaw）     ── WebSocket ──┘
```

## 启动

```bash
npm run bridge
# → ws://localhost:6789
```

## 连接

| 角色 | 方式 |
|------|------|
| **你** | 在真实终端运行 `packages/cbc-bridge/connect.ps1` |
| **我 (Claw)** | 通过 ws://localhost:6789 WebSocket 读写 |

## 目录

```
packages/cbc-bridge/
├── server.js        # 核心桥接：WebSocket + node-pty
├── connect.ps1      # 用户端：PowerShell 原生终端客户端
├── claw-client.js   # Claw 端：WebSocket 交互脚本
└── send.js          # 单次命令发送工具

archive/             # 冻结的旧计划/实验/文档（参考用）
├── references/       # 备选方案存档（如 web-xterm.js 方案）
└── ...
```
