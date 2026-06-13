# OpenClaw (Claw) 原理与架构

> OpenClaw 是一个 MIT 开源、本地优先的 AI Agent 执行网关。核心理念：将大模型与本地执行环境深度融合，让 AI 从"能说"升级为"能做"。

---

## 一、全局架构图

> ⚠️ **说明**：以下架构图基于 OpenClaw 官方文档（clawdocs.org）整理，反映 OpenClaw 的实际架构设计。OpenClaw 采用 **Gateway-centric（以网关为中心）** 的单进程架构，并非多 Agent 集群架构。

```
┌──────────────────────────────────────────────────────────────────┐
│                        入口层（多渠道接入）                          │
│  Telegram  │  WhatsApp  │  Discord  │  Slack  │  Gmail  │  CLI  │
└──────────────────────┬───────────────────────────────────────────┘
                       │  消息归一化 + 身份认证 + EXTERNAL_UNTRUSTED_CONTENT 标记
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│               Gateway（中央进程 — WebSocket 服务器 + 守护进程）       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │
│  │ 连接路由  │  │ 会话管理  │  │ 鉴权认证  │  │ 命令队列     │    │
│  │(Router)  │  │(Session) │  │(Auth)    │  │(CommandQ)   │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │
│  │ 节点注册  │  │ 执行审批  │  │ 心跳管理  │  │ 插件系统     │    │
│  │(NodeReg) │  │(ExecAprv)│  │(Hrtbt)   │  │(Plugins)    │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘    │
└──────────────────────────┬───────────────────────────────────────┘
                           │  编排（Orchestrator）
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                         Brain（LLM 推理引擎）                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │
│  │ 提示组装  │  │ 模型路由  │  │ Provider │  │ 上下文管理    │    │
│  │(SOUL+    │  │(Opus/    │  │ 故障转移  │  │(会话历史+    │    │
│  │ Memory+  │  │ Sonnet/  │  │(Fallback)│  │ Bootstrap    │    │
│  │ Skills)  │  │ Haiku)   │  │          │  │ Scoping)     │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘    │
└──────────────────────────┬───────────────────────────────────────┘
                           │  工具调用（Tool Call Protocol）
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                       Hands（执行环境）                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │
│  │ Shell    │  │ 文件系统  │  │ Browser  │  │ HTTP         │    │
│  │(终端命令) │  │(读写文件) │  │(Playwright│  │(API 请求)    │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────────┘    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 沙箱隔离（Docker Sandbox — agent / session / shared）     │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Memory（本地 Markdown 持久化）                    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  ~/.openclaw/memory/                                     │   │
│  │  ├── preferences.md   (混合检索：向量 70% + BM25 30%)     │   │
│  │  ├── contacts.md      (sqlite-vec 本地嵌入)               │   │
│  │  ├── projects.md      (max_context_tokens 控制预算)       │   │
│  │  ├── learnings.md     (Dreaming 模式后台整理)             │   │
│  │  └── custom/          (用户自定义分类)                    │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘

多 Agent 扩展（同一 Gateway 下的平级多实例）：
┌──────────────────────────────────────────────────────────────────┐
│  Gateway (port 18789)                                            │
│  ├── Agent "alex"  ──── Workspace + Memory + Model (独立)       │
│  ├── Agent "mia"   ──── Workspace + Memory + Model (独立)       │
│  └── Agent "coder" ──── Workspace + Memory + Model (独立)       │
│  消息通过 Bindings（渠道/账户/对端）路由到对应 Agent                │
└──────────────────────────────────────────────────────────────────┘
```

---

## 二、六大核心模块

### 2.1 Gateway（网关）— 中枢神经

整个系统的 **总调度中心**，所有消息和指令必须经过它：

| 职责 | 说明 |
|------|------|
| **连接与路由** | 对接多渠道，内置路由引擎按规则分发消息 |
| **会话管理** | 维护用户/平台的会话状态，保证上下文连续 |
| **指令分发与状态同步** | 分发任务到 Agent/节点，同步执行状态 |
| **鉴权与监控** | 全程后台常驻，无需手动启动 |

> **比喻**：Gateway 是"小区物业中控室"——不管从哪个门进来，都先报到中控室，中控室再派 AI 去干活。关了监控屏，后台仍在运转。

### 2.2 Brain & Hands（推理引擎 + 执行环境）

OpenClaw 将 AI 推理与系统执行分离为两个独立层。**Brain（大脑）** 负责决策，**Hands（双手）** 负责执行。

> **注意**：早期版本中 OpenClaw 存在 "Pi Agent" 概念，但在 v2026 大重构中已被移除/重命名为 OpenClaw agent 运行时（agent-core 包）。当前官方架构使用 **Brain（LLM 推理引擎）+ Hands（执行环境）** 来描述核心执行层。

#### Brain（LLM 推理引擎）

Brain 是 LLM 模型，负责解释请求、推理并制定行动计划：

