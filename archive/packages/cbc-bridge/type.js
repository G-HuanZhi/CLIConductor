// Type text character by character, like a real keyboard
const WebSocket = require('ws');
const text = process.argv.slice(2).join(' ') + '\r';
const ws = new WebSocket('ws://localhost:6789');

ws.on('open', () => {
  let i = 0;
  const timer = setInterval(() => {
    if (i >= text.length) { clearInterval(timer); setTimeout(() => process.exit(0), 1000); return; }
    ws.send(text[i]);
    i++;
  }, 30); // 30ms per char ≈ 33 chars/sec
});

ws.on('error', e => { console.error(e.message); process.exit(1); });
