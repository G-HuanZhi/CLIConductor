# 1.1.2 --bg + attach 琛屼负娴嬭瘯

> 瀹為獙鏃ユ湡锛?026-06-11

## 瀹為獙鐩殑

楠岃瘉 `codebuddy attach` 鍒拌繍琛屼腑鐨?bg 浼氳瘽鐨勫彲琛屾€с€?
## 娴嬭瘯缁撴灉

### 娴嬭瘯锛歛ttach 杩愯涓殑浼氳瘽

```bash
# 鍚姩涓€涓細杩愯涓€娈垫椂闂寸殑 bg 浠诲姟
codebuddy --bg --name test-wait -y "Please wait for 10 seconds..."

# 绔嬪嵆 attach
codebuddy attach test-wait
```

**杈撳嚭**锛?```
Attaching to session test-wait (log: C:\Users\14709\.codebuddy\logs\test-wait.log)
Press Ctrl+C to detach (session will continue running)
```

**缁撴灉**锛?- `attach` 鍚姩浜嗕絾闇€瑕佷氦浜掑紡缁堢鐜
- 鍦ㄦ垜浠」鐩殑 bash 绠￠亾鐜涓棤娉曟甯镐娇鐢紙渚濊禆 TTY锛?- 鈿狅笍 鍦ㄧ敓浜х幆澧冧腑锛岄€氳繃 node-pty 搴旇鍙互姝ｅ父 attach

### 娴嬭瘯锛歛ttach 宸查€€鍑虹殑浼氳瘽

```bash
codebuddy attach test3  # test3 宸插畬鎴愬苟閫€鍑?```

**杈撳嚭**锛歚Error: Session not found: test3`

### 娴嬭瘯锛歭og 璇诲彇

```bash
codebuddy logs test-wait  # 杩愯涓殑浼氳瘽
```

**杈撳嚭**锛歚Error: Session not found: test-wait` (鍗充娇 ps 涓彲瑙?

```bash
cat C:\Users\14709\.codebuddy\logs\test-wait.log  # 鐩存帴璇绘枃浠?```

**杈撳嚭**锛歚I waited 10 seconds.` 鉁?
### 娴嬭瘯锛歝odebuddy ps 鑳藉姏

```bash
codebuddy ps
```

杩愯鏈熻緭鍑虹ず渚嬶細
```
PID       KIND            NAME              STATUS      CWD                             STARTED
1188      bg              test-wait         unknown     e:\code\MyProject\CLIConductor  11s ago
25768     interactive     -                 unknown     E:\code\MyProject\CLIConductor  49m ago
```

## 缁撹

| 鍔熻兘 | 鍙鎬?| 澶囨敞 |
|------|--------|------|
| attach 杩愯涓細璇?| 鏈夋潯浠?| 闇€瑕?TTY 鐜锛岀閬?bash 涓棤娉曚娇鐢?|
| attach 宸查€€鍑轰細璇?| 涓嶆敮鎸?| 浼氳瘽閫€鍑哄悗涓嶅彲 attach |
| codebuddy logs | 鏈?bug | 杩愯涓細璇濇姤 "not found"锛岄渶鐩存帴璇绘枃浠?|
| codebuddy ps | 鏀寔 | 鑳界湅鍒?bg 绫诲瀷鍜?interactive 绫诲瀷浼氳瘽 |
| codebuddy kill | 鏀寔 | 鍙粓姝㈣繍琛屼腑鐨?bg 杩涚▼ |
| 鐩存帴璇?log 鏂囦欢 | 鏀寔 | 鏈€鍙潬鐨勬柟寮?|

## 瀵规湰椤圭洰鐨勫奖鍝?
- `attach` 涓嶉€傚悎浣滀负鑷姩鍖栨柟妗堬紙渚濊禆 TTY锛?- 璇诲彇 bg 浠诲姟鐨勮緭鍑猴細鐩存帴璇?`.codebuddy/logs/<name>.log` 鏂囦欢
- `codebuddy ps` 鍙敤浜庣洃鎺у瓙 agent 鐘舵€?- `codebuddy kill` 鍙敤浜庣粓姝㈠瓙 agent

