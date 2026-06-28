# CLIConductor 技术栈选型分析

> 分析日期：2026-06-27
> 目标：选定 CLIConductor MVP 的开发语言和框架

---

## 一、项目需求梳理

CLIConductor 需要这些底层能力：

| 需求 | 描述 |
|------|------|
| 子进程管理 | spawn CLI 进程（cbc），读取 stdout 行式输出，写入 stdin，终止进程 |
| 实时流 | 逐行读取子进程 stdout JSON，实时推送给多个 WebSocket 客户端 |
| HTTP API | 4-5 个 REST 端点（spawn/list/task/kill） |
| WebSocket | 双向通道，Dashboard 和 Agent 同时连接 |
| 文件存储 | Session 数据和对话历史存本地文件 |
| 运行平台 | Windows 为主 |

---

## 二、方案 A：Python + FastAPI + uvicorn

### 2.1 进程管理

```python
import asyncio
import json

# 启动 cbc 子进程
process = await asyncio.create_subprocess_exec(
    "cbc",
    "-p",
    "--output-format", "stream-json",
    "--input-format", "stream-json",
    "-y",
    stdout=asyncio.subprocess.PIPE,
    stdin=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.STDOUT,
)

# 发送消息
msg = json.dumps({
    "type": "user",
    "message": {"role": "user", "content": [{"type": "text", "text": "任务内容"}]}
})
process.stdin.write((msg + "\n").encode())
await process.stdin.drain()

# 逐行读取 stdout
async for line in process.stdout:
    line_str = line.decode("utf-8", errors="replace").rstrip("\n")
    if not line_str:
        continue
    event = json.loads(line_str)
    # 处理 event...
    if event.get("type") == "result":
        break  # 或继续等下一轮

# 终止
process.kill()
await process.wait()
```

**评价**：`async for` 逐行读最自然，stdin 写清楚，整体流程像一个管道。

### 2.2 HTTP + WebSocket

```python
from fastapi import FastAPI, WebSocket

app = FastAPI()
clients: list[WebSocket] = []

@app.post("/api/spawn")
async def spawn_worker(name: str):
    # 创建 Worker 逻辑
    return {"workerId": "worker-1", "status": "created"}

@app.get("/api/list")
async def list_workers():
    return {"workers": [...]}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.append(ws)
    try:
        while True:
            await ws.receive_text()
    except:
        clients.remove(ws)

# 广播事件
async def broadcast(event):
    for ws in clients:
        await ws.send_json(event)
```

**评价**：HTTP 和 WS 在同一框架里，不需要额外库组合。事件广播很简单。

### 2.3 依赖

```
fastapi
uvicorn
pydantic          # 请求校验，和 FastAPI 配套
```

### 2.4 Windows 注意事项

- Python 3.8+ 在 Windows 上默认使用 `ProactorEventLoop`，子进程直接可用
- `process.kill()` 在 Windows 上等效于 `TerminateProcess`，没有 SIGTERM
- 如果 cbc 以 `cmd /c` 方式启动，kill 父进程不会杀子进程

### 2.5 单项评分

| 维度 | 分 |
|------|:--:|
| 进程管理 | 9 |
| HTTP+WS 一体 | 9 |
| 类型安全 | 7 (mypy 可选) |
| 参考代码 | 9 (DionysusC ~2100 行) |
| Windows 兼容 | 7 |
| 学习曲线 | 6 |
| 开发速度 | 8 |

---

## 三、方案 B：Node.js + Express + ws (TypeScript)

### 3.1 进程管理

```typescript
import { spawn } from "child_process";
import { createInterface } from "readline";

// 启动 cbc 子进程
const child = spawn("cbc", [
  "-p",
  "--output-format", "stream-json",
  "--input-format", "stream-json",
  "-y",
], {
  stdio: ["pipe", "pipe", "pipe"],
  shell: true,
});

// 发送消息
const msg = JSON.stringify({
  type: "user",
  message: { role: "user", content: [{ type: "text", text: "任务内容" }] },
});
child.stdin!.write(msg + "\n");

// 逐行读取 stdout
const rl = createInterface({ input: child.stdout! });
rl.on("line", (line: string) => {
  const event = JSON.parse(line);
  // 处理 event...
});

// 终止
child.kill();
```