| 能力 | 说明 |
|------|------|
| **多 Provider 支持** | Anthropic（Opus/Sonnet/Haiku）、OpenAI、Google Gemini、xAI Grok、DeepSeek、OpenRouter、本地 Ollama/vLLM |
| **模型路由** | 按任务复杂度路由到不同模型：Heartbeat 用 Haiku、聊天用 Sonnet、复杂推理用 Opus |
| **故障转移** | 主 Provider 不可用时自动切换到备用 Provider |
| **上下文组装** | 从 SOUL.md、AGENTS.md、Memory、Skills、会话历史、渠道消息逐层组装 Prompt |

**Prompt 组装流水线：**

```
┌─────────────────────────────────────────────┐
│  SOUL.md（身份、个性、规则）                  │  ← 始终加载
├─────────────────────────────────────────────┤
│  AGENTS.md + TOOLS.md（任务指令）             │  ← 按 Agent
├─────────────────────────────────────────────┤
│  Memory（混合检索结果）                       │  ← 上限 max_context_tokens
├─────────────────────────────────────────────┤
│  激活的 Skill 指令                           │  ← 0-N 个技能
├─────────────────────────────────────────────┤
│  会话历史                                    │  ← Session 上下文
├─────────────────────────────────────────────┤
│  <<<EXTERNAL_UNTRUSTED_CONTENT>>>           │
│  渠道消息（注入防护标记）                      │  ← 实际输入
│  <<</EXTERNAL_UNTRUSTED_CONTENT>>>          │
└─────────────────────────────────────────────┘
```

#### Hands（执行环境）

Hands 执行 Brain 的决策，通过结构化的 Tool Call 协议通信：

| 能力 | 说明 | 示例 |
|------|------|------|
| **Shell** | 执行终端命令 | `ls`, `git`, `python`, `docker` |
| **Filesystem** | 读写/修改文件 | 创建配置、编辑代码、管理日志 |
| **Browser** | Chromium 自动化（Playwright） | 填表单、抓页面、截图 |
| **HTTP** | 发起 API 请求 | REST 调用、Webhook 投递 |

**工具调用协议**：Brain 通过 JSON 格式请求工具执行，Hands 返回结果，Brain 分析后可链式调用多个工具，直到产出最终回复。

**沙箱隔离**：支持 Docker 沙箱（`agent` / `session` / `shared` 三种作用域），生产部署可将 Hands 隔离在容器中。工具权限通过命名 Profile（minimal / coding / messaging / full）控制。

### 2.3 Tools / Skills / Plugins（能力扩展层）

```
┌────────────────────────────────────────────┐
│                扩展体系                      │
│                                            │
│  Skills（技能）  — 怎么用资源（工作流）        │
│       ▲                                    │
│  MCP / Tools（工具）— 能访问什么（执行动作）    │
│       ▲                                    │
│  Plugins（插件）  — 扩展连接能力（通信协议）    │
└────────────────────────────────────────────┘
```

| 层级 | 比喻 | 作用 | 运行位置 |
|------|------|------|---------|
| **Tools** | 手、眼、腿 | 执行具体动作（读写文件、执行命令） | 核心沙箱 / 节点 |
| **Plugins** | 对讲机 | 扩展网关连接能力，增加协议支持 | Gateway 层 |
| **Skills** | 厨师证、会计证 | 封装专业知识与复杂工作流 | Agent 逻辑层 |

**Skills 生命周期（5 阶段）：**

1. **扫描发现** — 多目录扫描，按优先级合并
2. **条件过滤** — 检查启用、平台兼容、依赖
3. **按需加载** — 系统提示词只放目录，选中后才读完整 SKILL.md
4. **规范载体** — SKILL.md = YAML 元数据 + 自然语言流程描述
5. **两种触发** — AI 自主调用 / 用户斜杠命令

### 2.4 Memory（记忆）— 白盒本地持久化

核心理念：**记忆 = 本地 Markdown 文件，而非向量空间的抽象**

```
┌──────────────────────────────────────┐
│           记忆系统                     │
│                                      │
│  记忆本体：本地 Markdown 文件          │
│       ↓                              │
│  混合检索：向量检索 70% + BM25 30%    │
│       ↓                              │
│  sqlite-vec 本地嵌入（无外部 API）     │
│       ↓                              │
│  Dreaming 模式后台整理去重             │
└──────────────────────────────────────┘
```

| 特性 | 传统 AI 记忆 | OpenClaw 记忆 |
|------|------------|-------------|
| 存储形式 | 向量空间抽象 | 本地 Markdown 文件（`~/.openclaw/memory/`） |
| 可见性 | 黑箱 | **白盒**，用户可直接查看修改 |
| 检索方式 | 纯向量检索 | 混合检索（向量 70% + BM25 关键词 30%） |
| 嵌入生成 | 远程 API | 本地 sqlite-vec（无外部调用） |
| 上下文预算 | 通常不限制 | `max_context_tokens` 可配置（默认 2000） |
| 后台整理 | 无 | Dreaming 模式（Light → REM → Deep 三阶段） |

**记忆文件结构：**

