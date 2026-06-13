const { spawn } = require('node-pty');
const { WebSocketServer } = require('ws');
const http = require('http');
const PORT = 6790;
const WORKDIR = 'C:\\Users\\14709\\.openclaw\\workspace';

let pty = null;
let ptyBuf = Buffer.alloc(0);
const MAX_BUF = 102400;

const server = http.createServer((req, res) => {
  if (req.url === '/') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>CBC B</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm/css/xterm.css"/>
<style>*{margin:0;padding:0}body{background:#1e1e1e}#term{height:100vh}</style>
</head><body><div id="term"></div>
<script src="https://cdn.jsdelivr.net/npm/xterm/lib/xterm.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit/lib/xterm-addon-fit.js"></script>
<script>
const t=new Terminal({cursorBlink:true,fontSize:14,theme:{background:'#2d2d2d'}});
const f=new FitAddon.FitAddon();
t.loadAddon(f);
t.open(document.getElementById('term'));f.fit();
async function poll(){try{const r=await fetch('/snapshot');const txt=await r.text();if(txt){t.reset();t.write(txt)}}catch(e){}setTimeout(poll,800)}
poll();
window.addEventListener('resize',()=>f.fit());
</script></body></html>`);
  } else if (req.url === '/snapshot') {
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end(ptyBuf.slice(-5000).toString('utf8'));
  } else {
    res.writeHead(200); res.end('ok');
  }
});

const wss = new WebSocketServer({ server });
wss.on('connection', ws => {
  console.log(`[WS-B] client connected (${wss.clients.size} total)`);
  if (!pty) {
    pty = spawn('cmd.exe', ['/c', 'cbc'], {
      name: 'xterm-256color', cols: 120, rows: 40, cwd: WORKDIR,
      env: { ...process.env, TERM: 'xterm-256color' },
    });
    pty.onData(data => {
      const b = Buffer.from(data, 'utf8');
      ptyBuf = Buffer.concat([ptyBuf, b]);
      if (ptyBuf.length > MAX_BUF * 2) ptyBuf = ptyBuf.slice(ptyBuf.length - MAX_BUF * 2);
      wss.clients.forEach(c => { if (c.readyState === 1) c.send(b.toString('utf8')); });
    });
    pty.onExit(() => { wss.clients.forEach(c => { if (c.readyState === 1) c.close(); }); pty = null; });
  }
  setTimeout(() => { if (ws.readyState === 1 && ptyBuf.length > 0) ws.send(ptyBuf.toString('utf8')); }, 200);
  ws.on('message', msg => pty.write(msg.toString()));
  ws.on('close', () => console.log(`[WS-B] client disconnected (${wss.clients.size} total)`));
});

server.listen(PORT, () => {
  console.log(`\n  🚀 CBC B on ws://localhost:${PORT}`);
  console.log(`  🌐  http://localhost:${PORT}\n`);
});
