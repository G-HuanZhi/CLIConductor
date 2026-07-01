# CLIConductor 代码审查报告

**审查日期**: 2026-07-01
**审查范围**: `main.py`, `src/`, `qq-bridge/`, `tests/`, `static/`, `ts/`, `index.html`
**排除**: `archive/`, `.venv/`, `.codebuddy/`, `experiments/`, `data/`

代码总量约 4189 行。整体架构清晰（FastAPI + asyncio 子进程管理 + WS 推送 + 持久化 Session），核心 replay/restart/kill 逻辑考虑了 Windows 进程树清理等不少边界情况。但存在若干**正确性 bug**、**性能阻塞点**和大量**重复代码**，下面按严重程度分级列出。

---

## 一、Critical — 正确性 / 安全 Bug

### 1.1 `api_rename` 在 worker 死亡时无法改名 【bug】
`src/server.py:641-665`

```python
w = worker.get_worker(worker_id)
if w:
    s = sess.get(w.session_id)
    if s:
        ...改名...
        return {...}
return {"error": "Worker not found"}
```

改名是 session 级操作，不应依赖 worker 是否存活。当前实现导致：worker 崩溃 / 未 spawn 时，用户在 dashboard 改名永远失败，提示 "Worker not found"。

**修复**：以 session 为入口，worker 存在则更新内存引用，不存在也允许改 session.name 并落盘。

### 1.2 QQ Bridge `_pending` 覆盖导致前一个请求永久挂起 【bug】
`qq-bridge/plugin.py:197-198`

```python
evt = asyncio.Event()
_pending[session_id] = evt   # 同一 session_id 第二次调用直接覆盖第一个 evt
```

同一用户连续发两条消息时（典型场景：用户在 120s 内追问），第二次 `_send_and_wait` 会覆盖第一个 `_pending[session_id]`，第一个 `await evt.wait()` 永远不会被 set，直到 125s 超时。期间用户看不到第一条的回复。

**修复**：用 `list[Event]` 或为每个请求生成唯一 `request_id`，按 request_id 索引；或对同一 session 加锁串行化。

### 1.3 `_spawn_process` 与 `create_worker` 的 `--model` 行为不一致 【bug】
`src/worker.py:296` vs `src/worker.py:446-447`

```python
# create_worker — 总是传 --model
extra_args = ["--model", s.model or DEFAULT_MODEL]

# _spawn_process — 仅当 s.model 真值时才传
if s.model:
    args.extend(["--model", s.model])
```

后果：`restart_worker` / `respawn_worker` 走 `_spawn_process`，若 session.model 为 None/空字符串，重启后 cbc 会用它自己的默认模型，**与首次 spawn 的模型不一致**。即用户开 session 时指定了 DEFAULT_MODEL，但 restart 后可能切到 cbc 内部默认值。

**修复**：统一为 `args.extend(["--model", s.model or DEFAULT_MODEL])`。

### 1.4 `_replaying` 标志在用户消息到达时被提前清掉，可能造成 history 重复 【bug】
`src/worker.py:222-223`

```python
# _consumer 收到用户消息
w._replaying = False   # 立即清除
...写入 stdin...
```

设计意图（见注释）是让用户消息之后的 assistant 事件正常 append。但 cbc 收到新 user 消息后，**仍可能先把残留的 replay 旧 assistant 事件吐完**，这些事件会被 `_read_stdout` 当成新消息 append 到 history，造成历史重复。

测试 `test_user_message_during_replay_clears_flag` 把这个行为固化成了"期望行为"，但实际仍存在重复风险——除非能保证 cbc 在收到新 user 后立即停止 replay 输出。

**修复建议**：用一个单调递增的 `replay_generation` 计数，user 消息 ++generation，replay 期间记录 generation，append 时比对；或要求 cbc 在 user 消息后发一个明确的 "replay end" 标记。

### 1.5 `api_takeover` 命令拼接存在 shell 注入 【安全】
`src/server.py:734`

```python
cmd = f'cd "{s.workdir}"; cbc --resume {s.cbc_session_id}'
subprocess.Popen(["powershell.exe", "-NoExit", "-Command", cmd], ...)
```

`s.workdir` 由用户请求传入（见 1.6），若包含 `"` 或 `;`，可注入任意 PowerShell 命令。`cbc_session_id` 来自 cbc 输出相对可信，但仍应防御。

**修复**：用 `subprocess.Popen` 的列表参数 + `cwd=`，避免 shell 字符串拼接：
```python
subprocess.Popen(["powershell.exe", "-NoExit", "-Command",
                  f"cbc --resume {s.cbc_session_id}"],
                 cwd=s.workdir, creationflags=...)
```

