---
name: agent-cockpit-spec
description: Agent Cockpit(維運駕駛艙)完整規格——桌面常駐 widget,把 PM 四個關注域(即時訊息/會議/工單維運/開發進度)聚合成一顆可拖曳的球與四個面板;含資料源契約、collector 管線、UI 行為、驗收條件、已知缺口與外部相依交付狀態。同時是「可替換資料源的原型」的規格基準。
version: 1.0.0
updated: 2026-08-29
---

# Agent Cockpit 規格書

## 0. 一句話

**一顆常駐桌面的球,只在該注意時發光;把「散在 Chat／Jira／行事曆／Git／商店的狀態」聚合成四個可展開的面板,每一列都能點開看到「這是什麼、為什麼、要做什麼」,而且所有判讀由本機 LLM(Codex)產生、不需要人整理。**

- **平台範圍**:Windows 桌面應用(Electron)。**本規格不涵蓋 iOS／Android**(§9 §10 N/A)。
- **使用者**:單人工具(PM 本人),無多租戶、無帳號分層。
- **執行位置**:全部在本機執行;唯一外送的資料是給 LLM 判讀的文字(見 §11.4)。

---

## A. 範圍界定

### 1. 變更範圍與改動類型

本規格描述系統**現況全貌**(v1.0 已上線),下表列出所有模組與其類型。

#### 1.1 應用層(`app/`)

| 模組 | 檔案 | 類型 | 職責 |
|---|---|---|---|
| 主程序 | `app/main.js` | 新增 | 視窗(四態同尺寸 420×700 恆定)、滑鼠穿透與 hook keepalive、collector 排程與進度事件、IPC(開檔/開連結/Jira 動作/Calendar 建立/undo/codex resume)、tray、可見性自癒 |
| 前置腳本 | `app/preload.js` | 新增 | contextBridge 白名單:`onState/onScan/onForceMode/setMode/setMouse/cursorOut/refresh/open/hide/nudge/override/undo/jira/calendarCreate/codexResume` |
| 畫面 | `app/index.html` | 新增 | 單一 glass sheet 版面、設計 token(5 字級/4px grid/3 圓角/單一 easing)、四格球體與迷你球、動畫定義 |
| 渲染 | `app/renderer.js` | 新增 | 四域渲染、亮度計算、互動狀態機(orb↔hover↔panel↔overview)、展開/收合動畫、拖曳排序、Ctrl+Z |
| 啟動閘門 | `app/restart.sh` | 新增 | `node --check` ×3 → 定向 kill → 啟動 → 驗證進程數與 boot log(不再靜默死亡) |

#### 1.2 資料層(`collectors/`,每支獨立可跑、失敗不互相牽連)

| collector | 產出 state 區段 | 資料源 | 頻率 |
|---|---|---|---|
| `chat_unread.py` | `immediate`, `chat_recent`, `immediate_wm` | Google Chat API(spaces/messages/spaceReadState) | 5 分(0700–1900) |
| `meeting_suggest.py` | `suggestions` | Chat 近 48h 訊息 + Calendar 衝堂查詢 + Codex 意圖判讀 | 5 分／每小時 |
| `jira_mine.py` | `jira`(await/need/info/mine_all/watches/fixed) | Jira REST(JQL + comments) | 每小時 |
| `jira_enrich.py` | 併入 `jira` 各列 | Codex(單摘要/分類/是否需回覆/是否已在 Chat 處理) | 每小時 |
| `calendar_today.py` | `meetings` | Google Calendar API | 每小時 |
| `meeting_digest.py` | `meetings[].digest` + HTML 紀錄檔 | cmmeeting MCP(逐字稿/彙整) + Codex | 每小時 |
| `release_status.py` | `release` | iTunes Lookup + Play 商店網頁 + Chat 發布群 | 每小時 |
| `dev_progress.py` | `dev` | git log + `.codex-work` lanes + state.jira + state.release + Codex | 每小時 |
| `weekly_draft.py` | `weekly` + 週報草稿檔 | 素材帳本 + 會議萃取 + 完成單 + vault 異動 + Codex | 週一 07:00 |
| `lane_report.py` | `state/lanes_<機器>.json` | 本機 `.codex-work` + git | 每小時(跨機) |
| `jira_action.py` | (無;寫入端) | Jira REST 寫入:狀態轉換、留言(ADF mention) | 使用者觸發 |

