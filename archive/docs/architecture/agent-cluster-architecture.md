# Agent 闆嗙兢鏋舵瀯鏂规

> 鐩爣锛氶€氳繃涓€涓富 Agent 鎿嶆帶绠＄悊澶氫釜**绗笁鏂?* CLI/IDE 瀛?Agent锛屽疄鐜拌法鍘傚晢 Agent 闆嗙兢銆?> 鍘熷垯锛氭ā鍧楀寲銆佽法鍘傚晢閫氱敤銆乻ession 鍙拷韪€丱S 鍘熻浼樺厛銆?
---

## 涓€銆佹€讳綋鏋舵瀯

```
                         鐢ㄦ埛
                          鈹?          鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹€鈹€鈹€鈹尖攢鈹€鈹€鈹€鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹€鈹€鈹€鈹?          鈹?      鈹?      鈹?      鈹?      鈹?       鈹屸攢鈹€鈻尖攢鈹€鈹?鈹屸攢鈹€鈻尖攢鈹€鈹?鈹屸攢鈹€鈻尖攢鈹€鈹?鈹屸攢鈹€鈻尖攢鈹€鈹?鈹屸攢鈹€鈻尖攢鈹€鈹?       鈹?QQ  鈹?鈹傚井淇?鈹?鈹俉eb  鈹?鈹傞偖浠?鈹?鈹侰LI  鈹? 鈫?鍏ュ彛灞?       鈹斺攢鈹€鈹攢鈹€鈹?鈹斺攢鈹€鈹攢鈹€鈹?鈹斺攢鈹€鈹攢鈹€鈹?鈹斺攢鈹€鈹攢鈹€鈹?鈹斺攢鈹€鈹攢鈹€鈹?          鈹?      鈹?      鈹?      鈹?      鈹?          鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹粹攢鈹€鈹€鈹€鈹€鈹€鈹€鈹尖攢鈹€鈹€鈹€鈹€鈹€鈹€鈹粹攢鈹€鈹€鈹€鈹€鈹€鈹€鈹?                          鈹?                    鈹屸攢鈹€鈹€鈹€鈹€鈻尖攢鈹€鈹€鈹€鈹€鈹?                    鈹? 娑堟伅缃戝叧   鈹? 鈫?缁熶竴娑堟伅鏍煎紡 + 璁よ瘉
                    鈹斺攢鈹€鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹€鈹?                          鈹?                    鈹屸攢鈹€鈹€鈹€鈹€鈻尖攢鈹€鈹€鈹€鈹€鈹?                    鈹? 涓?Agent  鈹? 鈫?鎰忓浘鍒嗘瀽 + 浠诲姟鎷嗗垎 + 缁撴灉姹囨€?                    鈹斺攢鈹€鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹€鈹?                          鈹?                    鈹屸攢鈹€鈹€鈹€鈹€鈻尖攢鈹€鈹€鈹€鈹€鈹?                    鈹? 璋冨害鍣?    鈹? 鈫?浠诲姟鍒嗛厤 + 骞跺彂鎺у埗
                    鈹斺攢鈹€鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹€鈹?                          鈹?          鈹屸攢鈹€鈹€鈹€鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹€鈹€鈹€鈹尖攢鈹€鈹€鈹€鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹€鈹€鈹€鈹?          鈹?      鈹?      鈹?      鈹?      鈹?     鈹屸攢鈹€鈹€鈹€鈻尖攢鈹€鈹愨攲鈹€鈹€鈹€鈻尖攢鈹€鈹€鈹愨攲鈹€鈹€鈻尖攢鈹€鈹€鈹€鈹愨攲鈹€鈹€鈻尖攢鈹€鈹€鈹€鈹?     鈹侰BC    鈹傗攤Claude 鈹傗攤Copilot鈹傗攤Aider  鈹? 鈫?閫傞厤鍣ㄥ眰锛堟瘡绉?CLI 涓€濂楋級
     鈹侫dapter鈹傗攤Adapter鈹傗攤Adapter鈹傗攤Adapter鈹?     鈹斺攢鈹€鈹€鈹€鈹攢鈹€鈹樷敂鈹€鈹€鈹€鈹攢鈹€鈹€鈹樷敂鈹€鈹€鈹攢鈹€鈹€鈹€鈹樷敂鈹€鈹€鈹攢鈹€鈹€鈹€鈹?          鈹?      鈹?      鈹?      鈹?          鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹粹攢鈹€鈹€鈹€鈹€鈹€鈹€鈹粹攢鈹€鈹€鈹€鈹€鈹€鈹€鈹?                          鈹?                    鈹屸攢鈹€鈹€鈹€鈹€鈻尖攢鈹€鈹€鈹€鈹€鈹?                    鈹?Session    鈹? 鈫?缁熶竴 session 绠＄悊
                    鈹?Manager    鈹?    sessions.json + PID 杩借釜
                    鈹斺攢鈹€鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹€鈹?                          鈹?                    鈹屸攢鈹€鈹€鈹€鈹€鈻尖攢鈹€鈹€鈹€鈹€鈹?                    鈹?杩涚▼绠＄悊灞? 鈹? 鈫?child_process.spawn + PID/kill -0
                    鈹?(OS 鍘熻)  鈹?    澶囬€夛細node-pty (bash wrapper)
                    鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?```

