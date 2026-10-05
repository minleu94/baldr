# 2026-10-05 有界語意審查與體驗接手

## 2026-10-05 原排名收藏與個股來源版本化（最新限定收尾）

已完成原排名選股→個股原排名／原 feature→版本化收藏→新程序 pinned 讀回→精確返回原收藏。v2 保存四模式、實際比較窗、原母體／方法／hash／排序／所選股；舊非 rank v1 內容與 bookmark/query/payload 雜湊不變，沒有真實清單遷移。缺件／錯版本／日期／股號／hash／來源修訂顯示原因，可明確另開最新個股研究，保留原證據。完整 Top/Bottom 字串照原 publisher 顯示，3–5 筆週 fallback 明示實際日期與非完整週，不反推 score／勝率。

受影響測試 136 首輪通過＋1 項定向修正後通過（合計 137 個案例）；Workbench 85；更新頁 validator 25 通過／4 略過；mypy 783 檔；18 個 Python 檔語法與 quant guard 通過。 真實既有 D 來源的 2382 四模式，在程序 24368 保存至隔離清單，程序 26516 重開核對來源與返回；兩程序正常退出且 worker=0。17 個 feature/rank 原檔及 DB/WAL/SHM stat、原引擎／母體設定保持不變；未重跑既有真實來源 publisher／learner，未寫正式 DB／registry 或真實收藏。排名來源測試僅用三股小型 fixture DB 與隔離產物。

其他原大盤／強弱 consumer 融合、完整 feature/method dictionary、正式合格母體／排程部署、長期 storage/growth 及其他 lifecycle crash 驗收仍是第一版工程。Backtest 18.62%／20% 未達保留。正式母體權威、official availability／歷史 membership／PIT，以及舊 Top/Bottom 口徑與 numeric score 暴露屬來源／方法版本決策。Native 鍵鼠／縮放／跨頁、完整 App startup 與 3–5 位真人驗收另待桌面時段；不把工程缺件稱為自然成熟。 詳見[本批限定 QA](UX18_RANK_BOOKMARK_SOURCE_VERSIONING_20261005.md)。原計畫 append-only；本地 commit/blob 核驗後交父層，不 push／清理／操控用戶視窗，未知 capture 與還原映射不動。以下較早紀錄只代表其版本當時狀態。


## 2026-10-05 UX13／18共用盤勢最新限定交接

基線 f07f298，具名 cohort Market→同快照名單→pinned個股閉環完成；原排名未提供明示unknown，僅排序原Decimal指標值，不做強弱／投資分數。partial缺件保完整分母與unknown，不假造下鑽列。45受影響tests／9重疊UI重驗、Workbench85、validator25／4skip、mypy777＋變更DailyView單檔、compile7／quant guard通過。真2382／1477／2026-10-05與隔離缺件／revision／schema拒絕恢復Native通過，12code pins與正式source stat穩定，worker0／程序退出；非全App／效能／真人驗收。6張Library IDs與逐項收據見[最新QA章](UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)。

原計畫保留append-only，本地commit/blob核驗後停止，不push／全量producer／正式DBwrite／train／清理。整體UX13／18／19、stage2／3仍partial；原排名發布／其他consumer融合／完整母體與收藏等工程另包。Backtest18.62%<20%未達不改，PIT／自然ML／真人證據不偽造。未知paper檔／還原映射不動。


## 最新接續：UX18 固定研究方法契約（基線 c50cefcd）

兩條既有 MA20／MA60 方法 metadata 綁 cache／manifest／逐股三態結果，錯方法／版本／參數／日期／hash 拒絕，舊 schema 僅明確更新重產；實際驗證與提交見 [QA 方法綁定新章](UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md) 及 Git。公式與用途不改，不授 alpha／勝率；原排名與市場共用 consumer 超出小改列下一包，UX18／19 與 stage2／3 仍 partial。

Backtest18.62%／20%未達、歷史 PIT／自然 ML／真人驗收限制維持，不以外部等待遮蔽工程缺項。原計畫追加保留，未讀／動未知 paper 或還原映射，不 push／清理／訓練／全量回歸；本地提交與 blob 核驗後停止交父層。

## 最新接續：UX04／05 日常研究名單與同源個股（基線695797ec）

本包承接有限UX18／19工程，把研究快照接到Recommendation實際入口與個股pinned讀回：既有兩條close／MA AND／OR、三態why／why-not、來源metadata經session完整保留，返回核對原manifest。repo專用研究區僅明確更新才bounded寫入；不改正式DB／排程，不升研究或離線候選為推薦。真實來源Native QTest與受控缺資料／revision場景分列，數字與提交以[QA新章](UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)及Git為準。

完整UX18／19／stage2／3仍待更多feature／method、全母體／原排名融合、其他consumer、正式排程／長期storage與跨process崩潰；Backtest18.62%／20%與自然PIT／ML限制不改。不重做舊ML、Frozen效能、Native1477或全量回歸，未授清理／security／push；paper與還原映射保留。

## 最新 UX19 有限研究閉環（基線3a975e3）

本包新增隔離 bounded producer→verified repository→實際 StockReport consumer，重用 close／MA20／MA60 與既有有限 DTO，不新增方法或正式 writer。來源缺件停止發布，失效股才重投影，候選核驗後原子切換 latest。限定實跑／測試與來源 pins 見 [UX19 QA 新章](UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)，原計畫只追加結果。

這不是完整 UX18／19 或階段2完成；其他 feature／method／consumer、選股融合、全母體排程與長期 storage 仍待，Backtest18.62%／20%與自然 PIT／ML 限制不改。已完成的語意審查、ML、Native 與效能不重做；paper、正式資料庫與還原映射未動。

## 最新優先：UX18 既有日特徵研究 consumer

50f45ce後依原plan第8.7允許的partial research，完成close／MA20／MA60共用快照到個股read_report／研究理由／首屏的有限垂直切片。穩定identity、4筆有界cache、來源日期與末段有效OHLC必要暖機及三態均有定向證據；不重算指標／排名、不新策略或writer。首屏未知不再自行比較。歷史availability／calendar／PIT仍unknown／false；Backtest18.62%子gate不放寬，整階段依賴不改。完整UX18及UX19工程、UX04／05其他consumer和自然ML用途依賴分列於[原QA收據新章](UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)。原plan append-only，本地commit／blob/status核驗後停止交父層；不重做既有ML／效能／1477，不清理／push或觸碰未知paper檔／還原映射。以下記錄保留其原版本。

