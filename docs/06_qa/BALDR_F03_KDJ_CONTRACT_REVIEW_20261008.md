# F03 KDJ 方法契約與缺口盤點

日期：2026-10-08

狀態：`KDJ 9/3/3 SMA / kdj-sma.v1` 方法證據 leaf 已核准並實作；全母體 qualification、UI 與 F03 尚未完成。
範圍：只盤點既有 KD／KDJ 依據並記錄獨立版本方法證據；本文件不代表策略公式、Main、Watchlist、現有 v4 方法契約或原始資料已變更。

Root 審查續記：已授權獨立純計算 leaf／Decimal oracle 測試的受控實作，採明示 `KDJ 9/3/3 SMA / kdj-sma.v1`，不稱唯一標準 KDJ。這個 leaf 已有合成原料測試證據；來源自洽 hash 不授予 qualified 資格。完整母體 observer、query、收藏與 UI 尚未接入，舊 KD／v4 保存 bytes 保持既有版本。

Root 初讀實作續記：Decimal 計算使用固定 precision／rounding／Emin／Emax／clamp／traps，並納入方法 identity，避免繼承 caller Decimal 狀態。最初的 future-date 變造案例只證 transport tamper 拒絕，未證合法未來原料不影響 cutoff 結果；後續已補合法保存來源案例，將 cutoff 後列寫入合成來源，再以同一 cutoff 開啟快照並比較方法輸出。另補較長前綴只取末 14 列、負 J 的下降交叉與已高位不重複交叉向量。這些結果僅接受 leaf 的有限方法證據，不代表 F03 整體完成。

## 回滾與變更範圍

Root 複驗續記：重算 source `8559E01C...74A625D`／test `791D927F...555967DC` 與 owner 凍結值一致；全新 native 合成 basetemp 複跑 **12 passed，1.05 秒**，兩檔 mypy clean。已實讀合法 future-source 同 cutoff、末 14 列、J 負值及下降／不重複交叉測試。接受純方法 leaf 這一切片，資格仍 false；owner 接續設計同次 F17 exact verified-parent collector／全母體 index／global query／SavedRecipe，暫不修改共享 reader／builder，以維持 F02 固定 pins。完整 F03 尚未完成。

- 變更類型：新增純計算 evidence leaf、合成測試與本 QA 契約紀錄；不改既有 KD／v4、Main、Watchlist 或來源 reader。
- 回滾：確認沒有後續 consumer 引用後，可移除 `app_module/daily_market_technical_kdj_evidence_v1.py`、`tests/test_daily_market_technical_kdj_evidence_v1.py` 與本文件；QA attempt/preimage 是歷史證據，不應覆寫。
- 回滾風險：不改既有產品行為；移除後只失去這個新版本 leaf、測試與契約紀錄。

## 現況證據