**评价**：`readline` 模块可靠，回调式写法需要管理清理。Windows 上 `shell: true` 处理 `.cmd` 执行。

### 3.2 HTTP + WebSocket

```typescript
import express from "express";
import { WebSocketServer } from "ws";
import http from "http";

const app = express();
const server = http.createServer(app);

app.post("/api/spawn", (req, res) => {
  res.json({ workerId: "worker-1", status: "created" });
});

app.get("/api/list", (req, res) => {
  res.json({ workers: [] });
});

const wss = new WebSocketServer({ server });
wss.on("connection", (ws) => {
  ws.on("message", (data) => { /* ... */ });
});

// 广播事件
function broadcast(event: object) {
  const msg = JSON.stringify(event);
  wss.clients.forEach((c) => c.send(msg));
}

server.listen(8765);
```

**评价**：HTTP 和 WS 是两个组件需要手动集成，代码量稍多，但逻辑清晰。

### 3.3 依赖

```
express
ws
tsx            # 零配置运行 TypeScript
typescript
@types/express
@types/ws
```

### 3.4 Windows 注意事项

- `child_process.spawn` 在 Windows 上最成熟，Node.js 官方一手支持
- `.cmd` / `.bat` 文件需 `shell: true` 才能执行
- 用 `tree-kill` 包可以杀进程树（npm 上）

### 3.5 单项评分

| 维度 | 分 |
|------|:--:|
| 进程管理 | 8 |
| HTTP+WS 一体 | 6 |
| 类型安全 | 9 (TypeScript) |
| 参考代码 | 4 (实验脚本) |
| Windows 兼容 | 9 |
| 学习曲线 | 7 |
| 开发速度 | 8 |

---

## 四、方案 C：Go + 标准库 + gorilla/websocket

### 4.1 进程管理

```go
import (
    "bufio"
    "encoding/json"
    "os/exec"
)

// 启动 cbc 子进程
cmd := exec.Command("cbc",
    "-p",
    "--output-format", "stream-json",
    "--input-format", "stream-json",
    "-y",
)
cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true} // Windows

stdin, _ := cmd.StdinPipe()
stdout, _ := cmd.StdoutPipe()
cmd.Start()

// 发送消息
msg := `{"type":"user","message":{"role":"user","content":[{"type":"text","text":"任务"}]}}`
stdin.Write([]byte(msg + "\n"))

// 逐行读取
scanner := bufio.NewScanner(stdout)
for scanner.Scan() {
    line := scanner.Text()
    var event map[string]interface{}
    json.Unmarshal([]byte(line), &event)
    // 处理 event...
}

// 终止
cmd.Process.Kill()
```

**评价**：`bufio.Scanner` 逐行读很自然。Windows 需要 `HideWindow` 避免弹出 cmd 窗口。

### 4.2 HTTP + WebSocket

```go
import (
    "net/http"
    "github.com/gorilla/websocket"
)

var upgrader = websocket.Upgrader{}
var clients = make(map[*websocket.Conn]bool)

http.HandleFunc("/api/spawn", func(w http.ResponseWriter, r *http.Request) {
    // ...
})
http.HandleFunc("/ws", func(w http.ResponseWriter, r *http.Request) {
    conn, _ := upgrader.Upgrade(w, r, nil)
    clients[conn] = true
})

func broadcast(event interface{}) {
    for conn := range clients {
        conn.WriteJSON(event)
    }
}

http.ListenAndServe(":8765", nil)
```

**评价**：标准库 HTTP 路由略弱，没有路径参数支持；需 gorilla/mux 或 chi 补充。

### 4.3 单项评分

