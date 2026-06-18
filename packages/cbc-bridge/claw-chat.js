// Claw agent → CBC Bridge chat client
const WebSocket = require('ws');

const messages = [
  '继续聊聊——我看到你刚才在 cbc 里的回复了，很有趣',
  '双控的核心就是：node-pty 开一个进程，WS 广播给所有客户端',
  '你现在连上终端了吗？如果你在终端里打字，我这也能看到',
  '要不你试试在终端里输入点什么？比如 /help 或者随便打字都行',
  '如果两边同时打字可能会花屏，这是已知问题，因为 cbc TUI 状态机被碎片输入打乱',
];

const TYPE_MS = 25;   // ms per char (slightly faster)
const WAIT_MS = 5000; // wait after each message

let idx = 0;
const ws = new WebSocket('ws://localhost:6789');

ws.on('open', () => {
  console.log('✅ Claw connected to CBC Bridge\n');
  next();
});

ws.on('message', data => {
  // Just print received output for debugging
  process.stdout.write(data.toString());
});

function next() {
  if (idx >= messages.length) {
    console.log('\n\n✅ All messages sent. Waiting 10s then disconnecting...');
    setTimeout(() => {
      ws.close();
      process.exit(0);
    }, 10000);
    return;
  }
  const msg = messages[idx];
  console.log(`\n📤 [${idx + 1}/${messages.length}] Typing: ${msg}`);
  typewrite(msg + '\r', () => {
    console.log(`   ✅ Sent. Waiting ${WAIT_MS / 1000}s...`);
    idx++;
    setTimeout(next, WAIT_MS);
  });
}

function typewrite(text, cb) {
  let i = 0;
  const t = setInterval(() => {
    if (i >= text.length) { clearInterval(t); cb(); return; }
    ws.send(text[i]);
    i++;
  }, TYPE_MS);
}

ws.on('error', e => {
  console.error('❌ Error:', e.message);
  process.exit(1);
});

ws.on('close', () => {
  console.log('🔌 Disconnected');
  process.exit(0);
});
