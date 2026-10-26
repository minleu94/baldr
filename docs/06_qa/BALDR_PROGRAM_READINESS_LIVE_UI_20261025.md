# Program Readiness 即時 UI 接線 QA（2026-10-25）

## 2026-10-25 Owner 授權決策落地與登錄後 readiness

依 Owner 在本對話明確授權，由 Codex 僅對 11 個尚無足夠來源接受證據的 P0 候選作非生效 `deferred` 決策：無 allowed use cases，不接受來源、不做法律審查、不授 downstream。既有兩個月營收決議維持 `limited`，僅 `research_shadow`／`diagnostics`。11 筆已追加到工作區候選 registry，readback 11/11，receipt 的 `formal_database_written=false`、`source_acceptance_granted=false`、`downstream_eligibility=none`；正式資料根與資料庫未寫入。

以合併決策檔重跑唯讀完整 readiness，inspection exit 2 是報告仍有 Gate blocker 的預期結果；外層受控 Job 成功、程序自然排空、handles 關閉、鎖釋放。最新結果仍 `action_required`：P0 `action_required`、Evidence／Paper／Performance `partial`、Formal／ML `action_required`，Runtime 與 Update History `ready`。P0 blocker 從缺少逐來源決策改為明確 `source_acceptance_deferred`，並保留 `license_not_accepted`、官方請求日無資料／公告時間缺失、`formal_oos_disabled`、`production_scheduler_disabled` 與 `downstream_eligibility_none`。換言之，現在沒有待 Owner 點頭的 source-choice，但證據與資格 Gate 仍未通過。

決策檔 `p0-source-decisions-owner-deferred-registered-20261025.json`、候選 SQLite registry、追加收據、授權 provenance 及 readiness JSON 均在本次 visualization workspace。第一次更新使用者環境變數 `P0_SOURCE_CONTROL_CENTER_DECISIONS` 遭 Windows registry access denied；經核准的使用者層級設定後已成功更新並讀回，現在指向上述新檔。下次啟動預期顯示 11 筆 deferred；尚未重啟 UI 做目視驗收。

本次未跑測試套件；readiness 是唯讀盤點。執行收據：`owned-validation/readiness-owner-deferred-registered-20261025b/receipt.json`，`passed=true`、`job_remaining=0`、`source_unchanged=true`。完整結果：`final-readiness-owner-deferred-registered-20261025.json`。

## 2026-10-24 P0 stale fallback 診斷補齊

官方主要路徑對查詢日回覆無資料時，若法人／信用的 TPEx fallback 成功解析到較早日資料，P0 audit 現將機器狀態標為 `degraded`、可得性標為 `stale_fallback_observed`，PIT 標為 `source_date_mismatch`。10/23 live audit 的法人 fallback 為 909/909、信用為 919/919，兩者觀測日期均是 10/22；各自的 10/23 primary raw／accepted 仍為 0。fallback 的解析筆數和日期另列，並保留 fallback payload hash。它不會被當成查詢日資料、PIT 歷史、來源接受或 downstream eligibility。

Data Update 表格把「來源日期早於查詢日」、「取得較早日期資料（非查詢日）」及較早日 fallback 的 accepted／observed 筆數直接呈現；完整原始代碼保留在診斷提示。中介 P0 DTO 已接通 audit 中 fallback counts，避免稽核有數字但表格顯示 0。

新 audit 摘要為 13 sources、12 degraded、1 missing、0 machine-verified；缺件仍為 MOPS 季報 artifact。candidate audit JSON 為 `p0-source-audit-stale-fallback-fix-20261023.json`，SHA-256 `6E18BA598DCB34A827513E1B7B14FB491AF9EBA60497573786F307CEE10DAF29`。HKCU `P0_SOURCE_CONTROL_CENTER_AUDIT` 已讀回指向此收據；decision 與 license 路徑保持原值。變更供下次啟動讀取，本次未重啟 app 做目視 UAT。

受控 Windows Job 驗證：P0 candidate ingestion、source evidence audit、formatter 與 Update Workbench 共 **146 passed**；Update validator **25 passed／0 failed／4 skipped**；修改檔 py_compile 通過；mypy **1,144 source files，無錯誤**。各 Job 自然排空，source pins 未變。這是 fallback 資料流／UI 回歸驗證，未把任何來源 Gate 升格，也未新增來源授權或 PIT 證據。

<a id="2026-10-24-utc-twse-coverage-範圍校正與雙來源更新"></a>

## 2026-10-24 UTC：TWSE coverage 範圍校正與雙來源更新

依官方上市清冊、上市日與 MOPS 月營收來源範圍重抓 TWSE machine evidence，沒有寫入正式資料根。原始 1,097 家現行清冊中，6467 在 2026-10-20 才上市，晚於 2026-10-17 月營收報告日；10 個 `91` 開頭的 TDR 不屬於 MOPS 月營收清冊範圍。對齊後母體為 1,086，官方月營收 1,088 列中 1,086 列屬於該母體，coverage 10,000 bp、品質 10,000 bp、缺漏 0。額外觀測到的 9105、912000 也依同一 TDR 範圍明確列為 out-of-scope，而非未知意外列。

現行 machine evidence SHA-256 為 `sha256:0961d587c11e67fbfe085d04dd8197b26000115720cf05ab3e37b39bfc31026f`；append-only TWSE 子決議為 `machine:twse.monthly_revenue_announcement:20261024T230051626085Z`，decision content hash `sha256:37267ba9fe5fab78d56da40ed277a92697f301258e369ed63c3239afd736b2fb`，狀態仍為 `limited`，僅 `research_shadow`／`diagnostics`。TPEx 現行 evidence 仍為 893/893、10,000 bp，亦為 `limited`。P0 Control Center 唯讀投影目前為 **2 limited／0 accepted／0 downstream eligible／11 contract-only**；production ingestion、scheduler、Formal OOS 與 ML promotion 均仍關閉。

TWSE 原先的 9 個缺列（99.17%）是把 TDR 與報告日後上市的公司放進錯誤分母；較早的證據及決議保留作歷史，新的範圍校正以子決議追加，沒有改寫既有決策。TWSE 現行候選證據路徑為 `C:\\Users\\archi\\.codex\\visualizations\\2026\\10\\23\\01a16afa-5b3f-7692-a5db-8881433773e9\\twse-monthly-revenue-machine-evidence-20261025-scopefix-v2`；combined decisions 與唯讀 projection 路徑仍由同一工作區的環境變數指向。新的 User environment license 路徑供下次啟動 app 讀取；本次沒有宣稱已目視確認重啟後 UI。

受控驗證：`tests/test_p0_machine_producer.py tests/test_source_acceptance_governance.py tests/test_capture_p0_license_evidence.py` **21 passed**；對修改的 producer、governance 與測試檔 `py_compile` 通過。兩次驗證 Job 均自然排空、handles 關閉、鎖釋放。這只證明此兩個月營收來源的限定證據，不改變其他 P0 source、正式資料、PIT 歷史、自然週期、Paper fills 或 Formal／ML inputs 的 gate。

<a id="2026-10-23-最近應有交易日-13-source-bounded-refresh"></a>

## 2026-10-23 最近應有交易日：13-source bounded refresh

為免週六 10/24 probe 把日頻來源的週末無列誤作缺漏，另以 10/23（週五）重做 13 個官方 route 的 bounded 唯讀 probe。當次 audit 有 **10 degraded、3 missing、0 machine-verified**；後兩者指 audit 層對該請求日期無官方列或季報 candidate artifact 未供應，不代表來源不存在。3 個 missing source 為 `institutional_flows`、`credit_transactions`（官方回覆該日無資料）及 `pit.quarterly_financials`（沒有合格 MOPS 季報 artifact）。

將這份 audit 和最新 append-only 決議合併後，唯讀 Control Center 為 **11 blocked_provenance／2 limited**，accepted 與 downstream 均為 0。兩個月營收 limited row 仍明列 `official_publication_timestamp_missing`、`license_not_accepted`、`downstream_eligibility_none`；`limited` 不代表正式接受。新的 audit 路徑 `p0-source-audit-live-20261024T230559Z.json` 已寫入 User 環境變數 `P0_SOURCE_CONTROL_CENTER_AUDIT`；decision 與 license 路徑也指向現行候選 bundle，供下次 app 啟動讀取。Windows Job 正常排空，無強制清理。原始 audit 和 projection 保存在 visualization workspace，沒有寫正式資料根。

Control Center service 與更新頁 P0 渲染定向回歸 **32 passed**（另 85 deselected）；UI 的 Fallback 欄可直接顯示要求日 10/23、替代來源觀測日 10/22。這是合成／投影回歸，不是 app 重啟後的目視 UAT。

## 範圍

Data Update「檢查數據狀態」在背景 worker 即時執行唯讀的 `inspect_program_readiness`，以七條 lane 投影至面板。明確設定 `PROGRAM_READINESS_ARTIFACT` 時，仍讀指定 artifact；未設定時不要求人工產生 JSON。Formal／ML 使用本次 UTC 檢查時間作 evidence cutoff，不執行訓練或授予 OOS。

## 驗證