| 维度 | 分 |
|------|:--:|
| 进程管理 | 8 |
| HTTP+WS 一体 | 7 |
| 类型安全 | 9 |
| 参考代码 | 0 |
| Windows 兼容 | 6 (需手动处理) |
| 学习曲线 | 5 |
| 开发速度 | 5 |

---

## 五、方案 D：Rust + axum

### 5.1 进程管理

```rust
use tokio::process::Command;
use tokio::io::{AsyncBufReadExt, BufReader};

let mut child = Command::new("cbc")
    .args(["-p", "--output-format", "stream-json", ...])
    .stdout(Stdio::piped())
    .stdin(Stdio::piped())
    .spawn()?;

let mut stdin = child.stdin.take().unwrap();
stdin.write_all(b"message\n").await?;

let stdout = child.stdout.take().unwrap();
let mut reader = BufReader::new(stdout).lines();
while let Some(line) = reader.next_line().await? {
    let event: Value = serde_json::from_str(&line)?;
}

child.kill().await?;
```

**评价**：tokio 生态成熟，async 逐行读很干净。但类型声明、错误处理、生命周期管理代码量大。

### 5.2 HTTP + WebSocket

```rust
use axum::{Router, routing::{get, post}};
use axum::extract::ws::{WebSocket, WebSocketUpgrade};

let app = Router::new()
    .route("/api/spawn", post(spawn_worker))
    .route("/api/list", get(list_workers))
    .route("/ws", get(ws_handler));

async fn ws_handler(ws: WebSocketUpgrade) -> impl IntoResponse {
    ws.on_upgrade(|socket| handle_socket(socket))
}
```

**评价**：axum 的路由和 WS 支持很好，类型安全出色。但编译时间长，不适合快速迭代。

### 5.3 单项评分

| 维度 | 分 |
|------|:--:|
| 进程管理 | 7 (代码量大) |
| HTTP+WS 一体 | 8 |
| 类型安全 | 10 |
| 参考代码 | 0 |
| Windows 兼容 | 5 |
| 学习曲线 | 2 |
| 开发速度 | 3 |

---

## 六、综合评分

| 维度 | Python+FastAPI | Node+Express+ws | Go | Rust |
|------|:--:|:--:|:--:|:--:|
| 进程管理 | 9 | 8 | 8 | 7 |
| HTTP+WS 一体 | 9 | 6 | 7 | 8 |
| 类型安全 | 7 | 9 | 9 | 10 |
| 参考代码 | 9 | 4 | 0 | 0 |
| Windows 兼容 | 7 | 9 | 6 | 5 |
| 学习曲线 | 6 | 7 | 5 | 2 |
| 开发速度 | 8 | 8 | 5 | 3 |
| 单文件运行 | ✓ | ✓ | ✓ | ✗ |
| **加权总分** | **7.8** | **7.4** | **5.7** | **5.0** |

---

## 七、结论

### Python + FastAPI 综合最适合

| 优势 | 实际影响 |
|------|---------|
| 进程 `async for` 管道 | 实时流处理最自然 |
| HTTP+WS 在一个框架 | 少选库，少集成代码 |
| DionysusC 是完整参考 | 进程管理/事件管道/session 都可以直接对，不用翻译 |
| `python main.py` 零配置启动 | 开发迭代快 |

| 风险 | 对策 |
|------|------|
| Windows 子进程信号 | 只用 kill/terminate，不用信号 |
| asyncio 学习成本 | DionysusC 就是教材 |

### Node.js + Express 是不错的二号方案

如果用户对 Python 完全陌生但对 JavaScript 更熟，选这个也不差。差异主要在参考代码多寡和框架集成度，核心能力都能打。

### Go 和 Rust 现阶段不推荐

对于"开发经验有限 + 需要快速 MVP"的组合来说，这两的编译流程和类型系统是额外的阻力，不是助力。

---

## 八、后续验证

选技术栈后，第一个 milestone 应做两件事：
1. 搭最小骨架（HTTP Server + 一个 spawn endpoint）
2. 验证 cbc 子进程完整生命周期（spawn → 写 stdin → 读 stdout → 收到 result → kill）
