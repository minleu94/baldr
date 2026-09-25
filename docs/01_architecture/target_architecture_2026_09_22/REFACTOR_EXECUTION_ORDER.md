# 重構執行順序

> 本文件將 [實作 DAG](REFACTOR_IMPLEMENTATION_DAG.md) 排成低衝突 waves。Wave 內「可平行」只代表檔案 owner 與依賴允許；dispatcher 仍須確認當時 worktree、前一 wave evidence 與實際 diff。不要為追求並行讓兩個 agent 同時改中央檔案。

## 執行規則

1. 每個 task 使用獨立 branch/worktree 或嚴格串行；開始前記錄 HEAD、dirty files、依賴task的commit/evidence。
2. task 只修改 `ALLOWED SCOPE`。發現需要碰另一 active task 的 high-risk file，停止並由 program manager重排。
3. 每個 wave 合併後執行該 wave checkpoint；下一 wave 不在紅色 checkpoint 上開始。
4. `recommendation_service.py`、`recommendation_repository.py`、`recommendation_save_coordinator.py`、`recommendation_view.py`、`update_service.py`、Direct ML stores 均視為 exclusive-owner files。
5. temporary component 必須先有建立與刪除task。沒有 deletion owner 不得合併。

## Wave 0 — 程式庫基線

| Task | 執行方式 | 理由／Gate |
|---|---|---|
| R001 | 單獨 | 所有後續task共同使用caller、artifact、dirty-state與TMP清冊。 |

Checkpoint：清冊涵蓋 direct/dynamic/string/serialized caller；沒有 production edits。

## Wave 1 — Characterization 與獨立 leaf contract（可控平行）

| Task | 可否平行 | 專屬輸出 |
|---|---|---|
| R002 | 可 | 新 recommendation semantics characterization 檔 |
| R003 | 可 | 新 execution-state characterization 檔 |
| R004 | 可 | 新 persistence characterization 檔 |
| R005 | 可 | 新 replay characterization 檔 |
| R006 | 可 | ML baseline 文件＋新小型測試 |
| R007 | 可 | 新 data leaf contracts 與 isolated tests |

限制：各 task 建立自己的新檔，不同時編輯既有大型 integration test。R007 只新增 leaf contracts，不接 production。發現缺 fixture 時由單一 task owner 抽共用 fixture，再重排依賴。

Checkpoint：所有 characterization 在原實作上通過或清楚記錄「預期現況 gap」；不可把 gap 先修掉。

## Wave 2 — Canonical recommendation contracts

| Task | 執行方式 | 依賴／衝突 |
|---|---|---|
| R008 | 單獨 | R002／R003／R007 穩定後，新增 decision/app contracts；不接 production consumer。若 parent package eager import 阻斷 INV-03，依 R008 受控範圍獨占窄 lazy-export 修正。 |

Checkpoint：contracts 深凍結、terminal state 組合與 typed ownership 通過；沒有 codec、writer 或 consumer。

## Wave 3 — Codec 與 ML boundary contract（可控平行）

| Task | 可否平行 | 依賴／衝突 |
|---|---|---|
| R009 | 可 | 擁有 codec 與 DTO 委派 seam；不碰 ML adapter。 |
| R010 | 可 | 只建立 ML contract 與空 adapter boundary；不碰 codec 或 source。 |

Checkpoint：codec 全欄位 roundtrip、ML contract 無 app import；沒有新 writer 或 consumer。

## Wave 4 — 中央 execution（嚴格串行）

| Task | 執行方式 | Exclusive files |
|---|---|---|
| R011 | 單獨 | `recommendation_service.py`、new execute、application ports |

Checkpoint：舊 list 入口與新 execution parity；禁止建立 writer 或開始 consumer migration。

## Wave 5 — Persistence（嚴格串行）

| Task | 執行方式 | Exclusive files |
|---|---|---|
| R012 | R011 合併且 checkpoint 綠後單獨執行 | repository/save coordinator、新 save/query/store |

Checkpoint：create-only、orphan recovery、legacy readback；禁止在 writer contract 不穩定時開始 consumer migration。

## Wave 6 — Consumer cutover 第一段（有限平行）

| Task | 可否平行 | 專屬owner／注意事項 |
|---|---|---|
| R013 | 可 | Qt recommendation files；不碰core service/save implementation。 |
| R014 | 可 | scheduled及QA scripts。 |
| R016 | 可 | saved-result readers/evidence/advice files。 |
| R017 | 可 | replay/provider/portfolio DTO files。 |

Checkpoint：Qt、scheduled、saved-result 與 replay consumer 已接 execution/query；各 task focused suite 通過。TMP-REC-03 尚未移除。

## Wave 7 — 最後保存 caller、獨立邊界與 ML experiment