| 檢查 | 結果 |
|---|---|
| `git diff --check`（本次變更檔） | 通過 |
| `python -m py_compile app_module/program_readiness_projection.py app_module/pre_v2_readiness_service.py ui_qt/views/update_view.py ui_qt/main.py tests/test_program_readiness_projection.py tests/test_pre_v2_readiness_service.py tests/test_ui_qt_update_view_workbench.py` | 通過 |
| `python -m pytest tests/test_program_readiness_projection.py tests/test_pre_v2_readiness_service.py tests/test_ui_qt_update_view_workbench.py -q -o addopts=` | 133 passed |
| `scripts/qa_validate_update_tab.py` | 25 passed、0 failed、4 skipped |
| `python -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime` | 1,144 source files，無錯誤 |
| `scripts/inspect_program_readiness.py --format markdown --training-as-of 2026-10-24T19:54:25+00:00` | 七條 lane 均有即時結果；總體 `action_required`，Evidence 顯示 legacy `data_path` 越界原因；CLI exit 2 為尚有 Gate blocker 的預期結果 |

Python 驗證均在 Windows Job 中執行：kill-on-close 已設定、Job 記憶體上限 8 GiB、程序上限 12、啟動時可用 RAM 約 24 GiB 以上；每個命令完成後 Job active process count 為 0。`qa_validate_update_tab.py` 的日誌輸出以 `BALDR_UPDATE_TAB_QA_LOG_DIR` 導向系統 TEMP，避開 repo `output` junction 的唯讀限制；QA 本身使用隔離雙根 fixture，不寫正式資料。

## 即時盤點發現（不代表接受 Gate）

- `update_history` 為 `ready`。
- P0 缺最新 live audit 與逐來源授權／用途判斷；Evidence 尚缺 weekly records 與完整推薦／決策證據；Paper ledger／週報不可計算。
- Formal／ML 的 causal portfolio ledger、champion snapshot history、PIT sector membership 三項來源皆缺失，OOS 保持停用。
- Performance baseline 未提供。Runtime 寫入 handle 在本次受限沙箱遭 `PermissionError`；這不能外推成使用者正式主機權限結論。
- Evidence 的推薦 query 拒絕讀取一筆 legacy run：SQLite `data_path` 指向舊 `D:\Min\...`，而目前 runs root 在 `F:\Min\...`；該舊路徑不存在。搬遷定位清冊列出此筆 F 檔案，大小及 SHA 與清冊相符，但 consumer 沒有可接受的獨立 custody pin，因此仍 fail closed。這不是已證實檔案損毀；也不能只把資料列路徑改成 F 槽就視為完成。現在 readiness diagnostic 保留有界原因並遮蔽絕對資料根，供 UI 顯示；要恢復 legacy query，仍須補齊並核驗符合既有契約的原件 custody 證據。

本次補上整體狀態的日常可見性與推薦完整性拒絕原因，不改任何來源內容、Gate、ML 輸出、Paper 帳本、排程或交易權限。市場／Evidence／Formal／Paper 的資料與資格缺口仍須以其原始證據逐項處理。

## 2026-10-25 legacy custody 接線追補（當時未驗收）

已在 saved recommendation query factory 為 `scheduled_rec_20260923_051003` 接上逐筆 custody pin：只接受 candidate `candidate_scheduled_rec_20260923_051003_1101.json`，SHA-256 `3d5784c24ee92257dfa8b9a66955305fc6800c595df4cfc4b53f746b82706e47`、4,337 bytes；仍要求原件路徑、原件 SHA、DB row SHA 與 runs 內 current path 全部吻合。沒有改寫正式 SQLite 或推薦 artifact。

受控聚焦測試輸出 `28 passed`，但該次 Windows Job 結束時仍回報 1 個 active process，違反程序排空條件；因此該次結果不列為驗收通過。後續驗收見下節。

## 2026-10-24 custody 接線驗收與即時盤點

逐筆 evidence pin 已完成 consumer 接線及受控驗證。saved recommendation query 共讀回 121 筆：33 筆 canonical payload/index verified、15 筆 legacy trusted hash verified、73 筆 legacy read-time hash only 並明確標記 research-only。原 88 筆 legacy 清冊沒有被整批提升為 trusted；只有能用獨立 candidate identity、大小與 SHA 固定的項目可進 trusted lane。9/23 的 `scheduled_rec_20260923_051003` 已通過獨立 custody pin；其他缺原始逐筆證據的項目仍留在 audit-only lane。

推薦存在性與 latest 選擇已分開：有保存紀錄但混有無時區 legacy 時鐘時，readiness 現回報歷史存在及 `recommendation_latest_selection_ambiguous_clock`，不再誤報「沒有保存推薦」。這只解除錯誤的缺件判斷，latest 仍不可裁定。

| 檢查 | 結果 |
|---|---|
| custody、legacy projection、saved consumer、readiness 聚焦測試 | 121 passed |
| Windows Job 自然排空 | active process count 0；8 GiB Job memory、12 process 上限已讀回 |
| 修改檔 `git diff --check` | 通過（僅既有 LF／CRLF 提示） |
| 修改檔 `py_compile` | 通過 |
| 全套 mypy | 1,144 source files，無錯誤 |

即時 Evidence lane 仍為 `action_required`：週資料量不足、Why Not payload 缺失、liquidity gate payload 缺失、screening matrix 缺失、latest 時鐘歧義，以及 `formal_credit_not_authorized`。全程沒有放寬這些 Gate，也沒有寫入正式資料。P0 audit、Paper ledger／週報、Formal／ML PIT 與 baseline、runtime／performance 證據仍要靠各自真實 artifact 或操作週期，owner 授權不能替代這些證據。

## 2026-10-24 latest clock 區間比較與七條 lane 重核

修正混合 canonical／legacy 結果的 latest 選取：legacy `created_at` 全部可解析，88 筆中 47 筆含 offset、41 筆無 offset，無缺值或格式錯誤。無 offset 時不猜本機時區，而以 ±24 小時作可能 UTC 範圍；只有候選範圍明確晚於其他所有紀錄範圍時才選取，區間重疊仍回報 ambiguous。此次 10/22 canonical 時鐘與所有舊時間範圍分離，因此選到最新 canonical 結果。

正式資料根唯讀 query 回讀 121 筆：33 canonical、15 legacy trusted hash、73 legacy research-only。Why Not、liquidity gate、screening matrix 各有 116/121 筆帶內容；選中結果 `rec_49453d47e7304e2cb34613df311bb1db` 為 canonical verified，決策日 2026-10-22、資料日 2026-10-20，三項內容筆數分別為 199、184、200。Evidence source-gap read model 的 `blocking_gaps=[]`、`warnings=[]`，先前這些 payload 與 latest clock 的誤報已解除。

完整 `inspect_program_readiness` 仍為 `action_required`，現存 Gate 如下：

| Lane | 現行狀態與阻塞 |
|---|---|
| P0 | 缺 live audit、逐來源 license/use-case/eligibility 決議；來源仍未接受，production scheduler disabled |
| Evidence | 真實 weekly history 不足；`formal_credit_authorized=false` |
| Paper | daily status DB 路徑不一致、Paper 與 benchmark 週報邊界不一致、週報不可計算 |
| Formal／ML | causal portfolio ledger、Rule Champion snapshot history、PIT sector membership 缺失；OOS disabled |
| Runtime | 本次環境的 config log 與 research DB 寫入探針回報 PermissionError；不能外推為正式主機權限結論 |
| Update history | `ready` |
| Performance | technical 與 broker performance baseline 未提供 |

最新修正驗證：saved consumer／readiness 聚焦測試 **45 passed**；修改檔 py_compile 通過；全套 mypy **1,144 source files，無錯誤**；Windows Job 自然排空 0，read-only audit 未寫正式資料。Weekly review、source/license lineage、Paper fills、Formal PIT 三項輸入及 performance measurements 都需要真實 artifact 或自然操作週期；沒有把 owner 對產品方向的授權轉成這些證據的替代品。

## 2026-10-24 Owner 授權後的 Gate 分流

Owner 已授權清除可由產品政策決定的阻塞；Roadmap §21 記下的 Guided 保守預設、Paper CSV 契約、官方來源優先／不購買付費資料、scheduler 啟用條件及 ML promotion 條件均已有決定，不應再把它們列成「等 Owner 點頭」。現有 `formal_credit_authorized=false` 也維持保守預設；未找到需要 Owner 現在另選的策略決定。這不會把融資／槓桿風險資料的授權假設成已核准。

| 阻塞 | 類型 | 可由程式直接解除嗎？ | 下一個實際出口 |
|---|---|---|---|
| P0 來源逐筆品質、授權、PIT 與 coverage | 外部來源證據 | 否 | 以官方來源原始回應、license/use-case、可得時間及完整性證據完成逐來源審查。本環境最近的 bounded 官方 probe 遇 DNS 名稱解析失敗，沒有形成 live audit；不把它記為來源拒絕或接受。 |
| 三個真實 weekly review period、三個操作日 evidence、恢復演練 | 時間／操作證據 | 否 | 按已定政策累積真實週期與演練收據後，產生 approval artifact；不能用回放補週期。 |
| Paper 帳本不可計算 | 真實帳戶輸入 | 部分 | Paper 匯入程式契約已選定；需當前 snapshot 及實際 fill CSV 才能 append-only 匯入並核對週報，不能從舊 baseline 推測持倉。 |
| Formal／ML 三份輸入缺失、Gate 7 OOS 關閉 | 真實 PIT／clock lineage | 否 | 依 prospective-only contract 建立新 clock-bound portfolio ledger、champion history、PIT sector membership，再逐項 exact-readback；目前設定路徑指向不存在的舊 artifact。 |
| Runtime 寫入探針 PermissionError | 執行環境權限 | 否（在此沙箱） | 在正式 Windows 主機受控核對目標路徑 ACL 與 handle；沙箱拒寫不能當成正式主機的失敗或通過。 |
| Technical／broker performance baseline 缺失 | 實測證據 | 否 | 需實際執行同一口徑的 baseline 並保存原始紀錄；不可用程式測試或合成樣本取代。 |

