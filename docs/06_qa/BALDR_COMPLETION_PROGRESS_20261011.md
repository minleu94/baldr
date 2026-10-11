# Baldr 補完接續（2026-10-11，進行中）

完整需求仍依 [原補完計畫](../superpowers/plans/baldr_product_completion_plan_20261006.md)，保留 P00–P14、M1–M3、F01–F23 與 G0–G4。本文只記錄本次實作與驗證，不取代 Snapshot 或 Manual。起點為 `dev`／`04b35387`；原九份文件 dirty 保留。

## 排他分工

| Owner | 可寫範圍 | 出口 |
|---|---|---|
| p01_perf（Luna Max） | `personal_data_paths.py`、其測試；root 審查後另釋出 v4 query／測試的單一時段；隔離 QA | 先取 current-source 真 API profile，再依證據改善；原 300ms 不變；Main freeze 期間不可改既有來源 |
| f12_journey（Luna Max） | 新營收 Main 旅程測試與隔離 QA | 精確只讀 SQL 角色、真確認／收藏／關閉／新程序重開 |
| p08_daily（Luna Max） | 新 `strategy_paper_account_daily.py`／測試；既有 `paper_trade_ledger.py`／測試 | 同交易 CAS、有序 fills、零成交與跨 DB 重試；正式 quote clock 缺口保留 |
| root | 配置 DTO／service、新持倉情境 service／測試、共用 UI／文件 | 純規則入口沿既有金融計算，已選帳本研究情境保存、讀回及 UI |

## Root 實作前檢查

- 量化 guard 已執行，兩項靜態檢查通過；其白名單不等同新情境因果性證明。
- 情境只接受決策前已知的完整帳本狀態與行情；同日／未來狀態不授執行提案；未知持倉不得補零。
- 等權與明示目標沿既有整數 bp／Decimal 引擎。純規則入口不得建立假 model／dataset 身分，也不授 broker 或 rebalance 權限。

## 回滾清單

### 變更檔案清單

| 檔案 | 類型 | 摘要 | 回滾方式 | 風險 |
|---|---|---|---|---|
| `app_module/portfolio_allocation_dtos.py` | 修改 | 新增純規則請求／數值投影契約 | 保存當前差異並核對 owner，只還原本輪 diff／preimage | 移除後新情境入口無法 import |
| `app_module/portfolio_allocation_service.py` | 修改 | 現有計算共用於 Rule/ML 與純規則入口 | 同上；不還原其他 lane 檔案 | 須重驗既有 ML 配置回歸 |
| 新 `app_module/portfolio_research_scenario_service.py` | 新增 | 已選帳本研究情境 | 核對 postimage 和依賴後只移除本新增檔 | consumer 需同步解除 |
| 新 `tests/test_baldr_completion_p06_scenarios.py` | 新增 | 真限制／身份／因果性案例 | 同上，只移除本新增檔 | 移除會失去本輪回歸覆蓋 |
| 本文件 | 新增 | 排他 scope、證據及限制 | 核對 owner 後只移除本新增檔 | 交接證據遺失 |
| `docs/01_architecture/system_architecture.md`／`docs/00_core/PROJECT_SNAPSHOT.md` | 修改 | 新 API 的責任及未完成接線 | 只逆向移除本輪新增段／列，保留其他 writer 增量 | 交接狀態不同步 |
| `app_module/personal_store_routes.py`／`tests/test_personal_store_routes.py` | 修改 | 新情境 archive domain 與派生私人路徑 | 核對本輪 preimage／diff，只回滾新 enum／分支／案例 | 新 repository 會失去路由 |
| 新 `app_module/portfolio_research_scenario_artifact.py`／`app_module/portfolio_research_scenario_repository.py`／`tests/test_portfolio_research_scenario_repository.py` | 新增 | immutable 情境編解碼、明示保存及公開 exact reader | 保存 postimage，確認 consumer 解除後只移除本新增檔 | 跨程序研究讀回不可用 |
| `app_module/portfolio_research_scenario_service.py` | 修改 | 保存完整 input 以核 input hash | 只回滾本輪新增 input 契約／驗證 | 原 artifact reader 需保留相應 decoder |

### 回滾步驟

1. 比對當前 diff 與 `output/qa/baldr_completion_20261011/root/preimages/`，保存其他 writer 增量。
2. 僅逆向套用 root 差異；新增檔先核 postimage 及 consumer，禁止整個工作樹 reset。
3. 重驗配置與情境定向案例，不回滾任何市場／私人 DB。

## 驗收狀態

本輪尚未關閉任何完整工作包。單元測試、隔離合成旅程、原來源、同版 EXE、Native 與真人接受需分別登記；daily clock 缺口不能以合成成交補足。

### P06 純規則與情境計算增量

- 新增 `PortfolioRuleAllocationRequestV1`／`PortfolioRuleAllocationResultV1`。原 `project()` 保持 Rule/ML metadata 與 authorization 路徑；`project_rule_only()` 與它共用 `_project_weights()`，不建立 ML 提案或模型身分。
- `PortfolioResearchScenarioService.compare()` 只經 `read_exact(account_kind, portfolio_id, snapshot_id)` 讀一次完整帳本狀態，產生維持、等權及明示目標比較。候選排序固定，等權沿既有 Construction，所有風控與成本沿既有 Allocation。
- 純規則 result 綁實際配置 policy hash；comparison input hash 綁帳本、原來源 hash、aware cutoff、全部 context 事實、候選及目標。Health 未知、晚到資料、同日／未來帳本、跨帳本 context、缺持倉、錯股數／權重及缺候選價格均拒絕；不推定健康或空倉。
- 目前只完成計算 API 與 reader protocol。正常帳本 adapter、情境 artifact 保存／公開讀回、Portfolio／個股 UI、返回／新程序及 G3／G4 **尚未完成**，不得將此項列為 P06 或 M3 完成。

| 驗證 | 結果／範圍 |
|---|---|
| allocation service、新 P06 情境、Construction sandbox、Paper policy 四組定向 pytest | **56 PASS**；新情境 23 項、既有 allocation 20 項、Construction／Policy 13 項。Windows 沙箱對 `Path.resolve(strict=True)` 拒絕，改以核准的 elevated process 在工作區 isolated `pytest03` fixture 執行；未碰正式 DB。 |
| 3 個變更 source 的定向 mypy `--follow-imports=silent` | 通過；不宣稱 full repo mypy |
| 3 個變更 source＋新測試 `py_compile` | 通過 |
| `scripts/quant_guard_linter.py` 修改前／後 | 兩項靜態檢查通過；未納白名單的新檔另以 Decimal／因果性測試檢查 |

首輪 19 PASS／1 fixture PermissionError、次輪 40 PASS／3 failures 是本輪過程。次輪兩項新測試修正既有 diagnostic 名稱與缺少的 test ML proposal `coverage_bp`，沒有放寬產品門檻或刪除 assertion。最終 56 PASS 是同組定向回歸終態，不與前輪數字相加。

成功命令：`.\.venv\Scripts\python.exe -m pytest tests/test_portfolio_allocation_service.py tests/test_baldr_completion_p06_scenarios.py tests/test_portfolio_construction_sandbox.py tests/test_paper_portfolio_policy.py -q -o addopts= --basetemp=output/qa/baldr_completion_20261011/root/pytest03`。

### 接續依賴

1. P06 接完整、受治理的帳本／Health reader adapter；缺原 clock 的帳本不能自行填 availability。
2. 設計情境 artifact 的明示私人保存路由與版本 decoder，再接正常 UI；session store 只是記憶體上下文，不能冒稱持久化。
3. P01 現源單次 cProfile 為 641.909ms（插樁診斷，非 p95）。主要成本是 lstat、bounded reads 與路徑檢查；已釋出 narrow absolute builtin Path 候選，不把單次診斷當原 300ms Gate 通過。
4. P08 CAS 葉片的 11 PASS 是 owner 聚焦結果；root 審查要求 `rowset_hash()` 固定同一 read transaction 並補測。daily companion、UI 與正式 clock 尚待，不先收完整葉片。

### P06 情境封存與公開 exact reader 增量

- 新增 `PORTFOLIO_RESEARCH` route，派生 `{personal_root}/portfolio/research_scenarios.sqlite`；constructor／空庫讀取不建立資料、不 fallback legacy。明示 append 才建立私人 schema；writer 僅限 PERSONAL，兩種 legacy 模式均拒絕 append。
- `portfolio_research_scenario_artifact.py` 封存完整 account、request、contexts、三種原計算結果與 policy／source hash。編解碼只接受 canonical JSON、有限 Decimal 字串、整數與已知版本；重複 key、JSON float／NaN、缺欄／多欄、執行旗標、錯帳本／時鐘／input hash／row contract 都拒絕。單一 payload 上限 2 MiB。
- `PortfolioResearchScenarioComparison` 核 row universe、current／requested／target／executable 權重、gap、行情價格／名稱、成本合計、等權分配與 causal state。讀回不呼叫現行 Allocation／Construction 重算原研究。
- repository 在 `BEGIN IMMEDIATE` 內核 schema、append／冪等回傳；content-addressed ID 不覆寫舊情境，重試保留首次 saved_at。保存時間統一 UTC，帳本 kind／id 隔離。公開 reader 沿 custody、SQLite `mode=ro`／query-only，在同一 read transaction 核大小、內容 hash 與索引，再回 typed artifact；查詢索引最多 200 IDs，選取時仍需 exact read 核內容。
- 新程序回歸以另一個 Python PID、實體私人 SQLite 與正式公開 reader 讀回同份 input／result。前後 DB SHA 相同；這是隔離合成帳本，**尚非正常 Main、正式帳本／Health adapter、原來源、同版 EXE 或真人接受證據**。P06／M3／G2–G4 仍未完整完成。

