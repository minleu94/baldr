# baldr 排程完整審視與修復（2026-09-29）

## 結論與範圍

本輪審視主機所有 21 項 baldr Windows tasks，而非只讀 09/21 的五項報告。修復已確認的
wrapper／來源契約／監控缺口；不是「全部正式 gate 已轉綠」。原始資料、凍結收據、
既有 dirty paths 與其他工作流全部保留。未重跑正式市場 updater、Evidence confirm、
Paper 舊執行或 ML rebuild，未改 Windows trigger／principal／power setting，未 push。

修正後的唯讀 registration inspector 於 `2026-09-29T21:50:29Z` 回報：21/21 available，
21 個 wrapper 存在、action 與 schedule 全部吻合，`configuration_ready=true`。
另以 Get-ScheduledTask／Get-ScheduledTaskInfo 核對：全部 Ready／Enabled，missed runs=0。
這只證明排程接線；Last Result=0 不證明來源完整、批准、模型效果或 formal closeout。
沒有可重現證據指出 dirty tree 導致本次失敗；已確認的錯誤在來源選取、契約、clock、
監控 inventory 與實際缺件，而不是清空工作區能解決的問題。

## 21 項工作逐項判讀

下表為修補前最新業務產物與本輪處置。時間是 America/Los_Angeles；晨間為 09/29，
傍晚最近執行為 09/28。未改寫舊 status 讓它看起來成功；修正需由下一次合法自然執行驗證。
名稱均有 `baldr-` prefix，表內省略 prefix。

| Task | 時間／Last Result | 最新業務狀態／根因 | 處置或剩餘界線 |
| --- | --- | --- | --- |
| data-update-quick-daily | 04:20／0 | 主 run passed_with_warnings；後來 learning child 覆寫 latest 為 failed | 已修 requested-date scope；已驗證 receipt 現直接重用，避免重複 updater |
| official-market-events-daily | 04:50／0 | 正式 event publication 已發布 | 接線存在；新 custody 導致舊 OOC stale，不能改舊 hash |
| data-freshness-check-daily | 05:00／0 | degraded，formal 基本面 expected periods 缺件 | current observations 不代替 PIT availability |
| ml-raw-pit-refresh-daily | 05:05／0 | blocked_insufficient_storage | 約少 19.83 GiB，容量 gate 正常，不降低 reserve |
| recommendation-snapshot-daily | 05:10／0 | passed，同日 canonical result 已保存 | 真實 ID／payload hash 只讀驗證通過 |
| evidence-pipeline-dry-run-daily | 05:15／2 | mixed latest clock ambiguity；Portfolio／risk 缺件 | 精確同日 binding 與 timeout 已修；人工 thesis 等仍保留 |
| ml-promotion-evidence-daily | 05:17／0 | formal_ooc_corporate_action_custody_stale | 缺 manifest／events hash 相符的新版本，不手改 frozen identity |
| ml-promotion-authority-daily | 05:18／0 | skipped_evidence_unavailable；compatible pointer missing | 正確 fail closed，broker=false，不補簽章 |
| ml-allocation-copilot-daily | 05:20／0 | passed_rule_only | 不代表 ML alpha／promotion 已核准 |
| decision-evidence-capture-daily | 05:25／0 | passed | 無已確認 wrapper 故障，不額外 confirm／重跑 |
| ml-direct-chain-maintainer | 05:30／0 | blocked_insufficient_storage | 同 raw gate，需容量／受控 rebuild 方案 |
| forward-outcomes-daily | 05:40／0 | passed_with_warnings | 自然成熟與資料缺件分開；不能補造未來結果 |
| recommendation-calibration-learning-daily | 05:45／1 | technical false blocker；availability gate／learning failed | 同日 strict technical reuse 已修；source-time gate 不放寬 |
| recommendation-calibration-learning-banktaiwan-shadow-daily | 05:50／2 | root 混用／full status 超 bounded read 上限 | 已修 Shadow root 與 bounded projection；query inventory 補齊 |
| paper-execution-eod-replay-daily | 06:00／2 | shared quick latest failed，dependency blocked | 上游覆寫問題已修；仍須真實 Paper lineage／session receipts |
| pit-sector-membership-preopen-capture-daily | 16:00／0 | archive 成功但 taxonomy blocked，使用啟動前 clock 驗本輪 completion | 重讀 actual clock、接官方 config、taxonomy failure 改非零 |
| paper-portfolio-daily | 16:15／3221225786 | `0xC000013A` 中斷；最新業務 status 仍是舊休市日 | 不確知 terminator；另有 09/08 missed pending session，需 owner 決策 |
| ml-allocation-forward-daily | 16:15／3221225786 | 同中斷碼，等 cutoff 過程缺 custody | 加 per-run wait heartbeat；native preflight passed，尚無修後自然 completion |
| formal-pit-sidecar-postcutoff-daily | 18:00／2 | 當日 denominator 被用來驗範圍外歷史；taxonomy／formal gate 缺件 | history scope、offline calendar 已修；license／formal publication 不跳過 |
| formal-input-producer-daily | 21:25／2 | candidate_only；Rule history／causal ledger／sector source 缺件 | 範圍外 PIT 誤報已修；真實 Rule／ledger custody 仍缺 |
| v2-2-weekly-collection | SUN 18:00／0 | 09/21–09/27 pending_human_review，最後交易日 09/24 | 預期人工佇列，不是漏跑或已批准 |

