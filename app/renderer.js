// Agent Cockpit renderer:狀態→四格亮度/面板渲染;互動=hover 分裂、點球全景、面板拖曳。
/* global cockpit */
// 面板表與視覺 token 的真相源是 config/(domains.json / theme.json),由 main 注入(見 applyTheme);
// 下面這份只是「讀不到設定檔時」的 fallback。
const PANELS = {
  imm:  { name: "即時訊息",  color: "var(--q-imm)"  },
  meet: { name: "會議",      color: "var(--q-meet)" },
  ops:  { name: "工單維運",  color: "var(--q-ops)"  },
  dev:  { name: "開發進度",  color: "var(--q-dev)"  },
};
function applyTheme(payload) {
  const root = document.documentElement.style;
  const set = (k, v) => { if (v != null && v !== "") root.setProperty(k, String(v)); };
  const t = payload && payload.theme;
  if (t) {
    const c = t.color || {};
    set("--bronze", c.bronze); set("--glass", c.glass); set("--glass-edge", c.glassEdge);
    set("--ink", c.ink); set("--ink-2", c.ink2); set("--ink-3", c.ink3);
    set("--hair", c.hair); set("--hot", c.hot); set("--alarm", c.alarm);
    if (t.motion) set("--e", t.motion.easing);
    if (t.font) {
      set("--fs-xs", t.font.xs); set("--fs-sm", t.font.sm); set("--fs-md", t.font.md);
      set("--fs-lg", t.font.lg); set("--fs-xl", t.font.xl); set("--font", t.font.family);
    }
    if (t.radius) {
      set("--r-sm", t.radius.sm); set("--r-md", t.radius.md);
      set("--r-lg", t.radius.lg); set("--r-sheet", t.radius.sheet);
    }
    for (const [lv, g] of Object.entries(c.sevGlow || {})) set("--sev-glow-" + lv, g);
  }
  const doms = payload && payload.domains && payload.domains.domains;
  if (Array.isArray(doms)) {
    for (const d of doms) {
      if (!d.key) continue;
      set("--q-" + d.key, d.color);
      if (PANELS[d.key]) PANELS[d.key].name = d.name || PANELS[d.key].name;
      else PANELS[d.key] = { name: d.name || d.key, color: "var(--q-" + d.key + ")" };
      const el = document.querySelector('.quad[data-q="' + d.key + '"]');
      if (el && d.hint) el.title = d.hint;
    }
    dbg("theme applied", doms.map(d => d.key + ":" + d.name).join(","));
  }
  if (mode === "panel" || mode === "overview") renderSheet();
}
let S = null, OV = null, mode = "orb", curPanel = null, hoverT = null;
let mouseSolid = null;
const dbg = (...a) => { try { console.log("[ui]", ...a); } catch {} };
dbg("boot", location.href);
let pinned = false, miniHoverT = null, sheetLeaveT = null, hoverSince = 0;
function setSolid(v) { if (v !== mouseSolid) { mouseSolid = v; cockpit.setMouse(!v); } }

// ── 亮度計算 ──────────────────────────────────────────────
function immLevel() {
  const rows = S?.immediate?.rows || [];
  const unread = rows.filter(r => (r.unread || 0) > 0);
  if (!unread.length) return 0;
  const dismissed = OV?.dismissed || {};
  const live = unread.filter(r => !dismissed[r.space + ":" + (S.immediate.scanned_at || "")]);
  if (!live.length) return 0;
  if (live.some(r => r.priority <= 1)) return 3;
  if (live.some(r => r.priority <= 3)) return 2;
  return 1;
}
function meetRecords() {
  return (S?.meetings?.today || []).filter(ev => ev.record && ev.end && new Date(ev.end) < new Date()).length;
}
function meetLevel() {
  const m = S?.meetings; if (!m || !(m.today || []).length) return 0;
  let lv = 0;
  if (m.next_start) {
    const mins = (new Date(m.next_start) - Date.now()) / 60000;
    lv = mins <= 10 ? 3 : mins <= 30 ? 2 : mins <= 60 ? 1 : 0;
  }
  if (meetRecords() > 0) lv = Math.max(lv, 2);   // 紀錄已出待處理
  return lv;
}
function opsLevel() {
  const j = S?.jira; if (!j) return 0;
  if (notIgn(j.need).some(r => (r.comment_stale_h || 0) > 4)) return 3;
  if (notIgn(j.await).length || notIgn(j.need).length) return 2;
  return j.total_open ? 1 : 0;
}
function sigOf(q) {
  if (q === "imm") return (S?.immediate?.scanned_at || "") + ":" + unreadTotal();
  if (q === "ops") return S?.jira?.sig || "";
  if (q === "meet") return (S?.meetings?.next_start || "") + ":rec" + meetRecords();
  return "";
}
function devLevel() {
  const ps = S?.dev?.products || []; if (!ps.length) return 0;
  return ps.some(p => p.commits7d > 0 || (p.lanes || []).length) ? 1 : 0;
}
function levels() {
  const lv = { imm: immLevel(), meet: meetLevel(), ops: opsLevel(), dev: devLevel() };
  const ack = OV?.ack || {};
  for (const q of ["imm", "meet", "ops", "dev"])
    if (lv[q] === 3 && ack[q] === sigOf(q)) lv[q] = 2;   // 看過且資料沒變 → 亮但不脈動
  return lv;
}
function ackPanel(q) {
  const ack = { ...(OV?.ack || {}) };
  if (ack[q] !== sigOf(q)) { ack[q] = sigOf(q); cockpit.override({ ack }); }
}
function unreadTotal() {
  return (S?.immediate?.rows || []).reduce((a, r) => a + (r.unread || 0), 0);
}

function paintOrb() {
  const lv = levels();
  document.querySelectorAll(".quad").forEach(q => q.dataset.lv = lv[q.dataset.q]);
  document.getElementById("ring").className = "ring" + (Object.values(lv).includes(3) ? " on" : "");
  const t = unreadTotal();
  const j = S?.jira, nOps = j ? notIgn(j.await).length + notIgn(j.need).length : 0;
  const nMeet = (S?.meetings?.today || []).length;
  const pcts = (S?.dev?.products || []).map(p => parseInt((p.pct || "").replace(/[^0-9]/g, ""))).filter(n => !isNaN(n));
  const devB = pcts.length ? Math.round(pcts.reduce((a, b) => a + b, 0) / pcts.length) + "%" : "";
  const bdgs = { imm: t > 0 ? String(t) : "", meet: nMeet ? String(nMeet) : "",
                 ops: nOps ? String(nOps) : "", dev: devB };
  document.querySelectorAll(".mini").forEach(m => m.querySelector(".bdg").textContent = bdgs[m.dataset.p]);
}

