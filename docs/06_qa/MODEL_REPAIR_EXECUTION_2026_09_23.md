# 模型修復執行紀錄（2026-09-23）

## 目前判定

尚未完成完整模型修復或切換。全量資料建置、原 bounded 家族的特徵／標籤重算及研究訓練入口分線處理；既有兩個舊模型繼續隔離，rule_only 與正式權限不變。六檔樣本已實際 fit、評估與推論，但部分指標弱於 train-only naive；不能以樣本跑通作為全量驗收。

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

當下執行中的 full v1 builder／其 source worktree 不熱改、不刪除；v1 含格式缺漏，**不得作最終 full fit 的已修正來源**。後續須建立新版本與 identity，修正受影響來源及其相依特徵／標籤，並記錄 parser／kernel SHA。這不放寬原 historical PIT gate。

## 驗證與並行重構

- 千分位修正的 causal kernel／dataset／current inputs tests **31 passed**，涵蓋數值等價、真缺值、nullable string、壞分組及缺值後暖機；technical publication／process-pool／既有 technical-analysis 回歸另 **25 passed**。parser／cleaner／capture 三檔 mypy 無錯，py_compile 與兩項量化靜態 guard 通過。
- 模型樣本的 12 份 heldout receipts、456 個整數統計值由 root 獨立驗算一致；限制及當日 13 檔推論證據見[當日研究輸入 QA](MODEL_REPAIR_CURRENT_INPUTS_2026_09_23.md)。
- 截至 dev `3462ec7a`，相關主工作樹測試 **28 passed**（pytest cache 寫入權限警告一則，測試本身成功）；15 個 ML 相容性凍結檔相對 `2268a98a` 沒有變更。
- 該次整合只以兩個窄 hunk 暫存本任務的文檔索引；原架構 dirty 內容保留。另 169 個既有 dirty 檔中 166 檔 bytes 不變，三份 untracked 重構文件在 owner 工作期間有並行變動、不在模型 patch 內。pre/post 核對結果保留於 integration 的 `output/qa/model_repair_review/dev_*_merge_56a6ba7f.json`；主 index 為空。

修訂歷史只能用於明示的 research refit。actual revision available time 不能回填到舊 decision；新的 bounded consumer 必須是獨立型別／入口，不修改 frozen PIT row、正常 loader 或原 gate。最終交付仍須包含兩個原家族的完整實際訓練、可重播評估、當日輸入驗證與版本化模型產物。
