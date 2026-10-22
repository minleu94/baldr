# Baldr V2 Release Closeout

本次承接既有 V2 與月營收工程，唯一 runtime Source 為 `06a4e1c15ed98d2b92a02967eaea03d5d47f49d8`。後續具名 closeout commit 只同步交付文件，不改此候選的程式。獨立證據根為 `output/tasks/baldr-v2-release-operations-closeout/`；本文 QA 編號均屬該任務，舊任務編號不得混用。交付裁決為 **`V2_RELEASE_CLOSEOUT_COMPLETE_WITH_EXTERNAL_ACTIONS`**；不以工程修復宣稱自然排程已恢復。

分軌結果：`V2_SOURCE_ENGINEERING_COMPLETE`、`V2_FINAL_RC_AUTOMATED_VERIFIED`；`NATIVE_SMOKE_NOT_EXECUTED`、`OWNER_UAT_NOT_PERFORMED`、`FINANCIAL_QUALIFICATION_PARTIAL`。前兩項只適用下列已驗工程與候選，不代表五旅程全部金融分支通過。

## 候選與版本

| 身份 | 固定值 |
|---|---|
| Source | `06a4e1c15ed98d2b92a02967eaea03d5d47f49d8` |
| 版本 | `2026.10.21+06a4e1c15ed9` |
| 唯一新候選 | `dist/candidate_06a4e1c15ed9_e74f9e5f/baldr` |
| EXE SHA256 | `75e53e364d19f0af7d73ede13a240917e1420043941296d16de115d0e30d5f8c` |
| BUILD_INFO SHA256 | `8ef145ed71a5e484ee6da6eeda6b71a2f9e93f8d9269bfd566b0704f7fb207bd` |
| Source archive SHA256 | `5d2edb548906a6baace9b1d2a258a62a0be3e21b3c07e501d0bcb8f2c5824651` |
| 隔離 state | 本任務 `candidate_state`；不與私人或正式根合併 |
| 12檔核心交付收據 SHA256 | `c0402a0468106143c050217780ea169bd2afb15a8e04b50a9c8484ad71b331ce`；包內 `DELIVERY_RECEIPT.json` 與任務 `release_summary.json` 相同 bytes |
| 全檔案 manifest SHA256 | `41821321123f4f226b39c1a23b869389c82eb8dea3c76bd342468a93a1585c46`；建立清單前 7,136 檔、976,816,844 logical bytes，另增 manifest／交付收據本身 |

QA010 僅建置一次。QA012 的同版命令通過固定 archive、依賴鎖、Source launcher／EXE、直接與 `-m` Main 入口及 journey／model／H20／V2 contracts 比較；該整輪因最後全域文件連結檢查失敗而仍為 FAIL。QA013 材料、Launcher prepare／check／錯 SHA 三切片通過；負例回 3，沒有修改 launch-info。QA014 三個 fresh CASE 均 PASS：100%／125% 各17路由於1280×760及首頁1500×900／1440×900／1920×1080，150% 的17路由於1500×900，沒有重跑笛卡兒積。11個月營收模組及3個新維運／邊界模組均由 PyiFrozenLoader 從該包 `_MEIPASS` 載入，無 workspace fallback。來源／樣本 pins 保持，正常 Main exit0、worker／pool0、deferred delete 後 window 無效；root已檢視100%／125%首頁、125%選股及150%首頁截圖。

以整包 `Launch-Baldr.cmd` 啟動，操作、資料日期、SHA 與限制見包內 `GUIDE.md`。四份固定公開樣本包括四股價庫及題材檔，沒有私人 Journal、正式資料或 R42 payload；包外技術來源仍唯讀、本機綁定、qualification unknown／PIT false。舊 d9、eefd 與 active delivery 均保留。回退時先正常關閉新包，再用舊包原 Launcher／原 state；不搬移或合併 state，不替換正式入口。候選未簽章，Native 與發布接受另列。

SSD metadata 僅按檔案 Length 加總：dist 70,816,754,409 bytes、歷史 output/trial 27,642,311,137 bytes、output/packaging 27,480,813,031 bytes，三範圍列舉錯誤0；不扣 hardlink、不代表實際配置區塊。記錄當時 F 可用66,965,258,240 bytes，詳 `release/ssd_metadata.json`；沒有清理任何舊包、build、Trial、模型或證據。

