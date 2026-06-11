// experiments/02-pty-control/e04-multiturn-pty.js
// 实验 E04: 同一 PTY 进程内多轮对话
//
// 验证: 通过 PTY 在同一交互式 cbc 进程内完成多轮连续对话
// 运行方式: node experiments/02-pty-control/e04-multiturn-pty.js

const pty = require('node-pty');
const path = require('path');
const fs = require('fs');

const sessionDir = path.resolve(__dirname, '../../sessions/e04-test');
if (!fs.existsSync(sessionDir)) fs.mkdirSync(sessionDir, { recursive: true });

const BASH_PATH = 'E:\\Git\\usr\\bin\\bash.exe';

console.log('=== E04: 同一 PTY 进程内多轮对话 ===\n');

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

// 第一轮: 简单问候
setTimeout(() => {
  console.log('\n----- 第一轮: "Say hello in one word" -----\n');
  shell.write('Say hello in one word\n');
}, 30000);

// 第二轮: 询问名字 (验证上下文)
setTimeout(() => {
  console.log('\n----- 第二轮: "What is my name?" -----\n');
  shell.write('What is the previous user message?\n');
}, 55000);

// 第三轮: 数学问题 (验证推理)
setTimeout(() => {
  console.log('\n----- 第三轮: "Calculate 15+27" -----\n');
  shell.write('Calculate 15+27\n');
}, 80000);

setTimeout(() => {
  console.log('\n\n===== E04 实验结果 =====');
  console.log('总输出字节:', totalBytes);

  const clean = output
    .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
    .replace(/\x1b\][0-9;]*[^\x07]*\x07/g, '')
    .replace(/\x1b[=<>FHLM6]/g, '')
    .replace(/\x1b\]0;[^\x07]*\x07/g, '')
    .replace(/[\x00-\x08\x0e-\x1f\x7f]/g, '')
    .trim();

  const round1Done = /hello/i.test(clean);
  const round2Started = /previous/i.test(clean);
  const round3Started = /15.*27|42/.test(clean);

  console.log('\n检测分析:');
  console.log('第一轮 (hello):', round1Done ? '✅' : '❌ (可能超时)');
  console.log('第二轮 (上下文):', round2Started ? '✅ (消息已发送)' : '❌');
  console.log('第三轮 (计算):', round3Started ? '✅ (消息已发送/回复)' : '❌');

  console.log('\n清洗后输出 (最后 1200 字):');
  console.log(clean.slice(-1200));

  shell.kill();
  process.exit(0);
}, 105000);
