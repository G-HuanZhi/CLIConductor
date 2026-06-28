# 已知问题

> 最后更新：2026-06-27

---

## 1. cbc 特殊命令（如 /model, /help）无法通过 stdin stream-json 发送

**现象**：在 Dashboard 输入 `/model deepseek-v4-pro` 等 cbc 斜杠命令，Worker 不会执行，因为当前消息格式是 `{"type":"user","message":{"role":"user","content":[{"type":"text","text":"/model ..."}]}}`，cbc 将其当作普通文本对话内容，而非 cbc 自身的命令。

**原因**：`--input-format stream-json` 模式下，所有 stdin 内容都被当作对话消息，不会触发 cbc 的斜杠命令解析器。

**解决方案（已验证）**：使用 `--resume <session_id> --model <new-model>` 重启 Worker，cbc 加载历史对话后以新模型继续。
- 已验证流程：spawn cbc → 发消息 → kill → `--resume` + `--model` → 新模型记得旧对话
- 实现：Python spike 新增 `POST /api/worker/:id/switch-model` 和 `switch-mode` 端点
- 局限：需重启 cbc 进程（有启动开销），但对话历史通过 `--resume` 完整保留
- 同样适用于 `--permission-mode`（对应 Shift+Tab 的模式切换）

**状态**：已解决（via restart + --resume）
