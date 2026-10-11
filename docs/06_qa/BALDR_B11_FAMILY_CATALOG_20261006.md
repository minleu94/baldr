# B11 原八族唯讀能力字典（2026-10-06）

> **狀態與操作提示（2026-10-11）：** 本字典是唯讀能力目錄與候選來源描述。有限 `close > BBANDS30 upper` 方法已採用為版本化方法 `daily_market.close_above_bbands30_upper@1.0.0`，歸在 `close_vs_bollinger_upper`；其來源／保存／研究投影與具名母體證據見 [A01 收據](BALDR_A01_BBANDS_UPPER_20261006.md)及 [BBP01 收據](BALDR_PARENT_BBANDS30_UPPER_20261007.md)。這不等於完整 `bollinger_compression_breakout` 家族已完成：BB30 bandwidth／ATR14-SMA 是原料，壓縮窗口與定義、量能條件、VCP、pivot／突破／失效規則仍未定；完整家族維持未完成。A01／BBP01 的合成證據不代表正式來源、PIT、自然成熟或交易資格；中央 daily caller 狀態見[中央接線收據](BALDR_DAILY_BBANDS_CENTRAL_20261007.md)。本文 rollback 命令屬歷史交接，不要直接在目前工作樹執行。

固定 base：`740fd64cd8a29064c7137bf92f0f78b5bfba2e25`。專屬分支 `lane/baldr-b11-family-catalog-20261006`；中央 owner `01a11020-88c2-7506-acc3-d51ecb674032`。依原 `output/plans/baldr_product_experience_plan_20261004.md` §8.6、Astra inventory §4.5／B11 與 Sol review 的有限集合要求；這份是工程收據，不另立 roadmap。

## 範圍與 API

新增 `app_module/rule_research_family_catalog.py`、`tests/test_baldr_b11_family_catalog.py` 及本文件；既有 `daily_market_research_capabilities.py` 只增加 import 與 `DailyMarketResearchCapabilityCatalog.families` 唯讀入口（10 行）。既有 `to_dict()` 的 features／methods、schema、投影、方法契約與 hash 全保持。新增入口沒有 UI、執行器、SQL、檔案／網路 I/O 或資料重算。

`RuleResearchFamilyCapability(family_id, title, status, versioned_method_refs, required_fields, warmup, missing, availability, cost, source_refs, blockers)` 十一欄固定，frozen／slots，巢狀 mapping／sequence 亦凍結；不接受可變非 JSON 基本值。`to_dict()` 產出 detached JSON-ready 副本；小數參數以字串記錄。`list_rule_research_families()` 回 tuple；`get_rule_research_family(id)` 僅 exact 配對，未知保留 caller ID、status=unknown、空 methods／fields／source、unknown missing 與 blocker，不做中文名稱／大小寫／空白別名。

`partial` 只表示有既存有限觀察來源，不能視為完整策略 supported；`unavailable` 表示該方向的方法與保存欄位尚未合格。本字典沒有交易勝率、回測效果或啟用權限。source_refs 是原碼候選入口，不是實際資料 pin；原來源日期、母體、時鐘、schema／hash 必須在原 artifact 核驗。所有家族 historical PIT／formal eligibility=false，official availability=unknown；缺值不補零或判為負樣本，cost 不填估計時間、記憶體、bytes 或交易成本。

| 原家族／exact ID | 目前能力 | 必要欄位方向與剩餘缺口 |
|---|---|---|
| 原價量排名／original_price_volume_ranking | partial；原本日／本週保存排名 | 保存排名、母體、期間、門檻；沿 original_stock_ranking，不重定分數、不造每日方法版本 |
| 趨勢轉強／close_vs_moving_average | partial；兩 MA 同一家族 | close／MA20／MA60；20／60 連續有效 OHLC 暖機；只有價格與均線關係，方向／交叉／量能完整條件未開 |
| 布林壓縮突破／bollinger_compression_breakout | unavailable（完整家族未完成） | 已採用的有限 `close > BBANDS30 upper` 是另一方法家族 `close_vs_bollinger_upper`，不構成壓縮突破；BB30 bandwidth／ATR14-SMA 只屬已保存原料。完整家族仍需同版對齊保存 close 與三條 band、前段壓縮歷史、volume／liquidity，以及窗口／門檻與確認／失效規則；詳見下方 U1 範圍說明。 |
| 波動收斂／volatility_contraction | unavailable | ATR／振幅／bandwidth／volume history；窗口門檻、保存、完整 VCP 辨識未完成 |
| 型態確認／pattern_confirmation | unavailable | pattern／當時可得確認及失效事件／signal_date；確認方法版本未定 |
| 籌碼轉強／institutional_flow_strengthening | unavailable | 法人淨買超／價量／available_date；5／20 日來源窗口尚未核驗，榜外不可補零 |
| 基本面動能／fundamental_momentum | unavailable | 營收／獲利／期間／前期／單位／available_date；current_fundamental_snapshots 只提供現況來源方向，不補歷史 PIT |
| 產業領先／industry_leadership | unavailable | 股票／大盤／產業相對報酬及 membership／available_date；同期範圍與分類版本未定，當前分類不造歷史 effective intervals |

