param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [string]$DecisionDate = (Get-Date -Format "yyyy-MM-dd"),
    [string]$DataRoot = $env:DATA_ROOT,
    [string]$OutputRoot = $env:OUTPUT_ROOT,
    [string]$DbPath = "",
    [string]$Sources = "all",
    [string]$PaperEvidenceOperationRoot = "",
    [string]$PaperEvidenceLedgerDb = "",
    [string]$PaperEvidenceHealthStatusPath = "",
    [string]$PaperEvidenceHealthBaseline = "",
    [string]$PaperEvidenceStatusPath = "",
    [string]$PaperHealthSourceOutput = "",
    [string]$PaperHealthForwardBinding = "",
    [string]$PaperHealthPolicySource = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    $DataRoot = "D:\Min\Python\Project\FA_Data"
}
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $DataRoot "output"
}
if ([string]::IsNullOrWhiteSpace($DbPath)) {
    $DbPath = Join-Path $DataRoot "sqlite\twstock.db"
}
if ([string]::IsNullOrWhiteSpace($PaperEvidenceOperationRoot)) {
    $PaperEvidenceOperationRoot = Join-Path $RepoRoot "output\paper_execution_eod_replay"
}
if ([string]::IsNullOrWhiteSpace($PaperEvidenceHealthBaseline)) {
    $PaperEvidenceHealthBaseline = Join-Path $OutputRoot "position_health\latest.json"
}
if ([string]::IsNullOrWhiteSpace($PaperEvidenceLedgerDb)) {
    $PaperEvidenceLedgerDb = Join-Path $PaperEvidenceOperationRoot "paper_trade_ledger.sqlite"
}
if ([string]::IsNullOrWhiteSpace($PaperEvidenceHealthStatusPath)) {
    $PaperEvidenceHealthStatusPath = Join-Path $PaperEvidenceOperationRoot "scheduled\paper_portfolio_isolated\latest_status.json"
}
if ([string]::IsNullOrWhiteSpace($PaperEvidenceStatusPath)) {
    $PaperEvidenceStatusPath = Join-Path $PaperEvidenceOperationRoot "scheduled\paper_portfolio_isolated\latest_status.json"
}
if ([string]::IsNullOrWhiteSpace($PaperHealthSourceOutput)) {
    $PaperHealthSourceOutput = Join-Path $OutputRoot "position_health_sources"
}
if ([string]::IsNullOrWhiteSpace($PaperHealthForwardBinding)) {
    $PaperHealthForwardBinding = Join-Path $RepoRoot "output\forward_position_thesis\bindings"
}
if ([string]::IsNullOrWhiteSpace($PaperHealthPolicySource)) {
    $PaperHealthPolicySource = Join-Path $RepoRoot "output\formal_daily_publications\rule_source\scheduler\rule_source_latest_status.json"
}

$Today = Get-Date -Format "yyyy-MM-dd"
if ($DecisionDate -ne $Today) {
    throw "Scheduled evidence wrapper only accepts today's natural decision date ($Today); received $DecisionDate."
}

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

$PythonArgs = @(
    (Join-Path $RepoRoot "scripts\scheduled\run_scheduled_evidence_pipeline_dry_run.py"),
    "--dry-run",
    "--bind-scheduled-recommendation",
    "--refresh-paper-health",
    "--bind-forward-thesis",
    "--produce-position-health-sources",
    "--evaluate-position-health-transition",
    "--run-exit-effectiveness",
    "--db-path", $DbPath,
    "--data-root", $DataRoot,
    "--output-root", $OutputRoot,
    "--sources", $Sources,
    "--paper-evidence-operation-root", $PaperEvidenceOperationRoot,
    "--paper-evidence-ledger-db", $PaperEvidenceLedgerDb,
    "--paper-evidence-health-status-path", $PaperEvidenceHealthStatusPath,
    "--paper-evidence-health-baseline", $PaperEvidenceHealthBaseline,
    "--paper-evidence-status-path", $PaperEvidenceStatusPath,
    "--paper-health-source-output", $PaperHealthSourceOutput,
    "--paper-health-forward-binding", $PaperHealthForwardBinding,
    "--paper-health-policy-source", $PaperHealthPolicySource
)

$Output = & $Python @PythonArgs 2>&1
$ExitCode = $LASTEXITCODE
$Output | Write-Output
exit $ExitCode
