# Copilot CLI --bg 实验（含网络验证）

> 实验日期：2026-06-11
> CLI 版本：GitHub Copilot CLI 1.0.61
> 参照文档：[copilot-cli DeepWiki](https://deepwiki.com/github/copilot-cli/3.3-session-management-and-history) | [brucetalk.com 分析](https://brucetalk.com/2026/05/17/copilot-cli-1-2/)

## 结论速览

**Copilot CLI 没有本地 `--bg` 后台 Worker 模式。** 它的"后台"概念与 CodeBuddy 完全不同：
- `&` = **云端委托**（GitHub Actions runner），不是本地后台
- "Background Agent" = **VS Code GUI 包装**，不是 CLI 功能
- 关闭终端 = 会话结束（除非手动用 tmux/screen）

## 本地实测

### --bg / --background

```bash
copilot --bg          # error: unknown option '--bg'
copilot --background  # error: unknown option '--background'
```

### 多轮对话

```bash
copilot -p "My favorite number is 42. Just reply OK." --silent --yolo   # → OK
copilot --continue -p "What is my favorite number?" --silent --yolo     # → 42 ✅
```

## 完整功能对比（本地实测 + 网络验证）

| 功能 | CodeBuddy Code | Copilot CLI |
|------|---------------|-------------|
| `--bg` 本地后台 Worker | ✅ | ❌ |
| `&` 云端委托 | ❌ | ✅ (GitHub Actions) |
| `-p` 非交互模式 | ✅ | ✅ |
| `--continue` | ✅ | ✅ (按 CWD 智能选择) |
| `--resume` | ✅ | ✅ (支持 ID/名称/前缀) |
| `--fork-session` | ✅ | ✅ (`/fork` 交互命令) |
| 一键允许 | `-y` | `--yolo` / `--allow-all` |
| 静默输出 | 默认 | `--silent` |
| JSON 输出 | `stream-json` | `--output-format json` (JSONL) |
| `ps` 列出进程 | ✅ | ❌ |
| `logs` 查看日志 | ✅ | ❌ |
| `attach` 接入 | ✅ | ❌ |
| `kill` 终止 | ✅ | ❌ |
| 交互式 Session 浏览 | `/resume` 列表 | `/sessions` + Session Picker |
| Session 删除 | 删文件 | `/session delete <id>` |
| Session 导出 | `--share` | `/export` |
| Session 存储 | sessions.json | `~/.copilot/sessions/` (JSONL) + SQLite |

## Copilot 的三种"后台"

### 1. `&` 云端委托（不等于本地后台）

在交互模式下用 `&` 前缀可以把任务推到 GitHub Cloud Actions runner：
```
copilot> & 重构整个项目
```
- ✅ 本地关机也继续运行
- ❌ 不是本地进程，无法本地 ps/attach
- ❌ 有延迟、有额度限制

### 2. VS Code Background Agent（GUI 包装）

VS Code Chat 视图中选择 "Copilot CLI" 作为 session target 时，VS Code 会在后台启动一个 Copilot CLI 进程并通过 SDK 通信。这是 VS Code 的 GUI 包装，**不是 CLI 本身的功能**。

### 3. tmux/screen（通用方案）

和任何 CLI 一样，可以用 tmux/screen 做终端级别的后台运行。但 Copilot CLI 本身不内置 session 管理命令（无 ps/logs/attach/kill）。

## 交互模式下的 Session 管理（仅 TUI 内可用）

```
/sessions              → 浏览和管理历史 session
/session delete <id>   → 删除指定 session
/session delete-all    → 清除所有历史
/fork                  → 复制当前 session
/export                → 导出 session 历史
/clear                 → 放弃当前 session
/compact               → 手动触发上下文压缩
```

**关键限制**：这些命令只在交互式 TUI 内部可用，无法从外部脚本/CLI 调用。

## 对本项目的影响

| 结论 | 说明 |
|------|------|
| Copilot 不能做本地 bg Worker | 无 `--bg` 无 ps/logs/attach/kill |
| 只能走独立进程方案 | `-p` + `--continue` 保持上下文 |
| 适配器需用 SDK（更好）或 CLI | Copilot SDK 提供 JSON-RPC 程序化控制 |
| Session 管理需自建 | 外部无 ps 命令，需自维护 session 注册表 |
| `&` 云端委托不适合作为子 Agent | 有延迟且不可控 |
