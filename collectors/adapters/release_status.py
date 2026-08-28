# -*- coding: utf-8 -*-
"""駕駛艙 collector④ v2:版本比對——線上版(iTunes 公開 API)vs 最新測試包(發布(測試)群「產品發佈」貼文)。
貼文格式:「*🍎產品發佈*: {App}🎉 / *TestFlight 版本*: x.y.z (build) / *描述*: …」(Android=🤖/AAB)。
Android 線上版需 Play API 憑證,未接、明標。寫 state.release。唯讀。"""
import sys, io, os, re, json, time, base64, urllib.parse, urllib.request

if sys.stdout and hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
else:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")

STATE = os.path.expanduser("~/.config/agent_cockpit/state.json")
TOKF = os.path.expanduser("~/.config/gws-chat/token.json")
RELEASE_ROOM = "SPACE_ID_2"   # [作者產品線]程式發布(測試)
APPS = {
    "Product A": {"itunes_id": "000000000", "play_pkg": "com.example.app",
             "keys": ["Product A", "Emily", "emily"]},
    "Product B":  {"itunes_id": "000000000", "play_pkg": "com.example.app",
             "keys": ["Product B", "Product B", "sara", "ProductB"]},
}
VER_RE = re.compile(r"\b(\d+\.\d+\.\d+)\b")
DESC_RE = re.compile(r"描述\*?[:：]\s*([^\n]+)")


def live_ios(app_id):
    try:
        d = json.loads(urllib.request.urlopen(
            "https://itunes.apple.com/lookup?id=%s&country=tw" % app_id, timeout=20).read())
        r = (d.get("results") or [{}])[0]
        return {"ver": r.get("version", "?"), "at": (r.get("currentVersionReleaseDate") or "")[:10]}
    except Exception:
        return None


