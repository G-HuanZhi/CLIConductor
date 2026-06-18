# PTY 鎿嶆帶 CLI 瀹屾暣鎸囧崡

> 閫氳繃 PTY 瀹炵幇瀵逛换鎰?CLI 鐨勫叏杈撳嚭鎹曡幏 + 闈為敭鐩樿緭鍏ユ帶鍒讹紙Tab 閫夋嫨銆佺澶撮敭銆? 鍛戒护绛夛級銆?
---

## 涓€銆佸畬鏁磋緭鍑烘崟鑾?
### 1.1 node-pty 鍩烘湰浣跨敤

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

### 1.2 鎹曡幏鎵€鏈夎緭鍑猴紙鍚?ANSI 搴忓垪锛?
```typescript
// onData 浼氭敹鍒版墍鏈夎緭鍑猴紝鍖呮嫭棰滆壊鐮併€佸厜鏍囩Щ鍔ㄣ€佹竻灞忕瓑鎺у埗搴忓垪
let rawBuffer = '';

term.onData((data: string) => {
  rawBuffer += data;
  console.log('鍘熷杈撳嚭:', JSON.stringify(data));
  // 杈撳嚭绀轰緥锛?  // "\x1b[32mHello\x1b[0m\n"     鈫?缁胯壊 "Hello"
  // "\x1b[?25l"                   鈫?闅愯棌鍏夋爣
  // "\x1b[2J\x1b[H"               鈫?娓呭睆骞剁Щ鍒板乏涓婅
  // "\x1b[1;1H\x1b[K"             鈫?绉诲埌绗?琛岀1鍒楋紝娓呴櫎璇ヨ
});
```

### 1.3 杈撳嚭缂撳啿绠＄悊

PTY 杈撳嚭鏄祦寮忕殑锛屼笉鏄畬鏁村抚銆傞渶瑕佽嚜寤虹紦鍐插尯锛?
```typescript
class PtyOutputBuffer {
  private buffer = '';
  private readonly frameTimeout = 200; // ms锛屽垽瀹氫竴甯х粨鏉熺殑绌洪棽鏃堕棿
  private frameTimer: NodeJS.Timeout | null = null;
  private lastFlush = 0;

  feed(data: string, onFrame: (text: string, raw: string) => void) {
    this.buffer += data;
    this.lastFlush = Date.now();

    // 寤惰繜鍒ゅ畾锛氱┖闂?N ms 鍚庤涓轰竴甯х粨鏉?    if (this.frameTimer) clearTimeout(this.frameTimer);
    this.frameTimer = setTimeout(() => {
      const raw = this.buffer;
      const clean = this.stripAnsi(raw);
      onFrame(clean, raw);
      this.buffer = '';
    }, this.frameTimeout);
  }

  stripAnsi(text: string): string {
    // 绠€鍗曠増 ANSI 鍓ョ锛堢敓浜х幆澧冪敤 strip-ansi 搴擄級
    return text.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')
               .replace(/\x1b\][0-9;]*[^\x07]*\x07/g, '')
               .replace(/\x1b\][0-9;]*\x1b\\/g, '')
               .replace(/\x1b[PX^_].*?\x1b\\/g, '');
  }
}
```

### 1.4 鍚屾璇诲彇锛堢瓑寰呯壒瀹氳緭鍑猴級

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
      reject(new Error(`绛夊緟杈撳嚭瓒呮椂 (${timeoutMs}ms)`));
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

