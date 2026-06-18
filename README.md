# CLIConductor

> 涓?Agent + 鐢ㄦ埛**鍙屾帶**鍚屼竴涓?CLI 杩涚▼鐨勫叡浜細璇濇柟妗堛€?
## 鏋舵瀯

```
浣狅紙鍘熺敓缁堢 / PowerShell锛夆攢鈹€ WebSocket 鈹€鈹€鈹?                                          鈹溾攢鈹€ server.js (node-pty) 鈹€鈹€鈫?cbc
鎴戯紙Claw / OpenClaw锛?    鈹€鈹€ WebSocket 鈹€鈹€鈹?```

## 鍚姩

```bash
npm run bridge
# 鈫?ws://localhost:6789
```

## 杩炴帴

| 瑙掕壊 | 鏂瑰紡 |
|------|------|
| **浣?* | 鍦ㄧ湡瀹炵粓绔繍琛?`packages/cbc-bridge/connect.ps1` |
| **鎴?(Claw)** | 閫氳繃 ws://localhost:6789 WebSocket 璇诲啓 |

## 鐩綍

```
packages/cbc-bridge/
鈹溾攢鈹€ server.js        # 鏍稿績妗ユ帴锛歐ebSocket + node-pty
鈹溾攢鈹€ connect.ps1      # 鐢ㄦ埛绔細PowerShell 鍘熺敓缁堢瀹㈡埛绔?鈹溾攢鈹€ claw-client.js   # Claw 绔細WebSocket 浜や簰鑴氭湰
鈹斺攢鈹€ send.js          # 鍗曟鍛戒护鍙戦€佸伐鍏?
archive/             # 鍐荤粨鐨勬棫璁″垝/瀹為獙/鏂囨。锛堝弬鑰冪敤锛?鈹溾攢鈹€ references/       # 澶囬€夋柟妗堝瓨妗ｏ紙濡?web-xterm.js 鏂规锛?鈹斺攢鈹€ ...
```

