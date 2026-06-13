# 项目辛辣评价：MyAgentsPlan

> 这是一份客观甚至刻薄的评价，不客气地说出那些设计文档不会自己告诉你的话。

---

## 一、整体判断：这项目到底值不值得做？

**一句话结论：想法值钱，但执行状态是一辆画满了炫酷涂装却没有发动机的跑车。**

让我说清楚。你想用一个 Agent 调度多个第三方 CLI，从 OS 层做进程控制，这件事本身非常有价值。现有框架（OpenClaw、CAO）确实做不到你描述的那种深度的第三方 CLI 操控——多轮对话、进程生命周期管理、跨厂商统一抽象。这是真实存在的痛点，不是臆想出来的需求。

**但是**，项目目前的状态是：写了 3 万字的文档、做了 16 个实验、画了漂亮的架构图，然后 `packages/` 目录下全是 `.gitkeep`。整个项目用 20 个 commit 完成了所有能写的文档和所有能跑的玩具脚本，然后停在 Phase 2 的门口，零行产品代码。

这就像一个建筑师花了两天画了整栋大楼的设计图，然后指着空地告诉你"这就是我的大厦"。不，这是你的梦想，不是你的大厦。

**值不值得做：值得。但值得做不代表正在做。**

---

## 二、大方向规划的问题

### 2.1 Phase 规划过度超前

你的 Phase 划分是这样的：

- Phase 0-1：文档 + 实验 ✅
- Phase 2：最小可行系统
- Phase 3：Web Dashboard、QQ Bot、OpenClaw 集成
- Phase 4：消息队列、负载均衡、子 Agent 间协作

**问题**：Phase 3 和 Phase 4 是在给一个还没出生的婴儿规划大学专业。

Phase 2 的 5 个模块（Session Manager、CbcAdapter、Task Queue、CLI 入口、E2E 测试）连一行代码都没有，但文档里已经在详细讨论"与 OpenClaw 的两种集成路径"、"psmux vs node-pty 的终端层对比"、"子 Agent 间协作的消息队列选型"。这是典型的**过早设计**——在没有任何产品代码的情况下，你已经替未来的自己做了大量很可能永远用不到的决策。

**更好的做法**：把 Phase 2 做完再谈 Phase 3+。你现在最需要的不是"与 OpenClaw 集成"的架构图，而是一个能跑起来的 `npx myagentsplan spawn cbc-worker-1 --task "hello world"`。

### 2.2 消息网关是当前阶段最大的范围膨胀

你的架构第一层是"消息网关"——统一多入口（CLI/Web/QQ/邮件）、归一化消息格式、认证鉴权、消息排队、去重、限流。

**说真的，你现在需要这个吗？**

你的 Phase 2 目标是"启动 2 个子 cbc，并行派发任务"。这个目标**不需要消息网关**。你甚至不需要 HTTP 服务器。你只需要一个 CLI 命令：

```bash
myagentsplan run --task "重构 auth 模块" --workers 2
```

消息网关是你未来如果有 QQ Bot、Web 页面、邮箱入口时才需要的东西。你现在写消息网关的设计文档，等同于一个还在学走路的小孩在研究马拉松配速策略。

**建议**：把消息网关从 Phase 2 的范围里删掉。Phase 2 只需要一个 CLI 入口，stdin/stdout 就是你的"消息网关"。

### 2.3 "主 Agent"的角色定位模糊

架构里有一个"主 Agent（Brain）"，负责意图分析、任务拆分、并行分发、进度监控、结果汇总。文档里给了一个例子：

> 用户消息："帮我找出项目里所有未使用的 import，删掉它们"
> → 意图分析 → 任务拆分 → 并行分发 → 监控进度 → 汇总结果

**问题**：这个"主 Agent"是谁？是另一个 LLM？是你自己写的调度逻辑？

如果是另一个 LLM（比如你现在对话的这个 cbc），那它已经具备了意图分析和任务拆分能力——这是 LLM 的默认技能，不是你需要开发的。你不需要写"意图分析模块"，你只需要给 LLM 一个 prompt 告诉它"你是调度器，你有这些 worker 可用"。

如果是你自己写的调度逻辑（if-else 规则引擎），那这个"意图分析"就是个笑话——规则引擎做不了通用任务拆分。

**这是一个核心的定位模糊**：你不清楚"主 Agent"的智能边界在哪里。哪些依赖 LLM 自身能力？哪些需要你写代码？这个不搞清楚，Phase 2 的开发方向就会跑偏。