| 驗證 | 結果／範圍 |
|---|---|
| 新封存、P06、Allocation、私人 route、Construction、Paper policy 六組定向 pytest | **132 PASS／6.29 秒**；新封存 53 項、P06 23 項、Allocation 20 項、route 23 項、Construction／Policy 13 項。核准 elevated process；fixture 只在工作區 `output/qa/baldr_completion_20261011/root/archive04`。 |
| scenario service／artifact／repository 的定向 mypy `--follow-imports=silent` | 通過，3 個 source；不外推 full repo |
| 同三個 source＋新測試 py_compile | 通過 |

首輪封存回歸為 61 PASS／3 failures：保存 API 回傳未正規化的候選 tuple 順序，與 canonical decoder 回傳不同。已修正 writer 回傳為實際封存 payload 的 typed decode；原金融結果／hash 未重算。次輪 107 PASS；最終加入單一 read transaction／query-only、超大 BLOB 在 decoder 前拒絕、未知 schema 不修復等案例後為 123 PASS，不累加各輪。

成功命令：`.\.venv\Scripts\python.exe -m pytest tests/test_portfolio_research_scenario_repository.py tests/test_baldr_completion_p06_scenarios.py tests/test_portfolio_allocation_service.py tests/test_personal_store_routes.py tests/test_portfolio_construction_sandbox.py tests/test_paper_portfolio_policy.py -q -o addopts= --basetemp=output/qa/baldr_completion_20261011/root/archive04`。

Subagent 唯讀審查另找出三項契約缺口，root 已修正後取得 132 PASS：限制私人 writer；拒絕 target／executable 中不在原 rows 的隱藏 0／正 bp 股票；schema 強制 covering index 的欄位及升降方向。新增拒絕負例、query plan 不使用暫存排序及兩個 writer 同時首次 append 的原子／冪等回歸。沒有定義自動刪除／保留配額；完整歷史可持續增長，現階段只證明單 payload、索引 read 與返回 ID 數的界線。實作前的 raw fixture／code SHA 保留，不作現行 schema 等價宣稱。

下一步仍是正常帳本／Health reader 的 exact source 與可得時鐘、Portfolio／個股 UI 接線、保存理由／返回／Main 新程序，以及完整 G3／G4。沒有以 caller 填的 SHA／時間推定真實來源；content hash 只證明封存完整性，不授資料資格。

另有既有金融契約限制：`CausalPortfolioState.v1` 與本 AccountState 要求正 bp 持倉；股數為正但整數權重為 0bp 的微小持倉不能完整表達。adapter 不得省略此持倉後產生情境，須明示來源與 blocker；完整 P06 仍需處理此情況。本輪沒有放寬既有 Rule/ML kernel 的 causal universe。

### P06 同帳本快照身分修正

Context 原僅核帳本 kind／id、股數與 bp；同帳本不同快照若持倉相同仍能混入。修正將 context 的 `snapshot_id` 納入必要輸入與 hash，並與 exact account／request 快照一併核對。比較 payload 與 input schema 升為 v2；舊 v1 缺快照耦合，公開 decoder 拒絕而不猜補身分、不改寫舊 DB。保存 store schema 維持 v1，因 SQL 欄位及索引未變。

回滾面僅限 scenario service、artifact codec 與兩個 scenario／repository 測試檔；preimage 保存在本機排除的 `output/qa/baldr_completion_20261011/root/context_snapshot_preimages/`。回滾前保存 postimage 並確認 consumers；只逆向本次增量，不回滾其他 writer 或市場資料。此修正不改金融計算或可得時鐘：所有 context 仍須在 cutoff 前已知，未知 Health 仍拒絕。根據因果自查，不以快照日期冒充保存／可得時間。

六組定向回歸本次 **140 PASS／6.75 秒／native exit 0**，比上一版本多 8 項負例／身分回歸：同帳本不同快照且持倉相同仍拒絕；完整更換快照身分會改 input hash；空白／非 canonical 身分拒絕；decoder 拒絕 v1、缺身分與錯快照；public reader 對 v1 payload 拒絕並保持 DB bytes 不變。另一個 Python PID 讀回的 fixture 亦隨新 payload 重驗。3 個 source 定向 mypy、4 檔 py_compile、修改前後量化靜態 guard 通過。命令沿前述六組測試，basetemp 改為 `output/qa/baldr_completion_20261011/root/context_snapshot01`；不累加前輪 132 PASS。此 backend 修正尚未接正常 UI、真帳本／Health 或完整 P06／M3 Gate。

### P06 精確估值契約

現有配置引擎從 NAV × cash bp 重建現金，而 bp 僅有萬分之一精度；真帳本的 Decimal 現金不能由此還原。新增 `portfolio_research_valuation.py` 與對應測試，保存完整股數、價格、市值、現金及 NAV，核 NAV = 現金 + 全持倉市值，保留正股數但顯示 0bp 的持倉。bp 只作明示確定性的近似顯示，不授資金、帳本可得時鐘或成交能力；後續須沿同一 Allocation 引擎接 exact monetary state。

| 檔案 | 類型／回滾 | 風險 |
|---|---|---|
| `app_module/portfolio_research_valuation.py` | 新增；保存 postimage 並確認 consumer 後僅移除此檔 | exact 估值 consumer 失去契約 |
| `tests/test_portfolio_research_valuation.py` | 新增；同上只移除此新增測試 | 失去資金守恆／微小持倉回歸 |

新增檔不改 Main 凍結來源；沒有修改正式帳本或捨棄持倉。金融自查：只核 caller 已取得的同份 snapshot 事實，不取未來行情；此 value object 不替來源 clock 或 Health 核驗背書。回滾須先解除 consumer，再核本次 postimage，不還原其他 writer。

估值契約定向案例 **32 PASS**；與已審閱的初版取消能力 7 項合跑為 **39 PASS／1.26 秒／native exit 0**，不與之前各輪相加。32 項涵蓋 exact 現金、NAV／全持倉守恆、同 bp 不同分金額的 hash 差異、微小 0bp 持倉、確定性最大餘數顯示、低 Decimal precision／Emax、未知列、股票 bp 損壞、重複持倉、數值／股數／列數界線。金融核心輸入拒絕 float／非有限 Decimal／分以下金額；乘法沿既有 `quantize_money` 並使用獨立 Decimal context，顯示 bp 沿整數分計算。2 個 source 定向 mypy、4 檔 py_compile 與量化靜態 guard 通過。

`PortfolioResearchValuation.from_snapshot()` 現可核正式 snapshot DTO 的完整估值，但不自行開 DB、不把收到 DTO 視為來源認證。尚未接替現有 Allocation 的 bp 還原金額路徑；現有情境 AccountState／causal v1 的微小持倉 blocker 仍有效。下一步須新增完整 monetary causal contract、沿同一引擎接精確金額，以及受治理的 exact source／availability reader，不能用新 value object 單測代替真帳本閉環。

### P06 精確金額接入（後端增量，完整接線仍待）

Root 單一 writer 接 Causal state 的版本化 monetary payload、同一 Allocation 引擎的 exact 現金／股數／市值及實際風控核對，並將 P06 AccountState 明示完整估值。舊無 monetary state 的 Rule/ML 請求維持原路徑；完整新情境不從顯示 bp 還原資金。新的比較／input payload 需升版，缺真現金的歷史 payload 不猜補。

回滾清單：Allocation DTO／service、scenario service／codec 與兩個 P06／archive 測試只逆向本輪 diff；新 exact-money 測試在核 postimage／consumer 後移除。六檔 preimage 保存於 `output/qa/baldr_completion_20261011/root/exact_money_preimages/`。回滾風險為新 monetary consumer 失去契約，須先解除 consumers，並重驗既有 ML／Rule 與情境；不覆寫其他 writer、不碰 DB 或市場來源。實作前後量化 guard 與因果負例必須通過，已知資料仍受 exact snapshot／aware cutoff／T−1 限制。

本節更新前述「尚未接 Allocation」的歷史狀態：`CausalPortfolioState.v2` 現綁完整估值；新 AccountState 必須保存實際現金、NAV、所有股數／mark price／市值。無 monetary state 的 v1 Rule／ML 請求沿既有計算；valued 請求沿同一 Allocation 引擎使用實際資金、整手／流動性／成本，並以成本後 NAV 核現金下限、實際單股／產業曝險、正股數持倉數與 hard exit。計算使用獨立 Decimal context，bp 仍作目標與既有再平衡政策單位，不能反推現金或忽略微小持倉。

比較／input schema 升為 v3；舊 v1／v2 缺完整金額證據，decoder 拒絕而不猜補或自動改寫舊 DB。政策 hash payload 升為 `portfolio-allocation-policy.v2`，明示 weight-derived／exact-money-post-cost-NAV 計算版本及原政策／成本／成交限制；不沿用舊 hash 冒稱新算法相同。封存讀回另外核完整 final valuation／顯示權重、按股數變化的現金守恆及此 v3 固定買 25／賣 55bp 成本，不重新執行當下 Allocation 或讀 live 行情。超過 10,000 列的估值先拒絕再建 DTO。

