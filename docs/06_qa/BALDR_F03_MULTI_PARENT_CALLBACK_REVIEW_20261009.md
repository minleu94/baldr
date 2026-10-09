# F03 三路投影雙 parent callback QA 摘要

## 範圍

本次只新增 `tests/test_daily_market_technical_universe_projection_group_v2_multiparent.py`，以既有 `synthetic_full_store` 真合成 producer fixture 驗證 StoreReader 對兩個 parent 的 callback 與三路暫存投影。沒有修改 F17、P01、MA、KDJ、波動度或 group runtime，也沒有讀取正式市場資料。

Fixture 由 `tests/test_daily_market_technical_universe_v4_query.py` 的 `synthetic_full_store` 建立：258 檔 declared、257 檔 included、1 檔 excluded；兩段 parent 分別含 256 與 1 檔 included 股票。Producer 只寫入該 fixture 的隔離合成根；fixture teardown 會清理由它建立的合成目錄。此測試不代表 1,000 檔效能、正式交易日曆資格、qualified group publication 或 UI／收藏接線完成。

## 測試內容

- 由真 `DailyMarketTechnicalUniverseV4StoreReader.read_exact_with_verified_parent_callback` 取得兩個 typed parent，核對 `(0, 1)` 順序、`(256, 1)` 分段、258/257/1 分母及 processed code 順序。
- 觀察 P01 每股只建立一次 parent row，並確認 MA、KDJ、volatility 收到相同 snapshot 與 row 物件；第一段完成後 group 為 `between_parents`，不發行 qualified session。
- 使用真 reader callback 測錯序與重播 parent，確認 group poison、部分 entries 清空且 Builder 沒有發行 session。
- 在第二 parent 的 volatility callback 注入明確 `RuntimeError`。此時 MA/KDJ 已收到第二段股票，volatility 尚未收到，故預期暫存數為 `(257, 257, 256)`；StoreReader 包裝錯誤的 `__cause__` 必須保留注入的例外型別與訊息，失敗後三路暫存均清空。

## 實際結果與失敗保留

| Attempt | 結果 | 說明 |
|---|---|---|
| a | 3 個 fixture setup errors，未進 producer | Sandbox 對 workspace 下的臨時根 `Path.resolve(strict=True)` 回 `WinError 5`。原始輸出 `output/qa/f03_group_multiparent_20261009_a/pytest.log`，SHA-256 `2F08463FF9B4921291D05567DB0C86D9DE5F1FF42DD89A385A7ABEFDEC973590`。 |
| b | 2 passed、1 failed，176.36 秒 | 測試前版在第二段 callback 錯誤要求三個 member 都仍為 256，導致斷言先於預期注入失敗。這是測試 oracle 錯誤，並未證明 intended volatility failure path。原始失敗 `output/qa/f03_group_multiparent_20261009_b/pytest.log`，SHA-256 `FC568591F9BFAA6B1DEDC7211913DBF43E4995FFD33A188E2A301E4D9738804E`。 |
| c | 1 passed、2 deselected，132.12 秒 | 修正 partial count 為 `(257, 257, 256)` 後，第二 parent 注入案例通過。該次實際受測檔 SHA 為 `53E3AEA041AE4880AE82343BBFE12525E013F4D06D587B1BF0E4CC3AB5B34630`；此版尚未加入下方的直接 `__cause__` 斷言。原始輸出 `output/qa/f03_group_multiparent_20261009_c/pytest.log`，SHA-256 `FD010F6E903BD0C1A164E4313B6BD73E5B34D15A543F5A653D0596C76566BD5E`；其受測檔快照保留於同目錄 `test_source_tested_c.py`。 |

Attempt c 之後，固定版測試再加入 `RuntimeError` cause 型別與訊息斷言。最新測試 SHA 為 `BDB0453BF24199A4685A41A6B3CB5434006B4928F0A3F3E27D82A9834796CF74`；對此版已通過 `py_compile` 與單檔 mypy。**最新固定版三項全套尚待獨立重跑；Attempt c 的單項通過不折抵這項驗收。**

## 重現路徑與隔離

重型 fixture 使用新的短 OS 暫存根 `C:\t\f03_multiparent_20261009_c_temp` 與 pytest basetemp `C:\t\f03_multiparent_20261009_c_pytest`；pytest fixture 本身仍依賴 `tempfile.gettempdir()`，不是由 `tmp_path` 建立。每次重跑須另選未存在的短暫存目錄，避免覆寫既有 attempt。命令路由為：

```powershell
$env:TEMP = 'C:\t\<new-unique-temp>'
$env:TMP = 'C:\t\<new-unique-temp>'
\.venv\Scripts\python.exe -X utf8 -m pytest `
  tests/test_daily_market_technical_universe_projection_group_v2_multiparent.py `
  -q -o addopts= --basetemp C:\t\<new-unique-pytest-temp>
```

此命令預設會執行三項新測試。使用的 bundle/store 都由合成 fixture 在新暫存根產生；沒有使用原市場資料、外部網路或 1,000 檔 benchmark。

## 凍結版本

- 新測試：`tests/test_daily_market_technical_universe_projection_group_v2_multiparent.py`，SHA-256 `BDB0453BF24199A4685A41A6B3CB5434006B4928F0A3F3E27D82A9834796CF74`。
- 被測 group runtime（本任務未修改）：`app_module/daily_market_technical_universe_projection_group_v2.py`，SHA-256 `0B0864D9017FAC0EFBC2E26F450EFA2C7A82C17D53AC1674B8B881D240B11AA2`。
- 原 group test（本任務未修改）：`tests/test_daily_market_technical_universe_projection_group_v2.py`，SHA-256 `CEA9DE7218D61EF113E1C6F18A54ECC5B6E1948DFEF784036799AB0C7943EB5E`。
- 多 parent publication 設計：`docs/06_qa/BALDR_F03_MULTI_PARENT_GROUP_PUBLICATION_PLAN_20261009.md`，SHA-256 `3D3BCAE5D0DDDCB47EFF6B3FDF72890A1ABC464F2E7654179E59614A41FFBD1D`。

## 中央固定版完整驗收

Root於全新TEMP/TMP `C:/t/f03-multiparent-root-20261009-a-temp`及basetemp `C:/t/f03-multiparent-root-20261009-a-pytest`，對固定SHA `BDB0453BF24199A4685A41A6B3CB5434006B4928F0A3F3E27D82A9834796CF74`執行完整三項。唯一handle34772 terminal exit0，3passed／497.32秒；JUnit `output/qa/f03_multiparent_root_20261009_a.xml`實讀tests3、errors0、failures0、skipped0。受測檔前後SHA吻合；正常單檔mypy clean、py_compile exit0。

此結果取代上文最新固定版待重跑狀態，涵蓋cause型別與精確訊息斷言、跨兩parent資料一致性及首段暫存清空。497.32秒包含fixture產製與全部案例，不是1000檔query效能結果；不授共同publication／F17資格／UI／收藏／EXE完成。
