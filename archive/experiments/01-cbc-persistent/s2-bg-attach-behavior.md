# 1.1.2 --bg + attach 行为测试

> 实验日期：2026-06-11

## 实验目的

验证 `codebuddy attach` 到运行中的 bg 会话的可行性。

## 测试结果

### 测试：attach 运行中的会话

```bash
# 启动一个会运行一段时间的 bg 任务
codebuddy --bg --name test-wait -y "Please wait for 10 seconds..."

# 立即 attach
codebuddy attach test-wait
```

**输出**：
```
Attaching to session test-wait (log: C:\Users\14709\.codebuddy\logs\test-wait.log)
Press Ctrl+C to detach (session will continue running)
```

**结果**：
- `attach` 启动了但需要交互式终端环境
- 在我们项目的 bash 管道环境中无法正常使用（依赖 TTY）
- ⚠️ 在生产环境中，通过 node-pty 应该可以正常 attach

### 测试：attach 已退出的会话

```bash
codebuddy attach test3  # test3 已完成并退出
```

**输出**：`Error: Session not found: test3`

### 测试：log 读取

```bash
codebuddy logs test-wait  # 运行中的会话
```

**输出**：`Error: Session not found: test-wait` (即使 ps 中可见)

```bash
cat C:\Users\14709\.codebuddy\logs\test-wait.log  # 直接读文件
```

**输出**：`I waited 10 seconds.` ✅

### 测试：codebuddy ps 能力

```bash
codebuddy ps
```

运行期输出示例：
```
PID       KIND            NAME              STATUS      CWD                             STARTED
1188      bg              test-wait         unknown     e:\code\MyProject\CLIConductor  11s ago
25768     interactive     -                 unknown     E:\code\MyProject\CLIConductor  49m ago
```

## 结论

| 功能 | 可行性 | 备注 |
|------|--------|------|
| attach 运行中会话 | 有条件 | 需要 TTY 环境，管道/bash 中无法使用 |
| attach 已退出会话 | 不支持 | 会话退出后不可 attach |
| codebuddy logs | 有 bug | 运行中会话报 "not found"，需直接读文件 |
| codebuddy ps | 支持 | 能看到 bg 类型和 interactive 类型会话 |
| codebuddy kill | 支持 | 可终止运行中的 bg 进程 |
| 直接读 log 文件 | 支持 | 最可靠的方式 |

## 对本项目的影响

- `attach` 不适合作为自动化方案（依赖 TTY）
- 读取 bg 任务的输出：直接读 `.codebuddy/logs/<name>.log` 文件
- `codebuddy ps` 可用于监控子 agent 状态
- `codebuddy kill` 可用于终止子 agent