// ── 面板渲染 ──────────────────────────────────────────────
const esc = s => String(s || "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function prioDot(p) {
  const c = p <= 1 ? "var(--q-meet)" : p <= 3 ? "var(--bronze)" : "rgba(244,239,232,.45)";
  return `<span class="dot" style="background:${c}"></span>`;
}
function renderSuggest(compact) {   // Chat「要約時間」→ 行事曆建議卡(一鍵建立,絕不自動建)
  const sg = (S?.suggestions?.items || []).filter(it => !(OV?.sg_dismissed || {})[it.id]);
  if (!sg.length) return "";
  const created = OV?.cal_created || {};
  let html = `<div class="bhead">約時間建議</div>`;
  for (const it of (compact ? sg.slice(0, 2) : sg)) {
    const k = "sg:" + it.id, done = created[it.id];
    const when = it.start ? `${mdDate(it.start)} ${it.start.slice(11)}–${(it.end || "").slice(11)}` : "時間未定";
    const conf = it.start ? (it.conflicts.length ? `<span class="over">衝堂 ${it.conflicts.length} 場</span>` : "無衝堂") : "";
    let detail = "";
    if (!compact && openKeys.has(k)) {
      detail = `<div class="detail"><div class="dwrap">
        <div class="dcm">原訊息(${esc(it.room)} · ${esc(it.at.slice(5))}):${esc(it.text)}</div>
        ${it.agenda ? `<div class="dcm">議題:${esc(it.agenda)}</div>` : ""}
        ${(it.attendees || []).length ? `<div class="dcm">與會:${esc(it.attendees.join("、"))}</div>` : ""}
        ${it.conflicts.length ? `<div class="dcm"><span class="over">衝堂:</span>${esc(it.conflicts.join("、"))}</div>` : ""}
        <div>${done ? `<button class="jbtn" data-open="${esc(done.link)}">✓ 已建立,開啟行事曆 ↗</button>`
          : it.start ? `<button class="jbtn" data-calcreate="${esc(it.id)}">建立行事曆事件</button>` : `<span class="dcm">訊息沒有明確時間,請到 Chat 敲定</span>`}
        <button class="jbtn" data-open="${esc(it.url)}">開聊天室 ↗</button>
        <button class="jbtn" data-sgdismiss="${esc(it.id)}">略過</button></div></div></div>`;
    }
    html += `<div class="q" data-sev="${done ? 1 : 2}" data-k="${esc(k)}" title="點=展開">
      <span class="act ${done ? "track" : "reply"}">約會</span>
      <span class="main"><div class="need">${esc(it.title || "約時間")}${done ? "　✓已建立" : ""}</div>
      <div class="sub">${esc(when)}${conf ? "　·　" + conf : ""}　·　${esc(it.room)}</div></span>
    </div>${detail}`;
  }
  return html;
}
function renderImm(compact) {
  const im = S?.immediate;
  if (!im) return `<div class="empty">尚無掃描資料——按 ⟳ 立即掃描</div>`;
  const dismissed = OV?.dismissed || {};
  const rows = (im.rows || []).filter(r => (r.unread || 0) > 0 &&
    !dismissed[r.space + ":" + (im.scanned_at || "")]);
  const sgHtml = renderSuggest(compact);
  if (!rows.length) return `<div class="empty">沒有未讀 ✓${im.readstate_scope ? "" : "（水位線模式：只看得到掃描後新訊息）"}</div>` + sgHtml;
  return rows.map(r => {
    const sev = r.priority <= 1 ? 3 : r.priority <= 3 ? 2 : 1;
    const one = (r.unread === 1 && r.preview?.length);
    const sub = one ? `「${esc(r.preview[0].text.slice(0, 88))}」`
      : r.preview?.length ? `最新:「${esc(r.preview[0].text.slice(0, 56))}」` : "";
    const open = openKeys.has("imm:" + r.space) && !compact;
    let detail = "";
    if (open) {
      const msgs = (r.preview || []).map(m =>
        `<div class="dcm">${esc(m.t)} · ${esc(m.text)}</div>`).join("");
      detail = `<div class="detail"><div class="dwrap">${msgs || "(無文字訊息)"}
        <div><button class="jbtn" data-open="${esc(r.url)}">開啟聊天室 ↗(不標已讀)</button></div></div></div>`;
    }
    return `<div class="q" data-sev="${sev}" data-k="imm:${esc(r.space)}" title="點=展開未讀訊息">
      <span class="act">未讀</span>
      <span class="main"><div class="need">${esc(r.label)}
        <span style="font-weight:normal;color:var(--ink-dim)">　${r.unread} 則${r.filtered_out ? `·另 ${r.filtered_out} 則判無關` : ""}</span></div>
      ${!compact && sub ? `<div class="sub">${sub}</div>` : ""}</span>
      <button class="done" data-sp="${esc(r.space)}" title="已處理(本輪熄燈)">✓</button>
    </div>${detail}`;
  }).join("") + sgHtml;
}
function renderMeet() {
  const m = S?.meetings;
  const wk = renderWeekly();
  if (!m) return `<div class="empty">尚未掃描——按 ⟳</div>` + wk;
  if (!(m.today || []).length) return `<div class="empty">今天沒有會議 ✓</div>` + wk;
  return m.today.map(ev => {
    const t = (ev.start || "").slice(11, 16) + (ev.end ? "–" + ev.end.slice(11, 16) : "");
    const mins = ev.start ? Math.round((new Date(ev.start) - Date.now()) / 60000) : null;
    const endT = ev.end ? new Date(ev.end) : null;
    const past = endT && endT < new Date();
    const sev = mins !== null && mins > 0 && mins <= 10 ? 3 : mins !== null && mins > 0 && mins <= 30 ? 2 : 1;
    const soon = mins !== null && mins > 0 && mins <= 60 ? `　·　<span class="hot">${mins} 分後</span>` : "";
    const rec = ev.record, dg = ev.digest;
    const url = (past && rec && rec.url) ? rec.url : ev.doc;
    const k = "meet:" + ev.start;
    let detail = "";
    if (dg && openKeys.has(k)) {   // 全景(整場在談什麼)+ 與我相關;紀錄 HTML 由逐字稿統整
      const sec = (label, arr) => (arr || []).length
        ? `<div class="dcm"><span class="hot">${label}</span></div>` + arr.map(x => `<div class="dcm">　- ${esc(x)}</div>`).join("") : "";
      const secs = (dg.apps || []).length
        ? (dg.apps || []).map(a =>
            `<div class="dcm">　<b>${esc(a.app || "")}</b>${a.status ? `<span style="color:var(--ink-3)"> · ${esc(a.status)}</span>` : ""}</div>` +
            `<div class="dcm">　　為何:${esc(a.why || "-")}</div>` +
            `<div class="dcm">　　要做:${esc(a.what || "-")}</div>` +
            (a.points || []).map(p => `<div class="dcm">　　- ${esc(p)}</div>`).join("")).join("")
        : (dg.sections || []).map(s =>
            `<div class="dcm">　<b>${esc(s.topic || "")}</b>${s.who ? `<span style="color:var(--ink-3)"> · ${esc(s.who)}</span>` : ""}</div>` +
            (s.points || []).map(p => `<div class="dcm">　　- ${esc(p)}</div>`).join("")).join("");
      const acts = (dg.actions || []).map(a => `<div class="dcm">　- ${esc(a.what || "")}${a.who ? `(${esc(a.who)})` : ""}</div>`).join("");
      detail = `<div class="detail"><div class="dwrap">
        ${dg.overview_summary ? `<div class="dcm">${esc(dg.overview_summary)}</div>` : ""}
        ${secs ? `<div class="dcm"><span class="hot">${(dg.apps || []).length ? "各產品狀況" : "逐節重點"}</span></div>${secs}` : ""}
        ${sec("決議", dg.decisions)}
        ${acts ? `<div class="dcm"><span class="hot">待辦</span></div>${acts}` : ""}
        ${dg.mine_summary ? `<div class="dcm"><span class="hot">與我相關</span>:${esc(dg.mine_summary)}</div>` : ""}
        ${sec("　需求", dg.mine_needs)}${sec("　我的待辦", dg.mine_todos)}
        <div class="dcm" style="color:var(--ink-3)">由逐字稿統整 ${esc(dg.at || "")}</div>
        <div>${dg.html ? `<button class="jbtn" data-open="${esc(dg.html)}">開完整紀錄 ↗</button>` : ""}
        ${rec && rec.url ? `<button class="jbtn" data-open="${esc(rec.url)}">原始文件 ↗</button>` : ""}</div></div></div>`;
    }
    const clickable = dg ? `data-k="${esc(k)}"` : (url ? `data-url="${esc(url)}"` : "");
    return `<div class="q" data-sev="${past && rec ? 2 : sev}" ${past && !rec ? 'style="opacity:.45"' : ""} ${clickable} title="${dg ? "點=展開會後萃取" : past && rec ? "點=開會議紀錄" : ev.doc ? "點=開會議文件" : ""}">
      <span class="act">${past ? (rec ? "紀錄" : "已結束") : t}</span>
      <span class="main"><div class="need">${esc(ev.title)}</div>
      ${dg && (dg.overview_summary || dg.mine_summary) ? `<div class="sub">${esc((dg.overview_summary || "").slice(0, 46) || dg.mine_summary)}${(dg.mine_todos || []).length ? `　·　<span class="hot">我的待辦 ${dg.mine_todos.length}</span>` : ""}</div>`
        : past && rec ? `<div class="sub">紀錄已出:${esc(rec.title.slice(0, 30))} · 點開</div>`
        : ev.prep || soon ? `<div class="sub">${ev.prep ? "要準備:" + esc(ev.prep) : ""}${soon}</div>` : ""}</span>
    </div>${detail}`;
  }).join("") + wk;
}
function renderWeekly() {   // AI 週報草稿(Codex 產;可 resume 同一個 thread 改稿)
  const w = S?.weekly;
  if (!w || !w.path) return "";
  const k = "weekly";
  const open = openKeys.has(k);
  const detail = open ? `<div class="detail"><div class="dwrap">
    ${(w.titles || []).map((t, i) => `<div class="dcm">${i + 1}. ${esc(t)}</div>`).join("") || `<div class="dcm">(草稿無標題,直接開檔看)</div>`}
    <div class="dcm" style="color:var(--ink-3)">產於 ${esc(w.at)} · Codex thread ${esc((w.thread || "").slice(0, 8))}</div>
    <div><button class="jbtn" data-open="${esc(w.path)}">開草稿</button>
    ${w.thread ? `<button class="jbtn" data-cxresume="${esc(w.thread)}">與 Codex 討論改稿</button>` : ""}</div>
  </div></div>` : "";
  return `<div class="bhead">AI 週報草稿</div>
    <div class="q" data-sev="2" data-k="${k}" title="點=展開">
      <span class="act reply">週報</span>
      <span class="main"><div class="need">${esc(w.week)} 週草稿已產 · ${(w.titles || []).length} 件事</div>
      <div class="sub">Codex 產;可開檔微調或直接與同一個 session 討論改稿</div></span>
    </div>${detail}`;
}
function hmn(h) { if (h == null) return ""; return h < 24 ? Math.round(h) + "h" : (h / 24).toFixed(1) + "天"; }
function mdDate(d) { const [m, day] = String(d || "").slice(5, 10).split("-"); return (+m) + "/" + (+day); }   // 2026-08-27T… → 8/27
function applyOrder(rows, bk) {
  const manual = (OV?.jira_order?.[bk]) || [];
  return [...rows].sort((a, b) => {
    const ia = manual.indexOf(a.key), ib = manual.indexOf(b.key);
    if (ia !== -1 && ib !== -1) return ia - ib;
    if (ia !== -1) return -1; if (ib !== -1) return 1;
    return (b.score || 0) - (a.score || 0);
  });
}
const openKeys = new Set();   // 展開中的單(行內完整敘述)
function notIgn(a) { const g = OV?.ignored || {}; return (a || []).filter(r => !g[r.key]); }   // 使用者忽略的單全視圖排除
function brick(r, i, compact, bk) {
  const act = r._act === "驗收" ? "accept" : r._act === "回覆" ? "reply" : "track";
  const main = r.need || r.title;                       // 主行=需要你做什麼(Codex);沒有就標題
  const what = r.need ? (r.what || r.title) : "";       // 次行=這單是什麼
  const who = r.lc ? `${esc(r.lc.by.split(/[A-Za-z]/)[0] || r.lc.by)}<span class="${(r.lc.stale_h || 0) > 24 ? "over" : "hot"}"> 等 ${hmn(r.lc.stale_h)}</span>` : "";
  const due = r.due ? `<span class="${r.overdue ? "over" : ""}">${mdDate(r.due)}${r.overdue ? "" : " 止"}</span>` : "";
  const app = `${esc(r.product)}·${esc(r.platform)}${r.feature && r.feature !== "其他" ? "·" + esc(r.feature) : ""}`;
  const sub = [what, who, due, app].filter(Boolean).join("　·　");
  const open = openKeys.has(r.key) && !compact;
  let detail = "";
  if (open) {
    const cm = c => c ? `<div class="dcm">💬 ${esc(c.by)}(${esc(c.at.slice(5).replace("T", " "))}):${esc(c.text)}</div>` : "";
    detail = `<div class="detail"><div class="dwrap">${esc(r.story || "(完整敘述將於下次掃描產生)")}
      ${cm(r.lc)}${cm(r.lc2)}
      <div><button class="jbtn" data-open="${esc(r.url)}">在 Jira 開啟 ↗</button>
      <button class="jbtn" data-jstatus="${esc(r.key)}">切換狀態</button>
      <button class="jbtn" data-jcomment="${esc(r.key)}">留言</button>
      ${bk ? `<button class="jbtn" data-mv="up" data-bk="${bk}" data-k="${r.key}">提前 ↑</button>
      <button class="jbtn" data-mv="dn" data-bk="${bk}" data-k="${r.key}">延後 ↓</button>` : ""}</div>
      <div class="jact" data-for="${esc(r.key)}"></div></div></div>`;
  }
  return `<div class="q" data-sev="${r.sev || 1}" data-k="${esc(r.key)}" title="${esc(r.key)}${open ? "" : " — 點開完整敘述"}">
    <span class="num">${i + 1}</span><span class="act ${act}">${r._act}</span>
    <span class="main"><div class="need">${esc(main)}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</span>
  </div>${detail}`;
}
function fvStage(r) {
  if (/等候驗收|待驗收|等待驗收/.test(r.status)) return "驗收";
  if (/後修|優化|技術債/.test(r.raw || "") || /後修|優化/.test(r.status)) return "後修/優化";
  return "進行中";
}
function fvOrd(r) {   // 細階預設序:已修正→驗收→Code Review→進行中→待辦→其他→後修
  if (r._fixed) return 0;
  const s = r.status || "";
  if (/等候驗收|待驗收|等待驗收/.test(s)) return 1;
  if (/code review/i.test(s)) return 2;
  if (/進行中|In Progress|處理中|待驗證/i.test(s)) return 3;
  if (/待辦|To Do|Pending|等待中|開放|Open/i.test(s)) return 4;
  if (/後修|優化|技術債/.test(r.raw || "") || /後修|優化/.test(s)) return 6;
  return 5;
}
function renderFeatView() {
  const j = S.jira;
  const needKeys = new Set([...(j.need || []).map(r => r.key),
    ...(j.watches || []).flatMap(w => (w.rows || []).filter(r => r.bucket === "need").map(r => r.key))]);
  const seen = new Map();
  for (const r of (j.mine_all || [])) seen.set(r.key, r);
  for (const w of (j.watches || [])) for (const r of (w.rows || []))
    if (!seen.has(r.key)) seen.set(r.key, { ...r, _w: w.label });
  const clearedAt = OV?.fixed_cleared_at || "";
  for (const f of (j.fixed || [])) {   // 已修正單(帳本)併入樹,直到一鍵清除
    if ((f.fixed_at || "") > clearedAt && !seen.has(f.key)) seen.set(f.key, { ...f, _fixed: true });
  }
  const allRows = [...seen.values()];
  const ignRows = allRows.filter(r => (OV?.ignored || {})[r.key]);
  const rows = notIgn(allRows);
  if (!rows.length && !ignRows.length) return `<div class="empty">沒有開放中的單(舊資料?按 ⟳ 重掃)</div>`;
  const exp = OV?.expand || {};
  const zhStatus = (s) => ({ "Pending": "等待中", "In Progress": "進行中", "To Do": "待辦",
    "Reopened": "重開", "Open": "開放", "Blocked": "卡關" }[s] || s);
  const fvRow = (r, showType, fk) => {
    const ask = !r._fixed && needKeys.has(r.key) && !r.chat_done;
    const open = openKeys.has("fv:" + r.key);
    const stage = fvStage(r);
    const sub = r._fixed
      ? `已修正　·　${mdDate(r.fixed_at || "")}`
      : [ask ? `<span class="hot">要回覆</span>` : "",
        stage !== "進行中" ? stage : esc(zhStatus(r.status)),
        r.due ? (r.overdue ? `<span class="over">${mdDate(r.due)}</span>` : mdDate(r.due) + " 止") : "",
        r._w ? "代管" : ""].filter(Boolean).join("　·　");
    let detail = "";
    if (open) {
      const lc = r.lc;
      const facts = ["狀態 " + zhStatus(r.status), r.due ? (r.overdue ? "已逾期 " + r.due : r.due + " 止") : "",
        r._w ? "代管:" + esc(r._w) : ""].filter(Boolean).join("　·　");
      detail = `<div class="detail"><div class="dwrap">
        ${r.what ? `<div class="dcm">原單:${esc(r.title)}</div>` : ""}
        ${ask && r.need ? `<div class="dcm"><span class="hot">要做:</span>${esc(r.need)}</div>` : ""}
        ${r.story ? `<div class="dcm">${esc(r.story)}</div>` : ""}
        ${lc ? `<div class="dcm">💬 ${esc(lc.by)}(${esc(lc.at)}):${esc(lc.text)}</div>` : ""}
        <div class="dcm">${facts}</div>
        <div><button class="jbtn" data-open="${esc(r.url)}">在 Jira 開啟 ↗</button>
        <button class="jbtn" data-jstatus="${esc(r.key)}">切換狀態</button>
        <button class="jbtn" data-jcomment="${esc(r.key)}">留言</button>
        <button class="jbtn" data-ign="${esc(r.key)}" title="只在駕駛艙隱藏,不動 Jira">忽略此單</button></div>
        <div class="jact" data-for="${esc(r.key)}"></div></div></div>`;
    }
    return `<div class="q fvq" data-sev="${ask ? 2 : 1}" data-k="fv:${esc(r.key)}" data-fk="${esc(fk || "")}" draggable="true" title="點=展開,拖曳=調順序">
      <span class="act ${ask ? "reply" : "track"}">${showType ? (r.is_bug ? "Bug" : "需求") : ""}</span>
      <span class="main"><div class="need">${esc(r.what || r.title)}</div>
      <div class="sub">${sub}</div></span>
    </div>${detail}`;
  };
  const tree = {};
  for (const r of rows) {
    ((tree[r.product] ??= {})[r.platform] ??= {})[r.feature] ??= [];
    tree[r.product][r.platform][r.feature].push(r);
  }
  const PROD_ORD = ["Product A", "Product B", "Product C", "Product D", "其他"], PLAT_ORD = ["iOS", "Android", "雙平台", "後端", "其他"];
  const byOrd = (ord) => (a, b) => (ord.indexOf(a) + 99 * (ord.indexOf(a) < 0)) - (ord.indexOf(b) + 99 * (ord.indexOf(b) < 0));
  let html = "";
  for (const prod of Object.keys(tree).sort(byOrd(PROD_ORD))) {
    const prodRows = Object.values(tree[prod]).flatMap(f => Object.values(f)).flat();
    const nProd = prodRows.length;
    // App 區域漸層強度=單量×嚴重度:有要回=3;有逾期或量大(≥20)=2;其餘=1
    const pAsk = prodRows.some(r => needKeys.has(r.key) && !r.chat_done);
    const glow = pAsk ? 3 : (prodRows.some(r => r.overdue) || nProd >= 20) ? 2 : 1;
    html += `<div class="fvblk" data-glow="${glow}"><div class="fvh fvh1">${esc(prod)}<span class="cnt2">${nProd} 張</span></div>`;
    for (const plat of Object.keys(tree[prod]).sort(byOrd(PLAT_ORD))) {
      const nPlat = Object.values(tree[prod][plat]).flat().length;
      html += `<div class="fvh fvh2">${esc(plat)}<span class="cnt2">${nPlat} 張</span></div>`;
      const feats = Object.keys(tree[prod][plat])
        .sort((a, b) => tree[prod][plat][b].length - tree[prod][plat][a].length);
      for (const feat of feats) {
        const rs = tree[prod][plat][feat];
        const fk = "fv|" + prod + "|" + plat + "|" + feat;
        const bugs = rs.filter(r => r.is_bug && !r._fixed), reqs = rs.filter(r => !r.is_bug && !r._fixed);
        const nFix = rs.filter(r => r._fixed).length;
        const nAsk = rs.filter(r => !r._fixed && needKeys.has(r.key) && !r.chat_done).length;
        html += `<div class="fvfeat${exp[fk] ? " open" : ""}"><div class="fvh fvh3" data-tg="${esc(fk)}">${esc(feat)}<span class="cnt2">需求 ${reqs.length}·Bug ${bugs.length}${nAsk ? `·<span class="hot">要回 ${nAsk}</span>` : ""}${nFix ? `·已修 ${nFix}` : ""}　${exp[fk] ? "▾" : "▸"}</span></div>`;
        if (exp[fk]) {
          // 手動拖曳序優先;預設=需求先於 Bug→細階狀態(驗收→CR→進行中→待辦→後修)→score
          // 列包在 .fvbody 裡,收合時先播 grid-rows 動畫再重渲染(見 sheetBody click 的 fvh3 分支)
          const manual = (OV?.fv_order || {})[fk] || [];
          html += `<div class="fvbody" data-fb="${esc(fk)}"><div class="fvbodyin">`;
          html += rs.sort((a, b) => {
            const ia = manual.indexOf(a.key), ib = manual.indexOf(b.key);
            if (ia !== -1 || ib !== -1) return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
            return (a.is_bug - b.is_bug) || (fvOrd(a) - fvOrd(b)) || ((b.score || 0) - (a.score || 0));
          }).map((r, i, arr) => fvRow(r, i === 0 || arr[i - 1].is_bug !== r.is_bug, fk)).join("");
          html += `</div></div>`;
        }
        html += `</div>`;
      }
    }
    html += `</div>`;
  }
  const nFixAll = rows.filter(r => r._fixed).length;
  if (nFixAll) {   // 已修正單就在各功能區內(排區內最前);這裡只是全域清除鈕
    html += `<div class="fold">✓ 已修正 ${nFixAll} 張(在各功能區內)<button class="jbtn" data-clearfix="1" style="margin-left:12px">會報完一鍵清除</button><span class="cnt2"></span></div>`;
  }
  if (ignRows.length) {   // 可逆:已忽略摺疊,取消即回列表
    html += `<div class="fold" data-tg="fvign">已忽略<span class="cnt2">${ignRows.length} 張 ${exp.fvign ? "▾" : "▸"}</span></div>`;
    if (exp.fvign) html += ignRows.map(r => `<div class="row jrow" data-sev="1">
      <span class="lab">${esc((r.what || r.title).slice(0, 30))}</span>
      <button class="jbtn" data-unign="${esc(r.key)}">取消忽略</button></div>`).join("");
  }
  return html;
}
function renderOps(compact) {
  const j = S?.jira;
  if (!j) return `<div class="empty">尚未掃描——按 ⟳</div>`;
  if (!compact) {
    const tab = OV?.ops_tab || "zones";
    const tabs = `<div class="tabs">
      <span class="tab${tab === "zones" ? " on" : ""}" data-tab="zones">現況</span>
      <span class="tab${tab === "feature" ? " on" : ""}" data-tab="feature">功能</span></div>`;
    if (tab === "feature") return tabs + renderFeatView() + renderRelease();
    return tabs + renderOpsZones(false);
  }
  return renderOpsZones(true);
}
function renderOpsZones(compact) {
  const j = S.jira;
  const needQ = applyOrder(notIgn(j.need).map(r => ({ ...r, _act: "回覆" })), "need");
  const awaitQ = applyOrder(notIgn(j.await).map(r => ({ ...r, _act: "驗收" })), "await");
  let html = "";
  const zone = (name, color, rows, bk) => {
    if (!rows.length) return "";
    let h = `<div class="bhead"><span class="bic" style="background:${color}"></span>${name}(${rows.length})</div>`;
    h += (compact ? rows.slice(0, 3) : rows).map((r, i) => brick(r, i, compact, bk)).join("");
    if (compact && rows.length > 3) h += `<div class="lc">…還有 ${rows.length - 3} 張</div>`;
    return h;
  };
  html += zone("要回覆——RD 在等你", "var(--bronze)", needQ, "need");
  html += zone("要驗收", "var(--q-imm)", awaitQ, "await");
  if (!needQ.length && !awaitQ.length) html += `<div class="empty">沒有要你動的 ✓(開放 ${j.total_open} 張)</div>`;
  const exp = OV?.expand || {};
  const infoQ = notIgn(j.info);
  if (!compact && infoQ.length) {
    html += `<div class="fold" data-tg="info">💬 留言更新／已在 Chat 處理<span class="cnt2">${infoQ.length} 張 ${exp.info ? "▾" : "▸"}</span></div>`;
    if (exp.info) html += infoQ.map(r => `<div class="row jrow" data-sev="1" data-url="${esc(r.url)}">
      <span class="lab">${esc(r.title.slice(0, 38))}</span><span class="meta">${r.chat_done ? "✓Chat:" + esc(r.chat_done.slice(0, 16)) : esc((r.lc || {}).by || "")}</span></div>`).join("");
  }
  for (const w of (j.watches || [])) {
    const wrows = notIgn(w.rows);
    if (!wrows.length) continue;
    const k = "w_" + w.id;
    const wa = wrows.filter(r => r.bucket === "await"), wn = wrows.filter(r => r.bucket === "need"),
          wo = wrows.filter(r => r.bucket === "other");
    html += `<div class="fold" data-tg="${k}">👀 ${esc(w.label)}<span class="cnt2">驗收 ${wa.length}·回覆 ${wn.length}·其他 ${wo.length} ${exp[k] ? "▾" : "▸"}</span></div>`;
    if (exp[k] && !compact) {
      const wz = (name, rows, act) => rows.length
        ? `<div class="bhead" style="margin-top:10px">${name}(${rows.length})</div>` +
          rows.map((r, i) => brick({ ...r, _act: act }, i, false, null)).join("")
        : "";
      html += wz("等候驗收", wa, "驗收") + wz("要回覆", wn, "回覆") + wz("進行中/其他", wo, "追蹤");
    } else if (!compact && !exp[k]) {
      html += `<div class="lc">點上排展開(同樣有 AI 整理與全景)</div>`;
    }
  }
  if (!compact) html += renderRelease();
  return html;
}
function renderDev(compact) {
  const dv = S?.dev;
  if (!dv || !(dv.products || []).length) return `<div class="empty">尚未掃描——按 ⟳</div>`;
  // 一個 App 一區:為何在做 → 現在做什麼 → 下一步;展開看依據/單況/版本
  return dv.products.map(p => {
    const open = openKeys.has("dev:" + p.id) && !compact;
    const j = p.jira || {}, rel = p.release || {};
    const sub = [p.pct || "估?", p.next ? `下一步:${esc(p.next)}` : "",
                 j.開放單數 ? `${j.開放單數} 張開放` : ""].filter(Boolean).join("　·　");
    let detail = "";
    if (open) {
      const list = (label, arr) => (arr || []).length
        ? `<div class="dcm"><span class="hot">${label}</span></div>` +
          arr.map(x => `<div class="dcm">　- ${esc(x)}</div>`).join("") : "";
      const relTxt = Object.entries(rel).filter(([, v]) => v).map(([k, v]) => `${k} ${esc(v)}`).join("　·　");
      detail = `<div class="detail"><div class="dwrap">
        <div class="dcm"><span class="hot">為何做</span>:${esc(p.why || p.goal)}</div>
        <div class="dcm"><span class="hot">現在</span>:${esc(p.step || "-")}(${esc(p.pct || "估?")};依據 ${esc(p.basis || "-")})</div>
        ${p.next ? `<div class="dcm"><span class="hot">下一步</span>:${esc(p.next)}</div>` : ""}
        <div class="dcm">目標:${esc(p.goal)}</div>
        ${list("等候驗收", j.等候驗收)}${list("進行中", j.進行中)}${list("待辦", j.待辦)}
        ${list("要回覆", j.要回覆)}${list("近期完成", j.近期完成)}
        ${relTxt ? `<div class="dcm">版本:${relTxt}</div>` : ""}
        ${p.commits7d ? `<div class="dcm">程式:7天 ${p.commits7d} commits · 最新「${esc(p.last_msg || "-")}」(${esc(p.last_at || "")})</div>` : ""}
        ${(p.lanes || []).map(l => `<div class="dcm">⚙ ${esc(l.name)}(${l.age_h}h 前活動)</div>`).join("")}
        ${p.remote ? `<div class="dcm">📡 ${esc(p.remote)}</div>` : ""}</div></div>`;
    }
    return `<div class="q" data-sev="1" data-k="dev:${esc(p.id)}" title="點=展開全景">
      <span class="act track">${esc(p.name.replace(/[（(].*$/, "").trim().slice(0, 5))}</span>
      <span class="main"><div class="need">${esc(p.step || p.goal.slice(0, 22))}</div>
      <div class="sub">${sub}</div></span>
    </div>${detail}`;
  }).join("");
}
function renderRelease() {
  const rl = S?.release;
  if (!rl) return "";
  let html = `<div class="bhead">版本狀態</div>`;
  for (const [name, a] of Object.entries(rl.apps || {})) {
    const k = "rel:" + name;
    // 平台成對:每平台一行 = 線上 x.y.z · 可送審 x.y.z(build) N項;推導版(建置未出)標註;.99 測試包另標
    const platLine = (label, live, rev, qa, nPend, liveNote) => {
      const lv = live ? `線上 ${esc(live.ver)}` : `線上 ${liveNote || "?"}`;
      let rv = "可送審 —";
      if (rev && rev.inferred) rv = `可送審 <span class="hot">${esc(rev.ver)}</span>(建置未出${nPend ? `·待上線 ${nPend}項` : ""})`;
      else if (rev) rv = `可送審 <span class="hot">${esc(rev.ver)}(${esc(rev.build || "?")}) ${rev.items.length}項</span>`;
      const qtxt = qa ? `　·　測試包 ${esc(qa.ver)}` : "";
      return `<div class="sub">${label}　${lv}　·　${rv}${qtxt}</div>`;
    };
    const revs = ["ios", "android"].filter(p => a[p + "_review"]);
    let detail = "";
    if (openKeys.has(k)) {
      const secs = ["ios", "android"].map(p => {
        const r = a[p + "_review"], qa = a[p + "_qa"], note = a[p + "_note"];
        const lv = (a[p + "_live"] || {}).ver || "?";
        const P = p === "ios" ? "iOS" : "Android";
        let h = note ? `<div class="dcm"><span class="hot">${P} 階段</span>:${esc(note)}</div>` : "";
        if (r && !r.inferred) {
          const vt = (v) => (v || "0").split(".").map(Number);
          const items = [...r.items].sort((x, y) => {
            const a2 = vt(x.v), b2 = vt(y.v);
            for (let i = 0; i < 3; i++) { if ((b2[i] || 0) !== (a2[i] || 0)) return (b2[i] || 0) - (a2[i] || 0); }
            return 0;
          });
          let lastV = null;
          h += `<div class="dcm">${P}　線上 ${esc(lv)} → 可送審 ${esc(r.ver)}(${esc(r.build || "?")})${r.n_builds > 1 ? ` · 累計 ${r.n_builds} 版建置` : ""},線上後全部變更(新→舊):</div>` +
            items.map(it => {
              const showV = it.v && it.v !== lastV; lastV = it.v || lastV;
              return `<div class="dcm">　${showV ? `<span style="color:var(--ink-3)">[${esc(it.v)}]</span> ` : "　　"}${esc(it.t)}</div>`;
            }).join("");
        } else if (r && r.inferred) {
          h += `<div class="dcm">${P}　線上 ${esc(lv)} → 送審候選 ${esc(r.ver)}(建置未出)</div>`;
        }
        if (p === "ios" && (a.ios_pending || []).length) {
          h += `<div class="dcm">線上 ${esc(lv)} 後已完成待上線(Jira 推導 ${a.ios_pending.length} 張):</div>` +
            a.ios_pending.map(it => `<div class="dcm">　- ${esc(it.t)}</div>`).join("");
        }
        if (qa) {
          h += `<div class="dcm">測試包 ${esc(qa.ver)}(${esc(qa.build || "?")}) · ${esc(qa.at)},驗證中:</div>` +
            (qa.items || []).map(it => `<div class="dcm">　- ${esc(it.t)}</div>`).join("");
        }
        return h;
      }).filter(Boolean).join("");
      detail = `<div class="detail"><div class="dwrap">${secs || "(近3週無可送審建置)"}</div></div>`;
    }
    html += `<div class="q" data-sev="${revs.length ? 2 : 1}" data-k="${esc(k)}" title="點=展開送審內容">
      <span class="act track">版本</span>
      <span class="main"><div class="need">${esc(name)}</div>
      ${platLine("iOS", a.ios_live, a.ios_review, a.ios_qa, (a.ios_pending || []).length)}
      ${platLine("Android", a.android_live, a.android_review, a.android_qa, 0, "未接(Play)")}</span>
    </div>${detail}`;
  }
  return html;
}
function renderStub(what, phase) {
  return `<div class="empty">${what}<br><span style="font-size:11px">Phase ${phase} 接入中</span></div>`;
}
function secHTML(key, bodyHTML, cnt) {
  const p = PANELS[key];
  return `<div class="bhead" data-goto="${key}" style="cursor:pointer" title="點=開單獨面板">
      <span class="bic" style="background:${p.color}"></span>${p.name}
      <span style="font-weight:normal;color:var(--ink-dim);font-size:10.5px">　${cnt || ""}</span></div>
    ${bodyHTML}`;
}
let SCAN = null;   // 掃描進度事件(main→onScan)
function renderScanSlot() {
  const el = document.getElementById("updated");
  if (SCAN?.running) {   // 掃描中:進度優先於時間戳
    el.textContent = `掃描中 ${SCAN.idx || "…"}/${SCAN.total || 6} ${SCAN.step || ""}`;
    el.style.color = "";
    return true;
  }
  if (SCAN?.errs?.length && Date.now() - (SCAN.doneAt || 0) < 5 * 60e3) {
    el.textContent = `掃描完成,${SCAN.errs.length} 支失敗:${SCAN.errs.join("/")}`;
    el.style.color = "var(--hot)";
    return true;
  }
  return false;
}
function updateStamp() {
  const srcTs = mode === "panel"
    ? ({ imm: S?.immediate, meet: S?.meetings, ops: S?.jira }[curPanel]?.scanned_at)
    : [S?.immediate, S?.meetings, S?.jira].map(x => x?.scanned_at || "").sort().pop();
  const el = document.getElementById("updated");
  if (renderScanSlot()) return;   // 掃描資訊佔用更新槽
  if (srcTs) {
    const ageMin = Math.round((Date.now() - new Date(srcTs.replace(" ", "T"))) / 60000);
    el.textContent = "更新 " + srcTs.slice(11, 16) + (ageMin > 15 ? `(${ageMin} 分前)` : "");
    el.style.color = ageMin > 15 ? "var(--hot)" : "";
  } else el.textContent = "";
}
let pendingOpen = null, pendingRow = null;   // 這次剛被點開的功能塊/單:只有它們播入場動畫
function playOpen() {
  const fk = pendingOpen, rk = pendingRow;
  pendingOpen = pendingRow = null;
  if (fk) {
    const el = document.querySelector(`.fvbody[data-fb="${CSS.escape(fk)}"]`);
    if (el) {
      el.classList.add("closing", "opening");        // 先壓到 0fr(無過渡起點)+標記播入場
      requestAnimationFrame(() => requestAnimationFrame(() => el.classList.remove("closing")));
      setTimeout(() => el.classList.remove("opening"), 400);
    }
  }
  if (rk) {   // 單的展開:同樣只讓這一張播,其他已展開的維持靜止(否則整片閃)
    const q = document.querySelector(`.q[data-k="${CSS.escape(rk)}"]`);
    const d = q && q.nextElementSibling;
    if (d && d.classList.contains("detail")) {
      d.classList.add("closing", "opening");
      requestAnimationFrame(() => requestAnimationFrame(() => d.classList.remove("closing")));
      setTimeout(() => d.classList.remove("opening"), 400);
    }
  }
}
function renderSheet() {
  const body = document.getElementById("sheetBody");
  const title = document.getElementById("sheetTitle");
  updateStamp();
  if (mode === "panel") {
    title.textContent = PANELS[curPanel].name;
    body.innerHTML = curPanel === "imm" ? renderImm(false)
      : curPanel === "meet" ? renderMeet()
      : curPanel === "ops" ? renderOps(false)
      : renderDev(false);
  } else {
    title.textContent = "全景總覽";
    body.innerHTML =
      secHTML("imm", renderImm(true), (unreadTotal() || "0") + " 未讀") +
      secHTML("meet", renderMeet(), (S?.meetings?.today || []).length + " 場") +
      secHTML("ops", renderOps(true), (notIgn(S?.jira?.await).length + notIgn(S?.jira?.need).length) + " 張") +
      secHTML("dev", renderDev(true), (S?.dev?.products || []).map(p => p.pct).filter(Boolean).join(" / "));
  }
  playOpen();   // 剛點開的功能塊補播高度展開動畫
}

