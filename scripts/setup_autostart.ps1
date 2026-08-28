# Setup Windows Task Scheduler for Daily Committer
$TaskName = "TakneeDailyCommitter"
$PythonPath = (Get-Command python).Source
$ScriptPath = "E:\taknee-ide\scripts\daily_committer.py"

Write-Host "[*] Configuring Scheduled Task: $TaskName"
Write-Host "    Python: $PythonPath"
Write-Host "    Script: $ScriptPath"

# Action to run python in the background
$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument "`"$ScriptPath`"" -WorkingDirectory "E:\taknee-ide"

# Trigger daily at 12:00 PM and on logon
$TriggerDaily = New-ScheduledTaskTrigger -Daily -At "12:00PM"
$TriggerLogon = New-ScheduledTaskTrigger -AtLogOn

$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

# Register or update
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger @($TriggerDaily, $TriggerLogon) -Principal $Principal -Force

Write-Host "[+] Successfully registered '$TaskName'!"
Write-Host "    The committer will run daily in the background and push small real commits."
