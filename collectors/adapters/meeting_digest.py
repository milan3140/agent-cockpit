# -*- coding: utf-8 -*-
"""駕駛艙 collector⑥ v3:會議紀錄產出 + 萃取。
來源=cmmeeting(公司會議 AI:錄影→逐字稿+投影片判讀),經 Conductor MCP 取 get_meeting(彙整/決議/待辦)
與 get_transcript(逐字稿全文)。Codex 產兩層:
  ①全景(overview):整場在談什麼、逐節重點、決策、待辦——**不管關不關 owner 的事都要寫**,讓他理解全景。
  ②我的段落(mine):與 owner/Product B Web/Product ABot/VIP2 相關的需求/決策/待辦(可空)。
產物=格式清楚的 HTML 會議紀錄,統一存 1_Projects/會議紀錄/YYYY-MM-DD_主題.html(含逐字稿摺疊)。
快取 by (meeting id, status);state.meetings.today[].digest 帶 html 路徑供面板開啟。唯讀外部系統。"""
import sys, io, os, re, json, time, html, subprocess

if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
else:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")

STATE = os.path.expanduser("~/.config/agent_cockpit/state.json")
CACHE = os.path.expanduser("~/.config/agent_cockpit/meeting_digest.json")
CONDUCTOR = os.path.expanduser("~/.claude/skills/conductor/scripts/conductor.py")
RECDIR = r"<REPO_ROOT>\1_Projects\會議紀錄"
NOWIN = 0x08000000 if os.name == "nt" else 0
FOCUS = "owner(Owner)本人、Product B 可轉債(Product B Web/Product B)、Product A Bot、VIP2 看板 3/4"
GLOSS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", "glossary.json")


def glossary_text():
    """名詞對照表:逐字稿的口語簡稱/音譯錯字→正式名(如 NRU=Product E Web)。"""
    try:
        g = json.load(open(GLOSS, encoding="utf-8"))
    except Exception:
        return ""
    rows = []
    for sec, label in (("products", "產品"), ("people", "人"), ("terms", "術語")):
        for it in g.get(sec, []):
            al = "、".join(it.get("aliases") or [])
            extra = it.get("note") or it.get("role") or ""
            rows.append("- [%s] %s ← %s%s" % (label, it["canonical"], al or "(無別名)",
                                              ("；" + extra) if extra else ""))
    mc = g.get("meeting_context")
    if mc:
        rows.append("\n〈會議進行方式(用『誰在講』交叉驗證這段屬於哪個產品)〉")
        rows.append("型態:" + str(mc.get("型態", "")))
        for pm, prods in (mc.get("PM負責產品") or {}).items():
            rows.append("- PM %s 負責:%s" % (pm, "、".join(prods)))
        rows.append("- RD 角色:" + "、".join("%s=%s" % (k, v) for k, v in (mc.get("RD角色") or {}).items()))
        rows.append("- 發言順序:" + str(mc.get("發言順序", "")))
    return "\n".join(rows)


