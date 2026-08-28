# -*- coding: utf-8 -*-
"""駕駛艙 collector② v2:我的單 + 代追蹤單(config/jira_watch.json)。
判斷層:①過濾自動化留言(🤖/自動初步分類/app 帳號)②「需回應」=最後一則人類留言非我
且帶請求語氣或提及我;其餘歸「留言更新」低干擾桶。標題去前綴(產品/平台進欄位,不佔內容)。
score→sev 三檔(3急/2高/1一般);含 duedate/逾期。寫 state.jira(含 sig 供已閱判定)。唯讀。"""
import sys, io, os, re, json, time, base64, hashlib, datetime, urllib.parse, urllib.request

if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
else:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
sys.path.insert(0, r"<REPO_ROOT>/2_Toolkit/Input/1D/Jira")
import jira as J

AUTH = base64.b64encode(("%s:%s" % (J.EMAIL, J.TOKEN)).encode()).decode()
ME = "ACCOUNT_ID_PLACEHOLDER"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.expanduser("~/.config/agent_cockpit/state.json")
WATCHCFG = os.path.join(HERE, "..", "config", "jira_watch.json")

AWAIT = ("等候驗收", "待驗收", "等待驗收")
FEATURES = [
    (r"\bUI\b|版面|設計稿|介面|新方案", "畫面/UI"),   # 改畫面/UI 類(owner 2026-08-28 加);放最前免被功能詞搶走
    ("直播|聊天室|語音|Agora", "聊天室/直播"), ("K線|線圖|走勢|清盤|副圖", "K線/圖表"),
    ("名單|篩選|成交量|健診|選股", "名單/篩選"), ("登入|TestFlight|權限|OAuth|登出", "登入/權限"),
    ("推播|通知|紅點", "推播/通知"), ("講義|下載", "講義/下載"),
    ("crash|閃退|Crash|當機|DNS|WebSocket|閃退", "穩定性"), ("陪跑|導購|LP|彈窗", "行銷/導購"),
]
ASK_PAT = re.compile(r"[?？]|請(?!假)|麻煩|提供|確認|需要|補一下|補個|可以嗎|幫忙|如何|哪個|嗎\b")
BOT_PAT = re.compile(r"^\s*🤖|自動初步分類|automation for jira|署名[:：]\s*GPT|信心值|Codex|Claude", re.I)
BOT_NAMES = re.compile(r"Claw|bot|Bot|自動|AI助理|agent", re.I)


def api(path, params=None):
    url = J.SITE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": "Basic " + AUTH, "Accept": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=45).read())


def adf_text(n):
    if isinstance(n, dict):
        if n.get("type") == "text": return n.get("text", "")
        return "".join(adf_text(c) for c in n.get("content", []))
    if isinstance(n, list): return "".join(adf_text(c) for c in n)
    return ""


def clean_title(s):
    t = re.sub(r"^(\s*(【[^】]*】|\[[^\]]*\]))+\s*", "", s)                      # 【BUG】【iOS-Product A】…
    t = re.sub(r"^(研究|分析|實作)[-—:：]\s*", "", t)
    t = re.sub(r"^(iOS|Android|雙平台|Web)?[-–]?(Product B形態學|Product A|Product A|Product B)[-–]?(APP|App)?\s*", "", t)
    return (t or s).strip()


def product_of(f):
    par = f.get("parent") or {}
    # 版本欄位(fixVersions/versions)名稱本身就寫產品,如「Product D_iOS_2.5.0」——最強訊號,先看
    vers = " ".join(v.get("name", "") for v in (f.get("fixVersions") or []) + (f.get("versions") or []))
    text = vers + " " + f.get("summary", "") + " " + par.get("key", "") + " " + \
           (par.get("fields") or {}).get("summary", "") + " " + \
           " ".join(c["name"] for c in f.get("components", []))
    if "Product B" in text or "Product B" in text or "ProductB" in text: return "Product B"
    if "TICKET-1000" in text or "Product A" in text: return "Product A"
    if "Product D" in text or "放風箏" in text: return "Product D"      # Product D=Product D,與Product C是兩個作者(owner 2026-08-28 糾正)
    if "Product C" in text or "動能" in text: return "Product C"
    return "其他"


