@echo off
rem 跨機 lane 回報(A 機每小時跑;B 機不需要——它自己就是主機)
rem 若你的 Python launcher 路徑不同,改下面那行
cd /d %~dp0
"C:\Users\<USER>\AppData\Local\Programs\Python\Launcher\py.exe" lane_report.py --push >> "%USERPROFILE%\.config\agent_cockpit\collector.log" 2>&1
if errorlevel 1 py lane_report.py --push >> "%USERPROFILE%\.config\agent_cockpit\collector.log" 2>&1