## 已交付能力與五條旅程

本包包含 d9 的四主導航、搜尋／鍵盤返回、首頁決策日與行情日分離、Journal／Registry／保存重開、人工確認 Paper Producer／UI，以及 c6 的雙市場月營收原件歸檔、分批歷史工具、逐用途資格 reader、百分率因子／比較／篩選／分市場 shadow 排名及安全 consumer 入口。後繼修正只處理正式設定 logical／physical 路徑身份、精確 repo/output junction 與唯讀維運分類；沒有更改帳戶、資金、金融公式或來源資格。

| Blueprint 旅程 | Code／Contract | Automated Main E2E | 金融來源資格 | Native／Owner |
|---|---|---|---|---|
| 首頁→線索→個股→保存→返回 | canonical／日期／Journal 守衛保持 | 重用 final-completion QA019 真 Main 歷史結果保存／fresh／返回；今日正向仍 stale PARTIAL | 真來源原降級保留，不升格 Paper | 未執行／未驗收 |
| 市場／題材→成分→個股→返回 | typed 版本與 selection 保持 | 重用 product QA096／103／162 的具名樣本與 fresh | 固定樣本，非全市場或 PIT | 未執行／未驗收 |
| 選股→條件→比較→個股 | 價格流程及月營收獨立用途契約保持 | 重用 product QA159 精確 query／page／row 返回；未以正式接受營收驗完整 Main 正向 | 金額單位 Unknown，正式月營收用途仍拒絕 | 未執行／未驗收 |
| 個股→Paper→Forward→覆盤 | Producer、原 ledger／CAS／Decimal／回滾／idempotency 已實作 | 重用 final-completion QA038 真 Main 人工確認正向保存／exact reopen／返回，僅隔離 fixture；整旅程 PARTIAL | 正式帳戶／cash／mark／日曆未接受；Forward 等自然成熟 | 未執行／未驗收 |
| 策略→回測→保存→Registry 比較→返回 | 原保存／相容性契約保持 | 重用 product QA162／164 功能切片；QA164 原整輪 FAIL 保留 | 研究範圍，不授 Alpha／ML promotion | 未執行／未驗收 |

上述 UI 與 research-paper runtime 自 d9 至本 Source 的 Git 差異為空，因此重用具名證據；它們不證明新包所有金融分支成功。月營收工程與實際 1,981 列／YoY 1,975 合格、6 Unknown 的有限研究結果依[全用途矩陣](MONTHLY_REVENUE_FULL_SCOPE_ACCEPTANCE_20261021.md)；金額單位 Unknown、歷史完整月份 0、正式 PIT／Scoring／排名／回測／Paper／Forward／ML Gate 未成立。歷史 HTML 截斷及舊 FAIL 不重寫。Paper 仍只支援原明示 500,000 TWD／八檔帳戶與整手政策，沒有替 Owner 建立真實狀態。

## 本次 QA 與原失敗

QA003 正式設定路徑 14 項通過。QA004／005 分別為 12／4 項 FAIL，原 stdout／收據保留；修正漏套的精確 junction 檢查、Paper 變數遮蔽與隔離 fixture 後，QA007 編譯、55 PASS／3 SKIP、mypy 4 檔通過。三項 SKIP 是本環境不具 symlink 建立能力，不冒作負例已驗；真 Windows mount-point junction 正負例已執行。

QA008：Workbench／Journal／Registry／Paper／月營收與正式設定共 260 PASS，更新頁 25 PASS／0 FAIL／4 SKIP，mypy 1,120 檔通過。QA009：維運 12 項、mypy 2 檔及 51 份 automation 前後核對通過。QA011 為本機 release helper 縮排編譯 FAIL，修正後 QA012 編譯與同版命令通過，沒有重建候選。QA012 最後文件命令的既有 junction 連結錯誤保留，不宣稱全庫全綠。原 product QA164 IPv6 isolation FAIL 與其他日期化失敗仍沿原件；僅 probe 的 loopback 臨時埠能力 bind 可放行，外部 connect／DNS／sendto 與 CASE 外寫入仍拒絕。