// 鐢ㄦ硶锛氱瓑寰?CLI 鍑虹幇鎻愮ず绗?await waitForOutput(term, (text) => text.includes('>'));
```

---

## 浜屻€侀潪閿洏杈撳叆锛欰NSI 杞箟搴忓垪鍏ㄩ泦

PTY 鐨?`write()` 鍙互鐩存帴鍙戦€?ANSI 杞箟搴忓垪妯℃嫙鎵€鏈夌壒娈婃寜閿紝**瀹屽叏涓嶉渶瑕佺墿鐞嗛敭鐩?*銆?
### 2.1 鎺у埗瀛楃

| 鎸夐敭 | 搴忓垪 | 璇存槑 |
|------|------|------|
| Enter | `\r` 鎴?`\n` | 瀵逛簬浜や簰寮?CLI锛宍\r` 鏇村彲闈?|
| Tab | `\t` | 瑙﹀彂琛ュ叏 |
| Backspace | `\x7f` 鎴?`\b` | 鍒犻櫎鍓嶄竴涓瓧绗?|
| Escape | `\x1b` | 閫€鍑哄綋鍓嶆ā寮?|
| Ctrl+C | `\x03` | 涓柇绋嬪簭 |
| Ctrl+D | `\x04` | EOF |
| Ctrl+Z | `\x1a` | 鎸傝捣杩涚▼ (Windows) |
| Ctrl+L | `\x0c` | 娓呭睆 |

### 2.2 鏂瑰悜閿?
| 鎸夐敭 | 搴忓垪 |
|------|------|
| 涓婄澶?鈫?| `\x1b[A` |
| 涓嬬澶?鈫?| `\x1b[B` |
| 鍙崇澶?鈫?| `\x1b[C` |
| 宸︾澶?鈫?| `\x1b[D` |

### 2.3 缁勫悎鏂瑰悜閿?
| 鎸夐敭 | 搴忓垪 |
|------|------|
| Ctrl+鈫?| `\x1b[1;5A` |
| Ctrl+鈫?| `\x1b[1;5B` |
| Shift+鈫?| `\x1b[1;2A` |
| Alt+鈫?| `\x1b[1;3A` |
| Shift+Tab | `\x1b[Z` |

### 2.4 鍔熻兘閿?
| 鎸夐敭 | 搴忓垪 |
|------|------|
| F1 | `\x1bOP` |
| F2 | `\x1bOQ` |
| F3 | `\x1bOR` |
| F4 | `\x1bOS` |
| F5 ~ F12 | `\x1b[15~` ~ `\x1b[24~` |

### 2.5 缂栬緫閿?
| 鎸夐敭 | 搴忓垪 |
|------|------|
| Home | `\x1b[1~` 鎴?`\x1b[H` |
| End | `\x1b[4~` 鎴?`\x1b[F` |
| PageUp | `\x1b[5~` |
| PageDown | `\x1b[6~` |
| Insert | `\x1b[2~` |
| Delete | `\x1b[3~` |

### 2.6 CTRL+瀛楁瘝蹇嵎閿?
| 鎸夐敭 | 搴忓垪 | 甯歌浣滅敤 |
|------|------|---------|
| Ctrl+A | `\x01` | 鍏夋爣绉诲埌琛岄 |
| Ctrl+E | `\x05` | 鍏夋爣绉诲埌琛屽熬 |
| Ctrl+K | `\x0b` | 鍒犻櫎鍏夋爣鍒拌灏?|
| Ctrl+U | `\x15` | 鍒犻櫎鏁磋 |
| Ctrl+W | `\x17` | 鍒犻櫎鍓嶄竴涓崟璇?|
| Ctrl+N | `\x0e` | 涓嬩竴琛?鍘嗗彶 |
| Ctrl+P | `\x10` | 涓婁竴琛?鍘嗗彶 |

### 2.7 灏佽涓哄伐鍏峰嚱鏁?
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

// 鍙戦€佹寜閿?term.write(Keys.up);       // 涓婄澶?term.write(Keys.enter);    // 鍥炶溅
term.write(Keys.ctrlC);    // Ctrl+C

// 缁勫悎浣跨敤锛氭寜涓嬬澶?3 娆?term.write(Keys.down + Keys.down + Keys.down);