// ── 模式切換 ──────────────────────────────────────────────
function setSheetOrigin(el) {
  const sheet = document.getElementById("sheet");
  if (!el) { sheet.style.transformOrigin = "calc(100% - 42px) 0px"; return; } // 大球正下
  const r = el.getBoundingClientRect();
  const fromRight = window.innerWidth - (r.left + r.width / 2);
  sheet.style.transformOrigin = `calc(100% - ${fromRight}px) 0px`;  // 該小球正下方
}
function setMode(m, panel, pin) {
  dbg("mode", mode, "->", m, "panel=" + (panel ?? curPanel), "pin=" + !!pin);
  mode = m; curPanel = panel ?? curPanel;
  pinned = (m === "panel" || m === "overview") ? !!pin : false;
  clearTimeout(sheetLeaveT); sheetLeaveT = null;
  clearTimeout(hoverT); hoverT = null;
  clearTimeout(miniHoverT); miniHoverT = null;
  if (m === "hover") hoverSince = Date.now();
  cockpit.setMode(m);
  if (m === "panel" || m === "overview") {
    renderSheet();
    if (m === "panel") ackPanel(curPanel); else ["imm", "meet", "ops", "dev"].forEach(ackPanel);
  }
  document.body.className = m;
}
document.getElementById("orbWrap").addEventListener("mouseenter", () => {
  if (mode !== "orb" && mode !== "hover") return;
  clearTimeout(hoverT); setMode("hover");
});
document.addEventListener("mouseleave", e => {
  const out = e.clientX <= 1 || e.clientY <= 1 || e.clientX >= window.innerWidth - 1 || e.clientY >= window.innerHeight - 1;
  dbg("docLeave", e.clientX, e.clientY, "out=" + out, "mode=" + mode);
  if (!out || qaPin) return;
  if (mode === "hover" && !hoverT)
    hoverT = setTimeout(() => { hoverT = null; if (mode === "hover") { dbg("collapse: doc-leave"); setMode("orb"); } }, 400);
  if ((mode === "panel" || mode === "overview") && !pinned && !sheetLeaveT)
    sheetLeaveT = setTimeout(() => { sheetLeaveT = null; if ((mode === "panel" || mode === "overview") && !pinned) { dbg("collapse: doc-leave-panel"); setMode("orb"); } }, 400);
});
document.addEventListener("mouseenter", () => clearTimeout(hoverT));
let lastPt = null;   // 最近游標位置(dwell 輪詢用)
document.addEventListener("mousemove", e => {
  lastPt = { x: e.clientX, y: e.clientY };
  const onUI = e.target.closest && (e.target.closest("#orbWrap") || e.target.closest(".mini") || e.target.closest("#sheet"));
  if (mode === "panel" || mode === "overview") {
    setSolid(true);
    if (!pinned) {
      if (onUI) { clearTimeout(sheetLeaveT); sheetLeaveT = null; }
      else if (!sheetLeaveT) sheetLeaveT = setTimeout(() => { sheetLeaveT = null; if ((mode === "panel" || mode === "overview") && !pinned) { dbg("collapse: sheet-leave"); setMode("hover"); } }, 500);
    }
    return;
  }
  if (mode === "hover") {
    const ow = document.getElementById("orbWrap").getBoundingClientRect();
    const d = Math.hypot(e.clientX - (ow.left + ow.width / 2), e.clientY - (ow.top + ow.height / 2));
    const safe = !!onUI || d < 85;
    setSolid(safe);                        // ★安全區內維持實體,避免穿透切換觸發假 mouseleave
    if (safe) { clearTimeout(hoverT); hoverT = null; }
    else if (!hoverT && !qaPin) hoverT = setTimeout(() => { hoverT = null; if (mode === "hover") { dbg("collapse: out-of-zone"); setMode("orb"); } }, 450);
    return;
  }
  setSolid(!!onUI);
});
setSolid(false); // 初始:穿透(球區靠 forward mousemove 喚醒)
// 小球可拖曳換位置(擋到按鈕時搬走);移動 <5px 視為點擊=開全景
let orbDrag = null;
document.getElementById("orbWrap").addEventListener("mousedown", e => {
  if (e.button !== 0) return;
  orbDrag = { x: e.screenX, y: e.screenY, moved: 0 };
  setSolid(true);
  e.preventDefault();
});
window.addEventListener("mousemove", e => {
  if (!orbDrag) return;
  const dx = e.screenX - orbDrag.x, dy = e.screenY - orbDrag.y;
  if (!dx && !dy) return;
  orbDrag.moved += Math.abs(dx) + Math.abs(dy);
  orbDrag.x = e.screenX; orbDrag.y = e.screenY;
  cockpit.nudge(dx, dy);
});
window.addEventListener("mouseup", () => {
  if (!orbDrag) return;
  const wasDrag = orbDrag.moved >= 5;
  orbDrag = null;
  if (wasDrag) { dbg("orb dragged"); return; }        // 拖完不開面板
  setSheetOrigin(null); setMode("overview", null, true);
});
document.querySelectorAll(".mini").forEach(m => {
  m.addEventListener("click", () => { setSheetOrigin(m); setMode("panel", m.dataset.p, true); });
  m.addEventListener("mouseenter", () => {
    // 部署飛行期(350ms)的 enter 不能「丟棄」——游標停在小球上不會有第二次 enter,丟了就永遠不開。
    // 改「延後」:剩餘護欄時間加進延遲;真幽靈(飛行中掠過)會由 mouseleave 清掉。
    const guard = mode === "hover" ? Math.max(0, 350 - (Date.now() - hoverSince)) : 0;
    clearTimeout(miniHoverT);
    miniHoverT = setTimeout(() => { if (mode === "hover" || ((mode === "panel" || mode === "overview") && !pinned)) { setSheetOrigin(m); setMode("panel", m.dataset.p, false); } }, 250 + guard);
  });
  m.addEventListener("mouseleave", () => clearTimeout(miniHoverT));
});
// 靜止游標下方「飛入」的小球不會產生 mouseenter(瀏覽器只在滑鼠移動時發邊界事件)——
// 快速滑到小球終點停住=永遠開不了。hover 模式用 hit-test 輪詢補:同一顆下方駐留 ≥250ms 即開。
let miniDwell = { key: null, since: 0 };
setInterval(() => {
  if (mode !== "hover" || !lastPt || qaPin) { miniDwell.key = null; return; }
  const el = document.elementFromPoint(lastPt.x, lastPt.y);
  const mini = el && el.closest && el.closest(".mini");
  const key = mini ? mini.dataset.p : null;
  if (key !== miniDwell.key) dbg("dwell", JSON.stringify({ pt: lastPt, el: el && (el.id || el.className || el.tagName), key }));
  if (!key) { miniDwell.key = null; return; }
  if (miniDwell.key !== key) { miniDwell = { key, since: Date.now() }; return; }
  if (Date.now() - miniDwell.since >= 250) {
    miniDwell.key = null; dbg("mini dwell-open", key);
    setSheetOrigin(mini); setMode("panel", key, false);
  }
}, 120);
document.getElementById("btnCollapse").addEventListener("click", () => setMode("hover"));
window.addEventListener("keydown", async e => {
  if (e.key === "Escape") setMode("orb");
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {   // Ctrl+Z=復原上一個操作
    e.preventDefault();
    const ok = await cockpit.undo();
    const el = document.getElementById("updated");
    el.textContent = ok ? "已復原上一步" : "沒有可復原的步驟";
    setTimeout(updateStamp, 1500);
  }
});
document.getElementById("btnRefresh").addEventListener("click", e => {
  e.currentTarget.classList.add("spin");   // 立即回饋;之後由 scan 事件接管(掃完才停)
  document.getElementById("updated").textContent = "掃描啟動…";
  cockpit.refresh();
});

