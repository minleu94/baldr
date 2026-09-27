# BALDR 產品可用性與 BUI-001 修復收據（2026-09-25）

## 範圍與證據界線

本清冊記錄主程式 `ui_qt/main.py` 的隔離啟動檢查、BUI-001 最小修復及合成資料驗證。程式修改只在 `decision_module/industry_mapper.py`；測試修改只在 `tests/test_industry_mapper_provider.py` 與 `tests/test_ui_qt_partial_data_startup.py`。未修改正式資料、使用者資料、Manual、主程式、排程或交易路徑。開啟 UI 本身會建立暫存 DB、輸出目錄、lock 檔與日誌，因此所有啟動都必須使用新的 TEMP 根目錄。

Native UI 由 root 獨佔操作。下表將 root 實際操作的 native 證據、offscreen workspace 回歸測試、直接呼叫真 service 的合成驗證分開列出；其中一種證據不代替另一種。所有 native 寫入都在 `PROFILE=test` 的 TEMP 資料／輸出根，只使用明示合成內容，未碰正式 DATA_ROOT、下單、排程、資料更新或正式 Evidence。

## 隔離啟動方式與副作用

```powershell
$qa = Join-Path $env:TEMP ('baldr_usability_' + [guid]::NewGuid().ToString('N').Substring(0,8))
New-Item -ItemType Directory -Path $qa | Out-Null
$env:PROFILE = 'test'
$env:DATA_ROOT = Join-Path $qa 'data'
$env:OUTPUT_ROOT = Join-Path $qa 'output'
$env:PYTHONIOENCODING = 'utf-8'
& .\.venv\Scripts\python.exe ui_qt\main.py
```

`PROFILE=test` 會在兩個根目錄下再加 `_test`。若只設 profile 而未覆寫 `DATA_ROOT` 與 `OUTPUT_ROOT`，設定仍會指向預設正式資料根目錄下的 `_test` 子目錄，因此不足以隔離。正式入口的 crash log 位於原始 `DATA_ROOT` 環境變數路徑的 `logs\ui_qt_crash.log`，不會加 `_test`；也必須確認它落在 TEMP 根目錄。

即使空資料啟動，MainWindow 初始化會建立 SQLite DB、回測 DB、預設觀察清單、Regime history lock、Portfolio JSONL lock、推薦回放輸出目錄及研究／設定日誌。這些檔案只出現在指定 TEMP 根目錄；請勿用正式路徑做可用性測試。

## 已取得的證據

