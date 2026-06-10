# Agent 集群架构方案

> 目标：通过一个主 Agent 与用户交互，操控管理多个 CLI/IDE，实现 Agent 集群。
> 原则：模块化、跨厂商通用、session 可追踪。

---

## 一、总体架构

```
                         用户
                          │
          ┌───────┬───────┼───────┬───────┐
          │       │       │       │       │
       ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐
       │ QQ  │ │微信 │ │Web  │ │邮件 │ │CLI  │  ← 入口层
       │ Bot │ │ Bot │ │页面 │ │接收 │ │直接 │
       └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘
          │       │       │       │       │
          └───────┴───────┼───────┴───────┘
                          │
                    ┌─────▼─────┐
                    │  消息网关   │  ← 统一消息格式 + 认证
                    │  (Router)  │
                    └─────┬─────┘
                          │
                    ┌─────▼─────┐
                    │  主 Agent  │  ← 意图分析 + 任务拆分
                    │ (Brain)   │      + 上下文管理 + 结果汇总
                    └─────┬─────┘
                          │
                    ┌─────▼─────┐
                    │  调度器     │  ← 子任务分配 + 负载均衡
                    │ (Scheduler)│
                    └─────┬─────┘
                          │
          ┌───────┬───────┼───────┬───────┐
          │       │       │       │       │
     ┌────▼──┐┌───▼───┐┌──▼────┐┌──▼────┐
     │CBC    ││Claude ││Aider  ││...... │  ← Agent 适配器层
     │Adapter││Adapter││Adapter││Adapter│     (每种 CLI 一套)
     └────┬──┘└───┬───┘└──┬────┘└──┬────┘
          │       │       │       │
          │       │       │       │
    ┌─────▼───────▼───────▼───────▼─────┐
    │          Session 管理器            │
    │  ┌──────┐ ┌──────┐ ┌──────┐      │
    │  │PTY 1 │ │PTY 2 │ │PTY 3 │ ...  │
    │  │cbc A │ │cbc B │ │shell │      │
    │  └──────┘ └──────┘ └──────┘      │
    │  session.json 索引 + 心跳监控      │
    └───────────────────────────────────┘
```

---

## 二、各层详细设计

### 2.1 入口层（Input Layer）

**目标**：支持任意渠道与主 Agent 对话，所有渠道共享同一份对话上下文。

```
入口层 → 消息网关 → 主 Agent
                ↑
          统一消息格式：
          {
            "id": "uuid",
            "userId": "user_001",
            "channel": "qq|wechat|web|email|cli",
            "content": "帮我重构 auth 模块",
            "timestamp": "2026-06-10T10:00:00Z",
            "replyTo": "msg_id_to_reply",   // 引用回复
            "attachments": [...],
            "context": { ... }              // 频道特定上下文
          }
```

| 渠道 | 实现方式 | 复杂度 | 优先级 |
|------|---------|--------|--------|
| CLI 直接 | stdin/stdout | 极低 | P0（立即可用） |
| Web 页面 | 本地 HTTP + WebSocket | 低 | P1 |
| QQ | QQ Bot SDK（go-cqhttp / 官方 API） | 中 | P2 |
| 邮箱 | IMAP 轮询 + SMTP 回复 | 中 | P3 |

**建议第一阶段只做 CLI 和 Web 页面**，后续扩展。

---

### 2.2 消息网关（Message Gateway）

**职责**：
- 接收来自各渠道的消息
- 转换为统一格式
- 认证 / 鉴权（防止别人操控你的 agent）
- 消息排队、去重、限流

```
消息网关内部结构：

┌─────────────────────────────────────┐
│            Message Gateway           │
│                                      │
│  ┌──────────┐  ┌──────────┐         │
│  │ QQ 源     │  │ Web 源   │  ...    │  ← 每种渠道一个 handler
│  └────┬─────┘  └────┬─────┘         │
│       │              │                │
│       └──────┬───────┘                │
│              │                        │
│     ┌────────▼────────┐              │
│     │  Message Queue   │              │  ← 消息队列（可选）
│     └────────┬────────┘              │
│              │                        │
│     ┌────────▼────────┐              │
│     │  Auth + Filter   │              │  ← 认证 + 过滤
│     └────────┬────────┘              │
│              │                        │
│     ┌────────▼────────┐              │
│     │   Main Agent     │              │
│     └─────────────────┘              │
└─────────────────────────────────────┘
```

