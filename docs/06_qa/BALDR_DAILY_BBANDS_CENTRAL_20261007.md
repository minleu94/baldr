# 日常 BB 版號中央接線（2026-10-07）

> **後續狀態提示（2026-10-11）：** 本文的「先整合 BBP01 parent API」是 10/07 當時狀態；後續 [BBP01 母體驗證](BALDR_PARENT_BBANDS30_UPPER_20261007.md) 已完成 44-case focused union。本文的 daily caller／UI 接線仍未完成，10 個專屬案例與 2 個 v2 讀回案例不代表 v3 producer 或完整日常產品驗收。

固定基準 d222ba0dbd3e87991ba5404fec29470646af2c68。中央只修改 daily owner、runtime adapter、observation acceptance 與專屬測試。BBP01 的 parent/producer CLI 四檔仍由其 lane 排他持有，本次沒有改其來源。

runtime 與 observation policy 可新增同值 `feature_contract_version`；缺欄仍使用原 v2，明示 v3 使用 `daily-market-feature-snapshot.v3.bbands30-upper`。policy 方法 hash 按版號重建核對，runtime/policy 異版、跨 segment 異版、保存 parent/policy 異版均拒絕。舊 runtime 不傳新 parent 參數，明示版號才傳 `contract_version`。沒有調整配額、200GiB capture reserve、cohort 上限、資格或 Task。

操作順序：先整合 BBP01 的 frozen parent API，再在隔離配置的 runtime 與 policy 同時指定 v3；父層 universe 與來源仍用原明示 pin。preview 核完整 declared cohort、方法 hash 與版本後才 execute。缺件保持 unknown/incomplete；BB 上軌有限比較不代表 compression 已完成。未整合 BBP01 前不能以此 patch 宣稱 v3 日常保存或正式啟用完成。

驗證：專屬 10 passed/1.22s；兩個原 v2 真保存／新程序讀回節點 2 passed/8.22s；三個 source targeted mypy 零錯、四 Python compile、quant guard/diff check 通過。專屬 producer spy 只證明 kw 傳遞，不是真 v3 producer。原 `.pytest_cache` sandbox 寫入 warning 不影響測試，未調整權限。

raw/JUnit：`output/qa/baldr_daily_bbands_central_20261007/final.log`、`final.xml`、`v2.log`、`v2.xml`，完整 SHA 在同目錄 handoff.json。沒有重跑重型 UI gate、沒有真資料寫入、Task/ACL/Native/訓練或交易。三個剩餘 lane 的排他/API/驗收見 `output/plans/baldr_parallel_remaining_dispatch_20261007.md`；中央保留 main/config/shared DTO/global mount 與 Manual。九 Stage/24 UX、七有限 closed、兩性能例外不升格。

回滾：撤除隔離 runtime/policy 的新欄後 revert 本次中央 commit，原 v2 artifacts、BBP01 lane 與正式資料保留。
