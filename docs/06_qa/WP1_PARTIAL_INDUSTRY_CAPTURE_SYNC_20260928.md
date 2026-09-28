# WP1 部分產業 capture 排程同步（2026-09-28）

## 結果

quick scheduled runner 現在會在產業更新回報 `success=false` 且 `partial=true`、並帶有本次非空 capture manifest 清單時，額外執行一次 date-scoped SQLite 同步。同步委派給 `UpdateService.sync_industry_index_captures_to_sqlite`，由既有 service 驗證 receipt、CSV 六欄 projection、交易日期範圍、SQLite transaction 與獨立 readback；失敗時保留既有 CSV／SQLite before-image compensation。

部分同步成功不會把整體 run 改成成功：`update_industry_index` 仍是 failed，terminal status 仍是 `failed`，batch 的 `failed_dates` 留在更新與同步結果，後續 broker、candidate、technical 與完成檢查步驟均不執行。這個分支不呼叫 generic `sync_source_to_sqlite("industry_index")`，也不退回舊 CSV 整份同步。更新失敗但沒有 capture 時完全不呼叫產業同步；成功的 verified no-op 維持原本同步器辨認 marker 後 skipped 的路徑。

## 修改與固定版本

| 檔案 | SHA-256 | 說明 |
| --- | --- | --- |
| `scripts/scheduled/run_daily_data_update_quick.py` | `38fe912825e27ed41d64448f4f19e90d77d852ba747d3d7803d987f7470d6d90` | 僅 partial + nonempty capture 時進 date-scoped sync |
| `tests/test_scheduled_data_update_runner.py` | `b0d14408696adbd64f32948e658096e70aebb08a1460ab908ac071d25230da56` | runner/main、真 UpdateService partial 回傳、隔離 SQLite readback 與終態測試 |

`APPLICATION_MANUAL.md` §4.2 已補充 partial batch 的排程行為。該 Manual 同時承載其他工作包的未提交段落，故表內不以整份 Manual 雜湊代表本 WP1 變更範圍。

## 驗證

在 repository 內新 basetemp `.tmp_w1p5` 執行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_scheduled_data_update_runner.py tests/test_twse_industry_index_capture.py -q -o addopts= --basetemp .tmp_w1p5 -p no:cacheprovider
```

結果為 `38 passed, 1 skipped`，exit 0；唯一 skip 是 Windows 環境不支援該測試所需的 symlink 建立。逐項涵蓋：

- 真 `UpdateService.update_industry` + 隔離 fake batch entrypoint 產生一個成功日期 capture 與一個失敗日期；runner 實際呼叫 scoped service 一次，SQLite readback 只替換成功日期，失敗日期與較早日期仍保留。
- terminal 仍為 `failed`、exit 1、失敗日期可讀、後續 steps 缺席；預置的舊 successful `latest_status` 未被重用。
- 沒有 capture 的 legacy failure 不觸發任一 industry sync；verified no-op 仍沿用 generic verified sync/skipped 語意。
- 相鄰 WP2 capture 路由仍測試 receipt 驗證、marker/readback 與失敗補償。

Targeted 型別檢查：

```powershell
.\.venv\Scripts\python.exe -m mypy --explicit-package-bases scripts/scheduled/run_daily_data_update_quick.py tests/test_scheduled_data_update_runner.py
```

結果 `Success: no issues found in 2 source files`。兩個 Python 檔 `py_compile` 與三個修改檔 `git diff --check` 均 exit 0。完整 pytest log 位於 [scheduled_and_capture_pytest.log](../../output/qa/personal_daily_product_20260928/wp1_partial_industry_sync_01/scheduled_and_capture_pytest.log)，SHA-256 `c9e0a7ee70e0f3ab4bd5bc0c0acfe681c910d828414497343af29dca4db4643b`；結構化收據見 [receipt.json](../../output/qa/personal_daily_product_20260928/wp1_partial_industry_sync_01/receipt.json)。QA 僅使用測試 tmp_path 下的資料根、輸出根與 SQLite；沒有連線或寫入正式行情庫，也沒有執行正式 updater／scheduler。

## 限制

本測試不呼叫網路，也不宣稱實際交易日排程已自然完成；batch entrypoint 是隔離 fixture。實際同步與 readback 使用既有 `UpdateService`。正式來源仍需後續正常排程自身的 capture、SQLite marker 與 terminal receipt 讀回來證明。
