// Agent Cockpit — Electron 主程序:單一透明視窗,四態縮放(orb/hover/panel/overview)。
// 唯讀駕駛艙:collectors 寫 state.json,本程式只讀+渲染;[⟳]=spawn collectors。
const { app, BrowserWindow, ipcMain, shell, Tray, Menu, screen } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");

const STATE_FILE = path.join(app.getPath("home"), ".config", "agent_cockpit", "state.json");
const OVERRIDES = path.join(app.getPath("home"), ".config", "agent_cockpit", "user_overrides.json");
const POSF = path.join(app.getPath("userData"), "cockpit_pos.json");
const COLLECTORS = path.join(__dirname, "..", "collectors");
const UILOG = path.join(app.getPath("home"), ".config", "agent_cockpit", "ui.log");

// 四態尺寸(寬×高);右上角錨定=右緣固定,寬變時左移
// 視窗恆定尺寸(永不 resize=零跳幀;空白區滑鼠穿透)
const MODES = {
  orb:      { w: 420, h: 700 },
  hover:    { w: 420, h: 700 },
  panel:    { w: 420, h: 700 },
  overview: { w: 420, h: 700 },
};

if (!app.requestSingleInstanceLock()) { app.quit(); process.exit(0); }
app.on("second-instance", () => { if (win) { win.show(); win.focus(); } });

let win = null, tray = null, anchor = null; // anchor = {right, top}
let userHidden = false;   // 只有使用者明確「隱藏小球」才 true;自癒器據此判斷可不可以自動叫回
function recoverWindow() {
  if (!win || win.isDestroyed()) return;
  userHidden = false;
  win.showInactive();
  win.setAlwaysOnTop(true, "screen-saver");
  applyMode("orb");   // 位置也重申(防移出螢幕)
}

function loadAnchor() {
  try { anchor = JSON.parse(fs.readFileSync(POSF, "utf-8")); } catch {}
  if (!anchor) {
    const d = screen.getPrimaryDisplay().workArea;
    anchor = { right: d.x + d.width - 12, top: d.y + 12 };
  }
}
function saveAnchor() { try { fs.mkdirSync(path.dirname(POSF), {recursive:true}); fs.writeFileSync(POSF, JSON.stringify(anchor)); } catch {} }

function applyMode(mode) {
  const m = MODES[mode] || MODES.orb;
  // 右上錨定
  win.setBounds({ x: Math.round(anchor.right - m.w), y: Math.round(anchor.top), width: m.w, height: m.h });
}

function createWindow() {
  loadAnchor();
  win = new BrowserWindow({
    width: MODES.orb.w, height: MODES.orb.h,
    x: Math.round(anchor.right - MODES.orb.w), y: Math.round(anchor.top),
    frame: false, transparent: true, resizable: false, alwaysOnTop: true,
    skipTaskbar: true, hasShadow: false, fullscreenable: false,
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, nodeIntegration: false },
  });
  win.setAlwaysOnTop(true, "screen-saver"); // 蓋過一般視窗但不搶焦點
  win.loadFile("index.html");
  win.webContents.on("console-message", (_e, _lv, msg) => {
    if (msg.startsWith("[ui]")) { try { fs.appendFileSync(UILOG, new Date().toISOString().slice(11, 23) + " " + msg + String.fromCharCode(10)); } catch {} }
  });
  win.once("ready-to-show", () => {
    applyMode(process.env.COCKPIT_MODE || "orb");
    try { fs.appendFileSync(UILOG, new Date().toISOString().slice(11, 23) + " [ui] bounds " + JSON.stringify(win.getBounds()) + " scale=" + screen.getPrimaryDisplay().scaleFactor + String.fromCharCode(10)); } catch {}
  });
  if (process.env.COCKPIT_MODE) win.webContents.once("did-finish-load", () => setTimeout(() => win.webContents.send("forceMode", process.env.COCKPIT_MODE), 600));
  win.on("closed", () => { win = null; });
}

function readJSON(f) { try { return JSON.parse(fs.readFileSync(f, "utf-8")); } catch { return null; } }

// Design token 與域定義都放 config/,啟動時送給 renderer 注入成 CSS 變數與面板表。
// 讀不到就用 index.html / renderer.js 內的 fallback,不會因為缺檔而起不來。
function loadConfig(name) {
  return readJSON(path.join(__dirname, "..", "config", name)) || null;
}
function pushTheme() {
  if (!win || win.isDestroyed()) return;
  win.webContents.send("theme", { theme: loadConfig("theme.json"), domains: loadConfig("domains.json") });
}

function pushState() {
  if (!win) return;
  win.webContents.send("state", { state: readJSON(STATE_FILE), overrides: readJSON(OVERRIDES) });
}

