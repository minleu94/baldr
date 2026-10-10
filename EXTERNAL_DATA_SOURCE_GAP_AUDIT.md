# Executive Summary

> **狀態補記（2026-10-10）：** 原摘要與候選矩陣有部分結論被後續證據否定或限縮。請以本段更新後判斷及 [GEMINI_EXTERNAL_DATA_AUDIT_REVIEW.md](GEMINI_EXTERNAL_DATA_AUDIT_REVIEW.md) 的逐項審查為準；這份報告不代表正式來源接納或完整 PIT gate 通過。

1. **我們現在真的缺哪些資料？**
   - **歷史產業分類 (Historical Industry Classification)**：完整歷史 PIT 尚未成立；目前的事件候選不含可證實的完整初始分類、變更、effective interval 與全市場覆蓋。
   - **真實交易成本與流動性 (Transaction Cost & Liquidity)**：缺乏可證明歷史逐筆價差或衝擊成本的資料。Gross-return 研究可明示限制；宣稱真實 after-cost／可成交表現時，固定費稅估算不足以替代 spread/impact evidence。
   - **TDCC 歷史資料 (TDCC Historical Data)**：近期已有官方候選及正式覆蓋記錄；更舊歷史仍需另驗合法可取得範圍。OpenAPI 近期可用不代表完整歷史已補齊。

2. **哪些只是缺 evidence (PIT/Publication Timestamp)？**
   - **月營收與季報的歷史公告日 (Fundamental PIT)**：MOPS 畫面及 F26–F29 bounded adapter 有秒級公告時間候選；這不證明正式 `available_at` 語意、數值版本關聯或完整歷史。現有研究 policy 與正式來源接納仍須分開判讀。

3. **哪些只是 pipeline 沒接好？**
   - **三大法人與信用交易 (Institutional & Credit)**：舊 candidate register 的 `formal_records=0` 不代表正式表為空。2026-09-21 唯讀 QA 記錄 `institutional_flows=229,472`、`credit_transactions=22,163`，最新資料同為 2026-09-08；這些列數不證明新鮮度或治理接納，pipeline/consumer 狀態須另查。

4. **哪些只是等待自然 maturity？**
   - **ML 預測成果 (Outcome Evaluation - Natural Forward)**：M11 原始摘要僅記 1 capture、19 pending、0 matured、0 outcome artifact，reason 為 `personal_outcome_source_or_cost_incomplete`。摘要沒有 19 筆逐列原因，因此自然到期等待的比例尚未證實，不能把 `not_evaluable` 一概歸因於 maturity。

5. **是否真的需要購買新資料源？**
   - **依目標歷史窗與資料聲明決定**。個人研究目前可在明示的來源／PIT 限制下先不購買；若要求全歷史、多市場、可稽核的 fundamental/industry PIT，免費來源是否足夠尚未證明。ezSearch 秒級列、事件爬蟲或未來增量累積都不能單獨證明完整回建。

---

# Verified Gap Registry

> 表內月份、季度與 candidate 數值保留原調查快照，不能視為 2026-10-10 的即時覆蓋；現況以連結的 Snapshot、source register 與日期化 QA 為準。以下分類已按後續獨立審查修正。

