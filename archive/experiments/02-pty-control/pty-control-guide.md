# PTY 操控 CLI 完整指南

> 通过 PTY 实现对任意 CLI 的全输出捕获 + 非键盘输入控制（Tab 选择、箭头键、/ 命令等）。

---

## 一、完整输出捕获

### 1.1 node-pty 基本使用

```typescript
import * as pty from 'node-pty';

const term = pty.spawn('powershell.exe', [], {
  name: 'xterm-color',
  cols: 120,
  rows: 40,
  cwd: process.cwd(),
  env: { ...process.env, TERM: 'xterm-256color' },
});
```

### 1.2 捕获所有输出（含 ANSI 序列）

```typescript
// onData 会收到所有输出，包括颜色码、光标移动、清屏等控制序列
let rawBuffer = '';

term.onData((data: string) => {
  rawBuffer += data;
  console.log('原始输出:', JSON.stringify(data));
  // 输出示例：
  // "\x1b[32mHello\x1b[0m\n"     → 绿色 "Hello"
  // "\x1b[?25l"                   → 隐藏光标
  // "\x1b[2J\x1b[H"               → 清屏并移到左上角
  // "\x1b[1;1H\x1b[K"             → 移到第1行第1列，清除该行
});
```

### 1.3 输出缓冲管理

PTY 输出是流式的，不是完整帧。需要自建缓冲区：

```typescript
class PtyOutputBuffer {
  private buffer = '';
  private readonly frameTimeout = 200; // ms，判定一帧结束的空闲时间
  private frameTimer: NodeJS.Timeout | null = null;
  private lastFlush = 0;

  feed(data: string, onFrame: (text: string, raw: string) => void) {
    this.buffer += data;
    this.lastFlush = Date.now();

    // 延迟判定：空闲 N ms 后认为一帧结束
    if (this.frameTimer) clearTimeout(this.frameTimer);
    this.frameTimer = setTimeout(() => {
      const raw = this.buffer;
      const clean = this.stripAnsi(raw);
      onFrame(clean, raw);
      this.buffer = '';
    }, this.frameTimeout);
  }

  stripAnsi(text: string): string {
    // 简单版 ANSI 剥离（生产环境用 strip-ansi 库）
    return text.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
               .replace(/\x1b\][0-9;]*[^\x07]*\x07/g, '')
               .replace(/\x1b\][0-9;]*\x1b\\/g, '')
               .replace(/\x1b[PX^_].*?\x1b\\/g, '');
  }
}
```

### 1.4 同步读取（等待特定输出）

```typescript
function waitForOutput(
  term: pty.IPty,
  predicate: (text: string) => boolean,
  timeoutMs = 10000
): Promise<string> {
  return new Promise((resolve, reject) => {
    const collected: string[] = [];
    const timer = setTimeout(() => {
      term.removeListener('data', handler);
      reject(new Error(`等待输出超时 (${timeoutMs}ms)`));
    }, timeoutMs);

    const handler = (data: string) => {
      collected.push(data);
      const full = collected.join('');
      if (predicate(full)) {
        clearTimeout(timer);
        term.removeListener('data', handler);
        resolve(full);
      }
    };

    term.onData(handler);
  });
}

// 用法：等待 CLI 出现提示符
await waitForOutput(term, (text) => text.includes('>'));
```

---

## 二、非键盘输入：ANSI 转义序列全集

PTY 的 `write()` 可以直接发送 ANSI 转义序列模拟所有特殊按键，**完全不需要物理键盘**。

### 2.1 控制字符

| 按键 | 序列 | 说明 |
|------|------|------|
| Enter | `\r` 或 `\n` | 对于交互式 CLI，`\r` 更可靠 |
| Tab | `\t` | 触发补全 |
| Backspace | `\x7f` 或 `\b` | 删除前一个字符 |
| Escape | `\x1b` | 退出当前模式 |
| Ctrl+C | `\x03` | 中断程序 |
| Ctrl+D | `\x04` | EOF |
| Ctrl+Z | `\x1a` | 挂起进程 (Windows) |
| Ctrl+L | `\x0c` | 清屏 |

### 2.2 方向键

| 按键 | 序列 |
|------|------|
| 上箭头 ↑ | `\x1b[A` |
| 下箭头 ↓ | `\x1b[B` |
| 右箭头 → | `\x1b[C` |
| 左箭头 ← | `\x1b[D` |

### 2.3 组合方向键

| 按键 | 序列 |
|------|------|
| Ctrl+↑ | `\x1b[1;5A` |
| Ctrl+↓ | `\x1b[1;5B` |
| Shift+↑ | `\x1b[1;2A` |
| Alt+↑ | `\x1b[1;3A` |
| Shift+Tab | `\x1b[Z` |

