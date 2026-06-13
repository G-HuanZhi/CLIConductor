// experiments/02-pty-control/e02-slash-commands.js
// 实验 E02: 发送 / 指令到交互式 cbc
//
// 验证: /help, /model, /clear 等可通过 PTY 发送并观察到响应
// 运行方式: node experiments/02-pty-control/e02-slash-commands.js

const pty = require('node-pty');
const path = require('path');
const fs = require('fs');

const sessionDir = path.resolve(__dirname, '../../sessions/e02-test');
if (!fs.existsSync(sessionDir)) fs.mkdirSync(sessionDir, { recursive: true });

const BASH_PATH = 'E:\\Git\\usr\\bin\\bash.exe';

console.log('=== E02: 发送 / 指令到交互式 cbc ===\n');

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

// 发送 /help
setTimeout(() => {
  console.log('\n----- 发送 /help -----\n');
  shell.write('/help\n');
}, 30000);

// 发送 /model 列出模型
setTimeout(() => {
  console.log('\n----- 发送 /model -----\n');
  shell.write('/model\n');
}, 45000);

// 发送 /clear
setTimeout(() => {
  console.log('\n----- 发送 /clear -----\n');
  shell.write('/clear\n');
}, 60000);

// 收集结果
setTimeout(() => {
  console.log('\n\n===== E02 实验结果 =====');
  console.log('总输出字节:', totalBytes);

  const clean = output
    .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
    .replace(/\x1b\][0-9;]*[^\x07]*\x07/g, '')
    .replace(/\x1b[=<>FHLM6]/g, '')
    .replace(/\x1b\]0;[^\x07]*\x07/g, '')
    .replace(/[\x00-\x08\x0e-\x1f\x7f]/g, '')
    .trim();

  const hasHelp = /help/i.test(clean) && /command/i.test(clean);
  const hasModelList = /model/i.test(clean) && (/\w+-\w+/).test(clean);
  const hasClear = clean.includes('/clear');

  console.log('\n检测分析:');
  console.log('/help 输出中显示命令列表:', hasHelp ? '✅' : '❌');
  console.log('/model 输出中显示可用模型:', hasModelList ? '✅' : '❌');
  console.log('/clear 可执行:', hasClear ? '✅' : '(/clear 不会产生输出)');

  console.log('\n清洗后输出 (前 1500 字):');
  console.log(clean.substring(0, 1500));

  shell.kill();
  process.exit(0);
}, 75000);
