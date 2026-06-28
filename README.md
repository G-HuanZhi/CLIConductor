# CLIConductor

> 中间层，让主 Agent 调度管理多个第三方 AI CLI 进程，同时人类可随时观察、插话、接管任意进程。

## 当前状态

**技术栈选型阶段** — 正在通过两端 spike 实战对比 Python+FastAPI vs Node.js+Express。

| 事项 | 状态 |
|------|------|
| 目标定义 | 完成 — `target.md` |
| 全局规划 | 完成 — `docs/global_plan.md` |
| Phase 1 计划 | 完成 — `docs/first_plan.md` |
| 技术栈分析 | 完成 — `docs/tech-stack-analysis.md` |
| Spike 对比 | 进行中 — `docs/spike-comparison-plan.md` |

## 架构

```
人类 (Dashboard / CLI / 消息渠道)
    │
    ├─ WebSocket 实时流
    ├─ HTTP API 注入/接管
    │
主 Agent (外部 AI)
    │
    ├─ HTTP API 派发任务
    ├─ WebSocket 接收事件流
    │
    ├──→ [CLIConductor 中间件] ──→ Worker-1 (cbc)
    │                              Worker-2 (cbc)
    │                              Worker-3 (cbc)
    │
    └──→ [持久化] SQLite
```

## 快速开始

### Python Spike

```bash
cd spike-python
pip install -r requirements.txt
python main.py
# → http://localhost:8767
```

### Node.js Spike

```bash
cd spike-node
npm install
npm start
# → http://localhost:8766
```

两者提供相同 API：`spawn` / `list` / `task` / `kill` / `restart` + WebSocket 实时流。

## 目录

```
CLIConductor/
├── target.md                        # 项目目标（不含技术栈）
├── notes.md                         # 综合研究笔记
├── docs/
│   ├── global_plan.md               # 全局规划 + Phase 1/2/3 路线图
│   ├── first_plan.md                # Phase 1 MVP 详细计划
│   ├── tech-stack-analysis.md       # 5 方案加权评分
│   ├── tech-stack-final-comparison.md  # 试验 + 架构推演综合对比
│   ├── spike-comparison-plan.md     # 对比试验计划与结果
│   ├── known-issues.md              # 已知限制
│   └── dionysusc-reference.md       # DionysusC 参考分析
├── spike-python/                    # Python+FastAPI spike
│   ├── main.py                      # 完整服务端（~280 行）
│   ├── index.html                   # Dashboard
│   └── requirements.txt
├── spike-node/                      # Node.js+Express+ws spike
│   ├── src/main.ts                  # 完整服务端（~255 行）
│   ├── public/index.html            # Dashboard
│   ├── package.json
│   └── tsconfig.json
├── archive/                         # 重构前代码 + PTY 实验归档
└── experiments/                     # stdin stream-json 验证试验
```