## 已修復的程式與契約

1. **查詢 inventory**：CMD 漏 BankTaiwan、Python inspector 漏 legacy learning 與 BankTaiwan。
   現兩者完全對齊 21 項，CMD count 從清單推導；含遺失 BankTaiwan 的非零 regression。
   只擴充唯讀查詢，不讓 aggregate registration 接管獨立 task。
2. **Evidence same-day identity**：scheduled CMD／PowerShell 開啟精確 binding，驗 task、
   passed、日期、root、寫入 flags、aware／非未來 checked／persisted clock 與 canonical
   artifact。使用 `--result-id` 同時接 importer／coverage，不放寬 generic mixed-latest gate。
   binding 失敗在 child 前停下；pipeline child 600 秒 timeout 保留 partial stdout／非零 status。
3. **Technical reuse**：既有 source contract 成功驗證後真的跳過 quick child，保持主 updater
   latest bytes。只是日期相同或 path 存在仍不足；invalid receipt 繼續 bounded updater／拒絕。
   未更動推薦、績效、financial calculations，也未新增未來資料可見性。
4. **PIT clock／failure propagation**：archive／denominator HTTP 完成後重讀 actual clock，
   不以啟動前時間拒絕本輪已完成回應。Injected clock 仍只供 fixture；08:30 cutoff 不變。
   taxonomy 或 denominator blocked 現 status degraded／exit 2，不再 archive 成功就回 0。
5. **PIT source wiring**：新增版本化官方 source-config，由盤前 CMD 預設綁定。無 TEMP
   path、手工 symbol mapping 或固定 completion clock；使用已生效規格，未生效修訂僅供
   history evidence。license 明確 `research_only_unaccepted`，formal acceptance=false。
6. **PIT history scope／calendar**：早於明確 coverage start 的日期資料夾只列 out-of-scope，
   原檔不改／不讀成當期 source，不補 required coverage。未知日期／範圍內失敗仍 blocker。
   盤後 calendar 與前置 gate 一致使用離線官方 cache，不額外線上 probe 補證。
7. **ML wait custody**：unique per-run state 與 runtime pointer 分開保存 heartbeat；等待不
   覆寫 business status，interruption／exception 留 terminal。外部 hard kill 仍只能留下
   最後非 terminal state，terminator=unknown，無 forward credit／broker permission。

本輪前已提交的相關修正：`afa408ee`（requested industry dates scope）、`d4bc27b1`
（BankTaiwan Shadow root／bounded snapshot source projection）、`7eaaef57`（default root test）。
本次新修正依契約／PIT／中斷觀測／查詢／文件分批提交，commit identity 以 Git history 為準。

## 真實來源取得與只讀讀回

### 行情與推薦

正式日價與技指最新資料日為 20260929；raw TWSE 1,095、TPEx 868，SQLite 同日 1,963
個代號，核對同日 code set 一致。這不是全資料域或歷史 PIT 完整性聲明。
Formal snapshot 的只讀新 binding 實測 result=`rec_194af705ec5f41d895849f16b530b281`：