def platform_of(f):
    names = [c["name"] for c in f.get("components", [])]
    s = f.get("summary", "") + " " + ((f.get("parent") or {}).get("fields") or {}).get("summary", "")
    if re.search(r"雙平台", s): return "雙平台"
    if re.search(r"後端|Back-?End", s) or "Back-End" in names: return "後端"
    has_i = "iOS_RD" in names or re.search(r"iOS", s)
    has_a = "Android_RD" in names or re.search(r"Android", s)
    if has_i and has_a: return "雙平台"
    if has_i: return "iOS"
    if has_a: return "Android"
    return "其他"


def feature_of(s):
    for pat, name in FEATURES:
        if re.search(pat, s, re.I): return name
    return "其他"


def hours_since(iso):
    try:
        t = datetime.datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")
        return round((datetime.datetime.now() - t).total_seconds() / 3600, 1)
    except Exception:
        return None


def human_comments(key, n=2):
    """回最近 n 則『人類、非自動化』留言(新→舊);無=[]。"""
    out = []
    try:
        c = api("/rest/api/3/issue/%s/comment" % key, {"maxResults": 6, "orderBy": "-created"})
        for cm in c.get("comments", []):
            if len(out) >= n: break
            if cm["author"].get("accountType") != "atlassian": continue        # app/bot 帳號
            if BOT_NAMES.search(cm["author"].get("displayName", "")): continue  # agent 帳號(Edith_Claw 等)
            txt = adf_text(cm.get("body"))
            if BOT_PAT.search(txt): continue                                   # 🤖 自動分類等
            out.append({"by": cm["author"].get("displayName", "?"),
                    "by_id": cm["author"].get("accountId", ""),
                    "at": cm.get("created", "")[:16], "stale_h": hours_since(cm.get("created", "")),
                    "text": txt[:800],
                    "asks": bool(ASK_PAT.search(txt)) or (ME in json.dumps(cm.get("body", {})))})
    except Exception:
        pass
    return out


def last_human_comment(key):
    hs = human_comments(key, 2)
    return hs[0] if hs else None


def fetch(jql, cap=150):
    issues, token = [], None
    while True:
        params = {"jql": jql, "maxResults": 100,
                  "fields": "summary,status,updated,components,parent,duedate,fixVersions,versions,issuetype"}
        if token: params["nextPageToken"] = token
        d = api("/rest/api/3/search/jql", params)
        issues += d.get("issues", [])
        token = d.get("nextPageToken")
        if not token or len(issues) >= cap: break
    return issues


def to_row(it):
    f = it["fields"]
    due = f.get("duedate") or ""
    overdue = bool(due) and due < datetime.date.today().isoformat()
    typ = (f.get("issuetype") or {}).get("name", "")
    raw = f.get("summary", "")
    is_bug = bool(re.search(r"bug|錯誤|故障|缺陷", typ, re.I) or re.search(r"【\s*(BUG|QA)\s*】|\bQA\b", raw, re.I))
    return {"key": it["key"], "title": clean_title(raw), "raw": raw, "type": typ, "is_bug": is_bug,
            "status": f["status"]["name"], "updated": f.get("updated", ""),
            "stale_h": hours_since(f.get("updated", "")),
            "product": product_of(f), "platform": platform_of(f),
            "feature": feature_of(raw + " " + ((f.get("parent") or {}).get("fields") or {}).get("summary", "")),
            "due": due, "overdue": overdue, "url": J.SITE + "/browse/" + it["key"]}


def sev_of(r, bucket):
    s = 50 + (20 if bucket == "await" else 0) + (15 if bucket == "need" else 0)
    sh = (r.get("lc") or {}).get("stale_h") if bucket == "need" else r.get("stale_h")
    if sh and sh > 4: s += 15
    if r["overdue"]: s += 20
    if re.search(r"閃退|crash|當機", r["raw"], re.I): s += 10
    if "作者" in r["raw"] or "本人" in r["raw"]: s += 8
    r["score"] = min(100, s)
    r["sev"] = 3 if s >= 85 else (2 if s >= 70 else 1)


