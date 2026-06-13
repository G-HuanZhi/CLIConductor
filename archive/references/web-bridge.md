# Web Bridge 方案（参考备用）

> 通过 xterm.js 在浏览器中访问共享 cbc 会话。
> 当前首选方案是原生 PowerShell 客户端（connect.ps1），此方案作为备选保留。

## 架构

```
你（浏览器 xterm.js）─ WS → server.js ─ node-pty → cbc
我（WebSocket）　　　 ─ WS →
```

## 核心代码

server.js 中内嵌的 HTML 页面：

```html
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>CBC Bridge</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm/css/xterm.css"/>
<style>*{margin:0;padding:0}body{background:#1e1e1e}#term{height:100vh}</style>
</head><body><div id="term"></div>
<script src="https://cdn.jsdelivr.net/npm/xterm/lib/xterm.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit/lib/xterm-addon-fit.js"></script>
<script>
const t=new Terminal({cursorBlink:true,fontSize:14,theme:{background:'#1e1e1e'}});
const f=new FitAddon.FitAddon();
t.loadAddon(f);
t.open(document.getElementById('term'));
f.fit();
window.addEventListener('resize',()=>f.fit());

const ws=new WebSocket('ws://'+location.host);
ws.onmessage=e=>t.write(e.data);
t.onData(d=>ws.send(d));

// 通知服务端 PTY 窗口尺寸变化
function sendResize(){const p=f.proposeDimensions();if(p)ws.send('__resize__'+p.cols+','+p.rows)}
window.addEventListener('resize',()=>{f.fit();sendResize()});
setTimeout(()=>{f.fit();sendResize()},200);
</script></body></html>
```

## 服务端接收 resize

```javascript
if (text.startsWith('__resize__')) {
  const [cols, rows] = text.replace('__resize__', '').split(',').map(Number);
  if (pty && cols && rows) pty.resize(cols, rows);
}
```

## 已知问题

- cbc 的 TUI 大量依赖 ANSI 光标定位 + 窗口尺寸同步
- xterm.js 在全屏 TUI 场景下可能出现画面重复/重绘异常
- 根本原因是浏览器终端 VS 原生终端对 TUI escape code 的处理差异
