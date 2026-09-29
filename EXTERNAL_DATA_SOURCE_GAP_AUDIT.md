# Executive Summary

1. **我們現在真的缺哪些資料？**
   - **歷史產業分類 (Historical Industry Classification)**：目前 repository 內依賴 2026-05-01 邊界與最新分類（current-only），缺乏全歷史的 PIT (Point-In-Time) 產業變更證據。
   - **真實交易成本與流動性 (Transaction Cost & Liquidity)**：目前缺乏歷史逐筆買賣價差 (bid-ask spread) 或衝擊成本資料，使得 outcome evaluation 的 after-cost 計算被迫保持 missing 或使用固定手續費估算（臺銀成本列為研究限定）。
   - **TDCC 歷史資料 (TDCC Historical Data)**：TDCC 官方 OpenAPI (`/v1/opendata/1-5`) 僅提供最新或近期週頻資料，無法完整輪詢歷史，導致新啟動的環境缺乏歷史集保持股分散資料。

2. **哪些只是缺 evidence (PIT/Publication Timestamp)？**
   - **月營收與季報的歷史公告日 (Fundamental PIT)**：資料值本身（如 EPS、月營收數字）可透過 TWSE/MOPS 取得，但欠缺官方發布時間戳記 (publication/announcement timestamp)。目前使用 `first-seen` 或 expected period 會導致 PIT 證據不滿足 (`official_publication_timestamp_missing`)。

3. **哪些只是 pipeline 沒接好？**
   - **三大法人與信用交易 (Institutional & Credit)**：官方 OpenData 與 endpoint 其實有提供，目前專案內也已寫入 candidate schema (Phase 3C backfill 成功抓取 126,014 列)。問題在於 pipeline 需要通過 governance/acceptance 才會進到 formal DB (`formal_records=0`)，因此這是 `PIPELINE_WIRING_MISSING`。

4. **哪些只是等待自然 maturity？**
   - **ML 預測成果 (Outcome Evaluation - Natural Forward)**：部分 V4/V6 的 Outcome `not_evaluable` 或 `missing` 是因為 pending insufficient future data（尚未到期），而非缺乏外部資料來源（`NATURAL_EVIDENCE_NOT_YET_MATURE`）。

5. **是否真的需要購買新資料源？**
   - **PARTIALLY (部分需要)**。
     - **不需要**購買外部資料。
     - **月營收與季報的精確公告日 (PIT)**：可以透過建立自行維護的網路爬蟲，定期抓取「公開資訊觀測站 - 公告快易查 (ezsearch)」的 AJAX 端點，以獲取精確到秒的歷史公告時間。
     - **歷史產業分類與 TDCC**：可利用既有 OpenAPI，配合定期抓取與增量累積，自行建立歷史資料庫。

---

# Verified Gap Registry

| Dataset / Evidence | Existing source | Current coverage | Historical coverage | PIT status | Availability timestamp status | Revision evidence | Current problem | External source actually needed? | Classification |
|---|---|---|---|---|---|---|---|---|---|
| 月營收 (Monthly Revenue) | TWSE OpenData / MOPS CSV | `2026-06` (待正式 apply) | Available (Values only) | `official_publication_timestamp_missing` | Missing explicit `available_date` | None | Formal DB stuck, no historical PIT timestamp | Yes (For PIT timestamp) | `PIT_EVIDENCE_MISSING` |
| 季報 (Quarterly Statements) | MOPS | `2024-Q1` (待正式 apply) | Available (Values only) | `official_publication_timestamp_missing` | Missing | None | Missing actual announcement dates | Yes (For PIT timestamp) | `PIT_EVIDENCE_MISSING` |
| 產業分類 (Industry Classification) | TWSE B12.00 PDF, Website | Current-only | Unknown | `industry_membership_pit_unavailable` | Missing | Manual tracking | No historical mapping API; safe boundary `2026-05-01` | Yes (Required for PIT) | `DATA_MISSING` |
| TDCC 集保持股分散 | TDCC OpenAPI `1-5` | Latest week | Missing | OK for recent | Weekly publish | N/A | Official API doesn't support full historical polling | Yes | `COVERAGE_MISSING` |
| 三大法人 & 信用交易 (Inst/Credit) | TWSE/TPEx OpenData | `2026-08-28` in candidate | Available | OK | OK | OK | Exists in candidate DB, but formal DB is empty (`formal_records=0`) | No (Fix pipeline) | `PIPELINE_WIRING_MISSING` |
| 交易成本與流動性 (Transaction Cost) | None (Fixed estimations) | N/A | N/A | N/A | N/A | N/A | `after_cost` targets missing or degraded | Yes (If strict cost required) | `OUTCOME_INPUT_MISSING` |
| 預測評估 (Outcome Evaluation) | N/A | N/A | N/A | OK | OK | N/A | `mature observations 0`, waiting for future data | No | `NATURAL_EVIDENCE_NOT_YET_MATURE` |

