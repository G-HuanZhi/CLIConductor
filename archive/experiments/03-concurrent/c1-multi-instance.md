# 1.3 多实例并发测试

> 实验日期：2026-06-11

## 1.3.1 两个 cbc 实例同时运行

### 测试

```bash
(codebuddy -p -y "What is 1+1?" &)
(codebuddy -p -y "What is 2+2?" &)
wait
```

### 结果

**两个实例并发运行成功。** 无报错、无冲突。interleaved 输出。

## 1.3.2 文件锁 / 资源冲突

### MEMORY.md 共享机制

CBC 的 auto memory 位于:
```
C:\Users\14709\.codebuddy\projects\e-code-MyProject-MyAgentsPlan\memory\
├── MEMORY.md          # 索引文件
└── user_preferences.md  # 用户偏好
```

### 隔离策略

为每个子 Agent 分配独立工作目录：

```
主 Agent:    e:\code\MyProject\MyAgentsPlan\
子 Agent 1:  e:\code\MyProject\MyAgentsPlan\sessions\agent-1\
子 Agent 2:  e:\code\MyProject\MyAgentsPlan\sessions\agent-2\
```

如果 CBC 基于项目路径哈希来定位 memory，不同子目录会映射到不同的 memory store，从而实现隔离。

### 验证方法

```bash
# 在不同目录中启动两个 cbc，验证 MEMORY.md 是否独立
cd sessions/agent-1 && codebuddy -p -y "Remember: X=1" &
cd sessions/agent-2 && codebuddy -p -y "What is X?" &  # 应该不知道 X
```

### 结论

| 测试项 | 结果 |
|--------|------|
| 并发启动 | ✅ 正常 |
| 并行执行 | ✅ 正常 |
| 共享目录内存 | ⚠️ 同一项目目录下共享 MEMORY.md |
| 独立目录隔离 | 待验证（Phase 2 实测） |

## 关键建议

1. Phase 2 为每个子 Agent 创建独立 `sessions/<agent-id>/` 工作目录
2. 通过 `--session-id` 显式管理 session
3. 子 Agent 目录放在 `.gitignore` 中，避免污染主项目
