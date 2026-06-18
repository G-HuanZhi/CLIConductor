# DionysusC 鈫?CLIConductor 瀵规瘮鍒嗘瀽

鏃ユ湡锛?026-06-27

## 涓€銆佹憳瑕?
绠€瑕佸姣旀闈?闄即鍨?Agent锛圖ionysusC锛変笌涓?浠?CLI 闆嗙兢璋冨害鏂规锛圡yAgentsPlan锛夈€傜粨璁猴細DionysusC 鍦ㄧ敤鎴蜂綋楠屻€侀櫔浼?鎯呯华寮曟搸鍜屽墠绔墦鍖呬笂鎴愮啛锛汳yAgentsPlan 鍦ㄥ CLI 娣卞害鎺у埗銆丼ession 绠＄悊涓庤法鍘傚晢閫傞厤涓婃洿瀹屽銆備袱鑰呭彲浜掕ˉ銆?

## 浜屻€佹牳蹇冨樊寮?
- 鏋舵瀯瀹氫綅锛?
  - DionysusC锛氫互妗岄潰 Electron 瀹㈡埛绔?+ FastAPI 鍚庣涓轰富锛岄潰鍚戠粓绔敤鎴蜂綋楠岋紙Live2D銆佹儏缁€乀TS锛夈€?
  - CLIConductor锛氫互涓?Agent 璋冨害澶氱涓夋柟 CLI 涓虹洰鏍囷紝寮鸿皟 OS 鍘熻銆佽繘绋?Session 绠＄悊涓庨€傞厤鍣ㄣ€?

- 浼氳瘽涓庤繘绋嬬鐞嗭細
  - DionysusC锛歋QLite 鎸佷箙鍖栥€丼ession 闄愭祦锛坢ax_concurrent锛夛紝鏈夐€傞厤鍣ㄦ敞鍐?Registry锛屼絾杩涚▼娣卞害绠＄悊鏇翠互閫傞厤鍣ㄨ兘鍔涗负涓汇€傞厤缃€氳繃 Pydantic/Settings 鍔犺浇闆嗕腑绠＄悊銆?
  - CLIConductor锛氱粏绮掑害 PID/蹇冭烦/褰掓。/閲嶅缓銆乻essions.json + archive/{id}.json锛屾槑纭?"valuable" 鏍囪涓庨噸寤烘祦绋嬨€?

- 鎵╁睍/閫傞厤绛栫暐锛?
  - DionysusC锛氭彁渚?IAgentAdapter 鎺ュ彛涓?AdapterRegistry锛屼究浜庢坊鍔?CLI 鏀寔锛涘己璋?persona/supervisor 鐢熸€併€?
  - CLIConductor锛氬己鍒堕€傞厤鍣ㄨ兘鍔涚煩闃碉紙CLIIdentity锛夈€丳TY 澶囬€夈€乧hild_process.spawn + --resume 涓洪閫夈€?

- 鐢ㄦ埛绔?浜や簰锛?
  - DionysusC锛氬叧娉ㄦ儏缁紩鎿庛€佽鑹查櫔浼淬€佹祦寮?UI銆佷富棰樹笌璺ㄨ澶囪闂€?
  - CLIConductor锛氬叧娉ㄥ鍏ュ彛锛圕LI/Web/IM锛変笌璋冨害鍙鍖栵紙Dashboard銆亁term.js锛夈€?

## 涓夈€佸叡鍚岀偣
- 閮戒娇鐢ㄩ€傞厤鍣?registry 妯″紡鏉ユ帴鍏ヤ笉鍚?CLI銆?
- 閮戒繚鐣欎簡澶?Agent 骞跺彂涓庢祦寮忎氦浜掕兘鍔涖€?
- 閰嶇疆涓庝富棰樺潎鍙€氳繃 YAML/env 瑕嗙洊锛屾敮鎸佺儹鍔犺浇/鍒囨崲銆?