## 最新優先：UX16唯讀來源契約與UX02 Native中文

dc14c080之後的有限包新增current-observed source contract／CLI、loader向後相容的時鐘投影與strict SQL。具名cutoff／cohort／來源版本／rowset hash核對可重讀研究資料；不生成特徵、正式snapshot或新方法。Root定向21passed、mypy3files、compile4檔、quant guard通過，9個UI blob同版沿用原UI gate；正式D2檔3日6列穩定，availability未知／cutoff-screened0，PIT與正式資格保持false。

四用途Native中文已清楚無豆腐字：三頁受控fixture，個股明示hash的記錄唯讀DTO（2382／10-05／331.0／ML unavailable），不是此run即時DB／自然模型證據。四輪8個QA PID退出，前3失敗與來源限制保留。詳見[UX16／Native限定收據](UX16_CURRENT_OBSERVED_SOURCE_CONTRACT_20261005.md)。

保留唯一原plan／UX01→UX16/17→UX18/19依賴，stage1 Backtest18.62%／20%門檻未全部通過；下一包為具版本／單位／暖機的共用feature dictionary、增量等價與UX19 manifest／完整性／原子發布／容量前置，由父層裁定放行，不跳新方法。歷史產業／PIT、benchmark與availability未知不冒稱驗證，也不阻擋具名當期研究。沒有重訓／producer／全量回歸／1477／清理／push；unknown paper檔與隔離還原映射未動。本批commit/blob/status核驗後停止回報，舊節只作歷史。

## 2026-10-05 小型 learner／Library 收尾（本節優先於歷史待辦）

接手核驗：`dev` HEAD `cd908443fe8a4afb098a5103e70ff6fe728ef6aa`；只有未知未追蹤 `paper_event_source_capture.py`，未讀、未改、未提交。既有 checkpoint、60 檔有界審查與 UI gate 不重做。

- 補強 `test_real_runner_writes_only_current_observed_research_candidate`：180 筆／20 特徵、360 筆重複輸入經真實 semantic dedup 回到 180 筆；重驗 capture／outcome 綁定後實際執行 learner、候選寫入與收據讀回。錯 entry source hash 在 learner 啟動前拒絕，沒有隔離候選產物；既有正式區與 canonical marker bytes 不變、active pointer 不存在、promotion／formal 資格均未取得。
- 來源驗證器使用受控 fixture（非官方原件或自然 producer）；learner、候選、lineage／receipt 是實際執行。結果 `fitted_research_only`，candidate `rec-cal-eef7ecbbcd02e49e5f57d98f`，dataset hash `sha256:428ca5f4c617a9652bf9c6dadd34bc2ab0e9632e2f3ca5081ff1baa4afe45b3a`。收據 hash `sha256:41bbb1958aaad358ec195b16dfe5addd6090f7f53e9effb4a116c7b8aea4d796`。測試暫存依原 fixture 結束回收，JUnit 保留身份；不冒稱原件仍留存。
- 最終單模組 pytest **19 passed／1 Windows symlink skipped，0.99 秒**；changed-test py_compile 與 diff check 通過。前置四個精確 nodes 4 passed，之後增加 JUnit 身份輸出才重跑此單模組；沒有全套或 UI 重驗，也沒有正式 DB／registry 寫入。
- 三張圖已保存使用者 Library（見下表）。全部為 `cd90844` 最小 UI 切片的**受控 DTO／offscreen**圖，不是真實模型、Native 或自然資格證據。雲端保存成功；Windows helper 不支援本機版本屬性寫回，ID 對照另存收據。
- 原始 QA：`output/qa/bounded_learner_library_20261005/pytest.xml`、`receipt.json`；指定原計畫原位更新，保留修改前副本 `plan_before_batch.md`。output／暫存不提交。

| 圖片 | 正式 library_file_id | file_id |
|---|---|---|
| `2382_summary_controlled.png` | `libfile_d0e11bd2f2b08191b4606269aded4421` | `file_0000000043dc81f4afc7e59ff82b5c42` |
| `2382_ml_collapsed_controlled.png` | `libfile_978664747334819186cbe7fb4dd6dd5c` | `file_00000000aa8881f4b90cc9edcd1922c4` |
| `2382_ml_audit_controlled.png` | `libfile_452fcff4b41481919827de371cdbd486` | `file_000000005d6c8243aa5e2a701547c2c5` |

尚待另批：Native 1477 真正取消完成→重試→新身份→正常保存→新程序重開，以及錯 date／run／hash。1000×835 outer／125% 已接受，1000×800 未達保留限制，不新增硬門檻。D 正式 raw-PIT 與清理沿用既有具名依賴；本批沒有重做容量 guard 或清理、沒有操作使用者 App。

後續明確指示已保留：先完成現有 Native 驗收及逐次具體批准的暫存清理，全部收尾後再按唯一 `output/plans/baldr_product_experience_plan_20261004.md` 推進，由 **Sol Medium＋Fast／GPT-6 Luna Max subagents** 分批實作，父層負責規劃審核。此新授權適用後續計畫階段，本批不開子代理、不跳到大計畫、不 push；永久刪除未獲隱含授權。

回退：本批只修改整合測試與兩份交接文件，可針對本批 commit 作 Git revert；ignored 原計畫可從修改前副本復原。Library 檔案保留，不因本機回退自動刪除。Manual／產品／架構無行為變更，不把本次工程測試改寫成正式產品完成。


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

## 2026-10-05 Native 可行性與最小 UI 追補（基線 0831633c）