### 鏍稿績宸紓鍖栬兘鍔?
鏈郴缁熺殑鍏抽敭宸紓鍦ㄤ簬**瀵圭涓夋柟闂簮 CLI 鐨勬帶鍒舵繁搴?*锛?
| 鎺у埗娣卞害 | 鏈郴缁?| 鍏朵粬妗嗘灦锛堝 OpenClaw锛?|
|---------|--------|----------------------|
| 鍚姩绗笁鏂?CLI | 鉁?`child_process.spawn` | 鉁?`claude -p`锛堝崟娆℃墽琛岋級 |
| 鑾峰彇杈撳嚭 | 鉁?瑙ｆ瀽 stream-json | 鉁?鎹曡幏 stdout |
| 澶氳疆瀵硅瘽 | 鉁?`--resume <session_id>` | 鉂?姣忔鏂拌繘绋?|
| 杩涚▼鐢熷懡鍛ㄦ湡绠＄悊 | 鉁?PID 杩借釜 + kill -0 + kill | 鉂?|
| Session 褰掓。閲嶅缓 | 鉁?鍏冩暟鎹?+ 瀵硅瘽鍘嗗彶鍙屽瓨 | 鉂?|
| 璺?CLI 缁熶竴绠＄悊 | 鉁?閫傞厤鍣ㄦā寮?+ `AgentAdapter` 鎺ュ彛 | 鉂?|
| 鎿嶆帶浜や簰寮?CLI (鏃?-p) | 鉁?PTY 澶囬€夋柟妗?| 鉂?|

---

## 浜屻€佸悇灞傝缁嗚璁?
### 2.1 鍏ュ彛灞傦紙Input Layer锛?
鏀寔浠绘剰娓犻亾涓庝富 Agent 瀵硅瘽锛屾墍鏈夋笭閬撳叡浜悓涓€浠藉璇濅笂涓嬫枃銆?
```
缁熶竴娑堟伅鏍煎紡锛?{
  "id": "uuid",
  "userId": "user_001",
  "channel": "qq|wechat|web|email|cli",
  "content": "甯垜閲嶆瀯 auth 妯″潡",
  "timestamp": "2026-06-10T10:00:00Z",
  "replyTo": "msg_id",
  "attachments": [...],
  "context": { ... }
}
```

| 娓犻亾 | 瀹炵幇鏂瑰紡 | 浼樺厛绾?|
|------|---------|--------|
| CLI 鐩存帴 | stdin/stdout | P0 |
| Web 椤甸潰 | 鏈湴 HTTP + WebSocket | P1 |
| QQ | QQ Bot SDK | P2 |
| 閭 | IMAP 杞 + SMTP 鍥炲 | P3 |

---

### 2.2 娑堟伅缃戝叧锛圡essage Gateway锛?
- 鎺ユ敹鍚勬笭閬撴秷鎭紝杞崲涓虹粺涓€鏍煎紡
- 璁よ瘉/閴存潈锛堥槻姝㈠埆浜烘搷鎺т綘鐨?Agent锛?- 娑堟伅鎺掗槦銆佸幓閲嶃€侀檺娴?- 绗竴闃舵锛氭枃浠堕槦鍒楋紙`tasks/` 鐩綍涓?JSON 鏂囦欢锛?- 绗簩闃舵锛歊edis 鎴?SQLite 闃熷垪

---

