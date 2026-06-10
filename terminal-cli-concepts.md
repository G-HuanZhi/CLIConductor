# 终端 / CLI 底层概念与 Agent 集群开发前置知识

> 面向需求：操控一个 CLI 去操控其他 CLI，跟踪每个 session，构建 agent 集群。

---

## 一、基础概念辨析

### 1. Terminal（终端）、Shell、Console、TTY 的区别

| 概念 | 是什么 | 在这个项目里的关系 |
|------|--------|-------------------|
| **Terminal（终端）** | 一个图形化窗口或设备，负责显示文字和接收键盘输入。本质是一个"显示+输入的设备模拟器" | 你的 Windows Terminal / iTerm2 / Alacritty 就是 terminal |
| **Shell** | 运行在终端里的命令解释器。接收你输入的命令，调用系统功能，返回结果 | bash / zsh / PowerShell 就是 shell |
| **Console** | 物理控制台（历史概念），现在通常 = 终端窗口 | 和 terminal 几乎同义 |
| **TTY** | 电传打字机（历史），现在是 `/dev/tty*` 设备文件，代表一个终端会话 | 每个打开的终端窗口 = 一个 tty 设备 |
| **PTY（伪终端）** | 软件模拟的终端。分为 master 端（程序控制）和 slave 端（shell 运行的地方） | **这是你控制另一个 CLI 的核心机制** |

```
[你的键盘] → [Terminal 窗口] → [PTY slave] → [Shell 进程]
                                              ↑
                              [PTY master] ← 可以在这里读写，操控 shell
```

### 2. 关键认知

- **Terminal 只是 UI**，它不执行命令，执行命令的是 Shell
- **PTY 是桥梁**，连接 Terminal UI 和 Shell 进程
- **TTY 设备文件** 是操作系统给每个终端分配的"身份证"

---

## 二、PTY（伪终端）— 操控 CLI 的核心

### PTY 是什么

PTY = Pseudo Terminal，是操作系统提供的一对虚拟设备：

```
┌──────────────┐          ┌──────────────┐
│  PTY Master   │  ←──→   │  PTY Slave   │
│  (控制端)      │  内核    │  (被控端)     │
│               │          │               │
│  GUI/CLI程序   │          │  Shell 运行    │
│  读写 master   │          │  在 slave 上   │
└──────────────┘          └──────────────┘
```

- **Master 端**：程序通过它往 slave 写入字符（模拟键盘输入），从 slave 读取输出（获取屏幕内容）
- **Slave 端**：Shell 进程的标准输入/输出/错误都连接到 slave

### 这意味着什么

**你可以写一个程序，打开一个 PTY，在 slave 端启动一个 shell（或 cbc），然后通过 master 端：**
- 向 slave 写入命令（模拟用户输入）
- 从 slave 读取输出（获取 CLI 的响应）
- 完全控制这个 CLI 实例

### PTY 在 Linux 上的体现

```bash
# 查看当前终端的 tty
$ tty
/dev/pts/3

# 查看所有 PTY slave
$ ls /dev/pts/
0  1  2  3  5

# 每个数字就是一个终端 session
```

### PTY 在 Windows 上的体现（ConPTY）

Windows 传统上没有 PTY，但 Windows 10 1809+ 引入了 **ConPTY**（Conhost Pseudo Terminal）：

- ConPTY API：`CreatePseudoConsole()`
- Windows Terminal、VS Code Terminal 都基于 ConPTY
- 允许程序像 Linux PTY 一样读写另一个控制台的输入输出

### 为什么 PTY 对 Agent 集群至关重要

```
你的主 Agent
    │
    ├── 打开 PTY-1 → slave 跑 cbc (子 agent 1)
    │                   master 端：写任务、读结果
    │
    ├── 打开 PTY-2 → slave 跑 cbc (子 agent 2)
    │                   master 端：写任务、读结果
    │
    └── 打开 PTY-3 → slave 跑 npm run dev (监控进程)
                        master 端：读日志、写控制命令
```

---

## 三、标准流：stdin / stdout / stderr

### 三个标准流

```
┌──────────┐  stdin (0)   ┌──────────┐  stdout (1)  ┌──────────┐
│  输入源    │ ──────────→ │  进程     │ ──────────→ │  输出目标  │
│ (键盘/文件) │             │  (程序)   │             │ (屏幕/文件) │
└──────────┘              └──────────┘              └──────────┘
                               │
                               │ stderr (2)
                               ↓
                          ┌──────────┐
                          │  错误输出  │
                          │ (屏幕/文件) │
                          └──────────┘
```

| 流 | 编号 | 方向 | 用途 |
|----|------|------|------|
| stdin | 0 | 进 | 程序读取输入 |
| stdout | 1 | 出 | 程序正常输出 |
| stderr | 2 | 出 | 程序错误/日志输出 |

### 重定向（对本项目非常重要）

