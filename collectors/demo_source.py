# -*- coding: utf-8 -*-
"""Demo 資料源——讓 Agent Cockpit 開箱即有畫面,不需要任何憑證。

它產生的 state.json 與真實 adapter(collectors/adapters/*.py)**格式完全相同**,
所以你可以:
  1. 先跑這支看 UI 全貌
  2. 再把 adapters/ 裡對應的那支換成你的資料源(改 config/*.json 或改 fetch 函式)
  3. 兩者可混用:例如真的接 Jira、其餘維持 demo

用法:py demo_source.py           # 寫入 ~/.config/agent_cockpit/state.json
     py demo_source.py --print   # 只印出結構不寫檔
"""
import io, os, sys, json, time, random, datetime

if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
else:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")

STATE = os.path.expanduser("~/.config/agent_cockpit/state.json")
NOW = datetime.datetime.now()
TS = NOW.strftime("%Y-%m-%d %H:%M:%S")


def iso(offset_min):
    return (NOW + datetime.timedelta(minutes=offset_min)).strftime("%Y-%m-%dT%H:%M")


# ── ① 即時訊息(來源類型:聊天平台 API)────────────────────────────
IMMEDIATE = {
    "scanned_at": TS,
    "readstate_scope": True,
    "rows": [
        {"space": "SPACE_ID_1", "label": "Direct — RD-iOS", "priority": 1, "unread": 1,
         "mode": "readstate", "filtered_out": 0,
         "url": "https://chat.example.com/room/SPACE_ID_1",
         "preview": [{"t": "10:24", "sender_tail": "9f21",
                      "text": "剛推上去的版本卡在建置,你那邊要先驗哪一支?"}]},
        {"space": "SPACE_ID_2", "label": "Team — Product A / Product B", "priority": 3, "unread": 3,
         "mode": "readstate", "filtered_out": 1,
         "url": "https://chat.example.com/room/SPACE_ID_2",
         "preview": [{"t": "10:11", "sender_tail": "3ab0", "text": "cc PM-2 這張要不要一起併?"},
                     {"t": "10:08", "sender_tail": "77c1", "text": "後端資料表拆好了,前端可以接了"},
                     {"t": "09:55", "sender_tail": "3ab0", "text": "今天下午的驗收改到四點"}]},
    ],
}

# ── ② 約時間建議(來源:聊天訊息 + 行事曆衝堂查詢 + LLM 意圖判讀)──
SUGGESTIONS = {
    "at": TS,
    "items": [{
        "id": "demo/msg/1", "space": "SPACE_ID_2", "room": "Team — Product A / Product B",
        "url": "https://chat.example.com/room/SPACE_ID_2", "from": "3ab0", "at": iso(-45),
        "text": "PM-2:明天下午三點可以約 30 分鐘對一下 Product A 的檔期嗎?RD-Backend 也一起",
        "title": "對齊 Product A 檔期", "start": iso(1500), "end": iso(1530),
        "duration_min": 30, "attendees": ["PM-2", "RD-Backend"],
        "agenda": "上線檔期與後端資料相依", "conflicts": ["Weekly Sync"],
    }],
}

# ── ③ 工單維運(來源:議題追蹤系統 + LLM 摘要/分類)───────────────
def ticket(key, what, status, product, platform, feature, is_bug=False, need=None,
           due=None, overdue=False, sev=1, story="", lc=None, extra=None):
    d = {"key": key, "title": what, "raw": "【%s-%s】%s" % (platform, product, what),
         "what": what, "need": need or "", "story": story or (
             "這張單處理「%s」。目前狀態 %s;需要 owner 確認的是驗收條件與影響範圍。" % (what, status)),
         "status": status, "product": product, "platform": platform, "feature": feature,
         "is_bug": is_bug, "score": sev * 10, "sev": sev,
         "url": "https://your-org.atlassian.net/browse/" + key,
         "updated": iso(-random.randint(30, 600))}
    if due: d["due"] = due
    if overdue: d["overdue"] = True
    if lc: d["lc"] = lc
    if extra: d.update(extra)
    return d


