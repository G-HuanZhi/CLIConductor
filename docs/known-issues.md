# 已知问题

> 最后更新：2026-06-28

---

## 1. cbc 特殊命令（如 /model, /branch）无法通过 stdin stream-json 发送

**现象**：`--input-format stream-json` 模式下，所有 stdin 内容都被当作对话消息，不会触发 cbc 的斜杠命令解析器（/model、/branch、/rename 等）。

**原因**：stdin stream-json 协议只识别 `type: "user"` 消息，没有 "command" 消息类型。

**解决方案**：用 CLI 参数 + `--resume` 重启 Worker 实现等价功能。

### cbc 命令 ↔ CLI 参数映射表

| cbc 命令 | CLI 等效 | 实现端点 | 备注 |
|----------|---------|---------|------|
| `/model` | `--model <model>` | `switch-model` | ✅ 对话历史保留（via --resume） |
| Shift+Tab | `--permission-mode <mode>` | `switch-mode` | ✅ 对话历史保留 |
| `/branch` | `--resume <sid> --fork-session` | `branch` | ✅ 创建新 Worker，新 sessionId |
| `/rename` | 无（cbc session 无 name 字段） | `rename` | ✅ CLIConductor 自维护名称 |
| `/help` | `--help` | 无需实现 | 静态信息 |

**局限**：所有切换都需要重启 cbc 进程（冷启动 ~3-5 秒），但对话历史通过 `--resume` 保留。

**状态**：已解决
