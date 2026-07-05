# CLIConductor 鉴权与权限设计方案

> 状态：设计阶段 | 目标：从基于来源的简单差异化，平滑演进到多用户角色权限体系

---

## 1. 当前问题与演进路径

| 阶段 | 实现方式 | 行为 |
|------|---------|------|
| **阶段 1（当前）** | `/api/capabilities` 基于 source 返回功能列表 | local=全功能, tunnel=受限（禁 takeover 等） |
| **阶段 2** | 引入角色定义文件 | 不改行为，功能列表从角色读取而非硬编码 |
| **阶段 3** | 引入用户与 Token | tunnel 访问需 token，本地直连自动当 admin |
| **阶段 4** | 前端加登录 UI | tunnel 无 token 时显示 token 输入框 |

核心原则：前端合约不变，一直调 `/api/capabilities`，后端换"识别源"。

---

## 2. 架构总览

```
请求到达 server.py
        │
        ▼
┌──────────────────┐
│ 1. 识别来源      │  CF-RAY 头 → local / tunnel
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ 2. 提取 Token    │  优先级: URL ?token=xxx > Authorization Bearer > X-API-Key > localStorage
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ 3. 匹配用户      │  查 config/users.json: token + allowed_sources
└──────┬───────────┘
       │ 匹配到用户
       ▼
┌──────────────────┐
│ 4. 查角色权限     │  查 config/roles.json: role → features
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ 5. 返回/校验     │  /api/capabilities 返回 features
│                  │  受保护路由检查 features[action]
└──────────────────┘
```

---

## 3. 数据模型

### 3.1 实体关系

```
         ┌────────┐
         │  User  │  (具体的人或设备)
         └───┬────┘
             │  belongs to
             ▼
         ┌────────┐
         │  Role  │  (权限模板: admin / operator / viewer)
         └───┬────┘
             │  contains
             ▼
         ┌────────────┐
         │  Feature[]  │  (原子权限: takeover, kill, chat, ...)
         └────────────┘
```

### 3.2 用户配置 `config/users.json`

```json
{
  "users": [
    {
      "id": "local-admin",
      "name": "本地管理员",
      "role": "admin",
      "token": null,
      "allowed_sources": ["local"]
    },
    {
      "id": "my-phone",
      "name": "手机",
      "role": "operator",
      "token": "sk-abc123def456",
      "allowed_sources": ["tunnel"]
    },
    {
      "id": "colleague",
      "name": "同事小王",
      "role": "viewer",
      "token": "sk-xyz789ghi012",
      "allowed_sources": ["tunnel"]
    }
  ],
  "defaults": {
    "local_without_token": "local-admin",
    "tunnel_without_token": null
  }
}
```

| 字段 | 说明 |
|------|------|
| `id` | 用户唯一标识 |
| `role` | 关联 `roles.json` 中的角色名 |
| `token` | API token，null 表示无 token（依赖 source 匹配） |
| `allowed_sources` | 该用户允许的访问方式，防止本地绕过鉴权 |

### 3.3 角色配置 `config/roles.json`

```json
{
  "admin": {
    "label": "管理员",
    "features": {
      "takeover": true,
      "kill": true,
      "settings": true,
      "chat": true,
      "spawn": true,
      "delete_session": true
    }
  },
  "operator": {
    "label": "操作员",
    "features": {
      "takeover": false,
      "kill": true,
      "settings": true,
      "chat": true,
      "spawn": true,
      "delete_session": false
    }
  },
  "viewer": {
    "label": "观察者",
    "features": {
      "takeover": false,
      "kill": false,
      "settings": false,
      "chat": false,
      "spawn": false,
      "delete_session": false
    }
  }
}
```

---

## 4. Token 传递方式

| 方式 | 示例 | 适用场景 | 安全性 |
|------|------|---------|:---:|
| URL 查询参数 | `?token=sk-xxx` | 浏览器直接访问 | 低（URL 可被记录） |
| Authorization 头 | `Authorization: Bearer sk-xxx` | Dashboard JS / API 调用 | 高 |
| X-API-Key 头 | `X-API-Key: sk-xxx` | 外部服务调用 | 中 |
| localStorage | Dashboard JS 自动带 | 用户只需输入一次 | 中 |

**优先级**：URL params > Authorization Bearer > X-API-Key

前端流程：
```
首次打开 Dashboard（tunnel） → /api/capabilities 返回 401
  → 前端显示 token 输入界面
  → 用户输入 token → POST /api/auth/verify {token}
  → 成功 → 前端存 token 到 localStorage
  → 后续请求自动带 Authorization: Bearer <token>
  → /api/capabilities 返回该用户的功能列表
```

