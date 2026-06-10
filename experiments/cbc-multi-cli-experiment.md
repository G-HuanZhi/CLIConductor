# CBC 多 CLI 操控实验记录

> 实验日期：2026-06-10  
> 目录：`d:\notes\Ablaze`  
> 当前模型：deepseek-v4-pro

## 一、实验目的

验证一个 CodeBuddy Code (cbc) 实例是否能操控其他 cbc 实例，并探索其能力边界：

1. 是否能用代码/工具切换当前会话的模型
2. 是否能启动并操控其他 cbc 实例
3. 子 cbc 是否能使用不同模型
4. 是否支持并发和链式调用
5. 是否支持持久会话和独立窗口

---

## 二、实验过程与结论

### 实验 1：能否在对话中切换模型

**尝试方式**：通过 Bash / PowerShell / ToolSearch 寻找模型切换工具

**结论**：**不能。**

- `/model <名称>` 是唯一的切换方式，属于 CLI 层斜杠命令
- 该命令未被暴露为任何可调用工具（含 deferred tools）
- 只有用户手动输入 `/model` 才能切换
- `codebuddy --help` 中确实有 `--model` 参数，但仅用于启动新会话

---

### 实验 2：一个 cbc 能否启动另一个 cbc

```bash
codebuddy --model glm-5.1 --print "用一句话介绍你自己"
```

输出：
```
我是由 GLM-5.1 模型驱动的 CodeBuddy Code，一个专注于软件工程任务的交互式 CLI 助手。
```

**结论**：**能。**

- 通过 `codebuddy --print "prompt"` 非交互模式可以启动子 cbc
- 子 cbc 处理 prompt 后返回文本输出，进程结束

---

### 实验 3：子 cbc 能否使用不同于主会话的模型

```bash
# 当前会话: deepseek-v4-pro
codebuddy --model kimi-k2.5 --print "你的模型是什么？当前工作目录是什么？"
```

输出：
```
我的模型是 **Kimi-K2.5**，当前工作目录是 **d:\notes\Ablaze**。
```

**结论**：**能。**

- `--model` 参数可以为每个子 cbc 指定不同模型
- 当前可用的模型列表（`/model list`）：

```
GLM-5.1, GLM-5.0, GLM-5.0-Turbo, GLM-5v-Turbo, GLM-4.7
MiniMax-M3, MiniMax-M2.7
Kimi-K2.6, Kimi-K2.5
Hy3 preview
Deepseek-V4-Pro, Deepseek-V4-Flash, DeepSeek-V3.2
```

---

### 实验 4：并发调用多个 cbc

```bash
codebuddy --model kimi-k2.5 --print "你叫 Kimi，只说'Kimi 签到'" &
codebuddy --model glm-5.1 --print "你叫 GLM，只说'GLM 签到'" &
wait
```

输出：
```
GLM 签到
Kimi 签到
```

**结论**：**能。**

- Bash 中用 `&` 后台运行，`wait` 等待全部完成
- 两个子 cbc 独立运行，互不干扰
- 输出顺序取决于各进程完成速度

---

### 实验 5：链式/嵌套调用（cbc → cbc → cbc）

```bash
codebuddy -y --model kimi-k2.5 --print \
  "执行: codebuddy -y --model glm-5.1 --print '用一句话自我介绍'"
```

输出：
```
我是由GLM模型驱动的CodeBuddy Code...
```

**结论**：**能，但有权限限制。**

| 层级 | 模型 | 角色 |
|------|------|------|
| 第 1 层 | deepseek-v4-pro | 启动者（主会话） |
| 第 2 层 | kimi-k2.5 | 中继者 |
| 第 3 层 | glm-5.1 | 最终执行者 |

- 不加 `-y` 时子 cbc 的 Bash 工具会因无法弹出权限确认而失败
- 加上 `--permission-mode bypassPermissions`（或 `-y`）后链式调用可行
- 每一层都是独立进程，彼此不知道调用来源

---

## 三、核心发现：无状态架构

### 交互模式 vs --print 模式

| 特性 | 交互模式（你当前在用的） | --print 模式（子 cbc） |
|------|:---:|:---:|
| 多轮对话 | 有 | 无（单次问答） |
| 上下文记忆 | 有（对话历史） | 无 |
| 文件记忆系统 | 有（MEMORY.md） | 无 |
| 任务列表 | 有 | 无 |
| 进程生命周期 | 存活直到退出 | 启动→处理→输出→死 |
| 可被管道操控 | 否 | 是 |

