# WebSocket 简介

## 什么是 WebSocket？

WebSocket 是一种在 **单个 TCP 连接** 上进行 **全双工通信** 的网络协议。与传统的 HTTP 请求-响应模式不同，WebSocket 允许客户端和服务器在建立连接后，**双向、实时地互相发送数据**，无需客户端反复轮询。

## 核心特点

| 特点 | 说明 |
|------|------|
| **全双工** | 客户端和服务器可以同时向对方发送数据 |
| **持久连接** | 一次握手后连接保持打开，无需反复建立 |
| **低延迟** | 数据可以直接推送，不需要 HTTP 请求开销 |
| **轻量级** | 协议头部仅 2-14 字节（HTTP 头部通常几百字节起） |
| **基于 TCP** | 可靠传输，保证数据有序到达 |

## 工作原理

### 1. 握手阶段（Upgrade）

WebSocket 连接始于一个标准的 HTTP 请求，客户端通过特殊的头字段请求升级协议：

```
客户端请求：
GET /chat HTTP/1.1
Host: server.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13

服务器响应：
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

一旦服务器返回 `101 Switching Protocols`，TCP 连接就不再用于 HTTP，而是切换到 WebSocket 协议。

### 2. 数据传输（帧）

握手完成后，双方通过 **帧（Frame）** 来传输数据。WebSocket 帧结构极简：

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-------+-+-------------+-------------------------------+
|F|R|R|R| opcode|M| Payload len |    Extended payload length    |
|I|S|S|S|  (4)  |A|     (7)     |             (16/64)           |
|N|V|V|V|       |S|             |   (if payload len==126/127)   |
| |1|2|3|       |K|             |                               |
+-+-+-+-+-------+-+-------------+-------------------------------+
|     Extended payload length continued, if payload len==127    |
+-------------------------------+-------------------------------+
|                               |Masking-key, if MASK set to 1  |
+-------------------------------+-------------------------------+
| Masking-key (continued)       |          Payload Data         |
+-------------------------------- - - - - - - - - - - - - - - - +
:                     Payload Data continued ...                :
```

关键字段：
- **opcode**: 帧类型（文本帧=1，二进制帧=2，关闭帧=8，ping=9，pong=10）
- **MASK**: 客户端发往服务器的帧必须掩码，服务器发往客户端的帧不掩码
- **Payload len**: 负载长度，支持 7 位、16 位（126）或 64 位（127）扩展

### 3. 心跳机制（Ping/Pong）

WebSocket 内置了 Ping/Pong 帧用于保持连接存活：

```
客户端 → 服务器: Ping 帧
服务器 → 客户端: Pong 帧
```

如果一方未能在规定时间内收到 Pong 响应，即可判定连接已断开。

## 与 HTTP 长轮询的对比

| 对比维度 | WebSocket | HTTP 长轮询 |
|----------|-----------|-------------|
| 连接方式 | 持久连接，一次握手 | 每次请求都建立新连接 |
| 数据方向 | 全双工双向 | 单向（服务器只能响应请求） |
| 头部开销 | 2-14 字节/帧 | 每次请求数百字节 HTTP 头 |
| 服务器推送 | 原生支持 | 需要客户端先发请求 |
| 实现复杂度 | 中等 | 简单 |
| 适用场景 | 实时通信、游戏、协作编辑 | 简单通知、兼容旧系统 |

## 使用场景

1. **实时聊天** — 微信网页版、Slack、Discord
2. **实时协作** — Google Docs 多人编辑、Figma 协同设计
3. **实时数据推送** — 股票行情、体育比分、监控大屏
4. **在线游戏** — 多人在线游戏的实时状态同步
5. **IoT 设备通信** — 智能家居设备的状态上报与控制

## 浏览器端示例

```javascript
// 建立连接
const ws = new WebSocket('wss://example.com/socket');

// 连接成功
ws.onopen = () => {
  console.log('连接已建立');
  ws.send(JSON.stringify({ type: 'subscribe', channel: 'price' }));
};

// 接收消息
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('收到消息:', data);
};

// 连接关闭
ws.onclose = (event) => {
  console.log('连接已关闭', event.code, event.reason);
};

// 错误处理
ws.onerror = (error) => {
  console.error('连接错误:', error);
};

// 发送消息
ws.send('Hello Server!');
```

## 服务器端示例（Node.js）

```javascript
const WebSocket = require('ws');
const wss = new WebSocket.Server({ port: 8080 });

wss.on('connection', (ws) => {
  console.log('新客户端已连接');

  // 接收消息
  ws.on('message', (data) => {
    console.log('收到:', data.toString());
    // 回复消息
    ws.send(`服务器收到: ${data}`);
  });

  // 主动推送
  const timer = setInterval(() => {
    ws.send(`当前时间: ${new Date().toISOString()}`);
  }, 5000);

  ws.on('close', () => {
    console.log('客户端已断开');
    clearInterval(timer);
  });
});
```

## 注意事项

1. **连接管理** — 需要处理断线重连、心跳保活
2. **负载均衡** — 长连接对负载均衡器有特殊要求（需支持 sticky session）
3. **安全性** — 始终使用 `wss://`（WebSocket over TLS），如同 HTTPS
4. **代理兼容** — 部分 HTTP 代理不支持 WebSocket，需确认网络环境
5. **消息格式** — 仅支持文本和二进制，结构化数据需要自行序列化（如 JSON、Protobuf）

## 总结

WebSocket 解决了 HTTP 协议在实时通信场景下的核心痛点——**服务器无法主动向客户端推送数据**。通过一次握手建立持久连接后，双方可以自由双向通信，极大降低了延迟和带宽开销。它是现代 Web 实时应用的基础协议之一。