### 2.4 功能键

| 按键 | 序列 |
|------|------|
| F1 | `\x1bOP` |
| F2 | `\x1bOQ` |
| F3 | `\x1bOR` |
| F4 | `\x1bOS` |
| F5 ~ F12 | `\x1b[15~` ~ `\x1b[24~` |

### 2.5 编辑键

| 按键 | 序列 |
|------|------|
| Home | `\x1b[1~` 或 `\x1b[H` |
| End | `\x1b[4~` 或 `\x1b[F` |
| PageUp | `\x1b[5~` |
| PageDown | `\x1b[6~` |
| Insert | `\x1b[2~` |
| Delete | `\x1b[3~` |

### 2.6 CTRL+字母快捷键

| 按键 | 序列 | 常见作用 |
|------|------|---------|
| Ctrl+A | `\x01` | 光标移到行首 |
| Ctrl+E | `\x05` | 光标移到行尾 |
| Ctrl+K | `\x0b` | 删除光标到行尾 |
| Ctrl+U | `\x15` | 删除整行 |
| Ctrl+W | `\x17` | 删除前一个单词 |
| Ctrl+N | `\x0e` | 下一行/历史 |
| Ctrl+P | `\x10` | 上一行/历史 |

### 2.7 封装为工具函数

```typescript
const Keys = {
  enter: '\r',
  tab: '\t',
  esc: '\x1b',
  up: '\x1b[A',
  down: '\x1b[B',
  left: '\x1b[D',
  right: '\x1b[C',
  ctrlC: '\x03',
  ctrlD: '\x04',
  backspace: '\x7f',
  home: '\x1b[H',
  end: '\x1b[F',
  delete: '\x1b[3~',
  shiftTab: '\x1b[Z',
  f1: '\x1bOP',
  f2: '\x1bOQ',
  f3: '\x1bOR',
} as const;

// 发送按键
term.write(Keys.up);       // 上箭头
term.write(Keys.enter);    // 回车
term.write(Keys.ctrlC);    // Ctrl+C

// 组合使用：按下箭头 3 次
term.write(Keys.down + Keys.down + Keys.down);

// 组合使用：选择列表第 3 项
term.write(Keys.down);     // 移到第二项
await sleep(100);
term.write(Keys.down);     // 移到第三项
await sleep(100);
term.write(Keys.enter);    // 确认
```

---

## 三、交互菜单操控

### 3.1 Tab 补全与选择

```typescript
// 场景：在 CLI 中输入目录名，按 Tab 触发补全
term.write('cd C:\\Users\\');
term.write(Keys.tab);

// 等待补全列表出现
await sleep(500);

// 读取输出，解析补全选项
const completions = readCurrentOutput();

// 如果有多个补全选项，用 Tab 或方向键选择
term.write(Keys.down);     // 选择下一个
term.write(Keys.enter);    // 确认
```

### 3.2 斜杠命令 (/ 命令)

/ 命令就是普通文本输入，无需特殊处理：

```typescript
// 发送 /resume 命令
term.write('/resume');
term.write(Keys.enter);

// 发送 /fork 命令
term.write('/fork experiment-1');
term.write(Keys.enter);

// 发送 /help 命令
term.write('/help');
term.write(Keys.enter);
```

### 3.3 菜单/列表选择器

```typescript
async function selectMenuItem(term: pty.IPty, index: number): Promise<void> {
  // 按下箭头 N 次移到目标项
  for (let i = 0; i < index; i++) {
    term.write(Keys.down);
    await sleep(80);  // TUI 渲染需要时间
  }
  // 按 Enter 确认
  term.write(Keys.enter);
}

// 用法：选择第 2 个 session
await selectMenuItem(term, 2);
```

### 3.4 输入文本并提交

```typescript
async function sendCommand(term: pty.IPty, command: string): Promise<void> {
  // 逐字符发送（模拟真实输入，某些 CLI 需要）
  for (const char of command) {
    term.write(char);
    await sleep(5);  // 模拟人类打字速度，部分 CLI 需要
  }
  term.write(Keys.enter);
}

// 或直接发送整行（大多数情况可行）
term.write('help\n');
```

---

## 四、ANSI 输出解析

### 4.1 常见 ANSI 序列及含义

