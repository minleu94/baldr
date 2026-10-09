# F06 波動範圍複合查詢契約（獨立 DTO 切片）

## 狀態與範圍

本文件描述 `daily-market-technical-official-disposition-volatility-query.v1` 的 canonical request DTO、純 predicate helper 與未核排序 helper。這個切片不讀取 SQLite、不開啟來源、不建立全母體 index，也不發行 qualified result/page。`query_identity_sha256`、來源 SHA 欄位與 JSON 自洽只能識別請求內容，不能授予來源或 reader 資格；真正接線仍須在同一次 exact source operation 中重核所有來源 pins，之後由 reader 發行 sealed result/page。

這是 F06 的原料範圍查詢入口，不代表 F06 的完整接線或 F03 KDJ 完成。F03 的 `KDJ 9/3/3 SMA` 仍是另一個明示條件組，後續 reader observer 必須能在同次全母體投影中合併 MA、KDJ 與 volatility。這裡的 BB30 與 ATR14 數值是 F06 leaf 定義的量化證據，不表示收斂、突破、趨勢建議或策略訊號。

## Canonical Query 欄位

Query V1 固定保存：

- `ma_source_query_json` 與 `ma_source_query_identity_sha256`：嵌入 F17 技術條件及 MA source recipe。nested MA query 必須保持 `ma_states=null`、`condition_combine_mode=AND`、`unknown_policy=include`，且 MA sort 為 `stock_code asc`。這些欄位只保留原來源條件，不提供外層組合、unknown、sort 或 page 的第二套權威；其中原 F17 技術 rule filters 仍是技術條件群。
- `volatility_read_session_identity_sha256`、`volatility_index_identity_sha256`、`volatility_source_request_identity_sha256`、`volatility_source_clock_identity_sha256`：預期的來源/索引 pins。DTO 只檢查其格式與來源時鐘、F17 decision cutoff/date 相符；真正 reader 必須重新核驗。
- 方法 pins：BB `daily_market.bollinger_bandwidth_sma30_population_2x` / `bollinger-bandwidth-sma30-population-2x.v1`，ATR `daily_market.atr14_sma_true_range` / `atr14-sma-true-range.v1`，並分別保存方法 identity SHA-256。只核 ID/version 不足以代表方法一致。
- `ma_states`、`bandwidth_min_pct`、`bandwidth_max_pct`、`atr14_min_pct`、`atr14_max_pct`：外層條件。範圍端點含等號；BB 與 ATR 的啟用範圍在 volatility 群內採 AND。
- `condition_combine_mode` 與 `unknown_policy`：三個條件群的唯一 AND/OR 與未知策略。三群為 F17 technical rules、MA alignment、volatility ranges；只有明確啟用的群組參與組合，停用群不會以 TRUE 參與 OR。只有一組啟用時組合正規化為 AND；沒有群組時正規化為 browse-only 的 AND/include，`unknown_policy=only` 無條件時拒絕。
- 最多 33 個全母體 `sort_clauses`。允許欄位來自 F17/MA 可排序欄位與 `bollinger_bandwidth_pct`、`atr14_pct`；如列出 `stock_code`，必須是最後的升冪 tie-break。page 不放在 Query identity 內。
- 固定資格限制：`scope=current_only`、`availability_status=unknown`、`source_available_at=null`、`historical_pit_eligible=false`、`qualification_status=request_only`。

若 hard eligibility 不成立，啟用群組標為 `not_evaluated`，unknown policy 與 OR 不得救回該 row。Audit-visible 與 predicate match 分開：row scope 可以顯示 excluded/pending 的稽核列，但它們不是符合條件或推薦。若所有條件群停用，helper 回傳 `not_applicable` 的組合結果並允許 browse；這不會創造正向 predicate match。

## Decimal 與界限

範圍只接受 `Decimal`，拒絕裸 float、bool、NaN、Infinity、負值、反向 min/max、過長 token 或超出 exponent/digit 範圍的值。等值上下界是有效的單值 inclusive 範圍；canonical 化讓 `1.00` 與 `1` 產生相同 identity。輸入值使用最多 34 位係數、指數及 adjusted exponent `[-100, 100]`、token 最多 256 bytes；JSON 深度最多 32、總 payload 最多 32 MiB，重複 key、非 canonical JSON 與 JSON 浮點數拒絕。來源 MA JSON 也限制 32 MiB。

PageRequest 獨立綁定完整 Query JSON 與 identity。`page_index` 必須為真正的 int，範圍 `0..1,000,000`；`page_size` 必須為真正的 int，範圍 `1..256`。`bool` 不可當整數。換頁不改全域 query identity。

純 sort helper 最多處理 100,000 筆未核投影，所有輸入 sort 值的 canonical JSON 合計最多 64 MiB，最多 33 欄且每欄依其公開欄位契約限定型別；大型整數在字串轉換前以 bit length 限制。排序每 256 列輪詢取消；null 在升序與降序都放尾端，並以股票代碼穩定破同值。Helper 輸出明確標示為 unqualified，不是 reader row/result/page。

## Truth 與排序語義

波動群只比較 query 明確啟用的範圍。已觀測值按 inclusive min/max 判斷；值缺失或 leaf state 為 unknown 時回 unknown。AND 中已知不符合會吸收另一條件的 unknown，避免 unknown 把已知 no-match 救回。跨三群的 AND/OR 僅聚合 active groups；unknown 的 include/exclude/only 只影響已 hard-eligible 的結果可見/納入策略，不能覆蓋 hard gate。純 helper 不計算 cohort denominator 或 page membership。

全母體應先套 hard eligibility 與三群 predicate，再依 canonical sort 排序，最後分頁；禁止在目前一頁局部篩選或排序。此切片只有純排序函式及 PageRequest contract，尚未有 reader-issued result/page 或實際全母體執行器。

## Look-ahead 與相容性

F06 leaf 僅由 exact decision date 之前已保存的 volatility measures 判斷，方法 measure 自帶 feature dates/window fingerprints；request DTO 檢查 F17 decision date/cutoff 與 source clock 一致，但 DTO 不重新驗原料。缺少官方 `available_at` 時依 leaf 與查詢契約保持 unknown/current-only，絕不標成 historical PIT。後續 reader 必須在 exact source observer 中確認每筆 measure 的方法 SHA、視窗日期不晚於 cutoff、來源 row fingerprints 及 source/index identity。

原 F17 與 MA query JSON/API 不變。新 DTO 嵌入 neutral MA source request 以沿用技術條件及來源 recipe；MA states、三群組合與 BB/ATR 範圍屬外層 Query V1。舊 F17/MA API 不得在新功能中被靜默改寫或當成 volatility qualification。

## 本切片測試範圍與尚缺項

配對測試以 synthetic typed MA request 與真實 F06 leaf measure DTO 驗證 canonical round-trip、方法 SHA、range/unknown、AND/OR、hard-gate/audit 分離、Decimal 正規化、JSON/排序/頁界限與取消。它不啟動 producer、SQLite、網路或正式資料，亦不證明任何 source pin 真實有效。

後續整合仍須新增同次 F17 exact read 的 bounded volatility collector/index、與既有 MA/KDJ observer 的原子 publication、完整 declared cohort counts、來源漂移/取消拒絕、全母體 query/result/page seal、跨頁 selected-row drill、收藏保存與新程序 exact reopen。F03 KDJ 仍未接入；本文件與本 DTO 均不可被描述成 F03/F06 full-N 或 UI 完成。