- 唯讀桌面核驗：前景 ChatGPT；Python 程序為 MCP／formatter，未發現正在執行的 baldr UI。沙箱前景 handle=0／CIM denied 不代表桌面空閒，改以獲批准的唯讀核驗取得真實前景。沒有操作／關閉既有程序、鍵盤、滑鼠或持倉。Native app 控制未開放；舊驅動 `window.show()` 與 modal 不能保證不搶前景，因此**本輪沒有啟動 Native 流程**。需協調短暫桌面時段，不能以 offscreen 替代。
- 1477 舊保存來源 `rec_3a882dd9fc06407298ccbd2a5e1c994f` 的 public query 在 41,453 bytes 小型 artifact／index 副本中讀回；重新編碼錯決策日、換 result/run ID、變造 index payload hash 三項均遭完整性拒絕。原 artifact／DB hash 未變。原封存事件證明 decision=2026-10-05、market=2026-10-02、invocation=`rec_3a882dd9fc06407298ccbd2a5e1c994f:9bbae285d1da44018eba40e6f3b3ae35`，market fingerprint=`cac39aaa588692578b88497d0e3fb2f58b557d740f73ea3aad8948ffbe22182c`。這是原保存來源完整性拒絕，**不是新 retry run、Native 選擇日期／run／hash 驗收或保存重開成功**。
- 確定小 UI 缺陷已修：ML 稽核按鈕依 toggle 狀態顯示展開／收合。DTO 明示 current scope 才標「當前ML研究」與研究日；saved scope 標「所選保存決策ML研究」與模型事件日，未知 scope 維持中性標題。歷史保存決策回顧顯示已讀回 Advice／保存分析日期；沒有所選日期時標未選定。品質降級呈現來源限制，無原因時明示原因未提供；沒有改計算、來源、資格或 hash 契約。
- 真實 2382 唯讀 current consumer：as_of=2026-10-05，ML event_date=2026-10-02、run=`20261002-ffb8777d33621369a15c3c22`、scope=`current_stock_research`；degraded 原因為「H5 標籤尚未成熟；不顯示報酬或成功結果。」已確認可見。沒有注入持倉服務，首屏只是 DTO 的 offscreen 投影，不是完整 MainWindow／Native 驗收。TWStockConfig 的 D 槽 config log 寫入被沙箱拒絕並回退 console-only；未實際寫入正式資料或 registry。
- 真實首屏 Library：`libfile_d7d04064bca881918a985dcada1ab24b`／`file_0000000054f88210b0ea43e50941efb7`。雲端成功，本機版本屬性 helper 在 Windows 不支援，身份對照保存在本批收據。
- affected tests **14 passed**；Workbench **85 passed**；validator **25 passed／4 skipped**；全域 mypy **766 files／0 issues**；兩個 changed Python py_compile 與 diff check 通過。新增測試的兩次失敗是 lookup 抓到 `deleteLater` 舊 group，最終改用獨立 view 觀察各狀態，未改產品 renderer；失敗 XML 保留。1477 負例全部完成後，最後 stdout cp1252 編碼失敗，收據與三項拒絕已落盤且獨立讀回，沒有重跑此負例或改寫 process exit 0。
- 原始證據：`output/qa/native_feasibility_followup_20261005/`，含 final affected XML、Workbench XML、validator／mypy log、真實 DTO／畫面、1477 完整性負例與 Library identity。原計畫原位更新。僅 stage 必要 UI／測試／Manual／功能文件／Snapshot／交接；output 與未知根檔不提交，不 push。

最小下一條 Native 流程已限定：獨立 QA settings／小型既有隔離來源；1477 原來源→Rule 分頁→scope 1477→開始→取消後必須等 `已取消` 且 worker 結束→檢查 last-good 與原 artifact 不變→一次重試；正常資訊 modal 只確認可見資訊，完成以新 execution/result/invocation 與 completed 終態綁定→正常 Save→保存 receipt/hash→新程序精確讀同一新 result。日期／股票／run／source／hash 在每一步從該步實際結果取證，不沿用舊 run；獨立 Native 負例另驗。每步沿用 90 秒上限，不反覆修跑；若失敗，停止並分清產品與驅動缺陷。本輪未執行上述流程，完整 Native 待辦保留。

桌面時段未確認前不顯示 QA 視窗，不修改使用者視窗與資料。暫存清理與大計畫維持前批順序及 Sol Medium＋Fast／Luna Max 後續配置。本輪不 producer、重訓、子代理、cleanup 或外觀擴張。回退僅針對本批 commit 的 UI／測試／文件；原計畫追加段落可還原修改前副本，原保存來源未變。

## 2026-10-05 使用者授權桌面 Native 有限驗收

- 本批基線 dev `e312dc61141d7f0a812466e0ba5f7c0b56ecbbae`，使用者明確授權桌面；僅 PySide6 QTest 的 Windows Native 隔離驗收視窗。無 node_repl Native 控制工具。未訓練、未執行 producer／全套回歸、未修改正式資料／排程／持倉、未刪暫存。
- 首次 sandbox 程序在原來源載入後 screen grab 失敗，尚未取消／重試；以已授權 desktop access 執行相同流程，不計為產品失敗。
- 1477 精確原保存來源 `rec_3a882dd9fc06407298ccbd2a5e1c994f` 成功載入（決策 2026-10-05／行情 2026-10-02）。取消 generation 2 確认「已取消」且 worker 結束，完整 last-good UI 與原來源 JSON 保持不變。
- 重試進入 generation 3，但 `completed retry` 等待逾 90 秒：無完成事件、無 worker_finished_objects、無新 completed result 身分。harness 記錄 TimeoutError 後關閉自己的視窗並退出。新身份→保存→新程序重開，以及新 run 的錯 date/result-run/hash Native 拒絕 **仍未驗收**；不能拿舊來源完整性負例替代。重試超時是工程／驗收阻礙，原因尚未定位，不能稱為等待自然成熟。本批沒有再次重跑1477。
- 外部停止只嘗試 PID 綁定核對，當時 QA PID 已不存在，未停止任何程序。中間推測 mouseClick 未返回已由最終收據更正：實際進入 completed retry 的 bounded_wait，generation=3。桌面已釋放，自己的1477與2382 QA程序均退出；其他應用未關閉。
- 2382 用真實只讀 consumer、Native 報告視窗正常 load_button→背景worker完成，非 MainWindow 全流程／持倉驗收。為禁止正式目錄與 logging 寫入，僅在 config 初始化封鎖該寫入，consumer 讀取與回報未替換。初始 badge/提示更新為「部分可用／報告部分載入」，as_of=2026-10-05，行情 2026-10-02/收盤332；ML current_stock_research run=`20261002-ffb8777d33621369a15c3c22`、source hash=`76368e75edaa665ee363cc25506687288f3ddeb2475c40cdb4c933fb16ba8d2e`，與先前真實2382來源一致。
- Header 疑點拆開：正常 load 沒有殘留「尚未載入」，證實該初始狀態源於 offscreen 直呼 render 未走 loaded callback；但未選定保存來源時「來源：未標示／決策日：未知／資料日：未知」仍存在，下方獨立行情來源另有2026-10-02。這是未提供 source context 的文字歧義，未取得資料混用證據，不直接判為產品 bug，也未改 UI。若要確認 MainWindow 選定來源脈絡需另批有限驗收。
- 1000×835/125%既有接受限制沿用，不重做尺寸工程；本批不宣告1000×800通過。沒有產品修改，沒有新增/重跑tests。
- 收據／截圖：`output/qa/native_acceptance_authorized_20261005/native_retry_final_receipt.json`、`2382_normal_load_receipt.json`、`library_identity.json`。2382圖正式Library `libfile_3dbdfe10c6c48191bd65b687bb8b7444`（`file_000000006d3081f4bf3bd49b257c7d4e`）；取消圖 `libfile_57e26618f2a081919724e90426e8be2a`；超時圖 `libfile_65f3870d3a908191998117af696e853c`。這批為 Native QA 證據，仍不是自然模型成熟證據。
- 下一批由父層裁定1477重試超時的有限診斷；暫存清理盤點已交付但未執行，仍須遵守先Native閉環→已批准清理→唯一原計畫的順序。永久刪除另需逐項批准。

