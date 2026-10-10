# 2026-10-09 Windows 排程、Codex automation 與最新報告修正

## 本輪結論與授權範圍

使用者已授權修正 Windows 排程、Codex automation prompt，以及最近各排程報告指出的注意與修正事項。本輪在 **2026-10-09 17:49 PDT（2026-10-10 00:49 UTC）** 回讀全部21個baldr Task。21/21存在、啟用、trigger／action／working directory符合目前契約，20 Ready、1 Running。這是設定與回讀證據，不能把18個LastTaskResult0全部當成業務成功。

原晨報截至05:44的Scheduler unknown、G6 running與05:45尚未到期，是該時點有限證據；下表使用較晚的實際結果，不回寫原歷史報告為成功。

## 已完成修正

1. **Windows診斷**：以host唯讀環境恢復21個Task完整查詢；啟用TaskScheduler Operational，由false→true，未清除事件。先前Windows PowerShell5啟用嘗試無收據且仍disabled；改用PowerShell7及診斷收據後成功。舊日期不存在的事件不會補回。
2. **排程稽核程式**：Direct預期時間05:30→10:00，與10/07已套用trigger一致；接受四個已部署固定背景launcher，但精確核interpreter／argv／cwd／task→CMD，不用子字串或舊schtasks文字掩蓋錯配。首次實際CLI回讀發現file入口import缺repo root，已修正並加入外部cwd回歸。
3. **Codex prompts**：透過automation_update更新既有晨報與paper兩個heartbeat，以[共同runbook](../07_guides/BALDR_SCHEDULED_AUDIT_RUNBOOK.md)取代過長、重複與過時段落。05:30／06:20、thread、ACTIVE、通知及其他欄位逐項回讀保持。新規則掃21個Task、辨識sandbox查詢限制、實際四小時G9預算、同次receipt／consumer與精確source roots；相同問題不每天重複通知。
4. **來源路徑**：ML Allocation Forward的休市／config preflight查repository `output/v4_ml_forward_scheduler/latest_status.json`；只有config已載入的child才用config.output_root。原guide指向舊child根，造成讀到10/06失敗；今日正確根的10/10台北休市receipt已驗。
5. **推薦品質說明**：200列中16入選；183 degraded的明確定義是visible but not source-missing，包含153個`liquidity_volume_ratio_below_min`及30個`strategy_filter_no_signal`。1516的1個missing是`total_score_missing_or_nonfinite`。不把183個正常篩選排除都列資料故障。
6. **回讀範圍**：Quick monthly六個artifact及weekly parent／兩children由既有唯讀audit核驗；G6 cycle／registry record／B terminal／model manifest／sidecar、G9 terminal、official wrapper immutable status、Paper EOD gate、Evidence child stdout pins均match。大型snapshot DB／model bundle本輪未重算全量hash；manifest／receipt匹配不代表投資效果或正式PIT。

## 全21個Windows Task最新結果

下表時間都是Windows Pacific本地時間；台北決策日可能已是次日。Result為Scheduler回讀，右欄為producer已保存來源；兩者分開。當輪producer根／SHA完整清冊保存在本機QA，不把raw產物納入公版文件。

