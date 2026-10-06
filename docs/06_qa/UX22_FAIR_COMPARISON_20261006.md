# UX22 同源公平比較工程（2026-10-06）

承接已接受 `ae90ba2c70b0221efe868193319403d874e0dda4` label readiness。唯一 Luna Max 實作薄 consumer／focused cases；root review、既有 evaluator 小幅抽取、CLI、整合證據與文件。沒有 UI 變更、真 fit／模型發布或新訓練平台。

## 實作與可評估邊界

沿 exact parent／outcome sealed reader → 原 label／split policy → CORE20 HistoricalFeatureBuilder → MLModelRecord／整數 MLShadowPredictionRecord → 同序共同 sample IDs → 原 integer historical evaluator。baseline／candidate 共用同一母體、日期、方法、H5／10／20 目標、split、label版本、成本及benchmark語義；不同來源／target contract不能混算。未標明policy或無合格candidate列缺件，沒有空結果通過。

新return-only入口重用原MAE／precision／NDCG／bucket monotonicity公式；原return+downside入口的值與輸出key順序保持。只有明示整數downside門檻才產生分類目標（endpoint value≤門檻），不把未知downside填0。top_k對所選evaluation window的共同樣本，不是交易selected；不足不縮k。共同分母與全母體／方法行／selected target／流失逐列分開，matched／notmatched都能做研究對照。

## 未來資料與 provenance 自查

特徵依既有ShadowInferenceRequest契約採T-1（feature_as_of／available_date都早於decision_date）；預測available_date≤decision_date，模型training audit的label cutoff早於evaluation開始。不對評估資料fit／標準化。兩角色逐樣本feature snapshot與原source_versions_hash必須一致。comparison binding是**事後標籤對齊封套**，含outcome及評分policy；原決策預測不可能預知它，故不寫回既有prediction DTO的來源hash。benchmark target只綁版本／來源／basis聲明，不帶事後endpoint row hash；target_contract及training audit是匯出端聲明，沒有替模型補歷史資格或驗真訓練lineage。

舊sealed current-observed來源／calendar／availability unknown限制仍在，training／historical PIT／formal／natural authority／execution皆false，selection unknown。合成完整feature與受控predict_shadow_bp只能驗介面，不證明真模型改善或自然forward成熟。endpoint-only無MFE／MAE／期間停牌評估。

原已封存label fixture是18 labels／12數值，但18筆availability全部unknown、0 temporal training candidates。合成日期／availability測試只驗條件分支，不可替這些sealed樣本授予訓練或PIT資格；本次共同評分仍只作事後研究。

本包模型created_at、training audit、feature／prediction可得日期及source hash都是明示fixture聲明；受控predictor實際在本次驗證時執行，並非原決策日已封存的歷史forecast。匯出DTO的日期滿足介面條件，不等於已驗真的availability／custody或訓練lineage。

## 操作與診斷

`scripts/run_rule_research_fair_comparison.py`預設繁中白話摘要，`--json`輸出有界來源、契約、逐樣本流失、共同分母、指標／差異與身份。政策、model／feature／prediction bundle都需明示，不找latest、不載pickle、不調用registry writer。政策64KiB／bundle及report2MiB／label4096／receipts32；重複JSON key、超限、浮點／bool、未知pins及不相容不截斷。操作、參數、判讀與排錯已同步[Manual](../07_guides/APPLICATION_MANUAL.md)。

## 驗證紀錄

最終89個不同案例通過（原ML回歸21＋label／split回歸40＋本包28：核心20、CLI6、scoped boundary2），0失敗／0略過。完整mypy817 source files、CLI／evaluator／guard targeted mypy、8檔py_compile、量化精度／未來函數及diff check通過。程式hash在最終檢查前後一致；本包無UI變更，沒有重跑Native／效能／已接受工作臺gate。

actual隔離SQLite→新parent capture→benchmark／成本封存→18 labels→合成CORE20→既有ControlledShadowModel及CLIControlledShadowModel共6次predict_shadow_bp→共同計分／白話CLI／新程序JSON重讀完成。原capture保留；1001 MA20改動只在本測試Temp DB、且另捕新parent，沒有改sealed member states。完整代表母體3／included2、兩方法6行；selected MA20/H5有matched1／notmatched1／excluded1，共同樣本2、未進共同1。H5/10/20總18 labels／12值／6缺值，18 availability unknown、0 temporal training candidates。兩fixture都回125bp，MAE都271bp、差異0；這不是效果改善證據。

