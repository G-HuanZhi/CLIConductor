# cbc (CodeBuddy CLI) 参考文档

**最后更新**: 2026-07-01

cbc 是 CLIConductor 目前唯一支持的 CLI 工具。本文档记录 cbc 的可接受参数、事件协议、模型清单和适配器实现细节，作为开发和接入新 adapter 的事实依据。

---

## 一、CLI 参数

### 1.1 基础参数（`base_args`）

每次启动 cbc 进程的固定命令行前缀：

```bash
cbc.cmd -p --output-format stream-json --input-format stream-json -y
```

| 参数 | 含义 |
|---|---|
| `-p` | 非交互模式（print mode，输出后退出） |
| `--output-format stream-json` | stdout 输出为 JSON 行流 |
| `--input-format stream-json` | stdin 输入为 JSON 行流 |
| `-y` | 跳过所有权限确认 |

对应 `CbcAdapter.base_args()` → `src/adapters/cbc.py:45`

### 1.2 模型参数（`model_args`）

```bash
--model <model_name>
```

- 始终传递，通过 `s.model or DEFAULT_MODEL` 解析
- 无无模型参数时的 fallback：`deepseek-v4-flash`

对应 `CbcAdapter.model_args(s)` → `src/adapters/cbc.py:49`

### 1.3 思考模式（`thinking_args`）

cbc v2.66.0 起 `alwaysThinkingEnabled` 默认为 `true`，关闭时**必须显式传 `--settings`**，否则始终启用。

```bash
# 关闭思考
--settings '{"alwaysThinkingEnabled": false}'

# 开启思考（默认行为，无需传参）
（无额外参数）
```

| 机制 | 配置方式 | 默认值 | 作用 |
|---|---|---|---|
| `alwaysThinkingEnabled` | `--settings` CLI | `true`（v2.66.0 起） | 全局思考开关 |
| `MAX_THINKING_TOKENS` | 环境变量 | 不生效 | 思考的 token 预算上限 |

来源：`D:\node_npm\node_global\node_modules\@tencent-ai\codebuddy-code\dist\web-ui\docs\cn\cli\settings.md`

对应 `CbcAdapter.thinking_args(s)` → `src/adapters/cbc.py:52`

### 1.4 Effort 参数（`effort_args`）

控制推理深度的 `--effort <level>` 参数。**合法值经 cbc CLI 逐值实测验证**：

| 值 | 实测结果 | 含义（推断） |
|---|---|---|
| `none` | ✅ | 无额外推理 |
| `off` | ✅ | 关闭增强推理（等同默认快速模式） |
| `auto` | ✅ | 自动选择推理深度（等同清除 settings.json 中的 `reasoningEffort`） |
| `low` | ✅ | 简单任务，快速响应 |
| `medium` | ✅ | 中等复杂度，日常编码推荐 |
| `high` | ✅ | 多文件重构、复杂 bug |
| `xhigh` | ✅ | 架构决策、极高推理深度 |
| `max` | ✅ | 最大推理投入 |
| `minimal` | ❌ | **cbc 报 `400 invalid parameter value`** |

**验证命令**（2026-07-01 执行）：
```bash
for val in none off auto low medium high xhigh max minimal; do
    echo -n "$val: "; cbc --effort $val -p "say hello" 2>&1 | head -1
done
```

只有 `minimal` 被 cbc 拒绝，其余全部通过。

对应 `CbcAdapter.effort_args(s)` → `src/adapters/cbc.py:60`  
对应 `CbcAdapter.effort_values` → `src/adapters/cbc.py:28`  
对应 `CbcAdapter._VALID_EFFORT` → `src/adapters/cbc.py:58`

### 1.5 权限模式（`permission_mode_args`）

```bash
--permission-mode <mode>
```

仅当 session 设置时传递。

| 值 | 含义 | 前端 label |
|---|---|---|
| `""` | 默认（dontAsk，需要用户确认操作） | `mode…` |
| `default` | 等同空字符串 | `default` |
| `acceptEdits` | 自动接受编辑 | `acceptEdits` |
| `bypassPermissions` | 绕过所有权限 | `bypass` |
| `plan` | 仅规划模式（不执行） | `plan` |
| `dontAsk` | 不询问确认，直接执行 | `dontAsk` |

来源：cbc `--help` + 前端 options 列表

对应 `CbcAdapter.permission_mode_args(s)` → `src/adapters/cbc.py:68`  
对应 `CbcAdapter.permission_modes` → `src/adapters/cbc.py:29`

### 1.6 会话恢复（`resume_args`）

```bash
--resume <cbc_session_id>
```

仅当 session 有 `cbc_session_id` 时传递。用于重启后恢复对话上下文。

### 1.7 Fork 分支（`fork_args`）

```bash
--fork-session
```

创建当前会话的分支副本。当新 session 没有 `cbc_session_id` 时，需同时传 `--resume ""`：

```bash
--resume "" --fork-session
```

对应 `CbcAdapter.fork_args(s)` → `src/adapters/cbc.py:78`

### 1.8 参数组装顺序（`build_spawn_args`）

```bash
cbc.cmd -p --output-format stream-json --input-format stream-json -y \
    --model <model> \
    [--permission-mode <mode>] \
    [--effort <level>] \
    [--settings '{"alwaysThinkingEnabled": false}'] \
    [--resume <session_id>] \
    [extra_args...]
```

`--resume` 必须在 `--fork-session` 之前（cbc 要求）。

对应 `CbcAdapter.build_spawn_args(s, extra_args)` → `src/adapters/cbc.py:84`

