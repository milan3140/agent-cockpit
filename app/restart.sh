#!/bin/bash
# agent_cockpit 重啟閘門:語法→殺舊→啟動→驗活+boot 日誌;失敗吐 stderr,絕不靜默
cd "$(dirname "$0")"
node --check main.js || { echo "FAIL: main.js 語法"; exit 1; }
node --check renderer.js || { echo "FAIL: renderer.js 語法"; exit 1; }
node --check preload.js || { echo "FAIL: preload.js 語法"; exit 1; }
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name='electron.exe'\" | Where-Object { \$_.CommandLine -like '*agent_cockpit*' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force -ErrorAction SilentlyContinue }" >/dev/null 2>&1
sleep 1
rm -f ~/.config/agent_cockpit/ui.log
env -u ELECTRON_RUN_AS_NODE ./node_modules/electron/dist/electron.exe . > /tmp/cockpit_err.log 2>&1 &
sleep 4
N=$(powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"name='electron.exe'\" | Where-Object { \$_.CommandLine -like '*agent_cockpit*' }).Count" 2>/dev/null | tr -d '\r')
if [ "${N:-0}" -lt 1 ]; then echo "FAIL: 進程沒活"; echo "── stderr ──"; head -20 /tmp/cockpit_err.log; exit 1; fi
if ! grep -q "boot" ~/.config/agent_cockpit/ui.log 2>/dev/null; then echo "FAIL: renderer 沒 boot"; echo "── stderr ──"; head -20 /tmp/cockpit_err.log; exit 1; fi
echo "PASS: procs=$N"; grep "bounds" ~/.config/agent_cockpit/ui.log | head -1
