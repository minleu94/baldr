param([string]$ReceiptPath)
# 只啟用排程事件日誌；不清除日誌、不啟動或修改 Task。
$ErrorActionPreference = 'Stop'
$target = $null
if ($ReceiptPath) {
    $qaRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\output\qa')) + [IO.Path]::DirectorySeparatorChar
    $target = [IO.Path]::GetFullPath($ReceiptPath)
    if (-not $target.StartsWith($qaRoot, [StringComparison]::OrdinalIgnoreCase)) { throw '收據只能保存到本專案 QA。' }
    if (Test-Path -LiteralPath $target) { throw '收據已存在，不覆寫。' }
    if (-not (Test-Path -LiteralPath ([IO.Path]::GetDirectoryName($target)) -PathType Container)) { throw '收據目錄不存在。' }
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw '請用系統管理員 PowerShell 執行；Windows 要求管理員權限才能啟用此日誌。'
}
$before = Get-WinEvent -ListLog 'Microsoft-Windows-TaskScheduler/Operational'
wevtutil sl Microsoft-Windows-TaskScheduler/Operational /e:true
if ($LASTEXITCODE -ne 0) { throw '無法啟用排程事件日誌。' }
$after = Get-WinEvent -ListLog 'Microsoft-Windows-TaskScheduler/Operational'
if (-not $after.IsEnabled) { throw '啟用回讀失敗。' }
if ($ReceiptPath) {
    $receipt = [ordered]@{ObservedAt=[DateTime]::UtcNow.ToString('o');BeforeEnabled=$before.IsEnabled;AfterEnabled=$after.IsEnabled;EventsCleared=$false;TasksStarted=$false}
    $stream = [IO.File]::Open($target, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
    $writer = [IO.StreamWriter]::new($stream, [Text.UTF8Encoding]::new($false))
    try { $writer.Write(($receipt | ConvertTo-Json)) } finally { $writer.Dispose() }
}
$after | Select-Object IsEnabled, RecordCount