- status bytes SHA-256：`c592a41dcc80c5a948ac35182121a79038ee4bb324063b1222dbd7161ed32e5d`
- canonical payload：`24bb1ec9f6131f4f7899a5f60fe317e48c505848e3f6099dcb91518a9d5edd34`
- observed verification：`2026-09-29T21:26:45.187207Z`

Binding 成功不代表 Portfolio／risk 同時 ready，也不是已重跑整個 dry-run。

### 官方 taxonomy config

21:37–21:38Z 做一次不落地的 GET／parser probe，六個官方端點全部 HTTP 200：TWSE
base specification、2023 change notice、revision history、current regulation、TPEx manual、
ISIN 全證券表。TWSE 既有 parser 重建 33 類，TPEx 31 類，ISIN 46,500 筆證券記錄；
46,500 **不是上市櫃股票數**。ISIN response 為 34,675,523 bytes，未超過既有 producer 的
64 MiB source 上限；probe 使用同一 bounded fetcher，沒有繞過大小限制。
Probe 只在記憶體保存 raw，不寫 scheduled bundle 或正式 DB；parser 通過不等於當日
denominator join／taxonomy bundle／formal license 全部通過。

Source config 的正式 URL 見 [版本化設定](../../scripts/scheduled/pit_taxonomy_source_config.json)。
TWSE [官方規格清單](https://dsp.twse.com.tw/brokerManual/list) 已列 B.12.13(202612)，
本 config 不把這個未生效版本當成目前分類。TWSE composite 的 05/01 生效政策與 TPEx
05/18 生效版本須由既有 parser/effective evidence 核對，不由 HTTP 200 推導。
本次 source bytes hashes（不包含授權核准）：

| Source | SHA-256 |
| --- | --- |
| TWSE base | `3739f28acba7bdce2c1d21016a2c8c3c8c63b2ca14d013446f9448d733f4a5dc` |
| TWSE change notice | `69d734728bd96336e21caa6c8bd55fee0e9c859d839840391fe9e120050e9864` |
| TWSE revision history | `465f69ef65e58c3a2c2469ac186fec658f988645a0b267ea886b471032a9b035` |
| TWSE current regulation | `7e2d415a1d062fe6d07f220fe88298718eb21c71a53ed1b3d2ddadb45d7d7353` |
| TPEx manual | `d9211860d9384ff43c63f75f79272d936e68f4969402278262fefa405aa1dd56` |
| ISIN security table | `eb4bd225ce441fd245bdb3b168c91a38789ed067f121d97a0f56cbff2a3908cd` |

### 當期 archive／forward preflight

以保存的 09/29 decision clock、當日獨立 denominator 與 coverage start=end=09/29，
只讀 history 驗證 14 份 archive：1 份範圍內有效，13 份舊檔不消費，invalid=0，
required／covered=[09/29]、missing=[]。仍有 `pit_formal_sidecar_publication_required`，
未發布新 sidecar／未補造 formal credit。不能由當期測試推論舊檔完整。

Native `run_ml_allocation_forward_daily.cmd preflight` exit 0：資料 DB、隔離 Paper state／
ledger、release／archive／calendar／helper 路徑存在且接線一致，不執行 network、wait
或 inference；不是下一次真實 forward completion 的證明。

## 尚不能自動消除的 blocker 與下一個 owner 動作

| Blocker | 真實限制 | 下一動作／不得做的事 |
| --- | --- | --- |
| blocked_insufficient_storage | D free=273,990,897,664 bytes；required=295,279,001,600 bytes（275 GiB），差約 19.83 GiB | 先核准明確容量／搬移／保留計畫；不刪 raw、不降低 200+35+40 GiB gate、不直接重跑重建 |
| pending_execution_session_missed:2026-09-08 | paper-main 的 scheduled_rec_20260907_051003 有 9 份 pending receipts，同 source hash；另有 2 份舊 receipt 缺 execution_date | Owner 選擇保留並建立可稽核 no-fill／expiry 處理或獨立新 profile；目前尚無批准的 recovery contract，不刪舊檔、不補造 09/08 fill |
| human_thesis_required／paper_position_identity_unproven:1418 | Portfolio／risk baseline 的真實 thesis／entry lineage 未證 | 補人類提供的 thesis 與入場證據；不能由程式代寫 thesis 或假定來源相同 |
| monthly／quarterly expected period 缺件 | formal 月營收最新 2026-06，財報 2024Q1；current-only 觀測已有 2026-08／2026Q2 partial | 需官方公告、availability 與 revision lineage 才 formal apply；不把現在取得日當歷史 available-at |
| formal_ooc_corporate_action_custody_stale | 新官方 events 與 frozen OOC manifest／events hash 不一致 | 受控版本化 rebuild／readback，先解容量，不改 frozen hashes、不補 promotion 簽章 |
| Formal Rule／ledger／sector source missing | 保存 producer 仍 candidate_only，缺 causal ledger／Rule history／正式 sidecar custody | 取得真實 source continuity／license 與 consumer readbacks，不把 current capture 改標 formal 3/3 |
| 0xC000013A／Task history disabled | 中斷者未知；無 Win32Battery，沒有已確認 shutdown／sleep 證據 | 由管理員開啟 Operational history；本輪啟用命令被 OS Access denied，不繞 ACL／ExecutionPolicy |

Paper pending source hash：`sha256:9330c91d8934405629d9f4f48d2c1a239741f1d886a71bfc75d4086fa33df165`。
Receipt root 為 repo `output/paper_execution_eod_replay/receipts`；只讀枚舉，不修改 ledger。
新 heartbeat 改善未來中斷的可觀測性，不能追認舊中斷因果。

沒有證據指出 daily reporting prompt 被傳進 Windows pipeline 或造成既有錯誤，故沒有改
Codex automation prompt。報告應繼續分清 registration、exit code、同次 artifact、source
coverage、自然成熟與人工批准；將 fail-closed 改成成功文案不算修復。

## 驗證與接受邊界

14 個來源／wrapper／contract suites：262 passed、5 skipped、exit 0（13.11 秒）。另 3 個
CMD inventory／registration suites：24 passed、exit 0。5 skips 全為 Windows symlink
權限 WinError 1314，不記作 pass。Targeted mypy 7 個 runtime source files 0 issues；
14 個 changed Python files py_compile 通過（包含後續 inventory inspector／tests）。
未改 UI，未聲稱 full-suite 或真實 scheduled E2E 通過。

測試 TEMP／TMP 都指定 repo 的 ignored `.tmp_scheduler_final_temp`，pytest basetemp 在
其下，符合原有 TEMP-only guard；不是放寬正式 root 限制。使用 `-o addopts=`／
`-p no:cacheprovider`，避免本機 pytest cache 權限干擾。第一輪未正確指定 TEMP 的
TEMP-root／ACL setup 失敗，以及 probe cp1252 console 印出中文的 encoding 失敗，
均不冒充 pipeline failure；修正隔離 setup 後完成上述驗證。

```powershell
$env:TEMP=(Resolve-Path .tmp_scheduler_final_temp).Path
$env:TMP=$env:TEMP
.\.venv\Scripts\python.exe -m pytest tests/test_recommendation_calibration_contract_guards.py tests/test_recommendation_calibration_snapshot_resolution.py tests/test_banktaiwan_recommendation_learning_operational.py tests/test_scheduled_evidence_pipeline_dry_run_wrapper.py tests/test_recommendation_evidence_importer.py tests/test_evidence_source_coverage_service.py tests/test_pit_preopen_schedule.py tests/test_formal_pit_history_handoff.py tests/test_formal_pit_sector_publisher.py tests/test_pit_taxonomy_daily_source.py tests/test_ml_forward_scheduled_wrapper.py tests/test_ml_allocation_forward_child_contract.py tests/test_scheduled_data_update_runner.py tests/test_twse_industry_index_capture.py -q -rs -o addopts= -p no:cacheprovider --basetemp=.tmp_scheduler_final_temp/run2
.\.venv\Scripts\python.exe -m pytest tests/test_scheduled_cmd_scripts_task_names.py tests/test_inspect_scheduled_task_registration.py tests/test_scheduled_cmd_scripts_exist.py -q -o addopts= -p no:cacheprovider --basetemp=.tmp_scheduler_final_temp/query
```

下一次自然執行才可核對 repaired receipt／clock／exit；不回填舊 status、不改 approved projection、
不授予 alpha／broker，不以 code regression 替代真實來源接線後的 E2E 證據。
