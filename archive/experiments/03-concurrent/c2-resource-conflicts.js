// experiments/03-concurrent/c2-resource-conflicts.js
// 实验 1.3.2: 文件锁 / 资源冲突测试
// 测试两个 codebuddy 实例同时写入 MEMORY.md 是否有冲突

const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const memoryDir = path.join(
  process.env.HOME || process.env.USERPROFILE,
  '.codebuddy/projects/e-code-MyProject-CLIConductor/memory'
);

// 备份当前 MEMORY.md
const memoryPath = path.join(memoryDir, 'MEMORY.md');
const backupPath = memoryPath + '.backup';

if (fs.existsSync(memoryPath)) {
  fs.copyFileSync(memoryPath, backupPath);
  console.log('已备份 MEMORY.md');
}

// 启动两个并发实例，各自要求写入记忆
const p1 = exec(
  'codebuddy -p -y "Remember this: value_a=alpha. Just say OK." 2>/dev/null'
);

const p2 = exec(
  'codebuddy -p -y "Remember this: value_b=beta. Just say OK." 2>/dev/null'
);

let done = 0;
function checkDone() {
  done++;
  if (done === 2) {
    // 检查 MEMORY.md 是否损坏
    setTimeout(() => {
      if (fs.existsSync(memoryPath)) {
        const content = fs.readFileSync(memoryPath, 'utf-8');
        console.log('\n=== MEMORY.md 内容 ===');
        console.log(content);
        console.log('\n包含 value_a:', content.includes('alpha'));
        console.log('包含 value_b:', content.includes('beta'));
        
        // 恢复备份
        if (fs.existsSync(backupPath)) {
          fs.copyFileSync(backupPath, memoryPath);
          fs.unlinkSync(backupPath);
          console.log('已恢复 MEMORY.md');
        }
      }
    }, 3000);
  }
}

p1.on('exit', checkDone);
p2.on('exit', checkDone);

console.log('两个 codebuddy 实例已并发启动...');
