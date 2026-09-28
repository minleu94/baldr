# 個人研究 UI 隔離啟動器（2026-09-28）

## 用途與界線

`scripts/qa_personal_research_ui.py` 供受控 QA 使用：以已固定的 repo-ignored SQLite snapshot 建立一份可寫複本，再以真正的 `ui_qt.main.MainWindow` 啟動個人研究畫面。它不建立預製推薦結果、不啟動排程、不呼叫訓練或升級流程；`prepare` 子命令不建立 `QApplication`，也不顯示視窗。只有明確執行 `launch` 才會顯示主視窗。

固定來源為候選訓練與 lineage 使用的隔離 snapshot：`output/qa/personal_daily_product_20261006/real_source_validation_runs/formal_source_snapshot_v2/twstock.db`，SHA-256 `c99c497657ca4ef63c73e56151d135996e3f2144ec45f8bf4b053eecf8dc5d08`，長度 3,827,728,384 bytes。旁邊的 `snapshot_receipt.json` SHA-256 必須為 `15e1f66f496865f55f97e6e76d1bb291cb1cb842d42d29ee42b7e8905f5b0e83`，且 receipt 內 schema、23 張資料表、逐表筆數及 SQLite `PRAGMA quick_check=ok` 必須相符。這是 quick check，不是完整 `integrity_check`。此 snapshot 是正式 D: 唯讀來源建立的 QA 副本，不是 UI 執行時 source-time trust 自動應綁的路徑。程式拒絕任意 DB 路徑或不符的 receipt。

程式會把來源以一般新檔案複製到新的 QA run root，讀回整份 working DB SHA，並以唯讀 SQLite 連線重驗 schema 與逐表筆數。來源和目的檔案身分必須不同；目的檔案不得是 symlink 或 hardlink。副本路徑由 `TWStockConfig` 真正解析後核對，固定為 `PROFILE=test` 下的 `run_root/data/_test/sqlite/twstock.db`。產品輸出根為 `run_root/output/_test`，個人 policy 檔固定為 `run_root/app_config/personal_use_policy.json`。

個人候選清冊根必須以絕對路徑明確提供，且其 `recommendation_learning` 子目錄已存在並位於 repo-ignored `output/qa/` 之下。它可與產品 run root 同在 `output/qa/` 下，但不得與 run root、固定 snapshot 路徑重疊或互為祖先；正式 D: 路徑會在檢查檔案前即被 QA-root 邊界拒絕。啟動前會在最多 10,000 個項目、單檔 512 MiB、總量 2 GiB 範圍內計算唯讀樹 pin；UI 關閉後再次計算並核對。此 launcher 不會在 learning root 寫入檔案。候選內容及 runtime eligibility 仍由個人候選清冊與既有 consumer 驗證，樹 pin 不取代它們。

產品資料、輸出、policy 與收據工作目錄均限制在 `output/qa/personal_daily_product_20261006/` 內，產品 DB 是固定候選訓練 snapshot 的獨立可寫複本；learning root 是另一個 repo-ignored QA 子樹。launcher 本身不把 `D:/Min/Python/Project/FA_Data` 設為執行根，也不開啟該正式 DB。對真實模型 UI 驗收，推薦頁的「個人研究來源 SQLite」必須明確選用本次 MainWindow 實際使用的隔離 working DB，亦即核實後的 `TWStockConfig.db_file`；不可選正式 D:，也不可拿其父 snapshot 代替 runtime working DB。候選仍須保留由固定訓練 snapshot 產生的原始 candidate／manifest／lineage pins，不搬移、不改寫。每個階段都要以同一 runtime working DB 重新檢查絕對路徑、device/inode 檔案身分與 bounded `source_slice_sha256`：來源 proposal、V2 policy save/readback、consumer/model 呼叫及 canonical save/readback 前後均不得沿用已過期的 preview。若 MainWindow 啟動或操作改變工作資料庫，先重新計算 source slice 並重新驗證政策；任一 path、identity、hash 或 slice 不匹配時立即停止並維持 `rule_only`，不可退回使用固定 snapshot trust 或正式 D:。此項逐階段 trust 綁定已由 m10 的真 MainWindow Qt widget journey 驗證（見本文件 m10 附記）；該驗證僅限隔離工作區，不代表 OS foreground、官方 PIT 或正式資料操作。首次準備需保留至少 snapshot 長度加 1 GiB 空間。失敗的 prepare 可能留下不完整 run root，程式不會自動刪除；請另選新的 run root，不要覆寫或連結舊目錄。

`prepare` 只建立隔離複本，不驗收 UI；`launch` 顯示真正 `MainWindow`。2026-09-28 的 m10 由 `scripts/qa_native_personal_model_acceptance.py` 操作真 Qt widgets 完成個人模型旅程。畫面檔來自 `QWidget.grab()`，不是 OS 前景視窗或桌面截圖；不得將 bounded Qt widget 驗收擴稱為原生桌面證據。操作限制仍是只在推薦分析流程核驗，不按資料更新或其他會連外的操作。

## 操作方式

先設定三個互相隔離的絕對路徑。`run-root` 必須是全新的目錄；`learning-output-root` 是位於共同 repo-ignored `output/qa/` 下的候選 shadow output root，其下必須已存在 `recommendation_learning`，並與 run root、固定來源 snapshot 路徑分離。若 fit/replay 正在寫入候選目錄，請等它自然結束後再執行 `prepare`；launcher 會將候選樹 pin 到 manifest，後續若內容改變就拒絕啟動。policy 路徑必須固定在 run root 的 `app_config` 下。

