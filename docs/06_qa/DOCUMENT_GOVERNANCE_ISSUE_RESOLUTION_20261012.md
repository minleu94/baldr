# 五項文件治理問題裁決與修復收據（2026-10-12）

本收據承接治理矩陣的 G02、G03、G04、G05、G10；基準提交為 `d929e003a508a24e97611b73f282f5061f9b0c7b`，開工時 tracked working tree 乾淨。它記錄文件裁決、實作與限定驗證，不是新的產品進度權威；目前狀態仍看 Snapshot，補完計畫的暫停界線保持。

## 1. 範圍與回滾清單

| 路徑 | 變更類型 | 範圍 | 回滾方式及風險 |
|---|---|---|---|
| `docs/superpowers/{plans,specs}/2026-07-11-*refactor*cycles*.md` 的四個具名文件 | 修改 | D–G／H–L 設定數、執行交接與觸發證據分開 | 保存當前 diff 後只反向本輪註記；低風險，整檔還原會覆蓋共享變更。 |
| `docs/09_archive/PHASE_3_3B_IMPLEMENTATION_PLAN.md` | 修改 | 原完成聲明標為未驗證自述 | 只反向本輪 erratum hunk；不得改歷史日期或 checklist。 |
| `V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md`／`P0_MOPS_OWNER_PACKET_REFRESH_2026_08_28.md` | 修改 | P0 canonical 分母與 EZSearch lane 的來源身分裁決 | 只反向本輪範圍註記；不回寫 decision registry。 |
| `scripts/scheduled/run_daily_data_update_quick.py`／`tests/test_scheduled_data_update_runner.py` | 修改 | explicit calendar cache 的唯讀 operation preflight 與跨年回歸 | 只反向本輪 hunk；回退會恢復失效的 private API 呼叫。 |
| `scripts/update_phase3c_candidates.py`／`tests/test_phase3c_backfill_runner.py` | 修改 | 型態檢查發現同類候選 CLI 舊 API 呼叫；同一 offline operation 驗年表 | 只反向本輪 hunk；保留候選隔離／confirm／禁止 online，回退會恢復失效呼叫。 |
| Portfolio／聲明持倉的具名程式與測試 | 修改 | 保存結果讀取、完整性與隔離測試資源 | 保留測試收據後反向限定 patch；須重新驗證讀取契約。 |
| 既有治理矩陣、manifest、線路矩陣、相關操作／QA 導覽 | 修改 | 同步此次裁決與實際驗證結果 | 只反向本輪 hunk；避免留下與程式不同版的狀態。 |
| 本收據 | 新增 | 可核對的裁決與驗收證據 | 只有入站引用解除且收據保存後才可移除。 |

Coverage Pass：治理矩陣、逐檔 manifest、線路矩陣、上述來源文件及 QA 入口為 Must。Manual 的聲明持倉操作／結果／缺件／排錯同步，架構補唯一 query 讀取 seam 與可比性界線；Snapshot、Roadmap Hub、6M、Legacy、中央 Index 維持各自權威，相關入口與本輪有限工程接受不衝突，產品補完暫停與全域 Gate 保持。未改產品優先序、來源接受決議、ML、交易／績效計算或正式原始資料。Look-ahead 自查：讀取保存結果維持原 decision/data date 與 evaluation cutoff；日曆修復只共用固定觀測 operation，不改日期選擇或行情。

## 2. G02：12／15 是不同流程的設定數

D–G 為四輪三角色，共 12 個設定；H–L 為五輪三角色，共 15 個設定。[四輪設計](../superpowers/specs/2026-07-11-safe-refactor-four-extra-cycles-design.md)、[四輪計畫](../superpowers/plans/2026-07-11-safe-refactor-four-extra-cycles.md)、[下午設計](../superpowers/specs/2026-07-11-afternoon-safe-refactor-cycles-design.md)、[下午計畫](../superpowers/plans/2026-07-11-afternoon-safe-refactor-cycles.md) 已分別補上日期化證據界線。

