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
  model: string | null;
  permissionMode: string | null;
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
    model: null,
    permissionMode: null,
  };

  setupWorkerIO(w, child);
  workers.set(id, w);
  broadcast({ type: "worker.spawned", workerId: id, name, status: "idle" });
  return w;
}

function setupWorkerIO(w: WorkerState, child: ChildProcess) {
  const rl = createInterface({ input: child.stdout! });

  rl.on("line", (line: string) => {
    let event: any;
    try { event = JSON.parse(line); }
    catch { return; }

    const t = event.type;

    if (t === "system" && event.subtype === "init") {
      w.sessionId = event.session_id;
    }

    if (t === "assistant") {
      const blocks = event.message?.content ?? [];
      for (const b of blocks) {
        if (b.type === "text") w.history.push({ role: "assistant", content: b.text });
        if (b.type === "thinking") w.history.push({ role: "thinking", content: b.thinking });
        if (b.type === "tool_use") w.history.push({ role: "tool", content: `${b.name}(${JSON.stringify(b.input)})` });
      }
    }

    if (t === "result") {
      w.status = event.is_error ? "error" : "done";
      broadcast({
        type: "worker.result",
        workerId: w.id,
        status: w.status,
        result: event.result,
        sessionId: w.sessionId,
        history: w.history,
      });
      w.status = "idle";
      return;
    }

    broadcast({ type: "worker.stream", workerId: w.id, event });
  });

  child.on("close", (code) => {
    // 如果进程已被 restart 替换，忽略陈旧事件
    if (w.process !== child) return;
    if (w.status === "idle" || w.status === "running") {
      w.status = "error";
    }
  });
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

function restartWorker(workerId: string): string | null {
  const w = workers.get(workerId);
  if (!w) return "Worker not found";

  const sessionId = w.sessionId;

  // 停旧进程
  w.process?.kill();

  // 起新进程（保留 session 以保留对话历史）
  const args = ["-p", "--output-format", "stream-json", "--input-format", "stream-json", "-y"];
  if (sessionId) args.push("--resume", sessionId);

  const child = spawn("cbc", args, {
    stdio: ["pipe", "pipe", "pipe"],
    shell: true,
  });

  w.process = child;
  w.status = "idle";

  // 重新挂载 stdout reader
  setupWorkerIO(w, child);

  broadcast({
    type: "worker.restarted",
    workerId,
    name: w.name,
    status: "idle",
    sessionId,
  });
  return null;
}

function respawnWorker(workerId: string, extraArgs: string[] = []): string | null {
  const w = workers.get(workerId);
  if (!w) return "Worker not found";

  const sessionId = w.sessionId;

  w.process?.kill();

  const args = ["-p", "--output-format", "stream-json", "--input-format", "stream-json", "-y"];
  if (sessionId) args.push("--resume", sessionId);
  args.push(...extraArgs);

  const child = spawn("cbc", args, {
    stdio: ["pipe", "pipe", "pipe"],
    shell: true,
  });

  w.process = child;
  w.status = "idle";

  setupWorkerIO(w, child);

  broadcast({
    type: "worker.reconfigured",
    workerId,
    name: w.name,
    status: "idle",
    sessionId,
  });
  return null;
}

function branchWorker(workerId: string, name?: string): WorkerState | string {
  const w = workers.get(workerId);
  if (!w) return "Worker not found";
  if (!w.sessionId) return "Worker has no session yet";

  const newId = `worker-${nextId++}`;
  const newName = name || `${w.name}-branch`;

  const args = ["-p", "--output-format", "stream-json", "--input-format", "stream-json", "-y",
    "--resume", w.sessionId, "--fork-session"];
  if (w.model) args.push("--model", w.model);
  if (w.permissionMode) args.push("--permission-mode", w.permissionMode);

  const child = spawn("cbc", args, {
    stdio: ["pipe", "pipe", "pipe"],
    shell: true,
  });

  const newW: WorkerState = {
    id: newId, name: newName,
    status: "idle",
    process: child,
    sessionId: null,
    history: [],
    model: w.model,
    permissionMode: w.permissionMode,
  };

  setupWorkerIO(newW, child);
  workers.set(newId, newW);

  broadcast({
    type: "worker.spawned",
    workerId: newId,
    name: newName,
    status: "idle",
    parentWorkerId: workerId,
    parentSessionId: w.sessionId,
  });
  return newW;
}

function renameWorker(workerId: string, newName: string): string | null {
  const w = workers.get(workerId);
  if (!w) return "Worker not found";

  const oldName = w.name;
  w.name = newName;

  broadcast({
    type: "worker.renamed",
    workerId,
    oldName,
    newName,
  });
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
    model: w.model, permissionMode: w.permissionMode,
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

app.post("/api/worker/:id/restart", (req, res) => {
  const err = restartWorker(req.params.id);
  if (err) { res.status(400).json({ error: err }); return; }
  res.json({ workerId: req.params.id, status: "restarted" });
});

app.post("/api/worker/:id/switch-model", (req, res) => {
  const { model } = req.body;
  if (!model) { res.status(400).json({ error: "model is required" }); return; }
  const err = respawnWorker(req.params.id, ["--model", model]);
  if (err) { res.status(400).json({ error: err }); return; }
  const w = workers.get(req.params.id)!;
  w.model = model;
  res.json({ workerId: req.params.id, model, status: "switched" });
});

app.post("/api/worker/:id/switch-mode", (req, res) => {
  const { permissionMode } = req.body;
  if (!permissionMode) { res.status(400).json({ error: "permissionMode is required" }); return; }
  const err = respawnWorker(req.params.id, ["--permission-mode", permissionMode]);
  if (err) { res.status(400).json({ error: err }); return; }
  const w = workers.get(req.params.id)!;
  w.permissionMode = permissionMode;
  res.json({ workerId: req.params.id, permissionMode, status: "switched" });
});

app.post("/api/worker/:id/branch", (req, res) => {
  const { name } = req.body;
  const result = branchWorker(req.params.id, name);
  if (typeof result === "string") { res.status(400).json({ error: result }); return; }
  res.json({ workerId: result.id, name: result.name, status: "idle", parentWorkerId: req.params.id });
});

app.post("/api/worker/:id/rename", (req, res) => {
  const { name } = req.body;
  if (!name) { res.status(400).json({ error: "name is required" }); return; }
  const err = renameWorker(req.params.id, name);
  if (err) { res.status(400).json({ error: err }); return; }
  res.json({ workerId: req.params.id, name, status: "renamed" });
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
