# -*- coding: utf-8 -*-
"""駕駛艙 collector②b:Codex 語意總結——對佇列中每張單產「這單是什麼(what)/需要你做什麼(need)」一句話。
快取按 issue updated 時戳,單沒動不重算;一次批呼叫(省 token)。寫回 state.jira 的 rows。
LLM=codex exec(headless,吃登入態免金鑰;Windows 要 UTF-8,見 KB 本地程式接LLM筆記)。"""
import sys, io, os, json, time, base64, subprocess, urllib.parse, urllib.request

if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
else:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
sys.path.insert(0, r"<REPO_ROOT>/2_Toolkit/Input/1D/Jira")
import jira as J

AUTH = base64.b64encode(("%s:%s" % (J.EMAIL, J.TOKEN)).encode()).decode()
STATE = os.path.expanduser("~/.config/agent_cockpit/state.json")
CACHE = os.path.expanduser("~/.config/agent_cockpit/enrich.json")


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


def codex(prompt):
    """headless codex exec;回 stdout 文字。中性 cwd、UTF-8。"""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    cwd = os.path.expanduser("~/.config/agent_cockpit")
    r = subprocess.run(["cmd", "/c", "codex", "exec", "--skip-git-repo-check", "-"],
                       input=prompt, text=True, encoding="utf-8", errors="replace",
                       capture_output=True, timeout=180, cwd=cwd, env=env)
    return (r.stdout or "") + ("" if r.returncode == 0 else "\n[rc=%s]%s" % (r.returncode, (r.stderr or "")[-200:]))