`BALDR_CODEX_AUTOMATION_INVENTORY_20260925.json` 的 `capturedAt=2026-09-25T20:48:00`，總數 48、ACTIVE 3、PAUSED 45。D–G 的 12 個 `baldr-master-report-refactor-*` 與 H–L 的 15 個 `baldr-afternoon-refactor-*` 都列為 PAUSED；本輪唯讀核對 27/27 現存 TOML 的 bytes SHA 與清冊 `sourceTomlSha256` 相同，27/27 memory 存在。沒有修改 automation。

本機 `output/automation/version_loop/refactor_nightly_closeout_20260711.md` 留有六個切片、focused union 24/24 與 `506d7a7` closeout；`refactor_afternoon_closeout_20260711.md` 記 H／I／K／L accepted、J `NO_SAFE_SLICE`。這些與 memory 支持持久化配置及執行交接鏈；設定數不等於完成切片數。缺少獨立 host event／audit，不能判定每次是 Scheduler 觸發或等價手動流程，也不能還原完整建立事件。

裁決：12／15 的文件數量矛盾已消解；歷史觸發來源仍 unknown，不把配置或 closeout 升格為 Scheduler attestation。

## 3. G03：canonical P0 分母與 EZSearch lane 分開

同期提交 `9c52b7763b` 的 `P0_SOURCE_IDS` 是 13 個 canonical P0 contracts，包含 `pit.quarterly_financials`，不包含 `mops.ezsearch.statement_publication`。當時 audit 逐一遍歷此 tuple，control-center 的 decision/audit 輸入也限定同一集合。registry 說明 EZSearch 是 statement availability lane，不是 numeric／governance source。因此 §14 的 13-row audit `accepted=0 / limited=0` 與 §7 的 DEV-66 EZSearch `limited` 決議事件不是同一分母。

本輪唯讀取回 `C:/Temp/technical_analysis_development_output/DEV-66-mops-ezsearch-20260727-20260728/` 的 owner JSON，其 source 為 `mops.ezsearch.statement_publication`、revision `decision:mops.ezsearch.statement_publication:20260727-r1`、status `limited`、decided_at `2026-07-27T21:19:18.3035865-07:00`；用途只含 `research_pit_statement_availability`、`development_shadow_projection`。formal OOS／credit／production scheduler 均 false，blend alpha 為 0。

| 證據 | SHA-256 |
|---|---|
| `owner-limited-source-decision.json` | `1bab0550e245dbdfb95eddedfb669b5ba8ef5c93bd9278f67445839c12d1960f` |
| `mops-statement-availability.json`（36 events、research_only） | `838a7507655934646d5118e3111118679d15dc935e5fa1e4372f8f060dcd602e` |
| `fundamental-statement-availability.csv` | `e621d19863be40641ebda7f9a6f83a5b78243d2cda2d90e459d2efa0ddbe838f` |
| DEV-66 `source-acceptance-working-copy.sqlite`（未作 current 權威） | `d270965b8e0fc437af009761ba060e8ea96610e514a18c785045e8ee86af0bce` |

8/28、8/30 指定 raw audit／intake／packet 路徑目前不存在；archive 只留 audit SHA 和彙總。沒有據此推定 raw audit 的 registry inputs 或最新 applying revision。[登錄](V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md)與[歷史 packet](../09_archive/P0_MOPS_OWNER_PACKET_REFRESH_2026_08_28.md)已保留原數值並加範圍裁決。

## 4. G05：歷史完整驗收未知

[Phase 3.3B 計畫](../09_archive/PHASE_3_3B_IMPLEMENTATION_PLAN.md)保留原日期和完成主張，標為未驗證來源自述。原引用的兩份完整驗證報告在工作區不存在；後續 TASK-LOOP-04／08 的離線限定 QA 不能替代三個 Epic 的完整接受。unchecked checklist 也不單獨證明未實作。文件的誤導已修正；歷史完整實作／接受保持 unknown。

## 5. G04：Portfolio／聲明持倉讀取

