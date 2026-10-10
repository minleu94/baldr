# B10 私人覆盤與來源分離（進行中）

> **日期與操作提示（2026-10-10）：** 本文件的 B09 custody 未完成／caller 待接線描述早於後續 B09 補強與 MainWindow bounded wiring，現況請以[B09 QA](BALDR_B09_PERSONAL_PORTFOLIO_20261006.md)、[P2／M03 integration receipt](BALDR_SECOND_WAVE_INTEGRATION_20261006.md)及[架構補記](../01_architecture/system_architecture.md)核對；這不證明本文件列出的全部 B10 caller 或 production writes 已完成。下方 rollback 表與命令屬歷史收據，不要直接照做。

中央排他 ownership：`app_module/decision_quality_service.py`、`app_module/decision_quality_repository.py`、新 selector／backup adapter 與具名 B10 tests；`data_module/config.py`、`ui_qt/main.py` 及文件仍由中央單一 owner 整合。B09 持有 Portfolio service/store，中央不共編。

實作前未來函數自查：本包只消費既有保存交易／notes／Evidence／Gap／Decay，保留原事件日與身份，不追加行情、不重新打分或改財務公式；未知可得性不授 PIT／ML／交易資格。市場衍生來源必須 readonly，私人覆盤 writer 不可經空庫回落到市場 DB。

## 回滾清單

| 檔案 | 變更 | 回復方式 | 風險 |
|---|---|---|---|
| DecisionQuality service/repository | 明示 source reader／private writer 與既有 notes selector | 僅在確認無其他 dirty 後 revert 本包 local commit | 已保存私人覆盤留存，不搬回市場庫 |
| 新 selection／backup adapter／tests | opt-in 路由及隔離驗證 | revert 本包 local commit，保留所有合成與正式資料 | 後續 B09/main 依賴需同步回復 |
| config/main／Manual／Snapshot | 明示選擇與操作 | 中央具名 commit 回復，不 revert 他人 lane | 禁止以全域 OUTPUT_ROOT 或 db_file 改值替代分流 |
| evidence_operations_service／B10 composition test | 原週報的私人覆盤 reader 與市場 decay reader 分離 | revert 具名中央 local commit，保留 synthetic 原資料 | 不改 B09 backend 或接管其 custody 鎖 |
| evidence_operations_history_repository／週報 CLI／CLI tests | 原週報 history 選 Review store，保存混合來源 refs | revert 具名中央 local commit，私人 history 留存 | readonly list 不建目錄，禁止回落市場 writer |

目前尚未宣稱完成 caller 接線或正式資料啟用；備份／還原由獨立三檔續包驗證，完成後補精確命令與接受範圍。

## 週報 composition 與歷史路由增量（2026-10-06）

中央排他檔：`evidence_operations_service.py`、`evidence_operations_history_repository.py`、既有週報 CLI/CLI tests、新 B10 composition test。設定 generic personal selector 後，DecisionQuality 讀取 exact 私人 Review route；Evidence/Gap/Decay 來源 query-only。readiness evaluator 使用 config 副本，不能重指共用 `db_file`。缺私人 review DB/table 不借市場舊 review，缺市場 decay 明示 unknown；完整原來源 refs 留在 detached `source_lineage`，不提升 snapshot/PIT 資格。

歷史 repository 於初始化及每次 connection 驗 DB/sidecars canonical、containment、links、regular-file/hardlink，I/O 使用既有 renderer；readonly 使用 `mode=ro` 與 `query_only`，不 mkdir/schema。CLI 保存至選取私人 Review DB，市場 working-copy 作證據來源；production-like/source guard 保留。list 在純配置解析下完成，空/單欄位配置不得 fallback。

新增驗證包含私人空庫不借市場、私人 review＋市場 decay、config 不變、missing source、同私人 DB 只有 weekly table 的缺 review、原 schema 新程序 hash/lineage 讀回、readonly query-only、constructor 後 hardlink sidecar 拒絕、CLI save→list 原市場/private bytes 不變，以及 list 空庫不建目錄、明示空 root 不借 env。B09 custody 批准仍未完成，本增量不轉移其 ownership 或代替 main 最終注入。

