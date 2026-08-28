@echo off
cd /d <REPO_ROOT>\2_Toolkit\Harness\agent_cockpit\collectors
"C:\Users\<USER>\AppData\Local\Programs\Python\Launcher\py.exe" meeting_suggest.py >> "%USERPROFILE%\.config\agent_cockpit\collector.log" 2>&1
"C:\Users\<USER>\AppData\Local\Programs\Python\Launcher\py.exe" jira_mine.py >> "%USERPROFILE%\.config\agent_cockpit\collector.log" 2>&1
"C:\Users\<USER>\AppData\Local\Programs\Python\Launcher\py.exe" jira_enrich.py >> "%USERPROFILE%\.config\agent_cockpit\collector.log" 2>&1
"C:\Users\<USER>\AppData\Local\Programs\Python\Launcher\py.exe" calendar_today.py >> "%USERPROFILE%\.config\agent_cockpit\collector.log" 2>&1
"C:\Users\<USER>\AppData\Local\Programs\Python\Launcher\py.exe" meeting_digest.py >> "%USERPROFILE%\.config\agent_cockpit\collector.log" 2>&1
"C:\Users\<USER>\AppData\Local\Programs\Python\Launcher\py.exe" release_status.py >> "%USERPROFILE%\.config\agent_cockpit\collector.log" 2>&1
"C:\Users\<USER>\AppData\Local\Programs\Python\Launcher\py.exe" dev_progress.py >> "%USERPROFILE%\.config\agent_cockpit\collector.log" 2>&1
