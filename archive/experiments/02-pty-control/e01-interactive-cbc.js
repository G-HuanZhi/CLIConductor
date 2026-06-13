// experiments/02-pty-control/e01-interactive-cbc.js
// 实验 E01: PTY 启动交互式 cbc
//
// 方案：通过 bash 启动交互式 codebuddy，使用 bash 包装解决 Windows 上直接 spawn 失败的问题
// 运行方式: node experiments/02-pty-control/e01-interactive-cbc.js

const pty = require('node-pty');
const path = require('path');
const fs = require('fs');

const sessionDir = path.resolve(__dirname, '../../sessions/e01-test');
if (!fs.existsSync(sessionDir)) fs.mkdirSync(sessionDir, { recursive: true });

const BASH_PATH = 'E:\\Git\\usr\\bin\\bash.exe';

console.log('=== E01: PTY 启动交互式 cbc ===\n');
console.log('工作目录:', sessionDir);
console.log('bash:', BASH_PATH);

// 先 spawn bash，再通过 bash 启动 codebuddy
const shell = pty.spawn(BASH_PATH, [], {
  name: 'xterm-color',
  cols: 120,
  rows: 40,
  cwd: sessionDir,
  env: Object.assign({}, process.env, {
    TERM: 'xterm-256color',
  }),
});

let output = '';
let totalBytes = 0;
let lastOutputSize = 0;
let stableCount = 0;
let phase = 'booting';

shell.onData((data) => {
  output += data;
  totalBytes += data.length;
  process.stdout.write(data);
});

// 等 bash 启动后，启动 codebuddy
setTimeout(() => {
  console.log('\n===== 启动 codebuddy 交互模式 =====\n');
  shell.write('codebuddy\n');
  phase = 'starting-cbc';
}, 2000);

// 等 codebuddy 启动并出现提示符后，发送一条消息
setTimeout(() => {
  console.log('\n===== 发送: "Say hello in exactly one word" =====\n');
  shell.write('Say hello in exactly one word\n');
  phase = 'first-msg';
}, 25000);  // cbc 启动需要时间

// 等回复完成后，发送 /clear
setTimeout(() => {
  console.log('\n===== 发送: /clear =====\n');
  shell.write('/clear\n');
  phase = 'slash-command';
}, 45000);

// 最终收集结果
setTimeout(() => {
  console.log('\n\n===== E01 实验结果 =====');
  console.log('总输出字节:', totalBytes);
  
  const hasPrompt = /›|>|\$/.test(output);
  const hasHello = /hello|Hello|HELLO/.test(output);
  const hasSlashClear = output.includes('/clear');

  // 尝试提取最后一段有效输出
  const lines = output.split('\n').filter(l => l.trim());
  const lastLines = lines.slice(-15);
  
  console.log('检测到提示符:', hasPrompt);
  console.log('检测到 hello:', hasHello);
  console.log('检测到 /clear:', hasSlashClear);
  console.log('\n最后 15 行非空输出:');
  lastLines.forEach(l => console.log('  ' + l.substring(0, 120)));

  // ANSI 剥离
  const clean = output
    .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
    .replace(/\x1b\][0-9;]*[^\x07]*\x07/g, '')
    .replace(/\x1b[=<>FHLM6]/g, '')
    .replace(/\x1b\]0;[^\x07]*\x07/g, '')
    .replace(/[\x00-\x08\x0e-\x1f\x7f]/g, '')
    .trim();

  console.log('\n清洗后完整输出 (前 1000 字):');
  console.log(clean.substring(0, 1000));
  
  // 判断 E01 结果
  const started = /›|>/.test(clean) || /codebuddy/i.test(clean);
  const replied = /hello/gi.test(clean);
  
  console.log('\n===== E01 判定 =====');
  console.log('交互式 cbc 启动:', started ? '✅' : '❌');
  console.log('消息读取并回复:', replied ? '✅' : '❌');
  console.log('/clear 可执行:', output.includes('/clear') ? '✅' : '❌');
  
  shell.kill();
  process.exit(0);
}, 65000);
