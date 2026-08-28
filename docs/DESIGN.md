# Agent Cockpit — PM 維運駕駛艙 設計規格(v1 定稿)

> 2026-08-27 owner 挑定。流程依 uiux-design-check:ASCII 候選 → 挑定(orb 形態,使用者自創第五案)→ 本文件=規格藍圖。
> 目的:讓 owner 隨時清楚**維運全景**——有哪幾類問題、優先順序、處理要用的工具與資源。

## 一、形態總覽(挑定)

常駐=**56px 玻璃小球**,十字分四格(**田字:左上/右上/左下/右下**,非 X 對角)。
Hover 大球 → 左側液滴分裂出 **4 顆 28px 小球**(顏色=面板色)→ hover/點小球=單面板 popover;**點大球=全景總覽(候選 A 直向堆疊)**。

### 四格語意與色板(owner 指定)

| 格位 | 面板 | 色 | 名 | 前景字色 |
|---|---|---|---|---|
| 左上 | 即時問題(Chat) | `#F0FFCE` | Frosted Mint | 深(#2b3313) |
| 右上 | 會議 | `#A53F2B` | Reddish Brown | 白 |
| 左下 | **Jira + 維運版本**(同面板) | `#CCC9A1` | Dry Sage | 深(#3a3722) |
| 右下 | 開發進度(Product ABot/Product B Web) | `#4C230A` | Dark Walnut | 白 |

輔助色:`#CB9F7D` Light Bronze=hover/次要強調、分隔線暖灰。玻璃底=白/黑 8~14% + backdrop-blur 24px + noise。

### 亮燈規則(格=暗→微亮→亮→呼吸脈動)

| 格 | 微亮 | 亮 | 脈動(液化漣漪) |
|---|---|---|---|
| 即時 | 有 P4↓ 未讀 | P2-P3 未讀(Product A小組/泳成) | **P1 Manager 未讀**;任一未讀擱置 >2h |
| 會議 | 下個會 ≤60 分 | ≤30 分;紀錄已出待轉逐字稿 | **≤10 分**;週報草稿已備待看 |
| Jira+維運 | 我 PM 單有新留言/狀態變化;版本審核狀態變化 | 等候驗收新增;RD 要東西;新版發布 | **待我回應 >4h 未動**;急件;版本被拒 |
| 開發 | 進度 % 推進 | 里程碑達成/目標理解更新 | 進度 session 卡死回報 |

## 二、佈局藍圖(挑定 ASCII)

```
【① 靜止】56px 球,田字四格,格=1/4 圓角方格(內發光=亮度);急=該格 1.0→1.06 縮放+漣漪
   ╭──┬──╮      左上 mint(即時)   右上 brown(會議)
   ├──┼──┤
   ╰──┴──╯      左下 sage(Jira維運) 右下 walnut(開發)
【② Hover】 ●walnut ●sage ●brown ●mint ← ╭田╮   (液滴分裂 spring;小球帶計數 badge)
【③ 單面板 popover】360px 玻璃卡,貼小球浮出(hover 350ms 浮出;點=釘住)
【④ 點大球=全景(候選 A)】380×~640px 直向四區,各區可收合;頂列=更新時間 [⟳] ⚙ ▏
   區順序:即時問題 → 今日會議 → Jira+維運 → 開發進度(區塊左緣 4px 面板色條)
【⑤ Calendar 建議卡】(即時面板內;Codex 從 Chat 分析)標題/時間/與會+衝堂實查/Agenda/出處
   [✅ 一鍵建立] [💬 跟 session 討論]   ← 建立=先只建 owner 自己日曆不寄邀請(可在 ⚙ 改成寄邀請)
```

微互動:小球分裂/回收=液滴 morph;面板 blur-in+12px 上滑;`prefers-reduced-motion` 全關;禁卡片陰影浮起(checklist 鐵則)→ 用玻璃層級+邊光。

## 三、面板內容規格

1. **即時問題**(每 5 分掃,絕不標已讀):房間+優先序=config/spaces.json。真未讀=spaceReadState(scope 到位前=水位線退化並標示)。PM支柱夥伴走 Codex 相關性過濾(規則在 config,ⓘ 顯示判定理由+已濾N則)。列=優先色點+房名+未讀數+最新預覽;點=開該房;右滑=手動「已處理」熄燈。偵測到會議邀約→Calendar 建議卡。
2. **會議**(0700 掃 Calendar 排今日;會後每小時盯紀錄檔):列=時間+會名+[要準備的東西];AI週會=[週報草稿▸(skill 產,可改,可喚回產它的 session)][文件▸];VIP2週會=[進度文件▸];紀錄檔出現→自動 meeting-transcribe-digest 轉逐字稿→萃取(需求/決策,限 owner/Product B Web/Product ABot 相關)→顯示摘要卡。
3. **Jira+維運**:JQL=負責PM(customfield_10059)=owner。第一分類=等候驗收/需補充資訊(RD留言要東西);第二=App(Product A/Product B);第三=iOS/Android;第四=功能鄰近排序(Codex 語意分群,如直播類相鄰)。嚴重×急迫評分(影響用戶數/是否影響作者/技術時長,Codex 評)→色深+組內序;[↑][↓] 手動改序(存 override,機器評分不覆蓋人工)。維運小節:未上線版本=Google Play console+ASC 實查 vs 發布(測試)群紀錄比對,列「已發包未上線的功能/修正」。
4. **開發進度**(每小時):掃 Git+Claude/Codex sessions(Product ABot=本機;Product B Web=A 機跑 reporter 寫回共享 repo)。先維護「產品目標理解檔」(終端目標→步驟樹),每次分析=當前在哪步+整體 %;顯示=產品×進度條×當前步驟一句話。

## 四、資料架構

```
collectors(py, Task Scheduler 排程) ──寫→ ~/.config/agent_cockpit/state.json(原子寫)
  chat_unread.py     每5分(0700-1900)      codex 分析步(相關性/評分/分群/萃取)由
  calendar_today.py  0700+會後每小時        orchestrator.py 呼叫 codex exec 完成
  jira_mine.py       每小時                 (中性 cwd;參照 gws_selfheal 模式)
  release_status.py  每小時
  dev_progress.py    每小時(+A 機 reporter 寫 repo)
Tauri app(常駐)──讀 state.json(fs watch)──渲染 orb/面板;[⟳]=立即觸發 collectors
```

規則:collectors 全唯讀(絕不標已讀/絕不回訊/Jira 只讀;唯一寫=使用者按「一鍵建立日曆」)。手動改序/已處理狀態存 `~/.config/agent_cockpit/user_overrides.json`。

## 五、分階段

- P1:orb+全景外殼(Tauri)+即時問題+Jira 面板(真資料)
- P2:會議(排程+紀錄監看+逐字稿萃取+AI週報草稿)+Calendar 建議卡
- P3:維運版本比對+開發進度(含 A 機 reporter)+Codex 評分/分群全接