## 鍥涖€佷簰鐩稿€熼壌寤鸿
- CLIConductor 鍊?DionysusC 鐨勭偣锛?
  1. 鍓嶇/UX锛氬紩鍏ョ畝鏄撻櫔浼村眰锛堟儏缁?鐘舵€佹槧灏勶級鐢ㄤ簬璋冨害浠〃鐩樼殑鍗虫椂鍙鍙嶉锛屾彁鍗囧彲瑙傛祴鎬т笌鍙嬪ソ鎬с€?
  2. Persona/涓婚閰嶇疆锛氬鍒跺叾 persona YAML 鏍煎紡浠ユ敮鎸佸彲瀹氬埗鐨勬儏缁笌璇皟锛堝澶栨紨绀烘洿浜插拰锛夈€?
  3. 鎵撳寘/鍙戝竷缁忛獙锛氬涔?Electron+PyInstaller 鐨勮法骞冲彴鎵撳寘娴佺▼涓庝富棰樼儹杞藉疄鐜般€?

- DionysusC 鍊?CLIConductor 鐨勭偣锛?
  1. 娣卞害 Session 绠＄悊锛氬湪 Adapter 灞傚鍔?PID/蹇冭烦銆乿aluable 鏍囪涓庡綊妗?閲嶅缓娴佺▼锛岄伩鍏嶄細璇濅涪澶辨垨閲嶈浼氳瘽涓嶅彲澶嶇幇銆?
  2. PTY 澶囬€変笌 child_process.spawn 绛栫暐锛氫负鏃犳硶鎻愪緵 resume/stream-json 鐨?CLI 鎻愪緵 PTY 鎿嶆帶鍚庡鏂规銆?
  3. 缁熶竴鑳藉姏鐭╅樀锛圕LIIdentity锛夛細璁╁墠绔?浠〃鐩樿兘鏄剧ず姣忎釜閫傞厤鍣ㄧ殑鑳藉姏涓庨檺鍒躲€?

## 浜斻€佷紭鍏堟墽琛岀殑鍏蜂綋寤鸿锛堢煭鏈燂級
1. 鍦?CLIConductor 鐨?Dashboard 涓姞鍏ョ畝鍗曟儏缁?鐘舵€佹潯锛坢apping: executing鈫抍onfident, success鈫抙appy锛夛紝澶嶇敤 DionysusC 鐨?emotion mapping 閰嶇疆銆? 
2. 鍦?DionysusC 鐨?AdapterRegistry 涓姞鍏ュ彲閫夌殑 ProcessManager锛坰pawn/heartbeat/archive hooks锛夛紝鍙?configuration flag 寮€鍚繁搴︾鐞嗐€? 
3. 鍙屾柟缁熶竴涓€涓皬鍨嬫枃妗ｆā鏉匡細Adapter 鑳藉姏鐭╅樀锛坣ame, capabilities, resume_support, native_list, session_ttl锛夛紝渚夸簬浜掔浉閫傞厤涓庤嚜鍔ㄥ寲灞曠ず銆?

## 鍏€佷腑闀挎湡寤鸿锛堟垬鐣ワ級
- 鑰冭檻鎶?CLIConductor 灏佽鎴愪竴涓彲琚?DionysusC 浣滀负 Skill/鍚庣绠＄悊鐨勬湇鍔★紙鎴栧弽鍚戯紝鎶?DionysusC 鍋氫负 CLIConductor 鐨勫墠绔帴鍏ュ眰锛夈€?
- 褰㈡垚鍏变韩鐨勪細璇濆綊妗ｈ鑼冿紙JSON schema锛夛紝鏀寔鍦ㄤ袱濂楃郴缁熼棿杩佺Щ/閲嶅缓瀵硅瘽鍘嗗彶銆?

---

鐢熸垚鑰咃細鍒嗘瀽鑴氭湰锛堝熀浜庨」鐩枃妗ｏ級

*鏂囦欢浣嶇疆锛欴ionysusC_vs_CLIConductor.md*