AWAIT = [
    ticket("TICKET-1011", "支援清單頁批次操作", "等候驗收", "Product A", "iOS", "清單/篩選",
           need="驗收批次選取與復原行為", due="2026-09-24", sev=2,
           lc={"by": "RD-iOS", "at": iso(-180), "text": "已在測試包,麻煩驗一下多選後切換分頁的狀態保留。",
               "asks": True, "stale_h": 3, "by_id": "rd-ios"}),
    ticket("TICKET-1012", "修正圖表縮放後標籤重疊", "等候驗收", "Product B", "Android", "圖表",
           is_bug=True, need="驗收縮放後標籤是否仍重疊", due="2026-09-10", sev=2),
]
NEED = [
    ticket("TICKET-1021", "推播文案要不要帶產品名", "等候 Code Review", "Product A", "雙平台", "推播/通知",
           need="回覆 RD:文案是否統一帶產品名", due="2026-08-27", overdue=True, sev=3,
           lc={"by": "RD-Mobile", "at": iso(-320), "text": "文案兩種寫法都可以,你決定哪一種我就照做。",
               "asks": True, "stale_h": 5, "by_id": "rd-mobile"}),
]
INFO = [
    ticket("TICKET-1031", "補上錯誤回報的追蹤欄位", "進行中", "Product B", "後端", "穩定性",
           sev=1, extra={"chat_done": "已在群組回覆過,RD 依此進行"}),
]
MINE_ALL = AWAIT + NEED + INFO + [
    ticket("TICKET-1041", "新增設定頁深色模式", "待辦事項", "Product A", "iOS", "畫面/UI", sev=1),
    ticket("TICKET-1042", "調整首頁載入順序", "進行中", "Product A", "Android", "畫面/UI", sev=1),
    ticket("TICKET-1043", "修正離線時的空狀態", "待辦事項", "Product B", "雙平台", "穩定性", is_bug=True, sev=1),
]
WATCH_ROWS = [
    {**ticket("TICKET-2001", "改善大盤頁載入過慢", "等候驗收", "Product C", "Android", "行情資料", sev=2),
     "bucket": "await"},
    {**ticket("TICKET-2002", "補上圖例說明", "進行中", "Product C", "iOS", "圖表", sev=1), "bucket": "other"},
]
FIXED = [
    {"key": "TICKET-1051", "title": "提供匯出圖片能力", "what": "提供匯出圖片能力",
     "product": "Product B", "platform": "iOS", "feature": "圖表", "status": "完成", "is_bug": False,
     "url": "https://your-org.atlassian.net/browse/TICKET-1051",
     "fixed_at": NOW.strftime("%Y-%m-%dT%H:%M:%S")},
]
JIRA = {"scanned_at": TS, "sig": "demo0001", "await": AWAIT, "need": NEED, "info": INFO,
        "mine_all": MINE_ALL, "fixed": FIXED, "total_open": len(MINE_ALL),
        "watches": [{"id": "demo_watch", "label": "代追蹤:PM-2 的 Product C 單",
                     "rows": WATCH_ROWS, "note": "示範代管他人工單"}]}

# ── ④ 會議(來源:行事曆 + 會議系統逐字稿 + LLM 萃取)──────────────
MEETINGS = {
    "scanned_at": TS, "today": [
        {"start": iso(-180), "end": iso(-140), "title": "Daily Standup — Board 3/4",
         "meet": "https://meet.example.com/abc", "attendees": 12,
         "record": {"title": "記錄 - Daily Standup", "url": "https://docs.example.com/d/DEMO"},
         "digest": {
             "src": "meeting-system", "mid": 1001, "at": NOW.strftime("%m-%d %H:%M"),
             "html": "",
             "overview_summary": "本場聚焦 Product E 兩端顯示邏輯不一致的收斂,以及 Product C 後端資料改接;"
                                 "結論是後端先提供全樣本、前端依清單決定預設顯示。",
             "apps": [
                 {"app": "Product E(Web)", "why": "圖表座標重疊,兩支標的需拆開呈現",
                  "what": "補需求單並修正標籤與座標拆分", "who": "PM-1", "status": "待補單",
                  "points": ["逐字稿未交代時程"],
                  "tickets": [{"key": "TICKET-1000", "t": "座標拆分需求", "s": "待辦事項", "rel": "就是在講這張"}]},
                 {"app": "Product C", "why": "訊號通知有延遲,資料表需拆開",
                  "what": "改接獨立資料表並查明延遲", "who": "PM-2、RD-Backend", "status": "待改接",
                  "points": ["9:03 發生、9:09 才通知"], "tickets": []},
             ],
             "decisions": ["後端資料擴充為全樣本", "前端依清單決定預設顯示"],
             "actions": [{"what": "補需求單並標註範圍", "who": "PM-1"},
                         {"what": "查明通知延遲原因", "who": "RD-Backend"}],
             "mine_summary": "本場無 Owner 直接相關事項",
             "mine_needs": [], "mine_decisions": [], "mine_todos": [],
         }},
        {"start": iso(120), "end": iso(180), "title": "Weekly Sync", "attendees": 8,
         "prep": "帶上週報草稿", "doc": "https://docs.example.com/d/WEEKLY"},
    ],
    "next_start": iso(120),
}

