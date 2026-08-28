# -*- coding: utf-8 -*-
"""駕駛艙 collector⑤:開發進度——每產品(config/goals.json):
①monorepo 該路徑 7 天 commits+最新一筆 ②活躍 codex lane(.codex-work mtime<48h)
③Codex 對照目標產「當前步驟+進度%(估)+依據」,快取 by 該路徑 HEAD。寫 state.dev。唯讀。"""
import sys, io, os, json, time, hashlib, subprocess, datetime

if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
else:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = r"<REPO_ROOT>"
STATE = os.path.expanduser("~/.config/agent_cockpit/state.json")
CACHE = os.path.expanduser("~/.config/agent_cockpit/dev_cache.json")
GOALS = json.load(open(os.path.join(HERE, "..", "config", "goals.json"), encoding="utf-8"))["products"]
NOWIN = 0x08000000 if os.name == "nt" else 0


def git(args):
    r = subprocess.run(["git", "-C", ROOT] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=30, creationflags=NOWIN)
    return (r.stdout or "").strip()


def codex(prompt):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run(["cmd", "/c", "codex", "exec", "--skip-git-repo-check", "-"],
                       input=prompt, text=True, encoding="utf-8", errors="replace",
                       capture_output=True, timeout=150,
                       cwd=os.path.expanduser("~/.config/agent_cockpit"), env=env, creationflags=NOWIN)
    return r.stdout or ""


def lanes_for(keys):
    base = os.path.join(ROOT, ".codex-work")
    out = []
    try:
        now = time.time()
        for d in os.listdir(base):
            p = os.path.join(base, d)
            if not os.path.isdir(p): continue
            if not any(k in d.lower() for k in keys): continue
            age_h = (now - os.path.getmtime(p)) / 3600
            if age_h < 48: out.append({"name": d, "age_h": round(age_h, 1)})
    except OSError:
        pass
    return sorted(out, key=lambda x: x["age_h"])[:5]


def jira_slice(prod):
    """該 App 的 Jira 現況(從 state 撈,不另打 API):進行中/待驗收/要回覆/本週完成。"""
    try: st = json.load(open(STATE, encoding="utf-8"))
    except Exception: return {}
    j = st.get("jira") or {}
    rows = {r["key"]: r for r in (j.get("mine_all") or [])}
    for w in (j.get("watches") or []):
        for r in (w.get("rows") or []): rows.setdefault(r["key"], r)
    mine = [r for r in rows.values() if r.get("product") == prod]
    need = [r for r in (j.get("need") or []) if r.get("product") == prod]
    fixed = [r for r in (j.get("fixed") or []) if r.get("product") == prod]
    pick = lambda a, n: [(r.get("what") or r.get("title", ""))[:48] for r in a][:n]
    return {"開放單數": len(mine),
            "等候驗收": pick([r for r in mine if "驗收" in (r.get("status") or "")], 5),
            "進行中": pick([r for r in mine if "進行" in (r.get("status") or "") or "Review" in (r.get("status") or "")], 5),
            "待辦": pick([r for r in mine if "待辦" in (r.get("status") or "") or "Pending" in (r.get("status") or "")], 5),
            "要回覆": pick(need, 3),
            "近期完成": pick(fixed, 5)}


def release_slice(app):
    try: st = json.load(open(STATE, encoding="utf-8"))
    except Exception: return {}
    a = ((st.get("release") or {}).get("apps") or {}).get(app) or {}
    g = lambda k: (a.get(k) or {}).get("ver")
    return {"iOS線上": g("ios_live"), "Android線上": g("android_live"),
            "iOS可送審": g("ios_review"), "Android可送審": g("android_review")}