### 2.3 涓?Agent锛圔rain锛?
涓?Agent 鏄暣涓郴缁熺殑澶ц剳锛?
```
鐢ㄦ埛娑堟伅锛?甯垜鎵惧嚭椤圭洰閲屾墍鏈夋湭浣跨敤鐨?import锛屽垹鎺夊畠浠?
         鈹?    鈹屸攢鈹€鈹€鈹€鈻尖攢鈹€鈹€鈹€鈹€鈹?    鈹?鎰忓浘鍒嗘瀽   鈹?鈫?浠诲姟绫诲瀷锛氫唬鐮佹鏌ュ拰娓呯悊
    鈹斺攢鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹€鈹?    鈹屸攢鈹€鈹€鈹€鈻尖攢鈹€鈹€鈹€鈹€鈹?    鈹?浠诲姟鎷嗗垎   鈹?鈫?瀛愪换鍔?锛氭壂鎻忔湭浣跨敤 import
    鈹?          鈹?   瀛愪换鍔?锛氶€愪釜鍒犻櫎骞堕獙璇?    鈹?          鈹?   瀛愪换鍔?锛氳繍琛屾祴璇?    鈹斺攢鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹€鈹?    鈹屸攢鈹€鈹€鈹€鈻尖攢鈹€鈹€鈹€鈹€鈹?    鈹?骞惰鍒嗗彂   鈹?鈫?瀛愪换鍔? 鈫?CBC Adapter
    鈹?          鈹?   瀛愪换鍔? 鈫?Shell Adapter
    鈹斺攢鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹€鈹?    鈹屸攢鈹€鈹€鈹€鈻尖攢鈹€鈹€鈹€鈹€鈹?    鈹?鐩戞帶杩涘害   鈹?鈫?pending / running / done / failed
    鈹斺攢鈹€鈹€鈹€鈹攢鈹€鈹€鈹€鈹€鈹?    鈹屸攢鈹€鈹€鈹€鈻尖攢鈹€鈹€鈹€鈹€鈹?    鈹?姹囨€荤粨鏋?  鈹?鈫?"鍙戠幇 12 涓湭浣跨敤 import锛屽凡鍒犻櫎锛屾祴璇曢€氳繃"
    鈹斺攢鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹?```

---

### 2.4 Agent 閫傞厤鍣ㄥ眰锛圓dapter Layer锛?
璺ㄥ巶鍟嗛€氱敤鐨勫叧閿€傛瘡绉?CLI 瀹炵幇缁熶竴鎺ュ彛銆?
```typescript
interface AgentAdapter {
  spawn(name: string, workdir: string, model?: string): Promise<{ pid: number; sessionId: string }>;
  execute(sessionId: string, task: Task): Promise<TaskResult>;
  continue(sessionId: string, task: Task): Promise<TaskResult>;
  status(sessionId: string): Promise<AgentStatus>;
  destroy(sessionId: string): Promise<void>;
  list(): Promise<AgentSnapshot[]>;
}
```

#### Phase 1 缁撹锛氬洓绉嶆柟妗堝姣?
| 鏂规 | 鍙鎬?| 璺?CLI | 澶嶆潅搴?| 鎺ㄨ崘搴?|
|------|--------|--------|--------|--------|
| **A: --bg 鍚庡彴 Worker** | 鉂?涓嶅彲琛?| 宸?| 涓?| 娣樻卑 |
| **B: PTY 缁堢鎿嶆帶** | 鈿狅笍 鏈夋潯浠?| 濂?| 楂?| 澶囬€?|
| **C: --resume 鐙珛杩涚▼** | 鉁?鍙 | 涓?| 浣?| 鍙敤 |
| **D: child_process.spawn** | 鉁?鍙 | 濂?| 涓?| **棣栭€?* |

#### 棣栭€夋柟妗堬細child_process.spawn + --resume

```
鍚姩锛歝hild_process.spawn(cbc, ['-p', '--stream-json', '-y'], { cwd: workdir })
澶氳疆锛歴pawn(cbc, ['-p', '--stream-json', '-y', '--resume', sessionId], { cwd: workdir })
杩涚▼绠＄悊锛歅ID 杩借釜 + kill -0 瀛樻椿妫€娴?+ kill 缁堟
```

**鏍稿績浠ｇ爜**锛堣瑙?[shell-process-control.md](./shell-process-control.md)锛夛細

