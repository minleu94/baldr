# R005 SOL 審查

## 判定

`tests/test_recommendation_replay_characterization.py` 的 6 個新案例及既有 replay／portfolio／timeline suites 在 SOL 重跑時共 59 passed。實作沒有修改 production。但新 oracle 只覆蓋部分 provider 行為，尚不足以在 R017/R020 切換後判定同 mode replay 是否保持原樣。

## 必須修正的項目

1. `R005_IMPLEMENTATION_REPORT.md` 的 mode difference table 把 `RecommendationDataFrameProvider` 稱為 interactive mode。該類是 portfolio/replay 使用的 legacy DataFrame evaluator；一般 interactive `RecommendationService` 有不同入口與業務語意。請依 source 更正 mode owner，明示哪些差異來自 replay wrapper、哪些來自 DataFrame provider；不可把兩者共同視為 interactive/replay 對照 oracle。
2. `tests/test_recommendation_replay_characterization.py:23` 的 future-append 案例使用每次都回固定 `FinalScore=85.0` 的 mock，且只查一個 stock code/score；不能證明完整舊 snapshot 在追加未來 row 後保持相同。請比較同 mode 的完整、具名 snapshot 欄位、ordered recommendations、config/profile/as-of、diagnostics 與獨立 expected values；不要用待遷移 helper 生成 golden。
3. `:68–134` 尚未涵蓋 numeric `YYYYMMDD` parsing、default/configurable lookback 80、max stocks 200、volume fast filter、score fallback、missing score/order、universe policy 與 per-stock exception 對 diagnostics/manifest 的影響。請以小型 deterministic fixture 針對每個政策做正反例；不需正式資料。
4. `:134` 只檢查 `unavailable_rows_excluded:1` 字串，沒有斷言被拒 row 不進入 recommendation，或 missing `available_date` 與 future availability 的不同結果。請精確 assert cutoff 後 provider 實際收到哪些 row，以及 snapshot 的 output/diagnostics。
5. 尚無 portfolio replay/date/factor manifest 的 task-owned oracle、mode-specific fixed results、stored annotation 不被 current model 重算的可觀察證據。原 packet 允許只查相關路徑，不要求改 broker/cost 或 ML；若某項目前無可控 fixture，須具名列 gap 與 downstream owner，不可宣稱全數兼容。
6. `R005_IMPLEMENTATION_REPORT.md` 只列新檔 6 passed；須補起始／結束 HEAD 與 dirty baseline、fixture grain、正確 mode difference table、golden 來源、已固定與未知差異、R017/R020 handoff、既有 `V-REPLAY` focused suites 的實際命令/結果、`py_compile` 與 `git diff --check`。目前 `UNRESOLVED RISKS: 無` 不成立。

允許變更限 R005 專用新測試與 R005 實作報告。不可更動 production provider/evaluator、portfolio accounting、正式 manifest 或其他 R-task 檔案。完成後重跑 V-REPLAY，交 SOL 查實際 diff。Wave 2 仍 blocked。

REVIEW_STATUS: CHANGES_REQUIRED
