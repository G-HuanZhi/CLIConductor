# Spike 对比计划

## 目的

Python+FastAPI 和 Node.js+Express 两边 spike 已实现对等功能（HTTP API + WebSocket + Worker + 多轮对话）。接下来通过一组分化性试验暴露两边的真实差异，辅助最终技术栈决策。

## 试验清单

按优先级排序，每个试验同时在两边实现或执行。

### 试验 5：添加新功能对比（最高优先级）

**内容**：两边同时添加 `POST /api/worker/:id/restart` 端点。

**行为定义**：
1. 检查 worker 是否存在
2. 旧进程还在则先 kill
3. 用相同参数重新 spawn cbc 子进程
4. 重新挂载 stdout reader + WebSocket 广播
5. 广播 `worker.restarted` 事件
6. 返回同一个 workerId

**对比维度**：
- 从开始编码到功能跑通的时间
- 遇到的坑（类型错误、异步问题、框架约束）
- 代码行数和改动文件数
- 主观开发体验

---

### 试验 1：多 Worker 并发

**内容**：同时 spawn 3 个 worker，向各自发送不同任务，观察 Dashboard 实时流。

**对比维度**：
- stdout 流是否流畅，有无饥饿/阻塞
- Dashboard 面板是否正确路由，有无串流
- WebSocket 广播是否有丢帧或乱序
- CPU/内存使用情况

---

### 试验 3：崩溃恢复

**内容**：外部 kill 掉 cbc 子进程，观察检测、通知、恢复全链路。

**对比维度**：
- 多久检测到进程退出
- WebSocket 是否正确广播 `worker.error`
- 重启是否干净（stdout reader 重新挂载）
- 错误处理的代码清晰度

---

### 试验 2：Stdin 注入冲突

**内容**：模拟 Agent 调度和用户手动介入同时向同一 worker 的 stdin 写消息。

**对比维度**：
- 是否需要 mutex/队列
- Python `asyncio.Lock` vs Node.js Promise 队列哪个更自然
- 并发写入是否导致崩溃或数据乱序

---

### 试验 4：长时间稳定性

**内容**：保持 2 个 worker 运行 15 分钟，每 2 分钟发一次任务，观察内存曲线。

**对比维度**：
- 内存是否持续增长（事件历史泄漏）
- 进程是否稳定不退出
- 各组件（WebSocket、subprocess）是否保持连接

---

## 执行顺序

1. **试验 5**：添加 restart 功能，记录开发体验
2. **试验 1**：多 worker 并发测试
3. **试验 3**：崩溃恢复测试
4. **试验 2**：stdin 注入冲突
5. **试验 4**：长时间稳定性

## 决策标准

试验完成后，用 tech-stack-analysis.md 中的评分框架更新实际开发体验数据，做最终技术栈决策。
