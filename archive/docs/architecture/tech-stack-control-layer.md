# Shell · child_process · Node.js 关系说明

> 面向需求：用代码操控任意 CLI 进程的启动、输入、输出、终止。

---

## 一句话关系

```
你在终端敲命令   ←→   Shell (bash/PowerShell)
Node.js 代码操控  ←→   child_process 模块
它们做的是同一件事：启动进程、收发数据、管理生命周期。
```

**Shell 给人用，child_process 给代码用。底层都是 OS 的原生进程 API。**

---

## 三层关系图

```
┌──────────────────────────────────────────────┐
│              你的 Agent 集群代码               │
│              (Node.js / TypeScript)           │
│                                              │
│   import { spawn } from 'child_process';     │
│   const cbc = spawn('codebuddy', ['-p', ...])│
│   cbc.stdout.on('data', ...)                 │
│   cbc.on('exit', ...)                        │
│   cbc.kill()                                 │
└──────────────────┬───────────────────────────┘
                   │ Node.js API 调用
┌──────────────────▼───────────────────────────┐
│           child_process 模块 (Node.js 内置)    │
│                                              │
│   封装了 OS 的进程管理 API，提供了：              │
│   · spawn()   → 启动进程                      │
│   · .stdout   → 读进程输出                     │
│   · .stdin    → 写进程输入                     │
│   · .pid      → 获取进程 ID                   │
│   · .kill()   → 终止进程                      │
│   · 'exit'    → 进程退出事件                   │
└──────────────────┬───────────────────────────┘
                   │ 底层调用 OS API
┌──────────────────▼───────────────────────────┐
│           操作系统 (Windows / Linux / macOS)    │
│                                              │
│   fork() + exec()      (Linux/macOS)         │
│   CreateProcess()      (Windows)             │
│                                              │
│   不管上层是 Shell 还是 Node.js，最终都是调用    │
│   这些 OS 原语来创建和管理进程                   │
└──────────────────────────────────────────────┘
```

---

## 概念对照

| 概念 | 是什么 | 在本项目中的角色 |
|------|--------|-----------------|
| **Shell** | 命令行解释器（bash/PowerShell/cmd） | Phase 1 手动实验用，快速验证想法 |
| **child_process** | Node.js 内置模块，代码操控进程的 API | Phase 2 起的主力，用代码替代手动操作 |
| **Node.js** | JavaScript 运行时，运行 child_process 代码的引擎 | 整个控制程序的技术栈 |
| **OS 进程 API** | fork/exec/CreateProcess，操作系统最底层的进程管理能力 | 一切的上游，Shell 和 child_process 都在调它 |

---

## 为什么说"Shell 方案"和"child_process 方案"是一回事

之前在 Phase 1 中用 shell 命令做的测试：

```bash
# Shell 方式（手动）
codebuddy -p "hello" > /tmp/out.txt 2>&1 &
PID=$!
kill -0 $PID && echo "running"
kill $PID
```

等价于 Phase 2 的 Node.js 代码：

```javascript
// child_process 方式（代码）
const { spawn } = require('child_process');
const cbc = spawn('codebuddy', ['-p', 'hello']);
cbc.stdout.pipe(fs.createWriteStream('/tmp/out.txt'));
const pid = cbc.pid;          // 相当于 $!
cbc.killed || cbc.exitCode;   // 相当于 kill -0
cbc.kill();                   // 相当于 kill
```

**同一个能力，两种调用方式。** 实验用 Shell 是因为写起来快；工程实现用 child_process 是因为可以写逻辑（条件判断、循环、错误处理、JSON 解析）。

---

## 与 PTY 的区别

```
Shell / child_process.spawn  →  纯进程管理：启动 → 传参数 → 读 stdout
PTY                           →  终端模拟：启动 → 模拟键盘 → 读屏幕 AN��I
```

| | child_process.spawn | PTY (node-pty) |
|--|-------------------|----------------|
| 机制 | 传命令行参数 | 模拟键盘输入 |
| 输出 | 干净的 stdout 字节流 | 带 ANSI 控制序列的终端画面 |
| 适用范围 | 支持 `-p --stream-json` 的 CLI | **所有** CLI（包括纯交互式） |
| 复杂度 | 低 | 高 |
| 本项目策略 | **主力** | 备选 |

---

## 一句话总结

> **Shell 是手动的，child_process 是自动的。本项目的目标就是把 Phase 1 中手动壳做的实验，用 child_process 写成自动化的代码。**
