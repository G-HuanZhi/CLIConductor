const WebSocket = require('ws');
const ws = new WebSocket('ws://localhost:6789');

ws.on('open', () => {
  console.log('Claw connected to cbc bridge');
});

ws.on('message', data => {
  // strip ANSI and log clean text
  const clean = data.toString().replace(/\x1B\[[0-9;]*[a-zA-Z]/g, '').replace(/\x1B\][0-9;]*(?:\x1B\\|\x07)/g, '').trim();
  if (clean) console.log('[cbc]', clean);
});

ws.on('close', () => console.log('Disconnected'));
ws.on('error', err => console.error('WS error:', err.message));

// Listen for commands from parent process stdin
process.stdin.on('data', chunk => {
  ws.send(chunk.toString());
});
