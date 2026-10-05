# 2026-10-05 有界語意審查與體驗接手

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
