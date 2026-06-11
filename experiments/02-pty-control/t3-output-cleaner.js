// experiments/02-pty-control/t3-output-cleaner.js
// 实验 1.2.3: 终端输出清洗工具
//
// 运行方式: node experiments/02-pty-control/t3-output-cleaner.js

const pty = require('node-pty');

// ============================================================
// ANSI 剥离函数
// ============================================================

/**
 * 剥离 ANSI 转义序列，保留纯文本
 */
function stripAnsi(text) {
  return text
    // CSI 序列 (大部分控制序列)
    .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
    // OSC 序列 (标题文本等)
    .replace(/\x1b\][0-9;]*[^\x07]*\x07/g, '')
    // 其他 escape 序列
    .replace(/\x1b[PX^_].*?\x1b\\/g, '')
    // SOS/PM/APC 序列
    .replace(/\x1b\[[0-9]*[^0-9;]/g, '')
    // 独立 escape 字符
    .replace(/\x1b[=>]/g, '');
}

/**
 * 从 PTY 输出中提取最后一次响应（去除提示符和命令回显）
 */
function extractLastResponse(output, command) {
  // 去除 ANSI 序列
  let text = stripAnsi(output);
  
  // 去除命令回显 (shell 会回显输入的命令)
  if (command) {
    const escapedCmd = command.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const cmdRegex = new RegExp(escapedCmd + '\\s*', 'g');
    text = text.replace(cmdRegex, '');
  }
  
  // 去除提示符 (PS > 或 $ 等)
  text = text.replace(/PS\s+[A-Z]:[^\n>]*>/g, '');
  text = text.replace(/^\s*(>|\$|#)\s*/gm, '');
  
  // 去除空白行
  text = text.replace(/\n{3,}/g, '\n\n').trim();
  
  return text;
}

// ============================================================
// 测试: 启动 shell 并执行命令
// ============================================================

console.log('=== 测试输出清洗 ===\n');

const shell = pty.spawn('powershell.exe', [], {
  name: 'xterm-color',
  cols: 120,
  rows: 40,
  cwd: process.cwd(),
  env: process.env,
});

const command = 'echo "HELLO_CLEANER_TEST"';

let rawOutput = '';

shell.onData((data) => {
  rawOutput += data;
});

shell.write(command + '\r\n');
shell.write('exit\r\n');

setTimeout(() => {
  console.log('原始输出:');
  console.log(JSON.stringify(rawOutput.substring(0, 200)));
  console.log();
  
  const cleaned = extractLastResponse(rawOutput, command);
  console.log('清洗后:');
  console.log(cleaned);
  console.log();
  
  console.log('包含 HELLO_CLEANER_TEST:', cleaned.includes('HELLO_CLEANER_TEST'));
  
  shell.kill();
  console.log('\n=== 实验完成 ===');
}, 2000);