| 路徑 | 結果 | 證據與限制 |
|---|---|---|
| MainWindow offscreen 啟動與九 workspace | 通過隔離 smoke 與 partial-data 回歸 | TEMP `baldr_ui_smoke_2c882181` 約 8.3 秒建立九個 workspace。BUI-001 專用測試再以 `companies.csv` 存在、`industry_index.csv` 缺失的完整 `MainWindow` 操作九個 navigation signals，九頁均可切換。offscreen 證據不代替 native 畫面檢查。|
| BUI-001 部分 metadata 啟動 | **已修復；focused tests 通過** | 原始重現 TEMP `baldr_partial_data_ae0180b3` 在缺少 `industry_index.csv` 時曾因 `KeyError: '指數名稱'` 終止。現在 mapper 先保留 companies 對股票產業的映射，僅在 index frame 缺失、空白或欠 `指數名稱` 欄位時略過 index normalization；不造 index 名稱。測試覆蓋缺檔、空 CSV、空 provider frame、缺欄 provider frame，以及完整 index provider 的 normalization parity。|
| 推薦進階預設與合成長歷史 | 真實 UI config + 真 service，合成驗證 10 候選 | TEMP `baldr_adv_ui_23ca40b3`；12 檔 synthetic symbols × 300 business days，OHLCV 指標使用既有 `calculate_causal_indicators` 全歷史前綴計算並存到隔離 SQLite。實際建立 MainWindow、點擊進階模式切換、讀取 `_collect_config()` 原預設，再以 `RecommendationExecutionRequest` 和 `window.recommendation_service` 執行，未 mock scorer／pattern／filter，完成 10 個候選、12 個 assessments。log：`%TEMP%\baldr_adv_ui_23ca40b3\fixture.log`，SHA-256 `8A8F38C4D4E27C4225618DC35F572808B5EDB3F4C28D6F43722F7424FB703A39`。這是合成資料 service 路由，不是 native 按鈕、自然行情或 ML 可用性證明；保留 `calibration_feature_source_unavailable:ValueError` 與 `legacy_source_identity_unbound` 警告。|
| 原生推薦空結果與可恢復性 | 通過 native 空結果呈現；非候選保存驗收 | root 在 TEMP `9be06d28` 使用 50 日合成資料實際執行穩健策略及進階固定門檻，兩次均回傳 0 候選；畫面顯示空結果 modal 且可恢復。診斷含總分 NaN、RSI 條件等。這與上列足量 300 日長歷史合成 fixture 的非空 service 結果分開記錄，未將短歷史空結果歸因為 scorer defect。推薦候選保存及其 canonical readback 仍未驗證。|
| Native 觀察清單與研究跨頁 | 合成操作與重開讀回成功，identity 仍未知 | root 在 TEMP `9be06d28` 手動將合成代碼 2330 加入觀察清單，保存後 `output\_test\watchlist\default.json` 讀回代碼與合成註記；`source_id=''`、decision identity unknown。選取 2330 後可開啟 Stock Research，顯示 9/24 價格及技術／基本面缺件。因沒有 exact `result_id`，研究結果頁相關操作停用並說明原因。重啟後觀察清單讀回也成功。它是手動 watchlist，不是推薦結果或 natural evidence。|
| Native Portfolio 手動紀錄與讀回 | 隔離 JSONL 保存及重開讀回成功 | root 在相同 TEMP 手動輸入合成 2330、buy 1,000 股、價格 100、fee 143、日期 9/25，note 明示 synthetic／非真實成交。保存 modal 成功；`trades.jsonl` 產生 `trade_20260925_225810_119241ef`。關閉再啟動後，Portfolio 頁讀回 1 檔、1,000 股、價格 934.30、市值 934,300。摘要的 last-refreshed 時間易與行情資料日混淆，原行情日 9/24 尚未在該摘要中確認。介面顯示 gross 投入 100,000，fee 是否需另列應按既有欄位契約判讀，本輪不定性為計算錯誤。只寫入隔離的手動研究帳本，沒有下單或正式資料。|
| Workbench 持倉摘要來源 | 已辨明為不同 read model，語意待產品確認 | root 觀察到手動 Portfolio 有一筆紀錄，而 Workbench 顯示沒有可呈現持倉列。原始碼顯示 Workbench 引導摘要使用 `dashboard.position_health`；`WorkbenchSourceService` 讀取 `PositionHealthTransitionReadService` 與唯讀決策快照，沒有直接把 Portfolio 手動 ledger 當成該健康報告。兩個讀模型不同，尚不足以判定資料丟失；需明示健康報告來源／日期，或由 application read boundary 提供 manual holdings count。此項不在 BUI-001 修復範圍。|
| Native viewport 與 Runtime/Evidence | 部分可用，仍有明確限制 | 1400×800 初始窗口中推薦候選頁底部研究／保存按鈕落在可視區外且頁面無捲動；最大化後可觸及。Runtime 可開啟，隔離環境顯示 receipts 0/6，未把治理歷史誤認成當前 artifact。Backtest／Review 的完整 end-to-end 流程及推薦候選 save/readback 仍未驗收。|

第一個合成 SQLite DB SHA-256：`0658792E28681D925F7788385DCE79D6B9D5AFBD2CDC1DA47E429BB301D29C11`；原始合成 `companies.csv` SHA-256：`9969F0C7F1A88BDEF99096DA980AF18660C741BC1C246EFC950AB69575B9A062`。長歷史進階 fixture 的全部 DB／輸出位於獨立 TEMP `baldr_adv_ui_23ca40b3`；該 fixture 未由 native app 開啟。root 的 `9be06d28` native DB 與以上 offscreen fixture 分開。