---

## 三、实验部分：质量参差不齐

### 3.1 实验设计有亮点

16 个实验、四套方案对比（A/B/C/D）、多轮验证，这个方法论本身是对的。尤其是在"先淘汰不可行方案"这件事上做得很好——--bg 方案、tmux 方案都在实验阶段被正确地毙掉了。

### 3.2 但实验结论的推广性存疑

你所有的实验都是在**你自己的 Windows 11 + Git Bash 环境**下跑的。实验结论说"child_process.spawn + --resume 是首选方案"，但这依赖于一个关键假设：**所有目标 CLI 都支持 `--resume` 参数**。

你验证了 CodeBuddy Code 的 `--resume`，标注了 Copilot CLI 的 `--continue` 和 Claude Code 的 `--resume` 是"待验证"。那 Aider 呢？Shell 适配器呢？如果一个 CLI 既不支持 `--resume` 也没有 `-p` 模式，你的 PTY 备选方案真的能在复杂场景下稳定工作吗？

**实验 14（e04-multiturn-pty）** 的结论是"3 轮消息均成功写入 TUI（AI 回复超时）"——**"AI 回复超时"是什么意思？** 你的 PTY 多轮对话实验并没有真正验证 AI 能否正确回复多轮消息，只验证了"能把消息写进去"。这就像测试一个聊天软件时说"消息发出去了（对方没收到）"。

### 3.3 实验代码质量问题

实验代码是**一次性脚本**——没有模块化、没有错误处理、没有测试框架、硬编码路径。这不是问题本身（实验就该快速验证），但问题是：**这些实验代码和未来的产品代码之间没有任何延续关系。**

你没有从实验中提炼出可复用的工具函数、没有建立 adapter 的原型、没有验证 stream-json 解析器的健壮性。实验做完了，结论写进文档了，代码扔在 `experiments/` 目录下再也不碰。这 16 个实验的实际产出只有文字结论，没有代码资产。

---

## 四、不成熟的地方

### 4.1 零工程基础设施

- **没有 `tsconfig.json`** — 你声称技术栈是 TypeScript，但连编译器配置都没有
- **没有构建系统** — `package.json` 里的 scripts 全是 `"echo '待实现'"`
- **没有测试框架** — 没有 jest/vitest/mocha，连 `.spec.ts` 的空文件都没有
- **没有 linter/formatter** — 没有 eslint、prettier
- **没有 CI/CD** — 没有 GitHub Actions、没有 pre-commit hook
- **没有环境管理** — 没有 `.env.example`、没有配置加载逻辑

你花了大量时间写架构文档和实验报告，但没有花 10 分钟跑 `tsc --init`。

### 4.2 依赖严重不足

`package.json` 只装了一个 `node-pty`。Phase 2 你需要但不限于：

- 一个 CLI 框架（commander / yargs / clipanion）—— 否则你的 CLI 入口只能手动解析 `process.argv`
- stream-json 解析库 —— 你需要解析 CBC 的流式输出
- 一个简单的 key-value 存储 —— 除非你真的想用 `fs.readFileSync` 管理 sessions.json
- 日志库 —— 除非 `console.log` 对你够用

这些问题都是**写第一行产品代码时就会立刻遇到的**，但你的项目里完全没有准备。

### 4.3 Session 管理设计过度

`sessions.json` 的设计有 13 个字段（id、name、adapterType、model、pid、sessionId、workdir、status、valuable、createdAt、stats.taskCount、stats.lastActiveAt），归档策略分了"活跃/无价值/有价值"三种，还有心跳机制、自动归档、重建流程。

**你真的需要所有这些吗？**

Phase 2 只需要回答一个问题："我启动了哪些 worker，它们还活着吗？" 一个 `Map<string, ChildProcess>` 加一个 `pid` 就够了。心跳机制、自动归档、三类策略、`valuable` 标记——这些是你有 50 个 worker 跑了一周之后才需要的东西。现在设计这些，纯属浪费时间。

**先让 2 个 worker 跑起来，再考虑怎么管理 50 个 worker。**

### 4.4 跨平台野心的虚伪性

文档里反复强调"Windows 11 + Git Bash 是主要环境"，但同时又说"macOS/Linux 可移植"。然后你选了 `child_process.spawn`（跨平台）作为首选方案，`node-pty`（需要编译原生模块）作为备选。

