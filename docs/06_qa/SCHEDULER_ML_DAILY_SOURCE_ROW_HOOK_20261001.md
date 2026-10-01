# ML 日常研究來源列投影排程接線 QA（2026-10-01）

## 範圍與狀態

本批只接線既有的 prospective daily-price candidate 與 `ml_daily_source_row_research_projection` API，修改排程 runner、wrapper 與其 focused tests，沒有變更來源資料 schema、Raw builder、Direct/OOC、revision gate、pointer、訓練或資料庫寫入。研究候選只寫入 repo 內 `output/qa/ml_daily_source_row_research_projections/<source-date>/<projection-id>/`；不寫正式 `D:` 資料根目錄。

`run_ml_raw_pit_refresh.cmd` 預設同時啟用 `--capture-prospective-daily-price-candidate` 與 `--project-daily-source-rows`。設定 `BALDR_ENABLE_ML_DAILY_SOURCE_ROW_PROJECTION=0` 只停用來源列投影；設定既有 `BALDR_ENABLE_ML_PROSPECTIVE_DAILY_CAPTURE=0` 會一併停用 capture 與依賴它的投影。CLI 直接執行時，兩個旗標皆可選擇啟用；只傳 `--project-daily-source-rows` 會被 parser 拒絕。

接線只在 runner 已取得 core freshness proof 後執行。Capture 必須回報 `captured` 或 `already_captured`，且其 candidate readback、manifest、capture receipt、source hash、雙市場範圍及研究／Formal 排除旗標通過驗證，才會呼叫 projection API。Capture 未完成或驗證失敗時不做投影。投影 API 必須回報 `completed_research_only`；其中間 `completion_receipt.json` 的 `awaiting_terminal_revision_validation` 只表示投影寫入完成，runner 會另建 terminal verification receipt 並讀回驗證後，才把 status 標為 `projected_research_only`。

Runner status 的 `prospective_daily_source_row_projection` 是新增的研究狀態欄位，預設 status 仍位於 `<output-root>/scheduled/ml_raw_pit_refresh/latest_status.json`。成功狀態包含 candidate、capture receipt、projection manifest、中間完成收據、observations 與 terminal receipt 的路徑／SHA，以及投影列數與實際驗證時間。Terminal receipt 位於該 projection candidate 內的 `runner_terminal_verification_receipt.json`，採 bounded、no-link、create-only 寫入、fsync 和完整讀回；碰到既有檔案不覆寫、不刪除、不重試。

## 綁定與失敗語意

Runner 對 capture manifest、capture receipt、projection manifest、中間完成收據及 observations 執行 bounded、no-link 讀取。它比對候選識別、source date、正式／研究旗標、來源窗口與市場 revision digest；實際串流 observations bytes 計算 SHA-256、byte 數及 JSONL 列數，並要求與 projector result、manifest 和 completion receipt 的聲明完全相同。Projection 時序須滿足 candidate availability ≤ projection start ≤ completion start ≤ API verification completion ≤ terminal receipt materialization/readback completion；缺時間、倒退或未來時間皆拒絕成功狀態。

六個 copied-input 檔案的原始 bytes 驗證由 projection API 負責。Runner 會把 API manifest 的六個 `input_files` 宣告 hash 與已驗證 capture pins 對照，但不會在 hook 再讀一次這六個 copied-input 檔案本體；QA 不將此描述為 runner 獨立重驗六份 bytes。Runner 另會對 candidate manifest、capture receipt、projection manifest、completion receipt 與 observations 做 bounded readback／hash 驗證。

Projection 發生任何錯誤時，狀態只新增 `rejected` 及錯誤診斷；capture 失敗時為 `not_run_capture_not_verified`。兩種情況都保留既有 Raw core、source-revision hold、正式 gate 與 exit code 的判斷，不把 research projection 成功當成 source revision 通過。pending、成功及失敗狀態均保留 `research_only=true`、`candidate_only=true`、`formal_credit=false`、`historical_pit_eligible=false`、`formal_source_contract_eligible=false`、`formal_oos_allowed=false`、`features_included=false`、`labels_included=false` 及 `model_use_claimed=false`。成功的 terminal verification receipt 另記 `direct_ooc_compatible=false`。

## 驗證結果

- `pytest tests/test_scheduled_ml_raw_pit_refresh.py -q -o addopts= -p no:cacheprovider -rs`：46 passed、1 skipped。唯一 skip 為 Windows symlink privilege 不可用（WinError 1314）；hardlink、超 byte cap、hash drift、receipt collision、capture 失敗、projection 失敗及 CLI 旗標依賴均有測試。Wrapper 控制流另以短暫隔離 repo 執行三種 Windows fake-child 情境：預設傳入 capture+projection、projection opt-out 僅傳 capture、capture opt-out 不傳兩旗標；三種情境皆確認 child argv 並保留 child exit code 17。測試不執行正式 runner。
- `python -m py_compile scripts/scheduled/run_ml_raw_pit_refresh.py tests/test_scheduled_ml_raw_pit_refresh.py`：通過。
- `python -m mypy scripts/scheduled/run_ml_raw_pit_refresh.py`：通過，1 source file。
- 成功路徑測試使用隔離 fixture 與 stub projector，核對 API 完成後才建立並驗證 terminal receipt，且後續 source-revision hold 照原結果保留。這是 hook 編排測試，不是正式 wrapper 的端到端執行。

本批沒有執行正式 `.cmd`、自然 Task、HTTP capture、資料庫寫入或訓練。Projection API 先前的獨立候選驗收不代表本 wrapper hook 已完成自然排程驗收；Hook 的自然執行仍待未來排程收據確認。此研究投影不提供 PIT 或 Formal credit。
