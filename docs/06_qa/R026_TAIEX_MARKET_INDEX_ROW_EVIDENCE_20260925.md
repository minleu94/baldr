# R026 TAIEX 大盤列證據 bounded slice（2026-09-25）

## 範圍

本切片為 quick/scheduled 路徑增加明確 TWSE `FMTQIK` 與 `MI_5MINS_HIST` capture
handoff，並以獨立 TAIEX publisher 將完整 `market_index.csv` 同步到 SQLite。writer 只替換
`(指數名稱='TAIEX', 日期)` 對應列，保留同日其他指數名稱；CSV 存在的歷史 TAIEX 列仍會
同步，但只有本次成功 capture 且逐欄符合 CSV 與 SQLite readback 的日期可產生 row evidence。

`DataLoader.update_market_index()` 的公開布林回傳保持不變；capture 路徑只有 CSV 發布成功後
才回傳給呼叫端。quick runner 將同一次 update 的 capture manifest 傳給專用 publisher，舊
service double 仍使用原同步介面。formal market guard 在任何 TAIEX row mutation 前執行，並以
`replace_dates=True` 驗證完整受保護欄位；此選項只驗證，不執行日期級刪除。publisher 的
keyed delete/insert 在一個 SQLite transaction 內完成，移除該 TAIEX 日期上 CSV 未提供的舊
動態欄位，同時保留 sibling row。缺少 `日期`／`指數名稱` 複合鍵欄位時明確拒絕。

## 證據語意與限制

- `first_observed_at` 沿用 capture manifest 的時區明確 `captured_at`，表示本機首次觀測時間；
  TWSE 原始資料未提供可驗證的發布時間，因此 `source_published_at` 固定為 `null`。
- 這是前瞻 capture，`historical_pit` 固定為 `false`；不把交易日期當作來源發布時間，也不
  宣稱歷史 point-in-time 證據。
- evidence reader 重新驗 manifest、兩份 raw report、CSV bytes、SQLite row values 與同次
  `SELECT value, typeof(value)` 的 SQLite storage type。SQLite 現有 REAL 欄位只代表該儲存邊界
  的數值表示，不代表原始 Decimal bytes 完全相同。
- CSV、SQLite 與 create-only sidecar 是跨資源步驟，沒有原子交易或 durable generation 保證。
  row evidence 只表示發布當下讀回相符；後續 reader 會重新驗證，漂移則回 `unknown`。sidecar
  寫入失敗不會把已成功的 CSV/SQLite 同步改報失敗。
- generic `sync_source_to_sqlite('market_index')` 的舊行為未由本切片修改；其他呼叫端不因此
  自動採用專用複合鍵 publisher。R028 technical publication owner 仍維持 BLOCKED；R026/TMP-ML-01
  及整體來源身分工作未完成。

## 驗證收據

