# 模型修復執行紀錄（2026-09-23）

## 目前判定

股票修訂 v2 的兩家族 fit／最新資料推論均完成；其評估另發現大盤來源缺陷。官方來源追加修復已核驗 153 個月、306 份回應，bounded 官方 v3 亦完成 17,285 列 fit、13 檔最新資料的 312 組預測，以及 327,816 筆 base OOF 獨立誤差重算。四期間 pooled MAE 與 downside Brier 均未勝 train-only 基準，不能由執行成功推論品質達標。全市場 H5 官方 v3 尚在建置，因此整體修復未結案；既有舊模型隔離、rule_only 與正式權限保持。詳見[大盤來源核對](MODEL_REPAIR_MARKET_SOURCE_AUDIT_2026_09_23.md)及[bounded 新舊版本評估](BOUNDED_RESTATED_RESEARCH_FIT_QA_2026_09_23.md)。

## 已確認的修復範圍

1. 來源修訂涵蓋 2026-05-20 的 868 檔。1256／1477 是使用者指出的例子，不能據此把其他股票排除。
2. Direct OOC 基線為 3,353,096 rows、62 欄；特徵與四個 horizon 標籤從 run02 修訂快照重算。原 targets 全部現金，新增列 targets 缺失；沒有替模型製造可學習的配置答案。
3. 原 bounded 資料 22,093 rows、11 檔。210 個 H60 outcomes 跨修訂日，210/210 重算有變化；其中 10 檔受到影響。這些列的決策日為 2026-02-11–03-23，H60 結束日為 5/20–6/17；並未一律截到 5/20。四個原 folds 不包含這 210 列。
4. bounded 舊特徵亦需重算：`row:2014-01-03:1101` 只有一日可核驗價格，18/20 technical slots 卻已觀測；2026-03-23 樣本另有八欄與完整前綴重算不符。120 尾窗未重現該晚期樣本差異，不能把它逕自宣稱為已證實根因。重算 20 個技術欄位與五個依賴它們的品質欄，保留原 row IDs、62 欄順序／尺度及 targets/state。
5. 首日前沒有個股來源的列，stock event 及 41 個 stock slots 保留 NULL／missing；不得捏造前一日價格。市場事件另驗，品質／市場欄仍可有觀測。訓練入口需保留該語意及計數。

## 千分位字串修正

唯讀 run02 查到合法的逗號價格：2330 的 2024-07-04 開／高／低／收為 `1,000.00`、`1,010.00`、`997.0`、`1,005.00`。舊 `Decimal(text)` 與 `pd.to_numeric` 會將帶逗號的價格視為無效，連帶使指標重新暖機、標籤整窗缺值。

11 檔 bounded 母體的逗號 OHLC 都在 2330、2454；兩者開／高／低／收儲存格數分別為 36/38/32/37、241/253/230/238。資料建置線另以唯讀查詢掃描全庫 5,317,343 daily rows：8,558 列有 builder 消費的逗號數值，共 44,208 格且全數分組合法；只出現在開、高、低、收、最後買價、最後賣價。TAIEX 的 3,088 列及八個數值欄沒有逗號。

全庫受影響範圍為 22 檔，其在 Direct OOC 原基線中共 35,582 rows（1.06%）。需重算這些股票的完整前綴及所有追加列，因指標影響可能延伸至最後一天；其餘股票可保留封存數值，合併時仍逐欄驗證。22 檔為 1519、1590、2059、2327、2330、2454、3008、3443、3533、3653、3661、4763、5269、6409、6415、6515、6669、6719、6781、6805、8454、910708。

新增 `utils/numeric_text.py` 僅移除**合法**千分位格式的逗號；`1,00.00` 等錯誤分組、NULL、`--` 仍交由原缺值／品質規則處理。指標共用 cleaner，研究資料的 Decimal 邊界亦使用同一純文字函式；沒有新增金融浮點計算、填補價格或修改 SQLite。新的 current capture 將 parser 檔案 SHA 一併綁入身分。

Root 對 run02 的 2330 完整 **3,092 列**做獨立參照：逐欄用 Decimal 轉換來源後，20 個指標的數值與缺值位置均與修正後 kernel 一致。真實 7/4 bar 的 close 恢復為精確 `Decimal('1005.00')`。本機結果在 `output/qa/model_repair_review/grouped_2330_source_oracle.json`。

full v1 builder 已完成並封存，執行期間未熱改其 source worktree；v1 含格式缺漏，**不得作最終 full fit 的已修正來源**。下列 full v2 已替換受影響來源及相依特徵／標籤，綁定 parser／kernel SHA；不放寬原 historical PIT gate。

## 全市場 v2 資料驗收

`E:/codex_model_repair_20260923/dataset/full_restated_v2/manifest.json` 已完成 **3,496,189 列、13 年分片**：原 Direct 基線 3,353,096 列與 143,093 列近期追加。合併精確替換 22 檔股票的 37,115 列（含 1,533 追加列），沒有創造新的 row IDs。Root 以獨立串流 Arrow 比較核對全部列、全部欄：3,459,074 列與 parent 完全一致，37,115 列與 corrected subset 完全一致，原 targets、列順序與日期不變；來源與輸出 hashes 在驗算前後一致。

千分位修正相對 full v1 使 11,009 列的特徵數值改變、7,392 列的 feature missing mask 改變；H5／H10／H20／H60 labels 及 mask 分別在 5,489／5,759／6,174／7,152 列改變。這些是逗號解析修正的差異，不代表整個 5/20 事故只有這些列。

