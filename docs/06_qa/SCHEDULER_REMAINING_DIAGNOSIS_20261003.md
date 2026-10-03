# 2026-10-03 剩餘排程診斷與信用交易受控恢復

本次範圍為 Windows tasks、Codex operational heartbeat 與資料來源更新鏈路。工作目錄為 `C:/Projects/PythonProjects/technical_analysis`，正式根依 `TWStockConfig` 為 `D:/Min/Python/Project/FA_Data`，Phase3C 隔離根為 `D:/Min/Python/Project/FA_Data_candidate`。本輪沒有修改原任務的 dirty 程式、既有 task 設定或 heartbeat prompt，沒有重訓、交易、stage、commit、push、刪除或停止原工作。

## 已完成的實際結果

| 項目 | 根因與目前證據 | 本輪處理與驗證 |
| --- | --- | --- |
| Windows task 查詢 | restricted sandbox 的 schtasks／COM 無權讀取，不能解讀為 task 遺失 | 06:07:13 UTC 核准的原生唯讀 inventory：21/21 available、action／schedule／working directory 相符、configuration_ready=true；後驗設定仍相符 |
| 10/2 信用交易未更新 | 10/2 Quick 當時 TWSE 回傳 no-data、TPEx 無有效明細；較晚 candidate checkpoint 保存 TPEx transport failure。本輪先遇 DNS，後遇 RemoteDisconnected／IncompleteRead，均為真實網路失敗 | 06:13:58–06:14:20 UTC 使用既有 `update_phase3c_candidates.py` CLI，只更新 `credit`／10/2。TWSE 1297 + TPEx 官方 OpenAPI 919 = 2216 筆；candidate checkpoint SUCCESS。既有 fallback 不需重做 |
| 下游 freshness | 更新前 canonical status 的信用交易實際日期為10/1、expected10/2、stale | 先保存舊 status，再觸發既有 `baldr-data-freshness-check-daily`。06:16:52 UTC 開始、LastTaskResult0；canonical 06:16:53 UTC status 讀回信用交易10/2 current、兩市場 version完整、duplicate0 |
| 三大法人 | 最新10/2的24797筆已存在、兩市場version完整 | 本輪唯讀確認 current；沒有重抓或覆寫。同時保留9/17、9/21–23、9/29–30的歷史 reconciliation conflicts，不能用最新日期正常掩蓋 |
| 集保股權 | 前任務已於23:47 UTC取得10/2週資料4078筆 | 本輪 canonical readback仍current，未重抓。既有週頻判讀保留兩個後續官方交易日的內部grace；它不是官方發布期限，也不證明發行人全集完整 |
| 月營收候選 | Quick core status只保存 `pending_after_core_publication` 和子收據路徑；另份子收據才是結果 | 子收據實際captured，10/2 11:45–11:46 UTC兩次HTTP200保存8月TWSE1086／TPEx892，共1978列與原件。沒有重抓，也不把這個結果寫成formal資料已更新 |
| 季報候選 | Windows action指向`.cmd`；`.cmd`在weekly core成功後呼叫公告／季度兩個獨立research children。單看`.ps1`會漏掉接線 | 已核對接線存在；最新已保存standalone collector為9/30 23:42:57 UTC completed_with_review_items，26 receipts、3960 raw／3952 preview、8 review。不是本輪新執行或自然weekly child驗收 |
| Operational automations | 本機兩個ACTIVE heartbeat先前已修成有限唯讀驗收、來源節奏／同次binding／失敗去重 | 本輪讀回 morning與paper prompt，沒有重做。WP5未恢復；10/3個人提醒仍disabled，未重建 |

### 信用交易資料完整性