| 序列 | 含义 |
|------|------|
| `\x1b[0m` | 重置所有样式 |
| `\x1b[1m` | 粗体 |
| `\x1b[3m` | 斜体 |
| `\x1b[4m` | 下划线 |
| `\x1b[31m` | 红色文字 |
| `\x1b[32m` | 绿色文字 |
| `\x1b[33m` | 黄色文字 |
| `\x1b[34m` | 蓝色文字 |
| `\x1b[90m` | 亮灰色（暗文本） |
| `\x1b[41m` | 红色背景 |
| `\x1b[2J` | 清屏 |
| `\x1b[H` | 光标移到 (1,1) |
| `\x1b[?25l` | 隐藏光标 |
| `\x1b[?25h` | 显示光标 |
| `\x1b[K` | 清除光标到行尾 |
| `\x1b[1;1H` | 光标移到 (row=1, col=1) |
| `\x1b[6n` | 请求光标位置（终端回复） |

### 4.2 剥离 ANSI 获取纯文本

```typescript
// 方案 A：使用 strip-ansi 库（推荐）
import stripAnsi from 'strip-ansi';
const clean = stripAnsi(rawOutput);

// 方案 B：手写正则（零依赖）
function stripAnsiRegex(text: string): string {
  return text
    .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')     // CSI 序列
    .replace(/\x1b\][0-9;]*[^\x07]*\x07/g, '')  // OSC 序列
    .replace(/\x1b[PX^_].*?\x1b\\/g, '');       // 其他序列
}
```

### 4.3 结构化解析 ANSI（保留位置信息）

```typescript
// 使用 node-ansiparser 做结构化解析
// npm install node-ansiparser
import { Parser, Terminal } from 'node-ansiparser';

const terminal = new Terminal({
  cols: 120,
  rows: 40,
});

const parser = new Parser(terminal);

term.onData((data: string) => {
  parser.parse(data);
});

// 获取屏幕内容（纯文本矩阵）
function getScreenContent(): string {
  const buffer = terminal.buffer;
  const lines: string[] = [];
  
  for (let row = 0; row < buffer.length; row++) {
    const line = buffer[row];
    let text = '';
    let lastAttr: any = null;
    
    for (let col = 0; col < line.length; col++) {
      const cell = line[col];
      text += cell[1] || ' ';
    }
    lines.push(text.replace(/\s+$/, ''));
  }
  
  return lines.join('\n').trim();
}
```

---

## 五、实战：操控 CodeBuddy Code

### 5.1 启动并控制

```typescript
async function controlCbc() {
  const term = pty.spawn('codebuddy', [], {
    name: 'xterm-color',
    cols: 120,
    rows: 40,
    cwd: 'e:/code/MyProject/CLIConductor',
    env: process.env as any,
  });

  // 等待 cbc 启动完成
  await waitForOutput(term, (text) => text.includes('>'));

  // 发送任务
  term.write('列出当前目录下的所有 .md 文件\n');

  // 等待 AI 回复完成（检测到新提示符）
  const response = await waitForOutput(term, (text) => {
    const clean = stripAnsi(text);
    return clean.split('>').length >= 2;  // 出现了新的提示符
  });

  console.log('AI 回复:', stripAnsi(response));

  // 用 /resume 打开会话列表
  term.write('/resume\n');
  await sleep(500);

  // 读取 /resume 菜单输出
  const menuOutput = readBuffer();

  // 选择第二个会话
  term.write(Keys.down);
  await sleep(100);
  term.write(Keys.enter);
}
```

### 5.2 多轮对话示例

```typescript
async function multiTurnConversation() {
  const term = pty.spawn('codebuddy', [], {
    name: 'xterm-color',
    cols: 120,
    rows: 40,
    cwd: 'e:/code/MyProject/CLIConductor',
    env: process.env as any,
  });

  const turns = [
    '帮我写一个 TypeScript 工具函数，读取 JSON 文件并解析',
    '给这个函数加上错误处理',
    '再添加一个文件锁防止并发读取',
  ];

  for (const prompt of turns) {
    console.log(`\n>>> 用户: ${prompt}`);
    
    term.write(prompt + '\n');
    
    const response = await waitForOutput(term, () => {
      // 检测 AI 完成回复（连续静默 2 秒或出现新提示符）
      ...
    });

    console.log(`\n<<< AI: ${stripAnsi(response)}\n`);
  }

  term.kill();
}
```

### 5.3 --bg 持久化 Session 操控

```typescript
async function persistentCbcSession() {
  // 用 --bg 启动，后台运行
  const term = pty.spawn('codebuddy', ['--bg', '--name', 'worker1'], {
    name: 'xterm-color',
    cols: 120,
    rows: 40,
    cwd: 'e:/code/MyProject/CLIConductor',
    env: process.env as any,
  });

  // 第一轮对话
  term.write('分析 agent-cluster-architecture.md 的核心设计\n');
  const result1 = await waitForAiResponse(term);
  console.log('第1轮:', stripAnsi(result1));

  // 第二轮对话（同一 session，上下文保留）
  term.write('在这个架构中，Gateway 模块应该怎么设计？\n');
  const result2 = await waitForAiResponse(term);
  console.log('第2轮:', stripAnsi(result2));

  // 第三轮
  term.write('请用 TypeScript 写出 Gateway 的接口定义\n');
  const result3 = await waitForAiResponse(term);
  console.log('第3轮:', stripAnsi(result3));

  // 退出
  term.write('/exit\n');
  await sleep(500);
  term.kill();
}
```

