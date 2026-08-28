# Agent Cockpit

一顆常駐桌面的球,把散在各系統的狀態聚合成四個可展開的面板;**只在該注意時發光**,平常安靜地待在角落。

它原本是一位 PM 的維運駕駛艙(訊息／會議／工單／開發進度),現在抽成**與資料源無關的原型**——
UI、狀態機、動畫、排程、韌性、寫入動作、QA 工具全部保留,你只要換掉「資料從哪來」就能變成別的東西:
交易看板、監控台、客服待辦、家庭行事曆、任何「四類資訊 + 需要注意時提醒你」的場景。

```
       ●            ← 常駐小球:四格顏色 = 四個域,亮度 = 該不該現在看
      ○○○           ← hover 分裂出四顆迷你球
   ┌─────────┐
   │  面板    │      ← hover 迷你球 → 該域面板從球下方展開
   └─────────┘
```

## 30 秒跑起來(不需要任何憑證)

```bash
cd app && npm install          # 只裝 electron
py ../collectors/demo_source.py   # 產生示範資料
./restart.sh                   # 啟動(內含語法檢查 → 啟動 → 驗活的閘門)
```

球會出現在螢幕右上角。滑過去看四個面板,點球看全景,拖曳可以換位置。

## 換成你的資料源

**一句話:改 `config/pipeline.json`,把 demo 換成你的 collector。**

```jsonc
{ "steps": ["my_source.py"] }              // 全部自己來
{ "steps": ["demo_source.py", "adapters/jira_mine.py"] }   // 混用:工單真實、其餘 demo
```

collector 的契約只有三條(完整版見 [SPEC.md](SPEC.md) §11.2):

1. **輸入**:`config/*.json`(你的來源設定)+ 外部 API/CLI
2. **輸出**:把自己的區段寫進 `~/.config/agent_cockpit/state.json`(讀→改自己那段→原子替換)
3. **規則**:唯讀外部系統;失敗就印錯誤並以非零碼結束,**不要寫壞 state**;LLM 判讀結果要快取,快取鍵必須含「輸入簽章 + 判讀邏輯版本」

UI 讀到 state 就會自動渲染,**不需要改前端**。

### 已經寫好的接法(`collectors/adapters/`)

這些是真實環境跑過的參考實作,示範了六種常見資料源型態:

| adapter | 型態 | 可以借用的部分 |
|---|---|---|
| `chat_unread.py` | 聊天平台 REST + OAuth | 未讀判定(讀取水位 vs 水位線降級)、只讀不標已讀、優先序、LLM 相關性過濾 |
| `jira_mine.py` / `jira_enrich.py` | 議題追蹤系統 + LLM | JQL 抓取、機器人留言過濾、嚴重度計分、LLM 摘要與分類、快取鍵設計 |
| `jira_action.py` | **寫入端** | 狀態轉換(先查可用轉換再送)、留言的真 @mention(ADF node,不是純文字) |
| `calendar_today.py` / `meeting_suggest.py` | 行事曆 + 意圖判讀 | 今日事件、附件偵測、衝堂實查、從訊息判「要不要約時間」 |
| `meeting_digest.py` | 逐字稿 → 結構化紀錄 | 名詞校對表、按產品分段(為何/結論/處境)、產出 HTML 紀錄 |
| `release_status.py` | 公開商店資料 + 通知解析 | 免憑證取線上版本、從通知訊息解析待送審版本與內容 |
| `dev_progress.py` | 版控 + 工作區 + LLM | 從 commit/lane 估進度、與工單/版本交叉 |
| `weekly_draft.py` | 多源彙總 → LLM 生成 | 四源材料組合、產生可續談的草稿(記錄 LLM thread id) |
| `lane_report.py` | 跨機器同步 | 把本機狀態寫成 repo 內檔案,另一台合併 |

> adapter 內的識別資訊(網域、帳號、產品名、單號)都已代換成 `example` / `Product A` / `TICKET-1000` 這類佔位符,**照著改成你的即可**。

## 你會拿到什麼

- **四域 × 三態的注意力模型**:每個域自己算 0–3 的亮度,3 會呼吸;看過且資料沒變就不再閃(ack 以內容簽章為單位)
- **一顆球的互動狀態機**:orb ↔ hover ↔ panel ↔ overview,含滑鼠穿透、安全區、輪詢收合、拖曳換位
- **展開/收合動畫**:高度連續過渡,且只有本次點開的區塊播入場動畫(否則整段重繪會整片閃)
- **排程與韌性**:逐支跑不互相牽連、失敗記錄、睡醒補掃、資料過期自動補、視窗被藏自癒
- **寫入動作的安全邊界**:所有外部寫入都要使用者按下按鈕,collector 一律唯讀
- **可量測的 QA 工具**:自截、強制模式、連續點擊、捲動回執、**動畫量測**、E2E 滑鼠注入
- **一份 24/24 的規格書**([SPEC.md](SPEC.md)):範圍、不做的事、狀態分支、fallback、事件欄位、AC、已知缺口

## 專案結構

```
app/            Electron 主程序 / preload / 單頁 UI / 渲染器 / 啟動閘門
collectors/
  demo_source.py    免憑證示範資料(開箱即用)
  adapters/         真實接法的參考實作(換成你的資料源)
config/
  pipeline.json     ★ 要跑哪些資料源
  *.example.json    各 adapter 的設定範本(複製成 *.json 再填)
qa/               E2E 與量測腳本(hover / 拖曳 / 動畫 / 閃動)
docs/             設計過程文件
SPEC.md           完整規格
```

## 需要什麼

- Node.js(Electron)、Python 3
- 選用:任何 CLI 型 LLM(adapter 裡用 `codex exec`,換成你慣用的即可——呼叫點都集中在各 adapter 的 `codex()` 函式)

## 授權

MIT