```powershell
$repo = 'C:\Projects\PythonProjects\technical_analysis'
$run = Join-Path $repo 'output\qa\personal_daily_product_20261006\personal_research_ui\run_20260928_01'
$snapshot = Join-Path $repo 'output\qa\personal_daily_product_20261006\real_source_validation_runs\formal_source_snapshot_v2\twstock.db'
$snapshotReceipt = Join-Path (Split-Path $snapshot) 'snapshot_receipt.json'
$learning = 'C:\Projects\PythonProjects\technical_analysis\output\qa\pc-fit-v7'
$policy = Join-Path $run 'app_config\personal_use_policy.json'
```

第一步只準備隔離複本，不開 UI：

```powershell
.\.venv\Scripts\python.exe scripts\qa_personal_research_ui.py prepare `
  --run-root $run `
  --source-snapshot $snapshot `
  --snapshot-receipt $snapshotReceipt `
  --learning-output-root $learning `
  --policy-config-path $policy
```

`prepare` 成功時會列印 `manifest_path`、working DB SHA、SQLite table count 與 `learning_root_tree_sha256`；逐項核對這些摘要與 `receipts/isolation_manifest.json`、三個實際隔離根都符合預期後，才明確啟動可見 UI：

```powershell
.\.venv\Scripts\python.exe scripts\qa_personal_research_ui.py launch `
  --run-root $run `
  --learning-output-root $learning `
  --policy-config-path $policy
```

`launch` 會重新驗證來源 snapshot receipt、QA working DB bytes/schema/逐表筆數、`PROFILE=test` 實際落點、policy 路徑及 learning tree pin；任一不同就停止，不會退回環境預設正式根目錄。這是隔離啟動檢查，不會自動建立或重用 V2 working-DB trust。模型 UI 驗收仍需在每一個上述階段重新計算 runtime `db_file` 的 path/device+inode/source-slice SHA，並證明 V2 policy 的 source-time binding 與之完全一致；capture-only、rule-only 或 prepare 通過均不足以代表此條件已通過。關閉 UI 後會新增 `receipts/visible_mainwindow_*.json`，記錄程序退出碼與 learning tree 前後 pin。只有 working DB bytes 仍與固定 snapshot 完全相同，才可對同一工作區再次執行此固定-snapshot launcher。UI 初始化或操作若已改動 working DB，launcher 會拒絕重啟；保留舊 run 及收據，另用全新的 `run-root` 執行 `prepare` 和 `launch`，不要覆寫或修補舊工作區。policy 檔可在此 QA run 內由 UI 建立或更新，其他路徑不會被用來補回 policy。

## 測試與限制

已登錄的 `tests/test_qa_research_journey_subprocess.py` 含此入口的 tiny SQLite 複製、PROFILE=test 實際 DB 路徑、create-only、hash mismatch 與 learning tree pin 測試。這些測試只使用暫存資料，不複製 3.8 GiB snapshot、不匯入 Qt 視窗，也不讀寫正式資料。2026-09-28 的 `run_02` working DB 偏離 pin、`run_03` 只啟動視窗，以及 CUA 無 apps/windows 的 `NOT_ACCEPTED_NATIVE_INTERACTION` 均是較早失敗／未驗收證據，保留為歷史。其後全新 m10 run 已通過限定範圍 Qt widget journey；詳見下節與 [m10 驗收報告](PERSONAL_MODEL_QT_WIDGET_ACCEPTANCE_M10_20260928.md)。m10 不證明 OS foreground、桌面截圖、WP1 自然排程、官方 historical PIT 或成熟模型效果。


## 2026-09-28 m10 Qt widget journey

m10 run root 為 `output/qa/personal_daily_product_20261006/personal_research_ui/m10`。隔離 working DB 與固定 source snapshot 均為 3,827,728,384 bytes、SHA-256 `c99c497657ca4ef63c73e56151d135996e3f2144ec45f8bf4b053eecf8dc5d08`；working DB 執行前後穩定，未有 WAL／SHM sidecar。正式 D: DB 未開啟。候選 `rec-cal-3f8b2c276ef316e28de3806d` learning tree 前後 pin 同為 `3b84158f9ab5edb9420fbcbbc427f0d80ea675fa13a5a741a26824fe8d0f1105`，未被寫入。

真 MainWindow 控件完成來源重新檢查、V2 個人研究政策 CAS 保存、推薦執行、canonical 結果保存與 fresh readback、capture v3 保存／讀回，以及 cold restart 後重新驗證、停用、fresh source proposal 的歷史版本回退與最終 `rule_only`。Result ID 為 `rec_26fcc0776bff4c0d85c6c54787202ca8`；capture SHA-256 `b1d2f4d2985b198990e8bf6752743a19235433708225b34f24a68ce9c3936b1d`。19/19 列為 6000 bp active calibrated probability；after-cost 欄位 unavailable，不當成 0。最後 policy revision 4 為 `rule_only`，global pointer 未變。完整收據與 widget render SHA 見 [m10 驗收報告](PERSONAL_MODEL_QT_WIDGET_ACCEPTANCE_M10_20260928.md)。

同一 capture 的 Stage C 為 `completed_with_pending`：mature 0、pending 19，reason `personal_outcome_source_or_cost_incomplete`；outcome artifact 為 null、published 0、global／promotion 為 false。這不代表績效失敗，也沒有成熟績效可宣稱。來源信任仍為 user-declared research-only，`official_historical_pit_verified=false`；本結果不證官方 PIT、正式 promotion、OS desktop 操作或自然 scheduler。