子代理唯讀審查發現零 bp hard exit 的 Advice 分類原先按 bp 遺漏，現按實際股數回 EXIT_CANDIDATE，完整可執行欄位仍在退出未完成時拒絕。非硬退出的小額持倉仍受既有再平衡 band／minimum trade；cash-only target 不代表強制清倉。保留的 0bp 持倉須在 executable contract、股數／市值、HOLD 與具名 retention diagnostic 中完整表達，不能顯示成已無持倉。

過程：首輪新金融案例 **79 PASS／1 failure**，原因是測試行情成交量上限先把目標增量截回 0bp；改為具名高流動性 fixture 以隔離真現金邊界後 **80 PASS**。八組回歸 `exact_money02`／`exact_money03` 均 **203 PASS**，最後一次 7.78 秒／native exit 0。接著增加 caller Decimal context 與小額 retention 兩例，三組定向 **82 PASS**；八組最終 **205 PASS／7.94 秒／native exit 0**。各輪數字不相加。

最終包含 frozen 金額損壞、成本後 cap、cash floor、買賣成本／守恆、同日／未來拒絕、caller context 獨立性及新 Python PID exact reader。收據 `output/qa/baldr_completion_20261011/root/exact_money_final01/receipt.json` SHA-256 `23c5584ce567a44c1db8557d054c172f44c2e264c96ff5aacff47c044983ce4d`：15 個來源／測試 byte pins 起訖相同，fresh reader PID 50928，隔離 DB SHA 前後均為 `9688541136c189d944110edcf365157a99647a35a65c50784af121646dde503e`，保存 clock 字串保持 UTC。六個 source scoped mypy、九檔語法、量化 guard 與 root scope diff check 全部 native0。全工作樹 diff check 另指出其他文件整理 owner 的 Archive EOF 空行，保留而未覆寫；不冒稱全樹 clean。Full UI／Main／原來源／新 EXE／真人與正常帳本／Health adapter 仍未完成。

### P08 審查接續（尚未接受增量）

Root 已讀 daily writer 全文與 ledger CAS 主流程。Owner 的 ledger 14／daily 9／cash seed 17 PASS 仍是 owner 聚焦結果；尚未 root 完整收取。審查要求先證明／補足以下缺口，不以 `performance_eligible=False` 取代金融核心核驗：

1. Caller fills 的費用、滑價與數量須核 exact binding policy／成本模型；目前只保存 hash 並做現金／股數 replay，不足以證明計算符合政策。
2. Quote event／cutoff 須與台北 execution／snapshot 日期及下一官方 session 契約一致；self-hashed sidecar 不能授正式行情時鐘。
3. Prior seed 的 `seed_created_at` 必須在決策 cutoff 前；daily prior 需實際 writer 保存／可得 clock，不能以 caller `mark_cutoff` 代替。
4. 後續 target→fill 若以開盤成交模擬，不能使用事後才完整的當日成交量。正式前向與明示 EOD replay 必須遵守各自因果邊界。

上述審查階段先由 owner 只讀盤點負例／既有 public API／最小修正範圍；沒有因此啟動正式 writer、Task 或 collector。

接續只讀負例已重現三項缺口：1,000 股非零買進而佣金／稅為零仍 append；quote event 的台北日期早於 execution date 仍 append；seed 保存時間晚於 decision cutoff 仍作 prior。root 已釋出新 daily／測試與可新增的 availability companion 範圍，先修時計並準備共享 producer engine 的精確 patch；既有 producer／seed writer／ledger／Main pin 暫不擴寫。成本模型、官方 event／calendar 與完整策略 persisted signal 的資格仍需補足，不把研究 replay 或 caller hash 當正式績效。所有正式 writer／Task／collector 保持未啟動。

### F12 聚焦 Main 旅程的本次終態

原 session `83137` 經同 handle 收取為 **exit 1／1 failed／1214.47 秒**，不冒稱 PASS 或測試 deadline timeout。Main 初始化最終完成，但 COW 按鈕不啟用；來源選擇回報 `personal_watchlist_source_unavailable`，尚未進 COW／catalog／query／fresh child。此前子代理工作區路由逾時不是程序終態；root 在 08:19:38 UTC 的 elevated CIM 確認 observer 可見且 exact runner tree（32848→52112→39552）已不存在，後由 owner 收取 pytest 終態。原來源 guard 保持。

根因仍需核 fixture：PROFILE=test 會使 output_root 加 `/_test`，而 test source 預建於未加後綴的路徑。先做小型配置／resolver 探針，再修自身 fixture；另加初始化階段 log、faulthandler 與明示 deadline，避免無界初始化觀察。未因 poll 逾時重啟、不用失敗 fixture 宣稱正式產品缺陷；新 Main candidate 須重新凍結來源再驗。

### P01 正式取消能力接線與整合驗證

前一 goal turn 僅回覆使用者進度，分類為 no progress；本輪核對當前 dev 後，root 審閱並套用六檔 Event qualification 候選，保留完整補完範圍。正式 TaskWorker／v4 View／query 與三個回歸檔在套用前逐檔核 base SHA，前版本及回滾表保存於 `output/qa/baldr_completion_20261011/root/p01_apply_2f16e38ff9ad4d1dbcbd6987b43a1a36/`；包含原 query／測試未提交增量，不以 HEAD 還原覆寫它們。

候選 patch SHA 為 `a44d8bcb3284ddb40dcfdbdd0ac5a993954e0b91c7b73f5c52283660bedc8abf`。`git apply --check` 通過；套用後 raw SHA 差異來自 newline，root 先斷言六檔 normalize 後文字與 pinned candidate 完全相等，再寫回原 candidate bytes，使六個 raw pins 與 manifest 相符。純 Python 能力模組與測試保持原候選版本。

TaskWorker 只在明確 opt-in、exact worker／原 method／Event 身分與未被 caller 提供的 callback 下發行能力；Event 方法不合格仍用原 callback 執行，不將 helper TypeError 當成任務失敗。v4 View 的選版／查詢／換頁／返回將同一 callback 與一次能力傳至 public reader。多 artifact 有界讀取保留 fresh I/O、原結果／錯誤順序、獨立 path memo 及 worker 自然排空；自訂回呼仍走序列路徑。沒有修改金融計算或來源資格。

| Root 驗證 | 結果及界線 |
|---|---|
| 純能力＋真 TaskWorker | 50 PASS；收據版重驗 1.82 秒／native0，八個 source／test raw pins 起訖一致。包含 positional callback、不以 kwargs 自動 opt-in、worker／Event override fallback。 |
| 更新工作台強制回歸 | 85 PASS／4.06 秒／native0；原測試未刪。 |
| 更新頁 validator | 25 通過／0 失敗／4 跳過／native0；合成 Temp 資料，不代表真下載或正式資料更新。 |
| 全範圍 mypy | 首輪 950 檔僅 P08 候選 daily JSON None 型別錯誤；交 owner 收窄後第二輪 950 檔通過／native0。保留首輪失敗；此結果不授 P08 金融／來源接受。 |
| 八個變更 Python 語法 | native0。 |
| 正式 query＋v4 View 全組 | session79511／pytest PID24644 執行中；尚未取得終態，不授整合通過。 |

Root raw 收據由 `output/qa/baldr_completion_20261011/root/run_p01_review.py` 保存 command、UTC 起訖、child PID、八個 raw source／test SHA 及檔案 log。stdout／stderr 直接寫專屬 regular file，沒有未排空 PIPE。觀察期限若到期會記 live_after_observation_timeout，不推定程序死亡；需沿原 handle／exact PID 核程序樹，不盲目重跑。

Manual §6.7 已同步背景讀取、取消後保留已核結果、晚到結果隔離與安全收尾；架構記錄程序內能力及序列 fallback 邊界。原千檔 filter p95 超過 300 ms 仍有效；完整 matrix、正常 Main／原來源／EXE／真人與完整 P01 Gate 尚待。P01 owner 接續 scratch 追加開始後取消、九個以上 artifact outstanding 上限與正常 TaskWorker matrix，未授權先跑重型 matrix。

### P08 Decimal context 審查負例

Root 在 availability source SHA `7429d5d047636fb9c4d7553f51fd98255ac0f2016594b13b960252ebcec2948d` 上只呼叫純 helper：同一合法 `500000.00`，caller Decimal precision 28 接受，precision 3 卻回 `root_cash_precision_invalid`。收據 `output/qa/baldr_completion_20261011/root/p08_decimal_context_probe01.json`；未開 DB。完整 snapshot 加總／估值／bp 核驗也仍使用 caller context，已交唯一 owner 補獨立、有界 Decimal 核驗及低精度正負例。Owner 前版 30 PASS 不涵蓋此缺口；新版金融資格尚未 root 接受，成本與 account-aware producer 候選仍續辦。

### F12 supervisor 聚焦更新