// 缁勫悎浣跨敤锛氶€夋嫨鍒楄〃绗?3 椤?term.write(Keys.down);     // 绉诲埌绗簩椤?await sleep(100);
term.write(Keys.down);     // 绉诲埌绗笁椤?await sleep(100);
term.write(Keys.enter);    // 纭
```

---

## 涓夈€佷氦浜掕彍鍗曟搷鎺?
### 3.1 Tab 琛ュ叏涓庨€夋嫨

```typescript
// 鍦烘櫙锛氬湪 CLI 涓緭鍏ョ洰褰曞悕锛屾寜 Tab 瑙﹀彂琛ュ叏
term.write('cd C:\\Users\\');
term.write(Keys.tab);

// 绛夊緟琛ュ叏鍒楄〃鍑虹幇
await sleep(500);

// 璇诲彇杈撳嚭锛岃В鏋愯ˉ鍏ㄩ€夐」
const completions = readCurrentOutput();

// 濡傛灉鏈夊涓ˉ鍏ㄩ€夐」锛岀敤 Tab 鎴栨柟鍚戦敭閫夋嫨
term.write(Keys.down);     // 閫夋嫨涓嬩竴涓?term.write(Keys.enter);    // 纭
```

### 3.2 鏂滄潬鍛戒护 (/ 鍛戒护)

/ 鍛戒护灏辨槸鏅€氭枃鏈緭鍏ワ紝鏃犻渶鐗规畩澶勭悊锛?
```typescript
// 鍙戦€?/resume 鍛戒护
term.write('/resume');
term.write(Keys.enter);

// 鍙戦€?/fork 鍛戒护
term.write('/fork experiment-1');
term.write(Keys.enter);

