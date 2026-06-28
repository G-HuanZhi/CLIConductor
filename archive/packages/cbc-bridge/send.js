// Usage: node send.js "<command>"
const WebSocket = require('ws');
const msg = process.argv.slice(2).join(' ') + '\r\n';
const ws = new WebSocket('ws://localhost:6789');
let buf = '';
ws.on('open', () => {
  ws.send(msg);
  // Wait for output, then exit
  setTimeout(() => process.exit(0), 4000);
});
ws.on('message', d => {
  buf += d.toString();
});
ws.on('close', () => process.exit(0));
ws.on('error', () => process.exit(1));
