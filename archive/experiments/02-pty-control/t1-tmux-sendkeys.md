# 1.2.1 tmux 操控另一个终端

> 实验日期：2026-06-11

## 实验目的

验证 tmux 操控另一个终端 session 的可行性。

## 环境检查

```bash
tmux -V
# → tmux: command not found
```

## 结论

**tmux 在 Windows 下不可用。** 此方案仅适用于 Mac/Linux 环境。

Windows 替代方案：
- node-pty（已验证可用）✅
- ConPTY API（node-pty 底层封装）
- PowerShell 的 Start-Process 配合管道

## 对本项目的影响

- 跨平台 PTY 操控：使用 node-pty 统一接口
- 不需要 tmux send-keys / capture-pane
- Session 管理用自定义方案（sessions.json + PID 追踪）