## 2026-10-05 Generation 3 重試超時診斷（未再開 Native）

- 結論：實際重試超時根因仍未知；已確認 driver 缺少 timeout 當下 worker/phase/error/stack 的觀測，不能回推90秒時是否仍運算、等待IO或signal遺漏。沒有明確產品bug，未修改產品程式，Native仍未通過、工程未完成。
- 先前成功1477 strict-PE從03:08:25.013198Z開始到03:08:29.711005Z保存讀回約4.697807秒（包含modal/save）。當時native_runner_v23.py的_wait用processEvents+time.sleep(.02)。本批qWait(1)小型離屏A/B為0.359秒對0.047秒，證實可增加等待延遲，但不能外推或證明真實90秒根因。Batch7亦曾generation3超時，其pump已用Python sleep；因此不能把兩次缺口都歸因qWait。Batch9沒有開始重試，是取消中誤判。
- timeout截圖仍分析中/舊結果，dialogs=0、completion_events=0、額外finished callback=0；沒有timeout isRunning/isFinished、progress/error/native_finished或stack紀錄。completed handler原本會先更新UI後開modal，支持當時不是完成modal卡住，但證據不足完全排除其他瞬時問題。
- 靜態路徑每次建立新ProgressTaskWorker，cancel event預設false，_begin_execution_status重設UI cancel flag；隔離離屏cancel generation2→retry generation3完成及native_finished通過，22事件、新cancel flag=false。這僅驗證Qt訊號/執行緒，不替代真實Native。既有兩個精準測試2P/1.44秒（pytest cache permission warning），沒有全量重測。
- graphify只查既有graph導引（72相關節點/427鄰邊），未重建或開子代理；目前HEAD原始碼為權威。沒有操作桌面、真實推薦/資料查詢、producer、learner、刪除或壓縮。
- 修好的隔離driver `output/qa/native_retry_diagnosis_20261005/native_retry_instrumented_not_run.py` **尚未執行**，保持90秒及原接受條件；恢復sleep(.02)，pre-start接全部worker訊號，記錄run-enter/exit、thread id/generation/ns time、實際retry config/scope；timeout保存worker flags、UIphase/progress/last_activity、result identity與Python全thread stacks；modal保留wrapper避免id重用漏記錄。`worker_diagnostic.py`已py_compile，觀測器離屏探針exit0。首個探針末尾stdout cp1252錯誤已保留，修UTF8後另用probe_utf8成功，未覆寫舊證據。
- 最小後續：父層安排新的桌面時段，先核對原來源/inputs/hash與retry config差異，只跑同一1477一次。遇error/timeout立即讀phase/stack/terminal紀錄，不延長期限掩蓋、不再盲跑；僅正確completed新identity才繼續save→fresh reopen→新run date/result/hash負例。依合作式shutdown安全收尾，不能強制terminate持有資料資源的thread；未安全退出就明示worker/桌面狀態。
- 完整證據及策略：`output/qa/native_retry_diagnosis_20261005/README.md`、pump_probe.json、probe_utf8/receipt.json、affected.xml、graph_probe.json。本批只修ignored驗收driver與文檔，沒有用fixture pass宣告Native接受，清理/roadmap順序保持。

## 2026-10-05 09:23 UTC：Native有界操作鏈已完成（更新較早待驗）

- 本次基線770625cd，遵照使用者09:11UTC授權直接操作；1477 generation2真正已取消、native thread完成且last-good保留，generation3在4.5秒完成並保存新來源 `rec_e677f9ba56d84a5cbcd6f18d5778a01c`。新程序PID34768與首次35148不同，完整execution/result/hash一致；決策2026-10-05、行情2026-10-02。payload `sha256:708fcd18c1980817203549d7a81440811c01a5677d39642e1d26cd6d9c0b5802`，raw artifact `sha256:40c62704e28ccd1f52e724de456b7b1af93942f0e6b90d62b590ff6f0e822965`。
- 本次正常UI新分析設定為PE999／volume ratio min1，因量能未入選，與原PE1的舊來源原因分開記錄；不得稱為推薦成功或原run。新來源Native截止日10/4拒絕10/5未來Advice；42,087-byte隔離副本的artifact日期／result-run／index hash三負例拒絕且保留同一last-good，原artifact/index不變。缺少source_snapshot_hash的欄位仍留空，沒有代填。
- driver觀測修正後真正重試一次就完成。讀回driver誤查Request.universe的失敗保留，改讀sealed config；metadata通過但畫面擷取偏早的版本也保留，最終reopen3加可見提示／表格條件及repaint350ms並實際看圖。只重開讀回／負例程序，未重跑已完成分析；沒有產品修正，不延長90秒。此前超時根因因原telemetry不足仍不回填為已定位。
- [完整Native驗收](NATIVE_1477_RETRY_READBACK_ACCEPTANCE_20261005.md)及本機output/qa/native_retry_completion_20261005/acceptance.json、attempt1/native_retry_final_receipt.json、reopen3/reopen_negative_receipt.json、library_identity.json為最終證據。新程序圖Library `libfile_4a0caaa465ec819188c4b880b112470c`，錯hash圖 `libfile_0583c30490608191981996418201059c`，其餘3圖ID見驗收表。
- 四個自己的QA程序均退出，09:23:01UTC核對PID全無，桌面釋放。未修改正式資料/持倉/排程、未訓練/producer/全量tests、未清理、未push。本次僅完成原Native工程鏈，不授自然成熟/正式模型/PIT資格；1000×835/125%沿用，不宣告1000×800。2382header前批正常load結果保留。
- Native已達標，交回父層安排安全清理，再依指定原plan分階段推進；永久刪除另需逐項批准。原plan正文保留，追加本收據，不另開替代計畫。

