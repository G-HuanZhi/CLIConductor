// Terminal client for CBC Bridge
// Run: node connect.js
// Uses your real terminal for native ANSI rendering
const WebSocket = require('ws');
const readline = require('readline');

const HOST = process.argv[2] || 'localhost';
const PORT = process.argv[3] || 6789;

const ws = new WebSocket(`ws://${HOST}:${PORT}`);

ws.on('open', () => {
  // Raw mode stdin: one character at a time
  process.stdin.setRawMode(true);
  process.stdin.resume();
  process.stdin.setEncoding('utf8');

  process.stdin.on('data', chunk => {
    ws.send(chunk);
  });
});

ws.on('message', data => {
  process.stdout.write(data.toString());
});

ws.on('close', () => {
  process.stdin.setRawMode(false);
  process.stdin.pause();
  process.exit(0);
});

ws.on('error', err => {
  console.error('Connection error:', err.message);
  process.exit(1);
});

// Handle Ctrl+C gracefully
process.on('SIGINT', () => {
  ws.close();
});
