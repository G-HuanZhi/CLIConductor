// experiments/02-pty-control/t2-node-pty-v2.js
// 实验 1.2.2: node-pty 启动 codebuddy 子进程
// 修复：使用 bash 包装 codebuddy 命令

const pty = require('node-pty');

console.log('=== 实验: codebuddy --print 通过 PTY (bash 包装) ===\n');

const cbc = pty.spawn('E:\\Git\\usr\\bin\\bash.exe', ['-c', 'codebuddy -p -y "Say exactly: PTY_SUCCESS" 2>/dev/null'], {
  name: 'xterm-color',
  cols: 120,
  rows: 40,
  cwd: process.cwd(),
  env: { ...process.env },
});

let cbcOut = '';

cbc.onData((data) => {
  cbcOut += data;
});

cbc.onExit((exitCode) => {
  console.log('退出码:', exitCode);
  
  // 剥离 ANSI 序列
  const clean = cbcOut
    .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
    .replace(/\x1b\][0-9;]*[^\x07]*\x07/g, '')
    .replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g, '');
    
  console.log('\n--- 原始输出 (前500字) ---');
  console.log(cbcOut.substring(0, 500));
  console.log('\n--- 清洗后 ---');
  console.log(clean);
  console.log('\n包含 PTY_SUCCESS:', cbcOut.includes('PTY_SUCCESS'));
  console.log('\n实验完成!');
});
