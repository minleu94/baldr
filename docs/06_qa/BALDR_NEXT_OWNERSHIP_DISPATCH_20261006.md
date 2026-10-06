# Baldr 下一波精確 ownership 派工收據（2026-10-06）

本文件是既有 Astra／Sol 審核與唯一原 plan 的派工補件，不是另一條 roadmap。固定基準 **5d9ddf9d611bd6e117d75d0b4fdbf8751ee2e5a0**；開始審查時 tracked clean。下列是待父層鎖定的 proposal，本文未派新 thread，也未修改 production、tests、inventory registry。原核准 union 收據沿用，不全面重測。

## 可立即平行

父層已派 B01-H6/H7；本次另可立即派 **P1 Paper ledger custody** 與 **I20 inventory 首 20 檔**。P2 在 P1 API／commit 定版後執行；可以由同一 Paper Sol 接續，初期最多一位 LunaMax。中央主線可持有文件同步、P1/P2 dependency 整合與驗收收據；source_id 三檔仍等待直接人類批准，不做間接 workaround。

### P1：兩個 Paper ledger 的 selected route／每 I/O custody

**排他 ownership（兩個 production＋新增 test／QA）**
- app_module/paper_trade_ledger.py
- app_module/paper_equal_weight_benchmark_ledger.py
- tests/test_baldr_personal_paper_ledgers.py（新增）
- docs/06_qa/BALDR_PERSONAL_PAPER_LEDGERS_20261006.md（新增）

**實際入口**：PaperTradeLedgerRepository.__init__(db_path)、append/append_many/append_batch、list/list_transitions、schema_readback/_ensure_schema；EqualWeightBenchmarkLedger.__init__(db_path)、append/list。目前兩 ctor 都先 mkdir／SQLite schema 寫入，必須在這些副作用前分流。

**API 凍結要求**：保留原 positional db_path；新增 keyword-only route: PersonalStoreRoute | None、personal_paths: PersonalDataPaths | None。routed portfolio_id 必須 exact route.identity.key；benchmark_id 是另一個已知 caller 身份，不能用 portfolio_id 冒充；routed ledger 對 append/list 的身份都 exact 核驗。由 caller 明示身份的新 keyword 名稱／signature，在落檔前回中央及 P2。PERSONAL 缺 paths 拒絕；LEGACY_READ_ONLY writer 在 mkdir/schema/connect 前拒絕，reader 必須 mode=ro/query_only、不建庫。無 route 的舊 API 保持既有相容；明示配置的 CLI 必須由 P2 在接觸該 API 前 fail-closed，不讓 configured caller 偷走舊路。

重用唯讀 PersonalPaperStorePaths.from_route 與 PersonalStoreCustody：cost_ledger_db／benchmark_db exact path，main/journal/wal/shm 每次 connect 前驗；canonical 身份不變，只 I/O 用既有 extended-length renderer。驗所有 append_batch 原交易與 transition 原子性，不能拆 transaction。純 fee、現金、部位、Decimal／bp、schema、query、去重與成本公式不改。

**依賴**：基準既有 route＋selection.paths／custody API，不依賴 source_id 或 B01；P2 依賴此包穩定 API。
**驗收**：原 ledger 回歸＋新 routed synthetic 保存→新程序同 root/account/readback；未配置舊 caller 相容；missing paths、wrong domain/account/db、legacy-readonly writer、post-constructor hardlink/junction、sidecar alias、lexical alias、deep Unicode/emoji >260 拒絕或正向；每項負例先核沒有 mkdir/schema/新檔。保存市場及 legacy sentinel bytes/hash/mtime 不變。changed mypy/compile/quant，pytest raw＋JUnit 在固定 local commit 落地。
**禁止**：改 shared routes/paths/config/DTO、Snapshot repository、UI/main、Manual、正式 DB／資料搬移／Task／ACL／交易／模型；不能整個 private root 或任意 staging path 放行。

**worker prompt**：先讀 AGENTS 及原 plan，以固定基準建立專屬 worktree，只改以上四檔。先回 exact constructor／identity API，保留兩 ledger 原公式與 atomic transaction。做 isolated synthetic 新舊 API／custody 負例與 fresh-process readback；每 I/O 驗 exact path、sidecars、route mode／identity，補 >260。只交 owned local commit、blobs、raw/JUnit/hash、Manual 建議與限制，不 dev cherry-pick/push；共享 API 若需擴鎖先報精確檔與理由，不自改。

### P2：benchmark builder＋daily／benchmark CLI 的完整 selected routing