#### 1.3 設定層(`config/`,**替換資料源時只改這裡**)

| 檔案 | 內容 |
|---|---|
| `spaces.json` | 掃描的 Chat 房間、優先序、相關性規則、自己的 user id |
| `jira_watch.json` | 代追蹤清單(他人 accountId + 產品過濾) |
| `goals.json` | 產品清單:名稱、程式路徑、lane 關鍵字、對應 Jira 產品名、對應商店 App |
| `meetings.json` | 例行會議 match→準備事項/文件 |
| `glossary.json` | 名詞校對表(產品/人/術語 正式名←別名)、會議進行方式(誰負責什麼、發言順序) |

### 2. 不做的事(Out of Scope)

1. **不標記已讀**:掃 Chat 只讀不寫,`spaceReadState` 僅供判斷未讀;開啟聊天室的按鈕明示「不標已讀」。
2. **不自動寫入外部系統**:Jira 狀態/留言、Calendar 事件一律「使用者按下按鈕才寫」;collector 全部唯讀。
3. **不做多使用者/權限系統**:單人本機工具,無登入、無角色。
4. **不做行動版**:無 iOS/Android 端。
5. **不即時推播**:資料以排程與手動 ⟳ 更新,非 WebSocket 即時流。
6. **不做資料倉儲**:state 是單一 JSON 快照,不保存歷史序列(已修正帳本除外,上限 100 筆)。
7. **不替使用者決策**:LLM 只做摘要/分類/判讀,所有外向動作與排序覆寫由人決定。

### 3. 相依既有功能與回歸範圍

| 既有功能 | 相依方式 | 回歸重點 |
|---|---|---|
| `~/.config/gws-chat/token.json` | Chat/Calendar/Drive 共用 token | 換 scope 或重授權後,四支 collector 都要重驗 |
| Conductor CLI(`~/.claude/skills/conductor`) | cmmeeting 逐字稿來源 | 該 CLI 版本或登入態變動 → 會議萃取失效 |
| `2_Toolkit/Input/1D/Jira/jira.py` | Jira 憑證與 SITE 常數 | 憑證輪替後 `jira_mine`/`jira_action` 同時受影響 |
| Codex CLI(`codex exec`) | 所有 AI 判讀 | 未登入/改版 → 判讀欄位為空但不中斷掃描 |
| Task Scheduler 三個任務 | 定時觸發 | 改任務名/路徑需同步 `run_hidden.vbs` 包裝 |
| vault git repo | dev 進度、週報素材、lane 回報 | repo 路徑變動需改 `goals.json` 與 `ROOT` 常數 |

---

## B. 前置條件

### 4. 使用者狀態與情境

本工具無會員分層,但**下列狀態會觸發不同分支**,驗收時每一種都要走到:

| 狀態 | 觸發條件 | 預期行為 |
|---|---|---|
| **首次啟動(無 state.json)** | `~/.config/agent_cockpit/state.json` 不存在 | 四格全暗、面板顯示「尚未掃描——按 ⟳」,不得崩潰 |
| **有資料且全部無事** | 掃完但無未讀/無待辦 | 面板顯示「沒有未讀 ✓」「沒有要你動的 ✓」,球維持最低亮度 |
| **有未讀且高優先** | 優先序 ≤1 的房間有未讀 | 即時格 lv3 呼吸+ring 亮;看過後(ack)降為 lv2 |
| **Chat token 降級** | 無 readstate scope | 走水位線模式,UI 明示「只看得到掃描後新訊息」 |
| **LLM 不可用** | codex 未登入/逾時 | 保留機械欄位(標題/狀態/期限),AI 欄位留空,不阻斷 |
| **外部 API 失敗** | Jira/Chat/Play 任一失敗 | 該 collector 記 scan.log 並繼續下一支,面板顯示上次成功的資料+stale 標記 |
| **資料過期** | state mtime > 15 分鐘 | 更新時間戳轉暖色並顯示「N 分前」 |
| **使用者已忽略某單** | overrides.ignored 命中 | 該單從所有視圖、計數、亮燈中排除,可在「已忽略」摺疊區還原 |

---

## C. 設定參數

### 5. 設定來源與值(等同本產品的 Remote Config)