截至這次重核，已能清除的 latest-clock 歧義、推薦缺件誤報及 readiness 需手動提供 artifact 的介面問題均已修復。其餘 blocker 不是待 Owner 再批准的產品選項；是目前缺少上述資料、可執行環境或自然週期。因此不會把 Gate 標成通過，也不會以刪除檢查條件製造「完整」狀態。

## 2026-10-24 Paper 狀態路徑遷移核對與重驗

Paper status 收據可能保留舊磁碟路徑。readiness 與 Decision Desk 現在只在 `status=passed` 且 snapshot ID、日期、現金、總值都和目前明確選定的 snapshot 完全一致時，將路徑差異降為 `paper_daily_status_state_db_path_rebound_by_snapshot_identity` warning；缺欄位或任何值不符仍保留 `paper_daily_status_state_db_path_mismatch` blocker。沒有改寫 status、snapshot、benchmark 或成交 ledger。

正式資料根唯讀 readback：snapshot 27 筆，2026-07-12 至 2026-09-07；Equal Weight benchmark 21 筆，2026-07-12 至 2026-08-28；Paper trade cost ledger 不存在。路徑差異現已由 snapshot 身分核對，不再是 blocker；目前 Paper blockers 為 `paper_weekly_report_boundary_mismatch` 與 `paper_weekly_report_not_computable`。基準落後 snapshot 末日，且缺真實成交成本列，故不能生成可比的成本後週報。

| 驗證 | 結果 |
|---|---|
| Paper readiness／Decision Desk 定向測試 | 30 passed |
| 修改 Python 檔 `py_compile` | 通過 |
| 全套 mypy | 1,144 source files，無錯誤 |
| Windows Job | 8 GiB／12 processes 上限讀回；測試、編譯、mypy 與唯讀 readiness 子程序均自然排空到 0 |

這只解除已由明確 snapshot 身分證明的舊路徑誤報。Paper 的週界與成交成本仍須真實輸入；Formal、ML、來源接受資格均未因此改變。

## 2026-10-24 Paper 證據日期範圍呈現與回歸

Portfolio Paper readiness 主摘要先前只列 snapshot、benchmark、成本帳筆數，未並列覆蓋日期，容易漏看筆數不同期間的邊界問題。現在摘要與展開診斷會分別呈現三者的日期範圍及筆數；空成本帳顯示「無成交紀錄」，日期缺一側時只標示可知的一端，不用其他 ledger 補值。此改動只調整唯讀畫面和說明，不寫入 snapshot、benchmark 或 fill ledger。

| 驗證 | 結果 |
|---|---|
| Paper 日期區間／readiness／fill import UI 定向案例 | 6 passed、102 deselected |
| `tests/test_ui_qt_update_view_workbench.py` | 90 passed |
| `scripts/qa_validate_update_tab.py` | 25 passed、0 failed、4 skipped；使用隔離資料與 TEMP 日誌 |
| 修改 Python 檔 `py_compile` | 通過 |
| 全套 mypy | 1,144 source files，無錯誤 |
| 成功受控 Job | 記憶體 8 GiB、程序 12 上限讀回；active process count 自然排空至 0 |

較廣的 `tests/test_ui_qt_portfolio_view.py -k paper`（10 個案例）執行 10 分鐘沒有終止輸出，root 中止該輪；它不列為通過，也沒有可採用的部分通過數。一次較早的受控定向輪因測試斷言未更新而失敗，修正斷言後以上述單一定向案例重跑通過。完整 Portfolio UI regression 尚未驗收。

### UI 呈現與 QA 批次範圍

Paper UI 的兩個定向案例（身分遷移 warning、未知診斷原碼保留）為 **2 passed**；`tests/test_ui_qt_update_view_workbench.py` 為 **90 passed**；`scripts/qa_validate_update_tab.py` 為 **25 passed／0 failed／4 skipped**。修改檔 `py_compile` 通過，全套 mypy 為 1,144 source files、無錯誤；各個成功的受控子程序均自然排空至 Job active process count 0。

另一次把 Paper services、完整 `tests/test_ui_qt_portfolio_view.py`、更新頁與 readiness projection 合併執行的 pytest 在 1,200 秒到時只完成約 30%，被同一受控 Job timeout 終止；該輪不列為通過，timeout 清理後 Job active count 為 0。故完整 Portfolio UI regression 尚未驗收；本次只接受上列定向 Paper UI 案例及更新頁 QA 結果，不外推到整個 Portfolio view。

## 2026-10-24 Paper Equal Weight 連續日期更新

Paper Equal Weight 原本只有「建立新 ledger」流程；snapshot 持續累積後，既有 benchmark 會固定落後，UI 也沒有可安全補齊的操作。現在更新預覽會以 baseline、全部目前 snapshot 日期與因果 T-1 市價完整重算，並將既有 ledger 與重算結果逐列比較。只有既有列是精確前綴時，確認後才追加缺少的連續尾段；中間缺行、舊列不一致或輸入在預覽後改變都 fail closed。新增後會唯讀回讀並要求全帳本等於重算結果。UI 顯示已核對筆數、待追加筆數及日期範圍；沿用 readiness 所選 personal-store route，避免更新按鈕繞過個人資料庫路由。沒有覆寫 snapshot、baseline 或市場資料，也不會下單。

| 驗證 | 結果 |
|---|---|
| Equal Weight builder／UI 更新定向案例 | 7 passed |
| 個人儲存路由的 exact-prefix 追加整合案例 | 1 passed |
| Paper 日期範圍、readiness 與 fill import UI 定向案例 | 6 passed、102 deselected |
| `tests/test_ui_qt_update_view_workbench.py` | 90 passed |
| `scripts/qa_validate_update_tab.py` | 25 passed、0 failed、4 skipped |
| 改動 Python 檔 `py_compile` | 通過 |
| 全套 mypy | 1,144 source files，無錯誤 |
| 成功受控 Job | 8 GiB memory、12 process 上限讀回；active process count 自然排空至 0 |

完整 `tests/test_baldr_personal_paper_producers.py` 在允許的隔離輸出根執行為 **31 passed、22 failed、3 skipped**；22 個可見失敗均在測試 fixture 建立硬連結時遭 sandbox `os.link` WinError 5 拒絕，故整套測試不能列為通過。使用可寫的外部暫存根後，先前受路徑隔離影響的 CLI 案例另行 **1 passed**，個人路由更新整合案例亦 **1 passed**。`tests/test_ui_qt_portfolio_view.py -k paper` 的較廣測試先前因 10 分鐘無輸出而中止，不列為通過；完整 Portfolio UI regression 仍未驗收。

這解除的是 benchmark 無法隨 snapshot 增長的程式操作缺口。正式資料根仍只讀；實際 Paper 成交成本 ledger 尚無成交列，因此成本後週報仍不能計算。來源接受、weekly／操作週期、Formal／ML PIT 輸入、正式主機 Runtime 權限及效能 baseline 仍須各自真實證據，沒有因 UI 或更新流程而改變 Gate。

## 2026-10-24 P0 即時盤點與 readiness 輸入接線

為避免沿用前一日狀態，本次以 2026-10-23 最近交易日執行 bounded 官方唯讀 P0 audit，並在同一受控程序把當次 audit 與已通過的 Runtime staging probe 傳入整體 inspector。12 個映射官方 endpoints 均在此執行環境 DNS 名稱解析失敗（`getaddrinfo failed`），共 12/12 個 P0 source rows 記錄 `network_probe_failed`、0 accepted rows；第 13 項 MOPS quarterly financials 缺少 candidate artifact。這證明本機環境沒有取得來源回應，不證明官方 endpoint 服務中斷、資料不存在或資料品質失敗；沒有接受任何來源。

同次整體 readiness 的現況為：P0 `action_required`（來源／授權／decision 仍未接受）；Evidence `waiting_for_external_input`（weekly history 不足、formal credit 未授權）；Paper `partial`（週報邊界不一致且缺可計算成交成本）；Formal／ML `action_required`（三份 clock-bound PIT inputs 缺失，OOS disabled）；Runtime `partial`（staging transaction 通過，正式 `config.log` 與 Research Registry handle 在本 sandbox 仍 PermissionError）；Performance `waiting_for_external_input`（兩份 baseline 缺失）；Update history `ready`。即時結果只說明本次所見，不授予排程、formal、ML 或交易資格。

另修正 Data Update live readiness 的輸入接線：P0 audit、license candidate 與 owner decision 若已明確設定，現在會一併傳入總體七 lane inspector，和同頁 P0 Control Center 使用同一組 artifact。先前即時檢查只載入總體 readiness 時會漏掉這些設定，錯把 P0 檔案顯示成未提供。明確整體 readiness artifact 仍優先；UI 盤點不發出 P0 網路請求。

| 驗證 | 結果 |
|---|---|
| bounded official P0 live audit（2026-10-23 decision date） | 12 個官方 routes 均 DNS failure；13 source rows 包含 12 network failure 與 1 MOPS candidate artifact missing；未接受來源 |
| Runtime ephemeral file／SQLite registry transaction／rollback | passed；cleanup passed；只代表 visualization staging，正式路徑仍拒寫 |
| P0 artifact 轉交 readiness 的更新頁回歸 | `tests/test_ui_qt_update_view_workbench.py`: 90 passed |
| `scripts/qa_validate_update_tab.py` | 25 passed、0 failed、4 skipped |
| 修改檔 `py_compile` | 通過 |
| 全套 mypy | 1,144 source files，無錯誤 |
| 受控 Job | 8 GiB memory、12 process 上限讀回；每個成功命令結束後 active process count 為 0 |