Owner 配置探針已確認 PROFILE=test 的來源需位於解析後 `output_root/_test/watchlist/default.json`；不合格舊路徑保持拒絕。小型 supervisor fixtures 為 2 PASS／2.26 秒：create-only regular log 寫入 3,145,945 bytes 且沒有 PIPE，專屬 suspended Windows Job 在 deadline 後清理其五個成員 PID。這些是 owner 小型證據，不是完整 Main／query／保存與 fresh child。舊失敗封套保留；root 審讀另要求 fresh child 改為 bounded log 與相同 owned tree 管理、明示 startup 隔離環境及新的來源 freeze。完整 Main 仍未釋跑，不關閉 F12 Gate。

### P01 query／View 終態與精確修正

Root 沿原 session79511 收取 terminal native exit1：**30 PASS／1 failure／609.08 秒**；八個 source／test raw pins 起訖相同。唯一失敗在 `test_p01_parallel_child_read_round_is_bounded_equivalent_and_keeps_fallbacks`：測試在 strict_page 賦值前比較 DTO，traceback 明示 UnboundLocalError，不能當成產品 reader 通過或功能缺陷。

已保存兩檔 preimage 與回滾表於 `p01_apply_2f16e38ff9ad4d1dbcbd6987b43a1a36/terminal_fix`。Root 只將 capability／strict DTO 完整比較移到 strict_page 賦值後，未刪除 assertion；另將 Worker 新增三行註解改為繁體中文，沒有 runtime 變更。精確失敗 node 重驗 **1 PASS／6.09 秒／native0**，收據 `output/qa/baldr_completion_20261011/root/p01_exact_fix01_9ca2bb8ec2e24cba8033bb28e0e63e38/receipt.json`，八 pins 不變。原全組的其餘 30 項不重複累加，這兩次證據合計覆蓋原 31 個獨立節點；不宣稱同一次全組全部綠燈。

註解修正後純能力＋真 Worker 重驗 **50 PASS／1.34 秒／native0**，收據 `p01_worker03_bf5e91f557a340f48d291351c4095434/receipt.json`；八檔語法 `p01_compile02_28fe736a237743d5b1f3f1317224a76e` native0。量化靜態 guard 兩項通過；它不代替新金融來源的因果與精度核驗。P01 owner 正準備執行中取消與超過八個 artifact 的 outstanding 上限回歸；兩測試尚未 root 接受，完整冷暖矩陣及原300ms Gate仍未閉合。

上一 goal turn 新收取特定 session79511 的終態與完整 failure trace，證據確認下一修正動作，分類為 progress；本輪已修正式測試順序並精確重驗。完整 P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4 範圍保持，沒有完整包結案。

### P06 完整封存成本核驗的 caller context 修正

Root 對已提交情境 codec 追加完整 encode／decode 回歸，caller precision 分別為1／3／28，Emax=1、Emin=-1並啟用 Inexact trap。修正前同份合法 frozen payload三例均於 Comparison 成本列加總拋 Decimal Overflow；另純記憶體 precision1探針重現成本比較 ValueError。原205項主要覆蓋 Allocation／估值的獨立 context，未覆蓋這段 Comparison 加總，保留原成功範圍與此次反例。

Root 只將封存成本加總包在 `localcontext(Context(prec=60))`，既有完整結果比較、成本／現金守恆、身份／clock／hash／政策均保留。未讀行情或重跑當下 engine，payload v3格式與算法政策未變；同一封存的 bytes/hash不變。修改前preimage與標準回滾表在 `output/qa/baldr_completion_20261011/root/scenario_context01/`。

精確三例重驗 **3 PASS／0.75秒／native0**；接續八組完整定向回歸 **208 PASS／10.66秒／native0**，不與前輪205或本輪3累加。收據 `output/qa/baldr_completion_20261011/root/scenario_context_final01_a09be89bd3b7459aa10722fbb47c648a/receipt.json` 保存command／UTC／child PID11144、15個source／test起訖SHA，pins一致。兩檔compile與source定向mypy通過，量化guard兩項通過。正常帳本／Health可得時鐘、UI／Main／原來源／EXE／真人及完整P06／M3／G2–G4仍待。

### 產品剩餘範圍與 P01 追加終態核對

Root 收取原 session80658 終態：執行中取消排空與超過八個 artifact 的未完成工作上限兩測試 **2 PASS／21 deselected／130.56秒／native0**，八個 source／test raw pins 起訖一致。收據 `output/qa/baldr_completion_20261011/root/p01_additional_tests01_f19220a90fe2426abc6d657150d8f23a/receipt.json`，child PID32044。正式 query 測試追加後語法檢查 native0；前輪全範圍 mypy 950檔 native0 的12個受核 pins 一致，收據 `completion_mypy01_360becf725a746d1ae57bfc0570ffd34/receipt.json`。這補足前節兩測試待接受狀態，仍不代表正常千檔冷暖矩陣或原300ms門檻通過。

P08 owner 回報 daily／availability 新版38 PASS／223.73秒／session19119 native0；此為 owner 證據，公開 exact checkpoint reader、共用 producer 與 root 完整審查仍續辦，尚未授完整P08／M3。F12完整 Main／fresh child 仍待候選凍結與 root 釋跑。

依原計畫與現況，剩餘工作可整理為六類：完整母體效能及共用查詢；其他資料域與策略定義；正常 UI／收藏／返回／重開；持倉情境與策略獨立帳本／績效；自然結果與維運終態；同版 EXE、Native 與3–5位真人接受。P00–P14全部仍有完整驗收缺口；M1／M2已有有限旅程，M3剩餘實作最多。此分類只供狀態說明，不重定義原工作包、條件或Gate，也沒有可核完整完成率或日曆工期。

### Root 保存與正常讀回審查接續

已核定的15個P01取消／有界讀取、P06完整codec精度檔案與五份操作／架構／狀態文件保存於本機dev `7dba5f82`。Stage前重核兩份final receipt共23個source／test pins全部相符，cached範圍精確且diff check native0；其他owner dirty候選保留，main／push未動。本提交不關閉任何完整工作包。

P08公開checkpoint reader靜態審查發現：用marker的歷史rowset_after比對當下完整rowset，後續合法成交後會拒絕原checkpoint；多次ledger public calls亦各用獨立連線，尚未證明同份read snapshot。已交owner先收session92496終態，之後補真兩日writer歷史重開與same-BEGIN exact ledger候選；新40節點結果即使綠燈，也不涵蓋這兩項尚未補入的契約。

F12候選freeze `96b184032190863d8aeaa97be0539a41a55028a5aa10e06ec3076c8b839c0607` 的58 formal＋5 harness pins由root重核全部相符。新startup audit對任何file URI無條件拒絕；root隔離probe在QA普通DB建立後，以其合法mode=ro URI讀取，取得 `F12 write guard 拒絕未解析 SQLite URI`。receipt位於 `output/qa/baldr_completion_20261011/root/f12_uri_probe_58357112669d401caadff4b9b5c6bc41/receipt.json`，harness raw SHA `7799cca2ae3a29e098cdca1d4781a6f74dedb336a6953d8a551b1a7605c56d1f` 起訖相同。Probe最後stdout受cp1252輸出限制拋UnicodeEncodeError／native1，receipt已先寫入；這是拒絕實證，不稱PASS。已要求owner補精確私人／受核合成唯讀URI及外部／歧義拒絕案例，重新freeze後才釋完整Main；未碰正式SQLite或舊失敗來源。

### P06 策略 Paper 完整帳戶 adapter 候選

新增 `portfolio_research_account_reader.py`，從使用者明示strategy/version/namespace/operation/snapshot與本次aware cutoff讀公開checkpoint。公開reader核完整帳本／clock後才建立AccountState；source hash綁binding、snapshot、base receipt、availability與ledger operation，未收caller hash、不推Health、不猜latest或現金。錯kind／portfolio／snapshot拒絕，晚到availability不能用於舊決策。因果自查及回滾清單於 `root/account_reader_preimages_01/`：沿原exact source及完整Decimal valuation，沒有新行情、公式或writer。

Root首兩輪各為2 FAIL／5 PASS（13.01秒與11.55秒），原因依序為測試引用writer結果不存在的snapshot欄位、valuation不存在的cash欄位。修正為獨立完整現金／NAV／股數／mark／市值與writer available_at數值oracle；原失敗不抹除，未減assertion。第一輪受控runner又在test helper建過長Windows路徑前失敗6 FAIL／1 PASS／0.80秒，17pins一致，收據 `account_reader_final01_ed9847dabcb8435abd6145176a0bf79a`；不是產品來源拒絕。改用既有短隔離QA basetemp後，完整七節點 **7 PASS／10.08秒／native0**，收據 `output/qa/baldr_completion_20261011/root/account_reader_final02_4b1fc7526aa34554a3c1d87d92ea3fb1/receipt.json`，child50644，17 source/test pins起訖一致。隔離state/ledger DB bytes讀取前後相同；source定向mypy、兩檔compile及量化guard兩項native0。

此候選只支援策略Paper source，依賴P08未提交reader；Health、manual/user_declared source、正常UI/Main、原來源、同版EXE、真人與完整P06/M3仍待，不以七測試關閉工作包。

### F12 URI修正的root小型證據

新版startup guard允精確QA/run/synthetic的mode=ro URI並強制query_only，private mode=rw限制QA/run；外部、歧義與未明示uri=True拒絕。Root同款隔離URI probe native0，收據 `root/f12_uri_probe_2049ed31edb6497c94ee25b8f061f268/receipt.json`，harness SHA `29231ffd60a4daab1d7757c01fc33c0849e4b6dc78c3f5a4a618e937f14daf76` 起訖相同，補足前輪誤拒反例。