```
~/.openclaw/memory/
├── preferences.md     # 用户偏好和习惯
├── contacts.md        # 用户认识的人
├── projects.md        # 活跃项目及上下文
├── learnings.md       # 发现和解决方案
└── custom/            # 用户自定义分类
    ├── work.md
    └── recipes.md
```

**Dreaming 模式（v2026.5+）：**
- 后台记忆整理进程，模拟睡眠周期
- Light 阶段：去重最近 24 小时记录
- REM 阶段：识别 7 天窗口内的模式和关联
- Deep 阶段：基于 6 个信号（相关性、频率、新近度、多样性、可信度、实用性）评分，提升或归档

> **注意**：OpenClaw 的记忆系统**没有**文档之前假设的"泳道队列强制串行"写入机制。写入一致性通过 Gateway 的 Command Queue（按 session 分 lane）保证，而非专门的记忆泳道队列。也没有像 MyAgentsPlan 的 MEMORY.md 那样的"类型分类（user/feedback/project/reference）"机制——OpenClaw 使用 `categories` 配置项（preferences/contacts/projects/learnings）来分类记忆。

### 2.5 Nodes（节点）— 物理能力延伸

节点是分布在终端设备上的代理程序，提供 **硬件能力 + 本地执行环境**：

- 摄像头、麦克风、GPS 定位等硬件访问
- 本地文件系统操作、脚本执行、桌面应用控制

这使得 OpenClaw 能超越云端 API 限制，与物理世界和本地数字环境交互。

### 2.6 Channels（渠道）— 交互入口

直接寄生于用户日常社交软件：Telegram、WhatsApp、微信、飞书、iMessage 等。

```
传统 AI 模式：用户 → 打开网站 → 主动访问"目的地"
OpenClaw 模式：AI = 联系人列表里的"随行者"，随时待命
```

---

## 三、多 Agent 协作机制

### 3.1 多 Agent 工作模式

OpenClaw 的多 Agent 并非层级式的"主 Agent 调度子 Agent"，而是**同一 Gateway 下的平级多实例**。每个 Agent 拥有完全隔离的工作区、记忆和可选的 LLM 模型，消息通过 Bindings（渠道/账户/对端）路由到指定 Agent。

```
Gateway (port 18789)
  ├── Agent "alex"  ──── Workspace + Memory + Model
  ├── Agent "mia"   ──── Workspace + Memory + Model
  └── Agent "coder" ──── Workspace + Memory + Model

  ▲ 消息通过 Bindings 路由到对应 Agent
```

**两种协作模式：**

#### 模式一：文件式消息传递（File-Based Messaging）

最简单的协作方式：Agent 通过共享文件通信。

```bash
# Agent "lead" 写入任务
echo '{"task": "Review PR #42", "priority": "high"}' > ~/.openclaw/shared/inbox-reviewer.json

# Agent "reviewer" 通过 Heartbeat 检查收件箱
cat ~/.openclaw/shared/inbox-reviewer.json
```

#### 模式二：看板编排（Workboard Orchestration）

