# BALDR R01 Registry 有界同份讀取（2026-10-06）

## 範圍與交接

固定 base `097267ae58fc723f28cb4611f8c8572942d0853d`；branch `lane/baldr-r01-read-budget-20261006`，worktree `output/worktrees/baldr-r01-read-budget`。handoff SHA256 `d834296ce6e37c9c1246d713ab364e5138d3aad6b2fbfcce8ced114eb7659f84` 已核。唯一原計畫 `output/plans/baldr_product_experience_plan_20261004.md` §6.7／UX12、§8.8／§11 是依據，原文唯讀。

排他 production 僅 `app_module/research_history_lookup.py`、`app_module/research_run_service.py`；新增 `tests/test_baldr_r01_registry_read_budget.py`，需中央精確入冊。repository／DTO／schema／保存格式／writer／金融公式／store 權限／allowlist／UI 不變。Manual、Snapshot、原計畫與最終 union 由主 owner `01a11020-88c2-7506-acc3-d51ecb674032` 同步。Notes backup GUI、週月及更多指標不屬本包。

## API 與行為

`ResearchRunService.load_run_data(run_id, *, max_artifact_bytes=None, max_total_bytes=None, check_cancel=None)` 保留 `ResearchRunData` 與舊 caller 無預算呼叫。非空預算必須為正整數；每次 load 有獨立計費 context，不修改 service 共用狀態。lookup 把原 `ResearchHistoryReadBudget`／cancel 傳入，Registry resolve 缺 budget 回 `registry_read_budget_required`；列表維持 metadata-only，不額外讀 Registry artifacts。

原 caller 64 MiB／artifact、256 MiB／round 不變。讀前 stat 拒超限，64 KiB chunk hash 與保留 bytes，open 後及讀完 fstat、path stat 核 size／mtime_ns／dev／inode；Parquet 從同份已核 bytes decode，不 hash 後重開 path。aggregate 包含本輪實際讀入 equity、trades、portfolio-result、replay-lineage，各一次開檔；sidecar 原 descriptor、hash 與 parent identity guard 保留。回傳前再核本輪所有來源。

超限回具名 `artifact_byte_budget_exceeded`／`aggregate_byte_budget_exceeded`；來源替換／大小或時間變動回 `artifact_source_changed`，消失／無法讀取回 `artifact_source_unavailable`，取消回 `read_cancelled`。取消於 metadata 前、每個 chunk、codec／Parquet decode 前及兩份 Parquet 之間、回傳前檢查。既有同步 decoder 內部不可合作式中斷，於返回後拒絕結果；此 serialized 預算不代表解碼 RAM 上限，不新增解壓容量政策。這不是 shared store 全域 custody 或 writer 容量改造。

## 合成驗證

所有保存／讀回使用 repo basetemp，無正式資料／真 DB write／Task／ACL／Native／migration／fit／清理／push／dev cherry-pick。四種 Registry、unmarked 與 marked portfolio（有／無 lineage）、兩種 legacy、舊 caller、新 interpreter、相同 identity／DataFrame、來源 SHA／mtime／檔案集合不變均驗。負例覆蓋單檔及逐檔累加、兩種 sidecar 超限開檔前拒絕、單次開檔、chunk 取消、decode 間取消、hash／exact selection、同 size／mtime inode 替換、grow／truncate／消失。原 UI scoped tests 驗切換／取消／parent close 晚到不 open，未重跑 full UI／mandatory union。

原失敗 `final_focused.log/xml` 與 `debug.log/xml` 保留：新增 marked 無 lineage fixture 漏掉既有 parent-bound unavailable 欄位，保存 guard 正確拒絕；修 fixture，未弱化 guard。

最終 focused（R01＋原 B07／Registry／saved-rule UI）**101 passed／65.70s**；相鄰 portfolio-result／lineage／finalize **73 passed／1 Windows symlink skip／5.00s**。兩個 production targeted mypy、三檔 compile、quant guard 與 diff check 通過。原初始 focused 78 passed／23.80s 與 fixture 修正前 99 passed／1 failed／63.34s 原樣保存，不併稱最終成功。

驗證 raw 位於 lane `output/qa/r01/`，交中央副本與 `receipt.json` 位於根 repo `output/qa/baldr_r01_read_budget_20261006/`，含 raw/JUnit SHA、命令、old/new Git blobs 與受保護檔相等驗證。分組有重疊，不能累加為完整 App PASS。

```powershell
python -m pytest tests/test_baldr_r01_registry_read_budget.py tests/test_baldr_b07_research_history.py tests/test_research_run_service.py tests/test_ui_qt_saved_strategy_rule_card.py -q -o addopts= --basetemp=output/qa/r01/temp4 --junitxml=output/qa/r01/accepted_focused.xml
python -m pytest tests/test_r020_portfolio_result_registry_service.py tests/test_research_run_replay_lineage.py tests/test_research_run_portfolio_finalize.py -q -o addopts= --basetemp=output/qa/r01/temp2 --junitxml=output/qa/r01/affected.xml
python -m mypy app_module/research_history_lookup.py app_module/research_run_service.py
python -m py_compile app_module/research_history_lookup.py app_module/research_run_service.py tests/test_baldr_r01_registry_read_budget.py
python scripts/quant_guard_linter.py
git diff --check
```

## 回滾清單

| 檔案 | 類型 | 變更 | 回滾方式 | 風險 |
|---|---|---|---|---|
| research_history_lookup.py | 修改 | Registry budget／cancel kwargs | 在隔離 lane 還原 base 指定檔 | 撤回新讀取防護 |
| research_run_service.py | 修改 | 每次 load bounded verified bytes | 在隔離 lane 還原 base 指定檔 | 撤回新讀取防護 |
| test_baldr_r01_registry_read_budget.py | 新增 | R01 合成驗證 | 核對無其他變更後移除新增檔 | 喪失 R01 回歸證據 |
| 本 QA 文件 | 新增 | 範圍與驗收 | 核對無其他變更後移除新增檔 | 喪失說明 |

依序先核 lane dirty tree／owner 範圍，再還原本包兩檔並移除本包新增檔，最後跑原 B07／Registry tests。原始資料無變更，回滾不清資料或其他 lane。替代方案為獨立 revert 本 local commit，須先核中央整合依賴。

## 中央安全接手點

核 local commit parent／兩個 production blobs／raw/JUnit SHA 後覆核；新 test 精確入冊、Manual／Snapshot／唯一 plan 同步與一次 final union 留中央執行。本包完成後停等整合，不宣稱全產品完成。