### 1.6 `api_spawn` / `api_create_session` 未校验 `workdir` 路径 【安全】
`src/server.py:282-283, 388-389`

```python
workdir_name = data.get("workdir") or name
workdir = WORKDIRS_DIR / workdir_name
workdir.mkdir(parents=True, exist_ok=True)
```

`workdir_name` 可为 `../../etc/foo`，造成路径穿越并在任意位置创建目录。后续 cbc 还会以该目录为 cwd 运行，可能写到敏感位置。

**修复**：白名单字符（`[A-Za-z0-9_-]`）或 `workdir.resolve()` 后校验仍在 `WORKDIRS_DIR` 之下。

### 1.7 `__import__("datetime")` 反模式 【bug-style】
`src/worker.py:161, 240`

```python
"timestamp": __import__("datetime").datetime.now().isoformat(),
```

模块顶部并未直接 import `datetime`（只有 `from datetime import ...` 在 session.py）。这两处每次调用都走 import 机制（命中 sys.modules 缓存但仍是函数调用），可读性极差。

**修复**：顶部 `from datetime import datetime`，改为 `datetime.now().isoformat()`。

---

## 二、High — 性能 / 阻塞

### 2.1 `session.save()` 同步写盘且每次重写全量 history，阻塞事件循环 【性能】
`src/session.py:108-111`

```python
def save(s: Session):
    s.updated_at = datetime.now().isoformat()
    _path(s.id).write_text(json.dumps(s.to_dict(), ...), encoding="utf-8")
```

- `write_text` 是同步阻塞 IO，在 `_read_stdout` 协程里被频繁调用（每个 assistant 事件后一次，见 `worker.py:142, 172`），长会话 + 高频事件时会卡住整个事件循环。
- `to_dict()` 包含完整 `history` 列表，每次 save 都把全部历史序列化+重写。会话越长，单次 save 越慢，整体 O(n²)。

**修复**：
1. 用 `asyncio.to_thread(_save_sync, s)` 或 `aiofiles` 移出事件循环。
2. 长期方案：history 走 append-only 日志（每条消息一行），save 只写元数据；或对 history 做分块存储。

### 2.2 `session.list_all()` 每次 5s 轮询都全量读盘 【性能】
`src/session.py:122-143` + `static/js/app.js:602`

dashboard 每 5s 调一次 `/api/sessions` → `list_all()` → 遍历 `SESSION_DIR.iterdir()` 读所有 JSON 文件。每个文件解析为 dict → 构造 Session。会话多时磁盘 IO 和 CPU 都很重。

而且 `_session_to_api` 还会再调 `worker.find_worker_by_session`（O(n) 线性扫），整体 `O(sessions × workers)` 每 5s 一次。

**修复**：
- 启动时一次性加载到 `_cache`，之后只读缓存。
- 用文件 mtime 或单独的 manifest 文件做增量刷新。
- 维护 `session_id -> worker` 反向索引，避免线性扫。

### 2.3 `_check_session_name` 每次创建/改名触发全量磁盘扫 【性能】
`src/server.py:118-123`

```python
for s in sess.list_all():
    if s.name == name:
        return ...
```

每次都调 `list_all()`（见 2.2）。再叠加 2.2，每次 dashboard poll + 每次 create/rename 都在重读磁盘。

**修复**：维护 `_name_index: dict[str, str]`（name -> session_id），create/delete/save 时同步更新。

### 2.4 `taskkill` 同步阻塞事件循环 【性能】
`src/worker.py:357, 400`

`_kill_takeover_terminal` 和 `_kill_process_tree` 都用 `subprocess.run(...)`，在 async 协程（`kill_worker`, `restart_worker`, `respawn_worker`, `shutdown_all`）里直接调用，阻塞事件循环直到 taskkill 完成（最多 10s timeout）。

**修复**：改用 `asyncio.create_subprocess_exec("taskkill", "/F", "/T", "/PID", str(pid), ...)` 并 await。

### 2.5 QQ Bridge 每次请求新建 `httpx.AsyncClient` 【性能】
`qq-bridge/plugin.py:56, 69`

```python
async with httpx.AsyncClient(timeout=10) as client:
    r = await client.get(url)
```

每次 HTTP 调用都新建 client、新建连接池，无连接复用。轮询期间 80+ 次请求都走完整握手。

**修复**：driver startup 时建一个全局 `httpx.AsyncClient`，shutdown 时 close。

### 2.6 QQ Bridge 轮询 80 次/任务 【性能】
`qq-bridge/plugin.py:88-89`

