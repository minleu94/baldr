# P01 單頁路徑渲染 memo 驗收紀錄

## 範圍

本切片只在一次 `DailyMarketTechnicalUniverseV4ReadSession.read_selection_page` 期間，重用相同絕對 `Path` 的純 `to_internal_io_path` 渲染結果。memo 使用精確 concrete `Path` 型別與原始 `str(path)` 作鍵，避免 Windows `Path` 大小寫相等語義混淆；只接受絕對路徑及建立 memo 的執行緒。容量上限為 4,096 項及 1 MiB UTF-16 路徑字串；滿額、相對路徑、其他型別或其他執行緒一律退回既有 strict renderer。

每次頁面操作都建立新的 memo，巢狀操作獨立，離開時清空並恢復 ContextVar。取消回呼與 strict clone/read 路徑會暫時停用 memo，避免外部回呼、複製的 context 或一般 strict API 借用 page scope。快取只包含路徑轉成 OS I/O 字串的純計算結果，不快取路徑存在性或檔案狀態。

所有 manifest/reference/artifact 的重新讀取、lstat、reparse 檢查、artifact bytes/SHA-256、layout 驗證、取消檢查及頁面 materialization 都照原路徑執行。測試逐一比對 fast page 與 `dataclasses.replace` strict clone 的完整 inner page payload、query/selection identity，以及 lstat/reparse/read 事件序列。此切片沒有更改市場資料、特徵值、條件、排序、決策時點或 availability，因此不改變 look-ahead/PIT 語義。

## 前像與固定來源

保存的 HEAD 前像位於 `output/qa/p01_page_path_render_20261009_b/preimage/`：

- `app_module/personal_data_paths.py`：SHA-256 `6af4b495f14a9a05dbb301487a345d3bd426999bc5fcdf9f3afd279ef5bcfd35`。
- `app_module/daily_market_technical_universe_v4_query.py`：SHA-256 `341b9d9de98b1fa760023de0021bf547e0181a90e066900add0dffb10d1d7b1b`。
- `tests/test_daily_market_technical_universe_v4_query.py`：SHA-256 `fae3d0e412748f74b1cb437092e047193bd8cda70533b1ed0f3d7d81b5b94dcd`。

本輪最終受測來源及測試 SHA-256：

- `app_module/personal_data_paths.py`：`d90a46bcd9a83bd905262765dbf2718bf29f0e324bda6bf6573b2a7b887cf1ed`。
- `app_module/daily_market_technical_universe_v4_query.py`：`ca4c84ac91d1329f3b05eec576a32bb5d587566ab25ba93cb0e9f4c9c4dea515`。
- `tests/test_daily_market_technical_universe_v4_query.py`：`10f002b52b00b10ceb114a592468b348227a882f6e3e146abbf9d209e7a3eb85`。
- `tests/test_daily_market_technical_universe_v4_session_metadata.py`：`39380514a8d9224d0a46a2af0f490971fb909b1fc1978b0c3b133efe303a1a41`。
- `tests/test_daily_market_technical_universe_v4_read_session.py`：`3833954a778b31f5d7c967f64924d9c8ba8afa30ff68696fdd13403eac8e1b5e`。
- `tests/test_daily_market_technical_snapshot_v4_semantic_rehydration.py`：`30871d1fcd121988e29a6656c81095f78a010ab82e90e55aac4b443ec0286d29`。

## 驗證結果