function jactBox(key) { return document.querySelector(`.jact[data-for="${CSS.escape(key)}"]`); }

// 功能視圖拖曳排序(同功能塊內;存 overrides.fv_order)
let dragK = null, dragFk = null;
document.getElementById("sheetBody").addEventListener("dragstart", e => {
  const q = e.target.closest(".fvq");
  if (!q || !q.dataset.fk) return;
  dragK = q.dataset.k.slice(3); dragFk = q.dataset.fk;
  e.dataTransfer.effectAllowed = "move";
});
document.getElementById("sheetBody").addEventListener("dragover", e => {
  const q = e.target.closest(".fvq");
  if (q && dragFk && q.dataset.fk === dragFk) { e.preventDefault(); q.classList.add("dropmark"); }
});
document.getElementById("sheetBody").addEventListener("dragleave", e => {
  const q = e.target.closest(".fvq"); if (q) q.classList.remove("dropmark");
});
document.getElementById("sheetBody").addEventListener("drop", e => {
  const q = e.target.closest(".fvq");
  if (!q || !dragK || q.dataset.fk !== dragFk) { dragK = dragFk = null; return; }
  e.preventDefault();
  const keys = [...document.querySelectorAll(".fvq")].filter(el => el.dataset.fk === dragFk).map(el => el.dataset.k.slice(3));
  const tgt = q.dataset.k.slice(3);
  const list = keys.filter(k => k !== dragK);
  list.splice(Math.max(0, list.indexOf(tgt)), 0, dragK);
  const fo = { ...(OV?.fv_order || {}) }; fo[dragFk] = list;
  cockpit.override({ fv_order: fo });
  dragK = dragFk = null;
});

