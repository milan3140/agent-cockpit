# -*- coding: utf-8 -*-
"""E2E:拖曳小球換位置。注入真滑鼠 按下→移動→放開,用 Win32 讀視窗 rect 驗位移,
並確認沒誤觸開面板(ui.log 無 -> overview);測完拖回原位。"""
import io, sys, time, ctypes, os, subprocess
from ctypes import wintypes

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
u32 = ctypes.windll.user32
u32.SetProcessDPIAware()
SW, SH = u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
LOG = os.path.expanduser("~/.config/agent_cockpit/ui.log")
MOVE, LDOWN, LUP, ABS = 0x0001, 0x0002, 0x0004, 0x8000

EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def cockpit_pids():
    ps = subprocess.run(["powershell", "-NoProfile", "-Command",
                         "(Get-CimInstance Win32_Process -Filter \"name='electron.exe'\" | "
                         "Where-Object { $_.CommandLine -like '*agent_cockpit*' }).ProcessId"],
                        capture_output=True, text=True, timeout=60)
    return {int(x) for x in ps.stdout.split() if x.strip().isdigit()}


def find_window(pids):
    """回傳 (hwnd, rect) —— 取可見且尺寸最大的那個(=主視窗)。"""
    best = [None, None, 0]

    def cb(h, _l):
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value not in pids or not u32.IsWindowVisible(h):
            return True
        r = wintypes.RECT()
        u32.GetWindowRect(h, ctypes.byref(r))
        area = (r.right - r.left) * (r.bottom - r.top)
        if area > best[2]:
            best[0], best[1], best[2] = h, (r.left, r.top, r.right, r.bottom), area
        return True

    u32.EnumWindows(EnumProc(cb), 0)
    return best[0], best[1]


def move(px, py):
    u32.mouse_event(ABS | MOVE, int(px * 65535 / SW), int(py * 65535 / SH), 0, 0)


def drag(x0, y0, dx, dy, steps=18):
    move(x0, y0); time.sleep(.3)
    u32.mouse_event(LDOWN, 0, 0, 0, 0); time.sleep(.15)
    for i in range(1, steps + 1):
        move(x0 + dx * i / steps, y0 + dy * i / steps); time.sleep(.03)
    u32.mouse_event(LUP, 0, 0, 0, 0); time.sleep(.5)


pids = cockpit_pids()
if not pids:
    print("widget 沒在跑"); sys.exit(1)
hwnd, r0 = find_window(pids)
if not hwnd:
    print("找不到可見視窗"); sys.exit(1)
print("before rect:", r0)
base = os.path.getsize(LOG)
# orbWrap 中心:視窗右上角往左 42*scale、往下 42*scale(CSS right:20 top:20,45px 球)
scale = (r0[2] - r0[0]) / 420.0
ox, oy = r0[2] - 42 * scale, r0[1] + 42 * scale
drag(ox, oy, -260, 180)
_, r1 = find_window(pids)
print("after  rect:", r1)
new = open(LOG, encoding="utf-8", errors="replace").read()[base:]
opened = "-> overview" in new
moved = abs(r1[0] - r0[0]) > 150 and abs(r1[1] - r0[1]) > 100
print("DRAG-MOVED:", "PASS" if moved else "FAIL", "| NO-PANEL-OPEN:", "PASS" if not opened else "FAIL")
drag(r1[2] - 42 * scale, r1[1] + 42 * scale, 260, -180)
_, r2 = find_window(pids)
print("restored  :", r2, "OK" if abs(r2[0] - r0[0]) < 15 and abs(r2[1] - r0[1]) < 15 else "DRIFT")