// 鍙戦€?/help 鍛戒护
term.write('/help');
term.write(Keys.enter);
```

### 3.3 鑿滃崟/鍒楄〃閫夋嫨鍣?
```typescript
async function selectMenuItem(term: pty.IPty, index: number): Promise<void> {
  // 鎸変笅绠ご N 娆＄Щ鍒扮洰鏍囬」
  for (let i = 0; i < index; i++) {
    term.write(Keys.down);
    await sleep(80);  // TUI 娓叉煋闇€瑕佹椂闂?  }
  // 鎸?Enter 纭
  term.write(Keys.enter);
}

// 鐢ㄦ硶锛氶€夋嫨绗?2 涓?session
await selectMenuItem(term, 2);
```

### 3.4 杈撳叆鏂囨湰骞舵彁浜?
```typescript
async function sendCommand(term: pty.IPty, command: string): Promise<void> {
  // 閫愬瓧绗﹀彂閫侊紙妯℃嫙鐪熷疄杈撳叆锛屾煇浜?CLI 闇€瑕侊級
  for (const char of command) {
    term.write(char);
    await sleep(5);  // 妯℃嫙浜虹被鎵撳瓧閫熷害锛岄儴鍒?CLI 闇€瑕?  }
  term.write(Keys.enter);
}

// 鎴栫洿鎺ュ彂閫佹暣琛岋紙澶у鏁版儏鍐靛彲琛岋級
term.write('help\n');
```

---

## 鍥涖€丄NSI 杈撳嚭瑙ｆ瀽

### 4.1 甯歌 ANSI 搴忓垪鍙婂惈涔?
| 搴忓垪 | 鍚箟 |
|------|------|
| `\x1b[0m` | 閲嶇疆鎵€鏈夋牱寮?|
| `\x1b[1m` | 绮椾綋 |
| `\x1b[3m` | 鏂滀綋 |
| `\x1b[4m` | 涓嬪垝绾?|
| `\x1b[31m` | 绾㈣壊鏂囧瓧 |
| `\x1b[32m` | 缁胯壊鏂囧瓧 |
| `\x1b[33m` | 榛勮壊鏂囧瓧 |
| `\x1b[34m` | 钃濊壊鏂囧瓧 |
| `\x1b[90m` | 浜伆鑹诧紙鏆楁枃鏈級 |
| `\x1b[41m` | 绾㈣壊鑳屾櫙 |
| `\x1b[2J` | 娓呭睆 |
| `\x1b[H` | 鍏夋爣绉诲埌 (1,1) |
| `\x1b[?25l` | 闅愯棌鍏夋爣 |
| `\x1b[?25h` | 鏄剧ず鍏夋爣 |
| `\x1b[K` | 娓呴櫎鍏夋爣鍒拌灏?|
| `\x1b[1;1H` | 鍏夋爣绉诲埌 (row=1, col=1) |
| `\x1b[6n` | 璇锋眰鍏夋爣浣嶇疆锛堢粓绔洖澶嶏級 |

### 4.2 鍓ョ ANSI 鑾峰彇绾枃鏈?
```typescript
// 鏂规 A锛氫娇鐢?strip-ansi 搴擄紙鎺ㄨ崘锛?import stripAnsi from 'strip-ansi';
const clean = stripAnsi(rawOutput);

// 鏂规 B锛氭墜鍐欐鍒欙紙闆朵緷璧栵級
function stripAnsiRegex(text: string): string {
  return text
    .replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '')     // CSI 搴忓垪
    .replace(/\x1b\][0-9;]*[^\x07]*\x07/g, '')  // OSC 搴忓垪
    .replace(/\x1b[PX^_].*?\x1b\\/g, '');       // 鍏朵粬搴忓垪
}
```

### 4.3 缁撴瀯鍖栬В鏋?ANSI锛堜繚鐣欎綅缃俊鎭級

```typescript
// 浣跨敤 node-ansiparser 鍋氱粨鏋勫寲瑙ｆ瀽
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

// 鑾峰彇灞忓箷鍐呭锛堢函鏂囨湰鐭╅樀锛?function getScreenContent(): string {
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

## 浜斻€佸疄鎴橈細鎿嶆帶 CodeBuddy Code

### 5.1 鍚姩骞舵帶鍒?
```typescript
async function controlCbc() {
  const term = pty.spawn('codebuddy', [], {
    name: 'xterm-color',
    cols: 120,
    rows: 40,
    cwd: 'e:/code/MyProject/CLIConductor',
    env: process.env as any,
  });

  // 绛夊緟 cbc 鍚姩瀹屾垚
  await waitForOutput(term, (text) => text.includes('>'));

  // 鍙戦€佷换鍔?  term.write('鍒楀嚭褰撳墠鐩綍涓嬬殑鎵€鏈?.md 鏂囦欢\n');

  // 绛夊緟 AI 鍥炲瀹屾垚锛堟娴嬪埌鏂版彁绀虹锛?  const response = await waitForOutput(term, (text) => {
    const clean = stripAnsi(text);
    return clean.split('>').length >= 2;  // 鍑虹幇浜嗘柊鐨勬彁绀虹
  });

  console.log('AI 鍥炲:', stripAnsi(response));

  // 鐢?/resume 鎵撳紑浼氳瘽鍒楄〃
  term.write('/resume\n');
  await sleep(500);

  // 璇诲彇 /resume 鑿滃崟杈撳嚭
  const menuOutput = readBuffer();

  // 閫夋嫨绗簩涓細璇?  term.write(Keys.down);
  await sleep(100);
  term.write(Keys.enter);
}
```

### 5.2 澶氳疆瀵硅瘽绀轰緥

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
    '甯垜鍐欎竴涓?TypeScript 宸ュ叿鍑芥暟锛岃鍙?JSON 鏂囦欢骞惰В鏋?,
    '缁欒繖涓嚱鏁板姞涓婇敊璇鐞?,
    '鍐嶆坊鍔犱竴涓枃浠堕攣闃叉骞跺彂璇诲彇',
  ];

  for (const prompt of turns) {
    console.log(`\n>>> 鐢ㄦ埛: ${prompt}`);
    
    term.write(prompt + '\n');
    
    const response = await waitForOutput(term, () => {
      // 妫€娴?AI 瀹屾垚鍥炲锛堣繛缁潤榛?2 绉掓垨鍑虹幇鏂版彁绀虹锛?      ...
    });

    console.log(`\n<<< AI: ${stripAnsi(response)}\n`);
  }

  term.kill();
}
```

### 5.3 --bg 鎸佷箙鍖?Session 鎿嶆帶

```typescript
async function persistentCbcSession() {
  // 鐢?--bg 鍚姩锛屽悗鍙拌繍琛?  const term = pty.spawn('codebuddy', ['--bg', '--name', 'worker1'], {
    name: 'xterm-color',
    cols: 120,
    rows: 40,
    cwd: 'e:/code/MyProject/CLIConductor',
    env: process.env as any,
  });

  // 绗竴杞璇?  term.write('鍒嗘瀽 agent-cluster-architecture.md 鐨勬牳蹇冭璁n');
  const result1 = await waitForAiResponse(term);
  console.log('绗?杞?', stripAnsi(result1));

  // 绗簩杞璇濓紙鍚屼竴 session锛屼笂涓嬫枃淇濈暀锛?  term.write('鍦ㄨ繖涓灦鏋勪腑锛孏ateway 妯″潡搴旇鎬庝箞璁捐锛焅n');
  const result2 = await waitForAiResponse(term);
  console.log('绗?杞?', stripAnsi(result2));

  // 绗笁杞?  term.write('璇风敤 TypeScript 鍐欏嚭 Gateway 鐨勬帴鍙ｅ畾涔塡n');
  const result3 = await waitForAiResponse(term);
  console.log('绗?杞?', stripAnsi(result3));

  // 閫€鍑?  term.write('/exit\n');
  await sleep(500);
  term.kill();
}
```

### 5.4 Fork/Resume 鎿嶆帶

```typescript
async function forkAndResume() {
  const term = pty.spawn('codebuddy', [], { /* ... */ });

  // 绗竴涓换鍔?  term.write('瀹炵幇鏂规A\n');
  await waitForAiResponse(term);

  // Fork 鏂?session 灏濊瘯鏂规 B
  term.write('/fork plan-b\n');
  await sleep(500);

  term.write('瀹炵幇鏂规B锛屼笌鏂规A涓嶅悓\n');
  await waitForAiResponse(term);

  // 鍥炲埌鍘?session
  term.write('/resume\n');
  await sleep(500);

  // 閫夋嫨鍘?session锛堝亣璁惧畠鏄1椤癸級
  // TUI 鑿滃崟鍑虹幇鍚庯紝涓嶉渶瑕佹寜鏂瑰悜閿紝鐩存帴鍥炶溅閫夌涓€涓?  term.write(Keys.enter);
  await sleep(500);

  term.write('缁х画鏂规A鐨勫伐浣淺n');
}
```

---

## 鍏€佸叧閿妧鏈潙鐐?
### 6.1 寤舵椂鍚屾

```typescript
// 鉂?閿欒锛氬彂閫佸懡浠ゅ悗绔嬪嵆璇昏緭鍑?term.write('ls\n');
const output = readBuffer();  // 鍙兘杩樻病杈撳嚭瀹?
// 鉁?姝ｇ‘锛氱瓑寰呰緭鍑虹ǔ瀹?term.write('ls\n');
await sleep(300);
const output = readBuffer();
```

### 6.2 TUI 娓叉煋寤惰繜

```typescript
// 鉂?閿欒锛氬揩閫熻繛缁寜鏂瑰悜閿?term.write('/resume\n');
term.write(Keys.down);     // TUI 杩樻病娓叉煋瀹岋紒
term.write(Keys.enter);

// 鉁?姝ｇ‘锛氭瘡姝ョ暀瓒虫覆鏌撴椂闂?term.write('/resume\n');
await sleep(500);           // 绛?/resume 鑿滃崟娓叉煋
term.write(Keys.down);
await sleep(100);           // 绛夐€夋嫨楂樹寒绉诲姩
term.write(Keys.enter);
```

### 6.3 杈撳嚭浣曟椂缁撴潫鐨勫垽瀹?
```typescript
// 鏂规 A锛氭娴嬫彁绀虹锛堟渶鍙潬锛?function isPromptReady(text: string): boolean {
  const clean = stripAnsi(text);
  return /[>#$%]\s*$/.test(clean.trimEnd());
}

// 鏂规 B锛氱┖闂茶秴鏃舵娴?let lastOutput = Date.now();
const IDLE_TIMEOUT = 2000;  // 2绉掑唴鏃犺緭鍑哄垽瀹氱粨鏉?
term.onData(() => { lastOutput = Date.now(); });

async function waitForIdle(): Promise<void> {
  while (Date.now() - lastOutput < IDLE_TIMEOUT) {
    await sleep(200);
  }
}

// 鏂规 C锛氱瓑寰呯壒瀹氭爣璁帮紙鏈€绮剧‘锛?async function waitForMarker(text: string, marker: string): Promise<string> {
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

### 6.4 Windows 鐗规湁鍧?
- ConPTY 鍦ㄦ煇浜?CLI 涓嬭涓哄紓甯革紙濡傞鑹蹭涪澶憋級
- 鏂囦欢璺緞鍒嗛殧绗︼細鍙戦€?`\` 鑰岄潪 `/`
- PowerShell vs cmd vs Git Bash锛歅TY 鍏煎鎬т笉鍚?- node-pty Windows 搴曞眰鐢?winpty锛堥潪 ConPTY API锛?
---

## 涓冦€佸伐鍏峰簱瀵规瘮

| 搴?| 骞冲彴 | 鐢ㄩ€?| 鎺ㄨ崘搴?|
|----|------|------|--------|
| **node-pty** | Win/Mac/Linux | PTY 鎿嶆帶鏍稿績 | 猸愨瓙猸?棣栭€?|
| **strip-ansi** | 閫氱敤 | 鍓ョ ANSI 搴忓垪 | 猸愨瓙猸?蹇呭 |
| **node-ansiparser** | 閫氱敤 | 缁撴瀯鍖栬В鏋?ANSI | 猸愨瓙 闇€瑕佷綅缃俊鎭椂 |
| **tmux** | Mac/Linux涓轰富 | session 绠＄悊 + 鎿嶆帶 | 猸愨瓙 detach/reattach 鍦烘櫙 |
| **pexpect** (Python) | Mac/Linux | 鑷姩鍖栦氦浜?| 猸?澶囬€夋妧鏈爤 |

---

## 鍏€佷换鍔″畬鎴愬垽瀹氭爣鍑?
- [ ] PTY 鑳藉惎鍔ㄤ竴涓?codebuddy 杩涚▼骞舵崟鑾峰叏閮ㄨ緭鍑?- [ ] PTY 鑳藉悜 codebuddy 鍙戦€佹枃鏈换鍔″苟璇诲彇 AI 鍥炲
- [ ] PTY 鑳藉彂閫?Tab銆佹柟鍚戦敭銆丆trl+C 绛夌壒娈婃寜閿?- [ ] PTY 鑳芥搷鎺?/resume 鑿滃崟锛岄€夋嫨骞跺垏鎹㈠埌鎸囧畾 session
- [ ] PTY 鑳芥墽琛?/fork 鍒涘缓鍒嗘敮 session
- [ ] 鑳藉疄鐜拌嚦灏?3 杞殑澶氳疆瀵硅瘽
- [ ] 杈撳嚭鑳芥纭墺绂?ANSI 搴忓垪锛屾彁鍙栫函鏂囨湰
- [ ] 鑳藉垽瀹?AI 鍥炲浣曟椂缁撴潫