- v2 dataset identity：`sha256:5b7c0979da1a3b1a967297deca8e88564217a260306c97f0a964a8e1922de3ea`。
- Manifest file SHA-256：`9b0603b6df3921af1711d971b9e09e881849fdca4743e265d3798299b9a955ce`。
- 外部 custody：`E:/codex_model_repair_20260923/training/full_restated_v2_source_custody.json`，file SHA-256 `e0062d9af685b383d09c96400d58fb34dd555ffb5a36c4afa88b60fae2b4e9e0`。另外綁定原 v1 custody；未觀察到 job-start source capture，明確保留 null，沒有補造開始證據。
- Root 證據：integration 的 `output/qa/model_repair_review/full_v2_independent_overlay.json` 與 `full_v2_root_custody_validation.json`。驗收涵蓋合併完整性與來源鏈，不能替代模型品質評估。

H5 完整重訓使用凍結的 integration commit `4c94b359`，不設定 `--max-fit-rows`，H5-only、batch 8192、兩執行緒，已於臺北 2026-09-23 15:38 完成。新輸出為 `E:/codex_model_repair_20260923/training/full_h5_repair_v2_root_release_20260923/runs/restated-repair-5a4ece1426e70aa3`。評估模型 fit 3,100,743 列、heldout 每組 144,088 列；最終模型 fit 全部 3,468,254 個成熟候選列。三份 heldout 預測的 114 個整數統計值由 root 以獨立 Decimal／整數程式驗算一致；不代表模型品質合格。詳見[完整 H5 重訓與評估](RESTATED_ALLOCATION_REPAIR_TRAINING_2026_09_23.md)。

## 驗證與並行重構

Root 對 bounded 新舊 13 份分片逐列比對 **22,093 列**：37 個未修訂 feature 的完整 payload 共 **817,441 項**相同，25 個重述 feature payload 共 **552,325 項**，其中 **84,758** 個數值改變。列次序、62 欄契約、targets/state 與標籤成熟日期保留；**210** 個 H60 labels 改變，其餘 **88,162** 個 horizon labels 完整一致。另確認最初 `2014-01-03:1101` 的 20 個技術指標皆按暖機規則缺值。此比對驗證保存範圍，不宣稱獨立重算全部指標與標籤；證據保存在 `output/qa/model_repair_review/bounded_full_original_preservation.json`。

bounded 新模型已完成四個原事件成熟 folds 與最終完整 fit；actual invocation 明確使用 random_state=42、HGB 60 次迭代、ridge alpha=1、兩執行緒，沒有宣稱可還原未記錄的歷史超參數。修訂後 210 列不在原 folds 中，因此原 folds 不能證明模型在事故期間的效果。Root 已獨立核對 426,624 組 base OOF predictions、96 個 fold groups 與 48 個 pooled 指標。最新資料的 bounded **13 檔 × 24 experts** 與完整 H5 **13 檔 × 3 experts** 均可實際讀回，詳見[當日研究輸入 QA](MODEL_REPAIR_CURRENT_INPUTS_2026_09_23.md)。固定 cash-only targets 不構成可學習的配置建議。

- 千分位修正的 causal kernel／dataset／current inputs tests **31 passed**，涵蓋數值等價、真缺值、nullable string、壞分組及缺值後暖機；technical publication／process-pool／既有 technical-analysis 回歸另 **25 passed**。parser／cleaner／capture 三檔 mypy 無錯，py_compile 與兩項量化靜態 guard 通過。
- 模型樣本的 12 份 heldout receipts、456 個整數統計值由 root 獨立驗算一致；限制及當日 13 檔推論證據見[當日研究輸入 QA](MODEL_REPAIR_CURRENT_INPUTS_2026_09_23.md)。
- 截至 dev `3462ec7a`，相關主工作樹測試 **28 passed**（pytest cache 寫入權限警告一則，測試本身成功）；15 個 ML 相容性凍結檔相對 `2268a98a` 沒有變更。
- 該次整合只以兩個窄 hunk 暫存本任務的文檔索引；原架構 dirty 內容保留。另 169 個既有 dirty 檔中 166 檔 bytes 不變，三份 untracked 重構文件在 owner 工作期間有並行變動、不在模型 patch 內。pre/post 核對結果保留於 integration 的 `output/qa/model_repair_review/dev_*_merge_56a6ba7f.json`；主 index 為空。

修訂歷史只能用於明示的 research refit。actual revision available time 不能回填到舊 decision；新的 bounded consumer 使用獨立型別／入口，不修改 frozen PIT row、正常 loader 或原 gate。兩個家族的完整 fit／評估／當日讀回已有版本化產物，但大盤來源差異尚待修復，不能將研究產物或 successful inference 當作整體品質驗收。

截至 dev `85e2be8a`，相關八組測試 **87 passed**（一則既有 pytest cache 權限警告）；targeted mypy、九個 Python 模組／腳本的 py_compile 及兩項量化 guard 通過。15 個相容性凍結檔相對 `2268a98a` 無變更。該次合入前後 **193 個**其他重構 dirty 檔逐檔 bytes 相同、index 為空，證據為 integration `output/qa/model_repair_review/dev_pre_merge_4c94b359.json`／`dev_post_merge_4c94b359.json`。