來源DB與benchmark DB在新程序讀回時暫移開、finally還原；20個capture／receipt／snapshot JSON與兩DB的before/after SHA相同。相同收據／policy／bundle重讀identity為 `sha256:d3e118517cf8623b6ea57e0ed2ad13bfd99ef6966019bbc94ba937f552863d0e`，所有資格旗標false。另用兩份真sealed fixture／不同source DB配對驗 `comparison_logical_source_or_version_mixed`，沒有pool成可比報表。

raw receipts保留於 `output/qa/ux22_fair_comparison_20261006/validation_receipt.json`、`fixture_actual_readback.json`、`different_source_rejected.json`、`boundary_readback.json`，不stage。原計畫前229037 bytes（SHA `fc727705cacd8cbf31f63f235c08b0a2a6edaf95aab9889f516209db90ef673e`）保留，僅追加。其他owner三檔與90d16858相同。

修訂中紀錄也保留：初版摘要缺ML名稱的CLI assertion、14個新模組型態錯誤、第一次跨程序不一致（發生於模組仍修訂時、未能歸因），以及最終第一輪「不計」／「未計算」的單一過度限定assertion。修正後最終重核通過；沒有把未完成版或舊fixture當成最後證據，也未丟棄source資料。

ML boundary在本包前已有八條違例（包含前批label adapter及其他owner），raw baseline保留；本包僅增加fair consumer exact module／symbol read-only allowlist並驗允許／拒絕未審training或registry symbols，不能宣稱全repo boundary通過。既有違例不在本包改動範圍。

### Base既有違例（ae90ba2c，八條）

|路徑|匯入module／symbol|類型|
|---|---|---|
|ml_module/current_observed_feature_snapshot_composer.py|app_module.recommendation.queries:_read_regular_file_no_follow|ml_imports_production_path|
|同上|app_module.saved_recommendation_queries:build_recommendation_execution_queries、execution_result_config|ml_imports_production_path ×2|
|app_module/personalization_read_service.py|ml_module.recommendation_calibration_evidence:verify_natural_maturity_session_proof|production_imports_ml_module|
|app_module/recommendation_calibration_consumer.py|ml_module.recommendation_calibration_training:InvalidCalibrationOutputError|production_imports_ml_module|
|app_module/rule_research_label_readiness.py|ml_module.historical_contracts:HistoricalLabelRow|production_imports_ml_module|
|同上|ml_module.historical_contracts:HistoricalLabelSpec|production_imports_ml_module|
|app_module/stock_research_report_provider_adapters.py|ml_module.current_restated_research_bridge:load_current_restated_outcome_model|production_imports_ml_module|

新allowlist只作用於 `app_module/rule_research_fair_comparison.py`，逐symbol允許 HistoricalFeatureRow、HistoricalFeatureBuilder、CORE_LONG_HISTORY_FEATURE_REGISTRY、MLModelRecord／MLShadowPredictionRecord、ShadowInferenceRequest／ShadowPredictionIdentity／prediction_id_for、evaluate_return_predictions／evaluate_historical_predictions。理由是只驗匯出DTO、causal feature contract與整數共同樣本計分；不允許MLModelRegistry／HistoricalTrainingService或其他未審symbol。不加module wildcard、不改全域production roots，既有八條也不消除；scoped consumer測試與base重現分開記錄，午夜review留待對應owner。

## 真實進度與未完成

本包完成同源feature／label／prediction對齊及共同計分工程子項，UX22／Stage7仍partial；9stage=1done／8partial／0pending、24UX=2done／21partial／1pending。尚缺合格真來源／決策時availability／模型target及training lineage的可信輸入、真baseline／candidate效果證據；未啟用正式Task／personal migration／DB寫入／重訓。原計畫僅追加並保留原bytes；Manual／Snapshot／architecture／navigation／index／coverage／QA routing同步。07:00 UTC前安全停手，不自行擴scope。
