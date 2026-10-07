# 技術規則同次視窗核驗重用

`evaluate_daily_technical_rules` 原本在五條規則與結果建立階段共十次計算同一不可變視窗狀態。現在每次公開呼叫只建立一個局部 `_WindowStatus`，傳給私有helper；沒有增加公開status參數或跨視窗／程序快取。window、sessions、features與parameters仍沿原frozen／tuple／Decimal型別，原source/window SHA、來源pins、feature lineage、prefix、未來日期、availability截止及逐規則判定都保留。

## 驗證

- owner新測試7 passed，原snapshot語意27 passed；原sandbox repo fixture strict resolve WinError5保留為環境失敗，沒有放寬正式guard。
- 中央初次34 passed／13 failed，13項皆為pytest basetemp沒有位於同一系統TEMP根的producer隔離guard拒絕；`C:/t/technical-rule-reuse-central-20261007-a` fixture保留。
- 對齊全新TEMP與pytest根後，中央三套46 passed／1 Windows symlink權限skip、8.55秒；raw：`output/qa/baldr_completion_m2_20261007/technical_rule_reuse_central_20261007_b.log`。涵蓋新因果反例、原snapshot計算與canonical／浮點／篡改拒絕、真16股新程序repository讀回與manifest／來源錯配。
- 新測試核單次只計算一次共同視窗與每個session fingerprint，五規則Decimal證據不變；壞SHA、future session、未核pins、不連續prefix及截止後來源仍fail closed，每次新評估重新核驗。
- 原固定257股query的非剖析單次4.8246224秒，前階段8.1980804秒；query/pins身份、258 declared／257 included／1 excluded／257 processed／0 pending／1 missing及原五股頁面相同。raw：`output/qa/baldr_completion_m2_20261007/full_v4_query_window_reuse_measurement_20261007.json`。query SHA仍`4ffdbd4660d51fb41b696ba417014cc2b6068f1b68f2c53f3b35475375d6c7d9`，rule SHA為`1731ac4978a72c4e5e0bed9bf7814850311c80a2035926fda95d79bbbf8e3591`。

## 限制

上述耗時是並行QA期間的單次觀測，不是冷暖／p95、1000或真N Gate，仍不足以宣告互動效能通過。此葉片尚未修改snapshot parser；後續單次decode內typed parts重用必須另審核，不能省略canonical、語意、rule或raw pins驗證。0f25b8c6真人候選尚未含本葉片；完整P00–P14／M3目標維持。
