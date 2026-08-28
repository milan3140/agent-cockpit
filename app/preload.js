const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("cockpit", {
  onState: (cb) => ipcRenderer.on("state", (_e, payload) => cb(payload)),
  onTheme: (cb) => ipcRenderer.on("theme", (_e, payload) => cb(payload)),
  onForceMode: (cb) => ipcRenderer.on("forceMode", (_e, m) => cb(m)),
  onScan: (cb) => ipcRenderer.on("scan", (_e, p) => cb(p)),
  setMode: (m) => ipcRenderer.send("mode", m),
  setMouse: (ignore) => ipcRenderer.send("mouse", ignore),
  cursorOut: () => ipcRenderer.invoke("cursorOut"),
  refresh: () => ipcRenderer.send("refresh"),
  open: (url) => ipcRenderer.send("open", url),
  hide: () => ipcRenderer.send("hide"),
  nudge: (dx, dy) => ipcRenderer.send("nudge", dx, dy),
  override: (patch) => ipcRenderer.send("override", patch),
  undo: () => ipcRenderer.invoke("undo"),
  calendarCreate: (p) => ipcRenderer.invoke("calendar_create", p),
  jira: (op, key, arg) => ipcRenderer.invoke("jira", op, key, arg),
  codexResume: (thread, cwd) => ipcRenderer.send("codexResume", thread, cwd),
});
