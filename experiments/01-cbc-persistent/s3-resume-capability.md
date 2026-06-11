# 1.1.3 codebuddy resume 能力探索

> 实验日期：2026-06-11

## 实验目的

验证 codebuddy 的 `--resume`、`--continue`、`--fork-session` 能力，评估作为多轮对话机制的可行性。

## 可用命令

从 `codebuddy --help` 获取：

| 参数 | 说明 |
|------|------|
| `-c, --continue` | 继续最近一次对话 |
| `-r, --resume [sessionId]` | 恢复指定 session（无参数时交互选择） |
| `--fork-session` | 与 `--resume`/`--continue` 联用，创建新 session 分支 |
| `--session-id <uuid>` | 使用指定的 session ID |

## 测试结果

### --resume 测试（核心能力） ✅

```bash
# 第一轮
echo '{"type":"user",...}' | codebuddy -p --stream-json
→ session_id: 67872ffb-...

# 第二轮（上下文保持）
echo '{"type":"user",...}' | codebuddy -p --stream-json --resume 67872ffb-...
→ 正确记住了第一轮中设置的 "favorite color: blue" ✅
```

**结论**：完美支持，上下文完全保持。

### --continue 测试 ✅

```bash
codebuddy -p -c "What is my name?"
→ 正确引用了之前对话中的内容
```

**结论**：工作正常，加载最近一次对话。

### --fork-session 测试 ✅

```bash
echo '{"type":"user",...}' | codebuddy -p --stream-json --resume <id> --fork-session
→ 创建了新 session_id，继承了原上下文 ✅
```

**结论**：支持会话分支。

### ⚠️ Auto Memory 泄露

CBC 的持久记忆系统（`C:\Users\14709\.codebuddy\projects\...\memory\MEMORY.md`）会在不同 session 间共享状态：

```
Session A: set color=blue
Session B (fork from A): set color=green
Session A again: auto memory 更新为 green
```

**影响**：fork 后的 session 不是完全隔离的。对于 Agent 集群，每个子 Agent 需要有独立的工作目录来避免记忆污染。

## 关键结论

1. `--resume <session_id>` 是可靠的持久化多轮方案
2. 每次对话独立启动进程，通过 session_id 关联上下文
3. `--fork-session` 可实现任务分支和并行探索
4. ⚠️ 必须通过 **独立工作目录** 或 **禁用 memory** 来防止子 Agent 间的记忆污染

## 对本项目 Phase 2 的影响

推荐的多轮方案架构：

```
主 Agent:
  for each sub-task:
    1. spawn: codebuddy -p --stream-json [--resume <session_id>]
    2. capture session_id from init message
    3. read result from stream
    4. store session_id for next turn

Session 管理:
  - 每个子 Agent 有独立 workdir
  - sessions.json 记录 session_id + workdir 映射
  - 子 Agent 间通过独立 workdir 隔离记忆
```
