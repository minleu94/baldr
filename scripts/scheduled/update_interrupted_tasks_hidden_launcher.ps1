param([ValidateSet('DryRun','Apply')][string]$Mode = 'DryRun')
# 只修改四個已存在且未執行的 Task action；不觸發 Task、不改 trigger／權限。
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$pythonw = Join-Path $repoRoot '.venv\Scripts\pythonw.exe'
$launcher = Join-Path $PSScriptRoot 'run_scheduled_cmd_hidden.py'
if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf) -or -not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw '缺少既有 pythonw 或 launcher。' }
$names = @('baldr-ml-direct-chain-maintainer','baldr-paper-portfolio-daily','baldr-pit-sector-membership-preopen-capture-daily','baldr-ml-allocation-forward-daily')
$cmdByTask = @{
    'baldr-ml-direct-chain-maintainer'='run_ml_direct_chain_maintenance.cmd'
    'baldr-paper-portfolio-daily'='run_paper_portfolio_daily.cmd'
    'baldr-pit-sector-membership-preopen-capture-daily'='run_pit_sector_membership_preopen_capture.cmd'
    'baldr-ml-allocation-forward-daily'='run_ml_allocation_forward_daily.cmd'
}
$scheduler = New-Object -ComObject 'Schedule.Service'
$scheduler.Connect()
$folder = $scheduler.GetFolder('\')
$backupRoot = Join-Path $repoRoot ('output\qa\schedule_hidden_launcher_' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ'))
foreach ($name in $names) {
    $task = $folder.GetTask($name)
    if ($task.State -eq 4) { throw "執行中的 Task 不修改：$name" }
    $before = $task.Xml
    $beforeLastRun = $task.LastRunTime
    $beforeAcl = $task.GetSecurityDescriptor(4)
    [xml]$xml = $before
    $ns = [System.Xml.XmlNamespaceManager]::new($xml.NameTable)
    $ns.AddNamespace('t', $xml.DocumentElement.NamespaceURI)
    $exec = $xml.SelectSingleNode('/t:Task/t:Actions/t:Exec', $ns)
    if ($null -eq $exec -or $xml.SelectNodes('/t:Task/t:Actions/*', $ns).Count -ne 1) { throw "Task action 不符合單一 Exec：$name" }
    $expectedArgs = '/c "' + (Join-Path $PSScriptRoot $cmdByTask[$name]) + '"'
    $hiddenArgs = '"' + $launcher + '" --task ' + $name
    if (-not (([string]$exec.Command -eq 'cmd.exe' -and [string]$exec.Arguments -eq $expectedArgs) -or
        ([string]$exec.Command -eq $pythonw -and [string]$exec.Arguments -eq $hiddenArgs))) { throw "Task 既有 action 與固定來源不符，不覆寫：$name" }
    if ($xml.SelectSingleNode('/t:Task/t:Principals/t:Principal/t:LogonType', $ns).InnerText -ne 'InteractiveToken') { throw "Task 登入類型不可改寫：$name" }
    foreach ($field in @('Command','Arguments','WorkingDirectory')) {
        $node = $exec.SelectSingleNode("t:$field", $ns)
        if ($null -eq $node) { $node = $xml.CreateElement($field, $xml.DocumentElement.NamespaceURI); [void]$exec.AppendChild($node) }
        $node.InnerText = switch ($field) { 'Command' { $pythonw }; 'Arguments' { '"' + $launcher + '" --task ' + $name }; 'WorkingDirectory' { $repoRoot } }
    }
    if ($Mode -eq 'DryRun') { [pscustomobject]@{Task=$name;Command=$pythonw;Arguments=$exec.Arguments;Mode=$Mode}; continue }
    if ($Mode -ne 'Apply') { throw '只有明示 Apply 可保存與修改 Task；DryRun 已於前一行結束本次迴圈。' }
    if (-not (Test-Path -LiteralPath $backupRoot)) { [void](New-Item -ItemType Directory -Path $backupRoot) }
    $taskBackup = Join-Path $backupRoot $name
    [void](New-Item -ItemType Directory -Path $taskBackup)
    [IO.File]::WriteAllText((Join-Path $taskBackup 'before.xml'), $before)
    [IO.File]::WriteAllText((Join-Path $taskBackup 'before.sddl'), $beforeAcl)
    # UPDATE | DONT_ADD_PRINCIPAL_ACE | IGNORE_REGISTRATION_TRIGGERS。
    [void]$folder.RegisterTask($name, $xml.OuterXml, 52, $null, $null, 3, $null)
    $updated = $folder.GetTask($name)
    $after = $updated.Xml
    [xml]$oldNormalized = $before
    [xml]$newNormalized = $after
    [void]$oldNormalized.Task.RemoveChild($oldNormalized.Task.Actions)
    [void]$newNormalized.Task.RemoveChild($newNormalized.Task.Actions)
    $onlyActionChanged = $oldNormalized.OuterXml -eq $newNormalized.OuterXml
    $aclPreserved = $beforeAcl -eq $updated.GetSecurityDescriptor(4)
    [IO.File]::WriteAllText((Join-Path $taskBackup 'after.xml'), $after)
    $receipt = [ordered]@{Task=$name;ObservedAt=[DateTime]::UtcNow.ToString('o');OnlyActionChanged=$onlyActionChanged;AclPreserved=$aclPreserved;TaskManuallyStarted=$false;LastRunBefore=$beforeLastRun;LastRunAfter=$updated.LastRunTime;Backup=$taskBackup}
    $receipt | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskBackup 'update.json')
    if (-not $onlyActionChanged -or -not $aclPreserved) { throw "更新後契約核對失敗，原 XML／ACL 已保存：$taskBackup" }
    [pscustomobject]$receipt
}
