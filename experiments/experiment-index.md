# 实验报告索引

> 共 16 项实验，全部完成。按阶段分组，每项标注结果和一句话结论。

---

## 初始探索

| # | 实验 | 文件 | 结果 | 结论 |
|---|------|------|:----:|------|
| 0 | --print vs --bg 基础能力探索 | [cbc-multi-cli-experiment.md](./cbc-multi-cli-experiment.md) | ✅ | --print 单轮可用，--bg 方案待验证 |

---

## 01-cbc-persistent — CBC 持久化 Session

| # | 实验 | 文件 | 结果 | 结论 |
|---|------|------|:----:|------|
| 1 | --bg + stream-json 多轮测试 | [s1](./01-cbc-persistent/s1-stream-json-multiturn.md) | ❌ | --bg 是 fire-and-forget，管道多轮 hang，--resume 可行 |
| 2 | --bg + attach 行为测试 | [s2](./01-cbc-persistent/s2-bg-attach-behavior.md) | ⚠️ | attach 需 TTY，直接读 log 文件更可靠 |
| 3 | --resume 能力探索 | [s3](./01-cbc-persistent/s3-resume-capability.md) | ✅ | --resume 完美保持上下文；--fork-session 可分支 |
| 4 | Copilot CLI --bg 等价能力 | [s4](./01-cbc-persistent/s4-copilot-bg.md) | ❌ | Copilot 无本地 --bg，只能走 -p + --continue |
| 5 | Shell 级进程控制验证 | [s5](./01-cbc-persistent/s5-shell-control-cbc.md) | ✅ | & + $! + kill -0 完全替代 --bg |

---

## 02-pty-control — PTY 终端操控

| # | 实验 | 文件 | 结果 | 结论 |
|---|------|------|:----:|------|
| 6 | PTY 操控知识文档 | [guide](./02-pty-control/pty-control-guide.md) | ✅ | 终端/Shell/PTY/ConPTY 概念整理 |
| 7 | tmux 操控 | [t1](./02-pty-control/t1-tmux-sendkeys.md) | ❌ | Windows 不可用 |
| 8 | node-pty + powershell/cmd/cbc | [t2](./02-pty-control/t2-node-pty.js) | ✅ | 能发送命令、捕获输出 |
| 9 | node-pty bash 包装修复 | [t2-v2](./02-pty-control/t2-node-pty-v2.js) | ⚠️ | 直接 spawn codebuddy 失败，需 bash 包装 |
| 10 | ANSI 输出清洗工具 | [t3](./02-pty-control/t3-output-cleaner.js) | ✅ | stripAnsi 有效剥离控制序列 |
| 11 | PTY 启动交互式 cbc | [e01](./02-pty-control/e01-interactive-cbc.js) | ✅ | TUI 完整捕获（边框、提示符、模型名） |
| 12 | / 指令通过 PTY 发送 | [e02](./02-pty-control/e02-slash-commands.js) | ✅ | /help /model /clear 均可发送 |
| 13 | Tab/Ctrl+C 特殊按键 | [e03](./02-pty-control/e03-special-keys.js) | ✅ | Tab → thinking 切换；Ctrl+C 可发送 |
| 14 | 多轮 PTY 对话 | [e04](./02-pty-control/e04-multiturn-pty.js) | ✅ | 3 轮消息均成功写入 TUI（AI 回复超时） |
| — | PTY 全 I/O 操控总结 | [summary](./02-pty-control/pty-experiment-summary.md) | ✅ | 核心 I/O 路径已验证，可用于适配器开发 |

---

## 03-concurrent — 多实例并发

| # | 实验 | 文件 | 结果 | 结论 |
|---|------|------|:----:|------|
| 15 | 多实例并发 + 记忆隔离 | [c1](./03-concurrent/c1-multi-instance.md) | ✅ | 两实例并发正常，独立 workdir 可隔离 |
| 16 | MEMORY.md 并发写入冲突 | [c2](./03-concurrent/c2-resource-conflicts.js) | ⚠️ | 同一目录下 auto memory 共享，需独立 workdir |

---

## 核心结论汇总

### 已淘汰

| 方案 | 原因 |
|------|------|
| A: --bg 后台 Worker | CBC 的 --bg 是 fire-and-forget；Copilot 没有本地 --bg |
| tmux 操控 | Windows 不可用 |

### 已采纳

| 方案 | 用途 |
|------|------|
| D: child_process.spawn + --resume | **Phase 2 首选** — OS 原语统一管理，跨 CLI 兼容 |
| C: stream-json + --resume | 底层技术，被方案 D 封装 |
| B: PTY (node-pty + bash) | **备选** — 用于无 --resume 的 CLI |

### 关键发现

1. `--resume <session_id>` 是 CBC 多轮对话的核心机制
2. OS 原语 (PID/kill -0/wait) 可完全替代 CLI 自身的进程管理
3. PTY 通过 bash wrapper 可在 Windows 上操控交互式 CLI
4. 每个子 Agent 必须有独立 workdir 避免 MEMORY.md 污染
5. Copilot CLI 只能走 -p + --continue，无本地后台能力

---

## 参考

- [项目总览 (HTML)](../docs/planning/project-overview.html)
- [项目总览 (Markdown)](../docs/planning/project-overview.md)
- [架构设计](../docs/architecture/agent-cluster-architecture.md)
- [进程控制方案](../docs/architecture/shell-process-control.md)
