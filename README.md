# CLIConductor

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
| **你** | 在真实终端运行 `node packages/cbc-bridge/connect.js` |
| **我 (Claw)** | 通过 ws://localhost:6789 WebSocket 读写 |

## 目录

```
packages/cbc-bridge/
├── server.js        # 核心桥接：WebSocket 服务端 + node-pty（端口 6789）
├── serverB.js       # 第二个实例（端口 6790），多实例实验用
├── connect.js       # 用户端：Node.js 原生终端客户端（raw mode，推荐）
├── chat.js          # Agent 端：多轮对话，逐字符输入 + 间隔等待
├── type.js          # 逐字符发送命令（用于 cbc 等 TUI 类 CLI）
├── key.js           # 发送特殊键（Tab/Esc/Alt+M/Ctrl-C 等）
├── send.js          # 一次性批量发送命令（不适用于 TUI 类 CLI）
├── claw-client.js   # Agent 端备用脚本（已弃用，由 chat.js 替代）
├── claw-chat.js     # Agent demo，硬编码消息演示

archive/             # 冻结的旧计划/实验/文档（参考用）
├── references/       # 备选方案存档（如 web-xterm.js 方案）
└── ...
```

