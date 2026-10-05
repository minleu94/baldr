# 2026-10-05 有界語意審查與體驗接手

本輪完成既定 60 個 production／operational checkpoint 變更與 caller／callee 的有界語意核對，72 個測試標籤對應實際 imports／test nodes／assert／raises／既有 gate，2 份文件核對。沒有把 tests PASS 當語意審查，也沒有把 60 個標籤當 60 個缺陷。原 47 個已關閉與前批 10 個完成項未重做。基線 branch `dev`／HEAD `2ca83c300d836e63054b71d48958dab5d1afea52`。

## 已修正

- semantic 去重將 sample ID 改為 semantic ID，但 fit 仍只接受 capture ID，所有經該入口成熟樣本會在來源綁定遭拒。現從逐份重驗的 capture＋outcome 重算相同 ID，按完整 hash 去重，再 exact row set／feature／date／return／cost 比對；舊 ID 路徑保留，mixed／變造 ID 拒絕。
- 極小正價差報酬取整 0bp，outcome label 卻為 1，與既有 training sample 契約衝突。現沿用 Decimal／ROUND_HALF_EVEN 後整數 bp >0；原價與原證據保留。
- wrapper 把 `fitted_research_only` 誤報 pending，現保留研究完成狀態，不授予正式資格或 promotion。
- `PROJECT_NAVIGATION.md` 的 cutoff 誤寫台北 04:30，修為 America/Los_Angeles 04:30（DST）。

未取消保護、未造 available_at／歷史 PIT／機率／自然成功。原失敗證據與未知根檔未讀改，沒有 producer／training／UI 操作／cleanup／新 agent。本輪後半依父層指定有界單代理覆核，不重新分派 Luna。

## 實際驗證與界線

受控四模組 pytest：95 passed、1 Windows symlink skip、1 actual fit test 依禁訓範圍 deselected；三個修改模組 mypy 通過；七個修改 Python 檔 py_compile 通過。首次回歸暴露 calendar fixture 時間比固定 observation 晚，改 fixture captured_at 不晚於前一日／現在，正式 guard 保留。pytest cache 權限警告以 no:cacheprovider 消除，未更改 ACL。完整 checkpoint gate（Workbench 85P、validator 25P／4skip、full mypy、1892P／12skip regression 等）仍只是修正前精確 bytes 基線；未重跑／偷沿用舊 pin。UI 未改，所以本輪沒有 UI 強制檢查或 Native 新驗收。

逐檔 hash、完整 checkpoint diff pin、人工核對要點及既有證據保留於 `output/qa/semantic_review_batch1_20261005/receipt.json`。72 個 test label 的 imports／nodes 與 gate 對應不是全測試內容的人工作品審查。

## 四用途與未完成工程

盤勢／選股／持倉健康／個股研究的來源與資格接線有界核對完成，不等於全產品 ready。2382 使用者真實截圖已確認：系統 condition missing／critical 混成股票／持倉風險；五問首屏長文與歷史／當期混雜；價格／均線被埋、精度冗長；ML −120bp 缺 horizon／benchmark／成本／資格語境，hash 先於用途；待驗結果滿表破折號。這是既有功能體驗缺口，下一批需修，不能改成自然證據不足結案。

下一最小批次為既有 presentation／stock research service／view、position health 與 Manual 的 UX02／06／14／15：首屏當期判讀、最多三項依據、反向／股票風險、資料／模型限制、待驗條件；診斷詳情可展開，來源身份不變。共享檔單一 writer，不啟動新圖表／策略／大型重構。

Native 已有 1000×835 outer／125% 同版部分四用途／六分頁證據。1477 真正 cancel terminal→retry→完成→正常 Save→新程序重開及 wrong date／run／hash 仍待驗；先前 probe 在取消中誤判完成，屬 harness 問題，不是產品已證實故障。1000×800 outer／125% 尚差約 35px 可見性，不冒用 835 PASS。使用者當前 UI 不操作。

05:54:14 UTC 容量：C natural／D research 通過，D formal raw（35GiB persist＋40GiB temp＋200GiB reserve）差 9,832,595,456 bytes，仍 FAIL。1251 cleanup 僅候選清單；20 路徑 QA 引用、153 tracked 引用，handles／相對引用未排除。後續逐個 owner／writer／引用／保全／可還原備份確認後受控清理，才重驗容量；本輪沒重掃或刪除。

真正自然等待僅為 forward／exit／H5 成熟、歷史 availability／PIT 與模型資格依原來源契約累積，不能等同 UI、接線、容量工程缺口。WP5／已取消個人提醒不恢復。

## 既有計畫原位整合

`output/plans/baldr_product_experience_plan_20261004.md` 已保存第 3 版，原第 2 版完整備份 hash `cd4484e09c9453c7b6c2b2d8f0201ce80e8209b2a89735202cdd7748655326ae`。保留效能→共用每日特徵／快照→多條件選股與研究→自然累積→ML 比較主線及 24 工作包，新增分類、2382 問題／最小修復／驗收與 Native／容量／cleanup 依賴；大型新增能力未開始。計畫與 QA output 受 Git 排除，未 force add。

