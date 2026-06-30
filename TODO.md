# TODO — Settings Panel Refactor

## 已实现

### 1. API 端点
- 新增 `POST /api/worker/{worker_id}/settings`（一次接收 model/mode/think/effort，更新 session 后调一次 `respawn_worker`）
- 旧端点 `switch-model`、`switch-mode`、`switch-thinking` **保留但不被前端调用**（server.py 中已标注 `Deprecated`）
- 无 worker 时 settings 通过 `PATCH /api/sessions/{id}` 持久化到 session

### 2. 前端设置面板
- Model / Mode / Think / Effort 共用单 `Apply Settings` 按钮，仅差异时显示
- `onThinkingToggle()` 处理 Think 勾选时 Effort 显隐 + 自动选 medium，不调 API
- `syncPanelFromServer()` 替换原 `syncSettingsPanel`，仅在打开面板 / 切换 session 时调用
- `updateTopBar` 不再同步设置面板字段
- `lastSyncedSettings` 追踪上次同步/应用的设置基线

### 3. send() Set-before-send
- 有 worker 且有 pending changes 时：先 `POST /api/worker/{id}/settings`，await 返回后再 `doSend()`
- 无 worker：按原逻辑 spawn（含当前 setting）

### 4. restartWorker
- 有 worker：直接调 `applySettings()`（后者已包含设置应用 + respawn）
- 无 worker：按原逻辑 spawn（含当前 setting）

### 5. 已废弃但保留的后端端点
- `POST /api/worker/{id}/switch-model` — Deprecated
- `POST /api/worker/{id}/switch-mode` — Deprecated
- `POST /api/worker/{id}/switch-thinking` — Deprecated
