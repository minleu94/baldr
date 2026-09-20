# TPEX 背景技術 publication QA（2026-09-20）

## 結論

本次 bounded 修正處理的是背景 TPEX 更新入口完成 technical calculation 後，沒有呼叫既有 `publish_technical_indicator_receipt` 的接線缺口。受影響入口為 `scripts/run_tpex_full_refresh_and_technical.py`；它現在會在實際 calculation 成功後保存 input snapshot、建立 hash-bound computation evidence，再呼叫既有 publication producer。currentity skip 若找不到可重用的 verified computation receipt 會維持 blocked，不以目前 checked clock 偽造新的 publication availability。

這只修復 source → technical publication 的工程接線，不改 source contract、formal DB、active pointer、scheduler 設定、自然 capture 或 promotion authority。publication receipt 的 `prospective_only=true`／`historical_pit_eligible=false` 仍維持；QA 的正例不能回填 2026-09-18 的 natural 或 calibration credit。

## focused QA

既有 source-contract／background 測試為 `15 passed`：

```text
tests/test_tpex_background_refresh_script.py
tests/test_recommendation_calibration_source_contract.py
```

原始結果見 [pytest_15pass.txt](../../output/qa/technical_source_contract_20260919/pytest_15pass.txt)，變更檔語法與型態結果見 [pycompile.txt](../../output/qa/technical_source_contract_20260919/pycompile.txt) 與 [mypy.txt](../../output/qa/technical_source_contract_20260919/mypy.txt)。`git diff --check` 見 [git_diff_check.txt](../../output/qa/technical_source_contract_20260919/git_diff_check.txt)。

## 隔離真實鏈驗收

驗收重用已核准的靜態 SQLite backup，先核對來源與 QA copy 的 SHA-256 都是
`a5c57014253738a826a155071a30667338c7a7807ae9a0785cf33f29b3e2a99f`、大小
`3,598,340,096` bytes，再以 normal SQLite `integrity_check=ok` 讀取。這是 verified immutable backup file copy，不能解讀成 live WAL snapshot。官方 2026-09-18 TPEX raw 只在 QA copy 受控 apply，`868 inserted` 且 `readback_verified=true`；正式 DB 沒有寫入。

在既有 QA snapshot 內只清除 `technical_indicators` 的 `1259`／`1569` 衍生列，再以 `force_all=False`、`ignore_existing_files=True` 分別執行實際 `UpdateService.calculate_technical_indicators`。兩檔都回報 success，完成後 QA technical table 為 `1259=2933`、`1569=3075` rows；publication receipt `d40d077390af636a` 的 `technical_computation_evidence_status=verified`、`covered_symbols=[1259,1569]`、`source_receipt_count=9`。完整 compact readback 見 [recalc_1259_1569_correct_shadow.json](../../output/qa/tp20_20260920T061923Z/recalc_1259_1569_correct_shadow.json)。

read-only source-contract 重查使用正確的 source artifact root
`D:\Min\Python\Project\FA_Data_Shadow`，沒有寫入 Shadow。舊 cutoff `2026-09-18T12:50:05Z` 明確為 `technical_prospective_available=false`；實際 QA observation cutoff `2026-09-19T23:35:53-07:00`、Taipei decision date `2026-09-20` 時，`technical_prospective_available=true`，technical value／lineage／feature snapshot 均 verified，`price_up.prospective_status=ready` 且 prospective blockers 為空，corporate adjustment custody 的 prospective proof 為 true。formal lane 仍 blocked，因 `formal_technical_source_contract_unverified` 與 formal corporate contract 尚未通過；這不是 adoption 或 natural credit。

## 不採認的早期 probe

早期使用 live DB `immutable=1` override 並手填 `calculation_result.success=true` 的 probe 不具驗收效力；另一份連續兩次 `force_all=True` 的 probe 只留下第二檔 symbol，也不能當雙股票正例。兩者均保留為歷史 QA artifact，不納入本結論。最後 recalc 的 console `cp1252` 結尾輸出曾因繁中 JSON 造成 exit `1`，但 compact JSON 已成功寫入、publication 已完成；後續 read-only reinspect exit `0`，故該 console encoding 問題不等同 calculation 或 publication 失敗。

## 未來操作邊界

執行背景入口後，先讀 `<OUTPUT_ROOT>\scheduled\technical_indicator_publication\<source_date>\<id>\receipt.json`。`technical_step_status=passed` 必須伴隨 `technical_computation_evidence_status=verified`、source receipt hash／raw hash、technical output binding 與 exact symbol coverage；currentity skip 則必須有可驗證的 computation reuse lineage。receipt 通過只代表 prospective source publication 可讀，不代表 20-session natural maturity、calibration adoption、active promotion 或 broker action 已完成。

正式 latest 與自然資料本輪沒有被回填或改判；自然 credit 仍只能由正常排程在合法 decision cutoff 產生。