```typescript
class ProcessManager {
  spawn(name, cmd, args) {
    const child = spawn(cmd, args);
    const id = `${name}-${Date.now()}`;
    this.workers.set(id, { pid: child.pid, process: child });
    child.on('exit', code => this.onExit(id, code));
    return id;
  }
  isAlive(id) {
    try { process.kill(this.workers.get(id).pid, 0); return true; }
    catch { return false; }
  }
  kill(id) { this.workers.get(id)?.process.kill(); }
}
```

#### 澶囬€夋柟妗堬細PTY (node-pty + bash wrapper)

鐢ㄤ簬鏃?`--resume` 鐨?CLI銆俉indows 涓嬮€氳繃 bash wrapper 鍚姩锛?
```javascript
const shell = pty.spawn('bash.exe', [], { cwd: workdir, cols: 120, rows: 40 });
shell.write('codebuddy\n');
shell.write('Say hello in one word\n');
```

PTY 宸查獙璇佽兘鍔涳細TUI 鎹曡幏銆佹枃鏈彂閫併€? 鎸囦护銆乀ab 閿€佸杞秷鎭啓鍏ャ€傝瑙?[PTY 瀹為獙鎬荤粨](../../experiments/02-pty-control/pty-experiment-summary.md)銆?
#### 璺ㄥ巶鍟嗛€傞厤绛栫暐

| CLI 宸ュ叿 | 鎿嶆帶鏂瑰紡 | 閫傞厤澶嶆潅搴?|
|----------|---------|-----------|
| CodeBuddy Code | `-p --stream-json --resume` | 浣?|
| Copilot CLI | `-p --silent --yolo --continue` | 涓?|
| Claude Code | `-p --resume` | 涓?|
| Aider | `--message` / `--chat-mode` | 涓?|
| OpenClaw | `claw` 鍛戒护 | 浣庯紙鍙綔涓鸿绠?Agent锛?|
| 閫氱敤 Shell | PTY (bash wrapper) | 涓?|

#### CLIIdentity 鑳藉姏鐭╅樀

姣忎釜閫傞厤鍣ㄥ繀椤诲０鏄庤嚜韬兘鍔涳細

```typescript
interface CLIIdentity {
  name: string;
  capabilities: {
    crossDirResume: boolean;       // --resume 鏄惁璺ㄧ洰褰曟湁鏁?    sessionTTL: number | null;     // session 杩囨湡鏃堕棿锛宯ull = 姘镐箙
    nativeSessionDelete: boolean;  // 鏄惁鏈夊師鐢?session 鍒犻櫎
    nativeSessionList: boolean;    // 鏄惁鏈夊師鐢?session 鍒楄〃
  };
}
```

---

### 2.5 Session 绠＄悊鍣紙Session Manager锛?
**鏍稿績鎬濊矾**锛氫笉涓?CLI 鐨?session 鍥炴敹瀵规姉锛岀敱涓?Agent 缁熶竴鎺ョ銆?
#### 涓夌被 session 绛栫暐

| 绫诲瀷 | 绛栫暐 | 璐熻矗鏂?|
|------|------|--------|
| **娲昏穬 session** | 蹇冭烦淇濇椿锛屼繚鎸?`--resume` 鍙敤 | 璋冨害鍣?|
| **鏃犱环鍊?session** | 涓嶅鐞嗭紝璁?CLI 鑷繁 GC | CLI锛堝厤璐癸級 |
| **鏈変环鍊?session** | 涓?Agent 鏄惧紡鏍囪鍚庡綊妗?| 涓?Agent + 璋冨害鍣?|

#### 褰掓。鍐呭

| 鏁版嵁 | 瀛樺偍 | 鐢ㄩ€?|
|------|------|------|
| Session 鍏冩暟鎹?(sessionId, CLI绫诲瀷, workdir, 鏍囩) | `sessions.json` | 蹇€熺储寮?鏌ヨ |
| 瀹屾暣瀵硅瘽鍘嗗彶 (messages[]) | `archive/{sessionId}.json` | 璺?CLI session 杩佺Щ/閲嶅缓 |

#### 閲嶅缓娴佺▼

1. 浠?`archive/{sessionId}.json` 璇诲彇瀵硅瘽鍘嗗彶
2. 鏂?`spawn` 涓€涓瓙 CLI 杩涚▼
3. 灏嗗巻鍙蹭綔涓?conversationSeed 娉ㄥ叆锛堥€傞厤鍣ㄨ礋璐ｅ簭鍒楀寲锛?
#### sessions.json 缁撴瀯