def main():
    try: cache = json.load(open(CACHE, encoding="utf-8"))
    except Exception: cache = {}
    prods = []
    for g in GOALS:
        paths = g.get("paths") or []
        head = git(["log", "-1", "--format=%H"] + ["--"] + paths) if paths else ""
        n7 = git(["rev-list", "--count", "--since=7.days"] + ["HEAD", "--"] + paths) if paths else "0"
        last = git(["log", "-1", "--format=%ci|%s", "--"] + paths) if paths else ""
        last_at, _, last_msg = last.partition("|")
        subjects = (git(["log", "--since=7.days", "--format=%s", "--"] + paths).split("\n")[:30]
                    if paths else [])
        lanes = lanes_for(g.get("lane_keys") or [])
        # 併入其他機器的 lane 回報(A 機開發 Product B,本機只看得到同步過的 repo)
        remote_note = g.get("remote", "")
        try:
            sdir = os.path.join(HERE, "..", "state")
            mine_m = (open(os.path.join(ROOT, "MACHINE"), encoding="utf-8").read().strip().split() or ["?"])[0][:8]
            for fn in os.listdir(sdir):
                if not fn.startswith("lanes_") or not fn.endswith(".json"): continue
                d = json.load(open(os.path.join(sdir, fn), encoding="utf-8"))
                if d.get("machine") == mine_m: continue
                keys = g.get("lane_keys") or []
                for l in d.get("lanes", []):
                    if keys and any(k in l["name"].lower() for k in keys):
                        lanes.append({**l, "name": "[%s] %s" % (d["machine"], l["name"])})
                c2 = (d.get("commits") or {}).get(g["id"]) or {}
                if c2.get("n7"):
                    remote_note = "%s機 7天 %d commits · 最新「%s」(%s)" % (
                        d.get("machine", "?"), c2["n7"], c2.get("last_msg", "")[:40], c2.get("last_at", ""))
        except Exception:
            pass
        jira = jira_slice(g.get("jira_product") or "")
        rel = release_slice(g.get("release_app") or "")
        row = {"id": g["id"], "name": g["name"], "goal": g["goal"],
               "commits7d": int(n7 or 0), "last_at": last_at[:16], "last_msg": last_msg[:60],
               "lanes": lanes, "remote": remote_note, "jira": jira, "release": rel}
        # 快取簽章:程式碼 HEAD + Jira 現況(沒有 repo 的 App 靠 Jira 變動觸發重算)
        sig = hashlib.md5(json.dumps([head, jira, rel], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:10]
        c = cache.get(g["id"]) or {}
        if c.get("sig") == sig and "why" in c:
            row.update({k: c.get(k, "") for k in ("step", "pct", "basis", "why", "next")})
        elif subjects or jira.get("開放單數"):
            prompt = ("你是 PM 助理。請用下列材料寫出這個 App 的**全景**,讓沒跟進的人也看得懂。\n"
                      "App:%s\n目標:%s\n"
                      "最近 7 天程式異動(新→舊,沒有代表本機無 repo):\n%s\n"
                      "Jira 現況:%s\n版本狀態:%s\n\n"
                      "輸出 JSON(繁中,無其他文字):\n"
                      "{\"why\":\"為何在做這些——這個 App 現在的處境與要解的問題(≤40字)\","
                      "\"step\":\"現在正在做什麼(≤24字)\","
                      "\"next\":\"接下來要做什麼——具體動作+對象(≤30字)\","
                      "\"pct\":\"對照目標的完成度估計(整數%%,標『估』,如 估72%%)\","
                      "\"basis\":\"估計依據一句(≤30字)\"}"
                      % (g["name"], g["goal"], "\n".join("- " + x for x in subjects if x) or "(無)",
                         json.dumps(jira, ensure_ascii=False), json.dumps(rel, ensure_ascii=False)))
            out = codex(prompt)
            try:
                got = json.loads(out[out.find("{"): out.rfind("}") + 1])
            except Exception:
                got = {}
            row.update({"step": got.get("step", "")[:40], "pct": got.get("pct", "")[:8],
                        "basis": got.get("basis", "")[:40], "why": got.get("why", "")[:60],
                        "next": got.get("next", "")[:50]})
            cache[g["id"]] = {"sig": sig, "head": head,
                              **{k: row.get(k, "") for k in ("step", "pct", "basis", "why", "next")}}
        prods.append(row)
    tmp = CACHE + ".tmp"
    json.dump(cache, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, CACHE)

    st = {}
    try: st = json.load(open(STATE, encoding="utf-8"))
    except Exception: pass
    st["dev"] = {"scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"), "products": prods}
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)
    for p in prods:
        print("dev %s: %s commits7d | %s %s | lanes=%d" %
              (p["name"], p["commits7d"], p.get("pct", ""), p.get("step", ""), len(p["lanes"])))


if __name__ == "__main__":
    main()