def main():
    # ── 我的單 ──
    mine = [to_row(it) for it in fetch("cf[10059] = currentUser() AND statusCategory != Done ORDER BY updated DESC")]
    awaiting = [r for r in mine if any(a in r["status"] for a in AWAIT)]
    rest = [r for r in mine if r not in awaiting]
    need, info = [], []
    for r in rest[:40]:
        hs = human_comments(r["key"], 2)
        lc = hs[0] if hs else None
        if lc and lc["by_id"] != ME:
            r["lc"] = lc
            if len(hs) > 1: r["lc2"] = hs[1]
            (need if lc["asks"] else info).append(r)
    for r in awaiting: sev_of(r, "await")
    for r in need: sev_of(r, "need")
    for r in info: sev_of(r, "info")

    # ── 代追蹤(watch) ──
    watches = []
    try: wcfg = json.load(open(WATCHCFG, encoding="utf-8"))["watches"]
    except Exception: wcfg = []
    for w in wcfg:
        if not w.get("enabled"): continue
        rows = [to_row(it) for it in fetch('cf[10059] = "%s" AND statusCategory != Done ORDER BY updated DESC' % w["owner_accountId"])]
        pf = w.get("product_filter")
        if pf: rows = [r for r in rows if r["product"] == pf]
        for r in rows:
            hs = human_comments(r["key"], 2)
            lc = hs[0] if hs else None
            if lc:
                r["lc"] = lc
                if len(hs) > 1: r["lc2"] = hs[1]
            if any(a in r["status"] for a in AWAIT):
                r["bucket"] = "await"
            elif lc and lc.get("asks") and lc.get("by_id") != w["owner_accountId"]:
                r["bucket"] = "need"
            else:
                r["bucket"] = "other"
            sev_of(r, r["bucket"] if r["bucket"] in ("await", "need") else "info")
        order = {"await": 0, "need": 1, "other": 2}
        rows.sort(key=lambda r: (order[r["bucket"]], -(r.get("score", 0))))
        watches.append({"id": w["id"], "label": w["label"], "rows": rows, "note": w.get("note", "")})

    # ── 已修正追蹤:上輪在列、這輪消失的鍵 → 問 Jira 是否真完成 → 進 fixed 帳本(供隔日會報;可一鍵清除)──
    LEDG = os.path.expanduser("~/.config/agent_cockpit/prev_rows.json")
    FIXEDF = os.path.expanduser("~/.config/agent_cockpit/fixed.json")
    all_rows = {r["key"]: r for r in mine}
    for w in watches:
        for r in w["rows"]: all_rows.setdefault(r["key"], r)
    try: prev = json.load(open(LEDG, encoding="utf-8"))
    except Exception: prev = {}
    try: fixed = json.load(open(FIXEDF, encoding="utf-8"))
    except Exception: fixed = []
    fixed_keys = {f["key"] for f in fixed}
    gone = [k for k in prev if k not in all_rows and k not in fixed_keys][:25]
    if gone:
        try:
            done = fetch("key in (%s) AND statusCategory = Done" % ",".join(gone), cap=30)
            for it in done:
                p = prev.get(it["key"]) or {}
                f = it.get("fields") or {}
                fixed.append({"key": it["key"], "title": p.get("title") or clean_title(f.get("summary", "")),
                              "what": p.get("what", ""), "product": p.get("product", "其他"),
                              "platform": p.get("platform", "其他"), "feature": p.get("feature", "其他"),
                              "status": ((f.get("status") or {}).get("name") or "完成"),
                              "url": "https://your-org.atlassian.net/browse/" + it["key"],
                              "is_bug": p.get("is_bug", False),
                              "fixed_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        except Exception as e:
            print("fixed-check err:", e)
    fixed = fixed[-100:]
    json.dump(fixed, open(FIXEDF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    snap = {k: {kk: r.get(kk) for kk in ("title", "what", "product", "platform", "feature", "is_bug")}
            for k, r in all_rows.items()}
    json.dump(snap, open(LEDG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    g = lambda rs: sorted(rs, key=lambda r: (r["product"], r["platform"], r["feature"], -r["score"]))
    awaiting, need, info = g(awaiting), g(need), g(info)
    sig = hashlib.md5(json.dumps(
        [[r["key"], r["updated"]] for r in awaiting + need], sort_keys=True).encode()).hexdigest()[:10]

    st = {}
    try: st = json.load(open(STATE, encoding="utf-8"))
    except Exception: pass
    st["jira"] = {"scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"), "sig": sig,
                  "await": awaiting, "need": need, "info": info,
                  "watches": watches, "total_open": len(mine),
                  "fixed": fixed,     # 已修正(原在列的單完成了;渲染端依 fixed_cleared_at 過濾)
                  "mine_all": mine}   # 功能視圖用:我的全部開放單(含沒留言的;lc 旗標已掛在同物件上)
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)
    print("jira: open=%d await=%d need=%d info=%d watch=%s" %
          (len(mine), len(awaiting), len(need), len(info),
           ",".join("%s:%d" % (w["id"], len(w["rows"])) for w in watches) or "-"))


if __name__ == "__main__":
    main()
