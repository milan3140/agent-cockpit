# -*- coding: utf-8 -*-
"""跨機 lane 回報(任一機器都可跑,預設由排程每小時跑一次)。
掃本機 `.codex-work` 活躍 lane + 該機近 7 天 git commits,寫成
`2_Toolkit/Harness/agent_cockpit/state/lanes_<機器>.json`(進 git,兩機共享)。
B 機的 dev_progress.py 會把非本機的檔案合併進對應產品,解決「Product B 在 A 機開發、B 機看不到進度」。
用法:py lane_report.py [--push]   (--push 會 add/commit/push 該檔;排程建議帶 --push)"""
import sys, io, os, re, json, time, subprocess

if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
else:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
OUTDIR = os.path.join(HERE, "..", "state")
NOWIN = 0x08000000 if os.name == "nt" else 0


def machine():
    for p in (os.path.join(REPO, "MACHINE"),):
        try: return open(p, encoding="utf-8").read().strip().split()[0][:8] or "?"
        except Exception: pass
    return os.environ.get("COMPUTERNAME", "?")[:8]


def git(args):
    r = subprocess.run(["git", "-C", REPO] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60, creationflags=NOWIN)
    return (r.stdout or "").strip()


def lanes():
    base = os.path.join(REPO, ".codex-work")
    out, now = [], time.time()
    try:
        for d in os.listdir(base):
            p = os.path.join(base, d)
            if not os.path.isdir(p): continue
            age = (now - os.path.getmtime(p)) / 3600
            if age < 72:
                out.append({"name": d, "age_h": round(age, 1)})
    except OSError:
        pass
    return sorted(out, key=lambda x: x["age_h"])[:12]


def main():
    m = machine()
    os.makedirs(OUTDIR, exist_ok=True)
    data = {"machine": m, "at": time.strftime("%Y-%m-%d %H:%M:%S"), "lanes": lanes(), "commits": {}}
    # 每個產品路徑的近 7 天 commits(路徑不存在就是 0,不報錯)
    for pid, path in (("emily_bot", "1_Projects/Product AAI_WebApp"), ("sara_cb", "1_Projects/Product B 可轉債")):
        n = git(["rev-list", "--count", "--since=7.days", "HEAD", "--", path]) or "0"
        last = git(["log", "-1", "--format=%ci|%s", "--", path])
        at, _, msg = last.partition("|")
        data["commits"][pid] = {"n7": int(n), "last_at": at[:16], "last_msg": msg[:80]}
    fp = os.path.join(OUTDIR, "lanes_%s.json" % m)
    tmp = fp + ".tmp"
    json.dump(data, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, fp)
    print("lane_report: %s lanes=%d → %s" % (m, len(data["lanes"]), os.path.basename(fp)))
    if "--push" in sys.argv:
        rel = os.path.relpath(fp, REPO).replace("\\", "/")
        git(["add", rel])
        git(["commit", "-q", "-m", "lane 回報(%s %s)" % (m, data["at"][:16])])
        git(["pull", "--rebase", "--autostash", "-q"])
        r = subprocess.run(["git", "-C", REPO, "push", "-q"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120, creationflags=NOWIN)
        print("lane_report: push rc=%s %s" % (r.returncode, (r.stderr or "")[:120]))


if __name__ == "__main__":
    main()