`POLL_INTERVAL=1.5s` × `MAX_POLL_TIME=120s` = 80 次 GET `/api/sessions/{id}`。每个任务最坏情况 80 次 HTTP 请求 + 80 次服务端全量 session 读盘（2.2）。

**修复**：
- 服务端已有 WS 推送能力，给 QQ bridge 开一个 WS 客户端订阅 `worker.result` 事件，零轮询。
- 或拉长到 3-5s 间隔 + 服务端支持 long-poll（last-event-id）。

### 2.7 `dashboard()` 每次请求读盘 `index.html` 【性能】
`src/server.py:134-136`

```python
return DASHBOARD_FILE.read_text(encoding="utf-8")
```

每次访问 `/` 都同步读盘。虽小但没必要。

**修复**：模块加载时读一次到内存，或用 `StaticFiles` 让 Starlette 处理缓存。

### 2.8 `_cache` 永不淘汰，长跑内存泄漏 【内存】
`src/session.py:67`

`_cache: dict[str, Session] = {}` 一旦 `get` / `create` / `list_all` 命中就常驻，从不淘汰（除 `delete`）。Session 内含完整 history 列表（见 2.1，长会话可达 MB 级）。长跑服务 + 历史会话多时内存单调增长。

**修复**：LRU + 上限（如最多 50 个）；或只缓存元数据，history 按需加载。

### 2.9 `Session.history` 无上限增长 【内存/磁盘】
没有任何 trim 机制。长对话（如 QQ bridge 持续追问几小时）history 无限增长，内存 + 单次 save 成本（2.1）双倍放大。

**修复**：设置 `MAX_HISTORY` 上限，超限滚动窗口或归档到独立文件。

---

## 三、Medium — 重复 / 冗余 / 矛盾

### 3.1 `static/js/app.js` 是 `ts/app.ts` 的编译产物，却在仓库里双重维护 【冗余】
`tsconfig.json` 配置 `outDir: static/js`，`app.js` 末尾有 `//# sourceMappingURL=app.js.map`。两个文件逻辑完全相同（仅 TS 类型擦除差异），共 1400+ 行重复。

任何对 .ts 的修改若忘了 `tsc` 编译，.js 与 .ts 不一致，dashboard 行为漂移。

**修复**：要么 `.gitignore` 忽略 `static/js/app.js` 在 CI 里编译，要么删掉 .ts 只维护 .js。当前双份是定时炸弹。

### 3.2 `server.py` 重复 import `os` 【冗余】
`src/server.py:6` 和 `src/server.py:755` 各 import 一次。后者还在 `# Static files` 区块中间，可读性差。

### 3.3 Session 字段提取逻辑三处重复 【冗余】
以下三段几乎逐字相同，提取 `name/model/permission_mode/always_thinking_enabled/effort/max_thinking_tokens/workdir_name` 并调 `sess.create`：
- `src/server.py:269-297` (`api_create_session`)
- `src/server.py:381-402` (`api_spawn` 新 session 分支)
- `src/server.py:209-237` (`ws_agent_endpoint` spawn 分支)

**修复**：抽 `_build_session_params(data) -> dict` + `_create_session_from_params(data) -> Session`，三处复用。

### 3.4 Session 字段更新逻辑三处重复 【冗余】
以下三段都是 `if "model" in data: s.model = data["model"]` 这套：
- `src/server.py:314-323` (`api_update_session`)
- `src/server.py:370-380` (`api_spawn` 已有 session 分支)
- `src/server.py:541-549` (`api_worker_settings`)
- 还有 deprecated 的 `switch-thinking` (`src/server.py:622-628`)

**修复**：抽 `apply_session_updates(s, data)`。

### 3.5 `broadcast` 函数对 `ws_clients` / `agent_clients` 复制粘贴 【冗余】
`src/server.py:59-73`

两段完全相同的 `for ws in list(...): try: ... except: dead.add(ws)` 循环。

**修复**：
```python
async def _send_set(clients: set[WebSocket], data: dict) -> set[WebSocket]:
    dead = set()
    for ws in list(clients):
        try: await ws.send_json(data)
        except Exception: dead.add(ws)
    return dead

async def broadcast(data: dict):
    ws_clients -= await _send_set(ws_clients, data)
    agent_clients -= await _send_set(agent_clients, data)
```

### 3.6 已废弃的 switch-model/mode/thinking 三个端点仍在 【冗余】
`src/server.py:576-638`

注释明确写了 `Deprecated — use POST /api/worker/{worker_id}/settings instead`，但仍占 60+ 行。前端 `app.js` 已全部走 `/settings`，无任何调用方。