### 5.4 Fork/Resume 操控

```typescript
async function forkAndResume() {
  const term = pty.spawn('codebuddy', [], { /* ... */ });

  // 第一个任务
  term.write('实现方案A\n');
  await waitForAiResponse(term);

  // Fork 新 session 尝试方案 B
  term.write('/fork plan-b\n');
  await sleep(500);

  term.write('实现方案B，与方案A不同\n');
  await waitForAiResponse(term);

  // 回到原 session
  term.write('/resume\n');
  await sleep(500);

  // 选择原 session（假设它是第1项）
  // TUI 菜单出现后，不需要按方向键，直接回车选第一个
  term.write(Keys.enter);
  await sleep(500);

  term.write('继续方案A的工作\n');
}
```

---

## 六、关键技术坑点

### 6.1 延时同步

```typescript
// ❌ 错误：发送命令后立即读输出
term.write('ls\n');
const output = readBuffer();  // 可能还没输出完

// ✅ 正确：等待输出稳定
term.write('ls\n');
await sleep(300);
const output = readBuffer();
```

### 6.2 TUI 渲染延迟

```typescript
// ❌ 错误：快速连续按方向键
term.write('/resume\n');
term.write(Keys.down);     // TUI 还没渲染完！
term.write(Keys.enter);

// ✅ 正确：每步留足渲染时间
term.write('/resume\n');
await sleep(500);           // 等 /resume 菜单渲染
term.write(Keys.down);
await sleep(100);           // 等选择高亮移动
term.write(Keys.enter);
```

### 6.3 输出何时结束的判定

```typescript
// 方案 A：检测提示符（最可靠）
function isPromptReady(text: string): boolean {
  const clean = stripAnsi(text);
  return /[>#$%]\s*$/.test(clean.trimEnd());
}

// 方案 B：空闲超时检测
let lastOutput = Date.now();
const IDLE_TIMEOUT = 2000;  // 2秒内无输出判定结束

term.onData(() => { lastOutput = Date.now(); });

async function waitForIdle(): Promise<void> {
  while (Date.now() - lastOutput < IDLE_TIMEOUT) {
    await sleep(200);
  }
}

// 方案 C：等待特定标记（最精确）
async function waitForMarker(text: string, marker: string): Promise<string> {
  return new Promise((resolve) => {
    let buf = '';
    const handler = (data: string) => {
      buf += data;
      if (buf.includes(marker)) {
        term.removeListener('data', handler);
        resolve(buf);
      }
    };
    term.onData(handler);
  });
}
```

### 6.4 Windows 特有坑

- ConPTY 在某些 CLI 下行为异常（如颜色丢失）
- 文件路径分隔符：发送 `\` 而非 `/`
- PowerShell vs cmd vs Git Bash：PTY 兼容性不同
- node-pty Windows 底层用 winpty（非 ConPTY API）

---

## 七、工具库对比

| 库 | 平台 | 用途 | 推荐度 |
|----|------|------|--------|
| **node-pty** | Win/Mac/Linux | PTY 操控核心 | ⭐⭐⭐ 首选 |
| **strip-ansi** | 通用 | 剥离 ANSI 序列 | ⭐⭐⭐ 必备 |
| **node-ansiparser** | 通用 | 结构化解析 ANSI | ⭐⭐ 需要位置信息时 |
| **tmux** | Mac/Linux为主 | session 管理 + 操控 | ⭐⭐ detach/reattach 场景 |
| **pexpect** (Python) | Mac/Linux | 自动化交互 | ⭐ 备选技术栈 |

---

## 八、任务完成判定标准

- [ ] PTY 能启动一个 codebuddy 进程并捕获全部输出
- [ ] PTY 能向 codebuddy 发送文本任务并读取 AI 回复
- [ ] PTY 能发送 Tab、方向键、Ctrl+C 等特殊按键
- [ ] PTY 能操控 /resume 菜单，选择并切换到指定 session
- [ ] PTY 能执行 /fork 创建分支 session
- [ ] 能实现至少 3 轮的多轮对话
- [ ] 输出能正确剥离 ANSI 序列，提取纯文本
- [ ] 能判定 AI 回复何时结束
