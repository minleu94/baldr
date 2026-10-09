# F03 KDJ 複合查詢契約（未核資格 leaf）

日期：2026-10-09  
狀態：獨立 query/predicate/sort/page-request 契約；尚未接入 F17 exact observer、全母體 reader、UI 或收藏。

## 範圍

`app_module/daily_market_technical_official_disposition_kdj_query_v1.py` 定義 KDJ 查詢要求、三值群組判讀、排序投影和獨立頁碼 request。它不讀 SQLite、bundle 或股票快照，不建立 reader-issued result/page，也不授予 KDJ compact entry 來源資格。即使 request、entry 或 sort projection 的 SHA-256 自洽，仍只代表內容識別；未來 reader 必須在同一次 F17 exact read 中驗證 parent/snapshot/source pins、日期與完整 cohort。

本 leaf 採用已版本化的 `kdj-sma.v1`（9/3/3 SMA）method identity。來源可用時間維持未知、資料可用性維持未知、歷史 PIT 資格為 false。KDJ 方法 leaf 與本查詢契約都不宣稱完成 F03 全母體接線。

## DTO 與 canonical identity

`DailyMarketTechnicalOfficialDispositionKDJQueryV1` 使用 schema `daily-market-technical-official-disposition-kdj-query.v1`。JSON 包含：

- 完整中立 `ma_query_json` 與其 identity；該 MA query 保留 F17 bundle、manifest、decision cutoff、技術 store、cohort 與官方來源 pins。
- `kdj_source_request_json` 及其 request identity，以及 KDJ read-session、index、source-clock identity 欄位。這些 SHA 欄位在本 leaf 仍是 request pins，不能單獨證明 reader 已核來源。
- 外層 `ma_states`、`kdj_states`、`condition_combine_mode`、`unknown_policy` 與排序 clauses。外層 MA 狀態是研究條件；巢狀 MA query 的 MA 條件必須停用，避免兩個 MA 條件來源。
- 固定 KDJ method ID、version 與完整 method identity SHA。source availability 為 null、availability 為 unknown、PIT 與 reader qualification 均為 false。

查詢 identity 是固定 body 的 canonical SHA-256。建構、`to_dict()`、JSON 解碼與 predicate/sort 入口都重驗巢狀 DTO、來源配對、狀態集合、active-group 正規形、排序欄位和 identity；直接建構或 `dataclasses.replace` 不能藉由重新計算 self-hash 接受語意無效的狀態。巢狀 JSON 最大 32 MiB，含 JSON escaping 與 query identity；source request 上限 16 KiB；JSON 深度最多 32。重複 key、float、超界整數、非 canonical JSON、未知欄位或未知 method 均拒絕。

`DailyMarketTechnicalOfficialDispositionKDJPageRequestV1` 使用獨立 schema。它綁完整 query JSON、query identity、頁碼與每頁筆數；頁碼不進 global query identity。頁碼索引範圍為 0–1,000,000，每頁 1–256 列。頁 request 仍只是要求，不是已核 Page。

## 群組、未知與 hard eligibility

目前純 predicate 群組為：F17 技術 rule filters、外層四均線狀態、KDJ 狀態。F17 bundle 的 row scope、market/disposal 與股票範圍仍由外層 hard eligibility 決定，不能放進 OR 讓不合資格列回流。技術群是否啟用取自巢狀 F17 query；MA 與 KDJ 啟用狀態分別取自外層 `ma_states` 與 `kdj_states`。

只有啟用的群組參與 AND/OR；停用群不以 TRUE 參與 OR。少於兩個啟用群時 combine 正規化為 AND；完全未啟用時 unknown policy 正規化為 include，且 `only` 在沒有啟用條件時拒絕。符合、未知與排除策略為：include 收 match/unknown，exclude 只收 match，only 只收 unknown。未知不補成 match，也不改寫其來源理由。

hard eligibility 在群組合併前處理。若列被排除，啟用群結果為 `not_evaluated`，OR 的其他 match 不能救回。若沒有啟用研究群，audit-visible 列可保留作瀏覽記錄，但 predicate candidate 仍為 false。可見列數與符合候選數必須由未來 reader 分開計數。

KDJ 群只接受 `DailyMarketTechnicalUniverseKDJCompactEntryV1`。它核對 stock code、同列 snapshot identity、source clock、decision date/cutoff，並拒絕晚於 cutoff 的 current/previous feature date。已核方法輸出 unknown 時，即使篩選集合含 match，也保留 unknown。此處 entry 是 projection-unqualified DTO；reader 仍須用同次 exact parent callback 驗證它來自該列，而不能信任呼叫者傳入的 snapshot hash。

## 全域排序邊界

排序 clauses 最多 33 個，不重複欄位；若指定 `stock_code`，它只能作最後的 ascending tie-break。欄位和值必須符合實際型別，禁止裸 float。Decimal 值限定有限值、最多 34 位有效數字與 bounded exponent。未知/null 在升降序都固定排尾。

`sort_composite_keys_v1` 接收最多 100,000 個未核 sort keys。它先檢查每列最多 16 KiB、總排序投影最多 64 MiB，再配置排序所需集合與分區；檢查、重複碼掃描、每欄分區及排序前後均輪詢取消。它輸出的 tuple 仍標示為 `sort_projection_unqualified`，不是 result、page 或 reader qualification。

## 下一個完整 F03 接線切片

正式全母體接線仍待 F02 共用 verified-projection hook 釋出。後續需在同一次 F17 exact read 的單一 snapshot→row callback 中，原子投影 MA、KDJ 與 F06 volatility；完整驗證 ordered cohort、parent root/receipt/clock/method pins，再一次性發布 qualified index/session/result。舊 F17/MA opener 不應默算 KDJ；只有明示的 KDJ query path opt-in。若任何群、source 或取消檢查失敗，不得發布 partial result。

完整 executor 必須一次掃描 hard-eligible cohort，合併已核的技術/MA/KDJ/volatility truths，先做全域排序再切頁；翻頁沿同一 issued result materialize，不重算母體。F06 volatility 與 MA、KDJ 是不同研究群；未來 unified query 必須明示所有群組狀態與停用語義，不能把目前三群 DTO 說成完整 F03。SavedRecipe 與 UI、跨程序 exact reopen 也未包含在本 leaf；後續必須以明示保存來源重新 exact-open，不得掃 latest、讀 live source 補值或升級 PIT。

## 本 leaf 測試證據

配對測試位於 `tests/test_daily_market_technical_official_disposition_kdj_query_v1.py`，使用合成 typed DTO，不建立 reader-issued source。測試覆蓋 canonical query/page identity、nested MA 中立性、來源 pin、rehash malformed DTO 拒絕、群組正規化、typed KDJ truth、hard gate/audit visibility、unknown policy、排序與 page bounds、JSON parser guards。這些結果只支持純契約，不能代替 full-N、exact reopen、UI、收藏或正式資料資格驗收。
