# Baldr 補完首波工程驗收（2026-10-06）

本收據記錄首波 M1 與 P01 底層葉片，不宣稱整份產品補完或完整選股器完成。範圍以[單一接續計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md)為準。

## 版本與保護

| 項目 | 已核實內容 |
|---|---|
| 開工 checkpoint | `bf9207fb72cd3acebac17f4b7816994efa601226`；原九檔先提交再分派 |
| 共用設定／版本 | `92ed944e`；43 個定向案例 |
| H20 純投影 | `cefef608`；12 個定向案例 |
| 中央入口／UI／建置 | `a35df3a734e367398bd3b5eda6f58773d0f65d05`；34 個定向整合案例 |
| 依賴鎖修正 | `96ecf00121d87c1820d3b98c6a10543581809e8a`；195 個 distribution 版本不變，校正四個 canonical names；初次 candidate 同版比較失敗 |
| P01 底層葉片 | `9330f7fb`；6 個案例、mypy 兩檔 0 error。初次 96ec candidate 不含此葉片，後續固定來源含其已測底層；全母體 UI 尚未接線 |
| Matplotlib 修正／重建固定來源 | `4b40788bea9e74b5d5207d3d81b1e1c80394b7d6`；共同 launcher 保留 MPLCONFIGDIR，移除 onedir 不需要的 onefile 暫存 hook，其餘 hooks 保留 |
| main／worktree | main 保持 `305635642ecdf5f1331a24a0c81566d07f36cb0d`；只有 dev/main、一 worktree，沒有 push／merge |
| 原計畫 | SHA256 `4f90d28051e91a2754466fd0ac4677eeb49a7c28e1de3cc419f78965716b9a55`，保留原 bytes |
| 原交付 exe | `dist/baldr/baldr.exe`，52,301,884 bytes；SHA256 `ab0c72ef1c98f906e3d7ef14d440490ea4bf238aa53f959597636ddc2b1b263e`；原包與 active_delivery 保留 |

M1 candidate 已建置並通過同版隔離 fixture 比較。發布建置身分為 `2026.10.06+4b40788bea9e`；這是固定來源候選，沒有替換 active_delivery，也沒有取得 Native 真人接受。

## 中央驗證

| 驗證 | 結果／邊界 |
|---|---|
| launcher、三個 Python 入口、新程序設定與身分 | 與 provenance、H20 畫面／可讀性合跑 34 passed；無效 JSON 在初始化前拒絕 |
| Workbench 必跑 | 85 passed；一則既有 pytest cache 權限 warning |
| update-tab 必跑 | 25 passed／0 failed／4 skipped；skip 不當作 pass |
| 指定 mypy | 857 檔 0 error；兩則既有 untyped-body notes 保留，不宣稱檢查所有未型別化函式內文 |
| 本輪 Python 檔案 | py_compile 通過 |
| 量化防禦 | 精度與 look-ahead guard 通過；沒有新增金融計算、推論或 fit |
| 既有 parent regression | 21 passed；TEMP 與 basetemp 對齊的短隔離根，原 guard 保留 |

原始 log 位於 [Workbench](../../output/qa/baldr_completion_first_wave_20261006/workbench.log)、[update-tab](../../output/qa/baldr_completion_first_wave_20261006/update_tab.log)、[mypy](../../output/qa/baldr_completion_first_wave_20261006/mypy.log)、[P01](../../output/qa/baldr_completion_first_wave_20261006/universe_run_final.log)。其餘早期工具結果與 agent 交接保留，不以重跑刪除失敗。

## 同版 candidate 驗收

初次固定來源 96ec candidate 四用途、模型、收藏、H20、取消結果一致，但 Python／exe 的 `MPLCONFIGDIR` 分別是共同外部狀態根與 PyInstaller 隨機暫存根；逐值比較因此拒絕。原[失敗收據](../../output/qa/baldr_same_version_96ecf00121d8_fc0fa2cf/same_version_receipt.json)和候選包保留。

修正後從 4b40788b 重建，候選目錄 `dist/candidate_4b40788bea9e_dd7335f7/baldr`、來源快照 `output/packaging/build_4b40788bea9e_dd7335f7/source`。exe 大小 **52,413,416 bytes**、SHA256 **`6015311ff93286fa045ff04ed2a82284f812ed009cd48db79db435a2ef344410`**；archive SHA `bd82b80c53060eafee495985372cc49899c44e2dd970a173cc11ed58a61c7432`；依賴鎖原 bytes SHA `b1a3bb4bd03246c025f09bca3658104aff6c676983c878f46d118cec992df743`。

[正式同版收據](../../output/qa/baldr_same_version_4b40788bea9e_523b910c/same_version_receipt.json)狀態為 **`passed_isolated_fixture`**；兩組完整 raw log 同目錄。`BUILD_INFO.json` 保留建置時 `built_not_validated` 原記錄，驗證資格由本收據與獨立 `VALIDATION_INFO.json` 承接。固定 archive 每個檔案、exe／依賴／資源 SHA 已核對，兩種形態從該 archive 的同一 probe 執行。

