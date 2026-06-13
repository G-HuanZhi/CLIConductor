# 通用 CLI 进程控制方案

> 利用操作系统原语，在 Shell/Node.js 层面统一管理任意 CLI 工具的后台生命周期。不依赖 CLI 自身的 --bg/ps/logs/attach/kill。

---

## 一、核心思路

不依赖 CLI 工具自身的后台功能（这些功能每个工具都不一样，甚至很多没有），而是**上移一层**到 OS 进程管理：

```
┌─────────────────────────────────────────┐
│          你的控制程序（Node.js）           │
│  child_process.spawn / fork / exec      │
│  → PID 追踪 → stdout/stderr 捕获         │
│  → exit 监听 → kill 信号发送              │
└──────────┬─────────────┬────────────────┘
           │             │
    ┌──────▼───┐   ┌─────▼──────┐
    │ CLI A    │   │ CLI B      │  ← 任何 CLI
    │ 进程实例  │   │ 进程实例    │     不需要它支持 --bg
    └──────────┘   └────────────┘
```

**一句话**：操作系统就是你的进程管理器，你不需要每个 CLI 各自实现一套。

---

## 二、Shell 原语对照表

这是所有方案的基础——无论你用 bash、PowerShell 还是 Node.js，本质都是调用这些 OS 原语：

| 操作 | Bash | PowerShell | Node.js |
|------|------|-----------|---------|
| 后台启动 | `cmd &` | `Start-Process` | `child_process.spawn()` |
| 获取 PID | `$!` | `$proc.Id` | `child.pid` |
| 检查存活 | `kill -0 <pid>` | `Get-Process -Id <pid>` | `child.killed` / `child.exitCode` |
| 终止进程 | `kill <pid>` | `Stop-Process -Id <pid>` | `child.kill()` |
| 等待退出 | `wait <pid>` | `Wait-Process` | `child.on('exit')` |
| 捕获 stdout | `> file` | `-RedirectStandardOutput` | `child.stdout.on('data')` |
| 捕获 stderr | `2> file` | `-RedirectStandardError` | `child.stderr.on('data')` |
| 退出码 | `$?` | `$LASTEXITCODE` | `exitCode` |

---

## 三、最小可行代码（Node.js）

```typescript
import { spawn } from 'child_process';
import fs from 'fs';

interface WorkerInstance {
  pid: number;
  name: string;
  cmd: string;
  args: string[];
  process: ReturnType<typeof spawn>;
  outputFile: string;
}

class ProcessManager {
  private workers = new Map<string, WorkerInstance>();

  /** 启动一个 CLI Worker，返回 Worker ID */
  spawn(name: string, cmd: string, args: string[]): string {
    const id = `${name}-${Date.now()}`;
    const outputFile = `./sessions/${id}.log`;

    const child = spawn(cmd, args, {
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    const logStream = fs.createWriteStream(outputFile);
    child.stdout.pipe(logStream);
    child.stderr.pipe(logStream);

    child.on('exit', (code) => {
      console.log(`[${id}] exited with code ${code}`);
    });

    this.workers.set(id, {
      pid: child.pid!,
      name,
      cmd,
      args,
      process: child,
      outputFile,
    });

    return id;
  }

  /** 向 Worker 发送输入 */
  send(id: string, data: string): void {
    this.workers.get(id)?.process.stdin?.write(data);
  }

  /** 检查 Worker 是否存活 */
  isAlive(id: string): boolean {
    try {
      const w = this.workers.get(id);
      if (!w) return false;
      process.kill(w.pid, 0);  // 信号 0 不杀进程，只检查
      return true;
    } catch {
      return false;
    }
  }

  /** 终止 Worker */
  kill(id: string): void {
    this.workers.get(id)?.process.kill();
  }

  /** 列出所有 Worker */
  list(): { id: string; pid: number; name: string; alive: boolean }[] {
    return [...this.workers.entries()].map(([id, w]) => ({
      id,
      pid: w.pid,
      name: w.name,
      alive: this.isAlive(id),
    }));
  }

  /** 等待 Worker 完成并获取输出 */
  async waitFor(id: string): Promise<{ exitCode: number; output: string }> {
    const w = this.workers.get(id);
    if (!w) throw new Error(`Worker ${id} not found`);

    return new Promise((resolve) => {
      w.process.on('exit', (code) => {
        const output = fs.readFileSync(w.outputFile, 'utf-8');
        resolve({ exitCode: code ?? -1, output });
      });
    });
  }
}
```

---

## 四、对 CBC（CodeBuddy Code）的适配

CBC 已经支持 `--resume <session_id>`，我们只需在 shell 层面补充 PS/KILL/LOGS：

```
Shell 层提供的能力        CBC 自身的能力
─────────────────        ──────────────
启动进程 (spawn)          stream-json 通信
PID 追踪 (ps)             无需额外支持
杀进程 (kill)             无（shell 提供）
捕获输出 (logs)           stream-json 流
检查存活 (status)         进程信号检测
多轮对话                  --resume <session_id>
```

**关键**：CBC 的 `--bg` 功能我们**不需要用**。shell 层已经覆盖了进程管理。

---

## 五、对 Copilot CLI 的适配

Copilot 完全没有后台进程管理命令，但 shell 层弥补了这个缺口：

```
Shell 层提供的能力        Copilot 自身的能力
─────────────────        ──────────────────
启动进程 (spawn)          -p 非交互模式
PID 追踪 (ps)             ❌ 无（shell 提供）
杀进程 (kill)             ❌ 无（shell 提供）
捕获输出 (logs)           --output-format json
检查存活 (status)         进程信号检测
多轮对话                  --continue / --resume
```

有了 shell 层控制，Copilot 和 CBC 在适配器层面**接口统一**，差异仅在于：
- 调用参数不同（`-p --silent --yolo` vs `-p --input-format stream-json`）
- Session ID 获取方式不同（JSON 字段名不同）
- Resume 参数不同（`--continue` vs `--resume`）

---

## 六、跨平台能力矩阵

| | Bash (Git Bash) | PowerShell | Node.js |
|--|----------------|-----------|---------|
| Windows | ✅ (Git Bash 内) | ✅ (原生) | ✅ (首选) |
| macOS | ✅ | ✅ (需安装) | ✅ |
| Linux | ✅ | ✅ (需安装) | ✅ |

Node.js child_process 是最推荐的——跨平台统一 API，无需依赖特定 shell。