| Dataset / Evidence | Existing source | Current coverage | Historical coverage | PIT status | Availability timestamp status | Revision evidence | Current problem | External source actually needed? | Classification |
|---|---|---|---|---|---|---|---|---|---|
| 月營收 (Monthly Revenue) | TWSE OpenData / MOPS CSV | `2026-06` (待正式 apply) | Available (Values only) | `official_publication_timestamp_missing` | Missing explicit `available_date` | None | Formal DB stuck, no historical PIT timestamp | Yes (For PIT timestamp) | `PIT_EVIDENCE_MISSING` |
| 季報 (Quarterly Statements) | MOPS | `2024-Q1` (待正式 apply) | Available (Values only) | `official_publication_timestamp_missing` | Missing | None | Missing actual announcement dates | Yes (For PIT timestamp) | `PIT_EVIDENCE_MISSING` |
| 產業分類 (Industry Classification) | TWSE B12.00 PDF, Website | Current-only | Unknown | `industry_membership_pit_unavailable` | Missing | Manual tracking | No historical mapping API; safe boundary `2026-05-01` | Yes (Required for PIT) | `DATA_MISSING` |
| TDCC 集保持股分散 | TDCC OpenAPI `1-5` | Latest week | Missing | OK for recent | Weekly publish | N/A | Official API doesn't support full historical polling | Yes | `COVERAGE_MISSING` |
| 三大法人 & 信用交易 (Inst/Credit) | TWSE/TPEx OpenData | 舊候選快照為 `2026-08-28`；2026-09-21 formal QA 最新同為 `2026-09-08` | Formal QA 記有資料列，非空 | Source timestamp 不足以判定目前可用性 | 需另驗 | 需另驗 | formal QA 記錄 229,472 institutional 與 22,163 credit rows；不證明 freshness 或 governance admission | 不應從舊 `formal_records=0` 推斷；先查資料新鮮度及 consumer | `FRESHNESS_AND_GOVERNANCE_REVIEW` |
| 交易成本與流動性 (Transaction Cost) | None (Fixed estimations) | N/A | N/A | N/A | N/A | N/A | `after_cost` targets missing or degraded | Yes (If strict cost required) | `OUTCOME_INPUT_MISSING` |
| 預測評估 (Outcome Evaluation) | N/A | M11 snapshot：1 capture、19 pending、0 matured、0 outcome artifact | 尚無 outcome artifact | reason 為 combined source/cost incomplete | 不適用 | 不適用 | M11 summary 未提供 pending rows 的逐列原因 | Cause breakdown 未證；不能全部歸因自然成熟等待 | `CAUSE_BREAKDOWN_NOT_PROVEN` |

---

# Candidate Source Matrix

| Gap | Candidate | Authority | PIT capable | Historical availability | Automation | Cost | Confidence | Decision |
|---|---|---:|---:|---|---|---|---|---|
| Fundamental PIT (月營收/季報公告日) | MOPS ezSearch 秒級事件候選＋既有 F26–F29 bounded adapter | High | Partial research evidence; formal `available_at` not established | Full revision/history coverage unverified | Prototype / source-limited | Free candidate | Medium | Research candidate only; not a formal PIT admission or proven OOS unblock |
| Historical Industry (產業分類變更) | MOPS / TWSE event discovery | High | Event dates do not establish complete effective intervals | Initial state and full-market history unverified | Partial discovery; needs scoped review | Free candidate | Low for complete reconstruction | Do not call full-history PIT; prospective collection or explicit paid-source review are options |
| TDCC 歷史資料 | 官方 OpenAPI、官方查詢與已保存的近期候選 | High | Recent data only; availability policy scoped | Longer historical span not proven | Prospective capture possible | Free candidate | Medium for recent coverage | Useful for bounded recent window; old history requires separate source/retention review |
| 交易成本 (Bid-Ask Spread) | Fixed fee/tax scenarios; spread/impact source still missing | Depends on claim | No historical spread/impact PIT evidence | Not established | No verified automation | Free estimates do not prove execution cost | Low for real after-cost claim | Optional for gross-return research; required evidence for a true after-cost/execution claim |
| Inst/Credit (三大法人/信用) | Existing TWSE/TPEx data and formal tables; validate consumers and freshness | Official | Do not infer from candidate flag alone | Rows exist in 2026-09-21 QA, currentness beyond that requires refresh | Pipeline status needs targeted check | Existing sources | Medium | The old empty-formal-table claim is contradicted; do not route directly to new-source purchase or blanket pipeline fix |

---

# Official Sources

來源存在、畫面顯示時間或 API 可查，均不自動證明全歷史 coverage、修訂鏈、決策時點 `available_at` 或 formal admission；各來源應依 [獨立 review](GEMINI_EXTERNAL_DATA_AUDIT_REVIEW.md) 的範圍判讀。

1. **TWSE 政府資料開放平臺 (OpenData)**
   - URL: `https://data.gov.tw/`
   - APIs: TWSE OpenAPI (`https://openapi.twse.com.tw/v1`)
   - Verified: 月營收、三大法人、信用交易 (可用，但需自行累積)
