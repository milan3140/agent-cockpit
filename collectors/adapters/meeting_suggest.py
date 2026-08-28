# -*- coding: utf-8 -*-
"""駕駛艙 collector⑦:Chat「要約時間」→ 行事曆建議卡。
掃 immediate 各房近 48h 別人發的訊息 → Codex 判是否在約會議/問有沒有空,解析時間(Asia/Taipei)/與會者/議題
→ 行事曆衝堂實查(events.list 該時段) → state.suggestions。快取 by 訊息 name(每則只判一次)。
建立事件由 widget 一鍵(main.js calendar_create),本檔唯讀。"""
import sys, io, os, re, json, time, datetime, subprocess, urllib.parse, urllib.request

if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
else:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "..", "config", "spaces.json"), encoding="utf-8"))
SELF = CFG.get("self_user", "")
STATE = os.path.expanduser("~/.config/agent_cockpit/state.json")
CACHE = os.path.expanduser("~/.config/agent_cockpit/suggest_cache.json")
TOKF = os.path.expanduser("~/.config/gws-chat/token.json")
NOWIN = 0x08000000 if os.name == "nt" else 0
TZ = datetime.timezone(datetime.timedelta(hours=8))


def token():
    c = json.load(open(TOKF, encoding="utf-8"))
    d = urllib.parse.urlencode({"client_id": c["client_id"], "client_secret": c["client_secret"],
                                "refresh_token": c["refresh_token"], "grant_type": "refresh_token"}).encode()
    return json.loads(urllib.request.urlopen("https://oauth2.googleapis.com/token", data=d, timeout=20).read())["access_token"]


def api(tok, url):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def codex(prompt):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run(["cmd", "/c", "codex", "exec", "--skip-git-repo-check", "-"],
                       input=prompt, text=True, encoding="utf-8", errors="replace",
                       capture_output=True, timeout=180,
                       cwd=os.path.expanduser("~/.config/agent_cockpit"), env=env, creationflags=NOWIN)
    return r.stdout or ""


def to_local(iso):
    try:
        return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ)
    except Exception:
        return None


def main():
    try: cache = json.load(open(CACHE, encoding="utf-8"))
    except Exception: cache = {}
    tok = token()
    now = datetime.datetime.now(TZ)
    since = now - datetime.timedelta(hours=48)
    cands = []
    for ent in CFG["immediate"]:
        sp = ent["space"]
        try:
            d = api(tok, "https://chat.googleapis.com/v1/spaces/%s/messages?%s" % (
                sp, urlencode({"pageSize": 30, "orderBy": "createTime desc"})))
        except Exception:
            continue
        for m in d.get("messages", []):
            snd = (m.get("sender") or {})
            if snd.get("name") == SELF or snd.get("type") == "BOT": continue
            at = to_local(m.get("createTime", ""))
            if not at or at < since: continue
            txt = (m.get("text") or "").strip()
            if len(txt) < 6: continue
            cands.append({"id": m["name"], "space": sp, "room": ent["label"], "url": ent.get("url") or
                          ("https://chat.google.com/room/%s" % sp if ent["kind"] == "room" else "https://chat.google.com/dm/%s" % sp),
                          "from": snd.get("name", "").split("/")[-1][-4:], "at": at.strftime("%Y-%m-%dT%H:%M"),
                          "text": txt[:400]})
    todo = [c for c in cands if c["id"] not in cache]
    if todo:
        prompt = ("你是 PM 助理。下面是 Google Chat 訊息(JSON,at=台北時間)。對每則判斷:是不是在**約會議/約時間/問有沒有空/要開會討論**"
                  "(純進度回報、感謝、公告=否)。是的話解析:title(會議主題≤20字)、start(依訊息時間推算的台北時間 YYYY-MM-DDTHH:MM,"
                  "無明確時間留空字串)、duration_min(預設30)、attendees(提到的人名/暱稱陣列)、agenda(要談什麼≤40字)。\n"
                  "只輸出 JSON:{\"<id>\":{\"invite\":true/false,\"title\":\"\",\"start\":\"\",\"duration_min\":30,\"attendees\":[],\"agenda\":\"\"},…}\n\n"
                  "今天=%s\n〈訊息〉\n%s" % (now.strftime("%Y-%m-%d %A"), json.dumps(todo, ensure_ascii=False)))
        out = codex(prompt)
        m = re.search(r"\{[\s\S]*\}", out)
        try: got = json.loads(m.group(0)) if m else {}
        except Exception: got = {}
        for c in todo:
            g = got.get(c["id"]) or {"invite": False}
            cache[c["id"]] = {"invite": bool(g.get("invite")), "title": str(g.get("title", ""))[:40],
                              "start": str(g.get("start", ""))[:16], "duration_min": int(g.get("duration_min") or 30),
                              "attendees": [str(x)[:20] for x in (g.get("attendees") or [])][:8],
                              "agenda": str(g.get("agenda", ""))[:80], "judged_at": now.strftime("%Y-%m-%d %H:%M")}
        cache = {k: v for k, v in list(cache.items())[-300:]}
        tmp = CACHE + ".tmp"
        json.dump(cache, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, CACHE)
    items = []
    for c in cands:
        g = cache.get(c["id"]) or {}
        if not g.get("invite"): continue
        it = {**c, **{k: g[k] for k in ("title", "start", "duration_min", "attendees", "agenda")}}
        it["end"] = ""
        it["conflicts"] = []
        if it["start"]:
            try:
                s = datetime.datetime.strptime(it["start"], "%Y-%m-%dT%H:%M").replace(tzinfo=TZ)
                e = s + datetime.timedelta(minutes=it["duration_min"])
                it["end"] = e.strftime("%Y-%m-%dT%H:%M")
                ev = api(tok, "https://www.googleapis.com/calendar/v3/calendars/primary/events?" + urlencode(
                    {"timeMin": s.isoformat(), "timeMax": e.isoformat(), "singleEvents": "true", "maxResults": 10}))
                it["conflicts"] = [x.get("summary", "(無標題)")[:30] for x in ev.get("items", [])
                                   if x.get("status") != "cancelled"]
            except Exception:
                pass
        items.append(it)
    items.sort(key=lambda x: x["at"], reverse=True)
    st = {}
    try: st = json.load(open(STATE, encoding="utf-8"))
    except Exception: pass
    st["suggestions"] = {"at": now.strftime("%Y-%m-%d %H:%M:%S"), "items": items}
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)
    print("suggest: 候選 %d, 新判 %d, 建議 %d" % (len(cands), len(todo), len(items)))


def urlencode(q):
    return urllib.parse.urlencode(q)


if __name__ == "__main__":
    main()
