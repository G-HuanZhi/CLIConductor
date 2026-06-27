# 已知问题

> 最后更新：2026-06-27

---

## 1. cbc 特殊命令（如 /model, /help）无法通过 stdin stream-json 发送

**现象**：在 Dashboard 输入 `/model deepseek-v4-pro` 等 cbc 斜杠命令，Worker 不会执行，因为当前消息格式是 `{"type":"user","message":{"role":"user","content":[{"type":"text","text":"/model ..."}]}}`，cbc 将其当作普通文本对话内容，而非 cbc 自身的命令。

**原因**：`--input-format stream-json` 模式下，所有 stdin 内容都被当作对话消息，不会触发 cbc 的斜杠命令解析器。

**影响**：无法通过 Dashboard 动态切换模型、修改配置等。

**可能的解决方案**：
- 在 Worker 启动时通过 CLI 参数预设配置（`--model`, `--permission-mode` 等）
- 调查 cbc 是否有 `system` 类型的 JSON 消息格式来模拟斜杠命令
- Dashboard 单独提供参数选择界面，重启 Worker 时带新参数

**状态**：待解决