- 寫入前用SQLite online backup保存544276480 bytes一致候選DB，quick_check=ok，SHA `17235d968ceb170500a1c39590e0e415972391e3086f62a25001fbf0d489efff`。原credit failed checkpoint另保存於readback；原60筆source observations全部前後相同。
- 兩份成功HTTP原件：TWSE128849 bytes／SHA `106b1a001dc353487bae12852b76ffad8308ef2a3adc69780ecda40d46a8e589`；TPEx550743 bytes／SHA `29d2ff4812b8ca165dd780e753bdaec6ad624212ba45bf9d820f038a29b69852`。
- 獨立用原始JSON欄位與整數重算2216列四個量值，共8864 comparisons全部相符；資料日僅10/2，沒有接受錯日OpenAPI快照。此檢查不另授交易單位、historical PIT或正式資格。
- 全量保護比較：舊credit55406列、institutional595789列、TDCC8104列、institutional history69列、非目標checkpoint77列、原observations60列，各表hash前後完全相同。唯一允許的變動為10/2 credit新列、該checkpoint與新observation。
- 三個實作程式的SHA／大小／mtime前後相同。正式DB3848364032 bytes與mtime未變；本輪沒有做正式DB全量hash前後比較，不外推metadata檢查為全formal資產byte盤點。
- 真實觀測時間為10/3 06:14 UTC，不能倒填成10/2可用或回授歷史訊號。

## 驗證

`tests/test_official_phase3c_fetcher.py` 與 `tests/test_scheduled_data_freshness_probe.py`：**74 passed、1 skipped**，10.24秒。skip為環境條件；pytest cache寫入遭ACL拒絕形成一個warning，不影響測試結果。未修改UI，未執行無關全套或ML訓練。原生App PID44504仍由原第三階段執行，本輪未停止。

原始與修後收據都保存在ignored `output/qa/scheduler_remaining_20261003/`，包含：

- `task_inventory_initial.json`（sandbox unknown，保留失敗）與`task_inventory_native.json`／`task_inventory_after.json`（原生成功）。
- `credit_probe_20261003T060959Z/report.json`（DNS failure）與`credit_probe_20261003T061135Z/report.json`（disconnect／truncated failure）。HTTP entity未完整取得時沒有宣稱有效原件。
- `credit_controlled_20261003T061355Z/{readback.json,independent_verification.json,candidate_before.db,response_00.body,response_01.body,run.log}`。
- `freshness_current.json`、`freshness_after_credit.json`、`freshness_canonical_before.json`／`freshness_canonical_after.json`及`focused_tests.txt`。

## 尚未收口的工程與來源事項

1. **監測 acquisition與qualified consumer分流未完整串接。** Freshness仍將current monthly／statement observations標示`manual source refresh`，沒有讀Quick monthly child receipt或weekly季度collector terminal。這兩列是DB current-observed的狀態，不能直接改為captured／current；應另新增具名research-acquisition lane，綁定run／parent status hash／create-only receipt／raw hash，保留formal與DB consumer各自狀態。`pending_after_core_publication`不能當子程序失敗，也不能當成功。
2. **歷史三大法人真實reconciliation conflicts仍未處理。** 最新10/2 current不解除六個舊日期的值／key衝突。需核對新舊canonical payload與來源修訂，提出保留歷史版本的受控resolution；不能覆蓋舊數值或將FAILED改為SUCCESS。這不是週末未發布。
3. **晚發布恢復目前靠後續Quick retry。** 本輪既有fallback受控實跑成功，沒有永久HTTP520 bug重現證據。是否增設既有task中的限定credit catch-up，須保持single writer、same-date、完整市場、custody與timeout；不能將Freshness唯讀task偷偷改成writer。沒有新增排程或重複producer。
4. **Formal基本面仍缺來源接受。** 正式月營收actual2026-06／expected2026-08、季報actual2024Q1／expected2026Q2；current-observed為8月／Q2但coverage partial。新季度未到公告截止、週末沒有新公布不能被當失敗；上述早已應存在期間的缺口則不能消警告。一般金額unit、issuer coverage、announcement／availability／revision契約未接受，不能以研究候選直接promotion正式歷史PIT。
5. **自然weekly後驗尚未發生。** NextRunTime為10/4 18:00 America/Los_Angeles；已修接線及既有collector證據可判工程，下一次自然來源結果不是本次工程收尾硬門檻。

### 必須協調的精確檔案

原對話仍進行第三階段，且以下檔案為既有dirty／版號pins範圍。本輪未獲可靠的獨占所有權，不直接修改：

- `scripts/scheduled/data_freshness_probe.py`與`tests/test_scheduled_data_freshness_probe.py`：research child binding／狀態分流。
- `scripts/scheduled/run_daily_data_update_quick.py`與`tests/test_scheduled_data_update_runner.py`：晚發布重試與monthly parent-child receipt完整串接。
- `data_module/official_phase3c_fetcher.py`、`data_module/phase3c_backfill_runner.py`及對應tests：必要時credit retry／歷史revision resolution；保留現有完整性防護。
- `app_module/update_service.py`、`app_module/scheduled_evidence_status_service.py`：consumer顯示與canonical來源綁定。
- `docs/00_core/PROJECT_SNAPSHOT.md`、`docs/07_guides/APPLICATION_MANUAL.md`、`scripts/scheduled/README.md`、QA索引：原owner正在整合的文件，應由已協調writer同步本次結果。

