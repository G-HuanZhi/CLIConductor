# 思考模式控制机制

## cbc 源码控制逻辑

cbc（CodeBuddy Code）的思考模式由两个独立机制控制：

| 机制 | 配置方式 | 默认值 | 作用 |
|------|----------|--------|------|
| `alwaysThinkingEnabled` | settings.json / `--settings` CLI | `true`（v2.66.0 起） | 全局思考开关 |
| `MAX_THINKING_TOKENS` | 环境变量 | 不生效 | 思考的 token 预算上限 |

**`alwaysThinkingEnabled`**：控制 cbc 是否启用思考模式。v2.66.0 起默认 `true`，即所有对话默认开启思考。
此设置可通过 `--settings '{"alwaysThinkingEnabled": false}'` 在命令行中覆盖。

**`MAX_THINKING_TOKENS`**：当 `alwaysThinkingEnabled` 为 `true` 时，控制思考过程的 token 预算。
设为此值后，cbc 在思考阶段的输出不会超过该 token 数。不设置时无限制，思考过程跟随模型默认行为。

> **注意**：`MAX_THINKING_TOKENS=0` 不具"禁用思考"语义，只是将预算设为 0，实际效果不明。
> 正确禁用思考的方式是 `--settings '{"alwaysThinkingEnabled": false}'`。

## 本项目处理逻辑

文件：`src/worker.py`

### `_thinking_args(s: Session) -> list[str]`
- 当 `s.always_thinking_enabled` 为 `false` 时，追加 `--settings '{"alwaysThinkingEnabled": false}'` 命令行参数，**显式关闭思考**
- 当为 `true` 时不追加，依赖 cbc 默认行为（思考开启）

### `_effort_args(s: Session) -> list[str]`
- 仅当 `s.always_thinking_enabled` 为 `true` 且 `s.effort` 非空时，追加 `--effort <level>` 参数

### 调用链路
三个 spawn 路径均调用以上函数：
1. `create_worker`：首次创建 worker
2. `_spawn_process`：restart / respawn worker
3. `branch_worker`：fork worker

### 默认行为
Session 创建时 `always_thinking_enabled` 默认为 `false`，`effort` 默认为 `""`。

因此**默认命令行**为：
```bash
cbc.cmd -p --output-format stream-json --input-format stream-json -y --model <model> --settings '{"alwaysThinkingEnabled": false}'
```

勾选 Think 后：
```bash
cbc.cmd -p --output-format stream-json --input-format stream-json -y --model <model> --effort medium
```

## 文档来源
- `D:\node_npm\node_global\node_modules\@tencent-ai\codebuddy-code\dist\web-ui\docs\cn\cli\env-vars.md`
- `D:\node_npm\node_global\node_modules\@tencent-ai\codebuddy-code\dist\web-ui\docs\cn\cli\settings.md`
- `D:\node_npm\node_global\node_modules\@tencent-ai\codebuddy-code\dist\web-ui\docs\cn\cli\release-notes\v2.66.0.md`
