# -*- coding: utf-8 -*-
"""駕駛艙 collector③:今日 Calendar → 會議清單+每會要準備的東西(config/meetings.json 對應)。
用 gws-chat token(scope 已含 calendar.readonly)。寫 state.json 的 meetings 區。唯讀。"""
import sys, io, os, json, re, time, datetime, urllib.parse, urllib.request

if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
else:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
TOKF = os.path.expanduser("~/.config/gws-chat/token.json")
STATE = os.path.expanduser("~/.config/agent_cockpit/state.json")
MEETCFG = os.path.join(HERE, "..", "config", "meetings.json")


def access_token():
    c = json.load(open(TOKF, encoding="utf-8"))
    d = urllib.parse.urlencode({"client_id": c["client_id"], "client_secret": c["client_secret"],
                                "refresh_token": c["refresh_token"], "grant_type": "refresh_token"}).encode()
    return json.loads(urllib.request.urlopen("https://oauth2.googleapis.com/token", data=d, timeout=20).read())["access_token"]


def main():
    cfg = []
    try: cfg = json.load(open(MEETCFG, encoding="utf-8"))["recurring"]
    except Exception: pass
    tok = access_token()
    today = datetime.date.today()
    tmin = "%sT00:00:00+08:00" % today.isoformat()
    tmax = "%sT23:59:59+08:00" % today.isoformat()
    q = urllib.parse.urlencode({"timeMin": tmin, "timeMax": tmax, "singleEvents": "true",
                                "orderBy": "startTime", "maxResults": 20})
    req = urllib.request.Request("https://www.googleapis.com/calendar/v3/calendars/primary/events?" + q,
                                 headers={"Authorization": "Bearer " + tok})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())
    rows = []
    for ev in d.get("items", []):
        if ev.get("status") == "cancelled": continue
        start = (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date", "")
        end = (ev.get("end") or {}).get("dateTime") or ""
        title = ev.get("summary", "(無標題)")
        row = {"start": start, "end": end, "title": title,
               "meet": (ev.get("hangoutLink") or ""),
               "attendees": len(ev.get("attendees") or [])}
        atts = ev.get("attachments") or []
        rec = next((a for a in atts if "紀錄" in (a.get("title") or "") or "Notes" in (a.get("title") or "")
                    or "記錄" in (a.get("title") or "") or (a.get("mimeType") or "").endswith("document")), None)
        if rec:
            row["record"] = {"title": rec.get("title", "會議紀錄"), "url": rec.get("fileUrl", "")}
        for rc in cfg:
            if re.search(rc["match"], title):
                row["prep"] = rc.get("prep", ""); row["doc"] = rc.get("doc", "")
                break
        rows.append(row)
    nxt = ""
    now = datetime.datetime.now().astimezone()
    for r in rows:
        try:
            st_dt = datetime.datetime.fromisoformat(r["start"])
            if st_dt > now: nxt = r["start"]; break
        except Exception: pass

    st = {}
    try: st = json.load(open(STATE, encoding="utf-8"))
    except Exception: pass
    st["meetings"] = {"scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"), "today": rows, "next_start": nxt}
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)
    print("meetings: %d today, next=%s" % (len(rows), nxt or "-"))


if __name__ == "__main__":
    main()