**技术选型建议**：
- 第一阶段：文件队列（`tasks/` 目录下 JSON 文件）
- 第二阶段：Redis 或内置 SQLite 队列

---

### 2.3 主 Agent（Brain）

主 Agent 是整个系统的大脑，负责：
1. 理解用户意图
2. 拆分为可执行的子任务
3. 选择合适的子 Agent 执行
4. 汇总结果，返回用户

```
主 Agent 工作流：

用户消息："帮我找出项目里所有未使用的 import，删掉它们"
         │
    ┌────▼─────┐
    │ 意图分析   │ → 任务类型：代码检查和清理
    └────┬─────┘
         │
    ┌────▼─────┐
    │ 任务拆分   │ → 子任务1：扫描项目找未使用 import
    │           │    子任务2：逐个删除并验证
    │           │    子任务3：运行测试确保没引入 bug
    └────┬─────┘
         │
    ┌────▼─────┐
    │ 并行分发   │ → 子任务1 → CBC Adapter → cbc 实例
    │           │    子任务3 → Shell Adapter → 运行测试
    └────┬─────┘
         │
    ┌────▼─────┐
    │ 监控进度   │ → 每个子任务的状态：pending / running / done / failed
    └────┬─────┘
         │
    ┌────▼─────┐
    │ 汇总结果   │ → "发现 12 个未使用 import，已删除，测试通过"
    └──────────┘
```

---

### 2.4 Agent 适配器层（Adapter Layer）

这是实现**跨厂商通用**的关键。每种 CLI 工具实现统一的适配器接口。

```
适配器接口（统一抽象）：

interface AgentAdapter {
  // 启动一个子 agent 实例
  spawn(name: string, model?: string): Promise<AgentInstance>;
  
  // 发送任务，等待结果
  execute(instance: AgentInstance, task: Task): Promise<TaskResult>;
  
  // 检查实例状态
  status(instance: AgentInstance): Promise<AgentStatus>;
  
  // 对已存在的实例追加任务（多轮对话）
  continue(instance: AgentInstance, task: Task): Promise<TaskResult>;
  
  // 停止实例
  destroy(instance: AgentInstance): Promise<void>;
  
  // 列出所有由本适配器管理的实例
  list(): Promise<AgentInstance[]>;
}

interface AgentInstance {
  id: string;          // 唯一标识
  name: string;        // 人类可读名称
  adapterType: string; // "cbc" | "claude-code" | "aider" | ...
  model: string;
  pid: number;         // 进程 PID
  sid: number;         // Session ID (如果适用)
  sessionId: string;   // CLI 工具自己的 session ID (如 cbc 的)
  status: 'starting' | 'ready' | 'busy' | 'error' | 'dead';
  createdAt: string;
  stats: {
    taskCount: number;
    lastActiveAt: string;
  };
}
```

#### CBC 适配器实现方案

> **核心需求：子 CLI 必须支持长对话（多轮上下文），`--print` 单次问答方案已废弃**。

| 方案 | 多轮对话 | 操控方式 | 状态 |
|------|---------|---------|------|
| `--bg` + PTY attach | ✅ | 通过 PTY 模拟键盘输入 | **待验证** |
| stream-json | ❓ | stdin/stdout JSON 流 | 待验证是否支持多轮 |
| PTY + spawn cbc | ✅ | node-pty 直接启动 | **推荐兜底** |
| ~~`--print`~~ | ❌ | 单次问答 | **已废弃** |

**方案 A：`--bg` + PTY 操控（首选）**
```
启动：codebuddy --bg --name worker-1 --model kimi-k2.5
操控：不通过 --print，而是用 PTY（tmux/node-pty）attach 进交互模式
     tmux send-keys -t worker-1 "列出所有文件" Enter
     tmux capture-pane -t worker-1 -p    # 获取输出
监控：codebuddy ps → 获取后台 session 列表
```
- 优点：原生长对话，有记忆系统，有 session 命名
- 风险：PTY 方式需要解析终端输出（去除 ANSI 控制序列）