真 MainWindow 跨頁整檔 **5 passed／10.77 秒**，包含 canonical 保存／真 Portfolio validator／摘要竄改拒絕及新 teardown 資源測試。alias 正例 fixture 補完整 decision/data dates 與 snapshot lineage，正式 validator 未放寬。隔離 root 使用短路徑；teardown 按 handler identity 去重，只關閉指向該 fixture root 的 FileHandler，外部 handler 保持可寫。先前 sandbox 的保存失敗與缺 lineage fixture 分開處理；初次 host 的 `2 passed, 1 teardown error` 原收據仍保留，不能當完整通過。

`SavedRecommendationConditionContextProvider` 已走既有 query，讀核驗 canonical execution／registered legacy DTO，不再旁路查 SQLite `runs.data_path` 和 JSON。caller 保留獨立 baseline、profile／version／計分配置一致、決策日期不晚於 evaluation date；新增 Request／Context profile 與配置 ID/hash 衝突拒絕。Query `persisted_at` 只作排序及獨立性檢查，`availability_custody=false`。整檔 **27 passed／0.97 秒**：真 canonical pair、跨 identity、Request／Context profile mismatch、strategy ID 衝突不能 fallback hash、legacy result ID mismatch，以及未來日期／Request 與 Context 日期不同均有負例。沒有新增金融計算或提升 PIT／交易資格。

另唯讀取回正式 Exit wrapper 的 10/12 保存產物：`D:/Min/Python/Project/FA_Data/output/exit_effectiveness/20261012.json`，2816 bytes，SHA-256 `b0eefc8d9b75e0e075c1080da3e83a7837e89e904009a9597994338a1d9bf31c`；與 wrapper typed receipt、log 的 path／hash／requested date 相符。直接核 raw JSON 的 `generated_at=2026-10-12T12:15:04.412987+00:00`，不是 PowerShell 日期重序列化後的本地 offset。結果仍 `degraded`、`transition_count=0`、`observations=[]`、`no_exit_transition_rows`；所有 formal credit／investment effectiveness／auto exit／broker order 均 false。

`evidence_pipeline_dry_run/latest_status.json` 的 SHA-256 為 `69cc0c025e67998a9c4a5768cddeae8ec05ba1d7c4f5ad49f55d2956eec6552f`；Exit child return code 0、artifact identity verified，但 wrapper overall failed／exit 2。現有收據沒有獨立 run_id 或完整 child 開始／完成時窗，不能補造 attestation。position-health sidecar 僅 paper_research、apply_transition=false；來源 transition rows 為 0，不為了清缺口建立正式退出或倉位。Exit producer／read-model／wrapper 的定向離線契約回歸 **38 passed／1 symlink 權限環境 skip／28 deselected**，不替代完整正常 Exit 有效性接受。日期化 readback 亦補於[原 Exit QA](EVIDENCE_DRY_RUN_READONLY_EXIT_DATE_QA_20261002.md)。

## 6. G10：工程回歸與自然事件分開

實際工程根因是 Quick explicit-cache preflight 直接呼叫新版需要 operation 參數的 private loader。現在以單一 `read_operation(allow_online_probe=False)` 的公開 evidence 介面核每個所需年度；缺件、無效、過期或未來 cache 繼續 fail closed，隱式 legacy 路徑不變。跨年測試覆蓋第二年缺件拒絕及單一 offline operation。

八模組 mypy 另找出 `scripts/update_phase3c_candidates.py:_calendar_for_candidate_cli()` 同一舊 API 呼叫，已採相同公開 offline 年表驗證。週末／官方臨時休市的短路不能替代年表，跨年共用同一 operation；候選 DB 隔離、confirm、正式資料拒絕及禁止 online 保持。整檔 40 passed／1.11 秒，包含跨年、缺年拒絕及臨時休市短路後再核年表。這是 G10 同類根因的修復，不恢復產品補完。

