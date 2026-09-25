# Wave 6 派工與同檔 owner 裁決

SOL 最終裁決（2026-09-23）：C1 為 `C1 ENGINEERING GATE PASS`；R013、R014、R016、R017 均為 `ACCEPTED_SCOPE`（synthetic／engineering）；Wave 7 為 `RELEASED_FOR_IMPLEMENTATION`。各切片的 reviewer 結論、驗證數字與限制見 [Wave 6 最終 gate 報告](WAVE6_FINAL_GATE_REPORT.md)；C1 最終狀態見 [C1_CHECKPOINT.md](C1_CHECKPOINT.md)，各 owner 的原始驗證見個別 implementation report。R013／R014／R016／R017 的 scoped acceptance 不等於完整整合 suite 全面通過：42-file／656-test combined run 未完成，另有一項舊 Qt ACK fixture failure 屬 R015 deferred。Wave 7 釋出僅允許後續工程實作，不代表 formal data acceptance、ML promotion 或 production deployment。C1 原 PASS 曾因[契約缺口](C1_CONTRACT_COMPLETENESS_FINDING.md)重開並撤回，修補後才重新裁決通過。保持原有 owner 與 task dependencies 不變。

| Task | 此 wave 的專屬 owner | 不得碰觸 |
|---|---|---|
| R014 | `scripts/scheduled/run_scheduled_recommendation_snapshot.py`、直接推薦 QA CLI、所需測試；新 `app_module/recommendation/composition.py` 由 R014 獨占，提供 app 層對既有 `ResultArtifactStore` → `RecommendationExecutionPersistence` → `RecommendationSaveService`／`RecommendationExecutionQueries` 的窄組合入口。路徑與舊 `RecommendationRepository` 同為 `config.resolve_output_path('recommendation/runs')`，artifact 在其 `execution_artifacts` 子目錄，DB 仍是 `recommendation_runs.db`。 | Qt view/coordinator、saved-result business consumers、replay/provider、R012 store/save/query 實作、calendar policy/scheduler registration。 |
| R016 | Advice、Decision Desk、watchlist、evidence importer 與 `HistoricalEvidenceReplayService` 的讀取 consumer／測試；可消費既有 `RecommendationExecutionQueries` API。 | `RecommendationReplayService`、DataFrame provider、portfolio DTO、R014 composition、R012 writer/store/codec、business policy。 |
| R017 | `RecommendationDataFrameProvider`、`RecommendationReplayService`、`RecommendationSnapshotDTO` 的 in-memory canonical bridge／測試。 | `HistoricalEvidenceReplayService`、evidence importer、portfolio backtest/evaluator、R012 writer/store、正式 child artifacts。 |
| R013 | Qt recommendation coordinator/view/presenter/model 與其測試／必要 Manual；在 R014 組合入口固定後消費已封存 execution 及同一 save command。 | R014 composition、核心 engine、R012 writer/store、其他 tab、R016/R017 reader/replay。 |

R014 的組合入口只是既定 INV-16 的資源接線，不得建立新的 repository framework、保存 schema、policy 或第二套 writer。若現有組合 `app_module/decision_service_composition.py` 需要增欄或改簽名，先停止並交 SOL 裁決，不讓 R013/R014 平行修改該中央檔。R016 需要 query 接線而現有 API 不足時也先報，不自行修改 R014 owner。R013 與 R014 都需保留原授權保存時點；R015 才移除最後的 TMP-REC-03 adapter。

`HistoricalEvidenceReplayService` 歸 R016；`RecommendationReplayService` 歸 R017。兩種 replay 的歷史 cutoff、結果 bytes 與 mode 差異不得互相併入。R017 建立的 TMP-REC-04 仍由 R020 退役。Wave 6 四項現均完成 scoped engineering acceptance，SOL 已釋出 Wave 7 實作；這項釋出仍受本文件既有 owner、dependencies 與正式資料／ML／deployment 邊界約束。R015 的舊保存 adapter／personalization ACK caller 仍是獨立 deferred work。
