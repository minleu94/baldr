# Stage6／UX11 規則卡唯讀投影限定收據（2026-10-06）

## Ownership 與範圍

- 基線：`e61786bc4`（完整基線 hash 以交付 Git 收據為準）。
- 分支：`lane/stage6-rule-card-20261006`。
- 專用 worktree：`C:/Projects/PythonProjects/technical_analysis/output/worktrees/technical_analysis_rule_card_lane`。
- 本 lane 只新增 `app_module/strategy_rule_card_readmodel.py`、`tests/test_strategy_rule_card_readmodel.py` 與本文件。背景執行，不操作使用者視窗。
- 主整合 owner `01a10b0e` 持有 dev/config/UI/Manual/原 plan；Journal 四介面及 personal lane 檔案不修改。原 plan 唯讀，未 merge dev、push、安裝依賴、fit、promotion、啟動 producer、DB writer 或清理。
- 使用者指定三檔排他範圍優先，本文件與最終交付取代額外 shared-state 檔案寫入。未建立其他 agent。

## 契約與來源盤點

原 plan 第 8.3、stage6、第 11 UX11 及 2026-10-06 純 backend 並行表要求規則追版本、缺值保留，不造交易條件或曲線。已有圖譜節點 `app_module_strategy_version_service_strategyversion` 指向 `app_module/strategy_version_service.py:L18`；來源事實再以實際原碼核對，未重建圖譜。

| 入口 | 既有來源 | 可顯示的已知值 | 明確缺件／資格 |
|---|---|---|---|
| `read_daily_method_rule_card` | `daily_market_method_contract.method_contracts_payload`；傳入 snapshot 時改用其捕獲的 `method_contracts` | 方法 ID、family、version、direction/window、required_fields；快照提供股號、scope、日期、units、policy、來源 trace 與原 condition | 是既有觀察方法，非可執行交易策略；沒有 sell-rule、成本、benchmark、持倉與可成交時間 |
| `read_strategy_rule_card` | `StrategyRegistry.get_strategy_meta`、`StrategySpec`、可選 `StrategyVersion` | 真實 Registry 名稱／description／參數 schema，spec 的 config.params、target_type/regime、data_version，version_id/source_run_id/validation_status | description 與參數名稱不等於 entry/exit 合約；沒有完整宣告的交易欄位維持缺件，不建立 executor |
| `read_profile_rule_card` | 已讀入的 `RecommendationProfile` | 原名稱、description、config、applicable_regimes | 固定 `profile_execution_contract_unbound`；選股設定尚未綁定執行規則，不使用風格／validation_label 推論勝率或交易權限 |

已實作實際方法 `daily_market.close_above_ma20` 與 `daily_market.close_above_ma60` 的 read-only projection。實際 baseline Registry `baseline_score_threshold`／`1.0` 的參數 schema 亦有測試核對；不由名稱推論規則，也不將 metadata default 自動套成此次執行參數。

每個欄位具有 `value`、來源路徑與 `missing_reason`。欄位包含名稱／說明、entry、exit、universe、period、parameters、parameter_schema、cost、required_features、units、data_insufficiency、execution_mode、signal_time、earliest_execution、holding_period、stop_loss、take_profit、position_limits、gap_suspension_unfilled、benchmark、qualification、source_trace。沒有來源時 `value=None`、`source=None`、原因 `source_contract_field_missing`；`missing` 列出精確欄位名。target_type/regime 不冒充完整歷史母體 membership。

## 身份、資格與 fail-closed

`StrategyRuleCard` 與各欄位不可變，巢狀值以 canonical JSON 保存；`to_dict()`／`field().value` 回傳 detached 副本。consumer 修改 DTO 匯出值不會改寫舊卡，原 spec/profile 後續修改亦不污染舊投影。

`RuleCardIdentity` 明列 rule_id、rule_version、source_ref、source_sha256、rule_sha256、result_kind、context_sha256。source hash 是已讀契約 payload 的 canonical SHA256，rule hash 是規則 payload 的 SHA256；context hash 捕獲完整 snapshot 投影內容，含股票、日期、scope、features、condition、policy 與來源 pin。來源 trace 同時保留 snapshot/input/method hashes 與 feature contract version。這些是內容身份核對，不宣稱已驗證 executor 程式碼或原始資料檔的完整 custody。

