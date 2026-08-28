# -*- coding: utf-8 -*-
"""駕駛艙 collector⑧:AI 週報草稿(Codex 產,可續談)。
材料四源:①素材帳本進行中卡 ②本週會議紀錄萃取(meeting_digest 快取) ③本週 Jira 完成單(fixed 帳本)
④本週 vault 異動(1_Projects/4_Memory 的 git commits)。
交 codex exec --json 產 3~5 件事的週報草稿(Context/Hypothesis/Progress/Key Decision 四欄,格式見
weekly-report skill 與 MA週報/定義與判準.md),存 1_Projects/MA週報/週報草稿_YYYY-MM-DD.md;
**記下 thread_id** → 面板「與 Codex 討論」= codex resume <thread_id>,可直接改稿。
用法:py weekly_draft.py [--force](預設同一週已產過就不重跑)"""
import sys, io, os, re, json, time, datetime, subprocess

if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
else:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")

ROOT = r"<REPO_ROOT>"
WRDIR = os.path.join(ROOT, "1_Projects", "MA週報")
STATE = os.path.expanduser("~/.config/agent_cockpit/state.json")
MDCACHE = os.path.expanduser("~/.config/agent_cockpit/meeting_digest.json")
FIXEDF = os.path.expanduser("~/.config/agent_cockpit/fixed.json")
NOWIN = 0x08000000 if os.name == "nt" else 0
TZ = datetime.timezone(datetime.timedelta(hours=8))


def week_start(now):
    d = now - datetime.timedelta(days=now.weekday())
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def git(args, cwd=ROOT):
    r = subprocess.run(["git", "-C", cwd] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60, creationflags=NOWIN)
    return (r.stdout or "").strip()


def cards():
    """素材帳本『進行中』卡:各欄截斷(整份太長會塞爆 prompt)。"""
    p = os.path.join(WRDIR, "素材.md")
    try: txt = open(p, encoding="utf-8").read()
    except Exception: return []
    out = []
    for blk in re.split(r"\n(?=## \[)", txt):
        if not blk.startswith("## ["): continue
        title = blk.split("\n", 1)[0][3:].strip()
        f = lambda k, n: (re.search(r"^- %s[:：](.+)$" % k, blk, re.M) or [None, ""])[1][:n].strip() \
            if re.search(r"^- %s[:：]" % k, blk, re.M) else ""
        st = f("狀態", 40)
        if "已寫入週報" in st: continue
        prog = f("Progress", 100000)
        out.append({"title": title, "status": st, "context": f("Context", 400),
                    "hypothesis": f("Hypothesis", 400),
                    "progress_tail": prog[-900:], "key_decision": f("Key Decision", 500)})
    return out[:8]


def meetings(since):
    try: c = json.load(open(MDCACHE, encoding="utf-8"))
    except Exception: return []
    out = []
    for k, v in c.items():
        out.append({"summary": v.get("overview_summary", "")[:200],
                    "decisions": (v.get("decisions") or [])[:4],
                    "mine": v.get("mine_summary", ""),
                    "mine_todos": (v.get("mine_todos") or [])[:4]})
    return out[-6:]


def jira_done():
    try: f = json.load(open(FIXEDF, encoding="utf-8"))
    except Exception: return []
    return [{"key": x.get("key"), "title": x.get("title", "")[:60],
             "product": x.get("product", ""), "at": x.get("fixed_at", "")[:10]} for x in f[-25:]]


def vault_changes(since_iso):
    lines = git(["log", "--since=%s" % since_iso, "--pretty=%s", "--",
                 "1_Projects", "4_Memory", "2_Toolkit", "0_Memory"]).split("\n")
    return [l[:120] for l in lines if l.strip()][:40]


def codex_json(prompt):
    """codex exec --json:回 (最終文字, thread_id)。"""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run(["cmd", "/c", "codex", "exec", "--json", "--skip-git-repo-check", "-"],
                       input=prompt, text=True, encoding="utf-8", errors="replace",
                       capture_output=True, timeout=900,
                       cwd=os.path.expanduser("~/.config/agent_cockpit"), env=env, creationflags=NOWIN)
    tid, msg = "", ""
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"): continue
        try: ev = json.loads(line)
        except Exception: continue
        if ev.get("type") == "thread.started": tid = ev.get("thread_id", "")
        it = ev.get("item") or {}
        if it.get("type") == "agent_message": msg = it.get("text", "") or msg
    return msg, tid


