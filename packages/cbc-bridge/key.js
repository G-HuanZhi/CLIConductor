// Send special keys to cbc bridge
// Usage: node key.js <key>
//   tab, enter, esc, ctrl-c, backspace
//   alt-<char>   e.g. alt-m, alt-t
//   ctrl-<char>  e.g. ctrl-d
const WebSocket = require('ws');
const keyMap = {
  'tab': '\t',
  'enter': '\r',
  'esc': '\x1b',
  'ctrl-c': '\x03',
  'ctrl-d': '\x04',
  'backspace': '\x7f',
};

const key = process.argv[2];
let seq;

if (keyMap[key]) {
  seq = keyMap[key];
} else if (key && key.startsWith('alt-')) {
  seq = '\x1b' + key.slice(4);
} else if (key && key.startsWith('ctrl-')) {
  seq = String.fromCharCode(key.slice(5).charCodeAt(0) - 64);
} else {
  console.error('Unknown key:', key);
  console.error('Usage: node key.js tab|enter|esc|ctrl-c|alt-m|backspace');
  process.exit(1);
}

const ws = new WebSocket('ws://localhost:6789');
ws.on('open', () => {
  ws.send(seq);
  setTimeout(() => process.exit(0), 1000);
});
ws.on('error', e => { console.error(e.message); process.exit(1); });