| Task（省略baldr-） | Last（PDT） | Result | Next（PDT） | 最新producer報告與注意事項 |
|---|---|---|---|---|
| data-update-quick-daily | 10/09 04:20 | 0x00000000 | 10/10 04:20 | passed_with_warnings；10/08 current，歷史 reconciliation 衝突保留 |
| official-market-events-daily | 10/09 04:50 | 0x00000000 | 10/10 04:50 | wrapper succeeded；三個 child 分列，現況估值仍非 historical PIT |
| data-freshness-check-daily | 10/09 05:00 | 0x00000000 | 10/10 05:00 | degraded；行情 current，正式基本面缺期／來源資格仍不足 |
| ml-raw-pit-refresh-daily | 10/09 05:05 | 0x00000000 | 10/10 05:05 | 外層 blocked_source_revision；07:04 結束，同 run research cycle completed |
| recommendation-snapshot-daily | 10/09 05:10 | 0x00000000 | 10/10 05:10 | 保存 passed；16 入選、153 流動性排除、30 無訊號、1516 總分 missing |
| evidence-pipeline-dry-run-daily | 10/09 05:15 | 0x00000000 | 10/10 05:15 | degraded；工程 errors=0、blocking gaps=0，INSUFFICIENT_SAMPLE；dry-run |
| ml-promotion-evidence-daily | 10/09 05:17 | 0x00000000 | 10/10 05:17 | blocked；formal OOC corporate-action custody pins stale |
| ml-promotion-authority-daily | 10/09 05:18 | 0x00000000 | 10/10 05:18 | skipped_evidence_unavailable；相容 promotion evidence pointer 缺失 |
| ml-allocation-copilot-daily | 10/09 05:20 | 0x00000000 | 10/10 05:20 | skipped_non_trading_day（台北10/09） |
| decision-evidence-capture-daily | 10/09 05:25 | 0x00000000 | 10/10 05:25 | skipped_non_trading_day（台北10/09） |
| forward-outcomes-daily | 10/09 05:40 | 0x00000002 | 10/10 05:40 | blocked／exit2；1538 的 H5 09/17、H10 09/24 價格缺件 |
| recommendation-calibration-learning-daily | 10/09 05:45 | 0x00000001 | 10/10 05:45 | failed／exit1；DailyPriceSourceRevisionError／prospective source 不合格 |
| recommendation-calibration-learning-banktaiwan-shadow-daily | 10/09 05:50 | 0x00000000 | 10/10 05:50 | skipped_non_trading_day（台北10/09），非 upstream 成功 |
| paper-execution-eod-replay-daily | 10/09 06:00 | 0x00000000 | 10/10 06:00 | not_trading_day；immutable dependency gate SHA已核對 |
| ml-direct-chain-maintainer | 10/09 10:00 | 0x00041301 | 10/10 10:00 | running；heartbeat新鮮，v3_downstream_started，fit_completion_verified=false |
| pit-sector-membership-preopen-capture-daily | 10/09 16:00 | 0x00000000 | 10/10 16:00 | skipped_non_trading_day（台北10/10週末） |
| ml-allocation-forward-daily | 10/09 17:25 | 0x00000000 | 10/10 17:25 | skipped_non_trading_day（台北10/10）；當輪 scheduler 根及receipt 已讀 |
| paper-portfolio-daily | 10/09 17:25 | 0x00000000 | 10/10 17:25 | skipped_non_trading_day（台北10/10週末） |
| formal-pit-sidecar-postcutoff-daily | 10/08 18:00 | 0x00000000 | 10/09 18:00 | 上次10/08為台北10/09休市；當輪10/09 18:00尚未到期 |
| v2-2-weekly-collection | 10/04 18:00 | 0x00000000 | 10/11 18:00 | 10/04 core pending_human_review；monthly／quarterly children已驗，待10/11 |
| formal-input-producer-daily | 10/08 21:25 | 0x00000000 | 10/09 21:25 | 上次10/08為台北10/09休市；當輪10/09 21:25尚未到期 |

## 尚未修復的來源缺口與具體處理

