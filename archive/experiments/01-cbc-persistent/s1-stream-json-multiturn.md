# 1.1.1 --bg + stream-json 多轮测试

> 实验日期：2026-06-11
> 模型：deepseek-v4-pro

## 实验目的

验证 codebuddy `--bg` 模式和 `--input-format stream-json --output-format stream-json` 是否支持多轮对话。

## --bg 模式测试

### 测试：带 prompt 的 bg 会话

```bash
codebuddy --bg --name test1 -p "hello"
```

**结果**：后台启动成功，返回 PID 和日志路径。任务完成后立即退出。

```bash
codebuddy ps
# 运行期间显示 bg 类型会话
# 任务完成后从列表消失
```

### 测试：不带 prompt 的 bg 会话

```bash
codebuddy --bg --name test3 -y
```

**结果**：立即退出，日志为空。

### 结论

- `--bg` 模式是 "fire-and-forget" 任务执行，不是持久交互式会话
- 任务完成即退出，无法保持连接等待后续输入
- **不适合用于需要多轮交互的子 Agent 场景**

## stream-json 模式测试

### 测试：单轮对话

```bash
echo '{"type":"user","message":{"role":"user","content":"Hello"}}' | \
  codebuddy -p --input-format stream-json --output-format stream-json
```

**结果**：
- 成功返回 JSON 流，包含完整的对话生命周期
- `system.init` → `system.status` → `assistant` → `result`
- session_id 在 init 消息中提供

### 测试：管道多轮对话

```bash
(echo '{"type":"user","message":{"role":"user","content":"Remember: 42"}}';
 sleep 5;
 echo '{"type":"user","message":{"role":"user","content":"What number?"}}') | \
  codebuddy -p --input-format stream-json --output-format stream-json
```

**结果**：**失败**。进程 hang 超过 2 分钟后被 kill。管道方式无法实现多轮对话。

## --resume 多轮方案（可行）

### 测试：session 恢复

```bash
# 第一轮：创建 session
echo '{"type":"user","message":{"role":"user","content":"My color is blue. Reply OK."}}' | \
  codebuddy -p --input-format stream-json --output-format stream-json -y
# 捕获 session_id: 67872ffb-...

# 第二轮：恢复 session（上下文保持）
echo '{"type":"user","message":{"role":"user","content":"What is my favorite color?"}}' | \
  codebuddy -p --input-format stream-json --output-format stream-json -y \
  --resume 67872ffb-5bff-4a90-b2c7-0f578d94d3ef
# 结果：Your favorite color is blue. ✅
```

### 测试：--fork-session 分支

```bash
# 从原 session fork 出新分支
echo '{"type":"user","message":{"role":"user","content":"Actually my color is green."}}' | \
  codebuddy -p --input-format stream-json --output-format stream-json -y \
  --resume 67872ffb-... --fork-session
# 结果：创建了新 session_id，继承了原上下文
```

**注意**：CBC 的 auto memory 系统（MEMORY.md）会导致不同 session 间的状态泄露。fork 后的 session 间不是完全隔离的。

## 关键发现

| 测试项 | 结果 | 结论 |
|--------|------|------|
| --bg 持久会话 | 不支持 | 任务即完成即退出 |
| stream-json 单轮 | 支持 | 正常工作 |
| stream-json 管道多轮 | 不支持 | 进程 hang |
| --resume 多轮 | **支持** ✅ | 关键方案 |
| --fork-session 分支 | 支持 | 会话可分支 |

## 多轮方案结论

**可行方案**：`stream-json + --resume + 独立进程调用`

```
第1轮: spawn codebuddy -p --stream-json → 获取 session_id → 进程退出
第2轮: spawn codebuddy -p --stream-json --resume <session_id> → 上下文保持 → 进程退出
第3轮: spawn codebuddy -p --stream-json --resume <session_id> → 上下文保持 → 进程退出
...
```

每次对话独立启动进程，通过 `--resume` 保持上下文连续性。这是"短进程 + 持久上下文的方案，避免了 PTY 的复杂性。

**注意隐患**：Auto memory (MEMORY.md) 会在不同 session 间共享状态，需要关注并发安全问题。