本工具**不使用 Firebase Remote Config**;所有可調參數放在 `config/*.json` 與 `~/.config/agent_cockpit/user_overrides.json`,**不需重編譯、下次掃描即生效**。

| Key | 檔案 | 值範例 | 來源 | 生效時機 |
|---|---|---|---|---|
| `immediate[].space` | `spaces.json` | `"SPACE_ID_1"` | Chat URL 的 room/dm id | 下次 5 分掃描 |
| `immediate[].priority` | `spaces.json` | `1`–`9`(小=先) | 使用者定義 | 下次掃描 |
| `immediate[].relevance_rule` | `spaces.json` | 自然語言規則字串 | 使用者定義,交 Codex 判 | 下次掃描 |
| `self_user` | `spaces.json` | `"users/1158…"` | 從自己發的訊息取得 | 下次掃描 |
| `watches[].owner_accountId` | `jira_watch.json` | Jira accountId | Jira 使用者搜尋 | 下次每小時掃描 |
| `watches[].enabled` | `jira_watch.json` | `true/false` | 使用者 | 下次掃描 |
| `products[]` | `goals.json` | 見 §1.3 | 使用者 | 下次掃描 |
| `glossary.products/people/terms` | `glossary.json` | 正式名←別名 | 使用者/會議脈絡 | 下次萃取(需推進快取版本) |
| `ack / dismissed / ignored / expand / jira_order / fv_order / cal_created / sg_dismissed / fixed_cleared_at / ops_tab` | `user_overrides.json` | 由 UI 寫入 | 使用者操作 | 立即(fs.watch 推送) |

**沒有 A/B 實驗干擾**:單人本機工具,無實驗分流機制。

### 6. 預設值與 fallback

| 情境 | Fallback 行為 |
|---|---|
| `config/*.json` 缺檔或格式錯 | 該 collector 印錯誤並略過該功能,其餘照跑(不得整支崩) |
| `state.json` 缺區段 | 對應面板顯示空狀態文案,不得 `undefined` 露出 |
| Codex 回非 JSON | 正則抓取最後一個 `{...}`;再失敗 → 該列 AI 欄位留空,機械欄位照顯示 |
| Chat 無 readstate scope | 降級為水位線(只認掃描後的新訊息)並在 UI 明示 |
| Play/iTunes 查詢失敗 | 該欄顯示 `?`,不影響其他三格 |
| cmmeeting 報告未產出 | 會議列標「待彙整」,下次掃描重試 |
| Jira 寫入失敗 | 按鈕就地顯示「失敗:<原因>」,不改變本地狀態 |
| 排程錯過(機器睡眠) | `StartWhenAvailable` 補跑 + 睡醒 15 秒補掃 + state >20 分鐘舊時 watchdog 自掃 |
| 滑鼠 hook 被系統移除 | 每 3 秒冪等重申(hover 最多 3 秒內自癒) |
| 視窗被外部隱藏 | 每 3 秒偵測,非使用者主動隱藏則自動叫回並記 log |

---

## D. 埋點與觀察

### 7. 事件記錄(本產品的 ELK 等價物)

三個本機 log,皆為純文字、可 `tail` 觀察:

| 檔案 | 事件 | 格式 | 用途 |
|---|---|---|---|
| `~/.config/agent_cockpit/ui.log` | `boot` / `bounds` / `mode A -> B panel=X pin=Y` / `dwell` / `collapse: <reason>` / `auto-reshow` | `HH:MM:SS.mmm [ui] …` | 互動狀態機軌跡;**hover 失效時此檔零行=事件沒進來**(鑑別式) |
| `~/.config/agent_cockpit/scan.log` | `scan start` / `<collector> ok` / `<collector> exit=N <stderr>` / `scan done errs=…` / `stale-watchdog kick` / `jira <op> <key> → <result>` / `calendar_create ok|fail` / `codexResume` | ISO 時戳 + 訊息 | 掃描鏈與寫入動作稽核 |
| `~/.config/agent_cockpit/collector.log` | 各 collector stdout/stderr | 原樣 | 排程執行結果 |

**逐事件關鍵欄位**(QA 要 check 的 params):

