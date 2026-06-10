# Todo List

> 目标：构建 Agent 集群，主 Agent 操控多个子 CLI，支持长对话，session 可追踪。
> `--print` 单次问答方案已废弃，所有子 CLI 方案必须支持多轮上下文。

---

## Phase 1：持久化 Session 操控实验（当前阶段）

核心目标：找到一种可靠方式，让主 agent 能对子 CLI 进行多轮对话操控。

### 1.1 CBC 内部机制验证

- [ ] **1.1.1 `--bg` + stream-json 多轮测试**
  - 启动 `codebuddy --bg --name test1 --input-format stream-json --output-format stream-json`
  - 通过管道持续发送多条 JSON 消息，检查是否支持多轮
  - 文件：`experiments/01-cbc-persistent/s1-stream-json-multiturn.md`

- [ ] **1.1.2 `--bg` + `attach` 的行为测试**
  - 启动 `codebuddy --bg --name test2`
  - 测试 `codebuddy attach test2` 是否打开交互式界面
  - 测试多个 attach 并发会不会冲突
  - 测试 attach 后 stdin 能否被程序化写入
  - 文件：`experiments/01-cbc-persistent/s2-bg-attach-behavior.md`

- [ ] **1.1.3 `codebuddy resume` 能力探索**
  - 确认有没有 `--resume <session-id>` 或类似参数，可以恢复到之前的对话
  - 检查 `codebuddy --help` 或内置文档
  - 文件：`experiments/01-cbc-persistent/s3-resume-capability.md`

### 1.2 PTY 操控方案验证

- [ ] **1.2.1 tmux 操控另一个终端**
  - 创建 tmux session，在里面跑 `codebuddy`（交互模式）
  - 用 `tmux send-keys` 发送任务，`tmux capture-pane` 获取输出
  - 验证：能发送第二条消息保持上下文吗？输出能否准确解析？
  - 文件：`experiments/02-pty-control/t1-tmux-sendkeys.md`

- [ ] **1.2.2 node-pty 启动子进程**
  - 安装 `node-pty`，spawn bash/CodeBuddy 作为子进程
  - 通过 PTY master 端写入命令、读取输出
  - 验证：能否解析子 agent 的响应文本？
  - 文件：`experiments/02-pty-control/t2-node-pty.md`

- [ ] **1.2.3 终端输出清洗工具**
  - 提取 `tmux capture-pane` 或 PTY 输出中的 ANSI 控制序列
  - 实现一个 `stripAnsi()` + `extractLastResponse()` 函数
  - 文件：`experiments/02-pty-control/t3-output-cleaner.js`

### 1.3 多实例并发测试

- [ ] **1.3.1 两个 cbc 实例同时运行**
  - 同时启动 2+ 个 cbc 实例，各自处理不同任务
  - 验证：共享工作目录下的 MEMORY.md 会冲突吗？
  - 文件：`experiments/03-concurrent/c1-multi-instance.md`

- [ ] **1.3.2 文件锁 / 资源冲突测试**
  - 两个 cbc 实例同时操作同一个文件会发生什么？
  - 配置文件（settings.json, CODEBUDDY.md）是共享还是隔离？
  - 文件：`experiments/03-concurrent/c2-resource-conflicts.md`

---

## Phase 2：最小可行系统（代码开发）

前置条件：Phase 1 确定了可行的操控方案。

- [ ] **2.1 Session Manager 实现**
  - `packages/core/src/session-manager.ts`
  - 实例注册 / 注销
  - 心跳监控（定时检查进程存活）
  - sessions.json 持久化
  - 状态机：starting → ready → busy → error → dead

- [ ] **2.2 CbcAdapter 实现**
  - `packages/adapters/cbc-adapter/src/adapter.ts`
  - spawn / execute / continue / destroy / list / status
  - 基于 Phase 1 选出的最优方案

- [ ] **2.3 任务队列实现**
  - `packages/core/src/task-queue.ts`
  - 文件系统队列（`tasks/` 目录，每个任务一个 JSON）
  - 状态：pending → running → done / failed
  - 支持优先级、超时、重试

- [ ] **2.4 CLI 主控入口**
  - `packages/main/src/index.ts`
  - 通过当前 cbc 的 Bash 工具操控子 cbc
  - 命令：`agent-cluster spawn <name>`, `agent-cluster ps`, `agent-cluster run <task>`

- [ ] **2.5 端到端测试**
  - 启动 2 个子 cbc
  - 分别派发任务，收集结果
  - 验证多轮上下文保持

---

## Phase 3：扩展和可视化

- [ ] **3.1 Web Dashboard**
  - `packages/dashboard/`
  - 使用 xterm.js 内嵌 PTY 终端
  - 实时查看子 session 状态和输出
  - 任务历史列表

- [ ] **3.2 其他 CLI 适配器**
  - Claude Code 适配器
  - Aider 适配器
  - 通用 Shell 适配器（基于 PTY）

- [ ] **3.3 多渠道入口**
  - Web 页面（本地 HTTP + WebSocket）
  - QQ Bot（go-cqhttp 或官方 API）

---

## Phase 4：完整集群

- [ ] **4.1 消息队列**（Redis / RabbitMQ 替代文件队列）
- [ ] **4.2 负载均衡**（根据子 agent 状态分发任务）
- [ ] **4.3 子 agent 间协作**（agent A 的结果传递给 agent B）
- [ ] **4.4 持久化记忆共享**（MEMORY.md 级别）

---

## 实验记录目录结构

```
experiments/
├── 01-cbc-persistent/          ← Phase 1.1
│   ├── s1-stream-json-multiturn.md
│   ├── s2-bg-attach-behavior.md
│   └── s3-resume-capability.md
├── 02-pty-control/             ← Phase 1.2
│   ├── t1-tmux-sendkeys.md
│   ├── t2-node-pty.md
│   └── t3-output-cleaner.js
└── 03-concurrent/              ← Phase 1.3
    ├── c1-multi-instance.md
    └── c2-resource-conflicts.md
```

---

## 当前建议行动

**今天就可以做的事**（按优先级）：

1. 开 tmux，手动 mock 整个流程：左侧面板是你（主 agent），右侧面板是子 cbc。你给子 cbc 下指令，看它能不能正确执行并维持上下文。
2. 用 `node-pty` 写一个最小 demo：spawn 一个 bash，往里写 `ls`，读回输出。
3. 查 cbc 的 `--help` 和内置文档，找有没有 `--resume` 或 `stream-json` 多轮的说明。
