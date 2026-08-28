# -*- coding: utf-8 -*-
"""駕駛艙寫入動作(唯一會改 Jira 的元件;只在使用者按下按鈕時被呼叫)。
用法(輸出一律 JSON 一行):
  py jira_action.py transitions <KEY>              # 可切換到哪些狀態
  py jira_action.py transition  <KEY> <TRANS_ID>   # 切換狀態
  py jira_action.py comment     <KEY> <文字>        # 留言;文字內「@某人」自動轉成 Jira 真 mention
mention=ADF {"type":"mention","attrs":{"id":accountId,"text":"@顯示名"}}——只有這種才會通知本人;
純文字「@名字」在 Jira 上只是字串(看起來像 tag 其實沒 tag 到)。名字→accountId 走 user search,
找不到就整段留原文並在回傳標 unresolved,不假裝 tag 成功。"""
import sys, io, os, re, json, base64, urllib.parse, urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, r"<REPO_ROOT>/2_Toolkit/Input/1D/Jira")
import jira as J

AUTH = base64.b64encode(("%s:%s" % (J.EMAIL, J.TOKEN)).encode()).decode()
H = {"Authorization": "Basic " + AUTH, "Accept": "application/json", "Content-Type": "application/json"}
MENTION_RE = re.compile(r"@([A-Za-z0-9_\u4e00-\u9fff.\-]{2,30})")


def api(path, params=None, data=None, method=None):
    url = J.SITE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=H, method=method or ("POST" if body else "GET"))
    r = urllib.request.urlopen(req, timeout=45)
    raw = r.read()
    return json.loads(raw) if raw else {}


def find_user(name):
    """名字/暱稱 → accountId。先精確比對 displayName,再前綴。"""
    try:
        us = api("/rest/api/3/user/search", {"query": name, "maxResults": 20})
    except Exception:
        return None
    n = name.lower().replace("_", "").replace(" ", "")
    def norm(u): return (u.get("displayName") or "").lower().replace("_", "").replace(" ", "")
    for u in us:
        if norm(u) == n: return u
    for u in us:
        if n and n in norm(u): return u
    return us[0] if us else None


def adf(text):
    """純文字 → ADF;@名字 轉成 mention node(查不到就留原文)。"""
    unresolved, content = [], []
    for line in text.split("\n"):
        nodes, pos = [], 0
        for m in MENTION_RE.finditer(line):
            if m.start() > pos:
                nodes.append({"type": "text", "text": line[pos:m.start()]})
            u = find_user(m.group(1))
            if u:
                nodes.append({"type": "mention",
                              "attrs": {"id": u["accountId"], "text": "@" + u.get("displayName", m.group(1))}})
            else:
                unresolved.append(m.group(1))
                nodes.append({"type": "text", "text": m.group(0)})
            pos = m.end()
        if pos < len(line):
            nodes.append({"type": "text", "text": line[pos:]})
        content.append({"type": "paragraph", "content": nodes or [{"type": "text", "text": " "}]})
    return {"type": "doc", "version": 1, "content": content}, unresolved


def main():
    op = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if op == "transitions":
            d = api("/rest/api/3/issue/%s/transitions" % sys.argv[2])
            out = [{"id": t["id"], "name": t["name"],
                    "to": (t.get("to") or {}).get("name", "")} for t in d.get("transitions", [])]
            print(json.dumps({"ok": True, "transitions": out}, ensure_ascii=False))
        elif op == "transition":
            api("/rest/api/3/issue/%s/transitions" % sys.argv[2], data={"transition": {"id": sys.argv[3]}})
            d = api("/rest/api/3/issue/%s" % sys.argv[2], {"fields": "status"})
            print(json.dumps({"ok": True, "status": ((d.get("fields") or {}).get("status") or {}).get("name", "")},
                             ensure_ascii=False))
        elif op == "comment":
            body, unresolved = adf(" ".join(sys.argv[3:]))
            d = api("/rest/api/3/issue/%s/comment" % sys.argv[2], data={"body": body})
            print(json.dumps({"ok": True, "id": d.get("id"), "unresolved": unresolved,
                              "mentions": sum(1 for p in body["content"] for n in p.get("content", [])
                                              if n.get("type") == "mention")}, ensure_ascii=False))
        elif op == "whois":     # 驗證用:名字能不能解析成真 mention 對象
            u = find_user(sys.argv[2])
            print(json.dumps({"ok": bool(u), "displayName": (u or {}).get("displayName"),
                              "accountId": (u or {}).get("accountId")}, ensure_ascii=False))
        elif op == "preview":   # 驗證用:看 ADF 會長怎樣(不送出)
            body, unresolved = adf(" ".join(sys.argv[2:]))
            print(json.dumps({"ok": True, "unresolved": unresolved, "adf": body}, ensure_ascii=False))
        else:
            print(json.dumps({"ok": False, "err": "usage: transitions|transition|comment|whois|preview"}, ensure_ascii=False))
    except urllib.error.HTTPError as e:
        print(json.dumps({"ok": False, "err": "HTTP %s %s" % (e.code, e.read().decode("utf-8", "replace")[:300])},
                         ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "err": str(e)[:300]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
