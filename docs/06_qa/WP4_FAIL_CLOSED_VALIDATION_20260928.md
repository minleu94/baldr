# WP4 個人模型失效封閉驗證（2026-09-28）

## 範圍與判讀

本次只補驗個人 V2 候選在 RecommendationService 真呼叫路徑中的三種工程負控：非有限機率輸出、訓練來源切片改變、模型 artifact bytes 損壞。測試使用 `tmp_path` 建立的隔離 SQLite、候選與 policy；沒有讀寫正式 `D:` 資料、既有 `pc-fit-v7` 候選、M10 workspace、global pointer 或 promotion receipt。這是 fixture-based fail-closed caller regression，不是正式來源 PIT 或自然效果證據。

既有真候選結果另見 [個人產品交付 QA](PERSONAL_DAILY_PRODUCT_DELIVERY_20261006.md)：新候選可在明示的 user-declared research-only V2 下影響校準機率、保存並讀回；未改推薦排序。16 筆 holdout Brier 為 2730 bp，固定 50% null benchmark 為 2500 bp，差 230 bp，表現較差；這是應揭露的效果提示，不是個人採用的工程封鎖。After-cost 機率仍 unavailable/null。個人 outcome read model 為 `completed_with_pending`，3 列 pending、成熟 0；沒有自然績效或 global promotion credit。

## 三種 fail-closed 負控

| 注入情境 | 阻擋層與精確狀態 | canonical fresh-query 驗證 |
|---|---|---|
| Calibrator 回傳 `inf` | 數值邊界 `_calibrated_bp` 拋出 `InvalidCalibrationOutputError`；consumer 將此具名錯誤降為 unavailable projection，warning=`model_probability_output_invalid_fail_closed`。其他無關例外不由此新分支吞掉。 | 個人 policy event 保存 `effective_mode=rule_only`；sealed `legacy_invocation_context` 與 fresh query 保留同一 blocker。推薦仍為規則結果，capture 被拒。 |
| 修改隔離訓練來源的一筆 feature RSI | V2 consumer 在候選投影前重新驗 source-time/replay slice，拒絕來源不一致；warning=`candidate_training_source_time_unverified_fail_closed`。測試在 `finally` 將該筆 SQLite 值還原。 | 同樣保存並讀回 rule-only 結果與精確 warning；不產生 personal capture。 |
| 修改隔離候選實際 artifact 的一個 byte | safe artifact loader 以 manifest hash 阻擋；warning=`artifact_hash_mismatch`。測試修改的是本次 `tmp_path` 候選副本。 | 保存並讀回 rule-only 結果與精確 warning；不產生 personal capture。 |

三種路徑都經 public `execute_recommendation`、canonical `save_execution` 和新建 composition 後的 `queries.get`，並核對 execution 相等及 `canonical_payload_and_index_verified`。若讀回含 projection rows，必須恰有一列對應 `AAA`，且依 DTO 契約精確為 `status=rule_only`、`calibrated_probability_status=unavailable`、機率為 null、row warnings 含該負控 blocker；若 receipt 不存在，則必須明確是 `ml_read_status=unavailable` 並帶 `ml_receipt_binding_missing`。規則型 DecisionBatch 仍有選取列，沒有把 `rule_score` 假稱機率。所有負控都斷言 capture 不建立。

第一次 source 負控曾以錯誤的寬前綴預期比對 warning 而失敗；實際警告是 `candidate_training_source_time_unverified_fail_closed`。第一次 artifact 負控也用了不符實際 loader 的預期前綴；實際警告是 `artifact_hash_mismatch`。另有中間測試因對缺少 ML receipt 的合法 fail-closed readback 仍要求 projection row，及將 `RecommendationItem` 當成帶 `calibration_status` 的 projection 而失敗。最終測試改為驗證上述兩種明確 readback 形狀，沒有放寬 production gate。中間錯誤日誌保留在同一 ignored QA 目錄；只以 final4 通過日誌作本次結果。

## 比較與使用限制

目前證據只支持工程上的「模型可用且真錯誤能封鎖、回退規則並留存 blocker」。固定 5000 bp 是 null benchmark，沒有可用的同列 rule-model probability；不得用 `rule_score` 製造規則機率。After-cost 機率或成本／流動性來源缺失時維持 unavailable/null，不得視為 0 或虧損。沒有同一候選、結果列、horizon、成本、來源 lane 的規則模型比較資料，因此目前沒有證據支持「繼續」、「建議停用」或「替換」判斷；可支持的讀法是效果資料不足、且既有 holdout 指標較 null 基準差。這些效果資訊不替代真正來源錯配、未來資料、artifact 損壞或非有限輸出的硬阻擋。

