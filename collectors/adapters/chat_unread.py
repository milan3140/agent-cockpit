# -*- coding: utf-8 -*-
"""駕駛艙 collector①:Chat 未讀掃描(每 5 分)。
真未讀=spaces.readState(lastReadTime) vs 訊息 createTime;scope 不足時退化=水位線(上次掃描後的新訊息)。
輸出:~/.config/agent_cockpit/state.json 的 immediate 區(原子寫)。唯讀、絕不標已讀、絕不發訊。
用法: py chat_unread.py [--once]   (排程每 5 分呼叫)
"""
import sys, io, os, json, time, subprocess, urllib.parse, urllib.request, urllib.error

if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
else:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "..", "config", "spaces.json"), encoding="utf-8"))
SELF_USER = CFG.get("self_user", "")   # owner 自己的 Chat user id:自己發的不算未讀
TOKF = os.path.expanduser("~/.config/gws-chat/token.json")
STATE_DIR = os.path.expanduser("~/.config/agent_cockpit")
STATE = os.path.join(STATE_DIR, "state.json")
READSTATE_SCOPE = "https://www.googleapis.com/auth/chat.users.readstate.readonly"


def access_token():
    c = json.load(open(TOKF, encoding="utf-8"))
    # 把 readstate scope 寫進 scope 欄(騎上 selfheal 的「聯集重授權」:下次自癒自動帶上)
    if READSTATE_SCOPE not in (c.get("scope") or ""):
        c["scope"] = (c.get("scope", "") + " " + READSTATE_SCOPE).strip()
        tmp = TOKF + ".tmp"
        json.dump(c, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, TOKF)
    d = urllib.parse.urlencode({"client_id": c["client_id"], "client_secret": c["client_secret"],
                                "refresh_token": c["refresh_token"], "grant_type": "refresh_token"}).encode()
    return json.loads(urllib.request.urlopen("https://oauth2.googleapis.com/token", data=d, timeout=20).read())["access_token"]


def api(tok, path):
    req = urllib.request.Request("https://chat.googleapis.com/v1/" + path,
                                 headers={"Authorization": "Bearer " + tok})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def read_state_time(tok, space):
    """回該房 lastReadTime(ISO)或 None(scope 不足/未支援)。"""
    try:
        rs = api(tok, "users/me/spaces/%s/spaceReadState" % space)
        return rs.get("lastReadTime")
    except urllib.error.HTTPError:
        return None


def recent_messages(tok, space, limit=25):
    q = urllib.parse.urlencode({"pageSize": limit, "orderBy": "createTime desc"})
    try:
        return api(tok, "spaces/%s/messages?%s" % (space, q)).get("messages", [])
    except urllib.error.HTTPError as e:
        return [{"_error": "HTTP %s" % e.code}]


RELEV_CACHE = os.path.join(STATE_DIR, "relevance_cache.json")
NOWIN = 0x08000000 if os.name == "nt" else 0


def judge_relevance(ent, unread):
    """relevance_filter 房:未讀逐則交 Codex 判相關(結果快取 by 訊息 name,判過不重判)。
    回 (留下的訊息, 濾掉數)。判斷失敗=fail-open(當相關、不入快取,下輪重判)——寧噪音不吞訊。"""
    try: cache = json.load(open(RELEV_CACHE, encoding="utf-8"))
    except Exception: cache = {}
    new = [m for m in unread if m.get("name") and m["name"] not in cache]
    if new:
        lines = []
        for i, m in enumerate(new):
            snd = (m.get("sender") or {}).get("name", "").split("/")[-1][-6:]
            lines.append("%d. [%s] %s" % (i, snd, (m.get("text") or "(附件/卡片)")[:300]))
        prompt = ("你是 PM owner 的訊息過濾器。判斷規則:%s\n\n以下每則訊息,只留「相關」的編號。訊息:\n%s\n\n"
                  "只輸出 JSON,無其他文字:{\"relevant\":[編號...]}(全部無關就 {\"relevant\":[]})"
                  % (ent.get("relevance_rule", ""), "\n".join(lines)))
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run(["cmd", "/c", "codex", "exec", "--skip-git-repo-check", "-"],
                               input=prompt, text=True, encoding="utf-8", errors="replace",
                               capture_output=True, timeout=120,
                               cwd=os.path.expanduser("~/.config/agent_cockpit"), env=env, creationflags=NOWIN)
            out = r.stdout or ""
            keep = set(json.loads(out[out.find("{"): out.rfind("}") + 1])["relevant"])
            for i, m in enumerate(new):
                cache[m["name"]] = i in keep
        except Exception:
            pass   # 失敗:new 不入快取 → 下面 cache.get 預設 True(fail-open)
        cache = dict(list(cache.items())[-300:])
        tmp = RELEV_CACHE + ".tmp"
        json.dump(cache, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, RELEV_CACHE)
    kept = [m for m in unread if cache.get(m.get("name"), True)]
    return kept, len(unread) - len(kept)