**排他 ownership（三個 production＋新增 test／QA）**
- app_module/paper_equal_weight_benchmark_builder.py
- scripts/run_paper_portfolio_daily.py
- scripts/build_paper_equal_weight_benchmark.py
- tests/test_baldr_personal_paper_producers.py（新增）
- docs/06_qa/BALDR_PERSONAL_PAPER_PRODUCERS_20261006.md（新增）

**四檔舊提案校正**：app_module/paper_portfolio_daily_runner.py 只有 PaperPortfolioDailyRunner.run 的純 Decimal 計算，沒有 I/O，保持唯讀。實際 benchmark 檔案出版是 Builder.write_new_ledger 的 mkdir→mkstemp→ledger→rename，不在純 daily runner。完整涵蓋兩個 CLI，最低是 P1 兩檔＋本包三檔，共五個 production，不能把第五檔隱藏成已接線。

**實際入口／API**：
- Builder.__init__(portfolio_id,benchmark_id,today_provider) 增 route／personal_paths keyword；preview/build_entries/commit/write_new_ledger 的原公開參數保持相容，commit confirm=False 原限制不變。state/baseline/benchmark 是 PersonalPaperStorePaths exact selected；market_db 是獨立只讀市場 caller，不能從 private root 推導。
- daily run(*,baseline_path,state_db,market_db,output_root,decision_at,calendar=None,now=None,ledger_db=None) 增 route／personal_paths keyword；先核 selected baseline/state/cost/status＋account，再有任何 status/mkdir/讀檔/connect。既有 Snapshot repository 的 route＋paths API 直接重用，該檔唯讀。
- 兩 CLI 用既有 config／selector 解析個人 mode/root，先拒 root-only/mode-only/blank/unknown 配置與 override mismatch；selected 模式忽略 legacy PAPER_EXECUTION_LEDGER_DB env，明示 path mismatch 拒絕。市場設定維持原 market config，不能重定向成 personal DB。selection 失敗只輸出錯誤，daily main except 不准掉回 legacy latest_status.json。
- 原 read-only helpers／baseline hash／cost projection 都每 I/O 驗 custody、用 renderer；不要先 resolve 掩蓋 alias。原 future decision、official calendar unknown、08:30 cutoff、query/schema/formula／200GiB 與既有 role reserve 政策保留，不另造 default 容量。

**staging 需明示**：既有 PersonalStoreCustody allowlist 不含任意 .tmp。daily 的 .latest_status.json.PID.tmp 與 builder mkstemp 的 .stem.*.tmp.sqlite 必須綁本次 generated exact temporary、selected target／parent、single-link／no-follow／sidecars，每次 I/O 檢查；不得擴整個 parent/root wildcard。Builder 不能把 arbitrary public db_path 轉成已核 staging。若需要擴 shared helper，由 worker 先交 exact API／檔案、等待父層鎖 ownership；不在本包偷偷改 PersonalPaperStorePaths。

**依賴**：P1 穩定 commit／signature；固定基準已有 B09 readonly consumers／Snapshot、selection/custody。無 source_id 依賴。
**驗收**：synthetic private baseline／原 fill ledger＋原 benchmark builder＋daily state/status 保存→B09 readiness/weekly 新程序同 account/root exact readback；市場 bytes/hash/mtime 與 legacy sentinel 不變。preview 不写，benchmark confirm false 拒絕；unknown calendar／future decision 不提高資格。CLI 配置錯誤／env/mismatch 不得 fallback 或 error-status 寫 legacy；post-preview/post-constructor swap、hardlink/junction/temp alias、publication race、deep >260、新程序 reader 均驗。只跑 affected Paper／CLI tests、targeted mypy/compile/quant；raw/JUnit 對 immutable owned commit，整合後必要的接線 subset，不重跑已核准四用途與 mandatory 全集。
**禁止**：改 pure daily runner、金融公式、shared storage/config/routes/DTO/main/UI、正式 Task／真資料／migration／ACL／交易；正式 writer 啟用仍未授權。此包只證明 synthetic selected chain。

**worker prompt**：採父層批准的 P1 owned dependency 到自己的 lane，鎖以上五檔，先回 builder/run 新 keyword API 和 exact temporary custody 設計。完整接兩 CLI，核 daily error handler 不落 legacy；沿原 producer／ledger／Snapshot 真實 synthetic 保存，不 stub 掉正向 writer。保原 confirm/calendar/cutoff/schema/hash/capacity／Decimal，完成新程序 consumers readback及 alias/override/errorpath/deep-path 負例，交 commit/blobs/raw/JUnit/Manual 素材，不改唯讀 shared 檔、不啟用 Task。