function watchState() {
  const dir = path.dirname(STATE_FILE);
  fs.mkdirSync(dir, { recursive: true });
  let t = null;
  try {
    fs.watch(dir, (ev, fname) => {
      if (fname && !String(fname).startsWith("state")) return;
      clearTimeout(t); t = setTimeout(pushState, 250); // debounce(原子寫=rename 事件)
    });
  } catch {}
}

// 逐支跑、一支失敗不砍後面;每支結果進 scan.log;進度即時推 renderer(⟳ 才有回饋)
const SCANLOG = path.join(app.getPath("home"), ".config", "agent_cockpit", "scan.log");
// 掃描管線=可替換的資料源清單(config/pipeline.json)。預設跑 demo_source.py:
// 免憑證、開箱即有完整畫面;要接真實系統就把 adapters/ 對應那支加進去(可混用)。
// 自己寫的 collector 只要把自己的區段寫進 state.json 即可(格式見 SPEC §11.2),UI 不必改。
function loadPipeline() {
  try {
    const j = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "config", "pipeline.json"), "utf-8"));
    if (Array.isArray(j.steps) && j.steps.length) return j.steps;
  } catch {}
  return ["demo_source.py"];
}
const SCAN_STEPS = loadPipeline();
let scanning = false;
function slog(s) { try { fs.appendFileSync(SCANLOG, new Date().toISOString() + " " + s + "\n"); } catch {} }
function sendScan(p) { try { if (win && !win.isDestroyed()) win.webContents.send("scan", p); } catch {} }
function runCollectors() {
  if (scanning) { sendScan({ running: true, note: "已在掃描中" }); return; }
  scanning = true;
  const errs = [];
  slog("scan start");
  const step = (i) => {
    if (i >= SCAN_STEPS.length) {
      scanning = false;
      slog("scan done errs=" + (errs.join(",") || "none"));
      sendScan({ running: false, errs });
      pushState();
      return;
    }
    const name = SCAN_STEPS[i].replace(".py", "");
    sendScan({ running: true, step: name, idx: i + 1, total: SCAN_STEPS.length, errs });
    let done = false, errBuf = "";
    const next = (tag) => { if (done) return; done = true; if (tag) { errs.push(name); slog(tag); } else slog(name + " ok"); step(i + 1); };
    try {
      const p = spawn("py", [SCAN_STEPS[i]], { cwd: COLLECTORS, windowsHide: true });
      p.stderr.on("data", d => { errBuf = (errBuf + d).slice(-500); });
      p.on("error", e => next(name + " spawn-error " + e));
      p.on("close", code => next(code === 0 ? "" : name + " exit=" + code + " " + errBuf.replace(/\s+/g, " ")));
    } catch (e) { next(name + " throw " + e); }
  };
  step(0);
}

