# Agent 集群架构方案

> 目标：通过一个主 Agent 操控管理多个**第三方** CLI/IDE 子 Agent，实现跨厂商 Agent 集群。
> 原则：模块化、跨厂商通用、session 可追踪、OS 原语优先。

---

## 一、总体架构

```
                         用户
                          │
          ┌───────┬───────┼───────┬───────┐
          │       │       │       │       │
       ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌──▼──┐
       │ QQ  │ │微信 │ │Web  │ │邮件 │ │CLI  │  ← 入口层
       └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘
          │       │       │       │       │
          └───────┴───────┼───────┴───────┘
                          │
                    ┌─────▼─────┐
                    │  消息网关   │  ← 统一消息格式 + 认证
                    └─────┬─────┘
                          │
                    ┌─────▼─────┐
                    │  主 Agent  │  ← 意图分析 + 任务拆分 + 结果汇总
                    └─────┬─────┘
                          │
                    ┌─────▼─────┐
                    │  调度器     │  ← 任务分配 + 并发控制
                    └─────┬─────┘
                          │
          ┌───────┬───────┼───────┬───────┐
          │       │       │       │       │
     ┌────▼──┐┌───▼───┐┌──▼────┐┌──▼────┐
     │CBC    ││Claude ││Copilot││Aider  │  ← 适配器层（每种 CLI 一套）
     │Adapter││Adapter││Adapter││Adapter│
     └────┬──┘└───┬───┘└──┬────┘└──┬────┘
          │       │       │       │
          └───────┴───────┴───────┘
                          │
                    ┌─────▼─────┐
                    │ Session    │  ← 统一 session 管理
                    │ Manager    │     sessions.json + PID 追踪
                    └─────┬─────┘
                          │
                    ┌─────▼─────┐
                    │ 进程管理层  │  ← child_process.spawn + PID/kill -0
                    │ (OS 原语)  │     备选：node-pty (bash wrapper)
                    └───────────┘
```

### 核心差异化能力

本系统的关键差异在于**对第三方闭源 CLI 的控制深度**：

| 控制深度 | 本系统 | 其他框架（如 OpenClaw） |
|---------|--------|----------------------|
| 启动第三方 CLI | ✅ `child_process.spawn` | ✅ `claude -p`（单次执行） |
| 获取输出 | ✅ 解析 stream-json | ✅ 捕获 stdout |
| 多轮对话 | ✅ `--resume <session_id>` | ❌ 每次新进程 |
| 进程生命周期管理 | ✅ PID 追踪 + kill -0 + kill | ❌ |
| Session 归档重建 | ✅ 元数据 + 对话历史双存 | ❌ |
| 跨 CLI 统一管理 | ✅ 适配器模式 + `AgentAdapter` 接口 | ❌ |
| 操控交互式 CLI (无 -p) | ✅ PTY 备选方案 | ❌ |

---

## 二、各层详细设计

### 2.1 入口层（Input Layer）

支持任意渠道与主 Agent 对话，所有渠道共享同一份对话上下文。

```
统一消息格式：
{
  "id": "uuid",
  "userId": "user_001",
  "channel": "qq|wechat|web|email|cli",
  "content": "帮我重构 auth 模块",
  "timestamp": "2026-06-10T10:00:00Z",
  "replyTo": "msg_id",
  "attachments": [...],
  "context": { ... }
}
```

| 渠道 | 实现方式 | 优先级 |
|------|---------|--------|
| CLI 直接 | stdin/stdout | P0 |
| Web 页面 | 本地 HTTP + WebSocket | P1 |
| QQ | QQ Bot SDK | P2 |
| 邮箱 | IMAP 轮询 + SMTP 回复 | P3 |

---

### 2.2 消息网关（Message Gateway）

- 接收各渠道消息，转换为统一格式
- 认证/鉴权（防止别人操控你的 Agent）
- 消息排队、去重、限流
- 第一阶段：文件队列（`tasks/` 目录下 JSON 文件）
- 第二阶段：Redis 或 SQLite 队列

---

### 2.3 主 Agent（Brain）

主 Agent 是整个系统的大脑：

```
用户消息："帮我找出项目里所有未使用的 import，删掉它们"
         │
    ┌────▼─────┐
    │ 意图分析   │ → 任务类型：代码检查和清理
    └────┬─────┘
    ┌────▼─────┐
    │ 任务拆分   │ → 子任务1：扫描未使用 import
    │           │    子任务2：逐个删除并验证
    │           │    子任务3：运行测试
    └────┬─────┘
    ┌────▼─────┐
    │ 并行分发   │ → 子任务1 → CBC Adapter
    │           │    子任务3 → Shell Adapter
    └────┬─────┘
    ┌────▼─────┐
    │ 监控进度   │ → pending / running / done / failed
    └────┬─────┘
    ┌────▼─────┐
    │ 汇总结果   │ → "发现 12 个未使用 import，已删除，测试通过"
    └──────────┘
```