**方案 B：stream-json 长连接**
```
启动：codebuddy --input-format stream-json --output-format stream-json
操控：持续通过 stdin 发送 JSON 消息，stdout 读取响应
     echo '{"type":"user","message":{"role":"user","content":"..."}}' | cbc ...
```
- 待确认：是否支持多轮？发完一条消息后进程是否退出？
- 如果支持长连接：最干净的编程操控方式
- 如果不支持：降级为单次，不可用

**方案 C：PTY 直接 spawn cbc（确保可行）**
```
用 node-pty / pexpect 直接启动 codebuddy（不加 --bg）
通过 PTY master 端读写，模拟完整交互终端
```
- 优点：完全控制，100% 可行，不依赖 cbc 的特殊模式
- 缺点：需要管理 PTY 生命周期，需要解析终端输出

#### 适配器实现示例（伪代码，基于 PTY 方案）

```javascript
// cbc-adapter.js
class CbcAdapter {
  spawn(name, model = 'kimi-k2.5') {
    // 方案A: --bg + tmux PTY 操控
    execSync(`codebuddy --bg --name ${name} --model ${model} --permission-mode bypassPermissions`);
    
    // 用 tmux 接管这个 session
    const tmuxName = `cbc-${name}`;
    execSync(`tmux new-session -d -s ${tmuxName}`);
    // ... 将 cbc bg session 挂入 tmux
    
    return {
      id: generateId(),
      name,
      adapterType: 'cbc',
      model,
      tmuxSession: tmuxName,
      status: 'starting'
    };
  }
  
  async execute(instance, task) {
    // 通过 tmux 模拟键盘输入（多轮对话的核心）
    execSync(`tmux send-keys -t ${instance.tmuxSession} "${escapeShell(task.content)}" Enter`);
    
    // 等待响应完成（需要解析输出判断何时回答完毕）
    await waitForResponse(instance.tmuxSession);
    
    // 捕获终端输出
    const raw = execSync(`tmux capture-pane -t ${instance.tmuxSession} -p`).toString();
    return stripAnsi(lastResponse(raw));  // 去掉 ANSI 控制序列，提取最后一段回答
  }
  
  async destroy(instance) {
    execSync(`codebuddy kill ${instance.name}`);
    execSync(`tmux kill-session -t ${instance.tmuxSession}`);
  }
}
```
```

#### 跨厂商适配策略

| CLI 工具 | 操控方式 | 适配复杂度 |
|----------|---------|-----------|
| CodeBuddy Code | `--bg` + `attach` | 低（已实验） |
| Claude Code | `--print` / `--resume` | 中 |
| Aider | `--message` / `--chat-mode` | 中 |
| Cursor CLI | stdin 管道 | 中 |
| 通用 Shell | PTY + tmux | 低 |

---

### 2.5 Session 管理器（Session Manager）

这是确保"每个 session 都可追踪"的核心组件。

```
Session Manager 职责：