Root小型六節點native0／6 PASS／2.79秒，但執行中journey test source變更，63 pins核驗不一致，runner因此拒絕接受該freeze。原收據 `root/f12_guard_supervisor01_abdbe981539a4c418149dac0d80d9201/receipt.json` 保留；不稱同一凍結候選PASS。Owner完成修改後重新freeze，root再核及精確重驗；Main仍未釋跑，原deadline及來源限制不變。

### F12 固定來源與最終小型回歸接續

Root 最終小型回歸收據 `root/f12_guard_supervisor02_9e04fba9f9354cff97d2eb86416afa93/receipt.json` 為 **10 PASS／2 deselected／3.01 秒／native0**，63 個來源／測試 pins 起訖相同，涵蓋 URI、環境、Job 清理及查詢期限服從總期限。這補足前輪執行中來源變更的拒絕；完整 Main 與原 resolver 節點不在這十項範圍內。

Owner 的來源重驗曾將 sandbox／長路徑讀取失敗判為三個 bundle 檔案缺失，原診斷保留。Root 改以核准的唯讀程序及 Windows extended path 直接核 bytes：原 `synthetic_main_42f484b9f27b47328b7d268a866cc755` **17／17 檔案 SHA 與大小相符、20／20 目錄存在**；收據 `root/f12_inventory_readonly_c6b32e82ac9a43c39713ae29aba23062.json`，沒有來源寫入。另由正式 catalog 在相同原根執行 native0 預檢：scan complete、唯一一筆可 exact-read、declared count 258。無須修復或重建原來源；已停止替代來源重建，部分 QA 根與失敗日誌保留。此證據解除來源缺檔誤判，仍須最終 freeze 與一次有界 Main→保存→正常關閉→新程序精確重開驗證，尚不授完整 F12 Gate。

本次 goal turn 接續前一輪的來源核驗進展；P08 公開 ledger reader 候選審查另發現 operation payload hash 必須由 repository 自行重算、transition fill order 與 foreign portfolio prefix 必須明確核對。候選尚未套用，不把暫時跨模組私有 schema 讀取當成正式架構完成。

### F12 固定來源 Main v3 終態與診斷缺口

Root 重核 v3 的63個候選 pins，另加入實際載入的 task_cancellation 依賴，共64個；原42f來源17檔與月營收14個來源／sidecar觀測均納入前後守衛。釋跑一次有界正常 Main，收據 `root/f12_main_v3_01_f43c9ac6902e4761b7442febc946a8d9/receipt.json` 記錄 terminal native1；外層測試1 FAIL／11.02秒，內層1 FAIL／6.98秒。Main 初始化完成5.469秒，收藏啟用按鈕 enabled，但點擊後仍為 personal_source_readonly，尚未進入查詢／保存／新程序。所有64個source pins及來源觀測前後一致。

專屬 supervisor 收據 `output/qa/f12_resume_20261011/main_candidate_c29656ee9ab140c0a9f1b6db4066adc7/supervisor-receipt.json` 記錄 owned Job 程序樹已關閉、最後active count為0、沒有逾時終止。這是失敗後程序清理證據，不是完整正常關閉旅程通過。舊log未保存 handler 捕獲例外所在的status_label，因此不能宣稱已定位錯誤；正式COW流程沒有mode=rwc，不放寬guard。接續先補正常頁面導航、可見按鈕滑鼠操作及有界標籤診斷，再以正式元件小型探針追因；不原樣重跑完整Main。

### P08 公開 exact reader 的原始列格式反例

Root 對候選reader以獨立合成帳本實際append成交／transition；只把fill的schema_version改為wrong-fill-schema，重算raw rowset_after及marker hash，沒有變動operation payload。候選read_exact_daily_operation仍接受，DTO重新顯示paper-trade-ledger.v1。探針native0，兩候選source／test pins前後一致；收據 `root/p08_schema_probe_0eb89b8b10d547819d68eb8001156246.json`。這證明目前22項owner候選測試尚未覆蓋原始fill schema的拒絕，不將其當完整reader接受。

已交唯一owner在解碼前明確核對schema，並審查原始SQLite整數／flags／文字是否被轉型掩蓋；新增重封schema負例後再交不可變base/post manifest及patch。正式ledger未套本候選。Owner daily／availability首次47節點回歸在過長basetemp建檔時取得44 FAIL／3 PASS、session78437已native1終態；改短隔離QA路徑後才重驗，不改產品來源掩蓋路徑問題。完整P00–P14／M1–M3／F01–F23／UX01–UX24／G0–G4仍進行中。

### P08 公開歷史 reader 正式套用與 raw schema 精確重驗

Root以同一獨立合成反例重驗新版候選，wrong-fill-schema已被ValueError明確拒絕；native0、兩candidate pins起訖一致，收據 `root/p08_schema_probe_4fb78cb5f2094ec3b52a5d5d1f3c56db.json`。此結果補足前節誤接受，不抹除原反例。

完整審查候選原始schema／SQLite primitive、獨立Context、canonical JSON、既有v1串流prefix、foreign portfolio、operation重算、transition fill order及有界讀取後，root保存working preimage與回滾清單，精確套用兩檔。Packet `root/p08_exact_apply_0d984d2399694dca92b53bcd9a45da49/`；patch SHA `7c639e44b415caa0b74a7aa2045a9aa067bac1e9fe72ff010f2c036c6a8db6dc`，raw post source `b4a9244cf692c038f00b978f752cf5c7996585a8350fc0f8aa03ca0ba86aa07c`／test `aba7f3a7f1e663aa617bab6d7867a050447dc18e1be2ecdd2b10d6f7026dfcd3`，完全等於隔離套用候選。前置與後置量化靜態guard兩項通過；沒有正式資料或既有SQLite寫入。

Root正式import全套ledger取得 **27 PASS／1.33秒／native0**，收據 `root/p08_exact_ledger01_120ba6037854473d822055c11e013a51/receipt.json`，child PID2716、28個source／test pins起訖一致。包括後續成交後歷史買賣／零成交重開、單BEGIN與WAL同snapshot、caller prec=1／Emax=1／Emin=-1／Inexact trap、重封raw schema／REAL股數與bp／錯flag、marker／fill／transition／rowset／foreign prefix及cap拒絕。Ledger定向mypy、兩檔compile與diff check通過；不能與owner同27項重複累加。

Owner短basetemp重驗原daily／availability取得47 PASS／325.16秒／session1897 native0；仍是暫時private ledger reader證據。現已釋availability唯一owner改用公開API，移除重複schema／rowset算法，保留clock／base／source operation拒絕；完成freeze後再由root跑正式ledger＋daily／availability＋P06帳戶reader完整定向回歸。正常producer／成本政策／日曆／benchmark／績效／UI與完整M3尚未完成。

F12小型owner探針取得真可見按鈕／QTest click／Yes確認各一次，仍readonly；標籤為path_preflight_failed，cause為PermissionError errno13／WinError5。Session28079／nested PID34588已native1終態、Job清理後remaining PID為空；來源未變。此與既有sandbox strict resolve誤拒須分開判讀，root待新診斷freeze後用核准的隔離小型probe核原因，不弱化正式custody。P01候選後置guard錯誤原會只寫failed而native0，已交owner修非零退出及純fixture；矩陣未釋跑。完整目標維持active，本輪已有正式code套用及原生回歸進展。

### P08 公開 API 接線與四組 root 整合終態

上一 goal turn 僅回覆剩餘範圍，分類為 no progress。本輪重新讀目前工作樹與 availability raw freeze：source `f9d3e7aceb343dd0d00e5f03fb755f8a7863bdd87a039c0324d884d2f6dafc8f`、test `074cb8d04d26284e66f192f04aceff621d05243d6e08afe878217b8aff9b539f`；owner preimages 在 `output/qa/p08_resume_20261011/availability_preimage/`。Root全讀pre/post差異：移除跨模組私有ledger schema／prefix／row decoders，只呼叫一次公開 `read_exact_daily_operation()`，核 typed bundle、marker、state operation、ordered fills／transition與上層clock。Public integrity errors保留cause並轉為availability拒絕碼；沒有取消state／來源核驗。

Root正式import四組 **81 PASS／246.73秒／native0**，包含ledger27、daily23、availability24、P06帳戶reader7；不與前輪或owner重複累加。收據 `output/qa/baldr_completion_20261011/root/p08_public_integration01_cf99f14a663f4ac7b4fc92dfb0632164/receipt.json`，child PID42924，28個source／test raw pins起訖一致。包含真writer空倉／買賣、零成交checkpoint、跨庫失敗恢復／冪等、後續append後歷史讀回、raw schema與payload篡改拒絕、同BEGIN及一次公開bundle並行寫入後仍讀原結果／下次拒絕、低Decimal context與錯帳戶／cutoff拒絕。