| 事件 | 欄位 | 意義 / 檢查點 |
|---|---|---|
| `boot` | `href` | 載入的 index.html 路徑;出現代表 renderer 起來了 |
| `bounds` | `x,y,width,height`,`scale` | 視窗實際位置與 DPI 縮放;寬高必須恆為 420×700 |
| `mode` | `from`,`to`,`panel`,`pin` | 狀態機轉換;`panel` 是當前面板 key、`pin` 是否釘住(釘住時不因離開而收合) |
| `dwell` | `pt{x,y}`,`el`,`key` | hover 輪詢命中的座標與元素;`el` 為 `quad`/`bdg`/`mini`,`key` 為四域之一 |
| `collapse` | `reason` | 收合原因:`poll-out`(游標離開視窗)/`out-of-zone`(離開安全區)/`sheet-leave`/`doc-leave` |
| `auto-reshow` | (無) | 視窗被外部隱藏後自癒;出現代表發生過非使用者主動的隱藏 |
| `scan`(IPC→UI) | `running`,`step`,`idx`,`total`,`errs[]` | 掃描進度;`errs` 為失敗的 collector 名稱清單 |
| `scan start/done` | `errs=<names\|none>` | 一輪掃描的起訖;`done` 未出現代表鏈中斷 |
| `<collector> ok\|exit=N` | `exit code`,`stderr` 末 500 字 | 單支結果;非 0 即失敗但不影響後續 |
| `stale-watchdog kick` | (無) | 資料超過 20 分鐘未更新而自動補掃 |
| `jira <op> <key>` | `op`(transitions/transition/comment),`key`,`result` JSON | 寫入稽核;`comment` 的 result 含 `mentions` 數與 `unresolved` |
| `calendar_create` | `ok`+`event id` 或 `fail`+原因 | 建立行事曆事件的結果 |
| `codexResume` | `thread` | 開終端續談的 Codex thread id |

**漏斗關係**:`scan start` → 逐支 `<collector> ok|exit` → `scan done errs=` → state.json mtime 更新 → renderer 收到 `state` 事件 → 面板時間戳更新。任一環節斷掉都能從此鏈定位。

### 8. UI 可觀察行為(不依賴 log 即可驗收)

| 行為 | 使用者眼睛看得到的 |
|---|---|
| 掃描進行中 | 標題列「掃描中 n/6 <collector 名>」+ ⟳ 持續旋轉 |
| 掃描失敗 | 標題列紅字「掃描完成,N 支失敗:<名稱>」(保留 5 分鐘) |
| 資料過期 | 「更新 HH:MM(N 分前)」轉暖色 |
| 亮燈等級 | 四格透明度 0.30/0.38/0.72/0.95,lv3 呼吸動畫 + 外圈 ring |
| 徽章 | 迷你球上的未讀數/場次/張數/平均開發完成度 |
| 展開/收合 | 高度連續過渡(非瞬間),僅本次點開的區塊播入場動畫 |
| 寫入結果 | 「✓ 已切到『X』」「✓ 已留言,tag N 人」「✓ 已建立,開啟行事曆↗」 |

---

## E. 平台特定行為

### 9. Android — **N/A**(本產品不涵蓋)

### 10. iOS — **N/A**(本產品不涵蓋)

### 10b. Windows 桌面特定行為(本產品實際需要的平台條款)

| 項目 | 要求 |
|---|---|
| 視窗 | frameless + transparent + alwaysOnTop(`screen-saver` 層) + skipTaskbar;四態同尺寸避免跳幀 |
| 滑鼠穿透 | `setIgnoreMouseEvents(true,{forward:true})`;球體半徑 85px 內轉實體;**低階滑鼠 hook 會被系統靜默移除 → 每 3 秒重申** |
| 截圖 | 分層視窗對 BitBlt/CaptureBlt 不可見 → QA 需用 app 自截(`COCKPIT_SHOT`) |
| 進程 | 只能以 CommandLine 含 `agent_cockpit` 過濾後 kill(`taskkill /IM electron.exe` 會誤殺其他 Electron 應用) |
| 排程 | Task Scheduler action 必須是 `wscript run_hidden.vbs <cmd>`(直接跑 .cmd 會彈黑窗);需 `StartWhenAvailable` |
| DPI | 螢幕縮放 150%;E2E 注入滑鼠前必須 `SetProcessDPIAware()` |
| 編碼 | 主控台需 UTF-8;`pythonw` 無 `sys.stdout.buffer`,collector 需 guard |

