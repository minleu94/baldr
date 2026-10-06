# BALDR B01-H6/H7 歷史 label 契約邊界裁決（2026-10-06）

本包僅裁決 H6/H7，承接 [中央精確表](BALDR_CLOSEOUT_STATUS_20261006.md)。固定 base `5d9ddf9d611bd6e117d75d0b4fdbf8751ee2e5a0`，隔離 branch `lane/baldr-b01-h6-h7-20261006`，worktree `output/worktrees/baldr-b01-h6-h7`。主 owner 為 `01a11020-88c2-7506-acc3-d51ecb674032`。修改範圍僅 guard、CLI tests 與本文件；shared DTO、app reader、其他 production、source_id 待批准三檔與 global aggregate assertion 均未修改。

## 原始來源與裁決

唯一原 plan `output/plans/baldr_product_experience_plan_20261004.md` SHA256 `b3344fbd53ff53918be995eba9fb7ae3f6d28fe14253587d978a965ff886e8d7`；Astra 附件 SHA256 `1b724facbbc1712cc93ca3ddb204ea95f2ebb5efd1bdb18cc1733a3ff005be60`；Sol review SHA256 `8e97eca8f1ae3da4538b441b246fa0b36535f1a97c34c416c488079a253f264e`。三者只讀，未追加或另立 roadmap。

先核 `scripts/check_ml_shadow_boundary.py::main`：CLI 以自身 repo root 執行 `MLShadowBoundaryGuard.inspect()`，從 `ml_module`、六個 production roots 與 `artifact_contracts` 原碼 AST 取得結果；有任何 violations 即 exit 1。中央原始 `output/qa/b15_integrated_ml_boundary_20261006.log` SHA256 `37d032533faa92bef335ab4c74fc86df348aead0c9b654d2525c0001ced56511` 為 676 檔／8 條／FAIL，沒有豁免檔或 baseline suppression。

H6/H7 是**同一個 exact caller 的兩條 symbol binding**：`app_module/rule_research_label_readiness.py` → `ml_module.historical_contracts.HistoricalLabelRow`、`HistoricalLabelSpec`。未增加第二個 caller 或整模組 allow。alias 仍按原 symbol 核驗，混入未核符號則逐條拒絕。

`historical_contracts.py` 只 import `__future__`、`dataclasses.dataclass`、`datetime.date`、`typing.Literal`，`ml_module/__init__.py` 只有 docstring。兩個 frozen DTO 的建構只用 `_require_non_empty`／`_date` 與整數／日期驗證，`HistoricalLabelRow.is_fit_eligible` 只比較 ready、缺值及 `available_date <= training_as_of`，不讀模型、不連 registry、不訓練。

caller 的 `build_label_readiness_batch` 負責正規化 policy／split、路徑與有界 receipt，並呼叫 app `read_forward_receipt`；後者驗證 sealed source、pins/hash/revision 與 qualification。receipt 檔案讀取與 path resolution 是 app orchestration 原有責任，不能據此聲稱整個 reader 零 I/O。兩個 DTO 的 caller 使用路徑是 label spec 建構、`_make_label_row` 建構／asdict／日期資格投影，不把 I/O 下推到 ML DTO。

因此僅在 guard 增加該 caller 的兩個 exact symbols；writer／initializer／trainer、整 namespace、wildcard、未核 DTO 與不匹配 caller 仍拒絕。未移動共享契約，原 class identity、label policy／schema／target、整數 bp、unknown 與 research-only 資格不變。

## 零 I/O 與負例證據

CLI tests 的 cold subprocess 在 stdlib bootstrap 後，確認 `ml_module` 尚未 import，安裝 audit hook 和 I/O tripwires，再冷載入原 module。只允許 exact `ml_module/__init__.py`、`historical_contracts.py` 的 readonly 原碼／bytecode loader opens；其餘檔案 opens／writes、DB、socket、Windows registry、subprocess 與 filesystem mutation 皆拒絕。`-B` 禁止 bytecode 寫入。DTO 建構、asdict、replace、frozen 拒寫、invalid horizon／日期／bool value／missing ready，以及 cutoff／pending 反例全部在封鎖內執行。最後 ML loaded module set 精確只有 package 與 historical_contracts，沒有 registry 或 trainer import。

原 caller 的 class identity 與純 `_make_label_row` 在檔案／DB／network／`read_forward_receipt` tripwires 下驗證；known research availability 建構原 label DTO，unknown 不構造合格 label，兩者在 current-observed／unknown source 下仍無 temporal training candidate，selection unknown／research-only 保留。既有 sealed receipt tests 另驗來源 bytes、分母、policy hash、成本／benchmark 缺件與 false qualification。