**修复**：确认无外部调用后直接删除。如需过渡，加一次性 deprecation log 即可。

### 3.7 `create_worker` / `branch_worker` 各自手搓 spawn 参数，未复用 `_spawn_process` 【冗余/矛盾】
`src/worker.py:296-304` (`create_worker`) 和 `src/worker.py:585-591` (`branch_worker`) 都手搓 `--model --permission-mode --effort --thinking --resume` 等参数，而 `_spawn_process` 已经封装了同样的逻辑（且行为还不一致，见 1.3）。

**修复**：让 `create_worker` 和 `branch_worker` 都走 `_spawn_process`，统一参数顺序和默认值处理。

### 3.8 `Session.to_dict` 手写而 `asdict` 已 import 却未用 【冗余】
`src/session.py:11` `from dataclasses import dataclass, field, asdict` — `asdict` 从未被调用；`to_dict` 是手写字段映射（`session.py:48-63`）。`field` 也只在 import 出现，未在 `Session` 里使用。

**修复**：要么 `to_dict = asdict`，要么删掉未用的 import。

### 3.9 `worker.spawned` 广播在 3 处发出，字段集各不相同 【矛盾】
- `src/worker.py:326-333`：`workerId, sessionId, name, status, model`
- `src/server.py:230-237` (ws_agent spawn)：`workerId, sessionId, name, status, model`
- `src/server.py:445-453` (/api/task auto-spawn)：`workerId, sessionId, name, status, model, reason`

前端 `app.js` 的处理是统一 `_setLocalWorker(d.sessionId, d.workerId, 'idle')`，多余字段被忽略。后端字段不一致纯属历史包袱。

**修复**：所有 spawn 都走 `worker.create_worker` 内部那一次广播，外层不要再发。

### 3.10 `api_spawn` 新建 session 分支未广播 `session.created` 【矛盾】
`src/server.py:381-402` 创建新 session 后直接 spawn worker，没有像 `api_create_session` (`server.py:292-296`) 那样广播 `session.created`。如果有其他 dashboard 监听 `session.created` 来刷新列表，会漏掉。

### 3.11 `interrupt_worker` = `restart_worker` 语义可疑 【矛盾】
`src/worker.py:625-631`

```python
async def interrupt_worker(worker_id: str) -> str | None:
    ...
    return await restart_worker(worker_id)
```

`restart_worker` 会用 `--resume` 重新拉起 cbc 并进入 replay，相当于"中断当前任务 + 重放历史"。而"interrupt"通常的语义是"打断当前工具调用，保留 cbc 上下文不重启"。当前实现等于 restart，按钮名字和实际行为不符。

**修复**：要么改名 `interruptButton` → `restartButton`，要么实现真正的 interrupt（向 cbc 发 SIGINT / 写特定 JSON 指令）。

---

## 四、Low — 死代码 / 小问题

### 4.1 死代码
| 位置 | 内容 |
|---|---|
| `src/session.py:146-148` | `list_active()` 在生产代码无任何调用 |
| `src/session.py:151-152` | `clear_cache()` 仅 tests 调用，生产不用 |
| `qq-bridge/plugin.py:41` | `BridgeSession.last_history_len` 字段被 set 3 处，从不被 read |
| `qq-bridge/plugin.py:43, 45-46` | `created_at` 字段 + `__post_init__` 总是覆盖传入值，参数无意义 |
| `src/worker.py:13` | `field` 从 dataclasses import 但 Worker 内部未用 |
| `static/css/styles.css:122-126` | `.sess-count` 类定义，HTML/JS 从未生成此 class |
| `static/js/app.js:569` | `modelData.push(d)` 紧接着 `refreshSessions()` 把 modelData 整个覆盖，push 无意义 |
| `src/server.py:755` | `import os` 重复 |

### 4.2 `app.js` `refreshSessions` 无 debounce 【体验】
`static/js/app.js:74-96`

WS 事件 `worker.spawned` / `worker.status` / `worker.result` 都触发 `refreshSessions`，且 `_setLocalWorker` 内部已 `renderSessionList` 一次。短时间多个 WS 事件 → 多个并发 fetch，最后到达的响应可能不是最新状态。

**修复**：`refreshSessions = debounce(refreshSessions, 100)`。

### 4.3 `app.js` 所有 fetch 无 `.catch()` 【健壮性】
`static/js/app.js` 全部 `fetch(...).then().then()` 链都没 catch，网络错误 / 服务端 5xx 静默失败，用户看不到任何提示。