---

## F. 驗收與例外

### 11. AC 驗收條件

#### AC-1 啟動與存活
- **AC-1.1** WHEN 執行 `app/restart.sh` THEN 印出 `PASS: procs=N`(N≥1)且 `ui.log` 出現 `boot` 與 `bounds`。
- **AC-1.2** WHEN 語法錯誤存在 THEN 啟動閘門在 `node --check` 階段中止並印出錯誤,**不得**留下半死進程。
- **AC-1.3** WHEN 使用者從 tray 選「隱藏小球」THEN 球消失且不自動叫回;WHEN 視窗被非使用者因素隱藏 THEN 3 秒內自動叫回並在 `ui.log` 記 `auto-reshow`。

#### AC-2 互動狀態機
- **AC-2.1** WHEN 游標移入球體 THEN 四顆迷你球以液化分裂出現於左側弧線;WHEN 游標離開安全區 ≥450ms THEN 收合回球。
- **AC-2.2** WHEN 游標停在某迷你球 THEN 對應面板自該球下方展開。
- **AC-2.3** WHEN 點擊大球 THEN 展開全景總覽(四域各一節)。
- **AC-2.4** WHEN 拖曳大球 ≥5px THEN 視窗跟著移動且位置持久化;WHEN 位移 <5px THEN 視為點擊開全景。
- **AC-2.5** WHEN 按 Esc THEN 回到球態;WHEN 按 Ctrl+Z THEN 復原上一個覆寫(最多 30 步)並提示「已復原上一步」。

#### AC-3 資料正確性
- **AC-3.1** WHEN 掃描完成 THEN 面板時間戳等於 `state.json` 對應區段的 `scanned_at`。
- **AC-3.2** WHEN 某房間有 1 則未讀 THEN 該列直接顯示訊息內容;WHEN >1 則 THEN 顯示最新一則預覽,點擊展開全部。
- **AC-3.3** WHEN 使用者自己是最後發言者 THEN 該訊息不計入未讀、不進預覽。
- **AC-3.4** WHEN 單子的最後留言是 RD 提問且尚未在 Chat 回覆 THEN 該單進「要回覆」;WHEN Codex 判定為純資訊補充 THEN 降級到「留言更新」。
- **AC-3.5** WHEN 單子在上次掃描存在、本次消失且 Jira 狀態為 Done THEN 進「已修正」帳本並顯示於原功能區,直到使用者按「一鍵清除」。
- **AC-3.6** WHEN 版本資料齊全 THEN 每個 App 顯示 iOS/Android 各自的「線上版」與「可送審版(build,N 項)」;WHEN 可送審版為 `x.y.99` THEN 歸類為功能測試包、不得當送審候選。

#### AC-4 寫入動作(唯一會改外部系統的路徑)
- **AC-4.1** WHEN 使用者在單詳情按「切換狀態」THEN 顯示該單當下可用的轉換清單(下拉選單);選定並按「切換」後回報新狀態。
- **AC-4.2** WHEN 留言內容含 `@名字` 且該名字可解析 THEN 送出後回報「tag N 人」,且 Jira 上顯示為真 mention(藍底);WHEN 無法解析 THEN 回報「查無此人:X」且不假裝成功。
- **AC-4.3** WHEN 使用者在約時間建議卡按「建立行事曆事件」THEN 寫入 Calendar 並回報連結;**未按下前不得寫入**。
- **AC-4.4** WHEN 任一寫入失敗 THEN 就地顯示錯誤原因,且本地狀態不變。

#### AC-5 會議紀錄
- **AC-5.1** WHEN 今日有已結束且 cmmeeting 報告完成的會議 THEN 產生 HTML 紀錄於 `1_Projects/會議紀錄/YYYY-MM-DD_主題.html`,內含:全景摘要、**按產品分段(每段:為何討論／結論要做什麼／處境／對應 Jira 單)**、決議、待辦、與我相關、完整逐字稿(摺疊)。
- **AC-5.2** WHEN 逐字稿出現名詞表中的別名 THEN 萃取結果一律使用正式名,且逐字稿原文保留但就地加註正式名。
- **AC-5.3** WHEN 會議與使用者無關 THEN「與我相關」明確寫「本場無 X 直接相關事項」,**不得**因此省略全景。