┌────────────────────────────────────────┐
│           Session Manager               │
│                                         │
│  ┌──────────────┐  ┌──────────────┐    │
│  │ 实例注册表     │  │ 心跳监控      │    │
│  │ sessions.json │  │ 定时检查进程   │    │
│  └──────┬───────┘  └──────┬───────┘    │
│         │                 │             │
│         └────────┬────────┘             │
│                  │                      │
│  ┌───────────────▼───────────────────┐  │
│  │         日志 + 审计                │  │
│  │  - 每个 session 的对话记录          │  │
│  │  - 任务执行历史                    │  │
│  │  - 错误和异常                     │  │
│  └───────────────────────────────────┘  │
└────────────────────────────────────────┘
```

**sessions.json 结构**：

```json
{
  "updated": "2026-06-10T12:00:00Z",
  "instances": {
    "cbc-worker-1": {
      "id": "cbc-001",
      "name": "cbc-worker-1",
      "adapterType": "cbc",
      "model": "kimi-k2.5",
      "pid": 28461,
      "sid": 28460,
      "tty": "/dev/pts/4",
      "sessionId": "cbc-worker-1",
      "status": "ready",
      "createdAt": "2026-06-10T10:00:00Z",
      "stats": {
        "taskCount": 5,
        "lastActiveAt": "2026-06-10T11:59:00Z"
      }
    },
    "cbc-worker-2": {
      "id": "cbc-002",
      "name": "cbc-worker-2",
      "adapterType": "cbc",
      "model": "glm-5.1",
      "pid": 28500,
      "sid": 28499,
      "tty": "/dev/pts/5",
      "sessionId": "cbc-worker-2",
      "status": "busy",
      "createdAt": "2026-06-10T10:05:00Z",
      "stats": {
        "taskCount": 3,
        "lastActiveAt": "2026-06-10T12:00:00Z"
      }
    }
  }
}
```

**心跳机制**：
```javascript
// 每 10 秒检查所有注册的实例是否还活着
setInterval(async () => {
  for (const [name, inst] of Object.entries(registry)) {
    try {
      process.kill(inst.pid, 0);  // 信号 0 = 检查进程是否存在
      inst.status = inst.status === 'dead' ? 'ready' : inst.status;
    } catch {
      inst.status = 'dead';
      log.warn(`Session ${name} (PID ${inst.pid}) is dead`);
      // 可选：自动重启
    }
  }
  saveRegistry();
}, 10000);
```

---

### 2.6 中间层（Middle Layer）

连接调度器和适配器，负责任务队列管理和结果分发。

这个层是最灵活的部分。建议第一阶段**不单独抽象**，直接在调度器里调用适配器。等规模变大再抽出来。

---

## 三、项目目录结构建议

```
MyAgentsPlan/
├── README.md                    # 项目总览
├── beforeInit.md                # 原始需求
├── terminal-cli-concepts.md     # 终端前置知识
├── cbc-multi-cli-experiment.md  # CBC 实验记录
├── agent-cluster-architecture.md # 本文件
│
├── packages/                    # 子项目
│   ├── core/                    # 核心库
│   │   ├── src/
│   │   │   ├── types.ts         # 通用类型定义
│   │   │   ├── session-manager.ts  # Session 管理器
│   │   │   ├── task-queue.ts    # 任务队列
│   │   │   └── registry.ts     # 实例注册表
│   │   └── package.json
│   │
│   ├── adapters/                # Agent 适配器
│   │   ├── cbc-adapter/         # CodeBuddy Code 适配器
│   │   ├── claude-adapter/      # Claude Code 适配器
│   │   └── shell-adapter/       # 通用 Shell 适配器
│   │
│   ├── gateway/                 # 消息网关
│   │   ├── src/
│   │   │   ├── channels/        # 各渠道实现
│   │   │   │   ├── cli.ts
│   │   │   │   ├── web.ts
│   │   │   │   └── qq.ts
│   │   │   ├── router.ts
│   │   │   └── auth.ts
│   │   └── package.json
│   │
│   ├── brain/                   # 主 Agent 逻辑
│   │   ├── src/
│   │   │   ├── intent-parser.ts
│   │   │   ├── task-decomposer.ts
│   │   │   └── result-aggregator.ts
│   │   └── package.json
│   │
│   └── dashboard/               # Web 管理界面
│       ├── src/
│       │   ├── App.tsx
│       │   ├── SessionList.tsx   # 查看所有 session
│       │   ├── TaskLog.tsx       # 任务历史
│       │   └── Terminal.tsx      # 内嵌终端（基于 xterm.js）
│       └── package.json
│
├── sessions/                    # Session 数据（运行时状态）
│   └── .gitkeep
│
├── logs/                        # 日志文件
│   └── .gitkeep
│
└── experiments/                 # 实验脚本
    ├── 01-cbc-persistent/        # CBC 持久化 session 实验
    ├── 02-pty-control/           # PTY 操控实验
    └── 03-concurrent/            # 多实例并发实验
```

---

## 四、开发路线图

> **详细 todo 清单见 [todolist.md](../planning/todolist.md)**，这里仅做概要。

### 第一阶段：持久化 Session 操控（当前）

```
目标：找到可靠的多轮对话操控方案（--print 已废弃）