QA015 完整重驗候選7,136檔、核心12檔與交付副本 SHA，舊d9 EXE／BUILD_INFO／交付收據三 pin 保持。28條變更路徑與17項coverage已核；10份具名正文／Feature Map與Context metadata檢查通過。較廣的全部變更Markdown仍有80個既有junction越界引用，逐項所在完整行均與c6基線相同；不是新引入的缺件或新連結通過，也沒有修改checker、登記例外或宣稱全庫語意一致。基線核對及原失敗列於 `evidence/link_baseline_review.json`，完整 metadata inventory 固定當時HEAD的5,296 tracked／1,647 docs；本新摘要當時另列未提交，沒有混入HEAD分類分母。

QA016 固定Source全部受改Python編譯、已終結Job的handle／mutex／程序核對及完整task結構／證據檢查通過。最後具名 Git commit 封存本頁與七份既有入口同步，runtime 相對 `06a4e1c15ed9` 差異為空；確切 final commit SHA、工作樹與外部設定備份位置記於本任務 `git_closeout.json`，不在同一commit內自填自身SHA。原 unrelated `do` 保留，不push、不改其他worktree。

所有 Python／import／compile／pytest／mypy／build／GUI probe 由 root 序列置於 8 GiB、12 程序、kill-on-close 與 workspace mutex 的 owned Job。終態核對須為 remaining_job_pids=[]、forced_cleanup=false。測試只寫隔離根；未呼叫正式 writer、HTTP、訓練或 Task 重跑。沒有取得整個正式資料根前後快照，不宣稱主機背景排程期間所有正式檔案皆無變動；已核的來源／樣本 pins 依各 QA 原收據判讀。

## Windows Tasks 與真正依賴

2026-10-21 PDT 主機完整發現 224 個 Tasks，保留 21 個 Baldr／repo／FA_Data 相關項目；21 JSON／21 XML 逐檔 SHA 核對無失配。20 個啟用，Direct 預期停用。全部 cwd 為本 repo、Interactive／Limited、IgnoreNew、RestartCount=0、StartWhenAvailable=false；16 個 72h、3 個 1h、1 個 2h、1 個 5h。四個 hidden action 經 venv pythonw→固定 dispatcher→CMD，其餘 17 個 CMD；詳細 argv、principal、timeout、Last／Next／Result、寫入能力與來源根在 `windows/operations_matrix.json`，不是只核名稱。

| Task（均為 baldr- 前綴） | Last Result | 同次應用結果／限制 |
|---|---:|---|
| data-update-quick-daily | 1 | revision receipt 的 D DB 與現行 F 不同；custody 未接受 |
| official-market-events-daily | 0 | 同次 wrapper overall succeeded；不用舊單一 child 代替 |
| data-freshness-check-daily | 0 | degraded，Quick 失敗與來源日期落後 |
| ml-raw-pit-refresh-daily | 1 | 最新可讀是前日；當日同次終態不足，STALE |
| recommendation-snapshot-daily | 2 | cohort 部分涵蓋／frozen source 缺件 |
| evidence-pipeline-dry-run-daily | 2 | 工程／上游證據失敗，非正式 write mode |
| ml-promotion-evidence-daily | 0 | 上游資料更新 proof 未通過 |
| ml-promotion-authority-daily | 0 | skipped evidence unavailable，沒有 promotion |
| ml-allocation-copilot-daily | 0 | passed_rule_only，研究降級 |
| decision-evidence-capture-daily | 0 | 同次 passed；不授正式金融資格 |
| forward-outcomes-daily | 2 | outcome_price_missing，保留日期／horizon |
| recommendation-calibration-learning-daily | 1 | 同次 ML output junction 邊界錯誤；程式已修，未重跑 |
| recommendation-calibration-learning-banktaiwan-shadow-daily | 2 | current marker 的 cost scenario metadata 不可讀 |
| paper-execution-eod-replay-daily | 2 | 同次 dependency gate 拒絕 Quick／freshness 缺件 |
| pit-sector-membership-preopen-capture-daily | 2 | 正式 config 路徑身份錯誤已修；當日 config 仍缺 |
| paper-portfolio-daily | 2 | 同次 terminal 拒絕 output junction；不能借舊 passed child |
| ml-allocation-forward-daily | 2 | 台北 08:30 前無已驗 PIT archive，非 Task timeout |
| formal-pit-sidecar-postcutoff-daily | 2 | config 身份錯誤已修；日期與來源守衛保持 |
| formal-input-producer-daily | 2 | 同上，舊 09/09 config 不能充當 10/22 PIT |
| v2-2-weekly-collection | 1 | 10/18 同次週度 terminal 部分成功，degraded |
| ml-direct-chain-maintainer | 2（10/13） | 10/14 已授權停用；不啟用、不以舊失敗判新 drift |