## 2026-10-05 可恢復暫存整理已交付

- 1251原白名單中879根同C盤隔離至C:/ta_iso_1005，642純pytest fixture、229空根、8mypy快取，108054檔、AllocationSize前後4,951,450,624bytes一致；不釋放檔案容量，未永久刪除／清空回收筒／改權限。r015 d/e/f成功，g/h/i保留；R20/R26 user Temp136空根成功，具QA引用的群組保留。372根保留，58引用根及19占用／權限未通過者均未動，精確理由／映射／還原步驟見[整理收據](TEST_TEMP_REVERSIBLE_ISOLATION_20261005.md)與output/qa/reversible_cleanup_20261005。實際r015 d還原並重新隔離、全879項identity核對通過。
- 最新只讀容量：C free237,505,548,288／既有需求215,285,235,712；D free300,638,941,184／既有需求295,279,001,600，兩者點時間PASS；不歸因本批隔離，不啟動writer，實際writer前重新查核。本批必要永久刪除清單為空；若要真正釋空間，879項未批准候選另需逐路徑批准。
- Native不重開：此前driver的pre-start訊號／run與timeout觀測、sleep(.02)等待及讀回sealed config／paint條件修正已記錄；歷史90秒根因仍未知，最終4.5秒真實鏈已接受。未開代理／producer／訓練／全量tests，未動正式資料／模型／持倉／排程。本批結束交回父層，按唯一原plan啟動後續階段。


## 2026-10-05 原產品計畫階段 0 首包

沿用原計畫，UX01有界基線／UX16來源子集／UX17量測已交付；產品程式未改，階段1優化尚未開始。首屏median10.148秒、資料10.126秒，30次列選取高亮p95=116.60ms；不能當篩選／圖表驗收。首次市場探索Overview worker發生重資料切片，loaded全程CPU60.94秒／RSS1.57GB、約90秒合作退出，是下一包工程入口，不歸因自然成熟。來源／正式資格／暖機／全市場與benchmark缺口仍見矩陣；原UX依賴不跳過。

完整結論／同版hash／失敗紀錄／兩位Luna工具派發及自省限制見[效能基線](PRODUCT_STAGE01_PERFORMANCE_BASELINE_20261005.md)及[來源矩陣](PRODUCT_STAGE01_SOURCE_MATRIX_20261005.md)。五個child與輸入guard通過，PID均退出；外層末尾Unicode print exit1保留，提交版僅輸出與CPU命名收尾，基線未重跑。不重開已接受的1477／learner、不producer／訓練／全量回歸／永久刪除／push，unknown根檔及還原隔離均保留。本包本地commit／blob核驗後停止交父層。


## 2026-10-05 階段1限定效能修正包

兩位指定Luna Max完成7個產品檔及6個test檔修正，root整合；profiler及main未改。日期解析單次memoize、回測／組合首次圖表lazy與可見錯誤重試、同輪盤勢整批近期價格及合作取消／native-finished關閉已驗。同條件5跑首屏10.148→8.642s（14.84%）、Industry3.206→1.842s（42.56%）、Backtest1.098→0.893s（18.62%），完整rowset SHA不變；四筆只啟動RSS約0.70→0.57GB。Loaded30關閉13.349s且worker0；完整盤勢正常完成另以Native探針驗，peakRSS1.452GB不與提前取消0.675GB混報。30列高亮p95 49.65ms不代表全互動速度。

Market61、root loader9（8項重跑）、整合47、Workbench85、validator25／4skip、mypy766、13檔compile通過；唯一Windows fixture長路徑失敗保留，短新Temp重跑1pass。5＋1 Native場景12個launcher／Python PID觀測均退出。來源與資源邊界、code／summary SHA與原始收據見[階段1收據](PRODUCT_STAGE1_PERFORMANCE_IMPROVEMENT_20261005.md)，commit readback留output。原plan append-only，UX01→UX16/17→UX18/19→UX04/05依賴維持。階段1／UX17仍部分完成：早期breadth／relative SQL僅區段前後取消，來源availability／warm-up／PIT／universe／benchmark與自然ML資格未全部完成；不新增方法或UX18 Gate。

1477既有Native驗收不重開，1000×835／125%接受與1000×800限制維持；沒有writer／訓練／永久刪除／push，未知paper檔及C:/ta_iso_1005映射未動。本地commit/blob/status驗證後停止交父層。


## 2026-10-05 階段1早期SQL取消小包

基於2acdbe2c，四檔backend補Builder→Breadth／Relative service→provider→shared loader取消callback，獨立SQLite分支亦用連線專屬progress handler；SQL確實中止才轉取消例外，真實DB故障不遮蔽，舊provider／Series.map dtype／Decimal／cutoff／排名不改。47 focused、50 UI/Shutdown整合、mypy766及7檔compile通過。Native早期SELECT中關閉：worker仍running時視窗保留，32.77ms至native-finished、131.31ms至hidden、沒有完成snapshot／殘留worker；取消→同來源按鈕重試21.141s正常產生真實snapshot。3個Native場景6個launcher／Python PID全退出，input guard／來源rowset SHA不變。

