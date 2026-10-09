# F12 月營收 durable raw archive v2 驗證

本文件記錄 durable archive v2 候選實作的合成來源驗證。這是交 Root 審閱的葉片證據，不代表 F12 全母體查詢、UI、收藏或產品整合已完成。

## 驗證範圍

`DailyMarketMonthlyRevenueReadSessionV1.archive_source()` 發行 v2 typed source reference；`open_exact_archived()` 只從已封存的 snapshot、raw HTML／CSV archive 與原 finished ledger 建立新 operation。每次重開使用新的 operation/session identity，原 source clock、cutoff、declared cohort、財務 facts 與 fact identities 保持原值。來源仍標記 `current_observed_only`、availability `unknown`，historical／formal PIT 均為 `false`。

V1 `open_exact()` 的 live source 精確重驗路徑保留。V2 不以目前 DB 路徑、目前 raw capture 路徑、最新資料或自我雜湊的 JSON 取代 archived bytes；saved snapshot、archive manifest、raw files、operation copy 的 pins 與 reparse／hardlink guard 仍須通過。原始 live DB 與 capture 只作 provenance pin，不在重開時 SQLite-open。

## 測試證據

最後完整 exact-reopen 執行使用唯一 synthetic basetemp `C:/t/f12-monthly-v2-final-20261009-l`：`tests/test_daily_market_monthly_revenue_exact_reopen_v1.py` 為 **16 passed、1 skipped**。skip 僅是 Windows 環境無法建立一般 file symlink；同檔的真 Windows directory-junction 案例已通過：改接歷史來源祖先後仍可從 archive 重開，archive root 與 operation root 的 junction 則在 SQLite connect 前拒絕。hardlink、封存檔竄改、manifest／capture 遺失、重簽錯誤 archive root，以及混搭不同 snapshot/archive 版本均有負例。

同版其他回歸：

- `tests/test_baldr_completion_p03_sources.py`：**32 passed**。
- `tests/test_fundamental_read_snapshot_lifecycle.py`：**5 passed**。
- 四個來源模組 mypy：**無錯誤**；五個變更 Python 檔 `py_compile` 通過。
- `git diff --check` 通過；Git 僅回報既有 LF/CRLF 工作目錄提示與 fsmonitor IPC 警告。

跨程序正例在更新 live DB 後，以及移走整個歷史 source ancestor 後，均由 fresh child PID 以同一保存 reference 讀出原 facts；junction 正例則將舊來源路徑改接至 synthetic decoy。測試核對 saved snapshot、archive、移走的原 source 與 decoy 的檔案內容／stat，並確認 SQLite 只開啟新 operation 內的 reader copy。attempt 中若封存驗證失敗或來源 pin 不符，不會發行 finished cohort。

## 本次修正與限制

Archived reopen 不對歷史 source DB／monthly source 路徑做實體 ancestor `lstat`，也不以 provider 目前 resolve 後的 `db_file` 取代保存 reference 內的 source path。`FundamentalReadSnapshotSession.finish()` 的 archived 分支改用 `_RawArchiveVerificationRoots` 傳遞 `output_root` 與保存 reference 的原始 monthly root 詞法身分，不再呼叫 `_clone_provider_for_reader()`。`_verify_raw_archive_reference()` 仍依保存的 source clock、finished manifest、archive manifest、raw pins、snapshot bytes、cohort 與 fact ledger 做完整比對；新 snapshot/archive/private operation 路徑仍檢查實體存在、reparse、hardlink、bytes、hash 與隔離邊界。非 archived V1 `finish()` 路徑與全域 provider constructor 未變。

完整測試曾先揭露 V1 exact verifier 呼叫 bounded inventory 時漏傳 `cancel_callback`；已補回 callback 傳遞，完整 V1／WAL／V2 回歸隨後通過。先前失敗 attempts 保留在各自 `C:/t/f12-*` 隔離目錄，不以刪除失敗證據換取通過。

## Archived `finish()` 歷史路徑與發行窗口回歸

新增 `test_archived_finish_does_not_resolve_or_lstat_historical_source_paths`：在 archived session 已由封存內容開啟並載入資料後，攔截 `Path.resolve()`／`Path.lstat()`。陷阱涵蓋歷史 DB、其 sidecars、專屬 DB parent、原 raw root 與封存 reference 所列的歷史 capture。測試先故意對歷史 DB 呼叫兩個方法，確認陷阱確實會拒絕，再清空命中記錄執行 `finish()`；執行期間歷史路徑命中數為零，finished cohort、來源內容 identity 與 processed cohort 仍與原保存來源一致。