def conductor(tool, args):
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    r = subprocess.run(["py", CONDUCTOR, "access", "--resource", "cmmeeting", "--action", "invoke",
                        "--tool", tool, "--args", json.dumps(args, ensure_ascii=False)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=120, env=env, creationflags=NOWIN)
    d = json.loads(r.stdout)
    return json.loads(d["data"][0]["text"][0])


def codex(prompt):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run(["cmd", "/c", "codex", "exec", "--skip-git-repo-check", "-"],
                       input=prompt, text=True, encoding="utf-8", errors="replace",
                       capture_output=True, timeout=300,
                       cwd=os.path.expanduser("~/.config/agent_cockpit"), env=env, creationflags=NOWIN)
    return r.stdout or ""


def norm(s):
    return re.sub(r"[\s（）()、,，\-–—:：]", "", s or "").lower()


def hhmm(sec):
    try: sec = int(sec)
    except Exception: return ""
    return "%02d:%02d" % (sec // 60, sec % 60)


def jira_pool():
    """給 Codex 校對會議內容的單池。**不能只放 owner 自己追的單**——立會會過其他 PM(PM-1/PM-2)的產品,
    只餵自己的單會全部對不上。故:本機 state 的單(有 AI 摘要,品質好)+ 全產線近 10 天更新的單(JQL)。

    ★邊界(owner 2026-08-28 要求):**這批單只進 prompt,絕不寫回 state.jira**——維運面板的
    await/need/mine_all/watches 全由 jira_mine.py 產生,本檔只寫 meetings[].digest,不碰 jira 區,
    所以其他 PM 的單不會污染你的追蹤面板;它們只以「會議段落對到的單號」形式出現在會議紀錄裡。"""
    rows = {}
    try:
        st = json.load(open(STATE, encoding="utf-8"))
        j = st.get("jira") or {}
        for r in (j.get("mine_all") or []): rows[r["key"]] = r
        for w in (j.get("watches") or []):
            for r in (w.get("rows") or []): rows.setdefault(r["key"], r)
        for r in (j.get("fixed") or []): rows.setdefault(r["key"], {**r, "status": "已完成"})
    except Exception:
        pass
    out = [{"key": r.get("key"), "t": (r.get("what") or r.get("title", ""))[:44],
            "s": (r.get("status") or "")[:10], "p": r.get("product", ""), "plat": r.get("platform", "")}
           for r in rows.values()]
    try:   # 全產線近況(含其他 PM 的單)
        import base64, urllib.parse, urllib.request
        sys.path.insert(0, r"<REPO_ROOT>/2_Toolkit/Input/1D/Jira")
        import jira as J
        auth = base64.b64encode(("%s:%s" % (J.EMAIL, J.TOKEN)).encode()).decode()
        jql = ('project in (PROJ, OPS, COMMON) AND updated >= -10d '
               'AND statusCategory != Done ORDER BY updated DESC')
        req = urllib.request.Request(
            J.SITE + "/rest/api/3/search/jql?" + urllib.parse.urlencode(
                {"jql": jql, "maxResults": 120, "fields": "summary,status"}),
            headers={"Authorization": "Basic " + auth, "Accept": "application/json"})
        d = json.loads(urllib.request.urlopen(req, timeout=45).read())
        have = {x["key"] for x in out}
        for it in d.get("issues", []):
            if it["key"] in have: continue
            f = it.get("fields") or {}
            s = f.get("summary", "")
            out.append({"key": it["key"], "t": re.sub(r"^【[^】]*】\s*", "", s)[:44],
                        "s": ((f.get("status") or {}).get("name") or "")[:10],
                        "p": "", "plat": "", "raw": s[:60]})
    except Exception as e:
        print("jira_pool JQL fail:", str(e)[:100])
    return out[:220]


def analyze(title, report_md, transcript, decisions, actions):
    """Codex:全景(不論是否與我有關)+我的段落。"""
    lines = ["[%s] %s: %s" % (hhmm(t.get("start_time_seconds")), t.get("speaker", "?"), t.get("text", ""))
             for t in transcript]
    body = "\n".join(lines)[:30000]
    prompt = (
        "你是資深 PM 助理。以下是一場公司會議的**逐字稿**(含講者與時間)與 AI 彙整報告。請產出:\n"
        "① overview_summary: 整場在談什麼(2~3 句,主軸與結論走向)\n"
        "② **apps: 按「討論到的 App／產品」分段**(這是重點——一場立會會跨多個產品,要拆開讓人看懂各自狀況)。\n"
        "   每個 App 一段:{\"app\":\"產品正式名。**一個作者可能有多個 App**(如Product E旗下有 Product E／Product F／Product G),"
        "要寫成『作者-App名』如『Product F』,不可只寫作者名混為一談;同一 App 只能有一段,跨平台議題不同就寫"
        "『作者-App名(平台)』;跨多產品的共用議題才寫『跨產品』\","
        "\"why\":\"**為何討論這件事**——背景與要解的問題(≤45字)\","
        "\"what\":\"**結論要做什麼**——收斂出的做法或決定(≤45字)\","
        "\"points\":[\"補充細節(≤50字)\",…最多3],\"who\":\"主導的 PM(可加 RD)\","
        "\"status\":\"這個 App 目前處境一句(如 待開單/等驗收/卡在後端;≤20字)\","
        "\"tickets\":[{\"key\":\"TICKET-1000\",\"t\":\"單標題(≤24字)\",\"s\":\"該單目前狀態\",\"rel\":\"這張單與本段的關係(≤16字,如 就是在講這張/會議說要開但已存在/相關待驗收)\"},…最多5]} 最多10段\n"
        "   **逐字稿講到的每個產品都要有一段,寧可某段只有一兩句也不要漏**(漏掉=使用者以為那個 App 沒被討論)。\n"
        "★**Jira 校對(重要)**:下面附〈Jira 現況〉=owner 追蹤的單 + 全產線近 10 天更新的未完成單(含其他 PM 的)。"
        "raw 欄是原始標題(含【平台-作者】前綴),可用來判斷那張單屬於哪個作者/App。請用它:\n"
        "   (a) 把每段對應到真實單號填進 tickets——**只能從清單裡挑,絕不可捏造單號**;找不到就給空陣列。\n"
        "   (b) 用單的標題與狀態**校正逐字稿的模糊講法**(逐字稿是口語,Jira 標題才精確);兩者衝突時以 Jira 為準並在 points 註明。\n"
        "   (c) 會議說「要開單」但清單裡已有對應單 → 在 points 寫「已有單 XXX-123,不需重開」;\n"
        "       會議說「已完成/待驗收」但單還在待辦 → 在 points 標出這個落差。\n"
        "   規則:**每段都要有 why 與 what**,只有結論沒有為何=不合格;會議沒講的別編,寫「逐字稿未交代」。\n"
        "③ decisions: 全場決議 [\"…(≤50字)\"] 最多8\n"
        "④ actions: 全場待辦 [{\"what\":\"要做什麼(≤40字)\",\"who\":\"負責人\"}] 最多8\n"
        "⑤ 與【%s】相關的部分(可空):mine_summary(≤40字;整場無關就寫「本場無 owner 直接相關事項」)、"
        "mine_needs / mine_decisions / mine_todos 各最多5條(≤36字)\n"
        "只輸出 JSON,無其他文字:\n"
        "{\"overview_summary\":\"\",\"apps\":[],\"decisions\":[],\"actions\":[],"
        "\"mine_summary\":\"\",\"mine_needs\":[],\"mine_decisions\":[],\"mine_todos\":[]}\n\n"
        "★校對規則:逐字稿是語音轉文字,簡稱與音譯常錯。下面〈名詞對照表〉左邊是正式名、右邊是會出現的講法,"
        "**輸出一律用正式名**(例:講「NRU」指的是Product E Web,不是別的系統);表上沒有的專有名詞保留原文別亂改。\n"
        "★歸屬規則:立會是 PM 逐一跟 RD 對進度,**發言者就是最強的產品歸屬訊號**——某段由哪位 PM 主導發言,"
        "那段就歸他負責的產品(對照表附了 PM↔產品分工);RD 只是回答者不決定歸屬。"
        "若逐字稿內容與分工衝突,以內容為準但在該段 points 註明。每段的 who 請填**主導的 PM**(可加 RD)。\n"
        "〈名詞對照表〉\n%s\n\n"
        "〈Jira 現況(key/標題/狀態/產品/平台)〉\n%s\n\n"
        "〈會議〉%s\n〈AI 彙整報告〉\n%s\n\n〈逐字稿〉\n%s" %
        (FOCUS, glossary_text(), json.dumps(jira_pool(), ensure_ascii=False),
         title, (report_md or "")[:6000], body))
    out = codex(prompt)
    m = re.search(r"\{[\s\S]*\}", out)
    try: g = json.loads(m.group(0)) if m else {}
    except Exception: g = {}
    lim = lambda a, n, c: [x for x in (a or [])][:n]
    return {"overview_summary": str(g.get("overview_summary", ""))[:300],
            "apps": lim(g.get("apps"), 10, 0),
            "sections": lim(g.get("sections"), 6, 0),   # 舊欄位相容(v3 前的快取)
            "decisions": [str(x)[:80] for x in lim(g.get("decisions"), 8, 0)],
            "actions": lim(g.get("actions"), 8, 0),
            "mine_summary": str(g.get("mine_summary", ""))[:80],
            "mine_needs": [str(x)[:60] for x in lim(g.get("mine_needs"), 5, 0)],
            "mine_decisions": [str(x)[:60] for x in lim(g.get("mine_decisions"), 5, 0)],
            "mine_todos": [str(x)[:50] for x in lim(g.get("mine_todos"), 5, 0)]}


def alias_hints():
    """逐字稿就地註記用:只挑「看了不知道是什麼」的別名(不是正式名的子字串,如 NRU／Tyrus／期貨大作用),
    長度>=3 免得中文短詞誤標;回 [(別名, 正式名)] 依長度降冪(先長後短,避免子字串互吃)。"""
    try:
        g = json.load(open(GLOSS, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for sec in ("products", "terms"):
        for it in g.get(sec, []):
            canon = it["canonical"]
            for al in (it.get("aliases") or []):
                if len(al) >= 3 and al not in canon:
                    out.append((al, canon))
    return sorted(out, key=lambda x: -len(x[0]))


CSS = """:root{--bg:#faf8f5;--ink:#2b2320;--ink2:#6b5f57;--ink3:#9a8d84;--hair:#e5ded6;--accent:#a5502b;--card:#fff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.75 "Noto Sans TC","Microsoft JhengHei",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:860px;margin:0 auto;padding:48px 24px 80px}
h1{font-size:26px;font-weight:700;letter-spacing:.01em;margin:0 0 6px}
.meta{color:var(--ink3);font-size:13px;margin-bottom:32px}
h2{font-size:13px;font-weight:700;letter-spacing:.14em;color:var(--ink2);margin:38px 0 12px;
padding-bottom:8px;border-bottom:1px solid var(--hair)}
.lead{font-size:16px;line-height:1.85}
.sec{margin:22px 0}.sec .t{font-weight:700;font-size:15px}.sec .w{color:var(--ink3);font-size:12px;margin-left:8px;font-weight:400}
.sec .wy,.sec .wt{margin-top:4px;font-size:14.5px}.sec .wy b,.sec .wt b{color:var(--accent);font-weight:700;font-size:12px;letter-spacing:.06em}
ul{margin:6px 0 0;padding-left:20px}li{margin:4px 0}
.mine{background:var(--card);border-left:3px solid var(--accent);padding:16px 20px;margin:14px 0;border-radius:0 6px 6px 0}
.mine h3{font-size:12px;letter-spacing:.1em;color:var(--accent);margin:14px 0 4px;font-weight:700}
.mine h3:first-child{margin-top:0}
.who{color:var(--ink3);font-size:12px}
table.tk{margin-top:8px;font-size:13px}table.tk a{color:var(--accent);text-decoration:none}
table.tk a:hover{text-decoration:underline}
table{border-collapse:collapse;width:100%;font-size:14px}td{padding:6px 10px;border-bottom:1px solid var(--hair);vertical-align:top}
td.n{color:var(--ink3);width:110px;white-space:nowrap}
details{margin-top:12px}summary{cursor:pointer;color:var(--ink2);font-size:13px}
.tx{margin-top:12px;font-size:13.5px;line-height:1.9;color:var(--ink2)}
.tx .sp{color:var(--accent);font-weight:600}.tx .ts{color:var(--ink3);font-size:12px;margin-right:6px}
.tx .al{border-bottom:1px dotted var(--accent)}.tx .alx{color:var(--accent);font-size:12px}
@media(prefers-color-scheme:dark){:root{--bg:#1c1815;--ink:#f0ebe4;--ink2:#b9ada3;--ink3:#8a7d73;--hair:#332b26;--card:#241f1b;--accent:#d68f6a}}"""


def build_html(meta, ana, participants, transcript):
    e = html.escape
    parts = []
    parts.append("<!doctype html><meta charset='utf-8'><title>%s</title><style>%s</style>" %
                 (e(meta["title"]), CSS))
    parts.append("<div class='wrap'><h1>%s</h1><div class='meta'>%s · 主持 %s · %d 人與會 · 由逐字稿統整(%s)</div>" %
                 (e(meta["title"]), e(meta["date"]), e(meta.get("host", "")), len(participants),
                  time.strftime("%Y-%m-%d %H:%M")))
    if ana["overview_summary"]:
        parts.append("<h2>會議全景</h2><div class='lead'>%s</div>" % e(ana["overview_summary"]))
    if ana.get("apps"):
        parts.append("<h2>各產品狀況</h2>")
        for s in ana["apps"]:
            pts = "".join("<li>%s</li>" % e(str(p)) for p in (s.get("points") or []))
            tk = "".join(
                "<tr><td class='n'><a href='https://your-org.atlassian.net/browse/%s' target='_blank'>%s</a></td>"
                "<td>%s<span class='who'>　%s%s</span></td></tr>" % (
                    e(str(t.get("key", ""))), e(str(t.get("key", ""))), e(str(t.get("t", ""))),
                    e(str(t.get("s", ""))), ("　·　" + e(str(t.get("rel")))) if t.get("rel") else "")
                for t in (s.get("tickets") or []))
            parts.append(
                "<div class='sec'><div class='t'>%s<span class='w'>%s%s</span></div>"
                "<div class='wy'><b>為何討論</b>：%s</div>"
                "<div class='wt'><b>結論要做什麼</b>：%s</div>%s%s</div>" % (
                    e(str(s.get("app", ""))), e(str(s.get("who", ""))),
                    ("　·　" + e(str(s.get("status")))) if s.get("status") else "",
                    e(str(s.get("why", "逐字稿未交代"))), e(str(s.get("what", "逐字稿未交代"))),
                    ("<ul>%s</ul>" % pts) if pts else "",
                    ("<table class='tk'>%s</table>" % tk) if tk else ""))
    elif ana.get("sections"):
        parts.append("<h2>逐節重點</h2>")
        for s in ana["sections"]:
            parts.append("<div class='sec'><div class='t'>%s<span class='w'>%s</span></div><ul>%s</ul></div>" % (
                e(str(s.get("topic", ""))), e(str(s.get("who", ""))),
                "".join("<li>%s</li>" % e(str(p)) for p in (s.get("points") or []))))
    if ana["decisions"]:
        parts.append("<h2>決議</h2><ul>%s</ul>" % "".join("<li>%s</li>" % e(d) for d in ana["decisions"]))
    if ana["actions"]:
        parts.append("<h2>待辦</h2><table>%s</table>" % "".join(
            "<tr><td class='n'>%s</td><td>%s</td></tr>" % (e(str(a.get("who", "—"))), e(str(a.get("what", ""))))
            for a in ana["actions"]))
    mine = []
    if ana["mine_summary"]: mine.append("<div class='lead'>%s</div>" % e(ana["mine_summary"]))
    for label, key in (("需求／被要求的事", "mine_needs"), ("決策", "mine_decisions"), ("我的待辦", "mine_todos")):
        if ana[key]:
            mine.append("<h3>%s</h3><ul>%s</ul>" % (label, "".join("<li>%s</li>" % e(x) for x in ana[key])))
    if mine:
        parts.append("<h2>與我相關</h2><div class='mine'>%s</div>" % "".join(mine))
    if participants:
        parts.append("<h2>與會者</h2><div class='who'>%s</div>" % e("、".join(participants)))
    if transcript:
        # 逐字稿保留原文(它是證據),但把難懂的簡稱/音譯就地加註正式名,讀原文也不會誤解
        hints = alias_hints()
        def mark(txt):
            s2 = e(str(txt))
            for al, canon in hints:
                if al in s2:
                    s2 = s2.replace(al, "<span class='al' title='%s'>%s</span><span class='alx'>（%s）</span>"
                                    % (e(canon), al, e(canon)), 1)
            return s2
        rows = "".join("<div><span class='ts'>%s</span><span class='sp'>%s</span> %s</div>" % (
            hhmm(t.get("start_time_seconds")), e(str(t.get("speaker", ""))), mark(t.get("text", "")))
            for t in transcript)
        parts.append("<details><summary>完整逐字稿(%d 句)</summary><div class='tx'>%s</div></details>" %
                     (len(transcript), rows))
    parts.append("</div>")
    return "".join(parts)


def main():
    try: st = json.load(open(STATE, encoding="utf-8"))
    except Exception: return
    rows = (st.get("meetings") or {}).get("today") or []
    today = time.strftime("%Y-%m-%d")
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%S")
    ended = [r for r in rows if (r.get("end") or "")[:19] < now_iso and r.get("attendees", 0) >= 2]
    if not ended:
        print("digest: 今日尚無已結束會議"); return
    try: cache = json.load(open(CACHE, encoding="utf-8"))
    except Exception: cache = {}
    try:
        lst = conductor("list_meetings", {"from": today, "to": today, "limit": 50}).get("meetings", [])
    except Exception as e:
        print("digest: cmmeeting list fail", e); lst = []
    os.makedirs(RECDIR, exist_ok=True)
    n_llm, n_hit = 0, 0
    for r in ended:
        hit = next((m for m in lst if norm(m.get("title")) == norm(r.get("title"))), None) \
            or next((m for m in lst if norm(r.get("title"))[:8] and norm(r.get("title"))[:8] in norm(m.get("title"))), None)
        if not hit: continue
        if not hit.get("report_ready"):
            r["digest"] = {"pending": True, "src": "cmmeeting", "mid": hit["id"]}
            continue
        n_hit += 1
        ck = "cm:%s" % hit["id"]
        c = cache.get(ck) or {}
        # 版本字串要隨「萃取語意/校對表」改動推進,否則舊快取把新結果擋在外面(KB:渲染語意改了要推進版本)
        sig = "%s|%s|v11-allpm" % (hit.get("status"), hit.get("report_ready"))
        if c.get("sig") != sig:
            try:
                mt = conductor("get_meeting", {"id": hit["id"]})
            except Exception as e:
                print("digest: get_meeting fail", hit["id"], e); continue
            try:
                tr = conductor("get_transcript", {"id": hit["id"]}).get("transcript") or []
            except Exception as e:
                print("digest: transcript fail(用彙整報告)", e); tr = []
            rep = ((mt.get("report") or {}).get("content_md")) or ""
            ana = analyze(r.get("title", ""), rep, tr, mt.get("decisions"), mt.get("action_items"))
            meta = {"title": r.get("title", ""), "date": (r.get("start") or "")[:16].replace("T", " "),
                    "host": (mt.get("meeting") or {}).get("host", "")}
            safe = re.sub(r"[\\/:*?\"<>|]", "_", meta["title"])[:40]
            fp = os.path.join(RECDIR, "%s_%s.html" % (today, safe))
            open(fp, "w", encoding="utf-8").write(
                build_html(meta, ana, mt.get("participants") or [], tr))
            cache[ck] = {"sig": sig, "at": time.strftime("%m-%d %H:%M"), "mid": hit["id"],
                         "html": fp, "n_tx": len(tr), **ana}
            n_llm += 1
            c = cache.get(ck)
        if c:
            r["digest"] = {"src": "cmmeeting", "mid": c.get("mid"), "at": c.get("at"), "html": c.get("html"),
                           "overview_summary": c.get("overview_summary", ""),
                           "apps": c.get("apps", []),
                           "sections": c.get("sections", []), "decisions": c.get("decisions", []),
                           "actions": c.get("actions", []), "mine_summary": c.get("mine_summary", ""),
                           "mine_needs": c.get("mine_needs", []), "mine_decisions": c.get("mine_decisions", []),
                           "mine_todos": c.get("mine_todos", [])}
    tmp = CACHE + ".tmp"
    json.dump(cache, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, CACHE)
    st2 = json.load(open(STATE, encoding="utf-8"))
    for r2 in (st2.get("meetings") or {}).get("today") or []:
        src = next((r for r in ended if r.get("start") == r2.get("start") and r.get("digest")), None)
        if src: r2["digest"] = src["digest"]
    tmp = STATE + ".tmp"
    json.dump(st2, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)
    print("digest: 已結束 %d 場, cmmeeting 配到 %d, 產紀錄 %d → %s" % (len(ended), n_hit, n_llm, RECDIR))


if __name__ == "__main__":
    main()