---

# Candidate Source Matrix

| Gap | Candidate | Authority | PIT capable | Historical availability | Automation | Cost | Confidence | Decision |
|---|---|---:|---:|---|---|---|---|---|
| Fundamental PIT (月營收/季報公告日) | MOPS 公告快易查 (ezsearch) 爬蟲 | High | YES | Full history (需自行累積) | Medium (需實作爬蟲) | Free | High | REQUIRED (自行開發) |
| Historical Industry (產業分類變更) | MOPS / TWSE 公告爬蟲 | High | YES | Full history (需自行累積) | Medium (需實作爬蟲) | Free | High | REQUIRED (自行開發) |
| TDCC 歷史資料 | 官方 OpenAPI 增量累積 | High | YES | Verified (Repo history) | High | Free | High | USEFUL |
| 交易成本 (Bid-Ask Spread) | 固定手續費估算或大盤流動性推估 | Medium | YES | N/A | High | Free | Medium | OPTIONAL |
| Inst/Credit (三大法人/信用) | 修正既有 TWSE/TPEx Pipeline | Official | YES | Already in candidate | High | Free | High | NOT_NEEDED — FIX EXISTING PIPELINE |

---

# Official Sources

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
1. **實作 MOPS 公告快易查 (ezsearch) 爬蟲**：這是解決「月營收與季報缺乏精確公告時間 (PIT)」的最佳免費方案。透過攔截並模擬 `mopsov.twse.com.tw/mops/web/ezsearch` 的 AJAX POST 請求，可以直接抓取到包含年月日時分秒的真實公告時間，解決 OOS blocked 的問題。
2. **實作產業分類歷史變更爬蟲**：透過爬取公開資訊觀測站的歷史重大訊息，解析產業分類變更公告，建立自己的 PIT 產業對照表。

## P1
3. **建立 TDCC 歷史資料累積機制**：官方 API (`1-5`) 雖無完整歷史輪詢，但可透過排程定期抓取並儲存當週資料，逐步累積成內部歷史資料庫。
4. **修復既有 Pipeline (三大法人、信用)**：不需外部購買，但需解除 `PIPELINE_WIRING_MISSING` 與 governance blocks，讓已抓到的候選資料寫入正式 DB。

## P2
5. **交易成本估算模型**：在不購買 Tick Data 的情況下，可利用現有的成交量、週轉率等數據，建立滑價 (Slippage) 的機器學習推估模型。

---

# Final Verdict

> Based on verified repository evidence and externally verified sources, does this project currently need additional external data sources?

**NO (不需要)**

原因：
1. **自行開發爬蟲可解決 P0 缺口**：使用者已經明確指出 MOPS「公告快易查 (ezsearch)」擁有我們需要的精確公告時間。透過 Python 的 `requests` 模擬 AJAX POST 請求，我們完全可以自行抓取真實的 Publication Timestamp，建立滿足 PIT 規範的本地資料庫，無需購買外部 API。
2. **官方 OpenData 足以支援**：包含三大法人、信用交易、TDCC 集保等，官方均有提供 API 或 CSV。只要落實本地的排程抓取與增量累積（Incremental Loading），並修復 Pipeline Wiring，即可補足歷史缺口。
3. **等待成熟 (Maturity Issues)**：Outcome evaluation 的 `not_evaluable` 是因為時間未到 (Natural forward data is not yet mature)，買再多資料也無法加速未來的時間。
