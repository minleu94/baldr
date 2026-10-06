# B12 每日研究 runtime 與深路徑 I/O

固定 base：`175d9c502985165e3b591af71f138ce4f3b9de6d`。分支 `lane/baldr-b12-daily-runtime-20261006`，worktree `output/worktrees/baldr-b12-daily-runtime`。沿唯一原 plan、Astra 15 WP 與 Sol review 的 B12；不重新分類原 9 stage／24 UX、七個有限 closed 或性能例外。

## 契約與操作

保留 `run_daily_owner(runtime_path, target_date, execute=False, cancel_callback=None)`。舊 runtime v1 可選追加 `expected_source_binding_sha256`、`safety_reserve_bytes`、`timeout_seconds`（整數 1–3600）。原必填欄位、isolated source/output allowlist、64MiB quota、31 日期、最多三次 retry、parent→sample→日接受的 exact pins 均保留。

新增 frozen typed `OfficialCalendarSnapshot`、`UpstreamTerminal`、`RuntimeSegment`、`DailyRuntimeRequest` 與 `run_daily_runtime(request, execute=False, cancel_callback=None, clock=None, process_runner=None)`。`clock` 與 `process_runner` 是明示測試注入 port；預設每次啟動新 owner 子程序，不呼叫正式來源、scheduler、today/latest 或資料抓取。上游 calendar／terminal 的實際 custody 與原 bytes hash 核驗由可信 caller 完成，本 adapter 核對明示 pins、日期、時刻、revision，不能用自行填的 hash／布林值取得正式資格。

request JSON 使用 `rule-research-daily-runtime-request.v1`，欄位完全對應 typed request，不接受缺欄位與 duplicate JSON keys。

| DTO | 必填內容 |
|---|---|
| calendar | coverage_start/end、trading_dates（排序且不重複，最多366）、source_identity/sha256、available_at、formal_verified、provenance、coverage_complete |
| terminals | 每項 job、target_date、status=complete、identity、receipt_sha256、source_binding_sha256、completed_at、provenance |
| segments | segment_id、start_date/end_date、runtime_path、runtime_sha256；最多64，不重疊，所有四類輸出根跨段亦不重疊 |
| request | target_date、decision_cutoff、calendar、terminals、expected_jobs、segments、coordination_root、timeout_seconds、expected_terminal_pins（三元組job/identity/hash）、expected_calendar_pin（二元組identity/hash）、offline_rehearsal |

正式日曆注入須 `provenance=official_snapshot`、`formal_verified=true`、`coverage_complete=true`；calendar.available_at 不晚於 decision cutoff，cutoff 不晚於明示 clock。terminal 須 `provenance=verified_receipt`，同目標日、同 source binding、同明示 receipt pins，完成時間不晚於 clock。未知／未核驗日曆或上游缺件停止；覆蓋內非交易日回 `non_trading_day`，不開 owner。沒有將原 capture／observation 的資格欄位升格。

synthetic 僅在 `offline_rehearsal=true` 且來源標示 `synthetic_offline` 時可供工程預演；所有來源、日曆、natural、PIT、formal、training 的原 unknown／false 保持。自然累積不是本包工程 gate；正式資格仍需原證據。

每個 segment runtime 必須明示同 terminal 的 `expected_source_binding_sha256`。預檢會核 exact runtime bytes hash、policy cutoff、根分離與容量；execute 前後重讀 runtime／policy pins，owner 在生產前核源 binding，接受前後仍沿原重新核驗。新 revision 另開明示 job，不改舊來源或收據。

```powershell
# 預設唯讀preflight
python scripts/scheduled/run_rule_research_daily_isolated.py --runtime-request <request.json>
# 明示隔離執行
python scripts/scheduled/run_rule_research_daily_isolated.py --runtime-request <request.json> --execute-isolated
# 只輸出可審查Task包
python scripts/scheduled/run_rule_research_daily_isolated.py --runtime-request <request.json> --task-review
```

`--runtime-request` 不可混舊 runtime-config／target-date／outcome-root；task-review 不可同時 execute。Task review 始終 disabled、task_registered=false，帳號與ACL為unconfigured；未註冊Task。正常運行回stdout `rule-research-daily-runtime-receipt.v1`，附輸入 identity/hash／日期、role effective policy、preflight、owner result、stdout hash及receipt identity。成功另重讀exact owner immutable receipt，核保存status/source/資格；缺receipt不能冒稱成功。CLI 0包含非交易日與preflight，不能當自然接受成功。

## 單writer、rollover、容量與停止

部署 caller 必須讓所有 segment 共用同一明示 coordination_root；執行取得create-only `.daily-runtime.lock`，原owner自己的lock仍保留。busy不清其他lock，僅釋放本程序持有的合作lock；不同段使用明示新roots／新程序，不選latest、不重用舊輸出根。舊segment、partial、已發布producer／parent／acceptance與source pins保留。