最終 affected union：`.venv/Scripts/python.exe -X utf8 -B -m pytest tests/test_baldr_b10_evidence_composition.py tests/test_evidence_operations_service.py tests/test_evidence_operations_history_repository.py tests/test_evidence_operations_history_dashboard_service.py tests/test_evidence_operations_cli.py -q -o addopts= -p no:cacheprovider --junitxml=output/qa/b10_evidence_history_union_20261006.xml`，28 passed／36.41s。XML SHA256 `7c4aed19534a795bed556dca11faf0c0479fb385bf0af6a3fc4bebec3737cb4a`。三 production 檔 targeted mypy、五 Python 檔 py_compile、quant guard、diff-check 均通過；未重跑 UI mandatory union，沒有真來源／正式私人寫入／Task／ACL／migration／清理。

## 私人覆盤核心接受範圍（2026-10-06）

`DecisionQualityService` 明示分開私人 review writer 與市場 Evidence／Gap／Decay readonly reader。私人 writer 必須注入與已選 PERSONAL/TRADES 路由完全相同的 Portfolio service，且 build 的 portfolio_id 必須等於該路由 identity；notes 必須使用同一 personal root，缺件在私人 review DB 建立前拒絕。讀取空私人 store 不借市場覆盤。原 legacy 未配置模式與財務公式保留。

來源 metadata 留存精確來源 DB、事件 ID 與原 event/gap/decay hash；私人 review hash 同時綁保存的交易、倉位及 notes DTO，防止不同來源因筆數相同被 deduplicate。原期間 review_id 與 schema 不變，同一期間不同內容仍遵守原 append-only 衝突契約，不覆寫。canonical 身份不含內部 extended I/O 前綴。

Repository 在 constructor 與每次 connection 前核私人 DB 及 `-journal/-wal/-shm` 的 canonical 路徑、containment、links、regular-file/hardlink；I/O 與 SQLite URI 使用共用 renderer。此為受控 custody 下的拒絕檢查，不宣稱能抵擋無排他 custody 的惡意並行替換。正式 migration／Task 啟用／真資料寫入仍未准。

驗證命令：`.venv/Scripts/python.exe -X utf8 -B -m pytest tests/test_baldr_b10_private_review.py tests/test_decision_quality_service.py tests/test_decision_quality_repository.py tests/test_personal_store_selection.py tests/test_decision_quality_dashboard_service.py -q -o addopts= -p no:cacheprovider --junitxml=output/qa/b10_private_review_focused_20261006.xml`：28 passed／6.05s。涵蓋原來源 bytes 不變、private 保存後新程序 readonly 讀回、不同來源等筆數不同 hash、錯路由／帳戶／notes 根目錄、DB 與 sidecar hardlink 拒絕。JUnit SHA256：`dc9a1dfc1d4d512993219ede0ba3ee0e9fecf6e43387fb465d5c6d23d949d51a`。

四 production 檔 targeted mypy、三 changed Python 檔 py_compile 與 quant_guard_linter 通過。首次把 personal fixture 放 repo 內遭既有 `personal_root_overlaps_application_package` 拒絕，改用原隔離 Temp 後上述命令通過，未放寬 guard。B09 per-I/O custody 依賴仍待批准，main 注入、完整 producer／consumer 路由及 UI union 尚未完成；本收據不提升 B09 或 B10 整包資格。

## 共用選擇配置的有限驗證

中央新增 `personal_store_selection.resolve_personal_store_selection(config)` 與 `TWStockConfig.personal_store_root/personal_store_mode`，以成對 opt-in 選擇私人 store；watchlist／notes 選擇維持獨立，未配置保持 legacy 相容。CLI 與環境設定一致，不改 OUTPUT_ROOT／市場 db_file，不 mkdir 私人 store。路由 identity 必須由 caller 已解析的帳戶／store 身份提供。

`pytest tests/test_personal_store_selection.py tests/test_personal_store_routes.py -q -o addopts= -p no:cacheprovider`：26 passed／0.64s；涵蓋 CLI、單設／未知模式在 config 建目錄前拒絕、legacy readonly 與空私人 store。新增 `assert_personal_store_path` 僅供 caller 每次 I/O 前核 canonical／containment／links／regular-file／hardlink，不授正式 migration 或抵擋無 custody 的惡意並行換路徑。config／selection 的 targeted mypy 在中央 service/repository 四檔聯集通過；後續 B09 必須採此獨立依賴接線，不能自造另一 mode 規則。
