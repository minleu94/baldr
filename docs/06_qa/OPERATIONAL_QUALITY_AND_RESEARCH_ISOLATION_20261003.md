# 2026-10-03 行情發布節奏與 Paper 研究隔離驗收

> **日期範圍：**本文是 2026-10-03 的工程／驗收快照；本文所列 task、來源資格與「仍待」狀態只反映該輪證據，不代表目前排程或整體資格狀態。

本次接續 `435a97e09f4788f1393b9f7c7ed803ee786b2c74`，不重做已接受的資料採集、CORE19 訓練或原整合修復。工作樹原有未知 `paper_event_source_capture.py` 保留、不納入提交；本次未啟動資料 producer、未暫停 Windows task、未改交易或正式 PIT/model revision 資格。以下以本次原始收據為準，不把先前 report 當目前故障。

## 根因、修正及適用邊界

| 問題 | 根因與修正 | 保留限制 |
| --- | --- | --- |
| 週末／假日行情被降級 | 四個 market/watchlist services 及 builder 第二層 date guard 原先把不同日期一律 degraded。共用 MarketSessionCadence 回讀 hash-bound、當時已取得且未過期的官方日曆。 | 無日曆、過期、真正缺行情、超過截止仍未更新、未來來源維持 degraded/missing，不以 SQL MAX 日期證明完整。 |
| 日常時間沒有時區 | EvidencePipelineRunner 原預設 naive UTC，日曆驗證因無時區無法成立。改為真實 aware UTC。 | 不補造歷史 availability，歷史查詢不能借用決策之後才取得的日曆。 |
| 略過廣度 1 列 | 6171 在 10/2 確有成交，官方 TPEx 原始漲跌欄為「除息」，數值 normalizer 沒有可比較價差。 | 只有 retained raw SHA/bytes、source/date/available_at、close/volume 全相符才列明 corporate-action 排除；不補 0 或猜測方向，不算進漲跌／平盤母體。其他未知方向仍 degraded。 |
| 相對強度略過 38 檔 | 增加逐檔 reason、有效觀測數、最後有效日、目標行情日及 SQLite 來源。 | 維持原 21 個有效觀測值與 500 bp 最大排除比例，不補價、不擴展歷史、不宣稱全部公司可用。 |
| Paper 研究拖累普通持倉／風險 | adapter 原直接替換 PortfolioAlert/RiskPrompt。改將 Paper alerts/risk/status/ready/warnings/blockers 放獨立 paper_research lane，普通區塊與其原品質完整保留。 | 研究 lane 的 missing identity／thesis／metrics／policy／entry lineage 仍明列；operational ready 不授予研究 ready。 |
| 缺 thesis 被寫成使用者待辦 | machine Paper 與未分類舊來源改列 required_governance_fields。只有明確 source_scope=user_portfolio 且 user_position_verified 的來源可產生 required_human_fields/user_actions。 | legacy manual 標籤本身不是持倉歸屬證明；1418 不補虛構成交或人工 thesis。任何 proposal 仍無自動執行權限。 |
| Risk 與 capture-ready 錯誤降級 | Risk 按 observed/estimated/degraded/missing 上游品質計算；僅允許已具名的來源附註，不要求所有 warning 為空。重算當次 transient quality gaps。 | 未知警告、缺 quote、provider error 仍不 ready，不清除無關 source/正式資格 gate。 |
| 來源追溯序列化 | source_lineage 新納入儲存快照，實跑發現分析邊界 numpy bool；DTO 邊界遞迴轉為保持原語意的 Python scalar，完整往返研究 provenance。 | 不改核心 Decimal 計算；新欄位無值時省略，保留 legacy snapshot 相容性。 |
| child exit0 但 summary 失敗 | wrapper 將 failed/errors>0 summary 回傳 exit2，保留實際 pipeline_exit_code。 | summary/stdout/report/hash/status 各自回讀，不能以單一 exit0 宣稱資料全面正常。 |

04:30 America/Los_Angeles 是既有**專案資料截止約定**，不是交易所原始發布時間證明。依 DST 換算 Taipei 決策日；當日截止前接受前一個已完成交易日，截止後要求當日官方交易日行情。週末、假日由官方年度 cache 驗證，不僅看 weekday。日曆失效即不授 current。

## 具名排除與原始來源核對

`output/qa/operational_quality_closeout_20261003/6171_original_custody.json` 綁定 10/2 TPEx 原始 response；`exclusion_source_classification.json` 保存 38 檔與官方 raw 表對照；原始資料與首次失敗都保留。

- 6171：原始「除息」、收盤 24.50、成交 339,000 股；由 raw SHA 與實際 quote 綁定後排除非可比較漲跌方向，仍呈現 1 個來源附註及排除母體數。
- 20 檔官方原始表當日無有效收盤價；數值 ranking 排除，不能用舊價代替。
- 10 檔當日有報價但不足 21 個有效觀測值：1538、2938、2949、3064、3718、6236、6762、7812、7825、7856。
- 8 檔不在已保存的當日官方報價表：2323、2601、2867、3085、4527、5301、5371、8183。其上市／交易狀態未確認，不能推論停牌／下市，也不能以等待下一次發布概括。已從當日 ranking 排除；該代碼的當日相對強度／流動性不可用。

按數值排除原因：26 檔缺當日有效 quote；12 檔有效歷史不足（其中 2 檔亦不在當日原始表）。這與 raw-source 分類 20+10+8 是不同切面，不能相加誤算。此範圍證據沒有顯示程式漏掉可解析的當日原始有效價；8 檔 listing status 的來源資格仍未核實。

## 驗收證據