最終單跑loaded30首屏9.350s、p95 54.173ms、peakRSS618,389,504 bytes、全程13.421s退出；這是spot check，不替換舊5跑median。五跑凍結gate逐項核對：首屏-14.84%、四筆純啟動RSS-18.19%、loaded30+close峰值-57.00%（含提前取消）、p95 49.65<300ms皆通過；Industry42.56%通過20%，Backtest18.62%未達20%（原凍結是兩段各自20%，已更正文案，不放寬或微調湊數）。上包13.349s是全程序時間而非close latency，PID退出證實不是只藏UI。完整normal retry RSS1,456,594,944 bytes與提前取消分列。

詳見[取消與gate收據](PRODUCT_STAGE1_SQL_CANCELLATION_20261005.md)與output/qa/product_stage01_20261005/stage1_sql_verified.json。main／view／原初始化優化／profiler的未變blob已核對，舊數字保持其版本身份。沒有重跑五baseline／訓練／producer／大DBcopy／永久清理／push；未知paper檔與C:/ta_iso_1005映射未動。停止交父層。

下一原plan包是stage1／UX02純呈現共用狀態字典，先接Research Console／Backtest，沿用上下文列與分層元件，保留未知碼、狀態維度及結果身份；本包只盤點，未實作。UX16來源能力、UX19容量／writer依賴與自然ML資格分開，不拿自然成熟阻擋UX17／UX02工程。不宣告整個stage1／UX17或全部gate完成，也不盲跳UX18／新ML。


## 2026-10-05 UX02 共用狀態有限切片

`ui_qt/status_vocabulary.py` 提供純呈現 `status_label`／`status_detail`，明確區分 data／load／research／qualification／event／validation；未知碼保留，completed 不跨維度授予資格。盤勢、持倉系統健康、選股、個股及 Console 的既有入口共用詞彙；Workbench 將時間等待／休市與具名故障分開，回測保留 PASS／WARN／FAIL 並加白話驗證狀態。原始診斷、來源及日期／身份沿原 DTO 保留，沒有修改策略／producer／模型或拒絕 guards。

本包是 UX02 有限落點，非全頁狀態重構或整個階段1完成。Backtest 初始化18.62%仍未達20%凍結門檻；UX16來源／PIT及UX19 writer／容量依賴另列，不以自然成熟阻擋本包工程。詳見 [UX02驗證收據](../06_qa/UX02_SHARED_STATUS_VOCABULARY_20261005.md)。未重跑效能／learner／Native1477、未producer／清理／push，未知根檔及C:/ta_iso_1005還原映射未動。完成本地commit／blob核驗後停止交父層。


## 2026-10-05 UX03／06／13 收藏原來源增量交付

基線3239d23；收藏→既有觀察清單→同源個股→同query已收藏股票切換→exact返回已完成限定工程閉環。JSON／SQLite兼容且明確同股書籤升級已由隔離fixture核驗；沒有自動真實遷移或第二ledger。取消、冪等、錯來源拒絕及精確移除／還原均有受控證據。

Storage/UI agent21項＋root related93項已解決全部失敗；WB85、validator25／4skip、mypy778、compile／quant guard通過。Native保存／新程序重開與post-copy final readback均passed，PID33448／14424／36364退出、worker0；原快照／正式DB stat不變。raw與最終codepins在 `output/qa/ux03_research_bookmark_20261005/`，最終Native收據SHA=`4b0360162532a6fc9569e8741a79695c3e57efae73d41f55bda43f1d977ffdc4`；Library四圖ID見library_metadata。真正HEAD／提交以新commit_readback與Git為準，勿以舊handoff倒退。

僅更新既定原計畫 `output/plans/baldr_product_experience_plan_20261004.md` append葉片，原內容保留。完整stage1–3與其他工程pending、Backtest18.62%／20%、真人／PIT／availability／自然ML資格仍各自保留；後續由父層安排。清理／永久刪除、push、producer／learner、真實使用者視窗操作皆未執行。


## 2026-10-05 UX04／05 預設與候選摘要背景包

基線42ff54b；五個固定MA預設明確套用、完整母體／缺件／三態與可見排除理由、選取支持／反證／資料限制立即刷新，來源／日期／方法／資格和exact收藏／返回保留。原排名未提供停用，不造新方法／分數／勝率。final43定向、WB85、validator25／4skip、mypy779、compile／guard與真D已發布2股readonly offscreen通過；receipt SHA=82ab54465294c69dc81828b009b40febb69dd31168f9a74d2307e1ebe9b40602，原snapshot／DB stat／code pins不變、worker0。初字型probe overload誤判與漏接選取信號修正後重驗，原收據保留，見同一UX16 QA新增章。

**新Native互動尚待桌面時段**：本包不開前景或操控鍵鼠，背景code/tests仍可繼續。原plan首版stage1–3尚缺Backtest18.62%／20%凍結改善、完整合格母體及原排名版本／day-week／topN發布、其他同源市場／強弱consumer融合，以及長期storage/growth與跨程序crash工程；PIT／official availability／自然ML／真人限制分列。下一背景包可先UX16／18母體與原排名來源契約。soleplan append-only，原前綴保留；本地commit/blob核驗後交父層，未push／正式或全量producer／training／永久清理／真實收藏寫入／遷移，未知paper與restore maps不動。


### UX16／18 有界母體來源契約延伸（2026-10-05，基線7e11f5a8）

明示母體設定是隔離研究批次來源：ID／版本／截至日／原檔hash、納入／排除與理由、已知或未知設定分母。可選manifest extension納入原不可變identity，讀取與consumer重新核對來源revision／刪除／成員／date；舊無設定cohort保留來源與原始分母未知。清單、母體盤勢及候選摘要共享同一契約，設定不授予PIT或推薦資格，不計算新分數。CLI明示讀included，禁止無設定手動更新默默降格已綁來源。

原排名來源audit：原計畫指StockScreener本日／本週價量強弱排序（原公式不改）。ScreeningResultDTO有period／method／version／eligible count，但即時結果未有不可變run／完整成員排除／hash發布；strong_stocks_view僅記憶體快取。saved recommendation屬另一rank kind不能代用。有限currentDB schema唯讀未找到rank／screen tables，不推論全球不存在。原排名未知且停用；需原引擎不可變結果發布工程，不稱等待自然成熟。