## I20：176 inventory 缺件的有限首 20 檔

**排他 ownership（只四個治理檔）**
- qa/full_app_healthcheck/test_inventory.py
- docs/06_qa/FEATURE_TEST_ROUTING_MATRIX_2026_06_23.md
- docs/06_qa/FULL_APP_HEALTHCHECK_COVERAGE_MAPPING_2026_06_24.md
- docs/06_qa/TEST_INVENTORY_HEALTHCHECK_CLASSIFICATION_2026_06_23.md

**精確 subset**：見下表。20 個檔案在固定 HEAD 存在且全在 missing_inventory_paths；source SHA／AST test count／imports／I/O 索引在同名 output/qa manifest。這些是 scope 證據，AST 的 append/connect 命中不自動決定 write-risk，也不代表已跑 pytest。worker 必須逐檔讀 fixtures／assert／執行入口，給分類理由與副作用位置；尤其 subprocess/producer 是否只 synthetic、GUI 是否真橋接，要照既有分類規則。

| # | exact readonly test path |
|---|---|
| 1 | tests/test_daily_market_cohort_main_bridge.py |
| 2 | tests/test_daily_market_cohort_projection.py |
| 3 | tests/test_daily_market_feature_snapshot.py |
| 4 | tests/test_daily_market_method_contract.py |
| 5 | tests/test_daily_market_research_bookmark.py |
| 6 | tests/test_daily_market_research_capabilities.py |
| 7 | tests/test_daily_market_research_screener.py |
| 8 | tests/test_daily_market_snapshot_consumer.py |
| 9 | tests/test_daily_market_snapshot_producer.py |
| 10 | tests/test_daily_market_snapshot_repository.py |
| 11 | tests/test_rule_research_benchmark_adapter.py |
| 12 | tests/test_rule_research_benchmark_integration.py |
| 13 | tests/test_rule_research_daily_owner.py |
| 14 | tests/test_rule_research_fair_boundary.py |
| 15 | tests/test_rule_research_fair_comparison.py |
| 16 | tests/test_rule_research_fair_comparison_cli.py |
| 17 | tests/test_rule_research_forward_isolated.py |
| 18 | tests/test_rule_research_forward_outcome.py |
| 19 | tests/test_rule_research_forward_outcome_reader.py |
| 20 | tests/test_rule_research_label_readiness.py |

**依賴／API**：只更新 TEST_INVENTORY 精確 path→既有分類與三文件對應數量；tests、production、runner、直接 bridge 名單皆唯讀。B01 label boundary 測試也唯讀，不借分類修 assert。P1/P2 新 test 等中央實際採入才另外登錄，不在本包先造不存在路徑。
**驗收**：只新增這 20 entries，舊 entries 值不变；direct bridge 精確 12 paths 不變、manual/legacy 不擅提升；三文件對應數量無漂移；scripts/audit_test_inventory.py --skip-pytest-collection --output-json output/qa/i20_inventory.json 的 filesystem=1281/inventory=1125/missing=156（固定基準且沒有中央其他採入時）、stale=0、documentation drift=0、overall仍 failed。若父層已採其他新檔，報基準→實際 delta，不硬湊數。collection skipped，不能宣稱全 pytest／全 registry PASS。需要 raw log/JSON/hash＋20逐檔理由及 base/head blobs；不得批量把其餘156歸 unit、放寬治理／排除清單或直接 runner。
**禁止**：動 test source、source_id 三檔、B01 guard、任何 UI／DB／正式執行／runner bridge／assert/xfail；不得把 missing inventory 宣稱產品 bug，也不跑全176。
**worker prompt**：固定 HEAD 建專屬 lane，讀四治理檔規則後只處理表中20。逐檔读 imports/fixtures/assert/CLI/subprocess 的真副作用，先列原類別候選／理由再寫 registry；不執行真資料測試。更新精確數量，capture skip-collection audit 與剩156 FAIL，commit 四 owned 檔，交差分/20分類理由/raw/hash。下一批由中央再鎖，不自行擴20。

## 邊界與中央接手

本輪文件審查沒有寫 DB、沒有跑測試，沒有新增 lane。基準已核四用途64、Workbench85、validator25/4skip、full-roots mypy839的證據沿用。原9stage／24UX、七有限 closed、性能例外、unknown／自然累積與正式啟用限制原樣保留。source_id 三檔直接批准尚未收到；本文不更改其鎖，也不建替代 caller 繞過。父層可立即派 P1＋I20；P2 收 P1 exact API 後由同 Sol 接續或另派。
