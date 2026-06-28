// Simple multi-turn chat: type, wait fixed time, type next
// Usage: node chat.js "q1" "q2" ...
const WebSocket = require('ws');
const questions = process.argv.slice(2);
if (!questions.length) { console.log('Usage: node chat.js "q1" "q2"'); process.exit(1); }

const TYPE_MS = 30;   // ms per char
const WAIT_MS = 4000; // wait after fully typed before next

let idx = 0;
const ws = new WebSocket('ws://localhost:6789');

ws.on('open', () => {
  console.log(`\nChat starting: ${questions.length} questions\n`);
  next();
});

function next() {
  if (idx >= questions.length) {
    console.log('\nDone.\n');
    setTimeout(() => process.exit(0), 1000);
    return;
  }
  const q = questions[idx];
  console.log(`[${idx+1}] Sending: ${q}`);
  typewrite(q + '\r', () => {
    console.log(`[${idx+1}] Sent, waiting ${WAIT_MS/1000}s...`);
    idx++;
    setTimeout(next, WAIT_MS);
  });
}

function typewrite(text, cb) {
  let i = 0;
  const t = setInterval(() => {
    if (i >= text.length) { clearInterval(t); cb(); return; }
    ws.send(text[i]); i++;
  }, TYPE_MS);
}

ws.on('message', d => process.stdout.write(d.toString()));
ws.on('error', e => { console.error(e); process.exit(1); });