### 进程模型

```
你当前的交互式会话
┌─────────────────────────────┐
│ 你 ←→ cbc (deepseek)        │  ← 有状态，长生命周期
│      记忆 / 任务 / 对话历史   │
└─────────────────────────────┘

--print 子进程
你 ─→ cbc (kimi) ─→ 输出  ← 无状态，随即销毁
      ↑ 启动 → 跑完 → 死
```

---

## 四、未解决的挑战

### 挑战 1：持久会话

| 方案 | 可行性 |
|------|------|
| `--resume <sessionId>` 恢复历史会话 | 理论可行，但 sessionId 获取方式未知 |
| `--input-format stream-json` 持续喂 stdin | CLI 文档显示支持，需外层脚本管理管道 |

### 挑战 2：子 CLI 有独立窗口且可被操控

| 模式 | 有窗口 | 可操控 |
|------|:---:|:---:|
| 交互模式（不加 --print） | 能 | 不能（等待用户手动输入） |
| --print 模式 | 一闪而灭 | 能 |
| `cmd /c start` + --print + pause | 能 | 不能（窗口暂停但无法再输入） |

**根本矛盾**：窗口可见要求交互模式，操控要求 --print 模式，两者互斥。

---

## 五、解决方案：后台模式（--bg）

### 核心思路

`--print` 的痛点是子 cbc 无状态。但 CBC 提供了 **后台模式**，可以解决这个问题。

| | --print 模式 | --bg 后台模式 |
|---|---|---|
| 启动方式 | `codebuddy --print "..."` | `codebuddy --bg --name xxx` |
| 生命周期 | 启动→跑完→死 | 持续存活 |
| 多轮对话 | 无 | 有 |
| 上下文记忆 | 无 | 有（MEMORY.md） |
| 可被 attach | 否 | 是 |
| 可被操控 | 否 | 理论可以 |

### 目标架构

```
┌──────────────────────────────────────────┐
│  你 ←→ 主 cbc (interactive)              │
│       │                                   │
│       │ 用 Bash 分发任务                   │
│       ├──→ bg session "kimi-worker"        │
│       │     --model kimi-k2.5             │
│       │     持续运行，有记忆                │
│       │                                   │
│       ├──→ bg session "glm-worker"         │
│       │     --model glm-5.1               │
│       │     持续运行，有记忆                │
│       │                                   │
│       └──→ bg session "ds-worker"          │
│             --model deepseek-v4-flash     │
│             持续运行，有记忆                │
└──────────────────────────────────────────┘
```

### 实际操作命令

```bash
# 启动一个常驻子会话
codebuddy --bg --name kimi-worker --model kimi-k2.5

# 查看所有后台会话
codebuddy ps

# 接入查看
codebuddy attach kimi-worker

# 关闭子会话
codebuddy kill kimi-worker
```

### 关键问题（待实测）

1. 主 cbc 能否用 Bash 执行 `codebuddy attach <name> --print "任务"` 向 bg 子会话派发任务？
2. bg 子会话能不能接收多轮对话？每次 attach 是追加到同一个会话上下文，还是独立回合？
3. 并发 attach 同一个 bg 会话会冲突吗？
4. bg 会话如何接收任务结果并返回给主 cbc？

---

## 六、总结

| 能力项 | 结论 | 备注 |
|--------|:----:|------|
| 切换当前会话模型 | 不能 | 只能手动 `/model` |
| 启动子 cbc 实例 | 能 | `codebuddy --print` |
| 子 cbc 使用不同模型 | 能 | `--model <名称>` |
| 并发操控多个 cbc | 能 | Bash `&` + `wait` |
| 链式嵌套调用 | 能 | 需 `-y` 绕过权限 |
| 子 cbc 间共享状态 | 不能 | 每个子进程完全独立 |
| 持久会话（--bg） | **有解** | 后台模式可启动常驻子会话 |
| 独立窗口 + 可操控 | 不能 | 架构上互斥 |

**一句话结论**：`--print` 是短期工（单次问答），`--bg` 是常驻员工（持久有状态）。要搭建「主 cbc 管理一群子 cbc」的架构，`--bg` 是更合理的方案，但能否通过 `attach --print` 实现主会话对子会话的自动化操控，尚待实测。
