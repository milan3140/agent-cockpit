# -*- coding: utf-8 -*-
"""E2E:快速滑進 orb 區直奔 ops 迷你球停住(<350ms 內抵達=舊版必死案例),驗面板 hover-open。
再驗慢速路徑與收合。PASS 條件:log 出現 hover -> panel pin=false(非點擊)。"""
import io, sys, time, ctypes, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ctypes.windll.user32.SetProcessDPIAware()
SW, SH = ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
SCALE = 1.5
WX, WY, WW = 848, 12, 420
ORB = (WX + WW - 20 - 22, WY + 20 + 22)          # 大球中心(DIP)
MINI_OPS = (ORB[0] - 37, ORB[1] + 35)            # ops 迷你球最終位(--tx-37,--ty35)


def move(px, py):
    ctypes.windll.user32.mouse_event(0x8000 | 0x0001, int(px * 65535 / SW), int(py * 65535 / SH), 0, 0)


def swipe(a, b, steps, dt):
    for i in range(steps + 1):
        move((a[0] + (b[0] - a[0]) * i / steps) * SCALE, (a[1] + (b[1] - a[1]) * i / steps) * SCALE)
        time.sleep(dt)


log = os.path.expanduser("~/.config/agent_cockpit/ui.log")
far = (ORB[0] - 350, ORB[1] + 300)
out0 = (WX - 120, ORB[1] + 300)
move(out0[0] * SCALE, out0[1] * SCALE); time.sleep(1.3)   # 歸零:出視窗等 poll-out 收合,起始狀態受控
base = os.path.getsize(log)
swipe(far, ORB, 10, 0.012)         # 快速滑到大球(觸發部署)
swipe(ORB, MINI_OPS, 6, 0.015)     # 立刻轉去迷你球(~90ms,抵達時仍在 350ms 護欄期=舊版必死)
time.sleep(1.6)                    # 停住等 250+剩餘護欄
new = open(log, encoding="utf-8", errors="replace").read()[base:]
fast_open = "hover -> panel panel=ops pin=false" in new
out = (WX - 120, ORB[1] + 300)     # 視窗外(x<848)才會 poll-out
swipe(MINI_OPS, out, 20, 0.02)     # 滑離出視窗
time.sleep(1.5)
new2 = open(log, encoding="utf-8", errors="replace").read()[base:]
print(new2.strip() or "(無新 log)")
print("FAST-MINI-OPEN:", "PASS" if fast_open else "FAIL",
      "| COLLAPSE:", "PASS" if "-> orb" in new2 else "FAIL")
