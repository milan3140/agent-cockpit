# -*- coding: utf-8 -*-
"""E2E:注入真滑鼠(mouse_event MOVE|ABSOLUTE)滑到大球→驗 hover 部署→移開→驗收合。"""
import io, sys, time, ctypes, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

SCALE = 1.5
WX, WY, WW = 848, 12, 420          # 視窗 DIP bounds(boot log)
ORB_DIP = (WX + WW - 20 - 22, WY + 20 + 22)   # orbWrap right:20px top:20px, 45px 中心
ctypes.windll.user32.SetProcessDPIAware()   # 不宣告會拿到虛擬化 1280x720,正規化座標全飛
SW, SH = ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
print("screen(phys):", SW, "x", SH)

def move(px, py):
    nx, ny = int(px * 65535 / SW), int(py * 65535 / SH)
    ctypes.windll.user32.mouse_event(0x8000 | 0x0001, nx, ny, 0, 0)

def move_path(x0, y0, x1, y1, steps=25, dt=0.02):
    for i in range(steps + 1):
        move(x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps)
        time.sleep(dt)

log = os.path.expanduser("~/.config/agent_cockpit/ui.log")
base = os.path.getsize(log)

ox, oy = ORB_DIP[0] * SCALE, ORB_DIP[1] * SCALE
move_path(ox - 500, oy + 400, ox, oy)      # 從遠處滑進大球
time.sleep(1.2)
move_path(ox, oy, ox - 600, oy + 500)      # 滑離
time.sleep(1.5)

new = open(log, encoding="utf-8", errors="replace").read()[base:]
print(new.strip() or "(無新 log)")
ok_in = "orb -> hover" in new
ok_out = "-> orb" in new
print("HOVER-DEPLOY:", "PASS" if ok_in else "FAIL", "| COLLAPSE:", "PASS" if ok_out else "FAIL")
