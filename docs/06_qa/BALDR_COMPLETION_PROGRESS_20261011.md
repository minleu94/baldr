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