| 同版比較 | 真正測到的行為 |
|---|---|
| 設定／版本 | 固定來源 Python 與 exe 的完整 commit、版本、release／clean、依賴 SHA 相同；同一 JSON 的 DATA／OUTPUT／research／runtime／MPL roots 逐值相同；另核直接 Qt script 與 `-m` 的 launch-info |
| 四用途 | 首頁四用途 callback，synthetic 市場／個股 worker／推薦 execution／持倉畫面相同；缺日期及技術條件 unknown，缺當前報價不以成本補市值 |
| 模型讀回 | 同一未訓練 shadow artifact bytes SHA `0ebf71b3e9ba8d44032ade8531ba20987b0fdb8b9527153bc61292d2161c857b`；原 loader 讀回、fresh PID 重開及錯 family fallback 相同；TA-Lib／scipy 可用 |
| 保存／新程序 | 真 WatchlistRepository 保存→讀回→fresh PID 的 revision／股票相同，probe JSON 保存再讀回；不冒稱 canonical 保存推薦已解阻 |
| H20／異常 | 固定過去日期的2382 +6.84% 呈現、六分域狀態與用途禁語可見；wrong cohort 拒絕、unavailable 清舊值、切股晚到拒絕；不 monkeypatch cutoff 或時鐘 |
| 取消／子程序 | TaskWorker 合作取消、replacement worker 完成、multiprocessing spawn0、模型 child與收藏 child均正常；九工作區導覽與安全關閉，無降級 placeholder |
| 資源／畫面 | icon／loading 圖 SHA 核對，主視窗 title／底部版本可見；[Python H20 截圖](../../output/qa/baldr_same_version_4b40788bea9e_523b910c/中文%20空白%20fixture/h20-python.png)與[exe 截圖](../../output/qa/baldr_same_version_4b40788bea9e_523b910c/中文%20空白%20fixture/h20-exe.png)已視覺檢查，1400×800 offscreen，不代表其他縮放／Native |

僅排除必要的資源實體位置、frozen 旗標與證據截圖檔名；其餘輸出逐值比對。Python 用固定 archive、exe 用 `_internal`，兩者在版本提示與 launch-info 明示。provider 網路禁止、未用正式市場 DB；Native 真人、正式 Task、真私人模型與自然結果仍未驗收。

## P01 底層驗收

實際保存 257 個納入、300 個排除、2 個重複代碼的母體清冊：第一個 included parent 含 256 檔／16 個 child batches，第二個含 1 檔。完整宣告 557 個 unique，含排除區跨三段查詢；原 child16／parent256 資源上限不改。

實際測試保存、錯日期／population 版本／source clock／segment membership 拒絕、來源 DB bytes 與 mtime 不變、缺證據計數、Decimal 全域升降序、NULL 尾端與代碼 tie-break。投影後取消與 receipt/index/manifest 暫存後取消都不發布，重新 writer 可續跑；thread/event 固定住 publication 前的取消順序，不靠 sleep 撞 race；發布後取消明示 already_published。fresh PID 唯讀查詢與損壞 projection 拒讀通過。

Windows drive-relative／absolute／UNC／backslash／`..` 的 manifest 路徑拒絕，reader 與 resume 解析後檢查 generation containment／symlink。此模組目前合併 run、catalog 與 index，約 2,200 行；後續 UI 接線前需再評估拆分責任及有界資源，不能只由這個 fixture 推導全市場性能。

## 保留的失敗與修正

- 第一輪中央 regression 的 4 個失敗揭露：非 H20 同日 MA 摘要被覆蓋，以及讀取錯誤被一般限制搶先顯示。已保留原 MA 結論，將具體 errors 提到限制首位；15 個受影響案例及後續 34 個整合案例通過。
- Python／exe 技術分析日誌原本不同根；現在兩種都用外部 `OUTPUT_ROOT/application_state/logs`。首輪模型 probe 的 Windows spawn 重進則改成受 main guard 保護的腳本。舊失敗 log 在 `.tmp/sameversion_preflight`，重驗另用新 fixture 根。
- 第一次固定來源建置被精確依賴 preflight 正確拒絕：四個套件名稱含點，與 canonical name 不符。鎖檔名稱校正後才建立新固定來源；沒有安裝或更新依賴，第一次 archive 保留。
- P01 第一輪 parent 合跑 34 pass／1 fail；中央用未對齊的 basetemp 重跑又觸發 20 個 isolated-output guard 拒絕。改用 TEMP 與 basetemp 對齊的短隔離根，既有 parent21 全通過；沒有刪／放寬 guard 或改既有 parent 測試。
- 只讀覆核找出 Windows 相對路徑與最後取消 check／rename 競態，修正後 6 項測試通過。既有 `layout_helpers.py` signal disconnect warning 保留，本輪沒有擴大成 layout 重構。

## 仍未驗收與下一個交付點

M1 只交共用入口／可核實版本／H20 首屏與固定來源候選。H20 呈現 fixture 不代替原 capture／activation；四用途 synthetic execution 不代替完整 canonical 保存推薦讀回，既有 Windows nofollow blocker 保留。正式 Task 下一自然 run、真私人模型、自然成熟樣本與交易資格均沒有本輪變更或新接受收據。

先用 M1 進行小規模 Native 真人試用，檢查 2382 五問摘要、來源／日期理解與返回；仍未實測。M2 才接 P01 完整母體 UI、原 query／比較／收藏／返回，並做 P02/P04 首批 MA5/20、KD、MACD、量能。M3 策略帳本先保留原 500000／8 檔政策；P02–P13 未完成項維持 open。