安全接手點：先由原owner確認上述資料排程slice移交，再釘目前程式／候選DB／receipt版本；信用交易已current，不再為舊HTTP520摘要重跑。可使用本文件與ignored原件準備最小監測補件，繼續原產品驗收；不得自行停止原對話或App。本輪未停用任何task，無本輪待恢復task。

## 06:41 UTC 追加：獨立修補、逐來源查核與最小協調

本節更新前文的時間範圍。前文「沒有修改 heartbeat」只適用最初診斷；本次後續已修改現有 morning prompt。前文 PID44504 是06:06的歷史觀測，後續程序查詢未再找到該原生App，不代表原對話已停止。dirty本身不能證明原owner正在修改每個列舉檔案。

### 已完成的獨立工程補件

新增 `scripts/audit_scheduled_research_acquisition.py`，沿實際Quick terminal／history binding讀宣告的monthly child；回讀六份候選與原始檔的大小、SHA、來源URL及HTTP狀態，確認市場齊備與formal/PIT禁止旗標。季報呼叫既有公開 `verify_capture_run` 重新查26 receipts、3960 raw及3952 preview，與terminal內readback逐項一致。工具不發HTTP、不更新DB、不觸發producer；輸出另外保存，不覆寫原receipt。

操作範例（PowerShell，在repo根）：

```powershell
.\.venv\Scripts\python.exe scripts/audit_scheduled_research_acquisition.py --quick-status D:/Min/Python/Project/FA_Data/output/scheduled/data_update_quick/latest_status.json --quarterly-terminal output/mops_quarterly_openapi_research/quarterly-openapi-20260930T234142052845Z-f0e035f3ff514fa8a022b08567f8e725/collector_terminal.json --output output/qa/scheduler_remaining_20261003/acquisition_audit_readback.json
```

正式根／Quick路徑須依有效config與wrapper定位；季度範例為本次已保存run，不應永久硬編碼作最新結果。退出0代表指定receipt的研究採集查核完成，季度仍可能`captured_with_review`；退出2代表failed／blocked，需看來源reason。`child_records_parent_sha256=false`與`weekly_parent_binding=not_recorded`都是明列的限制。兩個結果的`formal_database_updated=false`，不得解讀為正式DB已更新。匯入共用模組遇暫時SyntaxError也會保存blocked，不能崩潰後偽裝安靜成功。

06:38:53 UTC實際查核月營收為8月1978列、六個artifact全相符，季報readback全相符。已更新本機 `baldr-scheduled-evidence-morning-report` 的prompt，加入此有限唯讀入口與上述邊界；修改前後原件、CAS檢查與回讀保存在QA目錄。其status=ACTIVE、05:30 America/Los_Angeles規則、target_thread_id與其他欄位未變；paper prompt未改，WP5未恢復、取消提醒未重建。最终TOML SHA `09f88352cf94f120b5c533d4729c8383aa52ce7dff239580f64e076f9960b4fe`。沒有直接UI功能變更。

最終測試：fetcher、freshness及新增audit三份test共 **85 passed、1 skipped（12.09秒）**，停用pytest cache避免本機ACL警告。新增audit的mypy與兩個新增Python檔py_compile通過。新測試包含錯誤父子run、無效父terminal、檔案竄改、路徑跳脫、季度readback變動與非法PIT升格。

### 法人歷史衝突：來源調查完成，但不覆寫

六天各自仍有596／41／32／35／49／76列數值衝突；已排除觀測時鐘欄位，不是單純時間差。外資／投信的買、賣、部分net確實改變；新舊buy−sell=net皆成立，不能用算式成立判定哪版為歷史真相。9/22與9/29另缺00643K，其餘各天缺00636K／00657K／00668K。六份canonical observation的SHA全部有效。