fresh synthetic TEMP，`PROFILE=test`、`PYTHONUTF8=1`：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_taiex_market_index_publication.py tests/test_formal_market_data_repair.py tests/test_official_market_daily.py tests/test_scheduled_data_update_runner.py -q -o addopts= --basetemp=C:\t\taiexg5
```

最後一次 fresh TEMP 路由結果為 **63 passed**；pytest log 位於
`C:\t\taiexg5\pytest.log`，SHA-256：
`4C9E5C91C38A85B72454E43A44CB91719667DBA37A43831A1FD3D0BA2DC30ADA`。真實排程整合案例走過
`UpdateService.update_market()` 的動態 batch 載入、synthetic official calendar、真 `DataLoader`
capture sink、同一 capture list 與 quick runner 的 specialized publisher；TWSE 月報 HTTP 與
calendar I/O 均以合成資料隔離。路由也包含正常 TWSE 月報，以及正式市場 guard 三個 TAIEX 案例
（正常受保護列、stale row、缺少受保護欄位）。重複定義已移除，
`test_formal_market_data_repair.py --collect-only` 收集 14 個不同案例。

對六個來源檔執行 scoped mypy 為 **0 issues**；本切片的 Python 檔案 `py_compile` 通過。
`scripts/quant_guard_linter.py` 通過精度與 look-ahead 檢查。資料層新 publisher 未匯入
`app_module`。

QA inventory 將新檔 `tests/test_taiex_market_index_publication.py` 與本輪新增案例所在的既有
`tests/test_formal_market_data_repair.py` 各登錄一次，均分類為 `service-oracle-data-market`。
本輪 fast audit 的前值（僅含新測試 entry）為 filesystem 1,022、registry 913、missing 109；
完成兩個 entry 後為 filesystem 1,022、registry 914、missing 108、stale 0、collection errors 0、
`service-oracle-data-market` 130。兩個路徑都不在 missing 清單。既有
`test_full_app_healthcheck_test_inventory.py` 仍因全庫 108 個其他未登錄測試檔而失敗，另有 6 個
文件分類計數 drift；此處只登錄本切片所觸及的兩個測試檔，不宣稱全庫 inventory audit 通過。

## SHA-256

- publisher：`data_module/taiex_market_index_publication.py` —
  `ABDF171C6C82984F474922688BCBAC08D1455C1C1B3782D3C975EA379CB9465B`
- synthetic contract tests：`tests/test_taiex_market_index_publication.py` —
  `B67B34266EF63119EB89E2290A69202F37C112110E71E8D5B6BA82DD1D96BD1B`
- formal guard tests：`tests/test_formal_market_data_repair.py` —
  `FF7C0CAAA29D7FDDEC6328B94D119564953FEB42D819B78100941A031F917D3B`
- scheduled runner test：`tests/test_scheduled_data_update_runner.py` —
  `BF03CB81BBD1F69CC2930BB2FF4A2DE3D0C41C7C5B0C8221CB1CEC710069981C`
- inventory：`qa/full_app_healthcheck/test_inventory.py` —
  `B33456CC7F7551DA2179086E9B2A4DA3E694C6A197CD70288C5E18CAB82BEA5F`

本文件只記錄 bounded 合成測試與本機靜態檢查；等待獨立 review，不能作為完整 R026、R028 或
歷史 PIT 接受證據。

## P2 修復收據（2026-09-25）

依獨立覆核提出的兩項 P2 重現完成最小修復：

- `_sqlite_typed_row()` 在同一明確 read transaction、同一個 `SELECT value, typeof(value)` 中
  使用 `fetchmany(2)`，只有恰好一列才建立證據。合成測試以無 UNIQUE 約束的 SQLite schema
  分別插入相同值與不同值的同鍵重複列，兩者都回 `unknown`。
- evidence reader 以 SQLite read-only URI `mode=ro` 開啟資料庫。成功發布後將 TEMP DB 移至旁邊，
  以原 descriptor／database path identity 讀取仍回 `unknown`，且原路徑保持不存在；測試 finally
  只恢復該合成 TEMP DB。

修復前先執行新增的三個 P2 案例，結果為 **3 failed**，確認兩種重複列都曾錯誤 attested，且
缺失資料庫路徑曾被 reader 建立。修復後新增案例為 **3 passed**；指定四檔路由使用獨立 TEMP、
`PROFILE=test`、`DATA_ROOT=C:\Users\archi\AppData\Local\Temp\txd6a139\d`、
`OUTPUT_ROOT=C:\Users\archi\AppData\Local\Temp\txd6a139\o`：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_taiex_market_index_publication.py tests\test_formal_market_data_repair.py tests\test_official_market_daily.py tests\test_scheduled_data_update_runner.py -q -o addopts= -p no:cacheprovider --basetemp=C:\Users\archi\AppData\Local\Temp\txd6a139\p
```

結果 **66 passed**。log：`C:\Users\archi\AppData\Local\Temp\txd6a139\pytest.log`；SHA-256：
`BB2328A51215FEEE36C98CB1224B41AA69B4FF034B0E329E98EDD883B43F4512`。

靜態檢查：`mypy --explicit-package-bases --follow-imports=silent
data_module\taiex_market_index_publication.py --show-error-codes` 為 **1 source file, no issues**；
兩個修改 Python 檔 `py_compile` 通過。將測試檔一併交給 mypy 的探索性命令回報 6 項既有測試
helper typing 診斷（行 105、184、188、291），均在本次新增案例之前；新增案例沒有被指出型別錯誤。
`git diff --no-index --check -- /dev/null <file>` 對兩個原先 untracked 的 Python 檔沒有 whitespace
diagnostics；全檔 trailing-whitespace scan 亦通過。由於三個授權路徑原先皆為 untracked，標準
`git diff --check` 不會包含其內容。`C:\t` 因 sandbox 拒絕建立目錄而未使用；所有測試均在授權
系統 TEMP 執行。未啟動 scheduled main、未讀寫正式資料根目錄。

修改前 frozen hashes 與完成後 hashes：

- publisher：原 `ABDF171C6C82984F474922688BCBAC08D1455C1C1B3782D3C975EA379CB9465B`；完成後
  `80ECF0BBB74FAE3FF277793BF623CFA54AA5D3A8EC4355743F75AD4B12DB8593`
- synthetic contract tests：原 `B67B34266EF63119EB89E2290A69202F37C112110E71E8D5B6BA82DD1D96BD1B`；完成後
  `37E8D42BCBD8C39301C25151A0D2C063B6D4F9138F4547C285B9803EA25C44D2`

此收據只記錄兩項 P2 的合成修補與 scoped 驗證，等待 root review；R026 維持 IN_PROGRESS、R028
維持 BLOCKED，整體來源身分工作仍未完成。

## 註解語言與 test hash 更新（2026-09-25）

只將新增 CTAS 測試中的兩句說明註解改為繁體中文，測試行為未變。前述 66 passed 是註解更新前
執行的結果；本次僅有註解變更，未重跑 66 項路由。

- synthetic contract tests 更新後 SHA-256：`202F54082A5ACAB7B54B8EF8D83BA5549A73FD5B0CE58A9B6AE627235074F2F9`