# ── ⑤ 版本狀態(來源:商店公開 API/網頁 + 發布通知)────────────────
RELEASE = {
    "scanned_at": TS,
    "note": "線上版=商店公開資料;可送審=發布群通知解析",
    "apps": {
        "Product A": {
            "ios_live": {"ver": "2.6.1", "at": "2026-08-07"},
            "android_live": {"ver": "2.6.3", "at": ""},
            "ios_review": {"ver": "2.6.3", "build": "2026082501", "at": "2026-08-25", "n_builds": 2,
                           "items": [{"v": "2.6.3", "t": "TICKET-1000 篩選器新增排除條件"},
                                     {"v": "2.6.2", "t": "TICKET-1001 修正清單頁快取"}]},
            "android_review": {"ver": "2.7.0", "build": "373", "at": "2026-08-27", "n_builds": 1,
                               "items": [{"v": "2.7.0", "t": "TICKET-1002 設定頁改版"}]},
            "ios_note": "線上 2.6.1;2.6.3 候選已出建置、待送審",
            "android_note": "線上 2.6.3;2.7.0 候選待送審",
        },
        "Product B": {
            "ios_live": {"ver": "2.5.2", "at": "2026-07-31"},
            "android_live": {"ver": "2.5.13", "at": ""},
            "ios_review": {"ver": "2.6.0", "build": None, "at": "2026-08-21", "n_builds": 0,
                           "items": [], "inferred": True},
            "android_review": {"ver": "2.6.0", "build": "61", "at": "2026-08-28", "n_builds": 5,
                               "items": [{"v": "2.6.0", "t": "TICKET-2000 圖表事件標記"},
                                         {"v": "2.5.17", "t": "TICKET-2001 語音房進房修正"}]},
            "ios_qa": {"ver": "2.6.99", "build": "2026082101", "at": "2026-08-21",
                       "items": [{"v": "2.6.99", "t": "TICKET-2002 功能測試包"}]},
            "ios_note": "線上 2.5.2;2.6.0 候選卡 QA 回歸、建置未出;2.6.99 為功能測試包",
            "android_note": "線上 2.5.13;2.6.0 候選已出建置、待送審",
        },
    },
}

# ── ⑥ 開發進度(來源:版控 + 工作區 lane + 工單 + LLM 估算)────────
DEV = {
    "scanned_at": TS,
    "products": [
        {"id": "product_a", "name": "Product A Bot", "goal": "問答與健診全功能上線並對付費用戶開放",
         "commits7d": 7, "last_at": iso(-120), "last_msg": "收斂資料源與問答流程", "lanes": [{"name": "feature/bot-qa", "age_h": 2.5}],
         "remote": "", "why": "核心功能已可用,剩驗收與資料正確性", "step": "收斂問答資料源",
         "next": "請 owner 拍板 MVP 後由 RD 完成三張待辦並驗收", "pct": "估70%", "basis": "近 7 天集中在資料源與穩定性",
         "jira": {"開放單數": 3, "等候驗收": ["支援清單頁批次操作"], "進行中": ["調整首頁載入順序"],
                  "待辦": ["新增設定頁深色模式"], "要回覆": ["推播文案要不要帶產品名"], "近期完成": []},
         "release": {"iOS線上": "2.6.1", "Android線上": "2.6.3", "iOS可送審": "2.6.3", "Android可送審": "2.7.0"}},
        {"id": "product_b", "name": "Product B Web", "goal": "桌面版三欄工作區上線",
         "commits7d": 1, "last_at": iso(-900), "last_msg": "建立跨機交接指標", "lanes": [],
         "remote": "另一台機器開發中——本機只看得到已同步的 commits", "why": "跨機開發,本機視角有限",
         "step": "部署狀態可追蹤", "next": "確認部署環境並驗收主流程", "pct": "估35%",
         "basis": "本機僅同步到基礎設施部分",
         "jira": {"開放單數": 2, "等候驗收": ["修正圖表縮放後標籤重疊"], "進行中": [], "待辦": ["修正離線時的空狀態"],
                  "要回覆": [], "近期完成": ["提供匯出圖片能力"]},
         "release": {"iOS線上": "2.5.2", "Android線上": "2.5.13", "iOS可送審": "2.6.0", "Android可送審": "2.6.0"}},
    ],
}

# ── ⑦ 週報草稿(來源:素材帳本 + 會議 + 工單 + LLM 生成)────────────
WEEKLY = {
    "at": NOW.strftime("%Y-%m-%d %H:%M"), "week": NOW.strftime("%Y-%m-%d"),
    "path": "", "thread": "demo-thread-0000",
    "titles": ["[Product A] 核心流程可用,跨平台驗證仍待完成",
               "[Product B] 五項交付完成,重心轉向整合驗收",
               "[內部工具] 聚合面板打通四類資料源"],
}


def main():
    st = {"immediate": IMMEDIATE, "suggestions": SUGGESTIONS, "jira": JIRA,
          "meetings": MEETINGS, "release": RELEASE, "dev": DEV, "weekly": WEEKLY,
          "chat_recent": {"at": TS, "spaces": {}}, "_demo": True}
    if "--print" in sys.argv:
        print(json.dumps(st, ensure_ascii=False, indent=1)[:2000]); return
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)
    print("demo: 已寫入 %s(未讀 %d、工單 %d、會議 %d、產品 %d)" % (
        STATE, sum(r["unread"] for r in IMMEDIATE["rows"]), len(MINE_ALL),
        len(MEETINGS["today"]), len(DEV["products"])))


if __name__ == "__main__":
    main()