核心实验：
├── CBC stream-json 多轮测试
├── CBC --bg + attach 行为测试
├── tmux send-keys 操控实验
├── node-pty 启动子 cbc 实验
└── 终端输出清洗 + 多实例并发
```

### 第二阶段：最小可行系统

```
├── Session Manager（注册、心跳、日志）
├── CbcAdapter（基于 Phase 1 选出的方案）
├── 任务队列（文件系统）
├── CLI 主控入口
└── 端到端多轮对话测试
```

### 第三阶段：扩展和可视化

```
├── Web Dashboard（xterm.js）
├── 其他 CLI 适配器（Claude Code / Aider）
├── QQ Bot / Web 页面入口
└── 对话上下文管理
```

### 第四阶段：完整集群

```
├── 消息队列替代文件队列
├── 负载均衡
├── 子 agent 间协作
└── 持久化记忆共享
```

---

## 五、当前建议行动

**不需要写代码**，直接开终端验证：

### 实验：tmux 手动 mock 整体流程

```bash
# 启动 3 个 tmux session
tmux new-session -d -s main-agent    # 你自己（主 agent）
tmux new-session -d -s worker-1      # 子 cbc 1
tmux new-session -d -s worker-2      # 子 cbc 2

# 在 worker-1 里启动 cbc 交互模式
tmux send-keys -t worker-1 "codebuddy" Enter

# 主 agent 向 worker-1 发送第一条任务
tmux send-keys -t worker-1 "列出当前目录的所有文件" Enter
sleep 5
tmux capture-pane -t worker-1 -p | tail -20

# 验证多轮：再发第二条（看看 worker-1 有没有记住上下文）
tmux send-keys -t worker-1 "分析最大的那个文件的主要内容" Enter
sleep 5
tmux capture-pane -t worker-1 -p | tail -20
```

**关键验证点**：第二条消息时，worker-1 是否理解"最大的那个文件"指的是第一条结果中的文件。

### 实验：node-pty 最小 demo

```bash
mkdir experiments/02-pty-control
cd experiments/02-pty-control
npm init -y && npm install node-pty strip-ansi
```

```javascript
// test-pty.js
const pty = require('node-pty');

const shell = pty.spawn('bash', [], {
  name: 'xterm-color',
  cols: 120,
  rows: 40
});

shell.onData((data) => {
  process.stdout.write(`[PTY] ${data}`);
});

// 模拟交互
setTimeout(() => shell.write('codebuddy\r'), 500);
setTimeout(() => shell.write('列出所有 JS 文件\r'), 2000);
setTimeout(() => shell.write('分析第一个文件的主要内容\r'), 6000);
```

### 实验：检查 CBC 是否支持多轮 API

```bash
# 查看 cbc 所有选项
codebuddy --help

# 尝试 stream-json 多轮
echo '{"type":"user","message":{"role":"user","content":"记住：我叫张三"}}' | codebuddy --input-format stream-json --output-format stream-json
echo '{"type":"user","message":{"role":"user","content":"我叫什么名字？"}}' | codebuddy --input-format stream-json --output-format stream-json
```
```

---

## 六、架构设计的核心原则

1. **适配器模式是灵魂**：每种 CLI 一个适配器，实现统一接口
2. **Session 必须先注册再使用**：没有任何"看不见"的 session
3. **入口和调度解耦**：QQ/Web/邮件只负责收发消息，不关心谁在执行
4. **所有东西都是文件/JSON**：状态存 sessions.json，日志存 logs/，任务存 tasks/
5. **先跑通，再优化**：文件系统 → SQLite → 消息队列，逐步演进

---

## 七、待解答的关键问题

| # | 问题 | 影响 |
|---|------|------|
| 1 | `codebuddy attach <name> --print "任务"` 是否可行？ | 决定 CBC 适配器方案 |
| 2 | `--bg` session 是否支持多轮上下文？每次 attach 是追加还是独立？ | 决定子 agent 是否有"记忆" |
| 3 | 多个并发 `attach` 到同一个 bg session 会不会冲突？ | 决定是否需要任务队列 |
| 4 | Windows Git Bash 下 PTY 操控的兼容性如何？ | 决定是否需要在 WSL 中运行 |
| 5 | 不同模型的 cbc 实例能否共享同一个工作目录下的 MEMORY.md？ | 决定信息共享方案 |

---

> 下一步：选一个实验开始动手。建议优先验证问题 1（`--bg` attach 操控）。