## 阻斷項與驗收條件

**BUI-001：已修復並通過 scoped 驗收。** `IndustryMapper` 在 companies map 建立後再檢查 industry index；missing／empty／missing-column 時維持股票產業分類，index normalization 和 performance cache 保持空，不推造資料。正常 injected index 測試仍驗證 `半導體業` → `半導體類指數` parity。完整 MainWindow 測試在隔離根建立 partial metadata 後實際點擊九個 workspace navigation buttons。

focused 命令：`\.\.venv\Scripts\python.exe -m pytest tests/test_industry_mapper_provider.py tests/test_ui_qt_partial_data_startup.py -q -o addopts= -p no:cacheprovider --basetemp %TEMP%\bui1_final_194093ee\p`，7 passed in 3.05s；console log `%TEMP%\bui1_final_194093ee\pytest.log` SHA-256 `65265F01554FB7B76AD17AE23B03ACC1640D80A9F76C1A9D7423E0654C9C363A`。三檔 scoped `py_compile` 通過；同三檔 scoped mypy 回報 `Success: no issues found in 3 source files`。原生重啟、空結果及跨頁的限制另見上表，不能由 offscreen test 替代。

## 本輪來源保護指紋

以下列出第一輪來源基線及 BUI-001 最終驗證指紋。除 `industry_mapper.py` 與本次新增／更新的 scoped tests 外，其他列出的產品檔本輪未修改：

| 檔案 | SHA-256 |
|---|---|
| `ui_qt/main.py` | `93B7062B3A2998D135198261C57138344D9C190D73F687E49EEBAA9BD05E206E` |
| `data_module/config.py` | `D457A892248D87252A5D426C686E87CF8D460B0D4D74B0549DCE31B89170538B` |
| `decision_module/industry_mapper.py` baseline → final | `B1DA3703F8536540005469528E2D3CCF3D7236E623B5902545AFC6C7751C0CD8` → `3435EFD68EC2D34E14A9A69E0EC6972079DB0B7774B16E17DC7FEB4C79416AFD` |
| `ui_qt/views/recommendation_view.py` | `16BB7DDFBAED4B66BF4F76C0AFDBD0EB977F335FDC19A6424E2D652A81F8EFC1` |
| `ui_qt/views/watchlist_view.py` | `6B200D88DB5FEA011BF67895E6A290F9510BA20E5B97905002AA2FF25440DE75` |
| `ui_qt/views/backtest_view.py` | `71D3C400A42049F93CD56AC0274B05016B2AFF103D44992536981A496122AEEC` |
| `ui_qt/views/portfolio_view.py` | `0FFD4E1EA8C241D5A552AFE6612FAE9C84D68E369C26A68B05B7584817D2EB2A` |

| scoped 測試／清冊 | final SHA-256 |
|---|---|
| `tests/test_industry_mapper_provider.py` | `F2A6F99331E12694F6B41E740397802215B32C6EE8E5BDEAF4584E0CBE8B60C0` |
| `tests/test_ui_qt_partial_data_startup.py` | `6605A915175334BA1FED073D27400ABB863BC4D28156E2F14A66CC3897775F9C` |
| `docs/06_qa/BALDR_PRODUCT_USABILITY_20260925.md` | 更新後另行計算 |

## 文件狀態差異

目前來源與操作手冊的 workspace 數量有差異：`ui_qt/main.py` 初始化 9 個 workspace（含 `stock_research`），而 Manual 2.6 仍列 8 個。本輪依授權不修改 Manual；此差異須納入後續文件同步工作，不作為功能已驗收的證據。最終 native 重開驗收尚未完成；推薦候選保存 canonical readback、backtest／review 跨頁 end-to-end 仍待後續切片。