- 原生隔離 synthetic page subset：`7 passed, 11 deselected in 26.72s`，log `output/qa/p01_page_path_render_20261009_b/attempt03_native_frozen.log`，SHA-256 `f23ce8f2097eb01b9fac7b3701504a4b4718eb635fdf11d1b9d246be414fe040`。涵蓋 memo 大小寫鍵／跨執行緒 fallback、有界及巢狀清理、fast/strict page DTO 與 I/O 序列等價、strict callback 隔離及取消清理、selected/unselected artifact bytes 篡改且還原 mtime 後拒絕，以及真 Windows junction/reparse 拒絕與 fixture 還原。
- Proof/session metadata/read-session 回歸：`37 passed, 5 deselected in 420.34s`，log `output/qa/p01_page_path_render_20261009_b/attempt01_regression37_native.log`，SHA-256 `7b96e9ae9e4094350fd8013d564e3bf348773257a8ad194085432fc73344ba38`。此命令實際包含 query 測試 13 項（11 個既有 query cases 加 2 個無來源 memo contract cases）、session metadata 18 項，以及 `test_daily_market_technical_universe_v4_read_session.py` 的六個明確指定節點；不包含下一項 semantic rehydration suite，故不把此結果稱為 Root 指定的 semantic 13 項覆蓋。
- Semantic rehydration：`13 passed in 19.92s`，log `output/qa/p01_page_path_render_20261009_b/semantic_rehydration13_native.log`，SHA-256 `f9647ff8b8fefe6b3148bd93c34efb89fc07bc5bf27daf8d42ed85f74e375b9d`。
- Mypy：`--follow-imports=silent --no-incremental`，兩個產品來源檔 `Success: no issues found in 2 source files`。
- Compile：兩個來源檔及本輪 query 測試檔通過；pyc 輸出放在本 QA 目錄的 `pyc/`，未寫回 source `__pycache__`。
- `tests/test_personal_data_paths.py` 的獨立原生回歸由 Root 執行：首輪 `113 passed, 1 failed in 35.08s` 的唯一失敗是 rollback fixture 未達宣稱的 260 字元路徑長度；另以較長 fixture 單例 `1 passed`。這是兩次證據，並非一次全套無失敗結果。

## 失敗與修正紀錄

- 首次 sandbox fixture setup 因 `Path(tempfile.gettempdir()).resolve(strict=True)` 遇到 WinError 5，未進入測試；保留該失敗，不作產品結論。
- 第一個 native attempt 為 `5 failed, 13 deselected in 25.67s`。其後分離診斷發現 selection-page wrapper 本身沒有 `to_dict()`；測試改比對 wrapper 的欄位與 inner page `to_dict()`。Cancellation 例實際 `error.code` 已正規化為 `technical_universe_v4_query_cancelled`，失敗只因舊 assertion 比對底層 message；測試改為核對 `.code`，沒有改產品錯誤映射。Tamper測試的直接長路徑 I/O 與 junction relocation 也改經 `to_internal_io_path`。
- 修正後 attempt 曾有 `6 passed, 1 failed`：唯一失敗是測試選錯 configured-root ancestor，沒有執行 junction mutation。再前一個 reparse 單例因測試組出的 `cmd /c` 字串語法而 skip；改用標準 argv 後，真 junction 測試通過。
- 上述失敗 log 均保留：`callback_trace_attempt01.log`、`attempt02_native.log`、`reparse_attempt01_native.log`。成功的 reparse 單例為 `reparse_attempt02_native.log`，SHA-256 `f950e5b6ed57ce24c2a6329d87269128032a5e3320c94bfbe0b4c3644e859e74`。

## 驗收界線

這些是純 memo contract、17 股合成來源頁讀取及既有定向回歸，不是固定 1,000 股 benchmark，也沒有聲稱 300 ms 或 p95 通過。仍需沿固定來源與原始測量矩陣重驗正式 runtime 效能；本文件只記錄不減少 fresh I/O/identity checks 的 operation-local path rendering memo。

## 後續固定效能矩陣

後續固定 d12 archive 加四個受審 overlay 的六角色矩陣已完成，Root 對 warm child 每類 30 筆原始耗時獨立重算 nearest-rank p95：page flip `174.3009 ms`、filter/select/page `525.9606 ms`、global sort/select/page `219.2445 ms`。翻頁與排序通過嚴格 `< 300 ms`，篩選未通過；這是四 overlay 候選的矩陣結果，不代表完整 Main、EXE 或真人驗收。後續加入 component tuple 的不同版本矩陣結果見[Root 路徑字串重用審查](BALDR_P01_PATH_RENDER_DESIGN_ROOT_REVIEW_20261009.md)，不可混用兩組 p95。