app.whenReady().then(() => {
  createWindow();
  watchState();
  setTimeout(() => { pushTheme(); pushState(); }, 400);
  if (process.env.COCKPIT_SCAN) setTimeout(runCollectors, 800);   // debug:啟動即掃(驗掃描回饋)
  // 排程安全網:睡醒補掃(Task Scheduler 錯過的不補跑)+工作時段 state>20 分鐘舊就自掃
  try { require("electron").powerMonitor.on("resume", () => setTimeout(runCollectors, 15000)); } catch {}
  setInterval(() => {
    try {
      const h = new Date().getHours();
      if (h < 7 || h >= 19 || scanning) return;
      if (Date.now() - fs.statSync(STATE_FILE).mtimeMs > 20 * 60e3) { slog("stale-watchdog kick"); runCollectors(); }
    } catch {}
  }, 5 * 60e3);
  // debug 自截(視覺驗證 ground truth):COCKPIT_SHOT=<dir> → 2.5s 後存 page.png(渲染)+screen.png(桌面合成)
  if (process.env.COCKPIT_SHOT) {
    const dir = process.env.COCKPIT_SHOT;
    setTimeout(async () => {
      try {
        if (process.env.COCKPIT_CLICK) {    // debug:拍照前依序點擊 selector(用 |> 分隔多步,驗展開態)
          for (const sel of process.env.COCKPIT_CLICK.split("|>")) {
            await win.webContents.executeJavaScript(
              `document.querySelector(${JSON.stringify(sel.trim())})?.click()`);
            await new Promise(r => setTimeout(r, 700));
          }
        }
        if (process.env.COCKPIT_EVAL) {     // debug:執行一段 JS(可回 Promise)並把結果寫 eval.txt——驗行為/動畫
          try {
            const r = await win.webContents.executeJavaScript(process.env.COCKPIT_EVAL, true);
            fs.writeFileSync(path.join(dir, "eval.txt"), String(r));
          } catch (e) { fs.writeFileSync(path.join(dir, "eval.txt"), "EVAL-ERR " + e); }
        }
        if (process.env.COCKPIT_SCROLL) {   // debug:先把面板內容捲到指定位置再拍(驗 fold 下方)
          const got = await win.webContents.executeJavaScript(
            `(() => { const b = document.getElementById("sheetBody"); if (!b) return "nobody";
              b.scrollTop = ${parseInt(process.env.COCKPIT_SCROLL) || 0};
              return b.scrollTop + "/" + b.scrollHeight; })()`);
          fs.writeFileSync(path.join(dir, "scroll.txt"), String(got));
          await new Promise(r => setTimeout(r, 400));
        }
        const img = await win.capturePage();
        fs.writeFileSync(path.join(dir, "page.png"), img.toPNG());
        const { desktopCapturer } = require("electron");
        const srcs = await desktopCapturer.getSources({ types: ["screen"], thumbnailSize: { width: 1280, height: 800 } });
        if (srcs[0]) fs.writeFileSync(path.join(dir, "screen.png"), srcs[0].thumbnail.toPNG());
      } catch (e) { try { fs.writeFileSync(path.join(dir, "shot_err.txt"), String(e)); } catch {} }
      // QA 實例(強制模式)拍完自動退出——qaPin 會關掉輪詢收合,絕不可留在使用者桌面
      if (process.env.COCKPIT_MODE && !process.env.COCKPIT_SCAN) setTimeout(() => app.quit(), 600);
    }, 2500);
  }
  // tray:收到背景/叫回。圖示必須是真圖——空圖=系統列看不見,藏起來就永遠找不回
  try {
    const { nativeImage } = require("electron");
    const img = nativeImage.createFromDataURL("data:image/png;base64," +
      "iVBORw0KGgoSPACE_ID_2/9hSPACE_ID_2+/D/3H4SX2muDMS51ODWiG0CUQeiasRmA0xBsmnEZgGEILs34DEAxhCID8GkmZADYEIoNOHNy4X982EeZCy+m3AAQINcAeCxQbAA+Q4jSjM8QojXjMoQkzdgMIqQRAJjP6+l0ILckSPACE_ID_2");
    tray = new Tray(img);
    tray.setToolTip("Agent Cockpit");
    // 防呆:不做「顯示/隱藏」切換(視窗被蓋住時看似不見,切換=把還顯示著的藏掉);叫回與隱藏分兩個明確動作
    tray.setContextMenu(Menu.buildFromTemplate([
      { label: "叫回小球", click: recoverWindow },
      { label: "隱藏小球", click: () => { userHidden = true; if (win) win.hide(); } },
      { label: "立即掃描", click: runCollectors },
      { type: "separator" },
      { label: "結束", click: () => app.quit() },
    ]));
    tray.on("click", recoverWindow);   // 左鍵點圖示=直接叫回
  } catch {}

  // 穿透 hover 靠 WH_MOUSE_LL 低階 hook,Windows 會在回呼慢時「靜默拔掉」→ hover 間歇死亡且零事件零 log。
  // 解=每 3 秒把「當前想要的滑鼠狀態」冪等重申一次:ignore=true 時重呼叫會重裝 hook;false 無副作用。
  // 同一節拍自癒可見性:非使用者主動隱藏卻不可見(外部 SW_HIDE/掉置頂)→ 自動叫回並記錄。
  let lastMouse = { ignore: true };
  setInterval(() => {
    try {
      if (!win || win.isDestroyed()) return;
      if (lastMouse.ignore) win.setIgnoreMouseEvents(true, { forward: true });
      win.setAlwaysOnTop(true, "screen-saver");   // 置頂會被系統事件掉,冪等重申
      if (!userHidden && !win.isVisible()) {
        win.showInactive();
        try { fs.appendFileSync(UILOG, new Date().toISOString().slice(11, 23) + " [ui] auto-reshow(外部隱藏偵測)" + String.fromCharCode(10)); } catch {}
      }
    } catch {}
  }, 3000);
  ipcMain.on("mode", (_e, mode) => {
    applyMode(mode);
    if (mode === "panel" || mode === "overview") { lastMouse.ignore = false; win.setIgnoreMouseEvents(false); } // 面板=實體
  });
  ipcMain.on("mouse", (_e, ignore) => { lastMouse.ignore = ignore; win.setIgnoreMouseEvents(ignore, { forward: true }); });
  ipcMain.on("refresh", runCollectors);
  ipcMain.handle("cursorOut", () => {
    try {
      const p = screen.getCursorScreenPoint(), b = win.getBounds();
      return p.x < b.x - 4 || p.y < b.y - 4 || p.x > b.x + b.width + 4 || p.y > b.y + b.height + 4;
    } catch { return false; }
  });
  // 開連結;本機檔案(會議紀錄 HTML／週報草稿)走 openPath,不然只有 http 會開
  ipcMain.on("open", (_e, url) => {
    if (/^https?:\/\//.test(url)) shell.openExternal(url);
    else if (url) shell.openPath(url).then(err => { if (err) slog("openPath fail " + url + " " + err); });
  });
  // 與產草稿的 Codex session 續談:開一個終端跑 codex resume <thread>(cwd=MA週報,它讀得到草稿檔)
  ipcMain.on("codexResume", (_e, thread, cwd) => {
    try {
      spawn("cmd", ["/c", "start", "cmd", "/k",
                    "codex resume " + String(thread || "").replace(/[^A-Za-z0-9-]/g, "")],
            { cwd: cwd || app.getPath("home"), detached: true, windowsHide: false });
      slog("codexResume " + thread);
    } catch (e) { slog("codexResume fail " + e); }
  });
  ipcMain.on("hide", () => win && win.hide());
  ipcMain.on("nudge", (_e, dx, dy) => { // 面板頭拖曳(renderer 傳位移)
    anchor.right += dx; anchor.top += dy; saveAnchor();
    const b = win.getBounds(); win.setBounds({ x: b.x + dx, y: b.y + dy, width: b.width, height: b.height });
  });
  // 每次 override 前留快照 → Ctrl+Z 回上一步(忽略/清除已修正/拖曳/已處理/展開都可復原;最多 30 步)
  const undoStack = [];
  ipcMain.on("override", (_e, patch) => { // 手動改序/已處理 → user_overrides.json
    const cur = readJSON(OVERRIDES) || {};
    undoStack.push(JSON.stringify(cur)); if (undoStack.length > 30) undoStack.shift();
    const next = { ...cur, ...patch, _updated: new Date().toISOString() };
    try { fs.mkdirSync(path.dirname(OVERRIDES), {recursive:true}); fs.writeFileSync(OVERRIDES, JSON.stringify(next, null, 1)); } catch {}
    pushState();
  });
  // 行事曆建議卡「一鍵建立」:只在使用者按下時寫 Calendar(token=gws-chat,已授 calendar.events)
  ipcMain.handle("calendar_create", async (_e, p) => {
    try {
      const c = readJSON(path.join(app.getPath("home"), ".config", "gws-chat", "token.json"));
      const tr = await fetch("https://oauth2.googleapis.com/token", { method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ client_id: c.client_id, client_secret: c.client_secret,
          refresh_token: c.refresh_token, grant_type: "refresh_token" }) });
      const tok = (await tr.json()).access_token;
      const body = { summary: p.title, description: p.description || "",
        start: { dateTime: p.start + ":00", timeZone: "Asia/Taipei" },
        end: { dateTime: p.end + ":00", timeZone: "Asia/Taipei" } };
      const r = await fetch("https://www.googleapis.com/calendar/v3/calendars/primary/events", {
        method: "POST", headers: { Authorization: "Bearer " + tok, "Content-Type": "application/json" },
        body: JSON.stringify(body) });
      const j = await r.json();
      slog("calendar_create " + (r.ok ? "ok " + j.id : "fail " + JSON.stringify(j).slice(0, 200)));
      return r.ok ? { ok: true, id: j.id, link: j.htmlLink } : { ok: false, err: (j.error || {}).message || r.status };
    } catch (e) { slog("calendar_create throw " + e); return { ok: false, err: String(e) }; }
  });
  // Jira 寫入動作(切狀態/留言):只在使用者按下按鈕時走 collectors/jira_action.py
  ipcMain.handle("jira", (_e, op, key, arg) => new Promise(resolve => {
    const args = [path.join(COLLECTORS, "jira_action.py"), op, key];
    if (arg != null) args.push(String(arg));
    let out = "", err = "";
    try {
      const p = spawn("py", args, { cwd: COLLECTORS, windowsHide: true });
      p.stdout.on("data", d => out += d);
      p.stderr.on("data", d => err += d);
      p.on("error", e => resolve({ ok: false, err: String(e) }));
      p.on("close", () => {
        slog("jira " + op + " " + key + " → " + out.trim().slice(0, 160));
        try { resolve(JSON.parse(out.trim().split("\n").pop())); }
        catch { resolve({ ok: false, err: (err || out || "no output").slice(0, 200) }); }
      });
    } catch (e) { resolve({ ok: false, err: String(e) }); }
  }));
  ipcMain.handle("undo", () => {
    if (!undoStack.length) return false;
    const prev = undoStack.pop();
    try { fs.writeFileSync(OVERRIDES, prev); } catch { return false; }
    pushState();
    return true;
  });
});

app.on("window-all-closed", () => app.quit());
