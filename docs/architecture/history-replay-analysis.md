# 对话历史重建问题分析

> 最后更新：2026-07-01
> 状态：**已实施**（新方向已在 dev 分支落地，见第八节实施记录）
> 范围：frontend 分支 `58b1f99` 之后的 replay 重建机制

---

## 一、背景

`58b1f99` 之前发现某些历史保存 bug（具体场景已不可考，用户不记得了，devNote 无记录）。
基于此，`a10c4c6`..`f2a39b7` 一系列 commit 引入了 `_replay_buf` 机制，试图在 cbc
`--resume` 重放 stdout 时**重建一份"完美"的 history**，整体覆写 `s.history`。

现状：restart 后发消息，`_replay_buf` 累积了全部历史，但用户发消息后立即只剩最新
一问一答，之前的历史丢失。test worktree 的 `ses_9fa51929f66a8d61.json` 即现场：
`history = [user "回复2", assistant "2"]`，仅一轮。

---

## 二、当前 replay 重建机制（现状）

代码位置：`src/worker.py`

1. `create_worker` / `restart_worker` / `respawn_worker` 调 `_prepare_resume(s, w)`
   → 设 `w._replaying = True`、`w._replay_buf = []`
2. cbc `--resume` 在 stdout 重放历史，`_read_stdout` 把 user/assistant 事件塞进
   `_replay_buf`（worker.py:124-146）
3. 用户发新消息时，`_consumer` `await asyncio.sleep(0.5)` 后
   `s.history = w._replay_buf` 整体覆写，再 append 新消息（worker.py:225-239）

---

## 三、核心问题（不止一点）

### 1. 致命竞态：500ms sleep 同步不可靠（最可能的直接病因）

`_consumer` 用 `await asyncio.sleep(0.5)` 等待 replay 完成，但 replay 时长取决于
历史长度和 cbc 启动速度。

- 若 cbc 刚 spawn 还在 init（`--resume` 启动有延迟），用户发消息时 `_replay_buf`
  仍是 `[]` → `s.history = []` 直接清空 → append 新消息 → 只剩最新一问一答。
  **这正是 test worktree 现场的样子。**
- 500ms 是赌运气，不是同步原语。历史越长越容易翻车。

### 2. swap 之后 replay 仍在继续 → 历史错乱

若 swap 发生在 replay 中途，`_replaying` 已被置 False，但 `_read_stdout` 仍在收
replay 事件：

- `user` 事件：`if t == "user" and w._replaying:` → False，**直接丢弃**
  （worker.py:124）
- `assistant` 事件：走 `s.history` 分支，把旧的 replay assistant 消息 append 到
  新消息**后面** → 顺序错乱

### 3. 思路在解决一个不存在的问题

devNote "已完成的重大修复" 明确记载 history 持久化已修：

- `_consumer` 先 append+save 用户消息（worker.py:236-239）
- `_read_stdout` 每个 assistant 事件后立即 `_sess.save(s)`（worker.py:145-146）
- `session.py list_all()` 不覆盖已缓存 session（session.py:130-137）

**磁盘上的 `s.history` 就是 ground truth**，根本不需要从 cbc replay 重建。
`--resume` 的作用是恢复 **cbc 内部状态**（让 cbc "记得"之前的对话），与我们的
`s.history` 是两套独立的东西。

### 4. replay 重建的 history 并不"更完美"

replay 的 `user` 事件处理（worker.py:124-128）只取 `text` block，**漏掉
`tool_result`**。和正常路径一样的缺口，没比 `s.history` 多任何信息。
费大劲重建出来的是同等残缺的副本。

### 5. replay 期间 status 闪烁导致用户过早发送

replay 的每个 `result` 事件都设 `w.status = "idle"`（worker.py:157），dashboard
可能在第一轮 replay 结束就显示 idle，用户以为就绪了就发消息，撞上竞态。

### 6. `_prepare_resume` 的 None 崩溃

`restart_worker`（worker.py:476-477）和 `respawn_worker`（worker.py:511-512）
调 `_prepare_resume(s, w)` 前不检查 `s` 是否为 None。若 session 已被删除，
`_prepare_resume` 里 `if s.cbc_session_id` 抛 AttributeError。
`create_worker` 有做 not s 检查，这两个没有。

### 7. `branch_worker` 不走 `_prepare_resume`

branch 用 `--resume` 但没设 `_replaying`，replay 事件走正常分支 append 到
`s.history`。对 branch 来说恰好歪打正着（新 session history 从空开始），
但与主路径逻辑不一致，容易在后续改动里踩雷。

---

## 四、结论：当前思路不合理

用时间 heuristic（sleep 500ms）去同步一个异步外部进程的输出，本质就是 racy 的。
而且它解决的是个不存在的问题——`s.history` 已经可靠持久化，没必要重建。

`f2a39b7`（加 500ms delay）、`fcc8142`（keep buffer across turns）都是在错误
思路上打补丁。继续在这个方向上修补没有出路。