此次 fixture 測試不產生 natural outcome，也不改 Stage B／C 結果、global evidence、promotion 或 UI。真候選正式來源限制、user-declared 時間語意及 native Qt 操作狀態以交付 QA 報告為準；不得將本次隔離負控外推為官方歷史 PIT 或可見 UI 驗收。

## 凍結版本與驗證

HEAD 為 `29ff35b4a17fa3fc270aef6168ab70eaf48eeb1b`。本切片的四個檔案 SHA-256：

| 路徑 | SHA-256 |
|---|---|
| `ml_module/recommendation_calibration_training.py` | `B8E1CD5E666DFB9C6BD9B815E79A97257C56A86AF98772D0404B745E6E11518E` |
| `app_module/recommendation_calibration_consumer.py` | `464093CE1EE5CF6BA34FB61D7A7C7608431861127EA09861CED219C4822DBD64` |
| `app_module/recommendation_service.py` | `F0DBE04DEFB2CDBD534F0DB2005FE508D353BC25A5B223A42CD04FDEF9C2B667` |
| `tests/test_personal_model_full_stack_integration.py` | `32700F2124F97074E212F13384DFB802CB6CD0641F4616241E300B681EA49498` |

隔離驗證：

- Full-stack：`.\.venv\Scripts\python.exe -m pytest tests/test_personal_model_full_stack_integration.py -q -o addopts= -p no:cacheprovider --basetemp .tmp_wp4_final_fs4`，3 passed／0 failed。Log SHA-256 `A1A9BD562F32B7DD87186A768143277B4B8A28C5B75A49C065F8C00258F39206`。
- 相鄰 calibration regression：`.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_service_calibration_integration.py tests/test_recommendation_calibration.py tests/test_recommendation_calibration_training.py -q -o addopts= -p no:cacheprovider --basetemp .tmp_wp4_adjacent`，25 passed／0 failed。Log SHA-256 `1DECE8A316A3AC5B517E9D4FE1370633A2837E04FE8EA545E9CFF37D786E7756`。
- Targeted mypy：`.\.venv\Scripts\python.exe -m mypy app_module\recommendation_calibration_consumer.py app_module\recommendation_service.py ml_module\recommendation_calibration_training.py`，0 issues；4 個修改的 Python 檔 `py_compile` exit 0；`git diff --check` exit 0。完整命令及輸出保存在 `output/qa/personal_daily_product_20261006/wp4_fail_closed_negative_validation_20260928/checks_freeze2.log`。

本記錄不把 3 個 source/test slice 的結果相加冒稱 WP4 全面驗收；相同 scope 的量化比較、自然 outcome 成熟、native Qt 個人模型旅程仍各有其獨立證據與限制。

## 2026-09-28 fallback row assertion follow-up

獨立 review 指出首輪測試以「不等於 active」及 `.get()` 比較，缺欄位時仍可能通過。已改成精確檢查 fallback row 的 status、機率狀態、null 機率與 row warning；無 row 時仍精確要求 read model `ml_read_status=unavailable` 及 `ml_receipt_binding_missing`。這裡 `status=rule_only` 是 `RecommendationCalibrationProjection.unavailable()` 的實際 DTO 值；`unavailable` 屬於 `calibrated_probability_status`，不改寫 DTO schema。

後續只改測試斷言，三個 production source pins 與相鄰 calibration route 沿用首輪凍結版。新 full-stack 命令 `.\.venv\Scripts\python.exe -m pytest tests/test_personal_model_full_stack_integration.py -q -o addopts= -p no:cacheprovider --basetemp .tmp_wp4_fb2`：3 passed／0 failed；完整 log 與本次 pins 見 ignored QA companion receipt `output/qa/personal_daily_product_20261006/wp4_fail_closed_negative_validation_20260928/fallback_row_assertion_followup_20260928/followup_receipt.json`。測試檔 `py_compile` 與 scoped `git diff --check` 皆 exit 0。

本次 follow-up current test pin：tests/test_personal_model_full_stack_integration.py SHA-256 `432AB0C70C60ECE5FA338DA1AD5ADBCB27ECF58DE46E1CE4690C743F73DD8D80`。三個 production source pins 維持首輪收據所列雜湊；新 full-stack 命令與完整 log 路徑見上方 follow-up 段落。