四來源定向mypy native0，收據 `root/p08_public_mypy01_9c596ba956904145b07117ecff3fd69c/receipt.json`；八個Python語法native0，`root/p08_public_compile01_3f659df612424133b88afe1843822468/receipt.json`；兩項白名單量化靜態guard native0，`root/p08_public_quant02_f2ba6a4371414924aeafbe68e9c2e723/receipt.json`，皆28 pins一致。首輪quant wrapper在child已結束／receipt已保存後，打印emoji被cp1252拒絕；原 `p08_public_quant01_ea6f15b338d34c6dbeb862242b29f68d` 保留，重驗明示UTF-8，不將wrapper例外寫成檢查PASS。

驗證期間另一工作保存本機dev `3da61351`，含本輪八個金融source／test與F12 harness；root未執行這個commit。提交存在不授F12新候選或整體驗收。Daily仍為逐庫恢復，saved recommendation execution只核目前canonical config／clock，不授完整P07訊號；quote／成本policy／官方日曆、正常account-aware producer、benchmark／績效與UI／M3仍開放。P08 owner只在scratch盤點公開P07 signal、T−1 preopen volume與原policy／fill引擎契約，不接受caller target/hash代替策略權威。

### P01 final freeze 純核驗與失敗傳播負例

Root明示final manifest path與SHA `4c3691192e6b0bb8c207c52ceef20e842312d23935626fad4dd988992eaa339f`，sidecar一致；純preflight兩次核80個source/runtime file pins、51個實際產品module及594個runtime package/DLL檔案一致，native0／8.56秒。收據 `root/p01_pure_preflight_20c06f0359f64f9b82c51e5736f4a4ef.json`；沒有store讀取或矩陣啟動。

本輪root三個純負例 **3 PASS／6.21秒／native0**，80 raw pins起訖一致，收據 `root/p01_pure_guard01_1ddbe1afdae947dd82c236c64e2f45f2/receipt.json`，child PID9068。實際runner保存post-guard失敗並native1；未列入freeze的金融產品module及放在output的產品module alias皆拒絕。該module負例沿owner已凍結的versioned fixture，沒有拿latest正式來源資格。Supervisor `c6d730f89471ba02f2c7993a4bcdc4a39c1f2f9a1c35cecec73b0f6d65222d6e` 靜態審查尚缺失敗role的PID／Job清理／logs收據、失敗後postguard及supervisor自身漂移拒絕；已交唯一owner補正負例。正常六角色矩陣未釋跑，原300ms Gate保持。

### F12 root 小型 WatchlistView 的下一失敗定位

Root核小型candidate main SHA `cd03151036b5102c224fe522237ca588d9b58260ea29cdf107be1d707dc14de3`／child SHA `32456ac7c5c526c927a9a9c744676f07bdd050d08006562a08012f07200bf2bb`，只替換原64-pin release的兩harness；其他來源及data觀測沿原42f不替代。新release `root/f12_small_probe_root_release_20261011.json` 僅授單一小型node，Main未釋跑。

核准隔離probe收據 `root/f12_small_watchlist01_91de1ff0e9c64e97a4570da3869d5b02/receipt.json` 為native1／外層1FAIL／5.64秒；64 source pins及data前後一致。內層 `output/qa/f12_resume_20261011/watchlist_view_probe_fdc167fa972f45449f7df9de893235b6/` 保存真可見click／Yes各1，status label是 `personal_watchlist_convert_blocked: source_backup_write_failed`；preflight causes為空，已越過前輪path預檢。目標DB未建立、原source SHA不變；view正常close、worker0，專屬Job／root handles已關閉，remaining PIDs空。

測試停在information＋warning必須1的assertion，但正式handler捕獲exception只設標籤並return，兩modal為0符合該分支；不視為modal產品缺陷。Source backup真路徑是os.open→os.fdopen，QA audit目前將integer descriptor當路徑拒絕的假設待小型實證。已交owner補backup cause observer與分支modal oracle；若修fd守門，須以OS實際handle path核private containment，外部／合成readonly source／closed或reuse fd／非檔案拒絕，不能一概放行integer。未改正式COW或放寬資料防護，完整F12旅程仍待。

Owner其後交純descriptor child的具名收據 `output/qa/f12_resume_20261011/fdopen_guard_probe_f7280b3f45954bd6b7ffedeeaa3e1f4c/fdopen-guard-role-receipt.json`。Root直接核收據及supervisor：private regular file的os.open成功但fdopen被PermissionError拒絕，private file仍空；同數字重用、closed fd、pipe、外部及readonly synthetic source皆拒絕，source SHA不變。Supervisor child PID29524／native0、owned Job關閉後remaining PIDs空。此為owner基線反例，補足前節假設的特定guard行為，沒有證明修正或完整COW成功；精確OS handle候選仍待freeze／root review。

### P01 啟動器 v2／v3／v4 的獨立驗證與真啟動失敗

上一goal turn只答產品剩餘範圍，分類為no progress；本輪重核目前檔案並推進凍結候選。Root v2測試7 PASS／1.89秒／native0／82 pins一致，receipt `root/p01_supervisor_v2_01_8c69d089e207449796ad3cc433eaaa62/receipt.json`。一次v2 matrix在首role spawn前拒絕，原因是`sys.implementation.name`的cpython和manifest的CPython表示不一致；packet `root/p01_normal_matrix_v2_01_1450223121824f72827ad21dedba4bdb`保留，沒有效能樣本。

V3改用與manifest/runner一致的`platform.python_implementation()`，追加真正guard正例及錯implementation負例。Root9 PASS／1.84秒／native0／84 pins一致，receipt `root/p01_supervisor_v3_01_176d17d9c762442aa98e9289af06645d/receipt.json`。一次v3 matrix第一role native1，standalone runner無repository root搜尋路徑，import app_module失敗；packet `root/p01_normal_matrix_v3_01_1461e11a0be44a9e9b9222ccd2c9680a`及stderr保留。Job已排空、postguard通過，沒有store內容或p95樣本。

V4僅令child PYTHONPATH固定repository root，不繼承caller；final manifest `4c3691192e6b0bb8c207c52ceef20e842312d23935626fad4dd988992eaa339f`及runner `055669702e0d217957df5380d49532fba90bfd7a2c0f73ed51fb1a67fb466bca`原bytes保持。Root全讀delta及新增測試，以受污染caller環境跑真suspended Windows Job standalone runner --help，再核bootstrap全部51產品origin、80file pins、594package/DLL及四版本；零store內容存取，Main及QApplication未啟動。Root獨立 **10 PASS／6.07秒／native0／86 pins一致**，receipt `root/p01_supervisor_v4_01_a9ddf2c44c314a698052301a57f29b5c/receipt.json`。V4 supervisor SHA `f52a1602e6bc835c9a991e4b84d0849bae591688b04b623dc97bdfb2b4031f26`，test SHA `5d1674a0a4c03e4c819382cd06dc71d58445ebd8b67ca0e6565dd7c71692cbb8`。

Root確認沒有本任務QA競爭程序後啟動一次五cold／一warm矩陣；packet `root/p01_normal_matrix_v4_01_369bed5846674873ab31bacd52562ae5` native1／86 pins一致。Inner `supervised_matrix_attempts/attempt_20261011T104818Z_58b6e6a8b4a4` cold01在`_fixed_store_snapshot`的sealed inventory `os.lstat`碰到長路徑WinError3，cold_metrics及matrix皆空，不能寫成效能不合格或通過。Role supervisor PID50568／runner PID2864；owned Job closed、remaining PIDs空、cleanup errors空，80／51／594及supervisor自身postguard通過。Runner來源樹前／後核驗均停在同路徑，不能由code pins推整份store已核一致。

Root唯讀metadata確認報錯目錄普通path不存在、延伸路徑存在且為directory；這僅支持長路徑存取診斷，沒有證明全store hash。Owner接續new versioned runner／manifest長路徑候選及真sealed store全量預檢，禁止移動、重建、縮母體或略過子樹。原每role600秒、各類30樣本、嚴格p95<300ms、1000母體／20頁及完整DTO序列oracle保持，Main／EXE／真人與完整P01未完成。

### F12 Win32 實際 handle 診斷與截斷防護審查

同一API probe腳本SHA `42456040c15944797edcd5a686723996464490da7665742cb9be7b1a1e6216d5`在sandbox的DOS/GUID GetFinalPath失敗WinError5、NT/NONE成功；root核准隔離新QA根執行相同bytes後，三access modes的八種valid flags全成功。Root receipt `root/f12_handle_api_4465164d84004ff2907a3c22c9e6f330/win32-handle-api-receipt.json`，PID43804／native0，DISK／fstat／Winfileinfo的volume、inode與nlink1一致，descriptor全部關閉。此證據支持保留NORMALIZED DOS(0)精確guard，不採NT fallback；尚非私人副本／Main旅程成功。

候選guard逐次核真正handle path及identity、單連結與private containment。Root另發現write-capable os.open若先O_TRUNC後查hardlink，拒絕前已可能破壞外部別名；已交owner補pre-open／audit existing file link count及os.open／builtin open兩種截斷負例，外部bytes須保持。完整Main仍未釋跑。

### P08 前向觀察候選審查（未套用）

Owner scratch沿真v4 source session／child／parent writer及公開exact reader投影五predicate之一，保留完整included cohort合法UNKNOWN與source availability unknown／historical PIT false。Root全讀候選，要求讀回時source cutoff、parent completed clock逐值綁真public package，重核capture不早於真parent並補重封hash負例；讀檔改有界且各層reparse／hardlink驗證，不先read_bytes全量再核上限。保存時鐘語意亦須精確，不能以preparation clock稱已保存。候選不授完整StrategySpec、帳戶producer或績效；正式P07／P08／M3及完整產品scope保持。

