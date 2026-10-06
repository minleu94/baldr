# UX23 registry readonly 整合驗收（2026-10-06）

本機採納 lane d9efbc6d，cherry-pick 62c82e85；接到既有 shadow acceptance consumer 與 CLI。只讀明示一致 snapshot 的 metadata／lifecycle events，不讀 artifact、不載入模型、不採納／回滾、不升級資格。

## 操作及判讀

既有 `scripts/run_rule_research_shadow_acceptance.py` 研究輸入可加 `--registry-snapshot C:/absolute/consistent-registry.db`，與 `--lifecycle-export` 互斥。既有 receipt、case、policy、bundle 仍須明示。舊 export 路徑標示 `exported_declaration`，不宣稱連線核對；snapshot 路徑標示 `registry_snapshot_read`，成功為 `metadata_verified`，附 source SHA256 及未驗欄位。training_audit／target_contract 仍源自 caller，不能稱 lineage custody。全部資格 false、alpha／qualified_count 0、selection unknown。

既有 initializer 與 connection 沒有設定 journal_mode；synthetic initializer 實測 DELETE。此結果不代表現場 DB 模式。WAL header 或任何 wal/shm/journal 殘件拒絕，需另外受控的一致 snapshot。本包不對真 DB checkpoint、切 journal mode 或清 sidecar。一般 SQLite 短暫共享讀鎖可存在，沒有模型／registry 寫入。

保存時 DB hash 與 readback 診斷進入 immutable identity，重驗 source 改變拒絕發布。取消後不發成功收據，可明示重試；新程序 exact identity 重讀保存結果，不重新連 registry、不選 latest。舊 receipt 無新增診斷仍相容。

## 驗證與限制

Raw：`output/qa/ux23_registry_integration_20261006/`；preflight.json、plan_before.bin、final.xml、final.txt、cow_baseline.xml／txt。正式 final 結果見收據；完整 mypy 822 source files 通過，targeted reader／CLI 2 檔通過，5 Python compile／diff check 通過。覆蓋正常 metadata、缺件、WAL、sidecar、exclusive lock、錯 source、schema/version、禁寫 authorizer、terminal lifecycle、future observed_at、取消重試、來源改變、新程序 exact 重讀。首次 `.t` basetemp 不是 capture writer 允許的隔離保存根，改回 OS Temp；新增測試缺 Path import 已修正。

無 UI 修改，無 Native／Task／正式 DB／migration／push。僅提供既有 CLI consumer 接線，不聲稱 UX23 已完成正式 shadow 啟用或 custody。rollback 僅 revert 本包 commit，不刪原資料或 worktree。

## 上包失敗追蹤（不修改其他 owner）

- `tests/test_ui_qt_v5_research_views.py::test_price_chart_hover_exposes_point_date_ohlc_volume_and_range`：舊 assertion 日期標籤與現有「資料日」不同；96ebcb33 原 UI module 注入已重現，值本身未證實錯誤。
- `tests/test_ui_qt_v5_research_views.py::test_report_summary_exposes_evidence_change_risk_sufficiency_and_next_step`：缺 fundamental fixture 顯示「需核對資料」，assertion 期待「值得看」；同一原 UI 基線已重現。不能以失敗數推論真資料結果錯誤，需另包判斷預期。
- `tests/test_personal_data_paths.py::test_cow_synthetic_pipeline_with_new_internal_root[json]`、`[1]`、`[2]`：上一深 fixture 189 passed／3 failed，短根 192 passed。本包在 `.tmp_ux23_registry_readonly` 基線（base 96ebcb33 + readonly 新增三檔，未改 COW）實跑同三 ID，3 failed；本次更深根在 staging 更早受阻，並非宣稱相同 callsite。兩模組自 96ebcb33 到 HEAD git diff 空。ordinary Windows path 長度限制可能影響真實深目錄；目前沒有真 personal 驗收，也不稱「只影響測試」。raw cow_baseline.xml／txt 留存。

追加驗證：修正新增測試對 save API 回傳形狀的誤認（save 只回 receipt，capture 需 exact read）；新 11 案例已全部通過 integration_final.xml，含新程序 CLI exact 重讀。量化精度／未來函數 guard 通過。最後完整接受批次為 accepted.xml／accepted.txt。

最終接受批次：85 passed／0 failed／0 skipped（accepted.xml）。包含 readonly lane 47 案、既有 shadow 27 案及新增整合 11 案；完整 mypy 822、targeted mypy 2、5 compile、量化 guard／diff check 成功。
