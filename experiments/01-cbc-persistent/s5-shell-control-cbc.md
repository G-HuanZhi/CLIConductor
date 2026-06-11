# Shell 级进程控制实验（cbc 验证）

> 实验日期：2026-06-11
> 验证：用 Shell 原生原语统一管理 cbc 多 Worker 的后台生命周期

## 实验过程

### 1. 并行启动两个 Worker

```bash
# Worker 1: 记忆 SHELL_NUM=111
echo '{"type":"user","message":{"role":"user","content":"Remember: SHELL_NUM=111. Reply OK."}}' | \
  codebuddy -p --input-format stream-json --output-format stream-json -y \
  > /tmp/cbc-w1.txt 2>&1 &
W1_PID=$!  # → 22839

# Worker 2: 记忆 SHELL_NUM=222
echo '{"type":"user","message":{"role":"user","content":"Remember: SHELL_NUM=222. Reply OK."}}' | \
  codebuddy -p --input-format stream-json --output-format stream-json -y \
  > /tmp/cbc-w2.txt 2>&1 &
W2_PID=$!  # → 23434
```

### 2. 状态检查

```bash
sleep 12
kill -0 22839 2>/dev/null && echo "W1 running" || echo "W1 done"  # → W1 done
kill -0 23434 2>/dev/null && echo "W2 running" || echo "W2 done"  # → W2 done
```

### 3. 提取 session_id

```bash
grep '"session_id"' /tmp/cbc-w1.txt | head -1
# → session_id: "8171f0b3-bd9e-474a-9c87-38d9945ada3c"

grep '"session_id"' /tmp/cbc-w2.txt | head -1
# → session_id: "2e9ff435-f79f-49df-b1e5-34fb370421de"
```

### 4. 上下文恢复验证

```bash
# Worker 1 恢复
codebuddy -p --stream-json -y --resume "8171f0b3-..." \
  "What was SHELL_NUM?"
# → "111" ✅

# Worker 2 恢复
codebuddy -p --stream-json -y --resume "2e9ff435-..." \
  "What was SHELL_NUM?"
# → "222" ✅
```

## 结论

| 验证项 | 结果 |
|--------|------|
| Shell 后台启动 | ✅ `&` + `$!` 获取 PID |
| PID 存活检查 | ✅ `kill -0 <pid>` |
| 并行执行 | ✅ 两个 Worker 同时运行 |
| 输出捕获 | ✅ 重定向到文件 |
| session_id 提取 | ✅ 从 stream-json 解析 |
| --resume 上下文 | ✅ 各 Worker 记忆独立 |
| 无需 cbc --bg | ✅ Shell 层完全替代 |

**Shell 层 + --resume 方案对 cbc 完全可行。** 不再需要 `--bg`/`ps`/`logs`/`attach`/`kill`。
