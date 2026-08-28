' 以完全隱藏的視窗執行參數指定的批次檔(Task Scheduler 直接跑 .cmd 會彈 console)
' 用法: wscript.exe run_hidden.vbs <path-to-cmd>
Set sh = CreateObject("WScript.Shell")
sh.Run """" & WScript.Arguments(0) & """", 0, False
