@echo off
cd /d <REPO_ROOT>\2_Toolkit\Harness\agent_cockpit\collectors
"C:\Users\<USER>\AppData\Local\Programs\Python\Launcher\py.exe" weekly_draft.py >> "%USERPROFILE%\.config\agent_cockpit\collector.log" 2>&1
