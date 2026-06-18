// experiments/03-concurrent/c2-resource-conflicts.js
// 瀹為獙 1.3.2: 鏂囦欢閿?/ 璧勬簮鍐茬獊娴嬭瘯
// 娴嬭瘯涓や釜 codebuddy 瀹炰緥鍚屾椂鍐欏叆 MEMORY.md 鏄惁鏈夊啿绐?
const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const memoryDir = path.join(
  process.env.HOME || process.env.USERPROFILE,
  '.codebuddy/projects/e-code-MyProject-CLIConductor/memory'
);

// 澶囦唤褰撳墠 MEMORY.md
const memoryPath = path.join(memoryDir, 'MEMORY.md');
const backupPath = memoryPath + '.backup';

if (fs.existsSync(memoryPath)) {
  fs.copyFileSync(memoryPath, backupPath);
  console.log('宸插浠?MEMORY.md');
}

// 鍚姩涓や釜骞跺彂瀹炰緥锛屽悇鑷姹傚啓鍏ヨ蹇?const p1 = exec(
  'codebuddy -p -y "Remember this: value_a=alpha. Just say OK." 2>/dev/null'
);

const p2 = exec(
  'codebuddy -p -y "Remember this: value_b=beta. Just say OK." 2>/dev/null'
);

let done = 0;
function checkDone() {
  done++;
  if (done === 2) {
    // 妫€鏌?MEMORY.md 鏄惁鎹熷潖
    setTimeout(() => {
      if (fs.existsSync(memoryPath)) {
        const content = fs.readFileSync(memoryPath, 'utf-8');
        console.log('\n=== MEMORY.md 鍐呭 ===');
        console.log(content);
        console.log('\n鍖呭惈 value_a:', content.includes('alpha'));
        console.log('鍖呭惈 value_b:', content.includes('beta'));
        
        // 鎭㈠澶囦唤
        if (fs.existsSync(backupPath)) {
          fs.copyFileSync(backupPath, memoryPath);
          fs.unlinkSync(backupPath);
          console.log('宸叉仮澶?MEMORY.md');
        }
      }
    }, 3000);
  }
}

p1.on('exit', checkDone);
p2.on('exit', checkDone);

console.log('涓や釜 codebuddy 瀹炰緥宸插苟鍙戝惎鍔?..');