| Task | 可否平行 | 專屬owner |
|---|---|---|
| R015 | 可 | personalization script/adapter；等 R013／R014 完成後關閉 TMP-REC-03。 |
| R021 | 可 | StockScreener/data reader/composition。 |
| R023 | 可 | fundamental/monthly revenue vertical。 |
| R025 | 可 | strategy contracts/registry/backtest callers；若需改backtest UI，避開R013未合併diff。 |
| R027 | 可 | 隔離experiment＋QA報告；production read-only。 |

Checkpoint：所有保存 caller 已切換且 TMP-REC-03 關閉；各 domain boundary 有原行為 parity；R027 得到 PASS/FAIL/INCONCLUSIVE。沒有 PASS 就不排 R028。

## Wave 8 — Regime state 與 save-time cleanup（單獨）

| Task | 執行方式 | 依賴／衝突 |
|---|---|---|
| R022 | 單獨 | R015 關閉 TMP-REC-03 後才可碰 save-time caller cleanup；擁有 regime detector/service/state 與該 cleanup seam。 |

Checkpoint：多日／same-day／cooldown parity；execution-time regime 保存後不再 re-detect；state history 未清空或改格式。

## Wave 9 — 準備抽離與條件分支

| Task | 可否平行 | 依賴／衝突 |
|---|---|---|
| R018 | 單獨擁有推薦中央檔 | consumer cutover完成後抽input preparation。 |
| R024 | 可與R018平行 | 依賴R023；只碰statement/valuation/factor邊界。 |
| R028 | 只在R027 PASS；可與R018/R024平行 | 擁有update/technical publication files。 |

若R027非PASS：建立 `AB-ML-01` 決策記錄，R028不啟動。這不是「略過失敗測試」。

Checkpoint：input providers parity、factor reverse edges收斂；條件ML分支狀態可審核。

## Wave 10 — 單一 evaluator（嚴格串行）

| Task | 執行方式 | Exclusive files |
|---|---|---|
| R019 | 單獨 | `recommendation_service.py`、new decision recommendation modules。 |

Checkpoint：同 mode 對原 oracle exact parity；domain 無 I/O；以 R019 evaluator-core accepted gate 關閉 TMP-REC-01 的 narrow legacy-state/matrix→canonical-rule bridge。保留 app private source orchestration 與 clock/error/progress capture；ML availability/projection receipt capture 由 TMP-ML-01／R026 列管。若差異未分類，停止。

## Wave 11 — Replay 與 ML boundary（可控平行）

| Task | 可否平行 | 衝突控制 |
|---|---|---|
| R020 | 可 | replay/provider/policy files；不改execute/ml adapter。 |
| R026 | 可 | execute/ml adapter/calibration seam；不改replay。若兩者都要改同一composition檔，先R020後R026。 |

Checkpoint：只有一個rule evaluator；PreparedMLInput與receipt/source race驗證通過；TMP-REC-04及TMP-ML-01可退休。

## Wave 12 — Legacy retirement

| Task | 執行方式 | Gate |
|---|---|---|
| R029 | 單獨 | 所有known consumer已遷移、repo search完成、永久decoder/aliases已分帳。 |

Checkpoint：canonical rule result 不從 latest/cross-invocation last_* 重建；無雙engine／雙registry／逐欄save mapping；必要 execution telemetry capture 明列 owner/TMP，不視為 domain hidden input。`TMP-ML-02`可保持open，但必須寫明原因與owner。

## Wave 13 — Enforce 與 extensibility

| Task | 執行方式 | Gate |
|---|---|---|
| R030 | 單獨 | guards先對已知bad fixture失敗，再對repo通過或列具名baseline。 |

Checkpoint：confidence、新strategy、新technical feature三項synthetic acceptance均符合FINAL變更局部性。

## Wave 14 — Final relevant regression與交接

| Task | 執行方式 | Gate |
|---|---|---|
| R031 | 單獨 | Validation Matrix全部checkpoint、文件狀態與risk/TMP closure。 |

完成條件：工程證據可重跑；仍需外部產品／formal／natural evidence的項目保持未核准；不因文件或測試通過改變產品權限。

## 高風險檔案 owner 表

| File／component | 依序 owner tasks | 禁止平行 |
|---|---|---|
| `app_module/recommendation_service.py` | R011 → R018 → R019 → R026 → R029 | 上述task互相不得平行 |
| `app_module/recommendation_repository.py` | R012 → R029 | R004只加新測試，不改它 |
| `app_module/recommendation_save_coordinator.py` | R012 → R015 → R029 | R013不得順手修改 |
| `ui_qt/views/recommendation_view.py` | R013 | 其他task只透過contract／test影響 |
| replay/provider files | R017 → R020 → R029 | 不與同檔task平行 |
| strategy files | R025 → R029 | R030只加guard/fixture |
| regime files | R022 | 其他task不得順手修regime |
| factor/data verticals | R023 → R024 | R019只消費完成的domain契約 |
| `app_module/update_service.py` | R028（條件） | R027只能唯讀／實驗副本 |
| Direct/OOC ML source | R006/R027唯讀；任何寫入需另有explicit task | R028不得為搬移直接改15條凍結檔 |