Root host offline／合成回歸：`test_core/test_data_loader.py`、`test_update_daily_output.py`、`test_update_all_coordinator.py`、`test_scheduled_data_update_runner.py`、`test_twse_daily_price_sqlite_publication.py` 合計 **76 passed／3.48 秒**。包含 explicit no-data safe skip、混合 HTTP／解析／timeout 不可 safe-skip、future／transient text 拒絕、CSV／SQLite 未產生空或負面資格證據等。這是工程證據，不是自然 Task 收據。

定向唯讀查核正式 `output/scheduled/data_update_quick/`：115 個 JSONL records、59 個 run_id，captured_at 2026-08-28 至 2026-10-12；100 個 log、68,146,258 bytes，檔名 20260704 至 20261012。逐檔搜尋 explicit `SKIPPED_NO_DATA`／`twse_official_no_data`／`"no_data"` 無匹配。最新 run `20261012-37432` 的 TWSE step 是 HTTP 200/API OK、1095 rows、`twse_data_available`，`no_data_skipped_dates=[]`；不能把空陣列當 no-data 事件。

該有資料 run 的 raw／receipt 及同 run technical publication source binding 可驗 hash，只證明正向 lineage。仍缺自然 explicit no-data producer receipt 與同 run consumer binding；沒有啟動正式 producer、補造回應、寫原始資料或自行改 Task。查核分母與缺件是有限範圍結論，不聲稱全機歷史不存在。

| 有界查核證據 | SHA-256 |
|---|---|
| `history.jsonl`（146910 bytes） | `514bd24e1db9aa3701989312702d562e158d948064afd1b9555aa24d169d3bcf` |
| `latest_status.json`（369618 bytes） | `53b51c32f59ed9eadd4eb675e19c457511ac69942bd69352e8d5eef5d069c383` |
| `20261012_data_update_quick.log`（823756 bytes） | `879098a50b3bfb3c4bdca6af3ef9a873d91582b1af6719686d7c4c036d1ad3b7` |
| 有資料 TWSE raw response（5166355 bytes） | `226fc3b3a900a65d22ee1687c4650f54ae5a8d52415ca8a90d7c198917be73c4` |
| 同 run source receipt／observation | `114e331a25322a91fe9583d07ef540ddc36f209feed044a09fb080ea4e05caa0` |

## 7. 環境、程序與驗收界線

原 sandbox baseline 33 failed／42 passed；短 temp 後 22 failed／53 passed，定位 sandbox 對 immutable custody `os.link` 的 WinError 5。獲核 host 相同回歸 72 passed／3 failed，才定位 Quick 的真 API 錯誤；修後 76 passed。保持 create-only／identity／no-follow guards，沒有為通過測試放寬產品驗證。

所有 Python 驗證由 root 序列跑既有 named Windows Job，suspended assign-before-resume、kill-on-close、全 Job 8 GiB、最多 12 程序、啟動前至少 8 GiB可用 RAM、同 repo mutex。各已完成 run 都自然 Job 0、handles 關閉與 mutex 釋放，無 forced cleanup。Luna 僅靜態閱讀／候選編輯，未開 Python。

76-case PASS 原始收據：`output/qa/baldr_completion_20261011/root/single_owned_qa_6bbea6d99f1440278d8ef8b44f5b1a9e/receipt.json`，SHA-256 `67947f2b42e752b10a90e5d78057b1962fcbfc54aeb451335e5fd0b5c283e6cb`。原始失敗與 stdout／stderr 保存在各 immutable attempt，不刪失敗以達到零衝突。

本輪 Job 收據存於 `output/qa/baldr_completion_20261011/root/`；以下每個 suffix 目錄的 `receipt.json` 都保存真命令與 stdout／stderr hash。後續 driver 另外記 command SHA、source pins 起訖一致；沒有改候選以外的來源，也沒有把環境 skip 計入 PASS。

