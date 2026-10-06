# B10 私人覆盤與來源分離（進行中）

中央排他 ownership：`app_module/decision_quality_service.py`、`app_module/decision_quality_repository.py`、新 selector／backup adapter 與具名 B10 tests；`data_module/config.py`、`ui_qt/main.py` 及文件仍由中央單一 owner 整合。B09 持有 Portfolio service/store，中央不共編。

實作前未來函數自查：本包只消費既有保存交易／notes／Evidence／Gap／Decay，保留原事件日與身份，不追加行情、不重新打分或改財務公式；未知可得性不授 PIT／ML／交易資格。市場衍生來源必須 readonly，私人覆盤 writer 不可經空庫回落到市場 DB。

## 回滾清單

| 檔案 | 變更 | 回復方式 | 風險 |
|---|---|---|---|
| DecisionQuality service/repository | 明示 source reader／private writer 與既有 notes selector | 僅在確認無其他 dirty 後 revert 本包 local commit | 已保存私人覆盤留存，不搬回市場庫 |
| 新 selection／backup adapter／tests | opt-in 路由及隔離驗證 | revert 本包 local commit，保留所有合成與正式資料 | 後續 B09/main 依賴需同步回復 |
| config/main／Manual／Snapshot | 明示選擇與操作 | 中央具名 commit 回復，不 revert 他人 lane | 禁止以全域 OUTPUT_ROOT 或 db_file 改值替代分流 |

目前尚未宣稱完成 caller 接線、備份／還原或正式資料啟用；完成後補精確命令與接受範圍。

## 共用選擇配置的有限驗證

中央新增 `personal_store_selection.resolve_personal_store_selection(config)` 與 `TWStockConfig.personal_store_root/personal_store_mode`，以成對 opt-in 選擇私人 store；watchlist／notes 選擇維持獨立，未配置保持 legacy 相容。CLI 與環境設定一致，不改 OUTPUT_ROOT／市場 db_file，不 mkdir 私人 store。路由 identity 必須由 caller 已解析的帳戶／store 身份提供。

`pytest tests/test_personal_store_selection.py tests/test_personal_store_routes.py -q -o addopts= -p no:cacheprovider`：26 passed／0.64s；涵蓋 CLI、單設／未知模式在 config 建目錄前拒絕、legacy readonly 與空私人 store。新增 `assert_personal_store_path` 僅供 caller 每次 I/O 前核 canonical／containment／links／regular-file／hardlink，不授正式 migration 或抵擋無 custody 的惡意並行換路徑。config／selection 的 targeted mypy 在中央 service/repository 四檔聯集通過；後續 B09 必須採此獨立依賴接線，不能自造另一 mode 規則。
