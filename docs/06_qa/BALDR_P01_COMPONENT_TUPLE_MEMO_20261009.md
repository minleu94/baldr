# P01 單次頁面路徑祖先 tuple memo 驗證

## 範圍與安全邊界

本切片只重用單次 P01 page operation 內的純詞法路徑運算：將同一個 canonical absolute `Path` 的 root-to-leaf 祖先 tuple 暫存，供 `personal_data_paths._reject_links` 與 snapshot repository 的 `_reject_link_components` 共用。memo key 是 `(type(path), str(path))`，保留 Windows 大小寫 spelling；只接受 exact concrete `Path` type、absolute、語法驗證後字面值不變的路徑，並綁定建立 memo 的 thread。其他路徑、foreign thread、停用或滿額情況都走原 tuple 建構路徑。

祖先 tuple 與既有 OS path render 共用每次 operation 的容量：最多 4,096 個項目、累計最多 1 MiB UTF-16 lexical bytes。祖先項目的預算包含 key 與 tuple 中每個 `Path` 的完整字串。這是詞法字串預算，不是 Python heap 或整個程序的 RAM 上限。

本切片沒有快取 `lstat`、reparse/link 判斷、檔案 bytes、SHA、layout、來源資格或取消狀態。每個 component 仍逐一以原順序呼叫原有 `lstat` 與 link/reparse guard；每次讀檔仍走原 fresh bytes/hash 路徑。既有 page scope 的 `finally` 清空 tuple 與 render entries 並恢復 ContextVar；strict callback、巢狀 scope 與外部 thread 不借用外層 memo。

## 變更來源

修改的正式來源：

- `app_module/personal_data_paths.py`，前像 SHA-256 `d90a46bcd9a83bd905262765dbf2718bf29f0e324bda6bf6573b2a7b887cf1ed`，目前 SHA-256 `1f08d1b4f92a1a002192b09a7d92cc37a58fdba2c5f2d668158cd357f5bc2912`。
- `app_module/daily_market_technical_snapshot_v4_repository.py`，前像 SHA-256 `1bbfb41a41283fcfefea861248ccf9158e9f1484bf691b9a77d1cb4552b41ec7`，目前 SHA-256 `1e494ac97ee72ad05b9cb609b62bc9f39bfb0c2b3341634724189d2db1168f59`。

測試變更：

- 新增 `tests/test_p01_page_path_component_memo.py`，最終 SHA-256 `51bc5c29920e588bb4096e232974f9b08b3d36fea5fef159e22f07ea63f1d7c9`。
- 在 `tests/test_daily_market_technical_universe_v4_query.py` 的 P01 callback/cancel case 加入 memo component tuple 清理斷言；完整檔案 SHA-256 `4fe18f3b2113ef121979e46be6f0ead6ee34fdcca287e19327367cc4be9f9c38`。修改前檔案 SHA-256 `10f002b52b00b10ceb114a592468b348227a882f6e3e146abbf9d209e7a3eb85`。

逐檔前像位於 `output/qa/p01_component_tuple_memo_20261009_a/preimage/`；整體 patch 位於 `output/qa/p01_component_tuple_memo_20261009_a/component_tuple_memo.diff`，SHA-256 `2a89a49f0c9170fe9f89d22d48452fbc4ef61b41dd9baf500aed509fe543779e`。所有前像 SHA 均與變更前核對值一致。機械 pin 清單見同目錄 `frozen_pins.json`。

## 驗證結果

新增測試在隔離 Windows TEMP 下執行：

```powershell
$env:TEMP = 'C:\t\p01_component_tuple_memo_20261009_b'
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -B -m pytest tests/test_p01_page_path_component_memo.py -q -o addopts= -p no:cacheprovider -rs
```

在加入 junction 範圍斷言前，完整新增測試檔為 **10 passed、0 skipped，0.37 秒**；當時測試 SHA-256 為 `d7f4bd085c93e60b18554e20a9bf8847309e7c67ccbf97b3af4d572acffd9fa1`，輸出為 `output/qa/p01_component_tuple_memo_20261009_a/owned_tests_native_attempt02.log`，SHA-256 `ce1c338e40b70f2a8712be75aa47e3aa52e43eebaa95b18fbcbb3dd074345c5`。其後只在 junction case 加上 canonical `tmp_path` containment、reparse bit 與 cleanup 範圍斷言；以最終測試檔 SHA `51bc5c29920e588bb4096e232974f9b08b3d36fea5fef159e22f07ea63f1d7c9` 定向重跑該 node，結果 **1 passed，0.37 秒**，輸出 `output/qa/p01_component_tuple_memo_20261009_a/junction_containment_attempt01.log`，SHA-256 `4b901e9fb121489422c56c94f4112a34c14f497e2e01c9caa23941fe690489cf`。因此最終版本的全部 10 個 test functions 均有通過證據；前 9 個在完整檔測試中通過，最後 junction function 在範圍斷言版本重新通過。

對現有 P01 page path regression 執行七個指定 case：render key/foreign-thread、容量與巢狀 scope、fast page 對 strict clone 的完整 DTO 與 fresh I/O event 相等、re-entrant callback 中 strict repository read、取消後清理、selected 與 unselected sibling 的 mtime-restored tamper 拒絕，以及 page reparse fixture。結果為 **7 passed，33.33 秒**，完整輸出在 `output/qa/p01_component_tuple_memo_20261009_a/query_regression_attempt04.log`，SHA-256 `98557ad71ee5fc96461eb6fb091ef66380920d9ab13967e9cf1793d5e5bfe324`。

型態檢查：

```powershell
.\.venv\Scripts\python.exe -B -m mypy app_module/personal_data_paths.py app_module/daily_market_technical_snapshot_v4_repository.py --follow-imports=silent
```

結果：兩個來源檔 `Success: no issues found`，原始輸出 `output/qa/p01_component_tuple_memo_20261009_a/mypy_final.log`，SHA-256 `0c37c4158c91ef55c724ba017bf6465f26018199badb08e3ff13f98acdf056c2`。`py_compile` 對兩個來源與兩個測試檔均 exit 0，原始輸出 `output/qa/p01_component_tuple_memo_20261009_a/compile_final.log`，SHA-256 `44f2fa680bce35ef027b6ca1bd14316492ab53539439f911e797f17397d46f6c`；`git diff --check` 無 whitespace error。此次 sandbox query setup 嘗試因受限 TEMP 回 `WinError 5`，另有一次錯誤 pytest node selector（未收集測試）；兩者原始 log 均保留，最後有效回歸使用新的隔離 `C:\t` TEMP 完成。

## 效能與未完成驗收

此切片只證明輸出及 fresh I/O/reparse 行為與 strict 路徑相同，沒有執行或宣稱新的 1,000 檔 benchmark。最近一次六角色 1,000 檔矩陣仍維持原結果：page flip 與 global sort p95 通過 300 ms；filter p95 為 525.9606 ms，未通過。此變更仍需 Root 審查後，才可建立新的固定 overlay 並按原 5 cold + 1 warm / 90 samples / 300 ms 條件驗證；不得以本次單元測試替代效能 gate。