| writer角色 | 原政策來源／原reserve | 有效要求 |
|---|---|---|
| snapshot producer | ml_storage_capacity.resolve_heavy_chain_safety_reserve；中央20GiB | max(原20GiB, accepted override) |
| parent／capture／observation／sample／owner status | rule_research_sample_capture.SAFETY_RESERVE_BYTES；200GiB | max(原200GiB, accepted override) |
| 整鏈owner | capture衍生200GiB，加四根quota的新寫／暫存headroom | max(200GiB, accepted override)+工作預算 |

`daily_writer_effective_policy` 在preflight前及owner保存status列各role來源與有效值。override低於中央20GiB拒絕；20–200GiB不降低capture，300GiB保留300GiB的整鏈守衛。更高override由owner在各輪preflight強制，不改readonly writer的原常數，不回寫舊收據。容量未知／不足、quota不足拒寫；無自動清理。

owner可選合作timeout，retry與producer cancel沿原callback；wrapper每個子程序timeout有界，取消／超時先停止並回收本次子程序（最多5秒grace，必要時kill），回stdout timeout/cancel與partial_artifacts_preserved。沒有崩潰自動清partial或stale lock的機制；需明示新segment或人工檢視。stdout上限2MiB、stderr64KiB，超限／非JSON／退出與成功不符均不授成功。此為合作writer約束，不宣稱敵對Windows no-follow或完整崩潰durability。

## 必要snapshot I/O修復

中央明示擴ownership到producer／repository及其兩份測試，只修OS renderer。固定base同node實測原daily完整鏈失敗：`_atomic_write_bytes` 的 `os.replace` 回 WinError3。預設Temp case：snapshot batch根182 UTF16 units，`.staging/daily_market_snapshot_<8>.tmp` 230，`objects/<64hash>.json` 265。原失敗留存於 pytest-13193／13194 的Temp，沒有清理或縮短basetemp掩蓋。

重用唯讀 `personal_data_paths.to_internal_io_path`：mkdir／mkstemp／replace／stat／bounded open／retention scandir與reader realpath/isfile使用OS格式；mkstemp返回內部name映回canonical，containment仍在canonical root/path核驗。literal ADS、尾點／尾空白、device alias在resolve前拒絕。hash/schema/SQL/cutoff/byte limits/identity/policy/資格均未改；不改parent/capture/observation/sample模組。

深Unicode／emoji root超過260 UTF16 units的producer→repository→新Python程序讀回，source DB bytes/mtime與manifest身份不變；default Temp原失敗node保留為回歸。沒有全域Windows長路徑設定。

## 驗證與交接

focused範圍：原daily owner、B12 runtime、storage governance、snapshot producer／repository。包括mockclock歷史漏日（保留原future guard）、非交易日、缺／修訂／失配terminal、未知容量、higher override、低於中央、單writer／取消／retry、跨段新程序與原來源／partial保留、codec／CLI offline review、偽造成功receipt拒絕與preflight後config變更。

最終五檔focused `102 passed / 37.22s`：`python -m pytest tests/test_rule_research_daily_owner.py tests/test_baldr_b12_daily_runtime.py tests/test_research_snapshot_storage_governance.py tests/test_daily_market_snapshot_producer.py tests/test_daily_market_snapshot_repository.py -q -o addopts= -p no:cacheprovider --junitxml=output/qa/b12_final_focused_20261006.xml`。增加取消於preflight後、既存實體alias sentinel核驗後另跑相關9案例，收據追加如下。原固定base失敗node與新通過收據並列，不用短basetemp替代。

mypy限定6個source files通過，compile修改Python通過，quant precision／look-ahead與diffcheck通過。未改UI，不跑全UI。來源與交易公式未新增；日曆available-at≤cutoff、unknown不升資格，look-ahead自查通過。

最終delta `9 passed / 0.78s`，raw收據 `output/qa/b12_final_delta_20261006.xml`；共103個不同案例（102原組＋新增取消1，8個alias為強化後重測，沒有重複計數）。

中央需同步Manual上述入口、操作、參數、結果、安全與排錯，Snapshot／Architecture／Index／scheduled README與唯一原plan append；本lane只改授權ownership。正式calendar/terminal custody adapter caller、Task/account/ACL、正式source/output roots與安全啟用仍需部署決策；本包不真DB抓取、不私人migration、不B09 files、不交易、不Native、不真train、不dev cherry、不push。

回滾：先確認此lane未提交內容，`git revert <B12提交>`，再跑focused；保留所有原來源、segment與收據。新adapter caller由中央同時回復，無資料刪除。