def live_android(pkg):
    """Play 商店公開網頁就載版本(AF_initDataCallback 資料塊),免憑證。"""
    try:
        req = urllib.request.Request(
            "https://play.google.com/store/apps/details?id=%s&hl=zh_TW" % pkg,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        m = re.search(r'\[\[\["(\d+\.\d+\.\d+(?:\.\d+)?)"\]\]', html)
        return {"ver": m.group(1), "at": ""} if m else None
    except Exception:
        return None


def jira_done_since(app_keys, plats, since):
    """iOS 送審內容的權威推導:線上版發佈日後「已完成」的該 App 指定平台單。
    (Chat 對 iOS 建置極稀疏——實證 60 天只有 1 則;fixVersion 又是 PAGEs 框架版號,都不能當完整源)"""
    try:
        sys.path.insert(0, r"<REPO_ROOT>/2_Toolkit/Input/1D/Jira")
        import jira as J
        auth = base64.b64encode(("%s:%s" % (J.EMAIL, J.TOKEN)).encode()).decode()
        jql = 'project in (PROJ, OPS) AND statusCategory = Done AND resolved >= "%s" ORDER BY resolved DESC' % since
        req = urllib.request.Request(
            J.SITE + "/rest/api/3/search/jql?" + urllib.parse.urlencode(
                {"jql": jql, "maxResults": 100, "fields": "summary,resolutiondate"}),
            headers={"Authorization": "Basic " + auth, "Accept": "application/json"})
        d = json.loads(urllib.request.urlopen(req, timeout=45).read())
        out = []
        for it in d.get("issues", []):
            s = (it.get("fields") or {}).get("summary", "")
            if not any(k in s for k in app_keys): continue
            if not any(p in s for p in plats): continue
            t = re.sub(r"【(?:iOS|Android|雙平台)[-‐–][^】]*】", "", s).strip()
            out.append({"key": it["key"], "t": ("%s %s" % (it["key"], t))[:180],
                        "at": ((it.get("fields") or {}).get("resolutiondate") or "")[:10]})
        return out[:20]
    except Exception as e:
        print("jira_done_since err:", e)
        return []


def chat_token():
    c = json.load(open(TOKF, encoding="utf-8"))
    d = urllib.parse.urlencode({"client_id": c["client_id"], "client_secret": c["client_secret"],
                                "refresh_token": c["refresh_token"], "grant_type": "refresh_token"}).encode()
    return json.loads(urllib.request.urlopen("https://oauth2.googleapis.com/token", data=d, timeout=20).read())["access_token"]


def room_messages(tok, pages=8):
    out, token = [], None
    for _ in range(pages):
        q = {"pageSize": 60, "orderBy": "createTime desc"}
        if token: q["pageToken"] = token
        req = urllib.request.Request(
            "https://chat.googleapis.com/v1/spaces/%s/messages?%s" % (RELEASE_ROOM, urllib.parse.urlencode(q)),
            headers={"Authorization": "Bearer " + tok})
        d = json.loads(urllib.request.urlopen(req, timeout=30).read())
        out += d.get("messages", [])
        token = d.get("nextPageToken")
        if not token: break
    return out


BUILD_RE = re.compile(r"(\d+\.\d+\.\d+)\s*\((\d+)\)")


def vtup(v):
    try: return tuple(int(x) for x in v.split("."))
    except Exception: return (0,)


def parse_items(body):
    """驗收項目=以「- 」起頭的整段(含換行的完整標題),到下一個項目/空段為止;去掉 URL 行。"""
    items = []
    for chunk in re.split(r"\n(?=-\s)", body):
        chunk = chunk.strip()
        if not chunk.startswith("-"): continue
        lines = [ln.strip() for ln in chunk.splitlines()
                 if ln.strip() and not ln.strip().lower().startswith("http")]
        if not lines: continue
        txt = " ".join(lines).lstrip("- ").strip()
        if txt.startswith(("備註", "註:")): continue
        items.append(txt[:220])
    return items[:15]


def parse_review_card(m):
    """驗收教主卡片訊息 → {app, plat, ver, build, items[], at} 或 None。
    平台真相源=Firebase 連結的 android:/ios: 前綴;退而求其次看項目文字標籤。"""
    cards = m.get("cardsV2") or []
    if not cards: return None
    blob = json.dumps(m, ensure_ascii=False)
    if "驗收項目" not in blob: return None
    card = cards[0].get("card") or {}
    title = (card.get("header") or {}).get("title", "")
    # 找含驗收項目的 textParagraph
    body = ""
    for sec in card.get("sections") or []:
        for w in sec.get("widgets") or []:
            tp = (w.get("textParagraph") or {}).get("text", "")
            if "驗收項目" in tp: body = tp; break
        if body: break
    if not body: return None
    bm = BUILD_RE.search(body)
    ver, build = (bm.group(1), bm.group(2)) if bm else (None, None)
    if not ver: return None
    plat = "android" if "android:" in blob else ("ios" if "ios:" in blob else None)
    if not plat:
        plat = "android" if re.search(r"\[Android\]|【Android", body) else (
            "ios" if re.search(r"\[iOS\]|【iOS", body, re.I) else None)
    if not plat: return None
    # 備註段不算項目(常描述前一版差異)
    main_body = body.split("備註")[0]
    return {"title": title, "plat": plat, "ver": ver, "build": build,
            "items": parse_items(main_body), "at": (m.get("createTime") or "")[:10]}


STAGEC = os.path.expanduser("~/.config/agent_cockpit/release_stages.json")


def stage_notes(apps):
    """Codex 判讀版本階段(owner 2026-08-28 慣例:x.y.99=功能測試包非送審;候選版可能因 QA 回歸未出建置;
    版號跨平台對齊,如因應 Android 16 全線升 2.6.0)。輸出每 App×平台 ≤60 字說明,快取。"""
    import hashlib, subprocess
    payload = {}
    for name, a in apps.items():
        for plat in ("ios", "android"):
            rv, qa = a.get(plat + "_review"), a.get(plat + "_qa")
            payload["%s|%s" % (name, plat)] = {
                "線上": (a.get(plat + "_live") or {}).get("ver"),
                "送審候選": {"ver": (rv or {}).get("ver"), "建置未出": bool((rv or {}).get("inferred"))} if rv else None,
                "測試包": {"ver": (qa or {}).get("ver"), "items": [i["t"][:60] for i in (qa or {}).get("items", [])]} if qa else None,
                "候選內容樣本": [i["t"][:60] for i in (rv or {}).get("items", [])[:6]],
                "線上後已完成單樣本": [i["t"][:60] for i in (a.get("ios_pending") or [])[:6]] if plat == "ios" else []}
    sig = hashlib.md5(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:10]
    try: cache = json.load(open(STAGEC, encoding="utf-8"))
    except Exception: cache = {}
    if cache.get("sig") != sig:
        prompt = ("你是 PM 助理。以下是各 App×平台的版本資料(JSON)。版號慣例:x.y.99=功能測試包(驗證同線 x.y.0 的特定功能,"
                  "不是送審候選);「建置未出」=送審候選版還在 QA 回歸沒出建置;版號常跨平台對齊(如因應 Android 16 全線升版)。\n"
                  "對每個 key 輸出一句 ≤60 字的階段說明(繁中,講清楚:線上是哪版、送審候選是哪版與卡在哪、測試包在驗什麼),"
                  "只輸出 JSON:{\"App|平台\":\"說明\",…}\n\n" + json.dumps(payload, ensure_ascii=False))
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run(["cmd", "/c", "codex", "exec", "--skip-git-repo-check", "-"],
                               input=prompt, text=True, encoding="utf-8", errors="replace",
                               capture_output=True, timeout=180,
                               cwd=os.path.expanduser("~/.config/agent_cockpit"), env=env,
                               creationflags=0x08000000 if os.name == "nt" else 0)
            out = r.stdout or ""
            m = re.search(r"\{[\s\S]*\}", out)
            notes = json.loads(m.group(0)) if m else {}
            if notes: cache = {"sig": sig, "notes": notes}
            json.dump(cache, open(STAGEC, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except Exception as e:
            print("stage_notes err:", e)
    for k, v in (cache.get("notes") or {}).items():
        name, _, plat = k.partition("|")
        if name in apps: apps[name][plat + "_note"] = str(v)[:120]


def main():
    apps = {}
    for name, cfg in APPS.items():
        apps[name] = {"ios_live": live_ios(cfg["itunes_id"]),
                      "android_live": live_android(cfg["play_pkg"]),
                      "ios_test": None, "android_test": None,
                      "ios_review": None, "android_review": None}
    try:
        msgs = room_messages(chat_token())
    except Exception:
        msgs = []
    cards = {}                                       # (app, plat) -> [card,...] 新→舊
    for m in msgs:                                   # 新→舊
        rc = parse_review_card(m)                    # Android=驗收教主卡片(含驗收項目)
        if rc:
            for name, cfg in APPS.items():
                if any(k in rc["title"] for k in cfg["keys"]):
                    cards.setdefault((name, rc["plat"]), []).append(rc)
                    break
            continue
        # iOS 建置=純文字貼(TestFlight;常無「產品發佈」詞甚至無平台字樣,如「Product B App 2.6.99 (000000000)」)
        # 平台鑑別退路=build 格式:iOS build 是日期型 10 碼(20260821xx),Android 是小整數(56/373)
        tt = m.get("text") or ""
        if "AAB" not in tt and "🤖" not in tt:
            bm = BUILD_RE.search(tt)
            if bm and (("iOS" in tt or "TestFlight" in tt or "🍎" in tt)
                       or (len(bm.group(2)) >= 8 and bm.group(2).startswith("20"))):
                for name, cfg in APPS.items():
                    if any(k in tt for k in cfg["keys"]):
                        # CHANGELOG 行=「標題 https://…/browse/KEY」或「標題 [https://…/KEY]」:標題在 URL 前、單號在 URL 尾
                        items = []
                        for ln in tt.splitlines():
                            km = re.search(r"browse/((?:PROJ|OPS|COMMON)-\d+)", ln)
                            if km:
                                title = re.sub(r"\[?https?://\S+\]?", "", ln).strip(" -[]　")
                                items.append(("%s %s" % (km.group(1), title)).strip()[:180])
                            elif re.match(r"\s*(?:PROJ|OPS|COMMON)-\d+\s+\S", ln):   # 「KEY 標題」無連結型
                                items.append(ln.strip()[:180])
                        items = items[:15]
                        cards.setdefault((name, "ios"), []).append(
                            {"title": name, "plat": "ios", "ver": bm.group(1), "build": bm.group(2),
                             "items": items, "at": (m.get("createTime") or "")[:10]})
                        break
                continue
        t = m.get("text") or json.dumps(m, ensure_ascii=False)
        if "產品發佈" not in t: continue
        plat = "ios" if ("🍎" in t or "TestFlight" in t) else (
            "android" if ("🤖" in t or "AAB" in t or "Android" in t or "APK" in t) else None)
        if not plat: continue
        vers = [v for v in VER_RE.findall(t) if not v.startswith("9.99")]
        if not vers: continue
        for name, cfg in APPS.items():
            if any(k in t for k in cfg["keys"]):
                slot = plat + "_test"
                if apps[name][slot] is None:
                    dm = DESC_RE.search(t)
                    apps[name][slot] = {"ver": vers[0], "at": (m.get("createTime") or "")[:10],
                                        "notes": [dm.group(1)[:80]] if dm else []}
                break

    # 版號慣例:x.y.99=功能測試包(非送審候選);送審候選=線上後最高的非 .99 版
    # 可送審內容=線上版之後所有「候選線」建置的累計項目(同單去重);.99 測試包另欄呈現
    KEY_RE = re.compile(r"(PROJ-\d+|OPS-\d+|COMMON-\d+)")
    for (name, plat), cs in cards.items():
        live = apps[name].get(plat + "_live") or {}
        live_v = vtup(live.get("ver", "0"))
        newer = [c for c in cs if vtup(c["ver"]) > live_v] or cs[:1]
        qa = [c for c in newer if c["ver"].endswith(".99")]
        cand = [c for c in newer if not c["ver"].endswith(".99")]
        if qa:
            q = max(qa, key=lambda c: (vtup(c["ver"]), int(c.get("build") or 0)))
            apps[name][plat + "_qa"] = {"ver": q["ver"], "build": q["build"], "at": q["at"],
                                        "items": [{"v": q["ver"], "t": t} for t in q["items"]]}
        if not cand:
            continue
        latest = max(cand, key=lambda c: (vtup(c["ver"]), int(c.get("build") or 0)))
        seen_i, agg = set(), []
        for c in sorted(cand, key=lambda c: (vtup(c["ver"]), int(c.get("build") or 0))):
            for t in c["items"]:
                km = KEY_RE.search(t)
                ik = km.group(1) if km else t[:40]
                if ik in seen_i: continue
                seen_i.add(ik)
                agg.append({"v": c["ver"], "t": t})
        apps[name][plat + "_review"] = {"ver": latest["ver"], "build": latest["build"],
                                        "at": latest["at"], "n_builds": len(cand), "items": agg}

    # 沒有候選建置但有 .99 測試包 → 候選版=測試包版號去 .99(慣例:2.6.99 是驗證 2.6.0 功能的測試包)
    for name in apps:
        for plat in ("ios", "android"):
            qa2 = apps[name].get(plat + "_qa")
            if qa2 and not apps[name].get(plat + "_review"):
                cv = re.sub(r"\.99$", ".0", qa2["ver"])
                apps[name][plat + "_review"] = {"ver": cv, "build": None, "at": qa2["at"],
                                                "n_builds": 0, "items": [], "inferred": True}

    # iOS 內容補全:Chat 對 iOS 建置極稀疏 → 權威推導=線上版發佈日後完成的該 App iOS/雙平台單
    for name, cfg in APPS.items():
        since = ((apps[name].get("ios_live") or {}).get("at") or "").strip()
        if since:
            apps[name]["ios_pending"] = jira_done_since(cfg["keys"], ("iOS", "雙平台"), since)

    # Codex 階段說明:每 App×平台一句「線上/送審候選/測試包各是什麼、卡在哪」;快取 by 輸入簽章
    stage_notes(apps)

    st = {}
    try: st = json.load(open(STATE, encoding="utf-8"))
    except Exception: pass
    st["release"] = {"scanned_at": time.strftime("%Y-%m-%d %H:%M:%S"), "apps": apps,
                     "note": "線上版=iTunes/Play 公開資料;可送審=發布群驗收卡片"}
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)
    out = []
    for n, a in apps.items():
        out.append("%s: iOS線上%s / 可送審iOS %s And %s(%s項)" % (
            n, (a["ios_live"] or {}).get("ver", "?"),
            (a["ios_review"] or {}).get("ver", "-"),
            (a["android_review"] or {}).get("ver", "-"),
            len((a["android_review"] or {}).get("items", []))))
    print("release: " + " | ".join(out))


if __name__ == "__main__":
    main()