def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}


def save_state(st):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


def main():
    tok = access_token()
    st = load_state()
    wm = st.get("immediate_wm") or {}   # space -> 上次掃描時最新訊息 createTime(退化模式水位線)
    me_reply_hint = None
    rows = []
    readstate_ok = None
    for ent in CFG["immediate"]:
        sp, label, prio = ent["space"], ent["label"], ent["priority"]
        msgs = recent_messages(tok, sp)
        if msgs and msgs[0].get("_error"):
            rows.append({"space": sp, "label": label, "priority": prio, "error": msgs[0]["_error"],
                         "unread": None, "mode": "error"})
            continue
        lrt = read_state_time(tok, sp)
        if readstate_ok is None:
            readstate_ok = lrt is not None
        if lrt:
            unread = [m for m in msgs if (m.get("createTime", "") > lrt)]
            mode = "readstate"
        else:
            base = wm.get(sp, "")
            unread = [m for m in msgs if (m.get("createTime", "") > base)] if base else []
            mode = "watermark"
        if msgs:
            wm[sp] = max(wm.get(sp, ""), msgs[0].get("createTime", ""))
        # 自己發的訊息不算未讀也不進預覽(owner:重點是看別人傳什麼給我)
        if SELF_USER:
            unread = [m for m in unread if (m.get("sender") or {}).get("name") != SELF_USER]
        filtered_out = 0
        if ent.get("relevance_filter") and unread:
            unread, filtered_out = judge_relevance(ent, unread)
        preview = []
        for m in unread[:10]:
            snd = (m.get("sender") or {}).get("name", "").split("/")[-1]
            preview.append({"t": (m.get("createTime") or "")[11:16],
                            "sender_tail": snd[-4:],
                            "text": (m.get("text") or "(附件/卡片)")[:200]})
        rows.append({"space": sp, "label": label, "priority": prio, "kind": ent["kind"],
                     "unread": len(unread), "filtered_out": filtered_out, "mode": mode, "preview": preview,
                     "url": ("https://chat.google.com/room/%s" % sp) if ent["kind"] == "room"
                            else ("https://chat.google.com/dm/%s" % sp)})
    rows.sort(key=lambda r: (r["priority"], -(r["unread"] or 0)))
    st["immediate"] = {"scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "readstate_scope": bool(readstate_ok), "rows": rows}
    # 近期對話快照(給 jira_enrich 判「需回覆是否已在 Chat 處理」):每房最近 15 則、雙向都留
    recent = {}
    for ent in CFG["immediate"]:
        sp, label = ent["space"], ent["label"]
        msgs = recent_messages(tok, sp, 15)
        if msgs and msgs[0].get("_error"): continue
        recent[label] = [{"t": (m.get("createTime") or "")[5:16],
                          "sender_tail": (m.get("sender") or {}).get("name", "").split("/")[-1][-4:],
                          "text": (m.get("text") or "")[:200]} for m in msgs if m.get("text")]
    st["chat_recent"] = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "spaces": recent}
    st["immediate_wm"] = wm
    save_state(st)
    total = sum(r["unread"] or 0 for r in rows)
    print("scanned %d spaces | unread=%s | mode=%s" %
          (len(rows), total, "readstate" if readstate_ok else "watermark(退化;重授權後升級)"))
    for r in rows:
        if r.get("unread"):
            print("  [P%d] %s: %d" % (r["priority"], r["label"], r["unread"]))


if __name__ == "__main__":
    main()