- `historical_backtest`、`research_forward`、`live` 三種 kind 各自鎖定 identity。未知 kind 拒絕；當期觀察快照只能以 `live` 並保留 `current_observed_research_only` 用途。此處 live 只是當期來源分類，不授即時行情／交易資格。
- 已捕獲方法契約不轉讀 latest registry；上游改版後舊快照仍顯示其原契約，結果 pin 不能與最新版本混接。
- 方法 hash、condition ID/family/version/parameters、資料日／決策日、scope/hash 缺件、未來資料、重複／缺少 condition、必要 feature 缺漏／unknown、feature 與 condition 值不符或 relation/state 矛盾都保持 `not_evaluable`。
- `equal` 是已有方法的 `no_match`，仍可是 `eligible_observation_only`；不是成本後損失、策略退出或績效負樣本。暖機不足保留上游精確 unknown 理由，不補零／sell／no_match。
- 方法的可判讀資格只列 `eligible_observation_only`，保留上游 PIT／official availability／calendar 狀態。完整交易規則的 `rule_status` 與所有卡的 `performance_status` 保守維持 `not_evaluable`。
- Registry version 與 spec/version/config/params 不一致不借 current defaults。StrategyVersion 的 `validated` 只是原始宣告，backtest_summary 未投影為已驗證績效，不使用未核對的勝率或回測摘要。

`bind_result_reference(card, RuleCardResultReference(...))` 只核對完整 identity 及已提供 result_ref/result SHA256，成功回 `source_ref_only`；任何版號、hash、context、kind 或來源缺件拒絕連結。即使 ref 匹配，`performance_status=not_evaluable`；不計算績效、curve、cost、benchmark、勝率、排名或驗證 credit。result pin 必須由 consumer 從已讀、已驗證來源組成，不能將目前卡 identity 指派給無原始綁定的舊結果。

## 驗證證據

在本 worktree 執行，共用原 repo `.venv`，未安裝依賴：

```powershell
C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -m pytest tests/test_strategy_rule_card_readmodel.py tests/test_daily_market_feature_snapshot.py -q -o addopts=
C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -m mypy app_module/strategy_rule_card_readmodel.py --follow-imports=silent
C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -m py_compile app_module/strategy_rule_card_readmodel.py tests/test_strategy_rule_card_readmodel.py
C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe scripts/quant_guard_linter.py
```

- 41 個新契約案例與 10 個既有快照案例，合計 **51 passed**（最後執行 以最終交付執行收據為準）。
- 補入無效來源 payload 案例時，測試尾端副本隔離斷言誤放至新函式造成 `NameError`；已移回原測試，最終 51 案全部通過。
- 單檔 mypy 通過。最初 nullable metadata 的 narrowing 報錯已改用 `isinstance(StrategyMeta)`，修正後通過。
- 兩檔 py_compile 與 quant guard 通過；guard 為既有白名單 gate，額外人工核對新檔沒有 float 計算、fit、writer、完整市場掃描、策略執行器建立或網路。
- 所有 market/technical 資料來自本測試合成 DTO，調用既有 `DailyMarketFeatureSnapshotService.project` 取得真實服務的輸出，再投影規則卡。沒有正式 DB／檔案讀寫或自然 forward 證據。
- 覆蓋實際方法 match/below/tie、缺暖機／unknown、必要 feature、重複／缺 condition、錯日期／未來日期、錯版本／參數／family、來源缺 hash、scope 及股票 context、來源 payload 修訂、舊快照 pinned contract、Registry／Version params、無 executor、副本隔離、跨 historical/forward/live 及 missing cost/benchmark/result ref。
- 未修改 UI，沒有 UI／Native 驗收或整個 repo mypy／全量回歸的宣稱。主 owner 接線後應執行 UI 強制 gate。

## 主整合 owner 最小接線建議

