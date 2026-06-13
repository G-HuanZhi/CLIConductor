const { spawn } = require('node-pty');
const { WebSocketServer } = require('ws');
const http = require('http');
const PORT = 6789;
const WORKDIR = 'C:\\Users\\14709\\.openclaw\\workspace';

let pty = null;

// ── Snapshot buffer for web viewers ──
let latestSnapshot = Buffer.alloc(0);

// ── HTTP: web terminal (read-only polling) + health ──
const server = http.createServer((req, res) => {
  if (req.url === '/') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(getWebHTML());
  } else if (req.url === '/snapshot') {
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end(latestSnapshot.toString('utf8'));
  } else {
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('CBC Bridge alive');
  }
});

// ── Ring buffer for late WS joiners ──
const MAX_BUF = 102400;
let ptyBuf = Buffer.alloc(0);

function pushBuf(data) {
  const b = Buffer.from(data, 'utf8');
  ptyBuf = Buffer.concat([ptyBuf, b]);
  if (ptyBuf.length > MAX_BUF) ptyBuf = ptyBuf.slice(ptyBuf.length - MAX_BUF);
  // Also update snapshot (last 5000 chars for HTTP polling)
  latestSnapshot = Buffer.concat([latestSnapshot, b]);
  if (latestSnapshot.length > 5000) latestSnapshot = latestSnapshot.slice(latestSnapshot.length - 5000);
}

// ── WebSocket: terminal clients only (connect.js / claw) ──
const wss = new WebSocketServer({ server });
wss.on('connection', ws => {
  console.log(`[WS] client connected (${wss.clients.size} total)`);

  if (!pty) {
    pty = spawn('cmd.exe', ['/c', 'cbc'], {
      name: 'xterm-256color',
      cols: 120,
      rows: 40,
      cwd: WORKDIR,
      env: { ...process.env, TERM: 'xterm-256color' },
    });
    pty.onData(data => {
      pushBuf(data);
      wss.clients.forEach(c => { if (c.readyState === 1) c.send(data); });
    });
    pty.onExit(() => {
      wss.clients.forEach(c => { if (c.readyState === 1) c.close(); });
      pty = null;
    });
  }

  // Drain buffer to late joiner
  setTimeout(() => {
    if (ws.readyState === 1 && ptyBuf.length > 0) {
      ws.send(ptyBuf.toString('utf8'));
    }
  }, 200);

  ws.on('message', msg => {
    const text = msg.toString();
    if (text.startsWith('__resize__')) {
      const [cols, rows] = text.replace('__resize__', '').split(',').map(Number);
      if (pty && cols && rows) pty.resize(cols, rows);
    } else {
      pty.write(text);
    }
  });
  ws.on('close', () => console.log(`[WS] client disconnected (${wss.clients.size} total)`));
});

function getWebHTML() {
  return `<!DOCTYPE html>
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

async function poll() {
  try {
    const r=await fetch('/snapshot');
    const txt=await r.text();
    if(txt){
      t.reset();
      t.write(txt);
    }
  } catch(e){}
  setTimeout(poll, 800);
}
poll();
window.addEventListener('resize',()=>f.fit());
</script></body></html>`;
}

server.listen(PORT, () => {
  console.log(`\n  🚀 CBC Bridge → http://localhost:${PORT}`);
  console.log(`  🖥️  Terminal:     node packages/cbc-bridge/connect.js`);
  console.log(`  🌐  Web (RO):    http://localhost:${PORT}\n`);
});