06:35:34 UTC只唯讀抓一次TWSE 9/17官方T86：HTTP200、17977列、2307276 bytes、SHA `76bc0b1621345f3e40706226d31a9bd3392dd0acfbe0cb1641b4b4f01036ca95`。獨立解析九個整數量值與保留的新觀測比較 **161793次全相符**；三個K代碼也存在官方raw。這證明保留的新觀測符合目前官方回應，不足以證明舊版究竟是官方修訂還是早期解析差異；仍須舊raw／parser版本溯源。TPEx歷史量值沒有在此單一TWSE請求中驗證。

原觀測、舊資料與FAILED維持不動；`institutional_conflicts_readonly.json`、官方body與`institutional_twse_20260917_probe.json`保存完整細節。restricted socket失敗後才使用已授權host唯讀查詢，沒有執行producer。

### 三項精確工程缺口與協調範圍

| 缺口 | 檔案與可核對證據 | 影響／最小後續 |
| --- | --- | --- |
| canonical freshness／consumer尚未顯示獨立research acquisition | `scripts/scheduled/data_freshness_probe.py`／對應test未讀monthly child；Quick immutable terminal只宣告路徑。新audit實際已驗到1978列 | morning監測已補上；完整canonical整合仍須移交這兩檔，新增另一lane，保留原formal／current-observed結果。若UI要呈現再協調`app_module/scheduled_evidence_status_service.py`，本輪不需要改UI |
| weekly child與core無逐次強binding | `scripts/scheduled/run_v2_2_weekly_collection.cmd`的兩個call沒有parent run/hash收據；quarterly terminal只證collector自身。wrapper2380bytes，mtime9/30 23:48:23UTC | 能證研究collector與既有接線，不能證它是哪次weekly自然子結果。最小移交為此wrapper及新wrapper test；加入create-only parent/child receipt，不改core pending_human_review／exit語意，不必重跑producer或等下一次自然週期才寫修補 |
| 歷史revision／缺碼沒有版本化resolution接線 | `data_module/phase3c_backfill_runner.py`及對應test；六份CONFLICT與上列官方raw可重算 | 需將已保留observation投影為具真實observed_at的修訂view，保留旧版本與原FAILED；缺碼按新觀測時間追加而非回填歷史可用。先取得此runner移交，不能直接UPSERT舊canonical或授formal PIT |

**實際同檔案變動證據**：信用受控實跑時runner56545bytes／mtime10/2 22:53:33UTC（原SHA見readback）；06:36:47UTC已59879bytes且1077–1078行縮排錯誤，06:37:03UTC改為59930bytes並可匯入，後續85 tests通過。本輪沒有寫此檔，證明有其他writer，但無工具可直接確認它屬哪個對話。不能把暫時錯誤當目前仍壞，也不能依dirty推定所有檔案都被原worker佔用。既有協作API僅本thread的agent tree，沒有跨上述thread送訊接口；沒有讀session或UI繞過。

可直接給原對話的一句移交：**「請將 `scripts/scheduled/data_freshness_probe.py`、`scripts/scheduled/run_v2_2_weekly_collection.cmd`、`data_module/phase3c_backfill_runner.py` 與對應tests的資料排程slice交給新對話，原對話停止修改這些檔案；其餘產品驗收繼續。」** 此處只要求寫入協調，沒有要求停止原工作或程序。

### Formal與自然發布的區分

- 工程／資料缺口：formal月營收6月落後已到期8月、formal季報2024Q1落後已到期2026Q2；研究API unit未明示、statement basis／issuer分母／announcement-revision availability尚未接受，缺安全materialization接線。`mops_materialization_readiness_gate.py`要求registered decision revision、來源identity、coverage及整數金額等契約；不能靠等待週末或把review改approved清掉。使用者／owner仍須決定來源接受與用途，未有證據不能代簽。
- 自然等待：9月營收公告期限未到、2026Q3季報尚未到正常期限、TDCC週頻無新一期、休市no-work，以及10/4既有weekly的下一次自然結果。這些不是目前工程修補的硬門檻。
- 信用與法人最新交易日10/2、TDCC10/2已current；credit晚發布由既有Quick後續重試與本次受控恢復驗證，沒有充分證據再新增另一個writer。仍需未來自然執行觀測，但不聲稱目前全面資料正常。

本輪沒有停用任何task；無待恢復項。QA原失敗（含曾誤指`status.json`而非`latest_status.json`的查核）保留，最終結果另存`acquisition_audit_final_verified.json`與`final_tests.txt`，不覆寫成成功。