本次所有 controlled status-path 都只寫 `output/qa/operational_quality_closeout_20261003/controlled_runs/<run>/` 的 baseline、condition/metrics、proposal SQLite 與 Exit artifact；正式行情 DB／Paper ledger／正式 Evidence DB／既有 proposal 只讀。各輪失敗與測試 stderr 保存，不以後來成功覆寫。

- 針對性 tests、日期/品質/研究與真使用者混合、raw tamper/未來可得日/價格不符、writer 隔離、source lineage 和錯誤 exit 傳遞均有驗證；最終數字在下節原始收據回讀。
- 更新 Workbench 加四種使用流程：136 passed；更新頁 validator：25 passed、0 failed、4 skipped。
- mypy 覆蓋 ui_qt/app/data/analysis/backtest/decision/portfolio/runtime；py_compile 覆蓋本次 Python 修改。
- 21 個現有 Windows root baldr tasks 全部 Enabled、Ready，沒有本次暫停任務。自然 Evidence 既有 LastTaskResult=2 保留，控制成功不改寫該值。baldr-ml-raw-pit-refresh-daily 已啟用、Ready，不冒稱新 producer 執行。
- 兩份既有 automation TOML prompt 同步唯讀回讀契約；ACTIVE/RRULE/target thread/其他欄位完全不變，備份和 SHA 回讀保存在本次 QA。

## 尚受限的用途

現況原始 daily／technical、兩市場法人、信用交易及 TDCC 的更新依本次 freshness receipt 分別回讀；TPEx 信用交易舊 HTTP520 失敗保留，但不能當目前缺件。月營收 2026-08 與季度 2026-Q2 current observations 可供**有來源覆蓋的當下個股研究**；公司的完整範圍、原始公告時間／逐列歷史 PIT 仍未證明，季度未知 cash-flow basis 不供 aggregate feature。

歷史月營收仍缺預期 2026-08（availability lane 最後 2026-06）、formal/candidate quarterly 仍停 2024-Q1，statement availability map 缺件。它們限制歷史 PIT、正式基本面／估值／相關模型資格，不能以 current observations 取代，不全歸自然等待。source_qualification_required/gaps 將原 source_id、actual/expected period、reason 保留；aggregate freshness 與 wrapper 整體 degraded 不被改綠。未知 source、transport、真正 stale daily 或無效 receipt 仍是 engineering_action_required。

已接受 current-restated CORE19／Legacy／Bank 模型仍僅供既定受控研究，正式 calibration/source revision gate 不變。Paper 1418 無合格 entry identity，其他研究部位亦可能缺治理 thesis／forward binding／metrics 資格；研究尚未 ready，不要求使用者為 machine seed 補人工交易或 thesis。Forward sample 不足與 Exit 無合格實際平倉觀測只能自然／治理累積，不能虛構報酬或績效。

## 回復與提交

本次 `rollback_checklist.json` 與 `before_files/` 保存 source/docs 修改前 bytes；automation 額外保存 before TOML。回復前先比對最後 SHA，避免覆寫後續使用者變更。正式資料未修改、Windows task 未修改，因此沒有待還原的暫停任務。新 QA control writer artifacts 可保留為研究證據，無正式狀態移轉。

本次僅追加本機 commit；不 amend、不 push。未知根目錄 copy 保留在工作樹。

## 最後控制實跑及最終測試回讀

`output/qa/operational_quality_closeout_20261003/evidence_acceptance.json`、`acceptance_exit.json`、`acceptance_verified_readback.json` 是最後驗收，程式 bytes 在開始／完成一致：

- actual wrapper process exit **0**、actual child exit **0**、summary errors **0**、blocking gaps **[]**；watchlist/portfolio/risk capture-ready **皆 true**。
- 整體 **degraded**：`freshness_status=degraded`、`source_qualification_required=true`、`research_qualification_required=true`；`manual_action_required=false`、`engineering_action_required=false`、`validation_attention_required=true`。不把來源資格或研究缺件變綠，也不向使用者製造人工交易／thesis 待辦。
- child warning 只有 `forward_summary_status:INSUFFICIENT_SAMPLE` 1 次；來源附註 5 種各 1 次：6171 raw 證明的除息排除、原 ordinary manual 來源計数、2382 chip estimated、相對強度排除 38 檔、Risk 保留 portfolio estimated 品質。manual 計數不是已確認的真實持倉或新交易。
- Paper research lane status **degraded**、capture-ready **false**；其 alerts/risk、身份／thesis／metrics／policy 等限制獨立保存於 report/JSON，不授研究成功或正式資格。
- 原 canonical proposal **35 → 35**，全欄／全列精確一致；所有經回讀的衍生 writer paths 在本次 QA controlled_runs。dry_run=true、confirm=false、writes_evidence_db=false、production_scheduler_allowed=false。
- 最後 targeted tests **229 passed、2 skipped**；Workbench＋四使用流程 **136 passed**；validator **25 passed、0 failed、4 skipped**；mypy **756 files success**；py_compile 與 diff check 通過。測試跳過為既定 optional/platform 分支，不當成驗證成功。

Child stdout **652,914 bytes**，SHA `sha256:35e538b6bab788b47ff01d5ee8ddd1119ffaa5e2591283eac96cdd151caf77ba`；報告存在 `output\qa\operational_quality_closeout_20261003\reports\20261004_20261003_121335_600354_evidence_pipeline_dry_run.md`。前輪 NumPy provenance 序列化失敗（wrapper2/child0/errors1）及早期 naive-clock 失敗留在各輪 status/exit/stdout，未覆寫自然任務既有失敗。