`document_control init-task` 未能建立本多階段 goal 的 ignored task record：工具判定 repo `output` 儲存根不可讀（該路徑是指向 BaldrStorage 的 junction）。沒有改寫舊 task 或改用其他目錄冒充標準 task 狀態；goal 與接手狀態保留在本對話及此 QA 收據。其餘產出沒有寫入正式資料根。P0 live audit JSON 受工具政策限制只落在 OS TEMP，不作為持久來源接受 artifact。

## 2026-10-25 MOPS 現有原件與 P0 candidate 資格重核

重新盤點 `DATA_ROOT/output/current-mops-statements-4440adafdc72458b8018147b3106b2b8`：其中有 `current-mops-statements-update.v1` receipt、六份 TWSE／TPEx 季報回應 HTML、正規化列及原始 SQLite before-image。receipt 記錄 `2026-Q2`、1,976 家、83,606 筆正規化列、六個 HTTP 200 回應；receipt SHA-256 為 `cee2fb170c22cd4351c4ce968cf87f74af958fd28adb7b2d2f71bac137e318e5`。

這批現有資料明確標記 `historical_pit_eligible=false`、`issuer_denominator_complete=false`，而六份回應只記錄此次擷取時間，沒有可供逐報表核驗的官方上傳時間。它證明本機有 current-restated 季報研究資料，不符合 P0 季報 candidate 所需的公告時間／可得時間與完整母體契約；不能把它改包成已驗證 PIT artifact。P0 audit 所需的合格 MOPS quarterly candidate 仍缺，Formal／ML PIT 仍不通過。

同日重新查詢 `www.twse.com.tw`、`www.tpex.org.tw`、`data.gov.tw` 的 DNS 均失敗（Windows `Resolve-DnsName` 回 `Win32Exception`），因此本次沒有重跑 bounded official audit，也沒有把 DNS 失敗解讀成來源無資料或拒絕。全程只讀既有 receipt／檔案 metadata 與 DNS；沒有開啟 SQLite before-image、改動正式資料或建立新 artifact。

## 2026-10-24 TPEx 月營收 machine-evidence producer

補上 TPEx 月營收的 machine-evidence producer，採用 data.gov.tw dataset 56510、TPEx 官方 OpenAPI `mopsfin_t187ap05_O`，並以 TPEx 當前上櫃清冊 `mopsfin_t187ap03_O` 獨立核對 coverage。coverage 依官方 `DateOfListing` 對齊月營收報告日；若當前清冊含報告日之後才上市的公司，會留原始家數、逐筆排除清單與日期。data.gov.tw metadata 指向的通用 TWSE Swagger 與 TPEx endpoint Swagger 分開驗證；OpenAPI 3 `servers` base URL 會映射至精確 endpoint path。一次 bounded Swagger response 的字串值含無效 `\u` escape；解析器只將該字串內容當 literal 修復，留下 raw Swagger bytes/hash，記錄修復數，並仍要求 endpoint path 精確存在。正式成功 run 的 repair count 為 0。

TPEx 使用條款頁尾有每次變動的 Cloudflare challenge script。license capture 以 HTML 可見文字 NFC 指紋比對條款版本，同時保留每次原始 response SHA-256、byte count、Last-Modified 與 final URL，不保存頁面正文。兩次唯讀請求的可見文字指紋一致：5,225 bytes，SHA-256 `e512db3b3c203fda12e910382e424d7b9418847266058fdabeea7464d5ec3fe0`。Machine policy 明確維持 `legal_acceptance_inferred=false`、`formal_oos_allowed=false`、`production_scheduler_allowed=false`、`redistribution_allowed=false`。

| 檢查 | 實測結果 |
|---|---|
| TPEx machine producer | `machine_verified`；有限決議只允許 `research_shadow`／`diagnostics` |
| 官方月營收資料 | 報告日 2026-10-17；893 raw、893 accepted、0 quarantine、0 blocked；quality 10000 bp |
| TPEx 獨立清冊 coverage | 原始清冊 894 家，日期 2026-10-24；893 家在 10/17 報告日已掛牌。代號 2249（湧盛電機）於 10/22 才掛牌，明確列為未來掛牌排除；報告日成分 coverage 為 893／893（10000 bp），沒有缺列 |
| 時間／PIT | `first_observed_at`；沒有證明官方發布 timestamp 或歷史可得時間 |
| OpenAPI | raw Swagger hash 已綁定；精確路徑 `/mopsfin_t187ap05_O` 存在；invalid Unicode escape repair count 0 |
| 聚焦回歸 | producer、license capture、source governance 共 20 passed；修改的 5 個 Python 檔 `py_compile` 通過 |
| Machine evidence envelope | `sha256:d48e8722a8a7db473433eb5112df2995b66bb5f0eb3f4c1052c72c3b00c03e97`，candidate artifacts 位於 OS TEMP：`C:\Users\archi\AppData\Local\Temp\baldr-tpex-p0-mb7afdaj` |

此結果補上 TPEx 當前月營收的一條 machine evidence 路徑，沒有把 machine scope 當成正式 source acceptance，也沒有寫入正式資料根或啟用排程。清冊是 10/24 現況再依上市日回看 10/17，無法補回 10/17 之後已下市公司的歷史名單，故仍不構成完整歷史 PIT 分母。全體 13-source P0、逐來源具名接受、正式 OOS、其他來源的質量／PIT 與 production ingestion 仍須各自證據。條款的機器指紋通過不代表法律意見或自動推定 Owner 已接受。

## 2026-10-25 TPEx machine evidence 以現行程式重驗

為把已有 machine evidence 落成可讀的限定決議，先以現行 `append_source_acceptance_decision.py` 對保存的 TPEx evidence bundle 執行受控驗證。現行 governance validator 拒絕該 bundle：`machine_evidence_availability_producer_hash_mismatch`、`machine_evidence_pit_producer_hash_mismatch`、`machine_evidence_quality_producer_hash_mismatch`。因此沒有 append candidate registry，也沒有產生有效決議檔；原始 bundle 保留，沒有改寫 producer hash 或放寬 validator。

接著依現行 producer 以限定唯讀請求重建證據，第一個 data.gov.tw metadata 請求遇到 DNS `getaddrinfo failed`，producer 在讀取來源前停止，未寫出新 machine evidence。兩輪都使用受控 Windows Job（8 GiB memory／12 process 上限、suspended assign-before-resume、workspace mutex、起跑可用 RAM 約 30 GiB）；Job 自然排空為 0，handles 關閉、mutex 釋放，沒有強制清理。正式資料根、source decision registry 與排程均未修改。

在該次重驗結束時，TPEx 月營收只能保留為 2026-10-24 當時的 machine-evidence candidate 歷史紀錄，不能顯示成現行 validator 已接受的 limited 決議。其後成功重抓與限定決議見下節；仍不授予 production、scheduler、歷史 PIT 或 ML/OOS 資格。

## 2026-10-25 TPEx 現行 producer 重抓與 limited 決議

後續以受控 Windows Job 重跑現行 machine producer。第一次成功取得端點回應，但 TPEx 清冊 JSON 尾端不完整而被 parser 拒收；第二次 bounded 重試完整取得官方回應，producer 與現行 `SourceAcceptanceGovernance.evaluate_machine_evidence` 均通過。這是新的 live capture，不是把舊 artifact 的 producer hash 改寫成目前版本。

新 evidence bundle：`C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\tpex-monthly-revenue-machine-evidence-20261025\machine_evidence.json`，content hash `sha256:be108ae413aa433bee1a2d04ee8402413a15efc371f2792a23a631717b4f19c2`。報告日 2026-10-17，893 raw／893 accepted、quality 10000 bp、按上市日對齊後 coverage 893／893；2249 於 10/22 才上市，仍列為報告日母體之外。PIT 仍以 10/24 first-observed timestamp 為準，沒有官方發布時間或完整歷史 roster，故不是歷史 PIT 證據。

系統已在 visualization workspace 的非正式 candidate registry append `machine:evidence_policy` 的 `limited` 決議，decision hash `sha256:46de0a8bd85b1a76601c8666c4034adae4ef03aa1bfd5591157564185f46170a`；唯一用途是 `research_shadow`／`diagnostics`。P0 Control Center 唯讀投影為 1 limited、0 accepted、0 downstream eligible；另 12 項維持 contract-only。已設定使用者環境變數 `P0_SOURCE_CONTROL_CENTER_DECISIONS` 與 `P0_SOURCE_CONTROL_CENTER_LICENSE_EVIDENCE` 指向 workspace artifacts，下一次啟動 app 後讀取。這不授予正式來源接受、正式資料寫入、production scheduler、投資 Advice、歷史 PIT 或 ML/OOS。

整條 producer／evaluator／candidate append／Control Center projection 在受控 Windows Job 執行：起跑可用 RAM 約 26 GiB、Job 上限 8 GiB／12 程序、suspended assign-before-resume；程序自然歸零，handles 關閉、workspace mutex 釋放，未強制清理。正式資料根與正式 Registry 均未寫入。

<a id="2026-10-24-gate-續清-p0-官方回應效能基線與-technical-單股-canary"></a>

## 2026-10-24 Gate 續清：P0 官方回應、效能基線與 Technical 單股 canary

Owner 已授權按 Roadmap §21 的保守預設打通工程 Gate。本輪沒有將「已抓到資料」直接升格為 accepted：

