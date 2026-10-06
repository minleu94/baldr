# B10 私人覆盤與來源分離（進行中）

中央排他 ownership：`app_module/decision_quality_service.py`、`app_module/decision_quality_repository.py`、新 selector／backup adapter 與具名 B10 tests；`data_module/config.py`、`ui_qt/main.py` 及文件仍由中央單一 owner 整合。B09 持有 Portfolio service/store，中央不共編。

實作前未來函數自查：本包只消費既有保存交易／notes／Evidence／Gap／Decay，保留原事件日與身份，不追加行情、不重新打分或改財務公式；未知可得性不授 PIT／ML／交易資格。市場衍生來源必須 readonly，私人覆盤 writer 不可經空庫回落到市場 DB。

## 回滾清單

| 檔案 | 變更 | 回復方式 | 風險 |
|---|---|---|---|
| DecisionQuality service/repository | 明示 source reader／private writer 與既有 notes selector | 僅在確認無其他 dirty 後 revert 本包 local commit | 已保存私人覆盤留存，不搬回市場庫 |
| 新 selection／backup adapter／tests | opt-in 路由及隔離驗證 | revert 本包 local commit，保留所有合成與正式資料 | 後續 B09/main 依賴需同步回復 |
| config/main／Manual／Snapshot | 明示選擇與操作 | 中央具名 commit 回復，不 revert 他人 lane | 禁止以全域 OUTPUT_ROOT 或 db_file 改值替代分流 |

目前尚未宣稱完成 caller 接線或正式資料啟用；備份／還原由獨立三檔續包驗證，完成後補精確命令與接受範圍。

## 私人覆盤核心接受範圍（2026-10-06）

`DecisionQualityService` 明示分開私人 review writer 與市場 Evidence／Gap／Decay readonly reader。私人 writer 必須注入與已選 PERSONAL/TRADES 路由完全相同的 Portfolio service，且 build 的 portfolio_id 必須等於該路由 identity；notes 必須使用同一 personal root，缺件在私人 review DB 建立前拒絕。讀取空私人 store 不借市場覆盤。原 legacy 未配置模式與財務公式保留。

來源 metadata 留存精確來源 DB、事件 ID 與原 event/gap/decay hash；私人 review hash 同時綁保存的交易、倉位及 notes DTO，防止不同來源因筆數相同被 deduplicate。原期間 review_id 與 schema 不變，同一期間不同內容仍遵守原 append-only 衝突契約，不覆寫。canonical 身份不含內部 extended I/O 前綴。

Repository 在 constructor 與每次 connection 前核私人 DB 及 `-journal/-wal/-shm` 的 canonical 路徑、containment、links、regular-file/hardlink；I/O 與 SQLite URI 使用共用 renderer。此為受控 custody 下的拒絕檢查，不宣稱能抵擋無排他 custody 的惡意並行替換。正式 migration／Task 啟用／真資料寫入仍未准。

驗證命令：`.venv/Scripts/python.exe -X utf8 -B -m pytest tests/test_baldr_b10_private_review.py tests/test_decision_quality_service.py tests/test_decision_quality_repository.py tests/test_personal_store_selection.py tests/test_decision_quality_dashboard_service.py -q -o addopts= -p no:cacheprovider --junitxml=output/qa/b10_private_review_focused_20261006.xml`：28 passed／6.05s。涵蓋原來源 bytes 不變、private 保存後新程序 readonly 讀回、不同來源等筆數不同 hash、錯路由／帳戶／notes 根目錄、DB 與 sidecar hardlink 拒絕。JUnit SHA256：`dc9a1dfc1d4d512993219ede0ba3ee0e9fecf6e43387fb465d5c6d23d949d51a`。

四 production 檔 targeted mypy、三 changed Python 檔 py_compile 與 quant_guard_linter 通過。首次把 personal fixture 放 repo 內遭既有 `personal_root_overlaps_application_package` 拒絕，改用原隔離 Temp 後上述命令通過，未放寬 guard。B09 per-I/O custody 依賴仍待批准，main 注入、完整 producer／consumer 路由及 UI union 尚未完成；本收據不提升 B09 或 B10 整包資格。

## 共用選擇配置的有限驗證

中央新增 `personal_store_selection.resolve_personal_store_selection(config)` 與 `TWStockConfig.personal_store_root/personal_store_mode`，以成對 opt-in 選擇私人 store；watchlist／notes 選擇維持獨立，未配置保持 legacy 相容。CLI 與環境設定一致，不改 OUTPUT_ROOT／市場 db_file，不 mkdir 私人 store。路由 identity 必須由 caller 已解析的帳戶／store 身份提供。

`pytest tests/test_personal_store_selection.py tests/test_personal_store_routes.py -q -o addopts= -p no:cacheprovider`：26 passed／0.64s；涵蓋 CLI、單設／未知模式在 config 建目錄前拒絕、legacy readonly 與空私人 store。新增 `assert_personal_store_path` 僅供 caller 每次 I/O 前核 canonical／containment／links／regular-file／hardlink，不授正式 migration 或抵擋無 custody 的惡意並行換路徑。config／selection 的 targeted mypy 在中央 service/repository 四檔聯集通過；後續 B09 必須採此獨立依賴接線，不能自造另一 mode 規則。