| 驗證 | 結果 | immutable Job 目錄 | receipt SHA-256 |
|---|---|---|---|
| MainWindow 整檔／teardown | 5 passed／10.77s | `single_owned_qa_737dece04cc44bceb4ce8bb3f2ee3ac5` | `73e2db9c13fefc8d0232d71902809d292f31caff7b951937a8ecfa2e5b3c9a3d` |
| 聲明持倉整檔／cutoff 負例 | 27 passed／0.97s | `single_owned_qa_405362fc9dd0451db6bfed168b51bf17` | `17543d68c2c5250a7060c43c1a07ccbe453e0ab0e8d0cdb6ad04ffbfe395f0c9` |
| Exit 定向契約 | 38 passed／1 skip／28 deselected | `single_owned_qa_5dfb888b348e41fea932978f8e18030e` | `8abf76ac5fd65f4ddbb2bc5574bb96d262411bcac6df8fccd87785c7f3844145` |
| 更新工作台 | 85 passed／2.51s | `single_owned_qa_e7334ce06de14087abc7cd4b6256b304` | `a70801c8f51d81eba5c75234d271554415361752c47400fc7ddd71a010b5eb76` |
| update-tab QA | 25 passed／4 skip／0 fail | `single_owned_qa_586ac0f90b8547c481087ad79ca21e36` | `2893f6fec01535af92c32411d89d4b3905d6b9cbdfdaa3d7fbe660f848dd7550` |

update-tab 的 4 skip 為腳本既有離線／接口限制，沒有正式下載或合併。八模組首次 mypy 檢出本次新增的 Sequence 推導註記及候選 CLI 的同類日曆 private API 缺 operation；失敗收據 `single_owned_qa_06f64296f15f4f428277a90acd0b8422`（SHA `93373890cc0657faba8a80f6621f2be65b920618fdbf44d54264f72445f7b8ee`）保留。修後原八模組 **954 source files／0 issues**；兩 CLI 另以 namespace 的 `--explicit-package-bases` 檢查 **2 files／0 issues**。把 CLI 路徑直接加進八模組曾觸發同檔不同 module-name 的 QA routing error，原 attempt `single_owned_qa_6129afbcd5c04a38b13bd9affb0211ee` 保留；未改 package 結構或放寬檢查。

| 最終檢查 | 結果 | immutable Job 目錄 | receipt SHA-256 |
|---|---|---|---|
| 候選 CLI 整檔 | 40 passed／1.11s | `single_owned_qa_d5ddc229d4974d2c8acb6a1e921dbffd` | `6eadc85a955a83f5b7f26e6fed88e3ed96f8d785df73a6be8db601e26f5bb03e` |
| 原八模組 mypy | 954 files／0 issues | `single_owned_qa_53dc2c2b755d42f0b5eb843889bacc54` | `905b902a3b86ca262fc480a5e335941dfa3f749aebead10a8a7797337b935baa` |
| 兩 CLI mypy | 2 files／0 issues | `single_owned_qa_2601de852b714fd6bd3bfa60adc178a4` | `94536ecd97d0f27037e3933a61cc7c89d24637f7feaca2f001d8a16ba59e135f` |
| py_compile | 7 changed files／PASS | `single_owned_qa_41790ca21f9d4ff98442204d8ddc845c` | `48ecbb680595bd91371c8c871fb15aecd6c3d56dc7e084300b2221bf82a4de2f` |

最終產品來源 bytes SHA-256：caller `a00c673f8393fdee4c99f998e36310a555e21fe84128f41e75aacb0777294e33`；Quick `faace121d251a31107f45352471c296cf57ee69a18b71b04a320d0021543e830`；候選 CLI `cc4b00c3627515aad33ebc62fc491f37129ac3eb99632ef5c93f794855222bb2`。相關測試的 source pins 與起訖一致判斷見各 Job stdout，Git 最終 blob OID／物理行數則見逐檔 manifest 與提交，不把 CRLF 工作檔 bytes hash 混為 Git blob hash。

定版 Graphify 在限定提交完成後重抽本機 AST／明示文件 links，固定 HEAD 與來源指紋核驗見 `output/qa/gov5gf/graphify_final_verification.json`；只有該收據 passed=true 才判定本輪刷新通過。root `graphify-out` 保持不變，不以舊圖覆蓋新程式碼。本輪沒有 Push 或刪除原始資料、歷史文件；完整產品補完計畫與 Gate 的接受狀態保持。