### P01 v5 原 sealed 清冊與凍結後漂移

Root全讀v5 runner相對原runner差異：僅將lstat／scandir／檔案I/O轉為Windows extended path，canonical root、relative payload、排序、identity、reparse與hardlink拒絕均保持。原80 source、51產品module、594runtime及fixed inputs的manifest值相同。Root在manifest `9509fb22782f1bec5a72f54aca0f6a2882010f9de1cc558359aa285f4a4dc7cb`凍結時獨立 **2 PASS／2.84秒／native0／89 pins一致**，receipt `root/p01_extended_v5_01_d3ec4b112ba34af4860330c11c4fa311/receipt.json`。真sealed source共1457 entries（1150 files／307 directories），tree SHA `a8d9946d94361733d8f268894e8452a73999c22ff47676528f8660f769e7f3b9`、source DB SHA `54ad8d6cdd018cecfc449062edd8ced56ba682b3fde8c86c1bce25d311674f27`與原封套一致；無來源重建、移動或縮母體。

Owner其後同path新增bridge欄位造成9509 manifest變成e4；root要求保留e4新檔並恢復exact9509。Owner依已記錄欄位重建，computed SHA精確等於9509，root目前Get-FileHash已核實；e4另存preimage。新bridge manifest為 `772f77b8d9f7aa479f4e826dbb0456469d66d7578859c1a360215a0f43c8e45a`，但root獨立啟動時發現attempt30 freeze的preflight SHA `88f138ff0c6e68dfbe1fe9a63d33ad649fd30e1baca3d5680c01d88962b92be7`與現檔 `b6bc82f926874ccf6393f60c9a43817c4aa671dec32298571d9588249621dbae`不同，於產品／store前停止。該停止沒有pytest／matrix樣本；已要求唯一owner新filename與新freeze，不能把已凍結候選原地改寫。原300ms、五cold／一warm、每類30samples及完整DTO oracle不改。

### F12 descriptor 私人正例與 alias 夾具失敗

Root審查pre-open nlink1／private containment及每次真DOS0 handle、Winfileinfo／fstat identity候選；freeze `be682af87e765785e46a44270789648fa5c09b0e5b8d6733eea7685d600279d5`，harness source `5f8ae9f30c84f39d3d2acf1d5552d6a7767b19767d709014674ca47a78327005`、child保持 `32456ac7c5c526c927a9a9c744676f07bdd050d08006562a08012f07200bf2bb`。首root attempt忘明示F12_SYNTHETIC_ROOT，在child前1FAIL／0.91秒；收據完整保留。第二attempt明示原42f來源，receipt `root/f12_descriptor_preopen_02_cc9ec1499f5a476ea989c533a21157a9/receipt.json`為 **1FAIL／3.60秒／native1**；64source pins與17檔／14sidecar觀測起訖相同。

Inner `output/qa/f12_resume_20261011/fdopen_guard_probe_73ecba9a56d44ff297c81efaee38f6d6/`真private writer成功且bytes一致；外部／readonly source／closed／同fd數字reuse／pipe皆拒絕。預先開啟的hardlink handle、os.open O_TRUNC與builtin open wb都拒絕，外部檔bytes與SHA不變。唯一失敗是os.symlink缺權限WinError1314，未真正建立alias，不能宣稱reparse負例通過。Launcher PID46396已native1終態，owned Job／root handles閉合、remaining PIDs空。下一候選改新私人目錄junction，不skip、不移除alias斷言；小型COW與完整Main尚未驗。Guard-only release需明示未授Main，舊base繼承的true旗標不能當新授權。

### P08 前向觀察來源鏈的 root 獨立驗證

上一goal turn只答進度，分類no progress；本輪root重核現工作樹、完整讀凍結候選與八項測試，manifest SHA `a9634ca5815ef73dca5f570ce0a587ed2d0c9eb3485d1c4027b1ddac492f5c7e`。候選source `c9d67dd6ad5c28c0595a9bd6c51a7072bac7eeb253b623c059968e44554a600d`、test `e53aba44b8e19f8a6a78034218dfebcd6682f1fadae29245b1a01849a109e47d`。Root guard保留前輪28財務／UI pins，再加入候選及19正式技術source/test依賴，所有raw pins起訖一致。

Root01沙箱在.t.resolve(strict=True)被WinError5拒絕，8個setup errors／2.54秒／native1，未進來源；receipt `root/p08_forward_root01_3b1771175930482a871e2a6f544cbd8e/receipt.json`保留。核准相同bytes的工作區隔離測試Root02取得 **8 PASS／0 skip／8.99秒／native0**，receipt `root/p08_forward_root02_87ba28556269405e811dda66b0a46e6f/receipt.json`，launcher PID41036終態。包含真v4 read session→child／parent writer→公開exact reader→新觀察保存→fresh reader、完整included UNKNOWN、重封訊號／重複成員／cutoff與parent completed clock、naive／晚到／foreign universe、caller score禁止、junction／hardlink／2MiB超限拒絕與hostile Decimal context。

新程序收據 `output/qa/p08_resume_20261011/forward_signal_candidate/fresh_source_reader_receipt_32124_27568.json`記PID27568／exit0，保存與重開signals相等（2330 unknown、2382 match）；來源SQLite SHA before=after=`c1a7c08dcbd925e64d84875470a06da399a8b2116f95bf3b4e1798b8fd12bc05`。此為隔離synthetic source經真正式來源API的證據，非正式市場來源或交易績效資格；source availability unknown／historical PIT false保留。候選尚未套正式module。下一包須有完整版本卡、entry／hold／exit／unknown政策及typed executor、exact account daily route與原金融引擎；完整P07／P08／M3與所有產品Gate維持未完成。

本輪文檔coverage／preimages／回滾packet為 `root/forward_and_descriptor_docs_944bd7b90d8b4fa29482d88c6c8cb39c/`；沒有產品UI／架構行為變更，Manual／Roadmap／Index無需新增流程。原資料、失敗QA、其他writer及main／push／發布邊界保留。

### P01 v5 新 final 獨立通過與唯一矩陣啟動

Owner保留88 preimage、新名b6 preflight，另發final freeze `7d31f9434a63f4a478aff510f10c1bbed8a6acf4d27f80e47f96fa37b5f90736`；root全讀delta僅新增parent product-path map與fixed-input equality核驗。Supervisor v4→v5僅變manifest／runner／自身檔名與fixed identity，Job、deadline與operation protocol不變。Root獨立 **12 PASS／10.95秒／native0／99 raw pins一致**，receipt `root/p01_v5_final_root01_dbf6e3641549425db911a82a675e10ed/receipt.json`，PID50580 terminal；包含full sealed store、真standalone help／bootstrap、assignment／resume／timeout／postguard收據及精確runtime。不是原10項與新增2項的重複累加。

新名preflight獨立native0，receipt `root/p01_v5_final_preflight01_a75db7c34364465aa420f6d66c93af38/receipt.json`，PID42160 terminal；80 source/file、51 product origins、594 runtime/DLL及四版本相同，store內容存取0，99 pins一致。Root通知兩owner停止QA，已收到無QA／新subprocess確認；host唯讀盤點只有其他專案risk-lab Python程序，未停止或修改它們，因此不宣稱整台機器完全無其他負載。

Root釋出並啟動唯一一次完整矩陣，session49268／launcherPID1180，packet `root/p01_normal_matrix_v5_root01_18aa1514b6b248d099032a933a97d6fb/`；inner `supervised_matrix_attempts/attempt_20261011T110425Z_a2cdc0776321/`。本段記錄時仍execute_role:cold_01，外層handle已實際poll確認live，尚無native終態或p95。五cold／一warm、每role600秒、1000母體／20頁、各操作30samples、strict<300ms及完整DTO serial oracle保持。後續依同一handle收終態，不因觀察逾時另起矩陣。

F12新freeze `5e78321c1a7a060498feafea029b7e1d42e33c40b33d29d0100572bcc0669ebd`（main513745c6、child32456ac7）已靜態審查與64-pin核對；root純guard release `f12_junction_guard_root_release_20261011.json` SHA `24c30fa4ab210fce34ebae329ba80c9724ae2c5863270fdb59489d53ec4e17b8`明示released_for_one_Main_attempt=false。尚未跑descriptor、COW或Main；待矩陣terminal再按相同freeze接續。P08 owner於scratch做完整策略卡／executor／daily route，保持已凍結依賴不變。

### P01 v5 完整矩陣終態：cold01 到達原期限

上一goal turn已poll同一session49268並確認live，分類為verified wait。本輪再次poll同一handle後取得native1終態，沒有重啟矩陣。Root packet `root/p01_normal_matrix_v5_root01_18aa1514b6b248d099032a933a97d6fb/receipt.json` 保存99 raw pins起訖一致；inner `supervised_matrix_attempts/attempt_20261011T110425Z_a2cdc0776321/supervisor_receipt.json` 在cold01達600秒，由專屬Job終止owned tree。