本 B11 固定 base 的原始字典只列 `daily_market.close_above_ma20@1.0.0`、`daily_market.close_above_ma60@1.0.0`，均綁同一 `close_vs_moving_average`；不能把 2 MA 算成 2 個獨立家族。後續採用的 `daily_market.close_above_bbands30_upper@1.0.0` 是另一個有限家族，詳見上方 A01／BBP01 收據，不改寫此原始 base。MomentumAggressive 的 TotalScore 是混合評分，不能借作完整 compression 家族；deprecated SimpleStrategy 不作來源。

## U1：既有 30／2 SMA 上軌研究比較的有限可選方案

> **後續決議（2026-10-11）：** 本節原列的有限上軌選項已由 A01／BBP01 收據實作、版本化並驗證於合成具名母體；方法為 `daily_market.close_above_bbands30_upper@1.0.0`，family 為 `close_vs_bollinger_upper`。它只判斷 close 是否嚴格高於既存 BBANDS30 上軌，沒有定義或實作 `bollinger_compression_breakout`。產品補完表仍將 BB30 bandwidth／ATR14-SMA 列為原料，並將完整壓縮窗口、門檻、多段 VCP、pivot／突破／失效列為未完成；因此本節下方的完整壓縮缺口仍有效。中央 daily caller／完整日常接受亦未由本方法的有限證據宣告完成。

核對固定 base 的 `analysis_module/technical_analysis/technical_indicators.py:calculate_causal_indicators`：既存 TA-Lib BBANDS 使用 `timeperiod=30, nbdevup=2.0, nbdevdn=2.0, matype=SMA`，產出 `upperband`／`middleband`／`lowerband`。這是既存分析參數，不是本輪新增門檻。在本 B11 固定 base，daily v2 saved feature 只有 close／MA20／MA60，BBANDS 未保存；後續 A01 才為有限 upper 比較加入獨立 v3 保存契約，不能把這段原始 v2 限制讀成目前未採用該有限方法。

原方案列出的兩個選項及後續處置：

1. 維持現行兩 MA 方法，只提供本八族字典及未決 blocker；無需 producer 擴鎖。這是本包實際交付狀態。
2. 明示核定「既有 30／2 SMA 上軌研究比較」為另一個有限研究方法版本，再另包擴鎖必要特徵、方法契約、producer、repository、consumer 與回歸。此有限方法後續已由 A01／BBP01 收據採用為獨立的 `close_vs_bollinger_upper` 方法版本；其驗證仍受合成來源與資格限制。它不代表完整壓縮突破；不得回寫 v2 或更換其 hash。

原選項 2 的 review-ready 保存方向為 close 及 upperband／middleband／lowerband 三值、單位與未知狀態／reason，精確股票／行情日／decision cutoff，原 price／technical source refs 與 scoped fingerprints，BBANDS 30／`"2.0"`／`"2.0"`／SMA 參數、method ID／version／relation，暖機 required／observed count／state／basis、availability 及缺件理由。這是歷史提案描述，不是目前待辦；A01／BBP01 收據記錄已採用有限 upper 方法的實際契約與合成 cohort 驗證。其正式 source／PIT 資格仍未升格。

暖機沿既存 causal calculator：單股、按日期遞增的完整 OHLC prefix，至少 30 個連續有效 OHLC 觀測；缺值後重新暖機，不能先截取發布區間再算。30 是指標必要觀測數，不是官方日曆或 availability 資格。資料只有已收盤截止前資訊；預測／交易訊號另須遵守當時可得時鐘。TA-Lib 浮點值只在既有分析邊界，後續核心比較須使用 Decimal 或明示定點格式；本包只有字串／整數中繼資料，沒有金融計算。