但实际上：
- `node-pty` 在 Windows 上的安装就是个噩梦——需要 Python、C++ 编译工具链、node-gyp
- 你的 bash wrapper 方案依赖 Git Bash 的 `bash.exe`
- `kill -0` 在 Windows 上的行为和 Linux 不完全一致

你嘴上说着"跨平台"，但实验全在 Windows 上跑的。**你没在 macOS 或 Linux 上跑过一个实验。** 这不是跨平台，这是"假设跨平台"。

---

## 五、明显更好的做法

### 5.1 停止写文档，开始写代码

这是最核心的建议。你现在拥有的文档量已经足够支撑到 Phase 3 了。再写任何文档之前，问自己："我现在写的这段话，能让我更快写出能跑的代码吗？" 如果答案是"不能"，就别写。

具体来说：
- **不要再扩展架构文档了** —— 当前版本已经足够
- **不要再分析外部项目了** —— CAO 和 OpenClaw 的分析已经过度深入
- **不要再做实验了** —— 16 个实验的结论已经够用了

### 5.2 Phase 2 应该砍掉 60% 的范围

你当前 Phase 2 规划了 5 个模块：

1. Session Manager — **保留，但极简化**：一个 `Map<string, {pid, process}>` 即可
2. CbcAdapter — **保留，这是核心**
3. 任务队列 — **砍掉**，Phase 2 不需要队列，顺序执行即可
4. CLI 入口 — **保留**
5. E2E 测试 — **砍掉**，Phase 2 用手动测试验证

Phase 2 真正的 MVP 只需要三样东西：
- 一个能 `spawn` 子 cbc 的函数
- 一个能向子 cbc 发送任务并读取 stream-json 输出的函数
- 一个能 `--resume` 继续对话的函数

这三样东西可以写在一个 200 行的 `index.ts` 里，不需要 monorepo、不需要 5 个 package、不需要任何架构分层。

### 5.3 先验证"主 Agent 能调度子 Agent"这个核心假设

你的整个项目建立在一个假设上：**让一个 AI（主 Agent）指挥另一个 AI（子 Agent）干活，效果比一个 AI 自己干更好。**

你从来没验证过这个假设。

做一个最简验证：拿当前这个 cbc session，让它 `spawn` 另一个 cbc 去做一个子任务，然后把结果拿回来。看看到底是：
- A) 主 Agent 自己干更快更好
- B) 主 Agent 调度子 Agent 更快更好

如果答案是 A，你的整个项目就失去了存在意义。**这个验证比所有 16 个实验都重要，但你没做。**

### 5.4 技术栈选型问题：为什么不直接用 Node.js 脚本？

你选择了 monorepo + TypeScript + workspaces 的项目结构。但 Phase 2 的目标是"启动 2 个子 cbc，并行派发任务"。这个目标用**一个 `.mjs` 文件**就能实现：

```javascript
import { spawn } from 'child_process';

function runWorker(name, task) {
  const cbc = spawn('codebuddy', ['-p', '--stream-json', '-y', task], {
    cwd: `./sessions/${name}`
  });
  cbc.stdout.on('data', d => console.log(`[${name}]`, d.toString()));
  return cbc;
}

const w1 = runWorker('worker-1', '找出所有未使用的 import');
const w2 = runWorker('worker-2', '运行测试并报告结果');
```

**50 行代码验证核心假设，然后再决定要不要建 monorepo。**

你现在建了 5 个 package 目录，每个里面只有一个 `.gitkeep`，这是典型的"过度工程化前置"——在为不存在的代码准备复杂的目录结构。

---

## 六、其他值得批判的点

### 6.1 文档冗余严重

同一份信息出现在至少 3 个地方：

- `project-overview.html` + `project-overview.md` + `README.md` 的架构部分
- `agent-cluster-architecture.md` + `README.md` 的 Phase 规划
- 实验结论同时出现在 `experiment-index.md`、`project-overview.md`、`agent-cluster-architecture.md`

每当你修改一个决策，你需要在 4-5 个文件里同步更新。这在只有文档没有代码的阶段还能手工维护，一旦开始写代码，文档同步就会变成噩梦。**你需要一个单一事实来源（Single Source of Truth）。**

### 6.2 resource-index.md 是信息坟场

70+ 个外部项目链接，按分类整理得很漂亮。但你真的读过其中几个？有多少个只是"看起来可能有用就收藏了"？

