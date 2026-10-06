# Phase3C 2026-09-11 candidate 法人修復 runbook

本工具只處理隔離的 `phase3c_candidate.db` 之 `institutional_flows`、2026-09-11。它不接受正式 DB、不呼叫正式 producer，也不把候選資料授權給下游研究或交易流程。

## 證據與時間語意

- capture manifest、TWSE/TPEx raw payload、metadata 會在 plan receipt 下以原始 bytes 複製保存並驗證 SHA-256。
- row 的 `first_observed_at` 與 `available_at` 使用 capture 實際完成時間。這批資料是 2026-09-24 capture，不能宣稱 2026-09-11 當時已可得。
- 原有 32 個 material update 的 before row 會封存至 `phase3c_candidate_institutional_history`；after row 與 5 個 insert 也會留下 valid-from，`history` 子命令可依 custody timestamp 查回。

## 先建立 plan（唯讀 target DB）

```powershell
& .\.venv\Scripts\python.exe scripts\repair_phase3c_candidate_institutional.py plan `
  --capture-manifest 'C:\Projects\PythonProjects\technical_analysis\output\qa\phase3c_20260911_repair_capture\runs\20260924T213801985664Z\manifest.json' `
  --candidate-db 'D:\Min\Python\Project\FA_Data_candidate\phase3c_candidate.db' `
  --production-data-root 'D:\Min\Python\Project\FA_Data' `
  --formal-db 'D:\Min\Python\Project\FA_Data\sqlite\twstock.db' `
  --receipt-dir 'D:\Min\Python\Project\FA_Data_candidate\repair_receipts\20260924_20260911_institutional_run01'
```

plan 必須固定得到 21,479 source rows、32 UPDATE、5 INSERT、37 operations；任何 manifest/raw hash、ledger semantic hash、candidate preimage、非目標 table、observation ledger 或 checkpoint 漂移都 fail closed。plan 會保存 before/after row hash、logical snapshot、操作明細、capture raw/metadata copy 與 custody summary。

## apply 與 rollback（需 owner 審核後才可執行）

apply 會先建立 SQLite online backup，再複製 staging DB 驗證 37 operations、history、非目標 scope、observation ledger 與 checkpoint；只有 staging 成功後才在 candidate DB `BEGIN IMMEDIATE` 重驗 preimage 並提交。checkpoint 只在 rows 與 scope 驗證後才寫成 `SUCCESS`。

```powershell
& .\.venv\Scripts\python.exe scripts\repair_phase3c_candidate_institutional.py apply `
  --plan 'D:\Min\Python\Project\FA_Data_candidate\repair_receipts\20260924_20260911_institutional_run01\plan.json' `
  --confirm 'apply-phase3c-candidate-repair-20260911' `
  --production-data-root 'D:\Min\Python\Project\FA_Data' `
  --formal-db 'D:\Min\Python\Project\FA_Data\sqlite\twstock.db'
```

rollback 不以整個 DB backup 覆蓋 target。它會在 `BEGIN IMMEDIATE` 逐一比對本輪 after row，回復 32 UPDATE、刪除 5 INSERT、回復本輪 checkpoint 並刪除本輪 history rows；若本輪 rows 或 checkpoint 已被其他流程改寫，就拒絕執行。

```powershell
& .\.venv\Scripts\python.exe scripts\repair_phase3c_candidate_institutional.py rollback `
  --receipt 'D:\Min\Python\Project\FA_Data_candidate\repair_receipts\20260924_20260911_institutional_run01\receipt.json' `
  --confirm 'rollback-phase3c-candidate-repair-20260911' `
  --production-data-root 'D:\Min\Python\Project\FA_Data' `
  --formal-db 'D:\Min\Python\Project\FA_Data\sqlite\twstock.db'
```

唯讀查回 history：

```powershell
& .\.venv\Scripts\python.exe scripts\repair_phase3c_candidate_institutional.py history `
  --candidate-db 'D:\Min\Python\Project\FA_Data_candidate\phase3c_candidate.db' `
  --as-of '2026-09-24T21:38:05+00:00' `
  --stock-code 2049
```