def main():
    st = json.load(open(STATE, encoding="utf-8"))
    j = st.get("jira") or {}
    watch_rows = [r for w in (j.get("watches") or []) for r in (w.get("rows") or [])]
    seen = {}
    for r in (j.get("await") or []) + (j.get("need") or []) + watch_rows \
             + (j.get("info") or []) + (j.get("mine_all") or []):   # 功能視圖要每張都有故事
        seen.setdefault(r["key"], r)
    rows = list(seen.values())
    if not rows:
        print("enrich: queue empty"); return
    try: cache = json.load(open(CACHE, encoding="utf-8"))
    except Exception: cache = {}

    # Chat 近況(判「已在 Chat 處理」);快照時戳進 sig:對話更新就重判
    chat = st.get("chat_recent") or {}
    chat_at = (chat.get("at") or "")[:13]
    def stale(r):
        c = cache.get(r["key"]) or {}
        return c.get("sig") != r["updated"] or "story" not in c or "feat" not in c or c.get("chat_at") != chat_at \
            or (r.get("product") == "其他" and "app" not in c) \
            or (r.get("platform") == "其他" and "plat" not in c) \
            or (((r.get("lc") or {}).get("asks")) and "needs_reply" not in c)
    todo = [r for r in rows if stale(r)]
    if todo:
        # 撈描述+最近真人留言(供總結)
        packs = []
        for r in todo[:20]:
            desc = ""
            try:
                d = api("/rest/api/3/issue/%s" % r["key"], {"fields": "description"})
                desc = adf_text(d["fields"].get("description"))[:500]
            except Exception: pass
            packs.append({"key": r["key"], "title": r["raw"], "status": r["status"],
                          "due": r.get("due", ""), "desc": desc,
                          "last_comment": (r.get("lc") or {}).get("text", ""),
                          "comment_by": (r.get("lc") or {}).get("by", "")})
        prompt = (
            "你是 PM 助理。以下是幾張 Jira 單(JSON)。對每張輸出三欄,繁體中文:\n"
            "what=這單在做什麼(≤20字,講具體功能與問題,別複述單號/平台前綴)\n"
            "need=現在需要 owner(PM)做什麼(≤24字,動詞開頭,要具體:驗收什麼行為/回覆什麼問題/提供什麼資訊。"
            "若最後留言是 RD 提問,need 要直指該問題)\n"
            "story=完整敘述(80~120字,3~4句,給 PM 的全景:①背景與要解的問題②目前進度/RD 做了或說了什麼③卡點或待決事項。白話,別逐字抄描述)\n"
            "app=所屬產品,從標題/描述判斷:Product A(定存股)/Product B(Product B)/Product C(動能App)/Product D(Product D;與Product C是不同作者)/判不出留空字串,**禁止「其他」**\n"
            "plat=平台,從標題/描述判斷影響哪端:iOS/Android/雙平台/後端 四選一;純設計稿或資料建置類歸「雙平台」;真判不出留空\n"
            "feat=功能類別(≤7字):優先從【K線/圖表、聊天室/直播、名單/篩選、登入/權限、推播/通知、講義/下載、穩定性、行銷/導購、"
            "內購/訂閱、行情資料、審核/上架、官網、後台/工具、畫面/UI】挑(改版面/UI/設計稿/新方案畫面=畫面/UI);都不合就取該單具體功能名(如 畫圖工具、美顏濾鏡),**禁止輸出「其他」**\n"
            "needs_reply=true/false——看 last_comment:它是否**真的需要 PM 回覆/決策/提供資訊**"
            "(直接提問、要 PM 驗收確認、等 PM 給資料=true;純技術補充、根因記錄、進度說明、自問自答=false)\n"
            "answered_in_chat=true/false——比對下方〈近期 Chat 對話〉:若 RD 在單上問的事,owner 已在 Chat 裡回覆過/雙方已談定,設 true。"
            "拿不準=false。evidence=若 true,一句話指出是哪段對話(≤30字)\n"
            "只輸出 JSON:{\"KEY\":{\"what\":\"…\",\"need\":\"…\",\"story\":\"…\",\"answered_in_chat\":false,\"evidence\":\"\"},…},無其他文字。\n\n"
            "〈Jira 單〉\n" + json.dumps(packs, ensure_ascii=False)
            + "\n\n〈近期 Chat 對話(各房最近訊息,新→舊;sender_tail 為發言者 id 尾碼)〉\n"
            + json.dumps(chat.get("spaces") or {}, ensure_ascii=False)[:9000])
        out = codex(prompt)
        # 抓最後一個 JSON 物件
        try:
            s0, s1 = out.rfind("{\""), out.rfind("}")
            got = json.loads(out[out.rindex("{", 0, s0 + 1) if False else out.find("{"): s1 + 1]) \
                if s1 > 0 else {}
        except Exception:
            got = {}
        if not got:  # 寬鬆再試:掃每行找 JSON
            import re
            m = re.search(r"\{[\s\S]*\}", out)
            try: got = json.loads(m.group(0)) if m else {}
            except Exception: got = {}
        n = 0
        for r in todo:
            g = got.get(r["key"])
            if g and g.get("need"):
                cache[r["key"]] = {"sig": r["updated"], "what": g.get("what", "")[:40],
                                   "feat": (g.get("feat") or "")[:14], "app": (g.get("app") or "")[:10],
                                   "plat": (g.get("plat") or "")[:6],
                                   "needs_reply": bool(g.get("needs_reply", True)),
                                   "need": g.get("need", "")[:48], "story": g.get("story", "")[:400],
                                   "answered": bool(g.get("answered_in_chat")),
                                   "evidence": (g.get("evidence") or "")[:60],
                                   "chat_at": chat_at, "at": time.strftime("%m-%d %H:%M")}
                n += 1
        tmp = CACHE + ".tmp"
        json.dump(cache, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, CACHE)
        print("enrich: llm updated %d/%d (raw %d chars)" % (n, len(todo), len(out)))
    else:
        print("enrich: all cached")

    # 合併進 state
    st = json.load(open(STATE, encoding="utf-8"))  # 重讀防競寫
    j = st.get("jira") or {}
    def apply(r):
        c = cache.get(r["key"])
        if not c: return
        r["what"], r["need"], r["story"] = c["what"], c["need"], c.get("story", "")
        if r.get("feature") == "其他":
            if c.get("feat") and c["feat"] != "其他":
                r["feature"] = c["feat"]   # regex 沒認出的,用 AI 類別;命中的保持穩定
            else:
                r["feature"] = "待補需求"   # AI 也判不出=單本身沒內容,這就是它的類別(要 PM 補)
        if r.get("product") == "其他" and c.get("app") and c["app"] != "其他":
            r["product"] = c["app"]
        if r.get("platform") == "其他" and c.get("plat") in ("iOS", "Android", "雙平台", "後端"):
            r["platform"] = c["plat"]
    for bucket in ("await", "need", "info", "mine_all", "fixed"):   # fixed 帳本也要帶 AI 分類(快照在 enrich 前拍)
        for r in j.get(bucket) or []: apply(r)
    for w in j.get("watches") or []:
        for r in w.get("rows") or []: apply(r)
    # 已在 Chat 處理的/留言其實不需要回的 → 移出「需回覆」,進 info(判斷:Jira×Chat 交叉+語意)
    keep, moved = [], []
    for r in j.get("need") or []:
        c = cache.get(r["key"]) or {}
        if c.get("answered"):
            r["chat_done"] = c.get("evidence") or "已在 Chat 處理"
            moved.append(r)
        elif c.get("needs_reply") is False:
            r["chat_done"] = "留言為資訊補充,無需回覆"
            moved.append(r)
        else:
            keep.append(r)
    for w in j.get("watches") or []:   # watch 的要回覆同樣降級
        for r in w.get("rows") or []:
            c = cache.get(r["key"]) or {}
            if r.get("bucket") == "need" and c.get("needs_reply") is False:
                r["bucket"] = "other"
    if moved:
        j["need"] = keep
        j["info"] = (j.get("info") or []) + moved
        print("enrich: %d 張已在 Chat 處理,移出需回覆" % len(moved))
    st["jira"] = j
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)
    print("enrich: merged")


if __name__ == "__main__":
    main()