| Lane / 證據 | 實測結果 | Gate 結果 |
|---|---|---|
| P0 13-source bounded live audit（decision date 2026-10-23） | 13 項中 10 項取得官方回應但 degraded、3 項 missing、0 項 machine-verified；2 項對指定日回覆 official-no-data，MOPS quarterly artifact 缺少。coverage row count 與 `remaining_blocker` 保存在 OS TEMP audit。 | `action_required`。publication／available time、quality、license 與具名 source acceptance 仍未滿足；沒有開 production ingestion。 |
| 官方條款 candidate capture | TWSE、TPEx、TDCC allowlist 3/3 bounded capture 成功；僅存回應指紋與 keyword flags，沒有保存頁面本文。 | `requires_human_acceptance`，`license_accepted=false`。條款 capture 不是授權決議。 |
| Broker Flow latency | 正式 DB 唯讀觀察 1,210,170 rows、247 dates、51 branches、2,235 stocks；週線 cold 1,842 ms、warm P95 0.363 ms，gate pass；UI heartbeat 1.859 ms。DB SHA-256、size、mtime 前後相同。snapshot quality 為 degraded、warning count 31。 | baseline 已提供；效能過線不代表資料品質過線。 |
| Technical indicator latency | 0050、2330 各讀 500 rows，calculation warm P95 約 6.26／6.37 ms，唯讀、沒有並行或寫入。 | technical read-only baseline 已提供。 |
| Technical worker recovery | 真實計算器 bounded process pool、crash recovery、cancellation、retry、staging CSV／SQLite single-writer integration 9/9 checks 通過；正式輸入雜湊不變，staging cleanup 成功。 | staging worker acceptance 通過，不單獨代表 production enabled。 |
| Broker bounded fetch | 離線 transport 10/10 checks 通過；9 submissions、1 duplicate suppressed、1 retry、7 staged rows；rate-limit 及 parent writer 通過。 | offline contract 通過。 |
| Broker real HTTP | MoneyDJ 對凱基 9200、2026-10-23 lots 單一 GET 成功解析 100 rows；Selenium=0、production write=0。 | real HTTP canary 通過；不授權擴大 fetch，保留來源條款限制。 |
| Runtime host | 受控唯讀檢查在 elevated execution context 下 `DATA_ROOT`、`OUTPUT_ROOT`、log root、Research Registry 全 `ready`；另有隔離 staging file／SQLite transaction／rollback 通過收據。 | `ready`。只讀 handle 與 staging transaction 均通過；沒有宣稱對正式 Registry 執行了 transaction write。 |
| Technical production canary | 修正前單股呼叫曾觸發全表 5,366,575-row materialization 並因記憶體不足失敗；受控 rollback 成功。修正後 0050 一檔正式增量計算成功，11/11 validation 通過；worker process count=1、parent-only writer、worker write=false、db quick check=ok、latest date=2026-10-22、514 rows。 | canary 通過；備份在 `F:\Min\Python\Project\FA_Data\sqlite\backups\technical_indicator_canary_20261024T2158`，維持 worker 上限並等待下一次正式排程觀察。 |

修正 `TechnicalIndicatorJob` 在指定 `target_stock` 時先以參數化 SQL 按股票代號過濾；不再因只重算一檔卻展開全市場表。同步候選基準以維持 production/candidate AST parity。另修 `excluded_daily_price_revision` 的路徑 reparse 檢查：逐段驗證現存元件後，遇到第一個 `FileNotFoundError` 即停止；首次建立 DB 時不再把預期的缺檔當成檢查失敗。focused tests（candidate parity、incremental window、target stock SQL、missing descendant guard、first-source recovery）**5 passed**。較廣 R028 + raw-alias suite **42 passed、23 failed**：三項 R028 gate failure 是 pinned production source hash 尚未按新來源重跑驗收；20 項 fixture failure 是 sandbox 對測試 artifact `Path.resolve(strict=True)` 回傳 PermissionError。不得將整套 suite 寫成通過。修改檔 `py_compile` 通過，mypy 1,066 source files clean，`git diff --check` 無空白錯誤。

