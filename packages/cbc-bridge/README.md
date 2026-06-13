# cbc-bridge — 共享 CLI 会话桥

一个主 Agent + 人类用户**双控**同一个 CLI 进程的共享会话方案。

## 一句话

> 通过 `node-pty + WebSocket` 把任意 CLI 暴露给多个终端共享操控。

## 架构

```
你（原生终端）
  └─ connect.js ── WS ──┐
                         ├── server.js ── node-pty ── 目标 CLI (cbc)
我 (Agent)               │
  └─ chat.js/type.js ─ WS ┘
                         │
你（浏览器只读）
  └─ HTTP /snapshot ─────┘   (800ms 轮询)
```

- **server.js** — 核心桥接，一个进程一个 PTY
- 每个 WS 客户端可读写同一 PTY
- 浏览器端 HTTP 轮询只读（不参与 PTY 写入）

## 快速开始

### 1. 启动桥

```bash
cd packages/cbc-bridge
node server.js
# → ws://localhost:6789
```

### 2. 连接

**方式 A — 原生终端（推荐）：**
```bash
node connect.js
# 或指定端口：node connect.js localhost 6790
```

**方式 B — 浏览器只读监视：**
打开 `http://localhost:6789`

### 3. 多轮对话（Agent 使用）

```bash
node chat.js "第一个问题" "第二个问题" "第三个问题"
```

逐字符输入模拟键盘，每个问题间隔 4 秒等待回复。

### 4. 特殊按键

```bash
node key.js enter     # 回车
node key.js tab       # Tab (切换 thinking 模式)
node key.js alt-m     # Alt+M (切换 bypass/accept 模式)
node key.js esc       # Escape
node key.js ctrl-c    # Ctrl+C
```

### 5. 单次命令

```bash
node send.js "/model kimi-k2.6"
node type.js "/model kimi-k2.6"   # 逐字符发送
```

## 文件清单

| 文件 | 用途 |
|------|------|
| `server.js` | **核心** — HTTP + WebSocket + node-pty 桥（默认端口 6789） |
| `serverB.js` | 第二个实例 demo（端口 6790），用于多实例实验 |
| `connect.js` | **用户端** — Node.js 原生终端 WebSocket 客户端 |
| `chat.js` | **Agent 端** — 多轮对话，逐字符输入 + 固定间隔等待 |
| `type.js` | 逐字符模拟键盘输入 |
| `key.js` | 发送特殊按键（Tab/Alt+M/Esc/Ctrl+C） |
| `send.js` | 一次性发送字符串（不推荐，cbc TUI 需要逐字符） |
| `claw-client.js` | Agent 端备用连接脚本（已弃用） |
| `connect.ps1` | PowerShell WebSocket 客户端（弃用，PS 5.1 兼容性问题） |

## 双控原理

所有客户端（终端、Agent、网页）共享**同一个 node-pty 实例**的 stdin/stdout：

```
       ┌─── WS client A（你） ──→ pty.write()
user ──┤─── WS client B（我） ──→ pty.write()
       └─── HTTP polling ──────→ /snapshot（只读）

pty.onData() ──→ broadcast to ALL WS clients
```

## 已知问题

### TUI 花屏 / 多栏
- **表现**：cbc 思考时终端画面频繁刷新，出现多栏错位
- **根因**：多个 WS 客户端同时写入 PTY stdin，cbc 的 TUI 被碎片输入打乱状态机
- **没有简单锁方案**：写锁会破坏字符流的连续性（逐字符输入的必须性）
- **建议**：人 + Agent 不要同时操控

### 初始化丢帧
- **表现**：第一个客户端连接时 cbc 启动画面丢失
- **当前缓解**：ring buffer 缓存输出，新客户端 200ms 后回放
- **根因**：cbc 启动输出早于 WS 客户端监听准备完毕

### 网页端轮询闪烁
- 每 800ms `t.reset()` + `t.write()` 重绘，有可见闪烁
- 当前设计有意保持只读（避免写冲突）

## 扩展

这套桥接不限于 cbc。改一行就能换 CLI：

```javascript
// server.js 第 82 行
pty = spawn('cmd.exe', ['/c', 'cbc'], ...);
// 改成
pty = spawn('copilot', ['-p', ...], ...);
// 或
pty = spawn('claude', ['-p', ...], ...);
// 或
pty = spawn('node', ['my-cli.js'], ...);
```

每开一个端口 = 一个独立 PTY 实例，互不干扰。

## 依赖

- `node-pty` — 跨平台 PTY 创建（Windows ConPTY / Unix pty）
- `ws` — WebSocket 服务端 + 客户端