實際收據支持 Quick→Freshness、Quick→Evidence／Promotion evidence、Quick＋Freshness→Paper EOD、Snapshot→G9、Promotion evidence→Authority、盤前 archive→ML Forward。sidecar→formal input 與 Paper EOD→formal input 是 config 宣告順序，不能當本日產物已到齊；BankTaiwan 共享 shadow source root 也不證明必須等 G9 訓練成功。兩個 08:25 台北工作共用喚醒時間，是否可消費仍由各自 cutoff／lock／receipt 決定。沒有僅按 trigger 先後推定依賴已完成，或發現可無條件並行同根 writer 的依據；未提高 retry 或頻率。

主機時區為 Pacific Standard Time，當時 UTC-07；兩個盤前 Task XML 為 `2026-10-02T17:25:00-07:00`。當季台北 08:25 換算相符，11/1 後實際 DST 行為 `UNOBSERVABLE`：唯讀 COM GetRunTimes 回 MissingMemberException。需在 Task Scheduler 分別開兩項「觸發程序／同步跨時區」並讀回 11/1 後 NextRun 的 offset，確認仍對應 UTC00:25；核前不改 trigger。Proxy 的環境／registry／WinHTTP presence 未啟用、Windows VPN 列表無連線；兩個 up tunnel adapters 不證明第三方 VPN 狀態，網路可達性未測。完整證據在 `windows/host_environment.json`／`dst_and_timeout_audit.json`。

沒有修改 Windows Task 外部設定。上述程式修復已進 Git；舊收據、正式 runtime binding 與 Quick revision receipt 都未修改。修復後的自然 run 尚未驗收，不為更新 LastRun 強制重跑 writer。

## Codex Automations 與每日 Recovery

已備份並解析全部 51 份設定：48 PAUSED／3 ACTIVE、8 heartbeat／43 cron，其中 48 份與 Baldr 相關。兩個 active Baldr heartbeat 分別是 `baldr-scheduled-evidence-morning-report`（文件化 Pacific 05:30）與 `paper`（06:20）；另一個 active 為無關 moomoo 任務，未改。三個相關 paused heartbeat 與舊開發 cron 保留暫停，重新啟用前須重新確認範圍，不能承接舊開發 prompt 自動寫 repo。

透過 Codex `automation_update` 實際更新上述兩個既有 prompt，加入動態發現、精簡 SSOT、同次原收據／SHA、Direct 預期停用、owned Python 限制、金融分軌及異常差異報告；例行 unchanged／等待保持安靜。QA009 讀回確認只變 prompt／updated_at，時間、狀態、target thread、通知與其餘 49 份 bytes 保持；沒有建立 automation。兩個 active 與三個相關 paused target thread 最新可讀 turn 均 completed，這不代表 pipeline 成功。完整 prompt、hash、cron 可讀 model／effort／cwd 與分類在 `codex_automation_audit.json`、`automation_update_verification.json` 和 before／after 備份。

heartbeat 的實際 model／effort／執行 cwd、平台 timezone 與未暴露的 cron run history 為 `UNOBSERVABLE`。若需核實，於 Codex Automations 開既有項目讀取時區與 recent runs，再開原 target chat 核模型／思考設定及專案工作目錄；沒有重新登入、改模型或新增費用。Windows 負責既有確定性 producer，兩個 Codex prompt 只讀收據，不重複執行 pipeline 或並行修改 repo。外部 prompt 更新無法只靠 Git 回復；原 TOML 與 exact prompt 已備份，回復應用原 ID 的 automation_update，保留時間／狀態／target，不能直接把設定檔當平台成功。