```json
{
  "updated": "2026-06-12T12:00:00Z",
  "instances": {
    "cbc-worker-1": {
      "id": "cbc-001",
      "name": "cbc-worker-1",
      "adapterType": "cbc",
      "model": "deepseek-v4-pro",
      "pid": 28461,
      "sessionId": "67872ffb-5bff-4a90-b2c7-0f578d94d3ef",
      "workdir": "sessions/cbc-worker-1/",
      "status": "ready",
      "valuable": false,
      "createdAt": "2026-06-12T10:00:00Z",
      "stats": { "taskCount": 5, "lastActiveAt": "2026-06-12T11:59:00Z" }
    }
  }
}
```

#### 蹇冭烦鏈哄埗

```javascript
setInterval(() => {
  for (const inst of Object.values(registry)) {
    try {
      process.kill(inst.pid, 0);
    } catch {
      inst.status = 'dead';
      if (inst.valuable) {
        archiveSession(inst);  // 鑷姩褰掓。鏈変环鍊?session
      }
    }
  }
  saveRegistry();
}, 10000);
```

---

## 涓夈€侀」鐩洰褰曠粨鏋?
```
CLIConductor/
鈹溾攢鈹€ README.md
鈹?鈹溾攢鈹€ docs/
鈹?  鈹溾攢鈹€ planning/
鈹?  鈹?  鈹溾攢鈹€ project-overview.html   # 椤圭洰鎬昏锛堜富瑕佹枃妗ｏ級
鈹?  鈹?  鈹溾攢鈹€ project-overview.md     # 椤圭洰鎬昏 Markdown 鐗?鈹?  鈹?  鈹溾攢鈹€ preview.md              # 涓€椤甸€熻
鈹?  鈹?  鈹斺攢鈹€ beforeInit.md           # 鍘熷闇€姹?鈹?  鈹溾攢鈹€ architecture/
鈹?  鈹?  鈹溾攢鈹€ agent-cluster-architecture.md  # 鏈枃浠?鈹?  鈹?  鈹溾攢鈹€ shell-process-control.md       # 杩涚▼鎺у埗鏂规
鈹?  鈹?  鈹溾攢鈹€ tech-stack-control-layer.md    # 鎶€鏈爤鍏崇郴
鈹?  鈹?  鈹斺攢鈹€ terminal-cli-concepts.md       # 缁堢姒傚康绗旇
鈹?  鈹斺攢鈹€ analysis/
鈹?      鈹溾攢鈹€ openclaw-architecture.md       # OpenClaw 鏋舵瀯鍒嗘瀽
鈹?      鈹溾攢鈹€ cao-analysis.md                # CAO 鍒嗘瀽
鈹?      鈹斺攢鈹€ resource-index.md              # 澶栭儴璧勬簮绱㈠紩
鈹?鈹溾攢鈹€ experiments/
鈹?  鈹溾攢鈹€ experiment-index.md          # 16 椤瑰疄楠岀储寮?鈹?  鈹溾攢鈹€ cbc-multi-cli-experiment.md  # 鍒濆鎺㈢储
鈹?  鈹溾攢鈹€ 01-cbc-persistent/           # CBC 鎸佷箙鍖栧疄楠岋紙s1~s5锛?鈹?  鈹溾攢鈹€ 02-pty-control/              # PTY 鎿嶆帶瀹為獙锛坱1~t3, e01~e04锛?鈹?  鈹斺攢鈹€ 03-concurrent/               # 骞跺彂瀹為獙锛坈1~c2锛?鈹?鈹溾攢鈹€ packages/
鈹?  鈹溾攢鈹€ core/            # Session Manager銆乀ask Queue
鈹?  鈹溾攢鈹€ adapters/        # CBC / Claude / Copilot / Shell 閫傞厤鍣?鈹?  鈹溾攢鈹€ brain/           # 涓?Agent 璋冨害閫昏緫
鈹?  鈹溾攢鈹€ gateway/         # 娑堟伅缃戝叧锛堝鍏ュ彛锛?鈹?  鈹斺攢鈹€ dashboard/       # Web 绠＄悊鐣岄潰锛圥hase 3锛?鈹?鈹溾攢鈹€ sessions/            # 瀛?Agent 鐙珛 workdir
鈹溾攢鈹€ archive/             # 鏈変环鍊?session 褰掓。
鈹斺攢鈹€ logs/                # 杩愯鏃ュ織
```