成本分開：固定字典查詢無 I/O；完整 compression family 的新增計算／保存 CPU、memory、bytes、容量增量尚未量測，trade cost 亦 unknown，不能以本包 O(8) metadata 查詢代替 producer 成本證據。本 B11 包沒有擴鎖 producer；後續 A01／BBP01 已涵蓋有限 upper 方法的 producer／保存／讀回，但不代表完整 compression 成本或資格已驗。

完整 compression 仍未決：前段窗口、壓縮定義／門檻／分位、量能／流動性條件與確認／失效規則。若使用分位，只能對決策前窗口與事先明定的合格母體計算。有限 upper 方法已採用，不代表上述規則已定，也不授予完整第二家族或自然效果。

## 驗證與相容性

使用主 checkout 的 `.venv/Scripts/python.exe`，cwd 為本 B11 worktree：

- pytest：`-m pytest tests/test_baldr_b11_family_catalog.py tests/test_daily_market_research_capabilities.py tests/test_daily_market_method_contract.py tests/test_causal_technical_indicators.py -q -o addopts=`；31 passed（14 個 B11 案例＋既有回歸，共 31 個不同案例）。
- focused mypy：`-m mypy app_module/rule_research_family_catalog.py app_module/daily_market_research_capabilities.py --follow-imports=silent`；通過，僅兩個本包 source，不能代替全專案 typing gate。
- compile：`-m py_compile app_module/rule_research_family_catalog.py app_module/daily_market_research_capabilities.py tests/test_baldr_b11_family_catalog.py`。
- Quant Guard：`scripts/quant_guard_linter.py`；本包通過；本包人工自查亦無新 float、訊號計算或未來資料讀取。
- 無 UI 變更，未跑重 UI mandatory；中央穩定 union 另行驗收。

新增案例覆蓋十一欄 API、八族順序、巢狀 immutable／constructor detach／JSON detach、未知 exact lookup／missing、兩方法同一家族、BBANDS 未保存且門檻空值、舊 capabilities parity、future family append 不污染舊內容／hash、future method append 不默默成為可用方法。既有 capability snapshot tests 仍核部分缺件／完整母體及嚴格 identity 拒絕；causal indicator regression 沿既有 prefix invariant。

固定方法契約 SHA-256：`029bcb5ada592619d9748d327eef509db0642a1c6904b652b31f186027025dc5`。舊三 feature／兩 method catalog 的 canonical JSON SHA-256：`eb93750012c5c7de223cc01ece2a017848d88812a751361883d9a66404ef880e`。測試把這兩值鎖定；`catalog.families` 是 additive property，不加入舊 catalog.to_dict()，未來新增家族亦不改舊 artifact bytes。

## 交接、文件 coverage 與回滾

本包不改 Snapshot／Manual／architecture／原計畫（中央排他）。中央整合時可在能力字典章加入 exact API 及本收據連結，明示目前 8 個方向、2 個版本化方法、1 個 MA 家族，第二家族只交候選；UX10／16／18 和原 9stage／24UX 不提升整項 done。Roadmap／maturity／產品方向無變更；無新 UI 操作步驟。未觸 B13／ML／daily runtime／forward 或 producer／repository。

回滾檔案：新增的 module／test／本 QA 文件；修改的 daily_market_research_capabilities.py。尚未整合時先確認沒有後續變更，於本 worktree 執行 `git restore --source=740fd64cd8a29064c7137bf92f0f78b5bfba2e25 -- app_module/daily_market_research_capabilities.py`，再逐檔 `Remove-Item -LiteralPath <本包新增檔>`；已整合時由中央針對本包 commit 反向套用。回滾無原始資料風險，但撤回 family API 前需核對後續 consumer。不得刪其他 owner 檔、重置 dev 或清理 worktree。

本機 commit／完整 blobs 於交付回覆提供。完成後停等中央整合；未 cherry-pick 至 dev、未 push，無正式資料寫入／migration／ACL／Task／fit／Native。有限 upper 方法已有獨立採用證據；完整 compression family 與其 producer 規則仍是剩餘工程及決議，不假稱已完成。

更新記錄：2026-10-06 新增 B11 八族字典、有限 BBANDS 選項、相容性及聚焦 QA 收據。
更新記錄：2026-10-11 依 A01／BBP01 與產品補完 QA 收據，區分已採用的有限 BBANDS30 上軌方法與仍未完成的完整 compression family。