```bash
# 把 stdout 存到文件
codebuddy --print "hello" > output.txt

# 把 stderr 也重定向到同一文件
codebuddy --print "hello" > output.txt 2>&1

# 丢弃所有输出
codebuddy --print "hello" > /dev/null 2>&1

# 管道：把 stdout 喂给下一个程序
codebuddy --print "列出所有文件" | grep ".js"

# 把一个命令的输出作为另一个命令的输入（stdin）
echo "列出所有文件" | codebuddy --print -
```

### 管道（Pipe）vs PTY

| | Pipe | PTY |
|------|------|------|
| 本质 | 单向数据通道 | 双向终端模拟 |
| 数据格式 | 原始字节流 | 包含终端控制序列 |
| 交互性 | 无（批处理） | 有（可以逐字符交互） |
| 适用场景 | `cmd1 | cmd2` | 操控交互式 CLI |
| 获取输出 | 一次性读完 | 可以持续读取 |

**对本项目的意义**：操控交互式 agent CLI（如 cbc 交互模式）必须用 PTY，不能只用 pipe。

---

## 四、Session 与进程管理

### 什么是 Session

在操作系统层面，一个 **session（会话）** 是由一个领头进程（session leader）和它创建的所有进程组成的进程组集合。

```bash
# 每个终端窗口 = 一个 session
$ ps -eo pid,sid,cmd | grep bash
12345 12345 /bin/bash          # SID = PID，说明 bash 是 session leader
12346 12345  |-- codebuddy     # 子进程，同属一个 session
```

### 关键概念

| 概念 | 说明 |
|------|------|
| **PID（进程ID）** | 每个进程的唯一标识 |
| **SID（会话ID）** | 一个会话的唯一标识，通常是 session leader 的 PID |
| **PGID（进程组ID）** | 一组相关进程的标识 |
| **Session Leader** | 创建 session 的进程（通常是 shell） |
| **TTY** | 与 session 关联的终端设备 |

### 如何获取 session 的永久索引

```bash
# 1. 查看所有终端相关进程
ps aux | grep pts

# 2. 查看某个终端的进程树
ps -t /dev/pts/3 --forest

# 3. 获取进程的 SID
ps -o pid,sid,tty,cmd -p <PID>

# 4. 查看所有 session
ps -eo pid,sid,tty,cmd | sort -k2

# 5. 用 tmux/screen 管理 session（推荐）
tmux ls                    # 列出所有 session
tmux new -s worker1         # 创建命名 session
tmux send-keys -t worker1 "ls" Enter  # 向 session 发送命令
tmux capture-pane -t worker1 -p      # 捕获 session 输出
```

### 对本项目的意义

```
Session 索引方案：

方案 A：操作系统层级
    SID + TTY → 追踪所有进程
    优点：原生，不依赖额外工具
    缺点：tty 设备号可能变化，进程死亡后索引失效

方案 B：tmux/screen 层级（推荐）
    tmux session name → 永久命名索引
    优点：命名持久，支持 detach/attach，可编程操控
    缺点：依赖 tmux

方案 C：PTY master fd
    打开 PTY 时记录 master 端的 fd
    优点：最精确的控制
    缺点：需要自己写管理代码，fd 进程内有效

方案 D：进程 PID + 自定义注册表
    启动子进程时记录 PID，维护一个注册文件
    优点：灵活
    缺点：需要自己管理生命周期
```

---

## 五、读写另一个终端的输入输出

### Linux 上直接读写 TTY 设备

```bash
# 查看哪些终端存在
ls /dev/pts/

# 向另一个终端写入（需要有权限）
echo "hello from another terminal" > /dev/pts/2

# 读取另一个终端的输出（这会竞争读取，破坏正常输出）
cat /dev/pts/2   # 不推荐，会抢走本该给那个终端的输出
```

**注意**：直接读写 `/dev/pts/N` 非常粗暴：
- 写入 = 模拟键盘输入（程序会执行）
- 读取 = 从程序的 stdout 抢数据（原始程序就读不到了）

### tmux 方式（推荐）

```bash
# 创建一个后台 session，里面运行 cbc
tmux new-session -d -s agent1 "codebuddy"

# 向 session 发送命令（模拟键盘输入）
tmux send-keys -t agent1 "列出所有文件" Enter

# 捕获 session 的当前屏幕内容
tmux capture-pane -t agent1 -p

# 附加查看（人类操作）
tmux attach -t agent1

# 关闭 session
tmux kill-session -t agent1
```

### script 命令

```bash
# 启动一个 session 并记录所有输出到文件
script -f /tmp/session1.log

# 另一个终端实时查看
tail -f /tmp/session1.log
```

---

## 六、跨进程通信（IPC）机制

在不同 agent 之间传递任务和结果，需要 IPC：

| 机制 | 适用场景 | 复杂度 |
|------|---------|--------|
| **文件系统** | 任务队列、结果存储 | 低 |
| **命名管道（FIFO）** | 实时流式通信 | 中 |
| **Unix Domain Socket** | 高性能本地通信 | 中 |
| **标准输入/输出（stdio）** | 父子进程通信 | 低 |
| **HTTP/WebSocket** | agent 间网络通信 | 中 |
| **消息队列（Redis/ZeroMQ）** | 大规模集群 | 高 |