知识管理的铁律：**收藏不等于学会，索引不等于理解。** 这个文件给你的是一种"我已经做了充分调研"的虚假安全感，实际上它只是一个精心整理的书签文件夹。

### 6.3 对其他项目的分析带着"自证合理"的偏见

CAO 分析的核心结论是"不建议直接用 CAO，建议自己实现"。为了得出这个结论，你花了 370 行论证 Windows 兼容性、技术栈不一致、架构理念不同等问题。

但你没问过一个更基本的问题：**如果 CAO 已经是 511 个测试、84% 覆盖率的生产级项目，而你连一行产品代码都没写，凭什么认为"自己实现"是更优选择？**

即使 CAO 有 Windows 兼容问题，**改 CAO 的 tmux 依赖**（比如换成 node-pty 后端）可能比从零写一个完整的编排系统要快得多。你选择"自己实现"的理由更多是技术偏好（"我们统一用 TypeScript"），而不是工程理性（"改 CAO 的成本 > 重写的成本"）。

### 6.4 没有考虑过"CLI 厂商封杀"风险

你的方案依赖 `--resume`、`--stream-json` 这些参数。这些是 CLI 工具的内部实现细节，**不是公开 API**。厂商可以随时：

- 改变 `--resume` 的行为
- 修改 stream-json 的输出格式
- 限制并发实例数量
- 加入反自动化检测

你的整个系统建立在第三方 CLI 的实现细节上，而这些细节不在你的控制范围内。这不是说项目不应该做，但你至少应该在风险评估里提到这一点。

---

## 七、针对性建议

### 立即行动（本周）

1. **删掉 Phase 2 规划中 60% 的内容**。只保留：启动子进程、发送任务、读取输出。
2. **写一个 200 行的 `spike.ts`**，验证"主 Agent 调度子 Agent"这个核心假设。用你当前的 cbc session 作为主 Agent，通过 Bash 工具 spawn 另一个 cbc。
3. **跑 `tsc --init`**，安装 `commander` 和 `typescript`。
4. **停止写文档**。在 Phase 2 完成之前，不新增任何 `.md` 文件。

### 短期（两周内）

5. **实现一个能跑的 MVP**：`npx tsx src/index.ts run --task "hello world" --workers 1`
6. **不要建 monorepo 结构**。把所有代码写在一个文件或一个 package 里。等你需要第二个 adapter 时再拆分。
7. **补充缺失的基础设施**：tsconfig.json、构建脚本、基础日志。

### 中期（一个月内）

8. **验证跨平台**。在 macOS 或 Linux 上至少跑一次完整流程。
9. **写第一个 E2E 测试**。不是单元测试，是一个真正 spawn 子 cbc 的集成测试。
10. **重新评估 CAO**。当你有了能跑的 MVP 后，回过头来诚实地问：是继续自己开发，还是基于 CAO 改造？

### 长期方向调整

11. **把"消息网关"降级为 Phase 4 甚至 Phase 5**。你当前的产品形态不需要它。
12. **把"主 Agent"定位为 LLM + prompt，而不是自研调度引擎**。让 LLM 做它擅长的事（意图分析、任务拆分），你只做进程管理。
13. **接受"只支持 CBC"作为 Phase 2 的合理范围**。其他 CLI 适配器等你有了第一个稳定运行的 adapter 之后再考虑。
14. **建立单一事实来源**。砍掉 `project-overview.html` 和 `project-overview.md`，只保留 README 作为入口，详细内容分散到对应的架构/实验文档中。

---

## 八、最后的真话

你的研究能力很强。16 个实验、对 CAO 和 OpenClaw 的深度分析、清晰的架构文档——这些说明你有能力把一个复杂问题想清楚。

但你的执行有一个致命模式：**用研究和文档来替代编程。** 写文档比写代码容易得多，文档不会报错，文档不需要调试，文档永远看起来完美。但文档不能让子 Agent 跑起来。

你现在最需要的不是更多的分析、更多的实验、更多的架构图。你最需要的是**一行能跑的代码**。哪怕它很丑，哪怕它没有适配器模式，哪怕它硬编码了 cbc 路径。

**写出第一行产品代码，然后从那里开始迭代。** 这是你唯一需要做的事情。

---

> 以上评价基于 2026-06-12 的项目状态。如果 30 天后 `packages/core/src/` 下还是只有 `.gitkeep`，这份文档就是你的墓志铭。如果已经有能跑的代码了，这份文档就是你的纪念碑。