---

## 五、新方向

**彻底删掉 `_replay_buf` 机制，replay 期间完全不碰 `s.history`：**

1. 保留 `_replaying` 标志，但语义改为"replay 期间，丢弃所有 stdout 事件对
   history 的影响"
2. `_read_stdout` 里：`_replaying` 为 True 时，user/assistant/result 事件
   **一律不 append、不 save、不 broadcast**（只让 cbc 内部完成状态恢复）
3. `_consumer` 收到用户第一条新消息时：直接 `_replaying = False`，然后照常
   `s.history.append(user msg)` + save + 发 cbc
4. 删除 `_replay_buf`、删除 `sleep(0.5)`、删除 swap 逻辑

### 正确性推演（3 轮历史重启）

- 磁盘 `s.history` = [u1,a1,u2,a2,u3,a3]
- 重启 spawn `--resume`，`_replaying=True`，cbc 内部回放（stdout 事件被丢弃，
  不动 history）
- 用户发 u4：`_replaying=False`，append → [u1..a3,u4]，发 cbc
- cbc 回 a4：`_replaying=False`，append → [u1..a3,u4,a4] ✓

无竞态、无 sleep、无 swap。`s.history` 全程只增不减。

---

## 六、附带修复（同一改动里一起处理）

1. `_prepare_resume` 改名/简化为只设 `_replaying`，去掉 `_replay_buf`；
   加 None 防护
2. replay 期间 `w.status` 不设 idle（用 "replaying" 或保持原样），避免用户
   误判过早发送
3. `branch_worker` 统一走 `_prepare_resume`（branch 场景 `_replaying=False`，
   让它继续走 append 路径填充空 history——或者明确 branch 不 resume，需要单独确认）

---

## 七、待用户确认

1. **`58b1f99` 当时测试出来的历史保存 bug 具体是什么？**
   - 用户不记得，devNote 无记录
   - 若当时 bug 已被后续的 history 持久化修复（_consumer 先 save、每 assistant
     事件后 save、list_all 不覆盖缓存）覆盖，则 replay 重建完全无必要
   - 若当时 bug 是别的场景（如 tool_result 丢失、thinking 丢失），需评估新方向
     是否会重新引入
2. **`branch_worker` 的处理方式**：branch 时是否需要 `--resume`？若需要，
   replay 事件该如何处理？
3. **replay 期间 status 显示**：用 "replaying" 还是保持 idle 不变？
4. **是否立即按新方向实施**？

---

## 八、实施记录（2026-07-01，dev 分支）

### 决策

用户拍板：**不依赖 replay 重建历史**（别的 CLI 未必有 replay，CLIConductor
要独立稳定建立历史），但保留 frontend 分支的 replay 尝试作为兜底记录。

复用 dev 分支开发（而非从 58b1f99 新建分支），原因：
- dev 的 `worker.py` 已经是新方向的雏形（`_replaying` 标志 + 跳过 append，
  无 `_replay_buf` swap 机制），frontend 在 58b1f99 之后才改成复杂方案
- dev = 58b1f99 的 worker.py = replay 尝试前的干净状态
- frontend 分支保留不动 = replay 兜底

### 实施内容

| commit | 内容 |
|--------|------|
| `65da492` `29dd74f` `ee8b0f1` | cherry-pick 58b1f99 的 3 个日志增强 commit（`f155ebb` 不需要，dev 已有等价改动） |
| `cba0121` | 抽取 `_kill_process_tree(w)` 辅助函数，`shutdown_all`/`kill_worker`/`restart_worker`/`respawn_worker` 4 处统一调用 taskkill /F /T。额外修复 `respawn_worker` 不调 `_kill_takeover_terminal` 的 bug |
| `d3de3a1` | 对照第六节审查 `_replaying` 实现，修 3 个问题：①`_consumer` 发消息时不清 `_replaying`（关键 bug）②replay 期间广播 stream 事件 ③branch_worker 加注释说明有意不走 replay 模式 |
| `6ccb795` | 7 个单元测试覆盖核心不变量（mock process，不依赖真实 cbc） |

### 关于第六节附带问题的最终处理

1. **`_prepare_resume` None 防护**：dev 无此函数，`create_worker` 已 `if not s`
   检查，`restart_worker` 用 `s and` 短路——无需修复。
2. **replay 期间 status**：保持 idle。dev 的 `_consumer` 能正确处理过早发消息
   （清 `_replaying` + append），不会丢历史，所以"过早发消息"不再是问题。
   回退了"不设 idle"的初步改动。
3. **`branch_worker`**：保留现状（不走 replay 模式），加注释说明——新 session
   history 为空，需要从 cbc 重放填入历史，与主路径场景不同。

### frontend 分支状态

保留不动，13 个 replay 尝试 commit 完整保留作为兜底记录。若独立 history 方向
未来发现漏了什么，可 `git cherry-pick` / `git merge` 从 frontend 取回。

