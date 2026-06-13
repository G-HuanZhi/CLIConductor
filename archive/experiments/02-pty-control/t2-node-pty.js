// experiments/02-pty-control/t2-node-pty.js
// 实验 1.2.2: node-pty 启动子进程并操控
//
// 运行方式: node experiments/02-pty-control/t2-node-pty.js

const pty = require('node-pty');
const path = require('path');
const fs = require('fs');

// ============================================================
// 1. 启动 PowerShell 子进程
// ============================================================
console.log('=== 实验 1: 启动 powershell 并执行命令 ===\n');

const shell = pty.spawn('powershell.exe', [], {
  name: 'xterm-color',
  cols: 120,
  rows: 40,
  cwd: process.cwd(),
  env: process.env,
});

let output = '';
shell.onData((data) => {
  output += data;
  process.stdout.write(data);  // 实时输出
});

// 发送命令
shell.write('echo "Hello from PTY!"\r\n');
shell.write('Get-Date\r\n');
shell.write('exit\r\n');

// 等待进程结束
setTimeout(() => {
  console.log('\n=== 实验 1 完成 ===');
  console.log('总输出长度:', output.length);
}, 2000);


// ============================================================
// 2. 启动 cmd 并测试特殊按键
// ============================================================
setTimeout(() => {
  console.log('\n=== 实验 2: 测试 ANSI 转义序列 ===\n');

  const term = pty.spawn('cmd.exe', [], {
    name: 'xterm-color',
    cols: 100,
    rows: 30,
    cwd: process.cwd(),
    env: process.env,
  });

  let buf = '';
  const KEYS = {
    enter: '\r\n',
    up: '\x1b[A',
    down: '\x1b[B',
    ctrlC: '\x03',
  };

  term.onData((data) => buf += data);

  term.write(KEYS.up);           // 上箭头 (历史命令)
  term.write(KEYS.down);         // 下箭头
  term.write('echo TEST_SPECIAL_KEYS' + KEYS.enter);

  setTimeout(() => {
    const clean = buf.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '');
    console.log('清洗后输出:', clean.trim().split('\n').filter(l => l.trim()));
    term.kill();
  }, 1500);
}, 3000);


// ============================================================
// 3. 启动 codebuddy 交互模式 (通过 PTY)
// ============================================================
setTimeout(() => {
  console.log('\n=== 实验 3: codebuddy --print 通过 PTY ===\n');

  // 使用 -p 模式，更快
  const cbc = pty.spawn('codebuddy', ['-p', '-y', 'Say "PTY_WORKS" in one word'], {
    name: 'xterm-color',
    cols: 120,
    rows: 40,
    cwd: process.cwd(),
    env: process.env,
  });

  let cbcOut = '';
  cbc.onData((data) => cbcOut += data);
  cbc.onExit(() => {
    console.log('Exit code:', cbc.process);
    const clean = cbcOut.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
                        .replace(/\x1b\][0-9;]*[^\x07]*\x07/g, '');
    console.log('清洗后输出 (前300字):', clean.substring(0, 300));
    console.log('包含 PTY_WORKS:', cbcOut.includes('PTY_WORKS') || cbcOut.includes('PTY'));
    console.log('\n所有实验完成!');
  });
}, 5000);