只在使用者開啟單張說明卡時按需投影，不在啟動或列表逐列建立服務／executor／大量 cache。以目前已驗證 source 的原 DTO 接線：

```python
card = read_daily_method_rule_card("close_above_ma20", snapshot=pinned_feature_snapshot)
payload = card.to_dict()
# UI 使用 payload.fields 的 value/source/missing_reason；不另手寫規則或計算績效。
```

每日研究列的 condition 不能直接冒充 `DailyMarketFeatureSnapshot`；consumer 須保持原 verified snapshot 的 captured contract、完整來源與同股／同日期 context。只傳 row 而沒有這些 pin 時，先使用無 snapshot 的規則說明並明示資格缺件。策略卡以已讀入的 `StrategySpec`／可選 `StrategyVersion` 調用 `read_strategy_rule_card`；Profile 用原 profile DTO。不要為了讀卡初始化會 `mkdir` 的 VersionService 或含 writer 的其他服務。

UI 可分開呈現「規則說明」、「既有觀察」與「結果來源」。交易欄位的未知不能被 observation eligibility 覆蓋；validation_status 旁標上游宣告／尚未核對結果，缺成本與 benchmark 不能畫曲線或排名。每一結果類型保留自身頁籤、version/source pin 與 qualification，不用同卡來源身份替舊 run 補章。缺件可顯示精確欄位與理由，沒有隱性切換最新資料或重新分析動作。

## 尚未完成與交付邊界

本包完成 UX11 規則 readmodel 的有界 backend 切片；**stage6／UX11 整項仍 partial**。完整 entry/exit/execution/cost/benchmark/績效來源資格的 typed execution artifact 尚未由既有 metadata 提供；沒有補寫 shared registry/executor。規則卡一律明示缺件，既有方法只授觀察資格。真實歷史／自然 forward/live 結果來源的 adapter／custody、UI／Manual／plan、全頁一致化、Native／真人與長期 producer 均由主層另行處理。

回滾：主層 cherry-pick 前可保留 lane 不採用；採用後確認無其他依賴，對本包提交 `git revert <本地交付commit>`，再執行定向測試。回滾不碰正式資料；已新增 consumer 時需同步撤回其接線。worktree 保留供主層審查，不自行清理或合併。


## 主線review及最小consumer整合（2026-10-06）

三檔lane c7a9ea37 review後整合為a3b63070，所有lane worktrees保留。BacktestConfigPanel增加按需按鈕，BacktestView以既有回測同版StrategySpec（1.0與目前default config／params）呼叫read_strategy_rule_card，沒有借Registry新版本或綁旧结果；源版不符仍not_evaluable。新StrategyRuleCardDialog顯示當前設定、未連執行結果、未知契約、唯讀欄位及預設收合來源。Registry描述不推導交易規則，method/family/pin沿backend驗證，不造MA或賣出算法、費用、benchmark、勝率／曲線。

主線focused：63 passed（lane51＋consumer4＋既有backtest layout8），Workbench85 passed，validator25／0fail／4skip，完整roots mypy801、compile5、quant guards及diffcheck通過。pytest唯一warning是sandbox cache不可寫，無測試skip；不重跑251項或全市場。Consumer四項涵蓋參數修訂改hash、不取executor／不借舊run、未知欄位及收合唯讀、registry版不符及未選擇不開卡。

合成offscreen截圖留output/qa/ux11_rule_card_consumer_20261006/controlled_rule_card.png。首次獨立renderer未套主程式中文字型顯示方框，套既有register_qt_chinese_fonts後可讀；不修改font流程。此圖是合成設定，不是Native／真實結果。Manual同步入口、參數／結果解讀、安全限制及排錯，Snapshot／current architecture／UI feature／UserGuide與唯一plan同步。

UX11完成有限consumer，由待辦改partial；stage6仍partial。完整typed execution contract、真實結果adapter／custody、規則與執行一致證據、Native／真人仍待辦，readmodel不等於execution/performancequalification。UTC07:00停止期限不變；本批不新增代理、migration／activation／producer／push／清理。
