# 臺銀證券電子下單成本估算 QA（2026-09-14）

## 1. 判定與範圍

本卡交付一個可由交易日選版本的研究用 policy：

- policy id：`banktaiwan-electronic-order-v1`
- policy version：`banktaiwan-electronic-order-2026-v1`
- 有效交易日：2026-01-01 至 2026-12-31（含首尾）
- 估算核心使用 `Decimal`；股數與 lot sizing 使用整數。
- 未連接臺銀證券帳戶、未取得實際 broker fill、未建模滑價；結果必須標記為 `estimated_research_only`，不能作為正式成交成本或投資有效性證明。

本次實際 consumer 是 `RecommendationPortfolioBacktestService` 的 `NEXT_OPEN_CONTRACT` 歷史回放。legacy same-day close、單股 `BrokerSimulator` 與每日 recommendation learning／calibration 的固定 `50bp` lineage 不改動；固定 50bp 仍是手冊定義的 learning 假設，不會被重新標成臺銀實際成本，也不會改寫既有 after-cost probability／score。

## 2. 官方來源與採用邊界

| 規則 | 官方證據 | 本 policy 的採用方式 |
|---|---|---|
| 電子下單手續費 0.0498%、每筆最低 20 元、小數點以下無條件捨去 | [臺銀證券業務介紹](https://www.twfhcsec.com.tw/Activity/BusinessIntro) | 整股 commission 使用 `gross × 0.000498`，正數成交只在臺銀證券電子下單整股版本套最低 20 元，commission fractional TWD 截至整元。 |
| 零股電子交易最低 1 元優惠至民國 115 年底 | [臺銀證券新聞 1157](https://www.twfhcsec.com.tw/News/NewsContent?ID=1157) | 零股版本的最低 commission 為 1 元，有效至 2026-12-31；不把優惠延長到下一版本。 |
| 普通股票證交稅 3‰；其他核准有價證券的稅率規範 | [財政部證券交易稅說明](https://www.etax.nat.gov.tw/etwmain/tax-info/understanding/tax-saving-manual/national/securities-transaction-tax/JNxPwlJ)、[證券交易稅條例](https://law-out.mof.gov.tw/LawContent.aspx?id=FL006079&kw=10%E5%A4%A9%E5%85%A7&media=print) | 只在 `sell` 套稅；本版本直接支持 `ordinary_stock` 的 3‰ 與明確 `equity_etf` 的 1‰。 |
| ETF 不能只以泛稱判斷稅率 | [臺灣證券交易所公司簡介／交易稅說明](https://www.twse.com.tw/zh/about/company/guide.html) | 泛稱 `ETF`、債券 ETF、`other_approved_security` 一律要求更明確的商品子型別，不會自動映成 1‰；債券 ETF 等例外另建版本。 |
| 稅款的整元結算 | 本卡明確標記為研究估算假設；本次沒有把臺銀手續費備註或不相干的官方經收文件當成證交稅捨去法源。 | 稅額採「整元、fractional TWD 截至整元」的保守研究估算，實際以 broker／稅單為準。 |

重要區分：臺銀業務介紹中的「小數點以下無條件捨去」只用來支持 commission rounding；sell tax 的 3‰／1‰ 由財政部證交稅規定支持，但本卡的「整元截斷」是獨立標示的研究估算假設，沒有把手續費備註直接擴張成稅款規則。

## 3. Policy 契約

### 3.1 支援商品與 lot

- `ordinary_stock`：普通股，sell tax `0.003`。
- `equity_etf`：明確排除債券 ETF 的股票型 ETF 子型別，sell tax `0.001`。
- `unknown`、泛稱 `ETF`、`bond_etf`、`other_approved_security` 等未細分商品：fail-closed，拒絕估算，不回傳 `tax=0` 的假完整成本。
- `full_lot`：單筆股數必須是 1,000 股倍數，最低 commission 20 元。
- `odd_lot`：單筆股數為 1–999 股，最低 commission 1 元。consumer 對單一零股委託最多配置 999 股，不拆成多筆以避免重複最低費；若資金足夠但超過上限，結果會在 `unallocated_allocations` 記錄未配置預算。
- 零成交股數的 `no_trade` 不收最低 commission，也不收 sell tax。

### 3.2 計算與聚合

對單一有效成交：

```text
gross = price × quantity_shares
commission = max(truncate_twd(gross × 0.000498), lot_minimum)
sell_tax = truncate_twd(gross × tax_rate)  # 僅 sell 且商品明確支持
total_cost = commission + sell_tax
slippage = 0  # not modeled，不代表 observed fill
```

同一 `order_id` 的 fills 只在 `trade_date + side + instrument_type + lot_type` 都一致時聚合；價格不是 identity 的一部分。不同成交價先累計各 fill 的 gross，再只套一次最低 commission。sell tax 仍以每個 fill 的 gross 各自做整元研究估算後加總，避免把「最低手續費聚合」誤套到稅款。不同 `order_id` 各自套最低費；同一 order id 的 identity 不一致直接拒絕，避免靜默拆單。

例：同一整股委託以 0.01 元成交 1,000 股、再以 0.02 元成交 1,000 股，gross 合計 30 元，commission 仍是 20 元，不是兩次 20 元。

## 4. 可執行入口與 consumer

### 4.1 CLI

單筆估算：

```powershell
.\.venv\Scripts\python.exe scripts\estimate_banktaiwan_cost.py `
  --order-id demo-buy --trade-date 2026-09-14 --side buy `
  --lot-type full_lot --instrument-type ordinary_stock `
  --price 100 --quantity-shares 1000
```

同一委託的多價格 fills：

```powershell
.\.venv\Scripts\python.exe scripts\estimate_banktaiwan_cost.py `
  --order-id demo-multi --trade-date 2026-09-14 --side buy `
  --lot-type full_lot --instrument-type ordinary_stock `
  --fill 0.01:1000 --fill 0.02:1000
```

CLI JSON 的 Decimal 金額以字串輸出，避免輸出邊界把核心精度轉成二進位 float。

### 4.2 Recommendation portfolio `NEXT_OPEN`

`RecommendationPortfolioBacktestService.run_portfolio_backtest` 以 opt-in 參數接線：

```python
cost_policy_id="banktaiwan-electronic-order-v1"
cost_policy_lot_type="full_lot"  # 或 odd_lot
cost_policy_instrument_type="ordinary_stock"  # 或明確 equity_etf
execution_contract=NEXT_OPEN_CONTRACT  # from backtest_module.broker_simulator
```

其中 `NEXT_OPEN_CONTRACT` 的目前實際值為 `next-session-open.v2`；呼叫端應匯入常數，不要自行拼接字串。

接線契約：

1. affordability loop 先以 next-session open 和當時可用現金求候選股數，再用同一 policy 驗證最低 commission；資金不足一張整股時不建立有效 fill。
2. `ConservativeFillPolicy` 產生部分成交後，實際扣款再次以同一 `order_id + execution_date + side + instrument + lot` policy 計算；partial fill 不沿用候選股數的成本。
3. trade row、cash ledger、summary、credibility manifest、details 都攜帶 `cost_policy_id`／`cost_policy_version`，並明示 `cost_basis=estimated_research_only`、`broker_fill_observed=false`、`slippage_model=not_modeled`。
4. 未知商品與泛稱 ETF 在 consumer 建單前拒絕，不生成可被當作淨績效的 result。零股超過 999 股時只配置 999 股並記錄 `unallocated_allocations`。

## 5. Look-ahead 自查

- 版本只由明確 `trade_date` 選取，不讀目前時間、檔案 mtime 或未來公告。
- `NEXT_OPEN` 的 policy 日期使用實際 next-session execution date；signal snapshot 仍由既有 replay service 先限制在 `日期 <= as_of_date`。
- affordability 與實際 fill 只讀成交日可取得的 open、已保留現金、既有 known volume；不讀未來 close 或未來推薦結果。
- 到期日後（2027-01-01 起）沒有新版本時拒絕估算，不靜默沿用 2026 rate。

## 6. QA 覆蓋與結果

新增測試：

- `tests/test_banktaiwan_cost_policy.py`：Decimal／float boundary、整股／零股最低費、普通股與明確 equity ETF 稅率、未知／泛稱商品 fail-closed、零成交、交易日版本、不同價格同 order 聚合、不同 order 最低費與 identity mismatch、lot boundary、CLI。
- `tests/test_recommendation_portfolio_banktaiwan_cost.py`：整股最低費 affordability、買不起一張的 unfilled、零股 999 上限與未配置預算、partial fill 同 policy 重算、consumer metadata、future rows 不影響 next-open 結果、legacy contract／bps 混用拒絕。

執行命令與本卡結果：

```text
.\.venv\Scripts\python.exe -m pytest tests\test_banktaiwan_cost_policy.py tests\test_recommendation_portfolio_banktaiwan_cost.py -q -o addopts=
19 passed

.\.venv\Scripts\python.exe -m pytest tests\test_task_loop_04_contract.py -q -o addopts=
15 passed

.\.venv\Scripts\python.exe scripts\quant_guard_linter.py
精度與 look-ahead checks 通過

.\.venv\Scripts\python.exe -m py_compile financial_module\banktaiwan_cost_policy.py financial_module\__init__.py app_module\recommendation_portfolio_backtest_service.py scripts\estimate_banktaiwan_cost.py tests\test_banktaiwan_cost_policy.py tests\test_recommendation_portfolio_banktaiwan_cost.py qa\full_app_healthcheck\test_inventory.py
exit 0

.\.venv\Scripts\python.exe -m mypy --explicit-package-bases financial_module\banktaiwan_cost_policy.py financial_module\__init__.py app_module\recommendation_portfolio_backtest_service.py scripts\estimate_banktaiwan_cost.py tests\test_banktaiwan_cost_policy.py tests\test_recommendation_portfolio_banktaiwan_cost.py qa\full_app_healthcheck\test_inventory.py
Success: no issues found in 7 source files

.\.venv\Scripts\python.exe scripts\estimate_banktaiwan_cost.py --order-id demo-buy --trade-date 2026-09-14 --side buy --lot-type full_lot --instrument-type ordinary_stock --price 100 --quantity-shares 1000
exit 0；JSON commission=49、total_cost=49
```

pytest 的既有 `.pytest_cache` 寫入權限 warning 不影響測試結果；未執行正式資料重建、SQLite 寫入、broker 連線或 UI 變更。

## 7. 未解項與回滾

- 本 policy 不是實際臺銀證券 fill／對帳單；滑價、部分成交的實際時間序列、券商特殊商品稅務與手續費優惠仍需另有官方／broker receipt 才能升級證據等級。
- 每日 learning 的固定 `50bp`、既有 calibration after-cost lineage 與 legacy close 成本仍是既有契約；本卡只記錄 gap，不偷換歷史標籤。
- 2027-01-01 後必須新增並明確註冊版本，否則 fail-closed。
- 回滾只需移除本卡新增的 policy／CLI／targeted tests／QA doc，並還原 `financial_module/__init__.py` 與 `app_module/recommendation_portfolio_backtest_service.py` 的本卡差異；不涉及正式資料、SQLite、raw 或 scheduler。