// 列互動(開房/已處理/區塊跳轉)
document.getElementById("sheetBody").addEventListener("click", e => {
  const tb = e.target.closest("[data-tab]");
  if (tb) { e.stopPropagation(); cockpit.override({ ops_tab: tb.dataset.tab }); return; }
  const ig = e.target.closest("[data-ign]");
  if (ig) {
    e.stopPropagation();
    const g = { ...(OV?.ignored || {}) }; g[ig.dataset.ign] = true;
    cockpit.override({ ignored: g });
    return;
  }
  const ug = e.target.closest("[data-unign]");
  if (ug) {
    e.stopPropagation();
    const g = { ...(OV?.ignored || {}) }; delete g[ug.dataset.unign];
    cockpit.override({ ignored: g });
    return;
  }
  const cx = e.target.closest("[data-cxresume]");
  if (cx) {   // 開終端續談產草稿的那個 Codex session
    e.stopPropagation();
    cockpit.codexResume(cx.dataset.cxresume, "<REPO_ROOT>\\1_Projects\\MA週報");
    cx.textContent = "已開終端 ↗";
    return;
  }
  const js = e.target.closest("[data-jstatus]");
  if (js) {   // 切換狀態:先問 Jira 有哪些轉換,再讓使用者點
    e.stopPropagation();
    const key = js.dataset.jstatus, box = jactBox(key);
    if (!box) return;
    box.innerHTML = `<div class="dcm">讀取可切換狀態…</div>`;
    cockpit.jira("transitions", key).then(r => {
      if (!r || !r.ok) { box.innerHTML = `<div class="dcm"><span class="over">讀取失敗:${esc((r || {}).err || "?")}</span></div>`; return; }
      const cur = (S?.jira?.mine_all || []).find(x => x.key === key)?.status || "";
      box.innerHTML = `<div class="dcm">目前「${esc(cur)}」,切換到:</div>
        <div><select class="jsel">${r.transitions.map(t =>
          `<option value="${esc(t.id)}">${esc(t.to || t.name)}</option>`).join("")}</select>
        <button class="jbtn" data-jdo="sel" data-jkey="${esc(key)}">切換</button></div>`;
    });
    return;
  }
  const jd = e.target.closest("[data-jdo]");
  if (jd) {
    e.stopPropagation();
    const key = jd.dataset.jkey, box = jactBox(key);
    const sel = box.querySelector("select");
    const tid = jd.dataset.jdo === "sel" ? (sel && sel.value) : jd.dataset.jdo;
    if (!tid) return;
    box.innerHTML = `<div class="dcm">切換中…</div>`;
    cockpit.jira("transition", key, tid).then(r => {
      box.innerHTML = r && r.ok
        ? `<div class="dcm">✓ 已切到「${esc(r.status)}」(下次掃描同步)</div>`
        : `<div class="dcm"><span class="over">切換失敗:${esc((r || {}).err || "?")}</span></div>`;
    });
    return;
  }
  const jc = e.target.closest("[data-jcomment]");
  if (jc) {   // 留言:@名字 會轉成 Jira 真 mention(送出後回報 tag 幾人)
    e.stopPropagation();
    const key = jc.dataset.jcomment, box = jactBox(key);
    if (!box) return;
    box.innerHTML = `<textarea class="jta" data-tafor="${esc(key)}" rows="3" placeholder="留言內容;打 @名字 會 tag 本人(例:@Owner)"></textarea>
      <div><button class="jbtn" data-jsend="${esc(key)}">送出留言</button></div>`;
    const ta = box.querySelector("textarea"); if (ta) ta.focus();
    return;
  }
  const jsend = e.target.closest("[data-jsend]");
  if (jsend) {
    e.stopPropagation();
    const key = jsend.dataset.jsend, box = jactBox(key);
    const ta = box.querySelector("textarea");
    const txt = (ta && ta.value || "").trim();
    if (!txt) { return; }
    jsend.textContent = "送出中…"; jsend.disabled = true;
    cockpit.jira("comment", key, txt).then(r => {
      box.innerHTML = r && r.ok
        ? `<div class="dcm">✓ 已留言${r.mentions ? `,tag ${r.mentions} 人` : ""}${(r.unresolved || []).length ? `;<span class="over">查無此人:${esc(r.unresolved.join("、"))}</span>` : ""}</div>`
        : `<div class="dcm"><span class="over">留言失敗:${esc((r || {}).err || "?")}</span></div>`;
    });
    return;
  }
  const cc = e.target.closest("[data-calcreate]");
  if (cc) {   // 一鍵建立行事曆事件(唯一會寫外部系統的動作,只在按下時)
    e.stopPropagation();
    const it = (S?.suggestions?.items || []).find(x => x.id === cc.dataset.calcreate);
    if (!it || !it.start) return;
    cc.textContent = "建立中…"; cc.disabled = true;
    const desc = `來源:Google Chat ${it.room}(${it.at})\n原訊息:${it.text}\n議題:${it.agenda || ""}\n與會:${(it.attendees || []).join("、")}\n(由 Agent Cockpit 建議卡建立)`;
    cockpit.calendarCreate({ title: it.title || "會議", start: it.start, end: it.end, description: desc }).then(r => {
      if (r && r.ok) { const cr = { ...(OV?.cal_created || {}) }; cr[it.id] = { link: r.link, id: r.id }; cockpit.override({ cal_created: cr }); }
      else { cc.textContent = "建立失敗:" + ((r && r.err) || "?"); cc.disabled = false; }
    });
    return;
  }
  const sd = e.target.closest("[data-sgdismiss]");
  if (sd) {
    e.stopPropagation();
    const d = { ...(OV?.sg_dismissed || {}) }; d[sd.dataset.sgdismiss] = true;
    cockpit.override({ sg_dismissed: d });
    return;
  }
  const cf = e.target.closest("[data-clearfix]");
  if (cf) {
    e.stopPropagation();
    // 本地時間 ISO(fixed_at 也是本地),別用 toISOString(UTC 會差 8 小時)
    const now = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 19);
    cockpit.override({ fixed_cleared_at: now });
    return;
  }
  const tg = e.target.closest("[data-tg]");
  if (tg) {
    e.stopPropagation();
    const ex = { ...(OV?.expand || {}) };
    const key = tg.dataset.tg;
    const body = tg.parentElement && tg.parentElement.querySelector(":scope > .fvbody");
    if (ex[key] && body) {                 // 收合:先播收合動畫,播完才重渲染
      body.classList.add("closing");
      tg.querySelector(".cnt2") && (tg.querySelector(".cnt2").textContent =
        tg.querySelector(".cnt2").textContent.replace("▾", "▸"));
      setTimeout(() => { ex[key] = false; cockpit.override({ expand: ex }); }, 240);
      return;
    }
    ex[key] = !ex[key];
    if (ex[key]) pendingOpen = key;      // 展開:渲染後從 0fr 過渡到 1fr(見 playOpen)
    cockpit.override({ expand: ex });
    return;
  }
  const mv = e.target.closest("[data-mv]");
  if (mv) {
    e.stopPropagation();
    const bk = mv.dataset.bk, k = mv.dataset.k;
    const rows = (S?.jira?.[bk] || []);
    const cur = (OV?.jira_order?.[bk]) || rows.map(r => r.key);
    const list = rows.map(r => r.key).sort((a, b) => {
      const ia = cur.indexOf(a), ib = cur.indexOf(b);
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
    });
    const i = list.indexOf(k), j2 = mv.dataset.mv === "up" ? i - 1 : i + 1;
    if (i !== -1 && j2 >= 0 && j2 < list.length) {
      [list[i], list[j2]] = [list[j2], list[i]];
      const jo = (OV?.jira_order) || {}; jo[bk] = list;
      cockpit.override({ jira_order: jo });
    }
    return;
  }
  const done = e.target.closest(".done");
  if (done) {
    e.stopPropagation();
    const key = done.dataset.sp + ":" + (S?.immediate?.scanned_at || "");
    const d = (OV?.dismissed) || {};
    d[key] = true;
    cockpit.override({ dismissed: d });
    return;
  }
  const ob = e.target.closest("[data-open]");
  if (ob) { e.stopPropagation(); cockpit.open(ob.dataset.open); return; }
  const q = e.target.closest(".q");
  if (q?.dataset.k) {
    const k = q.dataset.k;
    if (openKeys.has(k)) {
      const d = q.nextElementSibling;
      if (d && d.classList.contains("detail")) {
        d.classList.add("closing");
        setTimeout(() => { openKeys.delete(k); renderSheet(); }, 240);
      } else { openKeys.delete(k); renderSheet(); }
    } else { openKeys.add(k); pendingRow = k; renderSheet(); }
    return;
  }
  if (q?.dataset.url) { cockpit.open(q.dataset.url); return; }
  const row = e.target.closest(".row");
  if (row?.dataset.url) { cockpit.open(row.dataset.url); return; }
  const head = e.target.closest(".bhead[data-goto]");
  if (head && mode === "overview") setMode("panel", head.dataset.goto);
});