原完成計畫 §5 的 F03 將 KD 列為已有規則、KDJ 列為待定規則；現有 KD 是 STOCH 5/3/3 SMA，今日 K>D 且前一觀測日 K≤D；低檔 K<30 與中檔 30≤K<70 屬既有 KD 版本。計畫明確要求 KDJ 自立 J、平滑與交叉定義，不能只把既有 KD 改名為 KDJ（[`baldr_product_completion_plan_20261006.md:206`](../superpowers/plans/baldr_product_completion_plan_20261006.md#L206)）。近期平行工作紀錄也把「現有 KD 不作替代」列為 F03 邊界（[`BALDR_PARALLEL_NEXT_WORK_20261009.md`](BALDR_PARALLEL_NEXT_WORK_20261009.md)）。

目前程式把舊規則固定為 `daily_market.kd_golden_cross_5_3_3_sma`，參數列明 `fastk_period=5`、`slowk_period=3`、`slowd_period=3` 及 SMA；判斷只讀 `slowk`／`slowd`，用今日 K>D 且前一觀測日 K≤D（[`selection_technical_rules.py`](../../decision_module/factors/selection_technical_rules.py)：`KD_CROSS_METHOD_ID`、`_KD_RULE_PARAMETERS`、`evaluate_daily_technical_rules`、`_kd_cross_predicate`）。v4 方法契約只有 `slowk`、`slowd` 等七項輸入特徵與五條規則，沒有 J，也沒有 KDJ 規則（[`daily_market_technical_method_contract_v4.py`](../../app_module/daily_market_technical_method_contract_v4.py)：`DAILY_MARKET_TECHNICAL_FEATURE_KEYS_V4`、`_FEATURES`、`_RULES`）。

現有因果指標路徑 `calculate_causal_indicators` 直接匯入 `talib`，並呼叫 STOCH 5/3/3 SMA（[`technical_indicators.py`](../../analysis_module/technical_analysis/technical_indicators.py)：第 87、192–203 行）。另存的 `talib_compatibility.py` 並非主路徑已接通的自動 fallback；既有程式參考審查指出主模組直接 `import talib`，相容模組沒有外部接線。若未來選用該相容實作，還要留意它的 `STOCH` 只把 fast-K 與 slow-K 平滑參數傳給 `ta` 套件，沒有使用 `slowd_period`；不能只憑函式參數名稱推定兩個執行分支完全一致（[`talib_compatibility.py`](../../analysis_module/technical_analysis/talib_compatibility.py)：第 43–45 行；[`GRAPHIFY_CODE_REFERENCE_REVIEW_2026_09_17.md`](GRAPHIFY_CODE_REFERENCE_REVIEW_2026_09_17.md)）。

已保存技術來源列保留 Decimal OHLCV、原始 token、股票、觀測日期及逐列 fingerprint；每股窗口最多 120 列（[`daily_market_technical_source.py`](../../app_module/daily_market_technical_source.py)：`DailyMarketTechnicalSourceRow`、`DailyMarketTechnicalSourceWindow`；[`daily_market_technical_read_session.py`](../../app_module/daily_market_technical_read_session.py)：`DAILY_MARKET_TECHNICAL_SOURCE_MAX_ROWS`）。v4 快照封存原料、source pins、最多兩個既有 feature session 與五條舊規則；其 availability 明確是 unknown、`source_available_at=None`、`historical_pit_eligible=False`（[`daily_market_technical_feature_snapshot_v4.py`](../../app_module/daily_market_technical_feature_snapshot_v4.py)：`DailyMarketTechnicalFeatureSnapshotV4`、`_POLICY`、`raw_rows`）。因此可以研究從已核的原料建立一個新方法，但目前舊快照本身不提供 KDJ 結果，也不提供歷史 PIT 資格。

## 已核准的 leaf 方法契約

此處定義的是與舊 KD 分離、可測且可保存的單一方法版本，不宣稱是唯一通用 KDJ 定義：

| 欄位 | 候選 v1 定義 |
|---|---|
| 方法 ID／版本 | `daily_market.kdj_kd_golden_cross_9_3_3_sma`／`kdj-sma.v1`。舊 KD ID、版本、欄位、canonical JSON 和收藏 bytes 不變。 |
| 輸入 | 同一已核保存來源、同一股票、按日期排序且 fingerprint 已核的 raw High、Low、Close；不讀 live DB 補洞。 |
| 原始隨機值 | `RSV(t) = 100 × (Close(t) − min(Low[t−8:t])) ÷ (max(High[t−8:t]) − min(Low[t−8:t]))`。窗口含當日，固定 9 個觀測列。 |
| K／D 平滑 | `K(t) = SMA_3(RSV)(t)`；`D(t) = SMA_3(K)(t)`。兩者均為包含當日的簡單移動平均。 |
| J | `J(t) = 3 × K(t) − 2 × D(t)`。不再對 J 做第二層平滑，也不截斷到 0–100；J 是可超出此區間的有限證據值。 |
| 交叉 | 僅當 `K(今日) > D(今日)` 且 `K(前一觀測列) ≤ D(前一觀測列)` 時為 `match`；今日相等不 match，昨日相等允許新交叉。此為候選的 K/D 交叉，J 隨結果保存供稽核，不宣稱存在額外 J 門檻。 |
| 暖機 | 9 列產生首個 RSV，3 個 RSV 產生首個 K，3 個 K 產生首個 D；判定兩日交叉至少需要 14 個連續有效原始觀測列。缺列、缺值、重複日、無效 OHLC 或不足暖機一律 `unknown`，不補 0、不回退到另一份 snapshot。 |
| 零分母 | 9 列 `最高價 == 最低價` 時 RSV 分母為零；該觀測明確為 `unknown: kdj_zero_range`，不填 0、不沿用前值。 |
| 數值政策 | 原料只接收已驗 Decimal token；在固定 `localcontext(prec=34, rounding=ROUND_HALF_EVEN)` 下計算並保存 K/D/J 的 canonical Decimal 字串。交叉只比較此同版本產生的 Decimal 值；不經裸 `float`、NumPy 或圖表數值回流。精度政策需進 method identity 和回歸向量。 |
| 門檻端點 | v1 不設低檔／中檔／超買超賣門檻，避免沿用舊 KD 的 K<30、30≤K<70，也不對 J 套同一範圍。若後續新增 J 區間條件，需另外命名規則並明定比較符號與端點。 |

此候選使用有限窗口 SMA，與遞迴式平滑作出明確取捨：SMA 可從有界 raw window 獨立重建，暖機長度及原始列可逐一列出，不需保存任意長歷史遞迴狀態或猜初始 K/D；代價是它不是遞迴 KDJ，輸出不能冒稱與遞迴平滑結果等價。若選遞迴平滑，必須另定 seed、歷史起點、逐列狀態保存／fingerprint 與最小有效前綴，這不是本候選的隱含替代方案。

選用 9/3/3 的目的，是把原料、RSV、K/D 平滑、J 公式、交叉和暖機完整定義為新方法。此版本已按此契約實作為證據 leaf；後續方法變更須發新版本，不新增舊規則 alias。

## Look-ahead／PIT 自查

1. **決策日期與截止**：所有 raw row 日期必須 `≤ decision_date`，且來源保存時計符合已核 cutoff。逐股錨在該次 exact snapshot 的 `current_session.feature_date`；不得因當日缺 KDJ 暖機或原料而向 live/latest、另一 snapshot 或較舊來源回退。
2. **同股同來源**：今日、前一觀測列及整個暖機窗口股票代碼、來源身份、session pins、原始 row fingerprint 必須一致；非同股或混來源拒絕，不以兩日日期相鄰推定同一交易所交易日。
3. **觀測日語義**：以來源已核的前一觀測列比較，不把「前一觀測列」改寫成「上一官方交易日」。`observed_prefix_contiguous=True` 只代表來源前綴已檢查連續，不證明官方行事曆完整或該 14 列是 14 個官方交易日。
4. **可得時間**：目前 v4 技術來源 `source_available_at` 未知，因此即使 feature date 在決策日之前，結果也只能是 current-restated research；`historical_pit_eligible` 必須保持 false。若觀測到可得時間晚於 cutoff，不能把該結果作為當時已知事實。
5. **排序與母體**：指標先在同一 exact saved parent 的完整 declared cohort 上逐股分類，再套既有外層硬資格與明示 unknown policy，全母體排序後分頁。排除、待處理或缺原料不能由 OR 條件救回；當頁不能重新計算或替代完整母體分母。
6. **無前視自查結論**：上述候選只用各日期及之前的 OHLC；rolling window 含當日、不含未來列，cross 只用前一觀測列與當日。此邏輯路徑本身避免未來列滲入，但仍須以 future-row mutation、cutoff-boundary 與新程序來源固定測試證明；可得時間未知使歷史 PIT 仍不成立。

## 已完成 leaf 與尚待接線的最小切片

已完成的範圍只包括下列純計算 leaf。真正走到 F03 全母體驗收，還需分開方法證據與 F17 讀取接點；單股公式 leaf 不算 F03 完成。

1. **方法證據 leaf（已實作）**：[`daily_market_technical_kdj_evidence_v1.py`](../../app_module/daily_market_technical_kdj_evidence_v1.py) 與 [`test_daily_market_technical_kdj_evidence_v1.py`](../../tests/test_daily_market_technical_kdj_evidence_v1.py)。輸入為既有 typed v4 snapshot，透過公開 `snapshot.to_dict()` 驗證 transport，再輸出 `match/no_match/unknown`、K/D/J、前後觀測日、warmup、原料 fingerprints、method ID/version、availability 與 PIT 限制。leaf 不做來源 I/O，也不取得 reader-issued qualification。
2. **完整母體接線**：新增 versioned `app_module/daily_market_technical_official_disposition_kdj_query_v1.py` 與真來源測試，接在已核 F17 exact reader 的同次 verified-parent 投影迴圈中；不要另行全量重讀或從 UI 當頁 raw rows 作市場篩選。F17 shared reader 的 hook 需由 Root 明確釋出，observer 綁 exact builder/session、source/manifest identity、完整 ordered cohort 與單次投影，外部自洽 hash 不得取得 qualified index。
3. **query 與分頁**：保存 query recipe 的方法／參數、KDJ tri-state policy、F17 原硬資格及來源 pins；對完整母體分類後 global sort，另以 typed page request 讀 ≤256 rows。停用 KDJ 群組不可在 AND/OR 中當作 TRUE，unknown、no-match、excluded、pending、missing 分母分開保存。條件／排序改變須使用原 exact source session 的公開 query API，不得套用頁內 filter。
4. **保存重開**：等 backend leaf 接受後另立 bookmark schema，不改既有 F17／KD bytes。Bookmark 保存明示 bundle reference、完整 recipe、page、選取股票與 row/result identities；新程序需由相同封存版本 exact reopen，再重算整個母體並核對原始 facts。operation/session identity 可以不同，source pins、原 cutoff、方法及 facts identity 必須一致；沒有來源或 pin mismatch 就拒絕，不能改讀 latest。
5. **UI 後續包**：backend full-N query 與 fresh-process reopen 通過後才接研究頁、比較、收藏、Main／Watchlist，並同步 Application Manual。UI 不自行算 KDJ、不改舊 KD 勾選、不從舊收藏推造 J。

## Leaf 驗證紀錄

- 方法／路徑：`daily_market.kdj_kd_golden_cross_9_3_3_sma`／`kdj-sma.v1`，純計算位置為 `app_module/daily_market_technical_kdj_evidence_v1.py`。
- 測試：隔離合成 SQLite 原料經既有 technical read session 與 snapshot builder 建立 typed snapshot；最終測試檔 SHA 對應的 `attempt09_native.log` 為 **12 passed in 1.01s**。測試涵蓋獨立 Decimal oracle、14 列交叉、常數與零區間、13 列不足暖機、無效最新列不回退、raw token／fingerprint tamper、已重算的同 cutoff future-source 追加列、20 列前綴僅末 14 列參與輸出、J 負值與下降交叉、前日已高不重複 match、外部 Decimal context 污染，以及 evidence hash 不取得 qualification。
- 無前視證據：固定 cutoff 為 `2026-10-08T16:00:00+08:00`，在合成來源追加 `2026-10-09` 至 `2026-10-11` 三列後重新以同 cutoff 讀取。前後快照都只含 cutoff 前 14 列；測試逐項比對 state、14 個輸入日期、14 個 raw row fingerprints、previous/current 兩日的 RSV/K/D/J 與日期，全部相同。snapshot identity 因來源副本不同而不同；這是獨立封存證據，不是把兩個來源當同一來源。未聲稱可得時間已知或歷史 PIT。
- 靜態檢查：leaf 與測試檔 `py_compile`、兩檔 targeted mypy、quant guard linter 均通過。方法使用明示 Decimal context，沒有裸 float 計算。
- 測試範圍限制：原料均為合成資料，不含正式來源、完整 F17 exact observer、全母體 query、保存重開、UI、收藏或效能驗收。數值與 source hashes 僅是方法證據及追溯資料，不是來源簽章或 qualification token。

## 驗收矩陣

| 面向 | 必要正例／負例 |
|---|---|
| 方法向量 | 固定 OHLC Decimal 向量逐列核 RSV/K/D/J；升勢、跌勢、平坦和 J<0／J>100；不與舊 KD 5/3/3 向量混用。 |
| 交叉語意 | 前一觀測列 K=D、今日 K>D 為 match；前一列已高於 D 不重複 match；今日 K=D 不 match；下降交叉不 match。所有輸出保存兩列實值與日期。 |
| 暖機／原料 | 13 列不足以判兩日交叉；14 列有效前綴可判。高低價全平、OHLC 缺值／不合法、重複或倒序日期、跨股票／跨來源、row fingerprint tamper 都拒絕或回具名 unknown，不回退湊值。 |
| 數值與版本 | 34 位 half-even 重複解析穩定、邊界相等、非常接近的 K/D 值、NaN／Infinity／float／超長 Decimal token 負例；公式、precision、參數或 method version 改變必改 identity。 |
| Look-ahead | 加入 cutoff 後的 future rows 不得改變 cutoff 前已核證據；future feature date／future available_at 拒絕或 unknown；raw prefix 的 calendar completeness 維持 unknown。 |
| 全母體 | 真 synthetic 257+1 跨段、含 match/no-match/unknown 與硬排除／缺件；全母體 counts、AND/OR、unknown include/exclude/only、排序與多頁集合用獨立 Decimal oracle 比對；取消不發布半份 query/result。 |
| 保存重開 | 真保存 bundle 新程序 exact reopen；改 live 根、刪歷史根、mixed archive、bundle/member tamper、method／cutoff／cohort mismatch 負例；新 operation ID 可不同但 source/fact/query recipe 必須按原版本重驗。 |
| 相容性 | 舊 KD 方法 ID、v4 method contract、canonical query／bookmark bytes 與原 KD 結果保持不變；回歸測試仍直接覆蓋既有 K<30 與 30≤K<70 語義。 |

## 尚未接受的範圍

本 leaf 測試只透過既有 reader 處理合成 SQLite，不跑 producer、正式來源或完整市場母體。它沒有證明方法具有投資效益，也沒有交付完整 F17 觀察器接線、全母體 query、fresh archive reopen、比較／收藏、UI、Manual、效能或同版 EXE。不得將 leaf 測試或自洽 evidence hash 當成完整 F03、reader qualification、歷史 PIT 或投資有效性證明。