#### AC-6 韌性
- **AC-6.1** WHEN 掃描鏈中某支 collector 失敗 THEN 其餘照跑,失敗名稱寫入 `scan.log` 與 UI。
- **AC-6.2** WHEN 機器睡眠錯過排程 THEN 睡醒 15 秒內補掃;WHEN state 超過 20 分鐘未更新且在工作時段 THEN watchdog 自動觸發掃描。
- **AC-6.3** WHEN hover 失效(hook 被移除)THEN 3 秒內自癒,無需重啟。

### 12. 已知缺口 / AC 例外(遇到不算 bug)

| 編號 | 內容 | 取捨理由 |
|---|---|---|
| **KNOWN-1** | Chat 未讀在無 readstate scope 時只認「掃描後的新訊息」,重授權前可能少算 | 該 scope 需重新授權;UI 已明示降級模式 |
| **KNOWN-2** | Android 線上版取自 Play 商店網頁解析,Google 改版可能失效 | 免憑證;失效時顯示 `?` 而非錯值 |
| **KNOWN-3** | 可送審版本仰賴發布群貼文格式;iOS 貼文常無平台字樣,靠 build 格式(日期型 10 碼)判別 | 格式若變更需更新解析規則 |
| **KNOWN-4** | 開發進度百分比為 Codex 估算,標「估」;非精確工程量測 | 用於趨勢感知,非承諾 |
| **KNOWN-5** | 跨機 lane(A 機的 Product B)需對方安裝回報排程,未裝時該區只顯示 repo 同步得到的 commits | 跨機協作邊界 |
| **KNOWN-6** | 會議萃取品質受逐字稿轉錄品質影響;名詞表未收錄的音譯錯字不會被校正 | 以名詞表增量修正 |
| **KNOWN-7** | 週報草稿的 Hypothesis 欄常標「需要你補」 | 設計如此:寧可標缺也不編造 |
| **KNOWN-8** | 面板為整段重繪,展開很多區塊時單次重繪成本上升 | 資料量級(<100 列)下無感 |

---

## G. 導航

### 13. UI 進入路徑

| 目標 | 路徑 |
|---|---|
| 四域概覽 | 桌面右上小球 → **點擊** → 全景總覽(即時/會議/Jira+維運/開發 四節) |
| 單一面板 | 小球 → **hover** → 左側四顆迷你球 → hover 對應球 → 該面板展開 |
| 即時問題 | 迷你球#1(米色) → 未讀列 →(1則直接顯示/多則點擊展開)→「開啟聊天室↗(不標已讀)」 |
| 約時間建議 | 即時問題面板底部「約時間建議」→ 點卡片 → 「建立行事曆事件」/「開聊天室↗」/「略過」 |
| 會議與紀錄 | 迷你球#2(磚紅) → 會議列 → 點擊 → 全景+我的段落 → 「開完整紀錄↗」 |
| AI 週報草稿 | 會議面板底部「AI 週報草稿」→ 點擊 → 「開草稿」/「與 Codex 討論改稿」 |
| Jira 現況 | 迷你球#3(卡其) → 「現況」tab → 要回覆/要驗收 → 點列展開 → 在 Jira 開啟/切換狀態/留言/忽略 |
| Jira 功能視圖 | 迷你球#3 → 「功能」tab → App → 平台 → 功能塊(點擊展開)→ 單列(點擊展開全景) |
| 版本狀態 | Jira 面板捲到底 → 版本狀態 → 點列 → 各平台線上/可送審與內容 |
| 開發進度 | 迷你球#4(深咖) → 四個 App → 點列 → 為何/現在/下一步/單況/版本 |
| 手動掃描 | 任一面板標題列 ⟳ |
| 收合/隱藏 | 面板標題列 ▏收合;tray 右鍵 →「隱藏小球」/「叫回小球」/「立即掃描」/「結束」 |

---

## H. 後端相依

### 14. 外部相依交付項與驗收環境

**驗收環境:正式資料(本工具直接連線上服務,無測試環境)。** 所有相依皆為**唯讀**,除 §AC-4 標示的三個寫入路徑。