### 4.4 `app.js` 同时用 WS 触发刷新和 `setInterval(refreshSessions, 5000)` 【冗余】
`static/js/app.js:602`

WS 已能感知所有变更（spawned/crashed/result/status），5s 轮询是兜底。但 WS 在线时轮询纯属浪费（叠加 2.2 的服务端成本）。建议 WS 连接时停掉轮询，断开时再起。

### 4.5 `_log` 用 `print` 而非 `logging` 【可观测性】
`src/server.py:20-22`

无日志级别、无文件输出、无 rotation。生产排查困难。建议改用标准 `logging` 或 `loguru`。

### 4.6 `find_worker_by_session` O(n) 线性扫 【性能-小】
`src/worker.py:657-661`

每次 `_session_to_api` 都扫一次。worker 数量大时不友好。维护 `session_id -> worker_id` 反向索引即可。

### 4.7 `api_takeover` 未检查 `w.status == "held"` 【bug-小】
`src/server.py:708-752`

已 held 的 worker 再次调用 takeover 会再开一个 PowerShell 终端，旧的 `takeover_pid` 被覆盖，原终端进程成为孤儿。

### 4.8 QQ Bridge 群消息 @ 未从 text 中剥离 【体验】
`qq-bridge/plugin.py:258-264`

判定了 @ 自己，但 `event.get_plaintext()` 仍包含 `@bot ` 前缀，cbc 收到的提问带 @ 字符。建议用 `event.message` 移除 at segment 后再取 plaintext。

### 4.9 QQ Bridge `bot.send` 无异常处理 【健壮性】
`qq-bridge/plugin.py:269-280`

被风控 / 网络抖动时 `bot.send` 抛异常，整个 handler 崩溃，NoneBot 可能日志一片红。建议 try/except + 降级。

### 4.10 `_LOG_SKIP` 仅在 import 时读一次环境变量 【小】
`src/server.py:27-31`

运行时改环境变量不生效。一般可接受，但调试时不便。

### 4.11 输入未校验 【健壮性】
- `api_create_session` 不校验 `name` 非空 / 长度 / 合法字符
- `api_worker_settings` 不校验 `model` 是否在 `SUPPORTED_MODELS`
- `api_task` 不校验 `text` 长度上限

---

## 五、汇总与优先建议

### 立即修复（影响正确性/安全）
1. **1.1** `api_rename` 解耦 worker
2. **1.2** QQ Bridge `_pending` 并发覆盖
3. **1.3** `_spawn_process` model 默认值统一
4. **1.5 / 1.6** shell 注入 + 路径穿越
5. **1.7** `__import__("datetime")` 改正常 import

### 性能优化（高 ROI）
6. **2.1** `session.save` 异步化 + 不再重写全量 history
7. **2.2** `list_all` 改纯缓存读取
8. **2.4** `taskkill` 改 `asyncio.create_subprocess_exec`
9. **2.5** QQ Bridge 复用 `httpx.AsyncClient`
10. **2.6** QQ Bridge 改 WS 订阅替代 80 次轮询

### 重构清理（中 ROI）
11. **3.1** 决定 .ts 或 .js 单一来源，删另一份
12. **3.3 / 3.4** Session 字段提取/更新抽公共函数
13. **3.6** 删除 deprecated switch-* 端点
14. **3.7** `create_worker` / `branch_worker` 复用 `_spawn_process`
15. **4.1** 清理死代码（list_active / last_history_len / .sess-count 等）

### 长期方向
- **2.8 / 2.9** Session 缓存 LRU + history 上限
- **4.5** 引入 logging 替代 print
- **4.2 / 4.3 / 4.4** 前端 debounce + fetch catch + WS 在线时停轮询

---

## 六、整体评价

代码核心逻辑（replay 处理、takeover 终端杀树、auto-spawn 兜底）考虑了大量边界情况，注释也写明了"为什么"，可见经过实际踩坑沉淀。主要问题集中在：

1. **Session 持久化路径**是性能与内存的双重瓶颈，且同步 IO 阻塞事件循环。
2. **HTTP / WS 接口层有大量复制粘贴**，session 字段处理、spawn 参数构造、广播发送都散落多处，导致行为不一致（1.3、3.9、3.10）。
3. **前后端两份"真理"**（.ts 与 .js、3 处 spawn 广播、3 处字段更新），长期会持续产生"改了一处漏了另一处"的 bug。
4. **QQ Bridge 轮询模型**与服务端的 WS 能力错配，80 次/任务的轮询既慢又重。

按上述优先级处理，预计能在不改变整体架构的前提下显著提升响应速度、降低内存占用，并消除几个隐藏的正确性/安全隐患。