| 項目／影響 | 需要的處理與責任角色 | 驗收條件 |
|---|---|---|
| Forward歷史缺價：1538 H5 2026-09-17、H10 2026-09-24；本輪Task結果2 | Data owner核官方原件、證券身分／交易狀態、對應session的close與來源custody，依既有受控來源修復流程處理；不可補平盤、猜停牌或刪event | exact事件／horizon能核有效官方價格或經明確政策接受的不可比較證據，原bounded health缺件解除；不重寫未來價格 |
| G6 formal source revision hold；G9 data／outcome dependency failed；影響正式historical PIT及calibration | Data／ML owner建立revision-aware新來源與新dataset lineage，核`DailyPriceSourceRevisionError`及prospective technical／corporate-action契約；既有current-restated研究成果獨立保留，不修改舊frozen manifest／pin | 下一自然run的source contract與typed terminal完整通過；研究cycle completed不能替formal parent改綠 |
| Promotion evidence的formal OOC corporate-action custody stale；authority缺相容pointer | ML owner以新版本OOC／corporate-action custody重新產生相容evidence與原資格證據；Direct仍執行中，先取得其真正terminal | same-revision manifest/file/canonical events hashes相符及合法release／authority鏈；Task exit0不足以解除 |
| Phase3C歷史reconciliation：本輪09/23、09/29、09/30為35／49／76衝突keys；前次6日期原件亦保留 | Data owner比對舊raw／parser版本／新官方回應與append-only修訂；10/03單一TWSE核驗只證新觀測符合當時官方回應，不證舊版根因 | 提供逐key差異及有來源的版本resolution，保留舊觀測與原失敗；credit10/08 current不解除此項 |
| Formal monthly expected2026-08／actual2026-06；statement expected2026-Q2／actual2024-Q1；availability map缺檔 | Fundamental Data owner取得官方公告、available-at、source hash、revision lineage，依PIT修復runbook先建隔離staging | 正式provenance逐列符合契約／無未來資料；current-observed partial/unverified capture不補造歷史可得日 |
| 推薦1516 total_score缺失或非有限值；1個screening missing | Recommendation owner沿保存result及1516同股來源檢查原score／特徵與provider原因，使用原數值／品質契約 | valid score或明確有來源的不可評估原因；不填0、不把無訊號變推薦、不調低門檻 |
| Direct現有run仍running | 排程／ML owner沿原heartbeat、child custody與實際Task／maintainer預算監測；當輪heartbeat新鮮，fit_completion_verified=false | 同run terminal、原來源與consumer pins完整；不終止或人工重跑取代自然結果 |

這些尚未解除的項目已納入新prompt的具名追蹤與驗收標準，本輪沒有改正式原始資料、補造歷史PIT／交易／thesis、重跑producer或放寬任何資格。

## 正常等待與人工事項

- 10/09台北官方休市、10/10週末：行情最新10/08，以及Paper／Bank／allocation／decision／sector等具有效calendar的skip屬合法結果。ML Forward新根不是舊child失敗。
- TDCC最新10/02，原內部發布寬限至10/13，保持expected_wait；超出寬限時再核其具名來源，不提前報故障。
- Evidence dry-run errors=0、actionable warnings=0、blocking gaps=0、自然INSUFFICIENT_SAMPLE；readiness ready_for_manual_confirm仍不是production_scheduler_allowed。日誌內readiness階段與status最終readiness分列。
- Weekly10/04 core pending_human_review、monthly captured_verified、quarterly captured_with_review；由owner對該collection進行原既有人工review。owner-approved UI projection不授formal credit。
- Paper1418是machine研究seed，不要求使用者補虛構交易或thesis。研究樣本不足／自然outcome未成熟與真正manual user actions分列。

## 驗證、文件coverage與回復

定向pytest **23 passed**，單檔mypy及py_compile通過。實際host稽核為21 available、unknown0、action/schedule/working-directory mismatch均0、configuration_ready=true；21份Task XML／ACL before與after完全相同，沒有手動Run Task。兩個prompt與預期正文相符、其餘TOML欄位保留（只有prompt及updated_at改變）。

Coverage Must：本QA、共同audit runbook、APPLICATION_MANUAL、排程搬機指南、指南README、scheduled README、DOCUMENTATION_INDEX、PROJECT_SNAPSHOT。Roadmap／current與target架構邊界未改；本輪不新增產品Gate或正式權限。

本機證據根：`output/qa/schedule_remediation_20261009`，包含before／after逐Task XML／SDDL、registration_before／after、event_log_enabled、verification、status_before、acquisition、pin_readback及automation_before／after。完整源資料hash與後續其他工作區修改分開；此QA只聲明自身限定核驗，不保證未來run。

回復prompt使用本目錄原完整TOML，經automation_update僅還原prompt並保留當時其他欄位。程式／文件只回復本輪差異，不整檔覆寫其他agent的後續變更。若要停用Operational，以管理員將該日誌enabled設false，不清事件；Task XML／ACL未改無需回復。沒有stage／commit／push。