可執行入口：在合規 owned Job 執行 `scripts/audit_daily_operations.py <observation.json> --snapshot-sha256 <外部SHA> --receipt-root <raw根>`。本輪 21 元件與 20 份逐位元 raw 副本已實跑，stdout 在 QA012 command 2；支援的狹義 receipt 要求 run_id、started_at、完成時鐘及 status。不支援的 legacy schema 不轉造已驗 receipt：嚴格 CLI 為 DEGRADED 1／EXECUTION_FAILED 13／STALE 1／UNKNOWN 6，HEALTHY 0；人工按各原 schema 核讀的 matrix 另列，不互相冒充。舊來源 blocker 與 Task 非零可同時存在，pipeline 與程序原因分開呈現。

| 狀態 | 自動處理／Retry | 人工恢復與下游 |
|---|---|---|
| HEALTHY | 唯讀核對；不啟動 producer | 僅同次核驗元件可解除本 audit 的 hold，不授金融資格 |
| DEGRADED | 不 retry | 核預期停用／rule-only／成熟等待；下游保持 hold |
| STALE | 可重新查詢已有 metadata，不補跑 | 取正確日期／同次終態；不得改期或補造歷史 |
| BLOCKED_SOURCE | 不 retry／不改來源 | Quick 需既有遷移 custody、Bank 需可核 cost metadata、PIT 需合格 cutoff 前原件；依賴下游 hold |
| EXECUTION_FAILED | 不自動重跑 writer | 核 wrapper／環境／stderr，程式修復後等待合格自然 run；必要非冪等重跑另須授權 |
| UNKNOWN | 有界唯讀重查一次 | 取得支援 schema／run／SHA／時鐘；平台不可讀仍保留 Unknown，下游 hold |

目前 CLI 的 safe_retry 全 false、auto_action 為唯讀；復原動作由有權執行者依具名資料／範圍決策。日常規則以[唯讀 Runbook](../07_guides/BALDR_SCHEDULED_AUDIT_RUNBOOK.md)為準，配置及移機依[操作指南](../07_guides/SCHEDULE_OPERATIONS_AND_MIGRATION.md)。

## 文件治理、後續與外部接受

本次用既有 document_control 對 HEAD metadata 全量分類，起始 5,291 tracked／1,647 docs：313 current/contract/status、33 navigation、2 routing metadata、6 config/asset、217 target-only、590 dated evidence/navigation、486 historical。這是路徑分類候選，不是重新逐篇 EOF 語意驗收；Context 的 unknown／headings-only／預算略過保持原 metadata。深讀集中於 V2 Blueprint／驗收、月營收、Paper、runtime／scheduler、搬遷及 Roadmap 權責；已修 stale D 舊根與歷史包單位外推風險。

Snapshot、Index、Manual、現行架構、Runbooks 與此單一 QA 摘要同步。6M／長期版本／Target／Blueprint 已核，其 Gate、優先序與目標設計沒有變更，保留原標準；完整五旅程金融 PARTIAL 不升格。V2.1 及下一版本仍從[Roadmap Hub](../00_core/DEVELOPMENT_ROADMAP.md)、[6M 工程順序](../00_core/ROADMAP_6M_ENGINEERING.md)、[V2.1–V4.0 成熟度](../00_core/VERSION_ROADMAP_V2_1_TO_V4_0.md)進入，先完成具名來源／自然證據，不把 release 修復當 maturity Gate 通過。

外部待辦集中為：精確官方金額單位與逐用途資格、Paper 正式帳戶／資金／mark／cash／日曆批准、Quick 遷移 custody 與 Bank candidate 原件、當日 PIT 與 Forward 自然成熟、DST／平台未暴露設定核對，以及 Native 停止解除與 Owner 發布接受。Owner UAT 保持 `OWNER_UAT_NOT_PERFORMED`，Native 保持 `USER_STOPPED_ESCAPE`／`NATIVE_SMOKE_NOT_EXECUTED`；兩者不阻工程候選交付。累計額外 Credits 授權 12,500 未重置，任務支出 `USAGE_UNOBSERVABLE`。沒有 push、正式入口替換、資料清理、實盤或付費設定變更。