通过 Workboard 卡片系统进行结构化协作。详见 [3.4 Workboard 看板编排](#34-workboard-看板编排任务分发机制)。

#### 模式三：MCP 协议通信

Agent 可以通过 MCP（Model Context Protocol）互相调用技能：

```json
{
  "mcp": {
    "servers": {
      "researcher-agent": {
        "command": "ssh",
        "args": ["user@server", "openclaw", "mcp", "serve", "--agent", "researcher"]
      }
    }
  }
}
```

#### 模式四：Orchestrator-Worker（编排器-工作者模式）

这是最接近"主 Agent 调度子 Agent"的模式。一个 lead Agent（通常用 Opus 模型）负责分解任务，多个 worker Agent（researcher/writer/reviewer，通常用 Sonnet/Haiku）认领执行。

```
Lead Agent                     Workboard                 Specialist Agents
    │                             │                             │
    ├── create card ────────────► │                             │
    │   "Research competitors"    │◄── claim ──────────────────┤ researcher
    │                             │                             │
    ├── create card ────────────► │                             │
    │   "Write report"            │   (blocked by research)     │
    │   blocked-by: research      │                             │
    │                             │                             │
    │                             │◄── done ───────────────────┤ researcher
    │                             │── auto-unblock ───────────►│
    │                             │◄── claim ──────────────────┤ writer
    │                             │                             │
    │◄── notify ──────────────────│◄── done ───────────────────┤ writer
```

> **注意**：Worker Agent 是**在 Gateway 配置中静态定义的常驻协作者**，不是临时 spawn 的进程。每个 Worker 有独立的 workspace 和 memory。

**Bootstrap Context Scoping（v2026.5.22+）：**
- 子 Agent 默认只接收 `AGENTS.md` 和 `TOOLS.md`，不接收 `SOUL.md`、`USER.md` 和主 Agent 的记忆
- 既节省 Token，又防止敏感上下文泄露

### 3.2 CLI 交互 vs 程序化交互

OpenClaw 主要使用 **CLI 命令** 进行交互（`openclaw chat`、`openclaw gateway`、`openclaw skill` 等），同时也支持程序化交互方式：

| 维度 | CLI 交互 | 程序化交互 |
|------|---------|----------|
| 调用方式 | 终端执行 `openclaw <command>` | MCP 协议调用 / WebSocket API / Webhook |
| 适用场景 | 手动管理、调试、日常使用 | Agent 间通信、自动化集成 |
| 工具集 | CLI 内置命令（onboard/gateway/skill/heartbeat 等） | 200+ RPC 方法（chat.send / tools.invoke / agents.list 等） |
| 交互模式 | 用户 → 终端 → Gateway | Agent → MCP → 另一 Agent / 外部系统 |

> OpenClaw **不存在** 文档中假设的"API 模式（主 Agent 完整工具集）vs CLI 模式（子 Agent 精简工具集）"的二分法。所有 Agent 运行的都是同一个 Gateway 进程，区别在于 workspace 配置不同。

### 3.3 并发控制（Command Queue 车道机制）

OpenClaw 通过 **Command Queue（命令队列）** 控制并发。每个 session 拥有独立的"车道"（lane），同一时间只有一个 Agent 运行操作某个 session。

```javascript
// 车道机制示意：每个 session 独立队列
const queue = new LaneAwareFIFO()
// Session A 的消息进入 Lane A，Session B 的消息进入 Lane B
// 同一条 Lane 内串行，不同 Lane 之间并行
```

**配置要点：**

- 每个 session 独立队列，防止多渠道/Heartbeat 同时触发导致消息乱序
- 不同 session 的消息可以并行处理
- 不涉及 CLI Backend 粒度的 serialize 配置

> **注意**：这与 MyAgentsPlan 对比分析中假设的 "CLI Backend serialize 机制" 不同。OpenClaw 的并发控制是**按 session 分 lane**，不是按 CLI backend 粒度控制串行/并行。原文档 7.9 节中关于借鉴 serialize 控制的建议需要重新评估。

### 3.4 Workboard 看板编排（任务分发机制）

OpenClaw 的 Workboard（v2026.6.1+）是官方的多 Agent 编排层，基于卡片（Card）和生命周期管理：

**卡片状态流转：**
```
todo → running → review → done
         ↓
      blocked
```

**Agent 交互工具：**

| 工具 | 功能 |
|------|------|
| `workboard_create` | 创建任务卡片，可设置父子依赖 |
| `workboard_claim` | 认领 `todo` 状态的卡片 |
| `workboard_update` | 更新卡片状态（done / blocked） |
| `workboard_link` | 创建卡片间依赖链 |
| `workboard_promote` | 提升卡片优先级 |
| `workboard_reassign` | 重新分配给其他 Agent |

**自动调度流程（Dispatch Workflow）：**

1. **Promote** — 检查依赖，将依赖已就绪的卡片从 `blocked` 提升为 `todo`
2. **Unblock** — 清除过期或失效的认领
3. **Claim** — Agent 认领下一个可用卡片
4. **Start** — Agent 开始执行
5. **Track & Notify** — 跟踪完成，依赖变更时通知相关 Agent

**与 MyAgentsPlan 的对比：**

- Workboard 是**去中心化的看板**，Agent 自主认领任务，无中央调度
- MyAgentsPlan 是**中央调度器分发**，主 Agent 主动分配任务给子 CLI
- Workboard 的 Agent 是**常驻协作者**（在 Gateway 中静态配置），非临时 spawn

---

## 四、任务执行流程

```
用户输入（自然语言）
    │
    ▼
渠道适配器  ──  身份认证 + 消息归一化
    │
    ▼
Gateway 路由引擎  ──  确定由哪个 Agent 处理
    │
    ▼
Agent 推理规划
    ├── 调用 Memory 检索上下文
    ├── 提交 LLM 推理
    └── 生成结构化行动计划
         │
         ├─ 步骤1：调用 Skill A（邮件搜索）
         ├─ 步骤2：调用 Skill B（文本总结）
         └─ 步骤3：调用 Tool C（文件写入）
              │
              ▼
         执行 → 更新记忆 → 结果反馈到渠道
```

---

## 五、OpenClaw CLI 命令参考

OpenClaw 的命令行入口是 `openclaw` 命令，包含丰富的子命令体系：

```
openclaw <command> [subcommand] [flags]

全局参数：
  --version     打印版本
  --help        显示帮助
  --config      使用自定义配置文件
  --verbose     详细输出
  --json        JSON 格式输出

常用命令：
  onboard       交互式安装向导
  dashboard     启动控制面板（浏览器）
  gateway       管理 Gateway 进程（start/stop/restart/status）
  chat          发送消息/启动交互式聊天
  channel       管理消息渠道（add/remove/list/status）
  skill         管理技能（install/remove/list/test）
  plugins       管理插件（list/install/update/enable/disable）
  clawhub       ClawHub 市场（search/install/publish/browse）
  heartbeat     管理心跳系统（--now 立即触发）
  logs          查看 Gateway 日志（--filter heartbeat/channel/brain/hands）
  status        系统状态
  stats         使用统计（heartbeat/tokens/channels）
  security      安全检查/扫描
  config        查看/修改配置（get/set/list）
```

**技术栈**：Node.js + 原生 CLI（非 Commander 框架） + WebSocket 协议

---

## 六、核心设计亮点总结

| 设计亮点 | 说明 |
|---------|------|
| **按需加载** | 工具/技能目录与内容分离，选中后才加载，大幅节省 Token |
| **白盒记忆** | Markdown 文件存储，用户可直接查看和修改 |
| **Gateway 单进程架构** | 一个进程管理所有通信、编排和执行，部署简单 |
| **混合检索记忆** | 向量 70% + BM25 30%，本地 sqlite-vec 无需外部 API |
| **Dreaming 后台整理** | 模拟睡眠周期的记忆整理（Light → REM → Deep） |
| **模型路由** | 按任务复杂度路由到不同模型，平衡成本和质量 |
| **Provider 故障转移** | 主 Provider 不可用时自动切换 |
| **多 Agent 平级实例** | 同一 Gateway 下多个独立 Agent，各有 workspace/memory/model |
| **Workboard 看板编排** | 卡片式任务分发，支持依赖管理和自动调度 |
| **Bootstrap Context Scoping** | 子 Agent 仅接收 AGENTS.md + TOOLS.md，节省 Token 且安全 |
| **技能市场 ClawHub** | 社区共享，10,700+ 技能可安装 |

---

## 七、OpenClaw 与 MyAgentsPlan 异同分析

### 7.1 核心定位对比

| 维度 | OpenClaw | MyAgentsPlan |
|------|----------|-------------|
| **定位** | AI Agent 执行网关（让 AI 从"能说"升级为"能做"） | Agent 集群操控系统（用 Agent 管 Agent） |
| **核心能力** | 多渠道接入 + 内置 Agent 推理 + 本地工具执行 | 操控多个**第三方** CLI/IDE 子 Agent 协同完成复杂任务 |
| **用户交互** | 寄生在社交软件中，AI 是"随行者" | 用户只与主 Agent 对话，子 Agent 全透明 |
| **首要目标** | 打通 AI 与本地环境的执行链路 | 打通一个 Agent **跨厂商**操控多个 CLI 的控制链路 |
| **场景侧重** | 个人助手：搜邮件、写总结、控设备 | 开发协作：分解大任务 → 多个 CLI 并行实现 → 汇总结果 |

> **一句话区别**：OpenClaw 是"一个人 + 一个 AI + 一堆工具"；MyAgentsPlan 是"一个人 + 一个主 AI + 一群**第三方** AI 同事 + 各自工具"。

---

### 7.2 核心痛点：第三方 Agent 的控制深度

MyAgentsPlan 要解决的一个关键问题是：**现有 Agent 框架对第三方闭源 CLI 的控制深度不足。**

OpenClaw 是一个自包含的 Agent 系统，使用自己的 Brain（LLM 推理）+ Hands（工具执行），不涉及对第三方 CLI 的进程级管理。它通过 CLI 命令（`openclaw chat`）与用户交互，通过 MCP 协议让 Agent 之间互相调用技能。

MyAgentsPlan 的差异不在"能不能调"，而在**控制深度**：

| 控制深度 | OpenClaw | MyAgentsPlan |
|---------|----------|-------------|
| 运行自己的 Agent | ✅ Brain + Hands 自包含推理执行 | ❌ 不内置 Agent，依赖第三方 CLI |
| Agent 间通信 | ✅ MCP 协议互相调用技能 | ✅ 适配器统一接口 |
| 跨厂商第三方 CLI 管理 | ❌ 不涉及 | ✅ 适配器模式 + child_process.spawn |
| 多轮对话保持 | ✅ 内置会话管理 | ✅ CLI 的 `--resume <session_id>` |
| 进程生命周期管理 | ❌ 不需要（单进程） | ✅ PID 追踪 + kill -0 + kill |
| 操控外部 CLI 进程 | ❌ 不是设计目标 | ✅ OS 层进程管理（spawn / PTY） |

```
OpenClaw 的 Agent 控制范围：
  ┌─────────────────────────────┐
  │  OpenClaw Agent（自包含）    │  ← 完全可控：Brain + Hands 一体
  │  MCP 调用其他 Agent 的技能   │  ← 协议级互调，非进程管理
  └─────────────────────────────┘

MyAgentsPlan 的 Agent 控制范围：
  ┌─────────────────────────────┐
  │  主 Agent（CBC/Claude Code） │  ← 协调者
  │      │                       │
  │      ├── CBC (CodeBuddy)     │  ← 第三方，OS 层深度管理
  │      ├── Claude Code         │  ← 第三方，OS 层深度管理
  │      ├── Copilot CLI         │  ← 第三方，OS 层深度管理
  │      ├── Aider               │  ← 第三方，OS 层深度管理
  │      └── (未来) VS Code / Cursor / ... │  ← 第三方，OS 层深度管理
  └─────────────────────────────┘
```

**为什么这个差异化能力有价值：**

1. **各厂商 CLI 能力不统一** — 有的有 `--resume`（CBC），有的只有 `--continue`（Copilot），有的可能什么都没有。MyAgentsPlan 的适配器模式统一抽象了这些差异。
2. **避免厂商锁定** — 底层 CLI 可以随时替换，适配器切换即可，不绑定任何单一实现。
3. **IDE 操控是空白地带** — 目前没有框架能程序化地操控 VS Code 或 Cursor 中的 AI Agent。MyAgentsPlan 的 PTY/OS 层方案为未来操控 IDE 预留了路径。

> **注意**：OpenClaw 的设计目标是"自包含的 AI 个人助手"——用自己的 Brain 推理、用自己的 Hands 执行。控制第三方 CLI 本就不是它的需求。MyAgentsPlan 只是选择了一条不同的路：不要求 CLI 厂商配合，从 OS 层面建立深度控制通道。

### 7.3 架构层面异同

**相同点：**

- 都采用 **消息网关 + Agent 执行** 的分层架构
- 都支持 **多渠道接入**（CLI/IM/Web），消息网关负责归一化
- 都有 **Session 管理**机制，确保上下文连续性
- 都强调 **模块化/可扩展**，通过插件或适配器机制接入外部能力
- 都用 **Node.js/TypeScript** 技术栈

**不同点：**

| 架构维度 | OpenClaw | MyAgentsPlan |
|---------|----------|-------------|
| **Agent 推理** | 内置 Brain（LLM 推理引擎） | 不内置，依赖第三方 CLI 自带的推理能力 |
| **Agent 来源** | 自包含 Agent（OpenClaw 实例） | **任意第三方 CLI**（CBC/Claude Code/Copilot/Aider/IDE） |
| **Agent 关系** | 同一 Gateway 下的平级多实例，通过 Workboard/MCP 协作 | 主 Agent 操控 + 多个长期存活的第三方 CLI 实例 |
| **通信方式** | Gateway WebSocket 协议 + MCP | `child_process.spawn` + `stream-json`（--print 模式），备选 PTY |
| **扩展方式** | Skills 市场 (ClawHub 10,700+) | 适配器模式注册新 CLI 厂商 |
| **部署形态** | 单进程守护进程 (Gateway daemon)，本地运行 | 控制层 + 被控 CLI 进程树，可本地可远程 |
| **任务执行** | Agent 自主认领（Workboard 去中心化） | 主 Agent 主动分配（Scheduler 中央调度） |
| **第三方 CLI 管理** | ❌ 不涉及 | ✅ OS 层进程管理

### 7.4 子 Agent 管控：本质差异

这是最核心的区别——**"管的是什么"和"怎么管"完全不同**。

```
OpenClaw 模型：
  Gateway → Brain (LLM) + Hands (执行) → 完成
  多 Agent：平级实例，通过 Workboard 看板或 MCP 协议协作
  Agent 是常驻协作者（静态配置在 Gateway 中）

MyAgentsPlan 模型：
  主 Agent → Scheduler → Adapter → child_process.spawn → CLI 进程 → --resume 多轮对话
  子 CLI 是"常驻员工"，长期存活、多轮交互、状态持久
  每个 CLI 一个适配器，OS 层统一管理
```

| 对比维度 | OpenClaw | MyAgentsPlan |
|---------|----------|-------------|
| **被控对象** | 自己的 OpenClaw Agent（Brain + Hands 一体） | **第三方闭源 CLI 进程**（CBC/Claude Code/Copilot/Aider） |
| **控制手段** | Gateway 内部 WebSocket 协议 + MCP | **OS 原生进程管理**（`child_process.spawn` + PID 追踪 + kill -0 存活检测） |
| **多轮对话** | 内置会话管理，天然支持 | 通过 CLI 的 `--resume <session_id>` 保持上下文连续性 |
| **生命周期** | 常驻进程（Gateway daemon 持续运行） | 长生命周期：spawn → 多轮对话 → 持续运行 → 显式销毁 |
| **状态感知** | Gateway 内部状态，天然可感知 | 需要解析 `stream-json` 输出流（--print 模式）或 ANSI 终端输出（PTY 模式） |
| **跨厂商** | 不需要（只用自己的 Agent） | **核心需求**（适配器模式是灵魂） |
| **会话恢复** | 内置会话存储 | 自定义 `sessions.json` + PID 映射 + `--resume`；支持归档重建 |
| **并发模型** | Command Queue 车道（按 session 分 lane） | 独立的 Task Queue + Concurrency Pool |
| **PTY 操控** | 不需要 | 备选方案（bash wrapper），用于无 `--resume` 的 CLI |
| **厂商锁定** | 有（绑定 OpenClaw 生态） | 无（适配器可随时替换底层 CLI） |

### 7.5 扩展体系对比

```
OpenClaw：               MyAgentsPlan：
Skills（工作流封装）         Adapters（厂商接入）
  ↑                         ↑
Plugins（插件）              Scheduler（任务分发）
  ↑                         ↑
MCP Servers（工具接入）      Channels（渠道接入）
```

**OpenClaw 的扩展逻辑**：能力由 Skills 市场提供，用户安装即用。扩展的是"能干什么"（**垂直深度**）。底层通过 MCP 协议接入海量工具（32,600+ MCP Servers）。

**MyAgentsPlan 的扩展逻辑**：能力由新 CLI 适配器提供，注册即用。扩展的是"找谁干"（**水平广度**）。

核心差异在于**扩展的边界**：
- OpenClaw 的扩展止于自己的 Agent 生态——你可以加 Skills 和 MCP 工具，但你没法说"让 Claude Code 代替 OpenClaw Agent 来做这件事"
- MyAgentsPlan 的扩展没有这个边界——新增一个 CLI 厂商只需要写一个适配器，调度器对底层 CLI 无感知

**OpenClaw 的扩展逻辑**：能力由 Skills 市场提供，用户安装即用。扩展的是"能干什么"（**垂直深度**）。

**MyAgentsPlan 的扩展逻辑**：能力由新 CLI 适配器提供，注册即用。扩展的是"找谁干"（**水平广度**）。

核心差异在于**扩展的边界**：
- OpenClaw 的扩展止于自己的 Agent 生态——你可以加 Skills，但你没法说"让 Claude Code 代替 Pi Agent 来做这件事"
- MyAgentsPlan 的扩展没有这个边界——新增一个 CLI 厂商只需要写一个适配器，调度器对底层 CLI 无感知

### 7.6 Session 管理策略对比

| 维度 | OpenClaw | MyAgentsPlan |
|------|----------|-------------|
| **Session 存储** | Gateway 内置会话存储 | 自定义 `sessions.json` + PID 映射 |
| **Session 过期** | 自己控制 | **不控制** — 三类策略：活跃保活 / 无价值让 CLI 自己 GC / 有价值归档 |
| **Session 归档** | 不需要（自己掌控） | 需要 — 元数据 + 对话历史双存，支持过期后重建 |
| **跨厂商统一** | 天然统一（Gateway 统一管理所有 Agent 会话） | **核心挑战** — 不同 CLI 的 session 概念完全不同 |

> MyAgentsPlan 的 session 归档策略详见 [项目总览 - Session 生命周期与归档策略](../planning/project-overview.html)。

### 7.7 记忆系统对比

| 维度 | OpenClaw | MyAgentsPlan |
|------|----------|-------------|
| **存储形式** | 本地 Markdown 文件（`~/.openclaw/memory/`） | 规划中（Phase 4：本地文件 + 向量索引） |
| **可见性** | 白盒，用户可直接查看修改 | 规划中（同样倾向白盒） |
| **检索方式** | 混合检索：向量 70% + BM25 30%（本地 sqlite-vec） | 规划中 |
| **写一致性** | Gateway Command Queue 按 session 分 lane 保证 | 规划中（文件锁 + 消息队列） |

> **记忆系统是本项目可以借鉴 OpenClaw 的模块之一**，包括本地 Markdown 文件存储、混合检索策略、Dreaming 后台整理等。但需注意：OpenClaw 没有 MyAgentsPlan 文档假设的 MEMORY.md 索引机制和类型分类（user/feedback/project/reference）——这些是 MyAgentsPlan 自己的设计，不能照搬。

### 7.8 成熟度与演进路径

| 维度 | OpenClaw | MyAgentsPlan |
|------|----------|-------------|
| **项目阶段** | MIT 开源成熟项目，社区活跃 | Phase 1 完成（16 项实验），进入 Phase 2 |
| **代码量** | 完整实现，生产可用 | 尚未开始编码（文档 + 实验验证完成） |
| **社区生态** | ClawHub 10,700+ Skills，32,600+ MCP Servers | 无 |
| **演进策略** | 持续迭代，社区驱动 | 四阶段渐进式路线图，先跑通再优化 |

### 7.9 本项目可借鉴的关键设计

| 借鉴点 | OpenClaw 做法 | 适用阶段 | 借鉴建议 |
|--------|-------------|---------|---------|
| **按需加载** | 工具/技能目录与内容分离 | Phase 2 | 适配器能力清单做成目录，主 Agent 选中后才加载完整适配器配置 |
| **白盒记忆** | Markdown 文件 + 混合检索 | Phase 4 | 记忆文件设计参考 OpenClaw 的目录结构，但索引机制（MEMORY.md + 类型分类）需自行设计 |
| **Dreaming 后台整理** | 模拟睡眠周期的三阶段记忆整理 | Phase 4 | 可借鉴记忆去重和整理思路，定期整理子 CLI 的会话归档 |
| **Bootstrap Context Scoping** | 子 Agent 仅接收 AGENTS.md + TOOLS.md | Phase 2 | 子 CLI 启动时控制上下文大小，避免 Token 浪费 |
| **Command Queue 车道** | 按 session 分 lane 串行 | Phase 2 | Session Manager 按 CLI 实例分队列，避免并发写脏数据 |
| **模型路由** | 按任务复杂度路由到不同模型 | Phase 3 | Dashboard 可显示各子 CLI 的任务类型分布 |
| **Skills 元数据格式** | YAML frontmatter + Markdown body | Phase 3 | 适配器配置文件可采用类似的 frontmatter 格式 |
| **Gateway 鉴权监控** | 全程后台常驻 + 实时监控 | Phase 3 | Dashboard 的监控面板设计参考 Gateway 的监控思路 |

### 7.10 本项目不能照搬的地方

| 差异点 | 原因 | 本项目的做法 |
|--------|------|------------|
| **不内置 Agent 推理** | OpenClaw 自包含 Brain（LLM 推理引擎），本项目不需要 | 主 Agent 本身是 CBC/Claude Code 等第三方 CLI，只管编排不管推理 |
| **不做 Skills 市场** | MyAgentsPlan 不面向终端用户，而是面向开发者 | 适配器即"技能"，按需编写安装，不走市场分发 |
| **不用 WebSocket 协议调子 Agent** | 第三方 CLI 不提供兼容的 WebSocket API，必须走 OS 进程操控 | `child_process.spawn` + `stream-json`（首选）/ PTY（备选） |
| **不做守护进程** | Phase 1-2 以验证可行性为目标 | 先跑通 CLI 主控入口，daemon 化放到后续阶段 |
| **不限制基础工具** | OpenClaw 的 Hands 有 4 个内置工具（Shell/Filesystem/Browser/HTTP），是设计选择 | 工具能力由被控 CLI 决定，本项目不做限制 |

### 7.11 与 OpenClaw 的集成可能性

**两种集成路径：**

#### 路径 A：作为 OpenClaw 的 Skill / MCP Server

OpenClaw 的 Skills 体系和 MCP 协议允许扩展 Agent 的能力。MyAgentsPlan 可以封装为一个 OpenClaw 的 Skill：

- OpenClaw Agent 将"派发任务给第三方 CLI"作为一个技能调用
- MyAgentsPlan 的调度层作为这个 Skill 或 MCP Server 的后端服务
- 填补了 OpenClaw 对第三方 CLI 深度管理的能力空缺

**适用场景**：OpenClaw 用户想在自己的 workflow 中调用多个第三方 CLI 协同工作。

#### 路径 B：作为 OpenClaw 的母级管理层

OpenClaw 本身也提供 CLI 入口（`claw` 命令），可以像其他 CLI 一样被 MyAgentsPlan 的适配器管理：

```
MyAgentsPlan（母级调度）
  ├── OpenClaw 实例 1  ← 作为子 Agent，负责渠道接入 + 个人助手任务
  ├── OpenClaw 实例 2  ← 作为子 Agent，负责另一组渠道
  ├── CBC 实例          ← 负责代码实现
  └── Claude Code 实例  ← 负责架构设计
```

**优势**：
- OpenClaw 擅长多渠道接入和用户交互，MyAgentsPlan 擅长多 Agent 编排
- 两者互补：OpenClaw 做"前端"（与用户对话、接入 IM），MyAgentsPlan 做"后端"（调度多个 CLI 并行执行）
- OpenClaw 已有的 Gateway + Session 管理能力可以直接复用

**两种路径不互斥**：可以先做 B（母级管理跑通），再封装为 A（作为 Skill 贡献回 OpenClaw 社区）。

### 7.12 总结

```
┌──────────────────────────────────────────────────────────────────┐
│                    OpenClaw ← → MyAgentsPlan                      │
│                                                                  │
│  相同灵魂：                                                       │
│    • Gateway 中枢 + Session 管理                                  │
│    • Node.js/TS + 模块化 + 可扩展                                 │
│    • 本地优先 + 白盒记忆                                          │
│                                                                  │
│  不同路径：                                                       │
│    • OpenClaw：自包含 Agent + Skills + MCP = AI 个人助手          │
│    • MyAgentsPlan：主 Agent 管多个第三方 CLI = AI 团队指挥官       │
│                                                                  │
│  核心差异化能力：                                                  │
│    对第三方 CLI 的控制深度 — 不仅是"能调"，而是生命周期管理          │
│    → 适配器模式 + OS 原语 + --resume 多轮 + 归档重建               │
│                                                                  │
│  最大共同挑战：                                                    │
│    Session 持久化 + 并发控制 + 状态同步                            │
│    → OpenClaw 的 Command Queue 车道、Workboard 看板是核心参考      │
│                                                                  │
│  最大不同挑战：                                                    │
│    MyAgentsPlan 需要深度"控制第三方 CLI 进程"                       │
│    → child_process.spawn + --resume + PTY + 跨厂商适配             │
└──────────────────────────────────────────────────────────────────┘
```