def main():
    now = datetime.datetime.now(TZ)
    ws = week_start(now)
    tag = ws.strftime("%Y-%m-%d")
    out_path = os.path.join(WRDIR, "週報草稿_%s.md" % tag)
    force = "--force" in sys.argv
    if os.path.exists(out_path) and not force:
        print("weekly: 本週草稿已存在(%s),--force 可重產" % os.path.basename(out_path))
    else:
        mats = {"本週區間": "%s ~ %s" % (tag, now.strftime("%Y-%m-%d %H:%M")),
                "素材帳本進行中卡": cards(),
                "本週會議萃取": meetings(ws),
                "本週完成的單": jira_done(),
                "vault 異動": vault_changes(ws.strftime("%Y-%m-%d"))}
        prompt = (
            "你是 owner(Acme 作者產品線 PM)的週報助理。依下列材料產出**本週 MA 週報草稿**。\n"
            "規格(不可違反):\n"
            "0. **一件事=一個 App**(Product A／Product B Product B／Product C／Product D;跨產品的 PM 系統另立一件),"
            "標題前面標 App 名。每件開頭先用一句「為何做」交代這個 App 現在的處境與目標,結尾用 `**下一步**` 一行寫"
            "接下來要做什麼(具體動作+對象),讓沒跟進的人也能理解該 App 的全景;沒有材料的 App 不要硬編,寫「本週無進展」即可。\n"
            "1. 收斂成 3~5 件事,排序依「對北極星(Product A AI 助理/Product B 可轉債/PM 自動化)的影響」,不是花的時間。\n"
            "2. 每件固定四欄:Context(為什麼做)、Hypothesis(**動筆開始時**的可否證押注:如果做 X 應觀察到 Y,因為 Z)、"
            "Testing & Building Progress(每條標 [支持]/[反對]/[未定],要能驗回該假說)、"
            "Key Decision(基於 Progress 證據的資源轉向,不是背景設定)。\n"
            "3. 因果鏈硬閘:KD 必須只靠該件 Progress 的證據句就能推出來;推不出來就重寫該件。\n"
            "4. 證據不足的欄位寫 `⚠ 需要你補:<具體問題>`,**不要編造**。\n"
            "5. 語氣=正式商業進度(給 BU Head 看),不要 MVP/實驗腔;內部工具建設除非影響交付否則不入報。\n"
            "輸出 Markdown,開頭 `# 週報草稿 <日期區間>`,每件事:\n"
            "`### N. [<App名>] <一句話結論式標題>` 然後四個粗體欄位,最後一行 `**下一步**:…`。"
            "最後加一節 `## ⚠ 待你確認` 列出你不確定的點。\n\n"
            "〈材料 JSON〉\n" + json.dumps(mats, ensure_ascii=False))
        msg, tid = codex_json(prompt)
        if not msg.strip():
            print("weekly: codex 無輸出"); return
        os.makedirs(WRDIR, exist_ok=True)
        head = ("---\nname: ma-weekly-draft-%s\ndescription: MA 週報草稿(Codex 產,%s;"
                "thread=%s——面板「與 Codex 討論」會 codex resume 這個 thread 改稿)\n---\n\n" %
                (tag, now.strftime("%Y-%m-%d %H:%M"), tid or "?"))
        open(out_path, "w", encoding="utf-8").write(head + msg.strip() + "\n")
        print("weekly: 產出 %s (thread=%s)" % (os.path.basename(out_path), tid[:8] if tid else "?"))
        st = {}
        try: st = json.load(open(STATE, encoding="utf-8"))
        except Exception: pass
        titles = re.findall(r"^### \d+\.\s*(.+)$", msg, re.M)
        st["weekly"] = {"at": now.strftime("%Y-%m-%d %H:%M"), "week": tag, "path": out_path,
                        "thread": tid, "titles": titles[:6]}
        tmp = STATE + ".tmp"
        json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.replace(tmp, STATE)


if __name__ == "__main__":
    main()
