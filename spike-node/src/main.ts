/** CLIConductor Spike — Node.js + Express + ws
 *
 * 完整链路：HTTP API → Worker spawn → cbc stdout 流 → WebSocket 广播
 */

import express from "express";
import http from "http";
import { readFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { WebSocketServer, WebSocket } from "ws";
import { spawn, ChildProcess } from "child_process";
import { createInterface } from "readline";

const __dirname = dirname(fileURLToPath(import.meta.url));

// ────────────────────────────────────────────
// Worker
// ────────────────────────────────────────────

interface WorkerState {
  id: string;
  name: string;
  status: "idle" | "running" | "done" | "error";
  process: ChildProcess | null;
  sessionId: string | null;
  history: any[];
}

const workers = new Map<string, WorkerState>();
let nextId = 1;

function createWorker(name: string): WorkerState {
  const id = `worker-${nextId++}`;

  const child = spawn("cbc", [
    "-p",
    "--output-format", "stream-json",
    "--input-format", "stream-json",
    "-y",
  ], {
    stdio: ["pipe", "pipe", "pipe"],
    shell: true,
  });

  const w: WorkerState = {
    id, name,
    status: "idle",
    process: child,
    sessionId: null,
    history: [],
  };

  const rl = createInterface({ input: child.stdout! });

  rl.on("line", (line: string) => {
    let event: any;
    try { event = JSON.parse(line); }
    catch { return; }

    const t = event.type;

    // 提取 session_id
    if (t === "system" && event.subtype === "init") {
      w.sessionId = event.session_id;
    }

    // 收集对话历史
    if (t === "assistant") {
      const blocks = event.message?.content ?? [];
      for (const b of blocks) {
        if (b.type === "text") w.history.push({ role: "assistant", content: b.text });
        if (b.type === "thinking") w.history.push({ role: "thinking", content: b.thinking });
        if (b.type === "tool_use") w.history.push({ role: "tool", content: `${b.name}(${JSON.stringify(b.input)})` });
      }
    }

    // 任务完成
    if (t === "result") {
      w.status = event.is_error ? "error" : "done";
      broadcast({
        type: "worker.result",
        workerId: id,
        status: w.status,
        result: event.result,
        sessionId: w.sessionId,
        history: w.history,
      });
      // 重置为 idle，准备下一轮（不 return，继续等 stdout）
      w.status = "idle";
      return;
    }

    // 推送给所有客户端
    broadcast({ type: "worker.stream", workerId: id, event });
  });

  child.on("close", (code) => {
    if (w.status === "idle" || w.status === "running") {
      w.status = "error";
    }
  });

  workers.set(id, w);
  broadcast({ type: "worker.spawned", workerId: id, name, status: "idle" });
  return w;
}

// ────────────────────────────────────────────
// Task dispatch
// ────────────────────────────────────────────

function sendTask(workerId: string, text: string): string | null {
  const w = workers.get(workerId);
  if (!w) return "Worker not found";
  if (!w.process || w.process.killed) return "Worker process dead";

  w.status = "running";
  w.history.push({ role: "user", content: text });

  const msg = JSON.stringify({
    type: "user",
    message: {
      role: "user",
      content: [{ type: "text", text }],
    },
  });
  w.process.stdin!.write(msg + "\n");

  broadcast({ type: "worker.status", workerId, status: "running" });
  return null;
}

function killWorker(workerId: string): string | null {
  const w = workers.get(workerId);
  if (!w) return "Worker not found";
  w.process?.kill();
  workers.delete(workerId);
  broadcast({ type: "worker.destroyed", workerId });
  return null;
}

// ────────────────────────────────────────────
// WebSocket broadcast
// ────────────────────────────────────────────

const wss = new WebSocketServer({ noServer: true });

const clients = new Set<WebSocket>();

wss.on("connection", (ws) => {
  clients.add(ws);
  ws.on("close", () => clients.delete(ws));
});

function broadcast(data: object) {
  const msg = JSON.stringify(data);
  for (const c of clients) {
    if (c.readyState === WebSocket.OPEN) c.send(msg);
  }
}

// ────────────────────────────────────────────
// HTTP Server
// ────────────────────────────────────────────

const app = express();
app.use(express.json());

// Dashboard - serve from file
const dashboardHtml = readFileSync(join(__dirname, "..", "public", "index.html"), "utf-8");

app.get("/", (_req, res) => {
  res.type("html").send(dashboardHtml);
});

// API
app.post("/api/spawn", (_req, res) => {
  const { name = "default" } = _req.body;
  const w = createWorker(name);
  res.json({ workerId: w.id, name: w.name, status: w.status });
});

app.get("/api/list", (_req, res) => {
  const list = [...workers.values()].map(w => ({
    workerId: w.id, name: w.name, status: w.status, sessionId: w.sessionId,
  }));
  res.json({ workers: list });
});

app.post("/api/task", (_req, res) => {
  const { workerId, text } = _req.body;
  const err = sendTask(workerId, text);
  if (err) { res.status(400).json({ error: err }); return; }
  res.json({ workerId, status: "running" });
});

app.post("/api/kill/:id", (req, res) => {
  const err = killWorker(req.params.id);
  if (err) { res.status(400).json({ error: err }); return; }
  res.json({ workerId: req.params.id, status: "killed" });
});

// HTTP + WS on same port
const server = http.createServer(app);
server.on("upgrade", (req, socket, head) => {
  if (req.url === "/ws") {
    wss.handleUpgrade(req, socket, head, (ws) => wss.emit("connection", ws, req));
  }
});

const PORT = 8766;
server.listen(PORT, () => {
  console.log(`\n  CLIConductor Spike (Node.js) → http://localhost:${PORT}\n`);
});
