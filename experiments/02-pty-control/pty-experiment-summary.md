# PTY 全 I/O 操控实验报告

> 实验日期：2026-06-12
> 验证场景：Windows 11 + Git Bash + node-pty + CodeBuddy Code v2.105.2
> 涉及实验：E01~E04

---

## E01: PTY 启动交互式 cbc

**验证目标**：node-pty spawn bash → bash 内启动 `codebuddy`（交互模式），捕获完整输出。

**实验条件**：bash wrapper 方式（`pty.spawn(bash.exe, [], ...)` → `shell.write('codebuddy\n')`）

**验证结果**：

| 维度 | 结果 |
|------|------|
| 交互式 cbc 启动 | ✅ 成功 — bash PTY 中 `codebuddy` 正常启动，TUI 完整呈现 |
| 启动画面捕获 | ✅ 含版本号、Tips、Recent activity、模型名、Web UI URL |
| 提示符捕获 | ✅ `> ` 提示符被完整捕获 |
| 用户输入发送 | ✅ `"Say hello in exactly one word"` 被发送并在 TUI 中回显 |
| AI 回复读取 | ⚠️ 成功 — 需等待 20s+（AI 生成时间） |
| /clear 发送 | ✅ 可执行 |

**关键发现**：
- PTY 可完整捕获 TUI 输出（含边框、进度条、ANSI 颜色）
- AI 回复时间比 --print 模式长（多了一层 bash → codebuddy 传递）
- Bash 包装是 Windows 上唯一的可行路径（直接 spawn codebuddy 失败）

---

## E02: 发送 / 指令

**验证目标**：通过 PTY 向交互式 cbc 发送 `/help`、`/model`、`/clear` 等指令并读取响应。

**验证结果**：

| 指令 | 结果 | 说明 |
|------|------|------|
| `/help` | ✅ 发送成功（TUI 回显） | AI 响应需要较长等待 |
| `/model` | ✅ 发送成功 | 可在输出中看到模型列表 |
| `/clear` | ✅ 可执行 | 无回显输出（正常行为） |

**关键发现**：
- `/ 指令` 在 PTY 中作为普通文本发送即可，无需特殊转义
- `/clear` 是最快的指令（本地执行，无需 AI 生成）

---

## E03: 发送特殊按键

**验证目标**：Tab（补全/切换）、Ctrl+C（中断）通过 PTY 发送。

**验证结果**：

| 按键 | ASCII | 结果 |
|------|-------|------|
| Tab | `\t` (0x09) | ✅ **thinking on/off 切换成功** — 输出明确显示 "Thinking off (tab to toggle)" |
| Ctrl+C | `\x03` | ⚠️ 已发送，但 AI 响应尚未开始，未观察到中断效果 |

**关键发现**：
- Tab 键 `\x09` 在 PTY 中成功触发 cbc 的 thinking 模式切换
- Ctrl+C 中断需要 AI 正在生成时发送才能验证效果
- 方向键在之前的 t2-node-pty.js 中已验证对 cmd.exe 有效

---

## E04: 多轮 PTY 对话

**验证目标**：同一 PTY 进程内连续多轮对话。

**验证结果**：

| 维度 | 结果 |
|------|------|
| 第一轮发送 | ✅ "Say hello in one word" 被写入 TUI |
| 第二轮发送 | ✅ "What is the previous user message?" 被写入 TUI（有上下文） |
| 第三轮发送 | ✅ "Calculate 15+27" 被写入 TUI |
| AI 回复读取 | ⚠️ 超时 — 3 轮 AI 生成在 130s 内未完成 |

**说明**：E04 验证了 PTY 可向同一交互式 cbc 进程连续发送多轮消息（3 轮均成功写入 TUI 提示符），但 timeout 130s 不足以等待 3 轮完整的 AI 生成 + 回复。实际场景中应适当延长超时，或使用更短 prompt 以减少生成时间。

---

## 实验总结

| 能力 | 状态 | 说明 |
|------|------|------|
| TUI 输出捕获 | ✅ 已验证 | 边框、ANSI、提示符均完整捕获 |
| 文本输入发送 | ✅ 已验证 | 普通文本和 / 指令均可发送 |
| Tab 键 | ✅ 已验证 | thinking 模式切换 |
| Ctrl+C 中断 | ⚠️ 部分验证 | 序列可发送，中断效果待在有生成时验证 |
| 方向键 | ✅ 之前已验证 | t2-node-pty.js 中对 cmd.exe 有效 |
| 多轮对话上下文 | ⚠️ 运行中 | |
| 输出结束判定 | ⚠️ 需设计策略 | 可监测新提示符 `>` 或连续静默超时 |
| 无 --resume CLI | ⚠️ 待扩展 | Copilot/Aider 需相同 PTY 路径 |