本包無Native前景或使用者視窗操作，無訓練、全市場producer、正式DB／registry或真實書籤寫入；永久清理仍未執行。驗證與commit結果見同章最終收據補記。


### 本包最終驗證與接受邊界

- 最終受影響9檔共104 passed；Workbench85 passed；validator25 passed／4 skipped／0 failed；全域mypy781 source files通過；13個changed Python compile通過；金融float／look-ahead guard及diff check通過。母體JSON／manifest嚴格比較包含bool／int alias拒絕。第一輪6個failure是新測試fixture明示reserve=1違反中央200GiB，已改mock204GiB並保留200GiB guard；原failure receipts保留，未降低產品容量限制。各局部agent測試與104重疊，不加總。
- 真D SQLite唯讀小批次1477／2330／2382，以明示設定排除2317（研究批次選擇，不是資料／投資風險判斷）。設定納入3／排除1／已知設定分母4，發布涵蓋3/3、缺件0；producer新增14832 bytes、暫存峰4455 bytes，200GiB預檢通過。2382個股consumer讀回verified；正式DB／WAL／SHM前後stat一致。沒有原排名／新分數／learner。
- manifest SHA256 `2d241068d3b6df9a06c65267da0c0925c30d3244c6116da626d6a537f742311c`；identity `6c4a3fd3c82f074f5085a9ac6dff0437c7ba287c80ea8e696bc16118d3f2d9e6`；設定來源SHA `264dd7632fded527d82f20e7199c5f48d7acb33f9f56e33ee85b2feabfbe3379`。截圖為真D唯讀＋隔離發布有界母體，offscreen；名單／盤勢／候選同identity與分母，手動更新不啟worker；source inventory與code pins前後一致、worker0。首輪未註冊中文字型的截圖保留為initial_font失敗證據，harness採既有font helper重拍後可讀；產品字型未改。
- QA收據：`output/qa/ux16_universe_20261005/verification_summary.json`、`related.xml/log`、`real_producer_receipt.json/log`、`offscreen_receipt.json`及兩張`real_configured_*.png`。本地commit/blob以同目錄commit_readback與Git為準；QA raw仍ignored，未push。唯一原plan原146969-byte prefix SHA `1be4f4eb34aa6d043915f60280a65ae4ab8c5482198a8ea0e503931318a05713`保留，僅追加。
- 已完成工程：有界母體設定custody、可選v2manifest extension、source revision/deletion/member/date拒絕、明示小批次CLI、同源consumer呈現、來源未知與排名停用。仍缺工程：原StockScreener day/week不可變結果發布（run／method/version／完整eligible成員與排除／原始rank/score/topN／sourcehash），以及原plan其他生命周期／storage/growth項；不稱等自然成熟。來源決策另須明確合格母體權威與可用性/PIT證據，本包手工研究成員不是正式母體。Native鍵鼠／縮放／跨頁及真人驗收未執行；全App startup未由本包證明。下一背景包建議先原排名publisher契約，沿原公式不重算新分數。永久清理、真實書籤遷移仍未授權執行。


## 最新延伸：2026-10-05 UX18 原引擎排名有限收尾（基線27768eb9）

已交付：既有StockScreener原公式day/week × strong/weak四mode不可變publisher／verified reader；原engine/method/version/params、parent feature/universe/date/inputhash、原rank／舊score label與窗口、research-only資格；來源拒絕、OSlock、atomic manifest、unchanged、容量有界；Daily名單／candidate／Market同排名身份。原引擎檔案未改，不以MA／其他score替代，沒有新公式。

驗證：87個不同affected有pass證據（首輪82pass／4fail→四案精準重驗4pass，新增inflight mode1pass），WB85、validator25／4skip、mypy783、12compile、guard／diff。初14typing、舊fixture參數及未提供label修正，失敗保留。真D既有三股feature parent不變，四modepublished→readback，repeatdaystrong unchanged且inventory不變；eligible3／missing0、18478bytes；DB/WAL/SHM stat、原5sourcefiles及engine SHA穩定。8offscreen圖同rank object／parent、worker0、finalcodepins吻合，不能替代Native。

剩餘第一版工程具名：rank-aware收藏／回訪及StockReport來源context版本化（本包明示拒絕原排名排序收藏）；其他原大盤／強弱consumer融合；完整feature/method dictionary；正式合格母體與排程部署；長期storage/growth及其他lifecycle crash驗收。Backtest18.62%／20%門檻未達仍保留。來源決策：正式母體權威、officialavailability／歷史membership／PIT；legacyTop/Bottom百分比口徑非一般前幾％，numeric score未暴露，若修改須原引擎方法版本決策。手工研究母體不是正式全市場。工程缺件不稱等自然成熟。

Native鍵鼠／縮放／跨頁、全Appstartup及3–5真人驗收另待桌面時段；未操控使用者視窗。沒有全市場採集／正式DB或registry寫入／train／大DBcopy／永久清理／push；未知paper及C:/ta_iso_1005映射不動。既有featurev2／舊bookmarks保持身份，無rank來源仍unknown，未靜默遷移。raw與commitreadback output/qa/original_rank_publisher_20261005；tracked證據 docs/06_qa/UX18_ORIGINAL_STOCK_RANKING_PUBLISHER_20261005.md。原plan151202bytes前綴完整保留，只追加，本地commit核驗後停止交父層。


[UX18完整收據](UX18_ORIGINAL_STOCK_RANKING_PUBLISHER_20261005.md)


## 2026-10-05 UX19 有界儲存與發布復原延伸

本批唯讀參照盤點與 dry-run 不提供永久刪除授權；歷史 manifest／artifact／v1-v2 收藏參照保留，未知 schema、缺件、來源不完整及超預算採保守保留。排名首次發布的缺件指標 CAS 與隔離跨程序復原收據、容量時點政策及驗證結果見 [限定收尾收據](UX19_STORAGE_AND_PUBLICATION_RECOVERY_20261005.md)。未改原引擎／排名／方法／日期，未重跑既有真實 publisher 或 ML。