下一體驗修復不需新的投資產品選擇；需協調 isolated Native 時段與 1000×800 修復範圍。新增圖表與 ML target 仍按原 UX07／UX21–22 決策，不阻礙既有 UI 修復。本批交父層覆核後停止，不自動開下一批。

## 60 個檔案核對範圍

| 檔案 | 本批處置 |
|---|---|
| `analysis_module/pattern_analysis/pattern_analyzer.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/evidence_pipeline_runner.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/forward_outcome_context.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/forward_performance_service.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/historical_evidence_replay.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/market_breadth_service.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/market_session_cadence.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/portfolio_alert_service.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/portfolio_condition_monitor.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/portfolio_service.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/recommendation/current_market_status_preflight.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/recommendation/execute.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/recommendation/input_preparation.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/recommendation_service.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/research_session/session_dtos.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/research_session/session_events.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/research_session/session_reducer.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/research_session/session_store.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/scheduled_evidence_status_service.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/scheduled_forward_outcome_service.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/stock_research_report_dtos.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/stock_research_report_service.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/update_service_status_support.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/user_declared_holding_research.py` | checkpoint 變更與相關契約有界審查 |
| `app_module/watchlist_analysis_service.py` | checkpoint 變更與相關契約有界審查 |
| `data_module/institutional_revision_read_model.py` | checkpoint 變更與相關契約有界審查 |
| `data_module/phase3c_backfill_runner.py` | checkpoint 變更與相關契約有界審查 |
| `data_module/portfolio_ml_direct_numeric_store.py` | checkpoint 變更與相關契約有界審查 |
| `data_module/portfolio_ml_raw_to_ooc_pipeline.py` | checkpoint 變更與相關契約有界審查 |
| `decision_module/market_regime_detector.py` | checkpoint 變更與相關契約有界審查 |
| `decision_module/recommendation/evaluate.py` | checkpoint 變更與相關契約有界審查 |
| `ml_module/current_observed_natural_research_fit.py` | 有界審查；確定缺陷已修正 |
| `ml_module/recommendation_calibration_evidence.py` | checkpoint 變更與相關契約有界審查 |
| `ml_module/recommendation_natural_outcome_service.py` | 有界審查；確定缺陷已修正 |
| `scripts/calculate_forward_outcomes.py` | checkpoint 變更與相關契約有界審查 |
| `scripts/capture_evidence_events.py` | checkpoint 變更與相關契約有界審查 |
| `scripts/continue_ml_direct_ooc_after_store.py` | checkpoint 變更與相關契約有界審查 |
| `scripts/continue_ml_direct_v3_refresh_chain.py` | checkpoint 變更與相關契約有界審查 |
| `scripts/maintain_ml_direct_v3_refresh_chain.py` | checkpoint 變更與相關契約有界審查 |
| `scripts/run_evidence_pipeline.py` | checkpoint 變更與相關契約有界審查 |
| `scripts/scheduled/data_freshness_probe.py` | checkpoint 變更與相關契約有界審查 |
| `scripts/scheduled/register_banktaiwan_recommendation_learning_task.cmd` | checkpoint 變更與相關契約有界審查 |
| `scripts/scheduled/run_banktaiwan_recommendation_learning_daily.cmd` | checkpoint 變更與相關契約有界審查 |
| `scripts/scheduled/run_banktaiwan_recommendation_learning_daily.py` | checkpoint 變更與相關契約有界審查 |
| `scripts/scheduled/run_daily_recommendation_learning.py` | 有界審查；確定缺陷已修正 |
| `scripts/scheduled/run_recommendation_calibration_learning.cmd` | checkpoint 變更與相關契約有界審查 |
| `scripts/scheduled/run_recommendation_snapshot.cmd` | checkpoint 變更與相關契約有界審查 |
| `scripts/scheduled/run_scheduled_decision_evidence_capture.py` | checkpoint 變更與相關契約有界審查 |
| `scripts/scheduled/run_scheduled_forward_outcomes.py` | checkpoint 變更與相關契約有界審查 |
| `scripts/scheduled/run_scheduled_recommendation_snapshot.py` | checkpoint 變更與相關契約有界審查 |
| `scripts/smoke_evidence_pipeline.py` | checkpoint 變更與相關契約有界審查 |
| `ui_qt/main.py` | checkpoint 變更與相關契約有界審查 |
| `ui_qt/views/decision_desk_view.py` | checkpoint 變更與相關契約有界審查 |
| `ui_qt/views/portfolio_view.py` | checkpoint 變更與相關契約有界審查 |
| `ui_qt/views/recommendation_view.py` | checkpoint 變更與相關契約有界審查 |
| `ui_qt/views/smart_money/smart_money_flow_view.py` | checkpoint 變更與相關契約有界審查 |
| `ui_qt/views/stock_research_report_view.py` | checkpoint 變更與相關契約有界審查 |
| `ui_qt/views/update_view.py` | checkpoint 變更與相關契約有界審查 |
| `ui_qt/views/watchlist_view.py` | checkpoint 變更與相關契約有界審查 |
| `ui_qt/widgets/user_declared_holding_research_widget.py` | checkpoint 變更與相關契約有界審查 |