2. **公開資訊觀測站 (MOPS)**
   - URL: `https://mops.twse.com.tw/`
   - Verified: 歷史月營收 HTML (需爬蟲，缺乏結構化公告日)。
3. **TDCC 集保結算所 OpenAPI**
   - URL: `https://smart.tdcc.com.tw/tdcc-opendata-api-docs/`
   - Verified: 股權分散表 (`1-4` / `1-5`)。只能取得當週/最新資料。
4. **臺灣證券交易所「市場公告」**
   - URL: `https://www.twse.com.tw/`
   - Verified: 產業類別變更公文公告 (需人工解析，無 API)。

---

# GitHub / Open Source Helpers

- **FinMind** (Taiwan Market Data API)
  - Authority: Third-party provider.
  - License: Open source client, API requires token.
  - Dependency Risk: Medium. Repo 過去曾測試過 `TaiwanStockMonthRevenue`，但 `create_time` 不等於官方公告時間。可用來補齊 TDCC 歷史，不可作為 Fundamental PIT。
- **Python Requests + BeautifulSoup (MOPS ezsearch 爬蟲)**
  - Authority: Official website.
  - License: Public access (需注意請求頻率避免被鎖 IP).
  - Dependency Risk: Low. 透過分析 MOPS 的 AJAX 請求（`POST`），可直接取得包含公告時間（如 `115/09/28 22:41:06`）的結構化回應，用以補齊 PIT 缺口。

---

# Rejected Sources

1. **購買第三方商業資料 (如 TEJ, FinMind)**
   - 原因: 專案目前策略為避免額外花費，優先以自行建置爬蟲與利用現有 OpenData 為主。
2. **FinMind API for Fundamental PIT (月營收公告日)**
   - 原因: 根據 repo 內 `V2_3_FINMIND_CANDIDATE_SOURCE_AUDIT_2026_07_12.md` 記載，其 `create_time` 為資料庫抓取時間 (storage-time)，並非官方原始公告日 (publication timestamp)，會引發前視偏差 (Look-ahead bias)。
3. **第三方免費財經網站 (Yahoo Finance, Cnyes 等) 取得歷史價差**
   - 原因: No historical coverage for bid-ask spreads at tick level.

---

# Recommended Acquisition Plan

按照 **correctness → PIT integrity → outcome completeness → automation reliability → research enhancement** 排序：

## P0
1. **若續做 MOPS ezSearch 原型**：先驗證端點可達性、時間欄位語意、numeric lineage、修訂事件與完整性；現有秒級畫面／F26–F29 bounded evidence 不得直接當正式 `available_at` 或宣稱 OOS blocked 已解除。
2. **若續做產業事件 discovery**：可評估部分公告事件的資料化，但須先定義初始分類、effective date、市場異動及全市場 denominator；不能預先承諾爬蟲可建立完整 PIT 對照表。

## P1
3. **限定 TDCC 歷史窗**：近期官方資料可依來源政策累積；若需求含官方保存期以外的歷史，先查合法封存或商業交付，不把未來累積描述為舊資料回補。
4. **核查三大法人／信用資料的新鮮度與 consumer**：先以最新唯讀 QA 對照來源、正式表及治理狀態；不能沿用舊 `formal_records=0` 作為目前 pipeline 故障證明。

## P2
5. **交易成本研究**：成交量／週轉率可作情境或代理變數，不能由此聲稱模型已學得真實 spread／impact；先明確區分 gross、估算成本及可成交 after-cost 結果。

---

# Final Verdict

> Based on verified repository evidence and externally verified sources, does this project currently need additional external data sources?

**目前個人研究可先不購買；全歷史 PIT 是否可由免費來源補足，尚未證明。**

原因：
1. 個人研究可採明示的受限來源與歷史窗，不代表 formal PIT 或 full OOS。未來是否購買取決於使用者要求的市場、年份、修訂完整度與成本聲明。
2. MOPS 秒級候選、事件公告、TWSE/TDCC OpenData 的存在不證明完整歷史、版本 lineage 或決策可得性；是否需要外部來源仍取決於缺口與目標範圍。
3. M11 pending 原因尚未逐筆拆解；自然成熟只對經證實的未到期觀測成立，不能作為所有 `not_evaluable` 的總解釋。