目前整體 inspector 中 Runtime 與 Update history 為 `ready`；performance 為 `partial`、無 blockers，待真實排程觀察；P0 仍 `action_required`。Evidence 仍缺自然週期與 formal-credit 授權；Paper 仍需實際 fills；Formal／ML 仍缺 3 份 prospective PIT inputs。這些資料、時間與環境證據不由 Owner 的產品方向授權代替。官方條款指出 TWSE／TPEx 網站資料自動擷取受限制，Government Open Data 授權範圍例外；使用前仍需逐端點核對資料是否落在例外／另有同意，見 [TWSE 使用條款](https://www.twse.com.tw/zh/terms/use.html) 與 [TPEx 使用條款](https://www.tpex.org.tw/en-us/gtsm_disclaimer.html)。

本輪主要 artifacts 位於使用者 visualization workspace；P0 audit 與 license capture 依腳本政策只留 OS TEMP。首次正式 canary 的備份也保留於 formal SQLite backup root，重試使用日期化目錄。沒有刪除或清理任何回復備份。Runtime stale next-action 文案也已修正：host readiness 與 staging transaction 都 ready 時，不再顯示仍待 owner 確認正式 ACL；對應 focused projection／inspector tests 累計 **4 passed**。

## 2026-10-24 Qt 關閉路徑失效物件防護

唯讀檢查既有 `ui_qt_crash.log` 時，找到一筆 2026-10-23 關閉記錄：`app.exec()` 已返回後，排空 Qt deferred delete 的 `processEvents()` 遇到已刪除的 `DecisionDeskView` 而拋出 `RuntimeError`；啟動清理接著呼叫已刪除 `MainWindow.hide()`，再度拋錯並遮蔽前一個收尾錯誤。

`_drain_qt_deferred_deletes` 現在遇到 late queued callback 的失效 Qt 物件時會記錄診斷並停止額外排空；`_cleanup_startup` 遇到已刪除的 window wrapper 時會結束 best-effort 清理，不再重複碰觸該物件。`tests/test_ui_qt_shutdown_coordinator.py` **11 passed**，包含新增的失效 child callback 與已刪除 window wrapper 回歸案例。受控驗證器使用 8 GiB／12 process Job，程序自然歸零、handles 關閉、workspace lock 釋放、source pins 未變。

本次真人桌面啟動未驗收：受限執行環境無法追加寫入正式資料根的 crash log；改用隔離 `DATA_ROOT` 後，主視窗初始化又被沙盒對使用者 AppData 研究狀態目錄的存取限制阻擋。這是環境 ACL 限制，不作為正式資料或 Gate 已通過的證據；未放寬權限、未寫入正式資料庫。

## 2026-10-24 source-candidate 原件與 provenance 分列

以 `scripts/inspect_source_candidate_readiness.py --db-path F:\Min\Python\Project\FA_Data\sqlite\twstock.db --decision-date 2026-10-23` 唯讀檢查正式 SQLite。正式資料庫有三大法人 229,472 列、信用交易 22,163 列、TDCC 4,047 列，但各來源 `accepted_row_count=0`：法人／信用最新資料日為 2026-09-08，所有列缺 `available_date` 且 quality 為 `degraded`；兩表 `observed_at` 都集中在 2026-09-09，晚於其 8/26–9/8 歷史資料日，不能用這次回補時間替歷史資料補 PIT 可得性。TDCC 最新資料日為 2026-09-04，available date 為 2026-09-10，早於其 observation date 的回溯決策因此被 `future_data_blocked` 擋下。三者的原始數值欄位確實存在，原報告卻因所有列都被阻擋，把 `candidate_fields_present` 顯示為空，混淆「原件有欄位」與「欄位可作決策輸入」。

Readiness projection 現分開列出 `candidate_fields_present` 與 `decision_ready_fields_present`，並輸出最新 observation／available 日期與 latest local capture timestamp；Markdown 報告也顯示這些欄位。新增限制文字明示 capture timestamp 不等於來源方 publication time，日期盤點也不等於 freshness pass；所有列缺 provenance 或不符合可得時間時，accepted count 與 decision-ready status 仍維持 0／false。`tests/test_source_candidate_readiness.py` **9 passed**；受控 Job 8 GiB／12 process、自然排空為 0、handles／lock 關閉、source pins 不變。正式 SQLite 全程 `mode=ro`／`query_only`，未寫入、未改變 Gate 或 eligibility。

## 2026-10-24 Owner 全面清障授權的適用範圍

Owner 明確授權總負責者直接完成所有可由 Owner 決定的保守產品政策與可回退工程工作，不必為已授權的政策重複詢問。此授權涵蓋既有 Roadmap §21 決策，也涵蓋在證據已齊時按既有程序提交 Owner 決議；不視為來源方授權、資料品質／PIT 證明、自然週期、正式主機權限、獨立 reviewer 簽核或 ML promotion 證據。

本次檢視沒有仍待 Owner 選擇的產品政策。Gate 2 的 `formal_credit_authorized` 不是單一政策開關：每筆 weekly collection 必須先由具名 owner／reviewer 依原始來源與品質內容審閱，才能發佈 approved projection；目前未審的資料仍維持 pending，不能因全面清障授權而批次核准。P0 來源 acceptance 也要逐來源完成條款、授權、availability、品質與 coverage 審查。上述核准資料不足時，Gate 保持 blocked，並將缺件標成資料／驗證待辦，而不是再標為等待 Owner 決定。

## 2026-10-25 Gate 原因白話呈現與診斷追查

Data Update 的整體 Gate 表格先前在阻擋欄顯示大量原始識別碼（例如 `source_acceptance_decision_missing`），狀態欄也並列 `action_required`，使用者必須先懂內部代碼才能知道下一步。現在表格以中文說明常見 P0、Evidence、Paper、Formal／ML、Runtime、效能與更新歷史原因；進度數字和安全邊界也改為中文。狀態欄只顯示中文，原狀態代碼與完整阻擋代碼保留在 hover 提示，完整 payload 仍由原「使用資格與完整阻擋原因」面板查看。未知的新原因以「其他阻擋原因，請查看完整診斷」呈現，原碼仍可由提示追查。

此改動僅改善缺口分類與可讀性，未變更 readiness 計算、Gate 狀態、下游資格、任何資料或正式權限。使用者手冊與 Feature Map 已同步。

| 驗證 | 結果 |
|---|---|
| `tests/test_program_readiness_projection.py` + `tests/test_ui_qt_update_view_workbench.py` | **102 passed**；受控 Windows Job 自然結束，剩餘程序 0，source pins 未變 |
| `scripts/qa_validate_update_tab.py` | **25 passed／0 failed／4 skipped**；第一次因預設 repo `output/` log 路徑 PermissionError 失敗，改用隔離 log 目錄重跑通過 |
| 全套 mypy | **1,144 source files，無錯誤** |
| 修改 Python 檔 `py_compile` | 通過 |
| `document_control check`：Feature Map 關聯、QA 收據與操作手冊 | 通過；手冊原先指向 repo `output/` 的未登記交接連結，改為連到 repo 內 QA 收據後通過 |
| 真人桌面／主視窗視覺驗收 | **not_run**；本次 offscreen Qt regression 不等於真人桌面驗收 |

pytest 前兩輪分別有 3 個及 1 個舊文案斷言未跟上新呈現；更新斷言後第三輪完整 **102 passed**。未刪除或覆寫失敗輸出。完整產品 readiness 仍依資料、來源與實測證據判定；本次 UI 文字變更不會解除其餘 Gate。

## 2026-10-24 P0 最近可用資料日重抓與 Control Center 更新

使用者已授權採用保守 Owner 決策並完成可回退工程，本次不再詢問已授權政策。為釐清「資料缺漏」是否其實是查詢日沒有資料，使用 8 GiB／12 程序的受控 Windows Job 對官方端點唯讀重抓。第一次取目前 UTC 日 10/24 的來源日線，P0 為 9 degraded／4 missing；改查 10/23 為 10 degraded／3 missing。最後以實際能回傳日線列的 10/22 重抓，得到 **12 degraded／1 missing／0 machine-verified**。

10/22 結果顯示法人 flows 19,151 列、信用交易 1,302 列、TDCC 69,700 列；除權息 77、減資／分割 8、停復牌 1、處置 6、分盤 6、全額交割 10、漲跌停候選 1,383、TWSE 月營收 1,088、TPEx 月營收 893 列。這些是當次官方回應的候選列數，**不是** PIT／授權／完整歷史覆蓋通過。唯一 machine `missing` 的 `pit.quarterly_financials` blocker 是 `mops_candidate_artifact_not_supplied`。10/23 日線查詢時，TWSE T86／MI_MARGN 回 official-no-data；TPEx fallback 實際回傳的觀測日是 10/22，故不能當作 10/23 已有資料。這次結果只支持「較早資料日可取得」，不回填其官方發布時間。

新 audit：`C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\p0-source-audit-last-observed-20261022.json`，SHA-256 `5D0E233BA22567680CA05C5CBD8EED800B3D3CA3EED90AABDC47123E3BAD298E`。唯讀 Control Center 投影：**11 blocked_provenance／2 limited、0 accepted、0 downstream eligible**；兩個 limited 仍僅 research_shadow／diagnostics，PIT blockers 保持。HKCU `P0_SOURCE_CONTROL_CENTER_AUDIT` 已切換至此新 audit；決議與 license 路徑未改，下一次 app 啟動會載入較完整的來源現況。正式資料庫、source registry、排程及 Gate 資格均未更動。

三次受控 Job 均自然排空、剩餘程序 0、handles 與 mutex 關閉，沒有強制清理。直接 sandbox 執行的網路請求曾 DNS 失敗；升權只用於同一個有界唯讀官方 probe，沒有寫正式資料。這一輪沒有把 P0 來源升格：目前已證明的是 12 項來源回應可觀測，PIT／來源方授權／逐源機器品質證據仍須補齊；MOPS 季報原件仍缺。

## 2026-10-25 UTC Owner 授權清障續辦與最新 readiness

Owner 已明確授權解除可執行的 gate 項目。本次以最新完整行情日 2026-10-22 為界，採用保守 formal training cutoff `2026-10-23T00:00:00+08:00`（不包含 10/23 當日資料），唯讀重跑 readiness；此 cutoff 是盤點參數，不代表 ML promotion 或 OOS 授權。

Paper Equal Weight ledger 原有 21 筆至 2026-08-28。先以 `preview_update` 核對既有列為重算結果的精確前綴，並確認只差 6 筆；再由 `commit_update(confirm=True)` 重新檢查來源與前綴，append 2026-08-31 至 2026-09-07，最後完整讀回 27 筆。正式檔案為 `F:\Min\Python\Project\FA_Data\output\paper_portfolio\paper_equal_weight_benchmark.sqlite`。Paper snapshot、成交成本 ledger 與市場 SQLite 均未改。受控 Job 收據：`C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\owned-validation\paper-benchmark-append-update-20261025c\receipt.json`；append／readback 程式保存在同一工作區 `append_paper_benchmark_tail.py`。Paper 的 `paper_weekly_report_boundary_mismatch` 已消失，仍因無真實 fill／成本資料而 `paper_weekly_report_not_computable`。

當時唯讀 readiness（尚未納入下方 MOPS availability 補件）：`C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\final-readiness-20261025.json`。已提供既有 P0 audit／decision、週歷史投影、技術與券商效能基線、Technical canary、runtime host readiness；盤點結果為：

| Lane | 狀態 | 現存阻塞 |
|---|---|---|
| P0 | `action_required` | 當時包含 MOPS candidate 缺件；其餘來源可得時間／發布時間、授權、品質、具名接受、指定日官方無資料及 scheduler/downstream 關閉 |
| Evidence | `partial` | 逐週資料仍需具名 owner/reviewer 審核；`formal_credit_authorized=false`，不得批次核准 |
| Paper | `partial` | 仍缺真實 fills／成本帳，週報不可計算 |
| Formal／ML | `action_required` | 缺 causal non-cash portfolio ledger、formal Rule champion snapshot history、PIT sector membership；`formal_oos_disabled` |
| Runtime | `ready` | 已接入 host-context readiness 收據；不代表正式 registry transaction 已執行 |
| Performance | `partial` | 基線與 canary 已接入；bounded worker production acceptance 仍待具名 review／正式排程觀察 |
| Update history | `ready` | 無 blocker |

這次把未提供 cutoff 的 `training_as_of_required` 改成三項確切缺件；Runtime 的 PermissionError 誤報也因提供正確 host-context readiness artifact 消失。Performance 不再缺 read-only baseline，但尚未接受 production worker。資料授權、PIT、週 evidence、真實 fills、獨立 review 與自然排程不能由產品政策授權替代。

受控 append Job 使用 8 GiB／12 process 上限，程序自然歸零、handles／lock 關閉、source pins 未變。兩次 readiness 檢查是唯讀盤點，依程式以 exit code 2 表示仍有 gate blockers；不是通過的 QA suite。本次未執行測試套件。

## 2026-10-25 UTC Owner 授權後續查核：週期證據內容與 P0 readiness 輸入

依 Owner 最新授權重新核對可由工程或受限來源決議補上的項目。Readiness 以當日 P0 live audit 與兩筆 machine `limited` 月營收決議重新盤點；P0 仍為 `action_required`，不是因缺少 Owner 點頭而可以改標通過。TWSE／TPEx 月營收決議只允許 `research_shadow`／`diagnostics`，`downstream_eligibility=none`、`formal_oos_allowed=false`；其餘來源的官方發布／可得時間、資料品質、授權證據、MOPS 季報 artifact、指定日無資料等阻塞仍在。重算報告：[readiness-p0-reconciled-20261025.md](C:/Users/archi/.codex/visualizations/2026/10/23/01a16afa-5b3f-7692-a5db-8881433773e9/readiness-p0-reconciled-20261025.md)。

另外唯讀重建 2026-10-12 至 2026-10-18 的 Evidence Operations weekly report，結果為 `coverage_only`：`reviews_count=0`、`observations_count=0`；缺 `production_scheduler_approval` 與保存推薦結果，且 liquidity、screening matrix、Why Not payload 缺漏。`write_performed=false`，沒有保存人工 history。這份報告不等同 V2.2 weekly collection 或 ML shadow Gate。

V2.2 週日 collection sidecar 最新列同樣涵蓋 2026-10-12 至 2026-10-18，payload 只有最後交易日 2026-10-16、來源路徑／hash 與 `pending_human_review`，沒有 runbook 要求的 source coverage、dry-run、smoke、warnings 與 blocking gaps。故 Owner 的授權不能用來核准內容尚未被蒐集的週期；目前確認的是 collection producer／approval packet 資料不足，需先補實際週期檢核內容，再走具名 review。這也說明舊 readiness 的 evidence lane 不能靠把 `formal_credit_authorized` 直接設成 true 來解決。

本輪沒有改正式市場資料、週期 history、source registry、production scheduler、Formal clock 或 ML/OOS 權限。

## 2026-10-25 Weekly collection 品質細節與行情原始回應核對

`scripts/collect_v2_2_weekly_evidence.py` 現在唯讀盤點週內每日列數、股票數、重複列及開高低收缺值；缺週資料會失敗，不再拿週前舊交易日冒充成功。Markdown 與 approval packet 列出不完整列及成交股數／筆數／金額，區分「有成交活動但 OHLC 缺值」與「缺值原因未知」。這讓缺口可追查，不做補價、不授 Gate credit；collection 仍為 `pending_human_review`、`source_write_allowed=false`、`formal_credit_authorized=false`。

隔離測試收據 `C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\owned-validation\weekly-activity-coverage-20261025d\receipt.json`：collector、repository 與 approval packet 測試 15 passed；受控 Job 自然歸零、handles／mutex 關閉、source pins 未變。正式 SQLite 僅以 `mode=ro` 讀取；產物與 sidecar 位於隔離工作區 `weekly-collector-live-readonly-20261025b`，沒有更新正式 DB。

2026-10-12..16 的 live coverage 為 5 個交易日、9,813 列、1,980 個觀察股票、0 重複列。15 筆開高低收缺值都已對照同日 `twse.mi_index.daily_price` 官方原始回應；五份 custody receipt 的 SHA-256 分別為 `226fc3b3a900a65d22ee1687c4650f54ae5a8d52415ca8a90d7c198917be73c4`、`2015fa6c00b9bdd8d3f1c1b18f1fb4ec84d92de80d3494bb5210f4e0bed67984`、`d2109036375062aac1189b0f0153a639203660eccf26ce6fa8a4d11cfc32c634`、`545626b3f1aa7f86d02fa157073a869ae4f80655ec996b23315ede410cae8f97`、`e5a2e8aa251e5da12298f5456465bced72641eeeb9a89e89ce84b578eef8a8d1`。每一筆官方原始列均在四個 OHLC 欄回報 `--`，成交活動欄與正式 SQLite 相符；因此這 15 筆是官方未提供 OHLC 的列，並非 collector/parser 漏掉了官方 OHLC。對 K 線／OHLCV 計算它們仍不可用；不能合成價格。1470 與 2910 在 10/16 的成交量、筆數、金額皆為 0，也由官方原始列一致支持。

Live Markdown/JSON：`C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\weekly-collector-live-readonly-20261025b\scheduled\v2_2_weekly_collection\v2_2_weekly_collection_20261018.md`。來源覆蓋分母仍未知，完整市場／凍結 universe coverage 未驗；此報告不代表週報核准、排程批准、來源可得時間／授權接受或 Formal／ML Gate 通過。

後續將 collector 升級為自動驗證同日期 TWSE custody receipt 內層 content SHA-256 及 raw response SHA-256，只比對本週缺 OHLC 股票；無封存、錯 hash 或同日多份互相矛盾的 raw response 時保留未驗證，不猜來源。最新受控 live receipt：`C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\owned-validation\verified-official-week-live-final-20261025i\receipt.json`；讀回數據 `observed_row_count=9,813`、`observed_symbol_count=1,980`、`incomplete_row_count=15`、`official_source_missing_value_rows=15`、`local_projection_missing_official_value_rows=0`、`unverified_missing_value_rows=0`，已驗證 custody 日期為 10/12..10/16 五天。受控測試 `verified-official-custody-tests-final2-20261025j` 為 16 passed，含 tampered raw receipt fail-closed 案例；此前兩次 profile 曾因無效掃描策略被取消，沒有收據且不列為成功。改成按週日期定位並只保存候選 symbol 後，單日 helper profile 約 0.06 秒完成，完整五日 collector Job 約 7.1 秒自然結束。
## 2026-10-25 MOPS Q2 PIT availability 補件

使用 MOPS 官方 EZSearch bounded adapter，限定查詢公告日 2026-08-14、上市市場及固定報表類別 F26–F29。四份完整原始回應均為 HTTP 200，每份各含 1 筆 2330「2026-Q2」公告；公告時間皆為 2026-08-14 13:46:30 +08:00。availability artifact 共 718 event／projection，duplicate、future、invalid 均為 0。原始檔、逐筆 hash、capture manifest 與 P0 audit 輸出保存在任務隔離 workspace；availability artifact SHA-256 為 `D7045DD40656F57A8AE97122C3B896FA070F6CFB2F94A172C057717BF72D0CB9`。

將該 artifact 傳入 `run_p0_candidate_audit.py` 後，`pit.quarterly_financials` 從「candidate artifact 未提供」改為 `machine_status=verified`、`pit_status=pit_date_verified`、`evidence_status=candidate_artifact_verified`，row／accepted counts 為 718。另以官方 t57 頁取得 2330 2026-Q2 consolidated PDF（9,323,383 bytes），PDF 可讀且封面身份相符；它未經完整數值抽取、逐表核對或 coverage 評估，因此不把 PDF 宣稱為已驗證財務數值資料集。

**來源接受／使用限制：**目前 artifact 證明公告可得時間及候選索引品質，不代表已完成來源授權審查、數值資料品質、歷史母體 coverage 或具名 source acceptance。決策能力仍限 `research_only=true`、`formal_oos_allowed=false`、`production_scheduler_allowed=false`、`downstream_eligibility=none`。Owner 已授權我代行可決的工程與產品政策決定；此處不是產品政策未決，而是授權條款與數值證據尚未提供。故不自行宣告 legal acceptance 或擴大財報用途。

授權證據核對參考 TWSE 官方資料說明：公開資訊觀測站供投資人自行查詢，另有提供資訊公司即時取得資料的主動派送服務；TWSE 亦將其交易資訊使用管理辦法、契約與收費列為獨立規範。這些頁面沒有確認本次 MOPS 季報批次擷取、持續留存及研究使用的具體權限，因此仍不能以公開可查推定授權已通過。[TWSE 資料服務說明](https://www.twse.com.tw/zh/products/information/history.html)、[TWSE 交易資訊使用規範](https://www.twse.com.tw/zh/products/information/use.html)。

Capture manifest 將 `maximum_requests` 摘要錯寫為 3，實際執行是 adapter 固定四項 F26–F29，全數成功，未重試或額外擴大請求。以 `capture-manifest-correction.json` 追加更正，保留原 manifest bytes/hash 不變。P0 audit 與輸出位於 `C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\p0-source-audit-mops-availability-20261025.json`；本輪未執行測試套件，也未寫正式 DB、candidate registry、scheduler 或 ML/Formal/Paper 路徑。

為使下次啟動載入新候選狀態，使用者層級 `P0_SOURCE_CONTROL_CENTER_AUDIT` 已更新並讀回指向上述 JSON；目前開啟的 app 尚未重啟或做目視 UAT。此設定只切換 UI 的唯讀 audit artifact，不會接受來源或授予 Gate credit。

## 2026-10-25 MOPS availability 後 readiness 重核

將上列最新 P0 audit 代入完整 `inspect_program_readiness` 輸入後重跑；輸出為 [final-readiness-mops-availability-20261025.json](C:/Users/archi/.codex/visualizations/2026/10/23/01a16afa-5b3f-7692-a5db-8881433773e9/final-readiness-mops-availability-20261025.json)，受控執行收據為 `C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\owned-validation\reconcile-readiness-mops-audit-final-20261025d\receipt.json`。完整輸入保留 weekly approval projection、technical/broker baselines、technical canary、runtime readiness、P0 decisions 與既定 cutoff；只替換 P0 audit。Inspector exit code 2 表示整體仍有 action required，不是執行失敗。

這次重核移除了 `mops_candidate_artifact_not_supplied`，沒有把 MOPS 提升為 accepted source，也沒有打開 downstream。最新 lane 狀態仍為 P0 `action_required`、Evidence `partial`、Paper `partial`、Formal/ML `action_required`、Performance `partial`、Runtime `ready`、Update history `ready`；P0 仍有授權、publication/availability time、source acceptance、指定日無資料及 scheduler/downstream 關閉等阻塞。正式資料與 Gate 狀態未寫入或變更。

## 2026-10-25 舊週 Evidence 待審提示修正

現行 Workbench 實際讀到 17 筆舊 sidecar rows；唯讀檢視顯示它們均指向不存在的 D 槽來源，而且 payload 都沒有 `source_coverage`。因此這些列無法靠 Owner 核准補成可審資料。`PreV2ReadinessService` 現在以唯讀查詢辨識 source／coverage 可審性並只輸出彙總數；當 pending rows 全部缺來源或 coverage 時，下一步改為以目前資料源重新收集，且明示 Owner 核准不能補出資料。Workbench 摘要同樣顯示「17 期舊週收集缺可核來源或 coverage，需重新收集」，不再把它列成等待 Owner 點頭。Sidecar rows、正式行情 DB、approved projection 與使用者環境設定均未寫入。

使用 bounded runner 對現行正式 sidecar 做唯讀 readiness 執行，並以 `py_compile` 編譯兩個變更 Python 模組；結果為 readiness `ready`、既有 approved history `3/3`、pending rows `17`、其中不可審閱 `17`（來源不可讀 `17`、coverage 缺漏 `17`），Workbench summary 已呈現重收提示。Job 剩餘程序 0、handles／lock 已關閉、source pins 不變。此次未新增或執行測試套件，亦未重啟 GUI；因此只驗證服務與摘要組合，不宣稱完整視窗 UAT 通過。收據：`C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\owned-validation\weekly-reviewability-live-inspection-final-20261025\receipt.json`。

`document_control.py check --context-metadata` 結構檢查讀取 12 features／39 link sources，但以 exit 2 回報 103 個既存／外部引用問題，主要是 junction `output` 權限拒絕與既有失效錨點；本次新增 Workbench／manual 關聯及新 QA 錨點未出現在錯誤清單。未清理其他歷史文件引用，避免把本次 scope 擴成全文件治理修復。

## 2026-10-25 推薦快照空結果時鐘修正

排程 `baldr-recommendation-snapshot-daily` 最近一次正式紀錄失敗：`ValueError: postprocess capture 缺少同次 available_at 或 decision_at`。根因是非個人化推薦路徑只在有候選列的成功分支才設定 `decision_at`；空候選提前返回仍有來源可得時間，但缺決策時間，故 postprocess 拒收。

`app_module/recommendation_service.py` 現在在來源讀取後就記錄帶時區的 UTC 決策時間並寫入同次執行上下文；後續有候選時仍由實際產生候選的時間更新。使用唯讀正式來源、task workspace 輸出及 `PROFILE=prod` 啟動 shim 的 bounded 隔離重跑已自然結束，runner 回執 `passed=true`、return code 0、Job 剩餘程序 0、source pins 不變。snapshot status=`passed`、`writes_evidence_db=false`。200 個掃描列中 4 個形成候選、172 個因成交量門檻排除、22 個策略篩選無訊號、2 個列為缺資料（1516、1541）；因此 `why_not_payload_rows=196` 是未形成候選 payload 的列數，不是 196 個資料缺漏，`snapshot_cohort_partial_source_coverage` 對應這 2 個缺資料列。排程狀態 UI 的 canonical cohort 分類顯示器已將上述分類分開。輸出在 task workspace `recommendation-snapshot-live-isolated-confirm-20261025`，收據為 `owned-validation/recommendation-empty-clock-confirm-20261025/receipt.json`。此隔離成功不等於正式排程已補跑或日常執行已修復；尚未重跑完整測試、未重啟 GUI。變更模組已通過 `py_compile`。

同日已把 `baldr-v2-2-weekly-collection` 排程重新登錄並讀回 Enabled/Ready，下一次為 2026-10-25 18:00 Pacific；上一次 10-18 結果碼 1。本次未觸發正式收集，須以該次實際 status／coverage 再判 Gate。舊週正式 sidecar 17 筆不可審紀錄仍需重新收集，不能由 Owner 授權代替證據。

## 2026-10-25 TWSE 臨時休市公告接線與資料日重判

10/24 Quick Update 將 2026-10-23 視為官方無資料查詢日，年度 holidaySchedule 又把它列為計畫開市；這造成缺少臨時休市證據的日曆矛盾。TWSE 官方 newsList/detail bounded discovery 現已取得公告標題「臺灣證券交易所集中交易市場115年10月23日休市一天」，publication time `2026-10-22T12:10:00+00:00`，newsList SHA `sha256:9c3c9c8964c2b2bd00eda402f5f8851563d7e00fcfcbae03e371940bebdc4679`、公告 detail raw SHA `sha256:0ee4c564cac1659a6255e287e20d58bbaa780436bbd7af7e97615b8ca0668fb9`。cache SHA `sha256:39562938315520005bb8242f2cbc0d123f062ab63d3fc40c303e5fe4947a442` 已經過 hash-bound loader 驗證，並以 create-only 加到 `output/paper_execution_eod_replay/calendar_cache/twse_temporary_closure_20261023_0ee4c564cac1659a.json`；不改年表原件、行情 DB、Evidence DB、Paper ledger 或 Formal clock。

`run_daily_data_update_quick.py` 現於日曆解析前呼叫既有 `refresh_twse_temporary_closure_events`，把 discovery 結果和錯誤寫入 running/final status；default `OfficialTradingCalendar` 也讀同一 calendar cache。網路受阻、部分失敗或 cache 缺失時保留明確 warning，不把未知當無臨時休市。bounded resolver readback 以實際 `_calendar_for_run` default 路徑驗證：10/23 closed reason=`twse_temporary_closure_official`，10/25 向前選取最近已開市日為 10/22（10/26 年度年表補假，10/27 開市）。對照 [TWSE 官方休市公告](https://www.twse.com.tw/rwd/zh/news/newsDetail?id=8a8216d6a0fa351b01a1638507a10203)、[TWSE 天然災害休市規則](https://www.twse.com.tw/zh/clearing/suspended.html)、[TWSE 年度開休市表](https://www.twse.com.tw/holidaySchedule/holidaySchedule?queryYear=115&response=html)。

受控 runner py_compile 與 resolver readback 均通過，runner Job／handles／lock 已乾淨；未執行正式 Quick Update（其會寫行情 DB）、未跑測試套件或重啟 UI。正式 scheduler 的下一次實際執行仍須讀回同次 status，確認 discovery 與市場資料步驟結果；10/24 舊 status 不會被回寫成成功。

## 2026-10-25 weekly approval packet 缺件分類修正

`app_module/evidence_weekly_approval_input.py` 先前以是否填入 owner／reviewer 名稱決定 packet 是否 `ready_for_human_review`，沒有把歷史 pending row 缺 `source_coverage` 視為不可審。現在逐筆建立 `reviewability_status`：pending row 缺 coverage 或 coverage status 時為 `recollection_required`，review 欄同步標記重收；coverage 存在者只列為 `reviewable_candidate`，仍不是核准。collection failure 與無 pending record 也有獨立 packet status。若 packet 內有任一需重收列，整包不會再顯示可送人工審查；JSON 與 Markdown 會列出數量、週期及缺件原因。

本修改沿用既有 source coverage 欄位，沒有回填或改寫歷史 sidecar；`formal_credit_authorized=false`、`production_scheduler_allowed=false`、`downstream_eligibility=none` 不變。bounded `py_compile` 通過，document-control route 分類為 implementation，要求 execution／testing QA／documentation；未執行測試。使用正式 sidecar 的唯讀 CLI 產生 task-workspace packet，讀回 17 筆 pending、17 筆 `recollection_required`、0 筆可審，`packet_status=recollection_required`、`write_performed=false`；sidecar SHA-256 `sha256:78fb7ea950e4613d7718d6a2415d4b52274b258dc3e042445a31e7f9d9d5201c`。候選產物位於 `C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\weekly-approval-packet-live-20261025\packet.json` 與 `packet.md`。桌面 inventory 沒有 Baldr 視窗，因此未做 GUI UAT。Runbook 要求的 scheduler／manual dry-run、smoke 與 Evidence Review dashboard 證據仍未由 packet 收集，這是下一個 producer/attachment 缺口。

## 2026-10-25 正式推薦快照到 Evidence dry-run 鏈路重查

正式 `recommendation_snapshot/latest_status.json` 仍是 10/24 05:10 PDT 的舊失敗，錯誤為 `postprocess capture 缺少同次 available_at 或 decision_at`；同日 05:15 的 `evidence_pipeline_dry_run/latest_status.json` 以 `scheduled_recommendation_status_identity_mismatch` 中止，`pipeline_execution_started=false`，Evidence DB 未寫。這與前述隔離修正通過、但正式排程尚未重跑一致。

為確認能否立即用正式路徑重跑，已先將舊 status／log 原件 copy 至 task workspace，對同一研究 producer 做 bounded 執行；它在 `TWStockConfig` 初始化時受 sandbox 拒絕建立 `output/_test/application_state/logs`，因此未開始推薦計算、未寫 recommendation artifact。正式 10/24 status／log hash 仍與執行前 copy 相同，未覆寫。這次手動嘗試不算修復通過；程式修正要由下一次自然 `baldr-recommendation-snapshot-daily` 排程驗證，並再觀察後續 Evidence dry-run。暫未用升權重跑，以免在同一台灣決策日重複追加推薦 artifact；自然排程狀態仍待核。無交易、Paper ledger、Evidence DB 或正式行情資料寫入。無 Baldr 視窗可做 GUI 驗收。

## 2026-10-25 Weekly collector 週期界線修正與本週來源缺值核對

週排程固定在 Sunday Pacific 執行，而當下台北已進入週一。collector 的預設週期原以執行機台日期直接取值，會把正在開始的新週當成已完成週。現在預設改為依 Pacific 日期回推最近已結束週日，再取該週週一至週日；明確傳入 `--period-end` 的呼叫方式不變。bounded `py_compile` 通過。

排程預設函式的唯讀檢查於 10/24 Saturday Pacific 回傳 2026-10-12..18，符合「最近已結束週日」；10/25 Sunday 排程執行時會回傳 2026-10-19..25。此讀取由 bounded runner 執行並通過，來源 pins 不變。

以正式來源 SQLite `mode=ro`、獨立 sidecar 與輸出目錄重跑 2026-10-19..25。Job receipt `weekly-period-candidate-source-readonly-20261025` 為 `passed=true`、`returncode=0`、`source_unchanged=true`、`handles_closed=true`、`lock_released=true`。結果最後交易日 10/22（10/23 官方休市），4 個交易日共 7,859 列、1,987 個觀察股票、0 重複列；來源覆蓋分母未知，未宣稱全市場完整。16 列缺 OHLC 均由同日 TWSE custody receipt 核對為官方原始值 `--`，無法用價格計算替代。

因此候選結果為 `degraded`／`pending_human_review`，`gate_credit_status=pending_human_review`、`source_write_allowed=false`、`sidecar_append_allowed=true`（僅表示候選可被 append，這次未 append）、`full_coverage_claimed=false`。沒有寫正式 sidecar、正式行情 DB、Gate credit 或 scheduler 狀態。這修正了週期預設錯位，沒有消除本週資料源的 16 列 OHLC 缺值，也沒有讓 weekly approval packet 自動具備乾跑、smoke、warnings、blocking gaps 等附件。隔離 JSON：`C:\Users\archi\.codex\visualizations\2026\10\23\01a16afa-5b3f-7692-a5db-8881433773e9\weekly-current-period-candidate-20261025\scheduled\v2_2_weekly_collection\v2_2_weekly_collection_20261025.json`。本輪未執行測試套件或 GUI UAT。
