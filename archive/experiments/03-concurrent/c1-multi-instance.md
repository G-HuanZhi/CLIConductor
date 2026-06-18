# 1.3 澶氬疄渚嬪苟鍙戞祴璇?
> 瀹為獙鏃ユ湡锛?026-06-11

## 1.3.1 涓や釜 cbc 瀹炰緥鍚屾椂杩愯

### 娴嬭瘯

```bash
(codebuddy -p -y "What is 1+1?" &)
(codebuddy -p -y "What is 2+2?" &)
wait
```

### 缁撴灉

**涓や釜瀹炰緥骞跺彂杩愯鎴愬姛銆?* 鏃犳姤閿欍€佹棤鍐茬獊銆俰nterleaved 杈撳嚭銆?
## 1.3.2 鏂囦欢閿?/ 璧勬簮鍐茬獊

### MEMORY.md 鍏变韩鏈哄埗

CBC 鐨?auto memory 浣嶄簬:
```
C:\Users\14709\.codebuddy\projects\e-code-MyProject-CLIConductor\memory\
鈹溾攢鈹€ MEMORY.md          # 绱㈠紩鏂囦欢
鈹斺攢鈹€ user_preferences.md  # 鐢ㄦ埛鍋忓ソ
```

### 闅旂绛栫暐

涓烘瘡涓瓙 Agent 鍒嗛厤鐙珛宸ヤ綔鐩綍锛?
```
涓?Agent:    e:\code\MyProject\CLIConductor\
瀛?Agent 1:  e:\code\MyProject\CLIConductor\sessions\agent-1\
瀛?Agent 2:  e:\code\MyProject\CLIConductor\sessions\agent-2\
```

濡傛灉 CBC 鍩轰簬椤圭洰璺緞鍝堝笇鏉ュ畾浣?memory锛屼笉鍚屽瓙鐩綍浼氭槧灏勫埌涓嶅悓鐨?memory store锛屼粠鑰屽疄鐜伴殧绂汇€?
### 楠岃瘉鏂规硶

```bash
# 鍦ㄤ笉鍚岀洰褰曚腑鍚姩涓や釜 cbc锛岄獙璇?MEMORY.md 鏄惁鐙珛
cd sessions/agent-1 && codebuddy -p -y "Remember: X=1" &
cd sessions/agent-2 && codebuddy -p -y "What is X?" &  # 搴旇涓嶇煡閬?X
```

### 缁撹

| 娴嬭瘯椤?| 缁撴灉 |
|--------|------|
| 骞跺彂鍚姩 | 鉁?姝ｅ父 |
| 骞惰鎵ц | 鉁?姝ｅ父 |
| 鍏变韩鐩綍鍐呭瓨 | 鈿狅笍 鍚屼竴椤圭洰鐩綍涓嬪叡浜?MEMORY.md |
| 鐙珛鐩綍闅旂 | 寰呴獙璇侊紙Phase 2 瀹炴祴锛?|

## 鍏抽敭寤鸿

1. Phase 2 涓烘瘡涓瓙 Agent 鍒涘缓鐙珛 `sessions/<agent-id>/` 宸ヤ綔鐩綍
2. 閫氳繃 `--session-id` 鏄惧紡绠＄悊 session
3. 瀛?Agent 鐩綍鏀惧湪 `.gitignore` 涓紝閬垮厤姹℃煋涓婚」鐩?