---

### 2.4 Agent 适配器层（Adapter Layer）

跨厂商通用的关键。每种 CLI 实现统一接口。

```typescript
interface AgentAdapter {
  spawn(name: string, workdir: string, model?: string): Promise<{ pid: number; sessionId: string }>;
  execute(sessionId: string, task: Task): Promise<TaskResult>;
  continue(sessionId: string, task: Task): Promise<TaskResult>;
  status(sessionId: string): Promise<AgentStatus>;
  destroy(sessionId: string): Promise<void>;
  list(): Promise<AgentSnapshot[]>;
}
```

#### Phase 1 结论：四种方案对比

| 方案 | 可行性 | 跨 CLI | 复杂度 | 推荐度 |
|------|--------|--------|--------|--------|
| **A: --bg 后台 Worker** | ❌ 不可行 | 差 | 中 | 淘汰 |
| **B: PTY 终端操控** | ⚠️ 有条件 | 好 | 高 | 备选 |
| **C: --resume 独立进程** | ✅ 可行 | 中 | 低 | 可用 |
| **D: child_process.spawn** | ✅ 可行 | 好 | 中 | **首选** |

#### 首选方案：child_process.spawn + --resume

```
启动：child_process.spawn(cbc, ['-p', '--stream-json', '-y'], { cwd: workdir })
多轮：spawn(cbc, ['-p', '--stream-json', '-y', '--resume', sessionId], { cwd: workdir })
进程管理：PID 追踪 + kill -0 存活检测 + kill 终止
```

**核心代码**（详见 [shell-process-control.md](./shell-process-control.md)）：

```typescript
class ProcessManager {
  spawn(name, cmd, args) {
    const child = spawn(cmd, args);
    const id = `${name}-${Date.now()}`;
    this.workers.set(id, { pid: child.pid, process: child });
    child.on('exit', code => this.onExit(id, code));
    return id;
  }
  isAlive(id) {
    try { process.kill(this.workers.get(id).pid, 0); return true; }
    catch { return false; }
  }
  kill(id) { this.workers.get(id)?.process.kill(); }
}
```

#### 备选方案：PTY (node-pty + bash wrapper)

用于无 `--resume` 的 CLI。Windows 下通过 bash wrapper 启动：

```javascript
const shell = pty.spawn('bash.exe', [], { cwd: workdir, cols: 120, rows: 40 });
shell.write('codebuddy\n');
shell.write('Say hello in one word\n');
```

PTY 已验证能力：TUI 捕获、文本发送、/ 指令、Tab 键、多轮消息写入。详见 [PTY 实验总结](../../experiments/02-pty-control/pty-experiment-summary.md)。

#### 跨厂商适配策略

| CLI 工具 | 操控方式 | 适配复杂度 |
|----------|---------|-----------|
| CodeBuddy Code | `-p --stream-json --resume` | 低 |
| Copilot CLI | `-p --silent --yolo --continue` | 中 |
| Claude Code | `-p --resume` | 中 |
| Aider | `--message` / `--chat-mode` | 中 |
| OpenClaw | `claw` 命令 | 低（可作为被管 Agent） |
| 通用 Shell | PTY (bash wrapper) | 中 |

#### CLIIdentity 能力矩阵

每个适配器必须声明自身能力：

```typescript
interface CLIIdentity {
  name: string;
  capabilities: {
    crossDirResume: boolean;       // --resume 是否跨目录有效
    sessionTTL: number | null;     // session 过期时间，null = 永久
    nativeSessionDelete: boolean;  // 是否有原生 session 删除
    nativeSessionList: boolean;    // 是否有原生 session 列表
  };
}
```

---

### 2.5 Session 管理器（Session Manager）

**核心思路**：不与 CLI 的 session 回收对抗，由主 Agent 统一接管。

#### 三类 session 策略

| 类型 | 策略 | 负责方 |
|------|------|--------|
| **活跃 session** | 心跳保活，保持 `--resume` 可用 | 调度器 |
| **无价值 session** | 不处理，让 CLI 自己 GC | CLI（免费） |
| **有价值 session** | 主 Agent 显式标记后归档 | 主 Agent + 调度器 |

#### 归档内容

| 数据 | 存储 | 用途 |
|------|------|------|
| Session 元数据 (sessionId, CLI类型, workdir, 标签) | `sessions.json` | 快速索引/查询 |
| 完整对话历史 (messages[]) | `archive/{sessionId}.json` | 跨 CLI session 迁移/重建 |

#### 重建流程

1. 从 `archive/{sessionId}.json` 读取对话历史
2. 新 `spawn` 一个子 CLI 进程
3. 将历史作为 conversationSeed 注入（适配器负责序列化）

#### sessions.json 结构