---

## 二、stdin/stdout 事件协议

### 2.1 stdin 输入格式

每行一个 JSON：

```json
{
  "type": "user",
  "message": {
    "role": "user",
    "content": [{"type": "text", "text": "用户消息"}]
  }
}
```

对应 `CbcAdapter.encode_user_message(text)` → `src/adapters/cbc.py:98`

### 2.2 stdout 输出格式

每行一个 JSON 事件。cbc 的 `--output-format stream-json` 保证有效行一定为合法 JSON。

#### system/init 事件（启动信息）

```json
{
  "type": "system",
  "subtype": "init",
  "session_id": "abc123...",
  "model": "deepseek-v4-pro"
}
```

对应解析：`is_init_event` / `extract_session_id` / `extract_model`

#### assistant 事件（AI 回复）

```json
{
  "type": "assistant",
  "message": {
    "role": "assistant",
    "content": [
      {"type": "thinking", "thinking": "思考内容..."},
      {"type": "text", "text": "回复文本"},
      {"type": "tool_use", "name": "Bash", "input": {"cmd": "ls"}}
    ]
  }
}
```

`content` 块可包含 `thinking`、`text`、`tool_use` 三种类型，数量不定。

对应解析：`is_assistant_event` → `extract_assistant_blocks` → 转为统一格式 `[{"role": "assistant"|"thinking"|"tool", "content": str}]`

#### result 事件（任务完成）

```json
{
  "type": "result",
  "result": "最终文本（可能为 null）",
  "is_error": false
}
```

对应解析：`is_result_event` / `is_result_error` / `extract_result_text`

注意：cbc 有时**只在 result 里给最终文本**，不在 assistant 事件里。worker.py 的 `_read_stdout` 会补这最后一条（防重复）。

---

## 三、模型清单

以下为 cbc 当前支持的模型，来源：`CbcAdapter.supported_models` → `src/adapters/cbc.py:18`

```
glm-5.2
glm-5.1
glm-5.0
glm-5.0-turbo
glm-5v-turbo
glm-4.7
minimax-m3
minimax-m2.7
kimi-k2.7
kimi-k2.6
kimi-k2.5
hy3-preview
deepseek-v4-pro
deepseek-v4-flash    ← 默认模型
deepseek-v3-2-volc
custom-local:deepseek-v4-pro
```

---

## 四、配置常量（环境变量）

| 变量 | 用途 | 默认值 |
|---|---|---|
| `CLICONDUCTOR_CBC_PATH` | cbc.cmd 路径 | `D:\node_npm\node_global\cbc.cmd` |

对应 `CbcAdapter._CBC_PATH` → `src/adapters/cbc.py:38`

---

## 五、adapter 映射

所有 cbc 特有逻辑集中于 `src/adapters/cbc.py`（160 行）。worker.py 不再直接感知 cbc。

| 类别 | 原 worker.py 函数（已删） | 现 CbcAdapter 方法 |
|---|---|---|
| 基础参数 | `_base_args()` | `base_args()` |
| 模型参数 | 内联于 `_spawn_process` | `model_args(s)` |
| 思考参数 | `_thinking_args(s)` | `thinking_args(s)` |
| Effort 参数 | `_effort_args(s)` | `effort_args(s)` + `_VALID_EFFORT` 校验 |
| 权限模式 | 内联于 `_spawn_process` | `permission_mode_args(s)` |
| 会话恢复 | 内联于 `_spawn_process` | `resume_args(s)` |
| Fork 分支 | 内联于 `branch_worker` | `fork_args(s)` |
| 参数组装 | 内联于 `_spawn_process` | `build_spawn_args(s, extra_args)` |
| stdin 编码 | 内联于 `_consumer` | `encode_user_message(text)` |
| 事件解析 | 内联于 `_read_stdout` | `parse_event` / `is_init_event` / `extract_session_id` / ... |
| Takeover 命令 | 内联于 `api_takeover` | `takeover_command(s)` |

---

## 六、前端配置驱动

`GET /api/adapter/config` 返回当前默认 adapter 的配置，前端据此动态渲染选择器：

```json
{
  "models": ["glm-5.2", "glm-5.1", ...],
  "defaultModel": "deepseek-v4-flash",
  "effortValues": ["none", "off", "auto", "low", "medium", "high", "xhigh", "max"],
  "permissionModes": [
    {"value": "", "label": "mode…"},
    {"value": "default", "label": "default"},
    ...
  ]
}
```

前端 `init()` → `fetch('/api/adapter/config')` → 动态 `buildModelSelect()` / `buildModeSelect()` / `buildEffortSelect()`。

---

## 七、文档来源

- cbc settings 文档：`D:\node_npm\node_global\node_modules\@tencent-ai\codebuddy-code\dist\web-ui\docs\cn\cli\settings.md`
- cbc 环境变量文档：`D:\node_npm\node_global\node_modules\@tencent-ai\codebuddy-code\dist\web-ui\docs\cn\cli\env-vars.md`
- cbc release notes v2.66.0：`D:\node_npm\node_global\node_modules\@tencent-ai\codebuddy-code\dist\web-ui\docs\cn\cli\release-notes\v2.66.0.md`
- 在线设置文档：https://www.codebuddy.ai/docs/zh/cli/settings
- 在线 CLI 参考：https://www.codebuddy.ai/docs/zh/cli/cli-reference
- cbc effort 参数逐值实测：`cbc --effort <val> -p "say hello"`（2026-07-01 执行）
- 适配器源代码：`src/adapters/cbc.py`、`src/adapters/base.py`