首次測試 62 pass／1 fail：tripwire 攔到 stdlib `__future__.pyc` bootstrap，未發現 DTO 資料 I/O；將 `__future__` 預載到 bootstrap 後重驗。原失败 log／XML 保留，不擴大允許的 loader files。中間 CLI 34 pass／1 fail 收據同樣保留；修正後 CLI 35 pass。

## 實際驗證與限制

命令皆在本 worktree，以主 repo `.venv/Scripts/python.exe -X utf8 -B` 執行；完整 paths／exit／SHA256／blobs 見 ignored `output/qa/b01_h6_h7_handoff.json`。

- Focused：`-m pytest tests/test_ml_shadow_boundary_cli.py tests/test_ml_historical_contracts.py tests/test_rule_research_label_readiness.py tests/test_rule_research_label_readiness_cli.py -q -o addopts= --basetemp=output/qa/b01_h6_h7_verified_temp --junitxml=output/qa/b01_h6_h7_verified.xml`，**63 passed／38.08s／exit 0**，同版 raw／JUnit 完整保留。
- Targeted：`-m mypy ml_module/shadow_boundary_guard.py`，1 source file 成功。
- Compile：`-m py_compile ml_module/shadow_boundary_guard.py tests/test_ml_shadow_boundary_cli.py`，成功。
- Quant：`scripts/quant_guard_linter.py`，precision／look-ahead AST guards 成功。此變更不改策略、報酬公式、價格／訊號／benchmark 時序；cutoff／pending 拒絕測試保留，不把 label 未來結果放入 decision-time features。
- Diff：`git diff --check` 成功；readonly DTO／reader、global assertion 及 source_id 三檔均逐 Git blob 等於 base。
- 全 guard standalone 一次：`scripts/check_ml_shadow_boundary.py`，**676 檔／6 違例／exit 1**；與中央原報告逐項相減僅移除 H6/H7，新增違例 0。focused 的 CLI assertion 仍要求非零出口與完整六條，不以 synthetic allow 測試稱 repo PASS。

## 剩餘六條仍是真問題

| # | caller → symbol | 保留的工程責任 |
|---|---|---|
| H1 | ml_module/current_observed_feature_snapshot_composer.py → app_module.recommendation.queries._read_regular_file_no_follow | orchestration 移 app／注入 readonly port，no-follow/source pins 保留 |
| H2 | 同 caller → app_module.saved_recommendation_queries.build_recommendation_execution_queries | query 建構留 app，完整母體與 identity 保留 |
| H3 | 同 caller → app_module.saved_recommendation_queries.execution_result_config | config 留 app，不增 source/fallback |
| H4 | app_module/personalization_read_service.py → ml_module.recommendation_calibration_evidence.verify_natural_maturity_session_proof | bounded verifier／純契約 ownership 裁決，原 availability/hash/session proof 不放寬 |
| H5 | app_module/recommendation_calibration_consumer.py → ml_module.recommendation_calibration_training.InvalidCalibrationOutputError | 純 exception 分離且 class/serialization 相容，不授 trainer |
| H8 | app_module/stock_research_report_provider_adapters.py → ml_module.current_restated_research_bridge.load_current_restated_outcome_model | 注入核驗 artifact/source/target port，不讓 view 載模型 |

`tests/test_ml_shadow_dependency_boundary.py::test_repository_respects_ml_shadow_dependency_boundary` 的 `assert report.violations == ()` 保持原 blob；六條未修使 global boundary 仍 FAIL，沒有 xfail、刪 assert、改 baseline 豁免或宣稱整包／Stage done。H1/H2/H3 在 CLI 中同模組 import 的兩個 occurrences 沿原輸出保留，不能去重當五條。

原 9 Stage＝1 done／8 partial／0 pending、24 UX＝2 done／22 partial／0 pending、七有限 closed、性能例外與其他工程待辦均不變。無 UI／全 train 重跑、真 DB／Task／ACL／Native／migration／fit／promotion／交易／push／dev cherry-pick。本機 commit 後停等中央整合，worktree 保留。

回滾：整合前在此 worktree 先檢查 dirty ownership，再 `git restore --source=5d9ddf9d611bd6e117d75d0b4fdbf8751ee2e5a0 -- ml_module/shadow_boundary_guard.py tests/test_ml_shadow_boundary_cli.py`；本文件若需移除，先確認無新 owner 內容，再以 `Remove-Item -LiteralPath docs/06_qa/BALDR_B01_HISTORICAL_LABEL_BOUNDARY_20261006.md` 處置。風險為撤回本次 H6/H7 裁決／測試證據；正式資料無風險，已整合後回滾由中央 owner 決定。