```json
{
  "updated": "2026-06-12T12:00:00Z",
  "instances": {
    "cbc-worker-1": {
      "id": "cbc-001",
      "name": "cbc-worker-1",
      "adapterType": "cbc",
      "model": "deepseek-v4-pro",
      "pid": 28461,
      "sessionId": "67872ffb-5bff-4a90-b2c7-0f578d94d3ef",
      "workdir": "sessions/cbc-worker-1/",
      "status": "ready",
      "valuable": false,
      "createdAt": "2026-06-12T10:00:00Z",
      "stats": { "taskCount": 5, "lastActiveAt": "2026-06-12T11:59:00Z" }
    }
  }
}
```

#### 心跳机制

```javascript
setInterval(() => {
  for (const inst of Object.values(registry)) {
    try {
      process.kill(inst.pid, 0);
    } catch {
      inst.status = 'dead';
      if (inst.valuable) {
        archiveSession(inst);  // 自动归档有价值 session
      }
    }
  }
  saveRegistry();
}, 10000);
```

---

## 三、项目目录结构

```
CLIConductor/
├── README.md
│
├── docs/
│   ├── planning/
│   │   ├── project-overview.html   # 项目总览（主要文档）
│   │   ├── project-overview.md     # 项目总览 Markdown 版
│   │   ├── preview.md              # 一页速览
│   │   └── beforeInit.md           # 原始需求
│   ├── architecture/
│   │   ├── agent-cluster-architecture.md  # 本文件
│   │   ├── shell-process-control.md       # 进程控制方案
│   │   ├── tech-stack-control-layer.md    # 技术栈关系
│   │   └── terminal-cli-concepts.md       # 终端概念笔记
│   └── analysis/
│       ├── openclaw-architecture.md       # OpenClaw 架构分析
│       ├── cao-analysis.md                # CAO 分析
│       └── resource-index.md              # 外部资源索引
│
├── experiments/
│   ├── experiment-index.md          # 16 项实验索引
│   ├── cbc-multi-cli-experiment.md  # 初始探索
│   ├── 01-cbc-persistent/           # CBC 持久化实验（s1~s5）
│   ├── 02-pty-control/              # PTY 操控实验（t1~t3, e01~e04）
│   └── 03-concurrent/               # 并发实验（c1~c2）
│
├── packages/
│   ├── core/            # Session Manager、Task Queue
│   ├── adapters/        # CBC / Claude / Copilot / Shell 适配器
│   ├── brain/           # 主 Agent 调度逻辑
│   ├── gateway/         # 消息网关（多入口）
│   └── dashboard/       # Web 管理界面（Phase 3）
│
├── sessions/            # 子 Agent 独立 workdir
├── archive/             # 有价值 session 归档
└── logs/                # 运行日志
```

---

## 四、开发路线图

### Phase 0：初始化 ✅
- 终端/CLI 概念学习、架构设计、外部资料收集
- CAO / OpenClaw 源码分析

### Phase 1：实验验证 ✅（16 项实验）
- CBC 持久化 session：--resume 多轮 ✅ / --bg 废弃 ❌
- PTY 操控：node-pty + bash wrapper ✅ / tmux ❌
- 多实例并发 + 记忆隔离 ✅
- **结论**：child_process.spawn + --resume（首选），PTY（备选）

### Phase 2：最小可行系统 ⏳
- Session Manager（注册、心跳、归档）
- CbcAdapter（基于 Phase 1 方案D）
- 任务队列（文件系统）
- CLI 主控入口
- 端到端：启动 2 个子 cbc，并行派发任务

### Phase 3：扩展和可视化 📋
- Web Dashboard（xterm.js）
- 其他 CLI 适配器（Claude Code / Copilot / Aider）
- QQ Bot / Web 页面入口
- 与 OpenClaw 集成（Plugin 或母级管理）

### Phase 4：完整集群 📋
- 消息队列替代文件队列
- 负载均衡
- 子 Agent 间协作
- 持久化记忆共享

---

## 五、与 OpenClaw 的集成可能性

两种互补路径（详见 [OpenClaw 分析](../analysis/openclaw-architecture.md#711-与-openclaw-的集成可能性)）：

| 路径 | 描述 | 互补点 |
|------|------|--------|
| **A: 作为 Plugin/Skill** | 封装为 OpenClaw 工具 | 填补 OpenClaw 对第三方 CLI 深度管理的空缺 |
| **B: 作为母级管理** | OpenClaw 作为子 Agent | OpenClaw 做前端（渠道+交互），本系统做后端（多 CLI 编排） |

---

## 六、核心原则

1. **适配器模式是灵魂** — 每种 CLI 一个适配器，统一 `AgentAdapter` 接口
2. **OS 原语优先** — 不依赖 CLI 自身的进程管理能力
3. **Session 先注册再使用** — 没有任何"看不见"的 session
4. **入口和调度解耦** — 消息入口不关心谁在执行
5. **不与 CLI 回收对抗** — 有价值的归档，无价值的放手
6. **先跑通再优化** — 文件系统 → SQLite → 消息队列