### 对本项目的建议

```
初期（快速验证）：
    文件系统 + tmux send-keys → 简单，能看到效果

中期（可用系统）：
    Unix socket / HTTP API → 可靠，可编程

后期（完整集群）：
    消息队列 + 服务注册 → 规模化
```

---

## 七、CLI 工具如何支持"被编程操控"

### 模式对比

| 模式 | 示例 | 操控方式 |
|------|------|---------|
| **交互模式** | `codebuddy`（不加参数） | PTY + 模拟键盘输入 |
| **--print 模式** | `codebuddy --print "任务"` | 命令行参数，获取 stdout |
| **stream-json 模式** | `codebuddy --input-format stream-json --output-format stream-json` | stdin 喂 JSON，stdout 读 JSON |
| **API 模式** | `curl http://localhost:8080/chat` | HTTP 请求 |

### stream-json 模式（最佳编程操控方式）

```bash
# 启动一个可编程操控的 cbc 实例
# 通过 stdin 发送 JSON 消息，stdout 读取 JSON 响应
echo '{"type":"user","message":{"role":"user","content":"列出文件"}}' | \
  codebuddy --input-format stream-json --output-format stream-json
```

这种方式不需要 PTY，直接用管道即可管控。

---

## 八、Windows 特有问题

### ConPTY

Windows 10 1809+ 引入了 ConPTY（Pseudo Console）API：

- `CreatePseudoConsole()` → 创建伪控制台
- 类似于 Linux 的 PTY 对
- Windows Terminal、VS Code 内置终端都基于它

### PTY 在 Git Bash 上的限制

你在 Windows 上用的是 Git Bash，它运行在 MinTTY 终端上：

- MinTTY 基于 Cygwin 的 PTY 实现，不是原生 Windows ConPTY
- 有些 Windows 原生 CLI 工具在 Git Bash 的 PTY 下行为异常（如没有颜色、不能交互）
- 解决方案：使用 `winpty` 包装

```bash
# 在 Git Bash 中运行 Windows 原生交互程序
winpty python
winpty cmd
```

---

## 九、构建 Agent 集群的核心技术要素总结

基于以上概念，以下是实现"主 agent 操控多个子 agent"需要的技术：

```
┌────────────────────────────────────────────────────────┐
│                    入口层（任意输入）                      │
│  QQ Bot  │  HTML 页面  │  邮件  │  CLI  │  其他...    │
└─────────────────┬──────────────────────────────────────┘
                  │ 统一消息格式
┌─────────────────▼──────────────────────────────────────┐
│                    主 Agent（调度层）                     │
│  - 接收用户消息                                         │
│  - 分析意图，拆分为子任务                                  │
│  - 分发到合适的子 agent                                  │
│  - 汇总结果返回用户                                      │
└───────┬──────────┬──────────┬──────────┬───────────────┘
        │          │          │          │
   ┌────▼───┐ ┌───▼────┐ ┌───▼────┐ ┌───▼────┐
   │ PTY 1  │ │ PTY 2  │ │ PTY 3  │ │ PTY 4  │  ← 每子 agent一套 PTY
   │ cbc A  │ │cbc B   │ │shell   │ │IDE     │
   └────────┘ └────────┘ └────────┘ └────────┘

   Session 管理层：
   ┌────────────────────────────────────────────┐
   │  子 agent PID + SID + TTY + tmux name      │
   │  记录文件：~/.agent-cluster/sessions.json   │
   │  心跳检测 + 异常自动重启                      │
   └────────────────────────────────────────────┘
```

### 关键决策点

| 问题 | 选项 | 建议 |
|------|------|------|
| 子 agent 生命周期管理 | PTY / tmux / 直接 process spawn | tmux 最简单直观 |
| 通信协议 | stdin/stdout / socket / HTTP | HTTP API 最通用 |
| Session 索引 | PID / SID / TTY / 自定义 ID | 自定义 ID + tmux session name |
| 跨厂商兼容 | 每种 CLI 一个适配器 | **适配器模式**，统一接口 |

---

## 十、推荐学习路径

1. **立即上手**：用 tmux 手动测试向另一个 session 发送命令 → 理解操控原理
2. **理解 PTY**：读 `man pty`，用 Python `pty` 模块写一个简单的终端模拟器
3. **学习 IPC**：用 Node.js/Python 实现两个进程通过 Unix socket 通信
4. **设计架构**：根据本项目和实验记录，画出 agent 集群的模块图

### 推荐工具库

| 语言 | PTY 库 | tmux 操控库 |
|------|--------|------------|
| Node.js | `node-pty` | 调用 tmux 命令 |
| Python | `pty` / `pexpect` | `libtmux` |
| Go | `github.com/creack/pty` | 调用 tmux 命令 |
| Rust | `portable-pty` | 调用 tmux 命令 |

---

> 下一步：动手实验。  
> - 用 `tmux` 创建 session，用 `send-keys` 操控  
> - 用 `node-pty` 创建一个 PTY 并启动子进程  
> - 用文件系统实现简单的任务队列