| 相依 | 用途 | 憑證/來源 | 狀態 |
|---|---|---|---|
| Google Chat API | 未讀、預覽、發布群貼文 | `~/.config/gws-chat/token.json` | ✅ 已通(含 `chat.users.readstate.readonly`) |
| Google Calendar API | 今日會議、衝堂查詢、**建立事件** | 同上(`calendar.readonly` + `calendar.events`) | ✅ 已通(2026-08-28 補授權) |
| Google Drive API | (舊路徑)記錄 Doc 匯出 | 同上 | ✅ 已通,現非主源 |
| Jira REST v3 | 我的單/代管單/留言/狀態轉換/mention | `JIRA_EMAIL`+`JIRA_API_TOKEN` 環境變數 | ✅ 已通 |
| cmmeeting(經 Conductor MCP) | 會議彙整報告 + **逐字稿** | Conductor OAuth(`~/.cache/acme-conductor/`) | ✅ 已通 |
| iTunes Lookup API | iOS 線上版 | 無需憑證 | ✅ 已通 |
| Google Play 商店網頁 | Android 線上版 | 無需憑證 | ✅ 已通(解析式,見 KNOWN-2) |
| Codex CLI | 全部 AI 判讀 | `~/.codex/auth.json` | ✅ 已通 |
| Task Scheduler | 三個排程(Chat 5分/每小時/週一) | 本機使用者身分 | ✅ 已建 |
| A 機 lane 回報 | Product B 的 lane 級進度 | 該機執行 `lane_report.py --push` | ❌ 待對方安裝(見 KNOWN-5;已於 HANDOFF 交辦) |

**交付狀態需在使用前再次確認**:token 可能被 Workspace 政策撤銷;`gws_token_watchdog` 會在 SessionStart 報告死亡憑證。

---

## 11. 架構契約(供「換資料源」時遵循)

### 11.1 單一狀態檔

所有 collector 只寫 `~/.config/agent_cockpit/state.json` 的**自己那一段**,採「讀→改自己區段→原子替換(.tmp + os.replace)」;UI 端用 `fs.watch` 監看該檔並推送給 renderer。**新增資料源=新增一個 state 區段 + 一個 render 函式**,不需改動其他模組。

### 11.2 collector 契約

```
輸入:config/*.json(可替換的來源設定)+ 外部 API/CLI
輸出:state.json 的一個 top-level key
規則:①唯讀外部系統 ②失敗印錯誤並以非零碼結束,不寫壞 state
     ③LLM 判讀結果一律快取(cache key 需含「輸入內容簽章 + 判讀邏輯版本」)
     ④判讀邏輯改變必須推進版本字串,否則舊快取會擋住新結果
```

### 11.3 渲染契約

```
render<Domain>(compact) → HTML 字串
列的結構:[動作 chip] [主行=要做什麼] [副行=狀態·期限·來源] (可選)[展開詳情]
亮度:level<Domain>() → 0..3,3=需立即注意(會呼吸)
確認:ack 以「內容簽章」為單位——看過且資料沒變就不再脈動
```

### 11.4 送出邊界

- 送往 LLM 的內容:Chat 訊息文字、Jira 單標題/留言、會議逐字稿、git commit 標題。
- **不送**:憑證、token、密碼、個資欄位(email/電話)。
- LLM 執行於本機 CLI(Codex),中性工作目錄 `~/.config/agent_cockpit`。

---

## 12. 驗證工具(QA 可直接使用)

| 工具 | 用途 |
|---|---|
| `COCKPIT_MODE=panel:<imm\|meet\|ops\|dev>` | 強制以某面板啟動 |
| `COCKPIT_CLICK='<sel> \|> <sel>'` | 拍照前依序點擊(驗展開態) |
| `COCKPIT_SCROLL=<px>` | 捲動後再拍(驗 fold 下方),回寫實際 scrollTop 當回執 |
| `COCKPIT_SHOT=<dir>` | app 自截(分層視窗外部截不到) |
| `COCKPIT_EVAL='<js>'` | 執行 JS(可回 Promise)並把結果寫 `eval.txt`——量測行為/動畫 |
| `qa/e2e_hover.py` | 注入真滑鼠驗 hover 部署與收合 |
| `qa/e2e_orbdrag.py` | 驗拖曳位移與「不誤觸開面板」 |
| `qa/anim_probe.js` | 量測展開/收合的 grid-rows 過渡序列 |
| `qa/flicker_probe.js` | 驗「只有本次點開的區塊播動畫」(舊元素 running=0、新元素 ≥1) |
