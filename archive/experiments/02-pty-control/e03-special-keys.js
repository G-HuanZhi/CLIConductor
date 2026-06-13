// experiments/02-pty-control/e03-special-keys.js
// 实验 E03: 发送特殊按键到交互式 cbc
//
// 验证 Tab (补全切换)、Ctrl+C (中断生成) 在 PTY 中的行为
// 运行方式: node experiments/02-pty-control/e03-special-keys.js

const pty = require('node-pty');
const path = require('path');
const fs = require('fs');

const sessionDir = path.resolve(__dirname, '../../sessions/e03-test');
if (!fs.existsSync(sessionDir)) fs.mkdirSync(sessionDir, { recursive: true });

const BASH_PATH = 'E:\\Git\\usr\\bin\\bash.exe';

console.log('=== E03: 发送特殊按键到交互式 cbc ===\n');

const shell = pty.spawn(BASH_PATH, [], {
  name: 'xterm-color',
  cols: 120,
  rows: 40,
  cwd: sessionDir,
  env: Object.assign({}, process.env, { TERM: 'xterm-256color' }),
});

let output = '';
let totalBytes = 0;

shell.onData((data) => {
  output += data;
  totalBytes += data.length;
});

// 启动 codebuddy
setTimeout(() => { shell.write('codebuddy\n'); }, 2000);

// 发送 Tab (触发 thinking 切换)
setTimeout(() => {
  console.log('\n----- 发送 Tab (thinking on/off 切换) -----\n');
  shell.write('\t');  // Tab 键
}, 30000);

// 等待观察 Tab 效果后清理
setTimeout(() => {
  console.log('\n----- 发送 /clear -----\n');
  shell.write('/clear\n');
}, 40000);

// 发送一条长 prompt 然后 Ctrl+C 中断
setTimeout(() => {
  console.log('\n----- 发送长 prompt: "Write a 500-word essay..." -----\n');
  shell.write('Write a 500-word essay about AI\n');
}, 55000);

// 中断
setTimeout(() => {
  console.log('\n----- 发送 Ctrl+C 中断 -----\n');
  shell.write('\x03');  // Ctrl+C
}, 65000);

setTimeout(() => {
  console.log('\n\n===== E03 实验结果 =====');
  console.log('总输出字节:', totalBytes);

  const clean = output
    .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
    .replace(/\x1b\][0-9;]*[^\x07]*\x07/g, '')
    .replace(/\x1b[=<>FHLM6]/g, '')
    .replace(/\x1b\]0;[^\x07]*\x07/g, '')
    .replace(/[\x00-\x08\x0e-\x1f\x7f]/g, '')
    .trim();

  const hasTabEffect = /thinking.*tab|tab.*thinking/i.test(clean);
  const hasInterrupt = /interrupt|abort|break/i.test(clean) || clean.includes('\x03');

  console.log('\n检测分析:');
  console.log('Tab 切换思考模式:', hasTabEffect ? '✅ (检测到效果文本)' : '⚠️ (Tab 在 TUI 内无声切换，需肉眼观察)');
  console.log('Ctrl+C 中断:', hasInterrupt ? '✅' : '⚠️ (可能回到提示符)');
  
  console.log('\n清洗后输出 (最后 800 字):');
  console.log(clean.slice(-800));

  shell.kill();
  process.exit(0);
}, 80000);