---

## 5. 来源检测

Cloudflare Tunnel 会自动给每个转发的请求注入以下头：

| Header | localhost | tunnel |
|--------|:---:|:---:|
| `CF-RAY` | 无 | 有（请求追踪 ID） |
| `CF-Connecting-IP` | 无 | 有（客户端 IP） |
| `CF-Visitor` | 无 | 有（`{"scheme":"https"}`） |

检测逻辑：

```python
def _is_tunnel(request: Request) -> bool:
    return "CF-RAY" in request.headers
```

安全性：Cloudflare 在 CDN 层会剥离客户端伪造的 Cloudflare 头再重新注入，因此无法被伪造。

---

## 6. 代码结构

```
src/
├── server.py       ← 中间件: 提取 token → 查用户 → 注入 request.state.user
├── auth.py         ← 新文件: 用户/角色加载、token 校验、权限判断
├── worker.py       ← 不改
└── session.py      ← 不改

config/
├── users.json      ← 用户配置（手工编辑，无需管理界面）
└── roles.json      ← 角色权限定义

static/js/app.js    ← init() 调 /api/capabilities，根据 features 显隐 UI
ts/app.ts           ← 同上（TypeScript 源）
```

### 6.1 `auth.py` 核心接口

```python
@dataclass
class User:
    id: str
    name: str
    role: str
    features: dict[str, bool]  # 已展开的角色权限

def resolve_user(source: str, token: str | None) -> User | None:
    """根据来源和 token 解析用户，返回 None 表示拒绝访问"""

def check_feature(user: User, feature: str) -> bool:
    """检查用户是否有某功能权限"""

def require_feature(user: User, feature: str):
    """无权限时抛 403"""
```

### 6.2 中间件注入

```python
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    source = "tunnel" if "CF-RAY" in request.headers else "local"
    token = _extract_token(request)
    user = resolve_user(source, token)
    if user is None:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    request.state.user = user
    request.state.source = source
    return await call_next(request)
```

### 6.3 `/api/capabilities` 路由

```python
@app.get("/api/capabilities")
async def api_capabilities(request: Request):
    user = request.state.user
    return {
        "user": {"id": user.id, "name": user.name, "role": user.role},
        "source": request.state.source,
        "features": user.features,
    }
```

### 6.4 高危路由守卫

```python
@app.post("/api/worker/{worker_id}/takeover")
async def api_takeover(request: Request, worker_id: str):
    require_feature(request.state.user, "takeover")
    # ... 原有逻辑
```

---

## 7. 前端差异化

### 7.1 初始化

```typescript
let capabilities = { features: {} };

function init() {
    fetch("/api/capabilities")
        .then(r => r.json())
        .then(data => {
            capabilities = data;
            applyRestrictions();
        });
    // ... 原有逻辑
}
```

### 7.2 UI 控制

```typescript
function applyRestrictions() {
    if (!capabilities.features.takeover) {
        document.getElementById("takeoverBtn")?.style.display = "none";
    }
    if (capabilities.source === "tunnel") {
        document.body.classList.add("tunnel-mode");
    }
}
```

### 7.3 兜底检查

```typescript
function takeover() {
    if (!capabilities.features.takeover) {
        toast("此功能仅支持本地访问");
        return;
    }
    // ... 原有逻辑
}
```

---

## 8. 功能权限一览

| Feature | admin | operator | viewer | 说明 |
|---------|:---:|:---:|:---:|------|
| `takeover` | yes | no | no | 接管 worker 到本地终端 |
| `kill` | yes | yes | no | 强制杀死 worker |
| `settings` | yes | yes | no | 修改模型/权限模式/thinking |
| `chat` | yes | yes | no | 发送消息 |
| `spawn` | yes | yes | no | 创建新 worker |
| `delete_session` | yes | no | no | 删除 session |

---

## 9. 典型场景

| 场景 | 来源 | Token | 匹配用户 | 权限 |
|------|------|-------|---------|------|
| 你本机打开 localhost | local | 无 | local-admin | admin（全部功能） |
| 你手机通过域名访问 | tunnel | sk-abc123 | my-phone | operator（禁 takeover/删除） |
| 同事通过域名访问 | tunnel | sk-xyz789 | colleague | viewer（只读） |
| 陌生人通过域名访问 | tunnel | 无 | null（defaults 为 null） | 401 拒绝 |
| QQ Bridge 调 API | local | 无 | local-admin | admin |