真實 MainWindow 九工作區在空資料、隔離配置、offscreen 子程序最小啟動／正常關閉通過（PID 23772，worker 0，guard 無違規）；這不替代帶正式資料的 App 功能、Native 或真人驗收。其他 consumer／完整方法字典／正式母體與排程／其他 writer 生命周期／長期自然成長仍是工程待辦；Backtest18.62%／20%保持未達，來源 availability／PIT／自然資格另列。使用者其他對話的容量／Evidence 變更保留且不納入本批提交，中央政策以時點 pin 為準。


## 2026-10-05 UX09 有界 MA 名單入選歷程

既有兩條 MA 三態快照經純比較模型、有限歷史 reader 與背景 UI 呈現本次新入選／持續符合／重新入選／未再符合，並保存前次日期、理由與可回放來源身份；不是策略升降級服務。無效／缺件／漏日／同日修訂／版本或母體變更及回填保持未知，不在刷新時寫事件。日曆只讀現有快取，publication 前可得性核驗；現有真實來源只有同日，不能作跨日自然歷程證明。

此為原計畫 §8.1／UX09 的研究讀取切片；不更換母體權威或舊標籤、不啟動自然 capture／outcome 階段5，不宣告首版完成。完整方法字典、其他 consumer 融合、正式母體／排程與其他 writer 生命周期仍是工程待辦，Backtest18.62%／20%不變；Native與真人驗收另待桌面時段。詳見 [UX09 限定收據](UX09_RESEARCH_MEMBERSHIP_LIFECYCLE_20261005.md)。


### UX09 最終限定收據（2026-10-05）

78 個不重複受影響案例、Workbench 85、validator 25／4 略過、mypy 786、8 檔編譯通過。真實單日三檔維持未知（翌日發布且無有效前次比較），17 檔來源雜湊及正式 DB/WAL/SHM 狀態不變；未授予 PIT／自然成熟。完整第一版與 Backtest 18.62%／20% gate 未變，長期歷史索引／分頁、部署／其他 consumer 與 Native 驗收仍待完成；容量工作屬其他 owner。詳細證據與回滾見 UX09_RESEARCH_MEMBERSHIP_LIFECYCLE_20261005.md。


## 2026-10-05 UX09 歷史索引／分頁與有限版本復原（最新）

長期保存的研究manifest以可重建SQLite派生索引查詢，32 refs／頁、固定來源／query／generation游標、64頁滑動導航窗口且可持續向更早頁讀取。背景history／explicit rebuild保持當期個股與篩選主線可用；schema／來源／hash／cancel／故障不偽造完整，原immutable來源／舊收藏不遷移。索引最多64MiB，每頁串流重核全index SHA及頁內原manifest/artifact，年度calendar以4096entries／32MiB逐份驗證，不再32份正常累積即整批未知。

限定受影響79個不重複案例、Workbench85、validator25／4skip、mypy788、11變更Python編譯與精度／未來函數guard通過。真實已保存三股來源隔離offscreen回放：晚發布仍unknown、17來源hash與正式DBsize/mtime不變、worker0；沒有讀正式DB去重核current identity。130日×2修訂合成metadata全260refs走9頁，index159744 bytes、最大page JSON13814 bytes／tracemalloc1226583 bytes；不當自然樣本或正式長期總容量證明。

本包關閉UX09索引／分頁／索引程式內版本復原；第一版工程剩餘固定F1–F4，詳細終點與owner見收據。Backtest18.62%／20%仍差1.38百分點，不重測湊數或放寬。舊1477 Native已在6691ec78通過，較早「仍待1477」文字由此更正；新分頁／跨頁Native及3–5位真人另驗。1000×835 outer／125%已接受，不新增1000×800硬門檻。具名full-cohort與原完整Top/Bottom標籤沿現況，官方全市場／新百分位方法只有擴充時才要明確決定，不阻塞目前研究限定工程。

完整操作與排錯見 APPLICATION_MANUAL 的歷史索引小節；[詳細驗證、來源選項與F1–F4凍結清單](UX09_HISTORY_INDEX_AND_RECOVERY_20261005.md)。


## 2026-10-05 F2／F3 原市場頁共享來源與已開能力矩陣（最新）

F2／F3 在已接受的 A／A 研究限定範圍完成：原大盤指數併列具名摘要，強勢個股、弱勢個股可明示切換至每日研究名單同一 immutable 來源；日／周 × 強／弱四模式保留原完整 eligible、Top／Bottom 標籤、實際比較窗及兩種排除。榜外與研究資料缺件分欄，來源變更／清除／過期回應拒絕，切返嚴格唯讀不啟 producer。既有全市場／產業來源、母體與可比較性仍獨立，沒有用三股取代全市場統計。

能力矩陣只登記 close／MA20／MA60、close_above_ma20／close_above_ma60，完整 field／unit／warmup／missing／availability／version／cost／source 與逐股 audit 可查；官方時點及未量測成本維持 unknown。完整只相對 named declared cohort；既有 feature v2／method hash／原引擎與收藏版本不變，沒有新增正式 B 母體或方法版本。

本批驗證：43 個不重複受影響案例有通過證據（根層首9＋相容29＋實際橋接新增1＋F2 focused4；最後11頁面相容重驗為既有案例不加總）、Workbench85、validator25／4skip／0fail、mypy790、12檔編譯及精度／未來函數 guard 通過。受控小型來源驗實際背景 consumer；真實既有三股保存來源驗能力投影與 offscreen 畫面，17 來源 hash 與正式 DB size／mtime 不變、worker 0；後者沒有開正式 DB 重核 current identity，不能宣稱自然跨日證據或 PIT。詳細來源、失敗保留及回滾見本批 QA 收據。

第一版工程剩 F1（18.62%／20%，差 1.38pp；不重測微調）及 F4（整條跨頁整合、部署、長期總容量）。新 Native／3–5 位真人另驗；舊1477 Native已在6691ec78完成，不重列待辦。1000×835 outer／125%沿已接受，不加1000×800硬門檻。工程缺陷不稱等自然成熟；source/capacity／Evidence 屬另一 owner，保留其變更並排除本批提交。沒有清理、正式資料寫入、訓練、前景視窗操作或 push。

[本批詳細收據](F2_F3_SHARED_CONSUMERS_AND_CAPABILITIES_20261005.md)