獨立審查中的 archive 發行窗口 probe 已正式納入測試，以四種 mutation 覆蓋 `raw_source_archive.json` 寫入後、reference 發行前的 source 漂移：新增原本不存在的 SQLite `-wal`、`-shm`、`-journal` sidecar，以及修改原始 monthly HTML。四例都須由 public `archive_source()` 以具名 source/capture pin error 拒絕，且不得留下已發行的 archived reference。這些測試只使用 `tests/test_daily_market_monthly_revenue_read_session_v1.py::_seed_provider` 建立的隔離合成來源。

前一版定向全路由使用唯一 basetemp `C:/t/f12-finish-full-20261009-b`，exact reopen、P03 sources 與 snapshot lifecycle 三檔結果為 **58 passed、1 skipped，11.16 秒**。唯一 skip 是此 Windows 環境無法建立一般 file symlink；Windows directory-junction 案例另有實際正反例。

其後追加三層 archived cancellation 覆蓋：預取消的 exact open 不建立 operation root、不呼叫 SQLite，且 live source、saved snapshot、raw archive inventory 前後相同；在 revenue wrapper 已完成底層 snapshot finish 後取消，wrapper 不發行 revenue cohort 並關閉 reader；在底層 archived snapshot `finish()` 中，刻意於 `_verify_raw_archive_reference()` 返回後、snapshot publication 前提出取消，具名取消錯誤使 snapshot reference 不可取得、reader 關閉，原 live source、saved snapshot 與 archive inventory 不變。第三層才是底層 archived snapshot finish 的取消證據；第二層明確是外層 revenue wrapper 的取消。

新增三層案例的 targeted 執行使用 `C:/t/f12-archived-cancel-20261009-e`：**3 passed、22 deselected，1.22 秒**。最後 exact reopen、P03 sources 與 snapshot lifecycle 全路由執行使用唯一 basetemp `C:/t/f12-finish-full-20261009-d`：**61 passed、1 skipped，12.05 秒**；完整輸出保存在 `output/qa/f12_archived_finish_no_historical_resolve_20261009_a/attempt12_final_exact_p03_lifecycle_with_cancel.log`。定向來源 mypy 五個檔案無錯誤，py_compile 通過。`git diff --check` exit 0；Git 另顯示既有 fsmonitor IPC 警告與 LF/CRLF 工作目錄提示。

修正過程中的 attempt 01 為 **1 passed、4 failed**：歷史路徑陷阱已通過；四種 mutation 都被拒絕，但測試錯把 public revenue wrapper 的 `DailyMarketMonthlyRevenueReadSessionError` 當作底層 `FundamentalReadSnapshotError`，未匹配正確 exception layer。attempt 07／08 分別因 sandbox `C:\t` WinError 5 與 OS Temp 深巢狀路徑 WinError 3，在測試 assertions 前無法建立 basetemp／fixture；attempt 09 的第一個 cancellation 測試在驗證通過後讀錯 finished-cohort 的 `.finished` 屬性；attempt 10 的底層取消案例已正確取消並清理，但測試預期錯誤碼字串。各次摘要與 logs 都保留在 `output/qa/f12_archived_finish_no_historical_resolve_20261009_a/`，沒有以重跑覆寫失敗證據。

## 交 Root 審閱的來源版本

| 檔案 | SHA-256 |
|---|---|
| `data_module/fundamental_read_copy_contract.py` | `43A6E1992CE41887193784ECE9664FECD1E41906F12540F22FC3C072BDDBD422` |
| `data_module/selection_fact_readers.py` | `1002A16E5D9F00FD7C9F825EE3913C819BB4D7F8CE2F621D77BBBEF9A2A32EB1` |
| `data_module/fundamental_read_snapshot.py` | `74BF6146B52D2F548EEBC8A71643299C87047CDF8BA5F7516BEDFFA7B571EFE1` |
| `data_module/daily_market_monthly_revenue_read_session_v1.py` | `A3800EAF2AAC7247BAE45BE85DEE80C2C8F3599E0E282E3AAAEC2240A42B01C5` |
| `tests/test_daily_market_monthly_revenue_exact_reopen_v1.py` | `CA2570F58071F4E582E15C35868AED5E13F5433215DF2FAFF29714961BC7C3D2` |

此候選不宣稱正式來源、producer、UI、全母體 F12 query、bookmark、performance 或真人驗收完成；未連線正式資料，也未執行網路請求或更新排程。