---

## 鍥涖€佸紑鍙戣矾绾垮浘

### Phase 0锛氬垵濮嬪寲 鉁?- 缁堢/CLI 姒傚康瀛︿範銆佹灦鏋勮璁°€佸閮ㄨ祫鏂欐敹闆?- CAO / OpenClaw 婧愮爜鍒嗘瀽

### Phase 1锛氬疄楠岄獙璇?鉁咃紙16 椤瑰疄楠岋級
- CBC 鎸佷箙鍖?session锛?-resume 澶氳疆 鉁?/ --bg 搴熷純 鉂?- PTY 鎿嶆帶锛歯ode-pty + bash wrapper 鉁?/ tmux 鉂?- 澶氬疄渚嬪苟鍙?+ 璁板繂闅旂 鉁?- **缁撹**锛歝hild_process.spawn + --resume锛堥閫夛級锛孭TY锛堝閫夛級

### Phase 2锛氭渶灏忓彲琛岀郴缁?鈴?- Session Manager锛堟敞鍐屻€佸績璺炽€佸綊妗ｏ級
- CbcAdapter锛堝熀浜?Phase 1 鏂规D锛?- 浠诲姟闃熷垪锛堟枃浠剁郴缁燂級
- CLI 涓绘帶鍏ュ彛
- 绔埌绔細鍚姩 2 涓瓙 cbc锛屽苟琛屾淳鍙戜换鍔?
### Phase 3锛氭墿灞曞拰鍙鍖?馃搵
- Web Dashboard锛坸term.js锛?- 鍏朵粬 CLI 閫傞厤鍣紙Claude Code / Copilot / Aider锛?- QQ Bot / Web 椤甸潰鍏ュ彛
- 涓?OpenClaw 闆嗘垚锛圥lugin 鎴栨瘝绾х鐞嗭級

### Phase 4锛氬畬鏁撮泦缇?馃搵
- 娑堟伅闃熷垪鏇夸唬鏂囦欢闃熷垪
- 璐熻浇鍧囪　
- 瀛?Agent 闂村崗浣?- 鎸佷箙鍖栬蹇嗗叡浜?
---

## 浜斻€佷笌 OpenClaw 鐨勯泦鎴愬彲鑳芥€?
涓ょ浜掕ˉ璺緞锛堣瑙?[OpenClaw 鍒嗘瀽](../analysis/openclaw-architecture.md#711-涓?openclaw-鐨勯泦鎴愬彲鑳芥€?锛夛細

| 璺緞 | 鎻忚堪 | 浜掕ˉ鐐?|
|------|------|--------|
| **A: 浣滀负 Plugin/Skill** | 灏佽涓?OpenClaw 宸ュ叿 | 濉ˉ OpenClaw 瀵圭涓夋柟 CLI 娣卞害绠＄悊鐨勭┖缂?|
| **B: 浣滀负姣嶇骇绠＄悊** | OpenClaw 浣滀负瀛?Agent | OpenClaw 鍋氬墠绔紙娓犻亾+浜や簰锛夛紝鏈郴缁熷仛鍚庣锛堝 CLI 缂栨帓锛?|

---

## 鍏€佹牳蹇冨師鍒?
1. **閫傞厤鍣ㄦā寮忔槸鐏甸瓊** 鈥?姣忕 CLI 涓€涓€傞厤鍣紝缁熶竴 `AgentAdapter` 鎺ュ彛
2. **OS 鍘熻浼樺厛** 鈥?涓嶄緷璧?CLI 鑷韩鐨勮繘绋嬬鐞嗚兘鍔?3. **Session 鍏堟敞鍐屽啀浣跨敤** 鈥?娌℃湁浠讳綍"鐪嬩笉瑙?鐨?session
4. **鍏ュ彛鍜岃皟搴﹁В鑰?* 鈥?娑堟伅鍏ュ彛涓嶅叧蹇冭皝鍦ㄦ墽琛?5. **涓嶄笌 CLI 鍥炴敹瀵规姉** 鈥?鏈変环鍊肩殑褰掓。锛屾棤浠峰€肩殑鏀炬墜
6. **鍏堣窇閫氬啀浼樺寲** 鈥?鏂囦欢绯荤粺 鈫?SQLite 鈫?娑堟伅闃熷垪