// 面板頭拖曳=移動整個 widget(送位移給主程序)
(() => {
  const head = document.getElementById("sheetHead");
  let dragging = false, lx = 0, ly = 0;
  head.addEventListener("mousedown", e => { if (e.target.closest(".hbtn")) return; dragging = true; lx = e.screenX; ly = e.screenY; });
  window.addEventListener("mousemove", e => {
    if (!dragging) return;
    cockpit.nudge(e.screenX - lx, e.screenY - ly); lx = e.screenX; ly = e.screenY;
  });
  window.addEventListener("mouseup", () => dragging = false);
})();

let qaPin=false;
if (cockpit.onForceMode) cockpit.onForceMode(m => {   // debug:COCKPIT_MODE=panel | panel:<imm|meet|ops|dev> | overview
  qaPin = true;
  const [mm, pp] = String(m).split(":");
  setMode(mm === "panel" ? "panel" : mm, pp || "ops");
});
// 決定性收合:輪詢游標,連續2次在視窗外即收(事件流不可靠時的地板)
let outPolls = 0;
setInterval(async () => {
  const active = mode !== "orb";
  if (!active || qaPin) { outPolls = 0; return; }
  const out = await cockpit.cursorOut();
  if (out) { if (++outPolls >= 2) { outPolls = 0; dbg("collapse: poll-out"); setMode("orb"); } }
  else outPolls = 0;
}, 400);
if (cockpit.onTheme) cockpit.onTheme(applyTheme);   // config/theme.json + domains.json → CSS 變數與面板表
cockpit.onState(({ state, overrides }) => {
  S = state; OV = overrides;
  paintOrb();
  if (mode === "panel" || mode === "overview") renderSheet();
});
setInterval(() => {   // 更新槽的「N 分前」要活著:每分鐘只重算時間戳,不動內容(捲動位置不歸零)
  if (mode === "panel" || mode === "overview") updateStamp();
}, 60e3);
cockpit.onScan(p => {   // 掃描進度:⟳ 轉+更新槽顯示進行到哪支;失敗留紅字
  SCAN = p.running ? p : { ...p, doneAt: Date.now() };
  document.getElementById("btnRefresh").classList.toggle("spin", !!p.running);
  if (mode === "panel" || mode === "overview") renderScanSlot();
});