Role rootPID3844、截止前Job成員3844／28700／29812；Job與root handles已閉合，remaining PIDs及cleanup errors皆空。80 source/file、51 product origins、594 runtime/DLL與supervisor postguard通過。兩個role log為0 bytes、沒有result.json／oracle檔或p95；不能由空log判斷停在open、selection或page讀取，也不能由三個PID推為artifact reader程序。既有sealed store全清冊是啟動前證據，本次強制終止沒有runner來源post-inventory，不能由程式pins代替來源全樹證明。下一版增加原子phase與有限stack觀察，保留1000母體／20頁／完整serial DTO oracle、五cold一warm、600秒與strict<300ms，不直接提高期限或縮小範圍。

### 正式前向規則來源 API 整合

Root先保存Coverage／回滾與候選raw preimages於 `root/forward_formal_adoption_ecb2e49e834a4992a1bcfa101d514355/`，以create-only新增 `app_module/strategy_rule_forward_observation.py` 及 `tests/test_strategy_rule_forward_observation.py`。沿原candidate c9d67dd6／test e53aba44，只有繁中說明、正式import、型別驗證明確分支及非空bool、fresh reader60秒精確kill／wait與receipt搬到ignored QA根；原candidate與19正式技術依賴保持不變。型態檢查首輪23 errors、第二輪5 errors完整保留；在前次測試native terminal後才修改正式source，沒有凍結期間覆寫。

最終source SHA `9c02bce9b80797eab62433f1468a1db0e908950a6e758fac9f3d3e46af4420a7`、test SHA `b641e8e2083926f237cf76dbf65b4e31ad00c1871207740b6046f43354001bdb`。Root正式匯入 **8 PASS／7.84秒／0 skip／native0**，receipt `root/forward_formal_v3_root01_68efbce9b940415b8a6bf86607f7c368/receipt.json`，launcherPID37036終態，53 raw pins起訖一致。不與原候選八項、前兩次正式測試重複累加。新程序收據 `output/qa/strategy_rule_forward_observation/fresh_source_reader_receipt_18744_31532.json` 記childPID31532／exit0、2330 unknown／2382 match與保存相同，來源SQLite before=after=`c1a7c08dcbd925e64d84875470a06da399a8b2116f95bf3b4e1798b8fd12bc05`。

最終mypy native0 `root/forward_formal_v3_mypy01_6b00b18f9cb74266a2281afd5d524087/receipt.json`；兩檔語法native0 `root/forward_formal_v3_compile01_f7ce87ab0b66461cac72a1cd58ab207f/receipt.json`；兩項白名單量化guard native0 `root/forward_formal_v3_quant01_6912ca0a78704c90bb8582673a541658/receipt.json`，均53 pins一致。白名單guard沒有涵蓋新module，來源時鐘／未來資料拒絕依完整八項與root review判讀。

追加既有v4八組來源回歸首輪 **91 PASS／20 FAIL／40.43秒／native1**，receipt `root/forward_source_regression01_49d88191a5ec48d88e671d5764e703fd/receipt.json`，53 pins一致；失敗集中在runner將basetemp放`.t`，無research_scope的舊測試producer依既有允許根契約拒絕`technical_snapshot_v4_isolated_output_required`。原失敗保留，僅以新wrapper改到既有允許的output/qa重驗，正式producer／既有測試沒有修改。

此正式API只授前向研究觀察、完整UNKNOWN、exact來源重讀，source availability unknown／historical PIT false／execution及performance false保持。完整版本卡、entry／hold／exit政策、typed executor、原金融引擎normal daily route、官方日曆／成本／benchmark／績效與正常UI仍待；P07／P08／M3及完整產品Gate未完成。

### F12 junction fixture 第二輪審查

Root按freeze5e78321c與main513745c6執行三個guard／branch節點，receipt `root/f12_junction_root01_ffbaefcc1a644b5a9ef586d655e18877/receipt.json` 為 **1 FAIL／2 PASS／3.71秒／native1**，64 pins及原17檔／14sidecar觀測起訖不變。Inner `fdopen_guard_probe_e0b216ccc52a4bf8940c3d0206505cc8` launcher2196自然native1，ownedJob／handles閉合、remaining PIDs空；junction流程之後仍引用已移除的private_sha_before_reparse，NameError使role receipt未完成，不宣稱junction通過。

Owner保持513745preimage並修新main9fe5dac0；freeze9778fa22的test_files已更新，但pin_inventory仍引用513745／舊size，root新prepare在pytest前拒絕兩份清冊不一致。沒有guard、COW或Main新樣本；已要求保留9778原bytes、另建一致的新freeze，不略過inventory equality。完整COW、Main保存／關閉／fresh reader仍待。

### 本輪來源回歸與 F12 私人副本獨立通過

相同八組來源測試僅改basetemp到producer既有允許的output/qa，取得 **110 PASS／1 skip／51.76秒／native0**，receipt `root/forward_source_regression02_f9f67d0f18374548bffd1ad5b9c67aac/receipt.json`，launcherPID33812終態，53 pins起訖一致。具名skip原因補查 `root/forward_source_symlink_reason01_6edfce9eda544245804bc8cfa2bc0d56/receipt.json`：原artifact symlink fixture因WinError1314無權建立而跳過，不視為該拒絕案例通過。正式新觀察API自己的八項維持0 skip，兩者覆蓋不互相替代。

F12 owner新freeze `14e3d64317aa542819b90f14c30976e665b35bf5a8399057d6e2fac034499b45` 保持main9fe5dac0／child32456ac7，64-pin aggregate `a747590f769ec24036697b38d096fb10df74acafcc00b5be93730f525aa6cc69`；root重新逐列比原base＋本輪Main差異，完整inventory與test_files相等後建立新guard release `e381a25bf040dee0e39f59206aec5166feeda7f2921a8a2da5ef7060d60c92a5`，仍未授Main。Root獨立 **3 PASS／3.52秒／native0**，receipt `root/f12_junction_pinrefresh_root01_364dd270767f4c58859a7abe8a903dbb/receipt.json`，64 pins及原來源觀測前後一致。

Inner `fdopen_guard_probe_a87335dd431e4c14a9f52a841f3fdb22/fdopen-guard-role-receipt.json` 全部assertions為true：private DOS handle writer及exact bytes、external／readonly source／closed／reuse／pipe拒絕、兩種hardlink截斷pre-open拒絕且外部bytes不變。實際junction創建成功、alias寫入被拒，target SHA在before／after-attempt／after-cleanup皆 `fc1c6f1bdd46318f9ed5e7b0d65bed6f56bc2b8d99dc53efdda0b8319891f952`；alias已非遞迴移除而target存在。Create／remove各自owned Job的PID31736／50900均native0、handles閉合、remaining PIDs空。

按同freeze釋單一小型COW release `fd971d4dc7e3a9fa07b562737d698f6f9c2cb321f1b75d268a4fea50a8ae99cf`，Root **1 PASS／8.37秒／native0**，receipt `root/f12_small_cow_junction_root01_39caa64443a64a939a419182484a04d0/receipt.json`，64 pins及來源觀測不變。Inner `watchlist_view_probe_154961274ee04880898444a5ed0bb3c0` 真可見WatchlistView按鈕QTest click1／Yes確認1／information1／warning0，service repository active；新私人target在run root、SQLite v3 ready、query_only true／write_blocked true、active reader成功，原source SHA未變。Worker34208 native0、registry排空及owned Job／handles關閉、remaining PIDs空。這是私人副本啟用證據，完整營收query與收藏fresh reader仍另驗。

Root核上述COW三份inner receipt、當前64pins後，建立唯一一次完整Main release `f0aef1f2238bc3112f88bf2380091b031171f444ad09e8b3a2e0662aaa2f7a48`。Session15138／launcherPID47352，packet `root/f12_full_main_after_cow_root01_23779aee1cb14e11b4a1fac9967fc4a6/` 已啟動，記錄時尚live／沒有終態。原42f來源與258完整cohort不換，worker2400／Main init600／fresh subprocess600／fresh init540／query min480remaining為防失控上限，不當產品效能門檻。後續poll同handle收結果，無新EXE／真人或完整Gate驗收。

完整Main同一session15138後續poll取得 **1 FAIL／25.97秒／native1**，receipt `root/f12_full_main_after_cow_root01_23779aee1cb14e11b4a1fac9967fc4a6/receipt.json`，64 pins及來源觀測起訖一致。Inner `main_candidate_6f6597e4d85e422d8e707e90739e0b84` launcher17792、active count0／tree closed／root handles closed，未逾時。Main QApplication／theme／真正MainWindow全部初始化完成，私人副本啟用後，在「核驗雙來源並執行全母體查詢」停止：`monthly_revenue_yoy_index_v1_source_archived_open_failed:PermissionError:fdopen_must_transfer_descriptor_ownership`。

Root靜態沿真source archived路徑核 `data_module/fundamental_read_snapshot.py` 的2445／2903：private封存writer使用os.fdopen(..., wb, closefd=False)，以caller保留fd供flush／fsync／close；現QA guard在write mode強制closefd=True。此是guard與正式writer生命週期契約的下一停點，不據此宣稱產品讀取缺陷。Owner接續exact actualhandle／private regular nlink1／descriptor ownership候選與closefalse正負矩陣，不放行外部／hardlink／reparse／closed／reuse／pipe，也不改正式fundamental reader、縮母體或略過保存／fresh child。完整F12旅程未通過；root現無live QA，後續新freeze審後重驗。
