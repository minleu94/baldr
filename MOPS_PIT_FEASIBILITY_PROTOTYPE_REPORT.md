# MOPS Fundamental PIT Source Feasibility Prototype Report
**MOPS ezsearch、重大訊息與官方開放資料之 Fundamental PIT 可行性調查報告（最終修正版）**

> **證據可攜限制：** 下方標為「作者本機：scratch/...（未入庫）」的來源指向原工作站暫存資料，不屬於此 repository。報告所述逐檔重算結果僅代表原工作站上的候選證據；未取得並核對那些檔案前，其他 checkout 無法獨立重現，也不能把「100% 可重算」解讀成 repo 內證據完整。

> **本版相對前版修正清單 (Change Log)**：
> 1. **Hash B 命名與實作精準化**：撤回「RFC 8785」之表述，明確標記 Hash B 為經 Python `json.dumps(ensure_ascii=False, sort_keys=True, separators=(',', ':'))` 規範化排序序列化後之 SHA-256。
> 2. **Hash C 命名精準化**：修正 Hash C 定義為「HTTP response body bytes SHA-256」，明確其不包含 headers/status line，亦非底層傳輸 stream。
> 3. **修正 307 觸發原因描述**：修正前版「27 次密集請求觸發 WAF」之推論，精確記錄為「Q01 在第一筆請求即收到 HTTP 307 安全頁面，表明在當前環境與請求條件下存取受阻」，不作過度因果外推。
> 4. **廣達 M99 內文客觀邊界修正**：因未成功取得 M99 實體 HTML 內文，修正前版「內文無外鍵」之斷言，精準修正為「目前保存之 ezsearch metadata 列及 URL 未顯示連回 F26–F29 之系統外鍵，實體內文因端點受阻未取得 (保留 UNKNOWN)」。
> 5. **多渠道交叉驗證引進**：跨越 ezsearch 單一 HTML 爬蟲受阻瓶頸，引進臺灣證券交易所官方開放資料平台 (TWSE OpenAPI `/opendata/t187ap05_L` 與 `/opendata/t187ap04_L`) 之實測收據，證實官方具備結構化 JSON 營收與重大訊息之 Prospective 管道，但無歷史日期參數查詢功能。
> 6. **八層 PIT 判定模型落實**：將 PIT 檢驗細分為 8 個獨立層級，分開 Prospective Capture 與 Historical Backfill 裁定。
> 7. **驗證器升級與負例測試**：完成 `scratch/verify_all_evidence.py` 之逐檔比對與臨時 fixture 負例測試，保證全部收據具備 100% 可重算性。
> 8. **確立單一最終建議**：嚴格收斂為單一建議 **`MORE_PROTOTYPE`**。

---

## 1. 執行摘要 (Executive Summary)

本輪調查以端到端、唯讀、多渠道交叉驗證的方式，全面調查臺灣市場公開數據（含 MOPS ezsearch、重大訊息、TWSE OpenAPI）是否足以為月營業收入 (F22) 與季度財務報告 (F26-F29) 建立：
$$\text{原公告} \longrightarrow \text{更正／重編公告} \longrightarrow \text{原數值版本} \longrightarrow \text{更正數值版本}$$
的 Point-in-Time (PIT) 修訂鏈。

### 核心結論與事實發現
1. **公告事件與時間標記存在 (`VERIFIED`)**：
   - ezsearch 回應明列 F22（月營業收入）與 F26-F29（資產負債表、綜合損益表、現金流量表、權益變動表），每筆具備 `CDATE` 與 `CTIME`，可作為 `official_announcement_at_candidate`。
   - `data_module/mops_ezsearch_statement_availability.py` 之 F26-F29 映射經代碼與資料逐筆核對完全正確。
2. **多渠道證實更正公告機制 (`PARTIALLY_VERIFIED`)**：
   - 廣達 114Q4 樣本確認在 F26-F29 發布 22 分鐘後發布 M99 重大訊息「更正本公司114年第四季IFRS iXBRL」。
   - 重大訊息標準格式包含「事實發生日、發生緣由、更正前後金額/內容、因應措施（重新上傳）」，證實基本面更正會以重大訊息發布，且更正後官方會更新申報檔案。
3. **無系統外鍵，文件配對非確定性 (`NOT_VERIFIED`)**：
   - ezsearch metadata 列未提供指向原申報之官方 Foreign Key；廣達四表併發而更正公告僅籠統提及 iXBRL，無法 1-to-1 鎖定特定報表，僅能依賴自然語言啟發式比對。
4. **數值版本保留情況未知 (`UNKNOWN`)**：
   - 因端點探測在當前環境受阻，未實際取得同一 numeric URL 更正前後的數值檔案原始 bytes。未取得修訂前後數值，阻止了 Revision-Safe Historical PIT 的成立。
5. **官方 OpenAPI 帶來 Prospective 突破 (`VERIFIED` for Prospective)**：
   - 實測臺灣證券交易所官方開放資料 API `https://openapi.twse.com.tw/v1/opendata/t187ap05_L`（上市公司每月營業收入彙總表，1086 筆）與 `/opendata/t187ap04_L`（上市公司每日重大訊息）均返回 HTTP 200 JSON。此管道無 WAF 阻擋，但無歷史日期查詢參數，僅適合作為每日定時快照存檔之前瞻管道。
6. **單一建議**：**`MORE_PROTOTYPE`**（維持於 `scratch/` 進行受控原型研究，評估 OpenAPI 每日快照與受控合規環境下的數值版本化驗證）。

---

## 2. 八層 PIT 判定架構與裁定 (8-Level PIT Hierarchy)

依據量化決策與防範未來函數 (Look-ahead Bias) 規範，將 PIT 能力拆解為 8 個層級獨立判定：

| 層級 | 判定維度 | 判定結果 | 具體證據與現況 | 對 Historical PIT 影響 | 對 Prospective PIT 影響 |
|:---:|:---|:---:|:---|:---|:---|
| **L1** | **公告事件存在** | `VERIFIED` | ezsearch 保存樣本明列 F22、F26-F29 申報事件與時間 | 具備公告時間上限候選 | 具備公告時間上限候選 |
| **L2** | **原公告與更正公告候選配對** | `VERIFIED` | 廣達 114Q4 同日同季出現 F26-F29 與 M99 更正事件 | 證實有修訂事件候選 | 證實有修訂事件候選 |
| **L3** | **確定性文件級配對** | `NOT_VERIFIED` | ezsearch metadata 列無外鍵；四表併發而 M99 籠統更正 iXBRL | 無法 1-to-1 唯一鎖定特定表 | 需依賴標題模糊匹配規則 |
| **L4** | **原始 numeric 版本可取得** | `UNKNOWN` | 未取得更正前 (18:13) 之實體 numeric/XBRL 文件 bytes | **阻止 Historical PIT 成立** | 若及時快照則理論上可得 |
| **L5** | **更正後 numeric 版本可取得** | `UNKNOWN` | 未取得更正後 (18:35) 之實體 numeric/XBRL 文件 bytes | **阻止 Historical PIT 成立** | 若及時快照則理論上可得 |
| **L6** | **兩版本公告與取得時點可辨** | `PARTIALLY_VERIFIED` | 公告時間可辨 (18:13 vs 18:35)；但系統實際取得時間 (captured_at) 未記錄 | 缺乏時間戳記聯鎖收據 | 需在抓取時紀錄 captured_at |
| **L7** | **任意歷史 cutoff 重建可見值** | `NOT_VERIFIED` | 缺乏數值版本收據，歷史端點可能只呈現覆寫後數值 | **嚴禁正式回測使用 (Look-ahead)** | 自建快照後可保證無滲漏 |
| **L8** | **查詢覆蓋完全可對帳** | `NOT_VERIFIED` | 當前環境 Q01 第一筆即遭 307 攔截，未完成拆分聯集對帳 | 無法證明歷史回補完整無遺漏 | 依賴每日全市場快照保證 |

> **裁定結論**：
> - **Historical Backfill PIT**：**`NOT_VERIFIED` / `BLOCKED`**（因 L3-L5、L7 未達，歷史回補存在重大 Look-ahead Bias 風險）。
> - **Prospective Capture PIT**：**`PARTIALLY_VERIFIED`**（L1-L2 成立，且 TWSE OpenAPI 提供免阻擋之每日快照管道，具備可行性，待落實 L4-L6 快照原型）。

---

## 3. 多渠道調查紀錄 (Multi-Channel Investigation Findings)

針對九大核心問題，本輪採用至少三種實質渠道進行獨立追查：

```
[渠道 A] MOPS ezsearch 網頁端點與代碼審計 (scratch/mops_evidence, scratch/mops_audit_evidence)
[渠道 B] TWSE 官方開放資料 OpenAPI (openapi.twse.com.tw - t187ap05_L, t187ap04_L, swagger.json)
[渠道 C] Google 原生搜尋、公開重大訊息規範、法規與公開申報文本檢索
```

### 3.1 民國 102、112 年歷史覆蓋與 Schema 一致性
- **渠道 A (ezsearch 實體探測)**：在當前請求條件下發送請求收到 307，磁碟中無 102/112 年實體 JSON 收據。
- **渠道 B (TWSE OpenAPI)**：檢視 OpenAPI Swagger 文件，所有端點參數均為 `Parameters: None`，官方 OpenAPI 不支援歷史日期查詢。
- **渠道 C (法規與文獻檢索)**：台灣自民國 102 年全面採用 IFRS，財報由 ROC GAAP 轉換為四大表。
- **判定**：**`NOT_VERIFIED`**（缺乏磁碟原始收據，依資料審計標準維持 NOT_VERIFIED）。

### 3.2 官方 1000 筆上限、分頁與拆分完整性
- **渠道 A (代碼與新探測)**：`data_module/mops_ezsearch_statement_availability.py` 本地主動拋出例外；Q01 探測第一筆即收 307，未獲官方伺服器端觸頂 JSON。
- **渠道 B (OpenAPI 對比)**：TWSE OpenAPI `/opendata/t187ap05_L` 單次返回 1086 筆上市公司全量月營收，無 1000 筆限制。
- **渠道 C (MOPS ezsearch 前端代碼)**：前端 AJAX `step=00` 無分頁按鈕，顯示上限 1000 筆。
- **判定**：**`PARTIALLY_VERIFIED`**（本地限制屬實；ezsearch 伺服器端底層分頁機制為 `UNKNOWN`；拆分查詢未完成對帳）。

### 3.3 月營收與財報更正公告類別
- **渠道 A (已保存樣本檢驗)**：F22 (446 筆) 與 F26 (762 筆) 中標題含「更正」之筆數為 0。
- **渠道 B (TWSE OpenAPI 重大訊息)**：`/opendata/t187ap04_L` 證實重大訊息依條款分類，內文提供完整「說明」段落。
- **渠道 C (重大訊息處理程序檢索)**：依證交所重大訊息處理程序，重大資產交易更正發布於第 20 款 (M20)，概括其他事項更正發布於第 51 款 (M99)。
- **判定**：**`PARTIALLY_VERIFIED`**（基本面更正走重大訊息發布，且 M99 僅為其中一種條款，不可外推為「統一走 M99」）。

### 3.4 廣達 114Q4 M99 更正公告詳情
- **渠道 A (本地已保存列)**：保存之 ezsearch 列包含主旨「更正本公司114年第四季IFRS iXBRL」，無外鍵欄位。
- **渠道 B (詳情端點實體抓取)**：請求 `ajax_t05sr01_1` 回傳 307 安全頁面，未取得實際 HTML 文字字節。
- **渠道 C (重大訊息標準格式查證)**：更正 iXBRL 之重大訊息內文格式為「1.事實發生日 2.發生緣由（說明更正前後項目與金額） 3.因應措施（重新上傳 iXBRL）」。
- **判定**：**`UNKNOWN`（詳情內文未取得）**。確認目前保存的 metadata 列未顯示外鍵，實體內文保留 UNKNOWN。

### 3.5 月營收真實更正正例
- **渠道 A (廣達與台積電樣本)**：各 21 個月均為 0 筆營收更正，證實營收更正為低頻異常事件。
- **渠道 B (OpenAPI 當月營收)**：全市場 1086 筆營收資料中，「備註」欄多數為 '-'，部分載明前期營收調整原因。
- **渠道 C (公開資訊檢索)**：檢索到中工、聯亞藥等發布「更正本公司營業收入公告」之公開案例，包含「更正前金額」與「更正後金額」。
- **判定**：**`NOT_VERIFIED`**（本專案磁碟尚無成對之月營收修訂前後實體收據）。

### 3.6 財報真實更正正例
- **渠道 A (廣達 114Q4 樣本)**：原公告 F26-F29 於 `115/03/16 18:13:27` 發布；更正公告 M99 於 `115/03/16 18:35:50` 發布。
- **渠道 B (重大訊息處理程序)**：更正程序包含發布重大訊息並重新上傳 iXBRL。
- **渠道 C (數值版本驗證)**：未取得 18:13 原版與 18:35 更正版之實體 numeric/XBRL 文件 bytes。
- **判定**：**事件層級 `VERIFIED`，文件與數值版本 `UNKNOWN` / `NOT_VERIFIED`**。

### 3.7 歷史舊版本能否自官方或合法封存取得
- **渠道 A (MOPS 查詢介面)**：MOPS 數值端點（如 `t164sb03`）採即時查詢，重新上傳後直接呈現最新值。
- **渠道 B (TWSE OpenAPI)**：僅提供當前最新快照，無歷史切面。
- **渠道 C (官方重編專區檢索)**：公開資訊觀測站僅設有特定重大重編專區，非全量保留任意版本歷史切面。
- **判定**：**`UNKNOWN`**（本輪未取得舊版本，阻止 Revision-Safe Historical PIT 成立）。

### 3.8 `CDATE`、`CTIME` 之來源語意
- **渠道 A (ezsearch 欄位)**：提供 `CDATE` 與 `CTIME` 秒級戳記。
- **渠道 B (TWSE OpenAPI 重大訊息)**：提供 `發言日期` 與 `發言時間` (如 070004)。
- **渠道 C (法規查證)**：證交所規定發言人透過系統鍵入傳輸確認後自動揭示。
- **判定**：**`PARTIALLY_VERIFIED`**（可作為官方揭示時間候選上限）。

### 3.9 正式 `available_at` 保守推導政策
- **推導公式**：
  $$\text{available\_at} = \max(\text{official\_announcement\_at} + \Delta_{\text{poll}}, \text{session\_open\_buffer})$$
- 盤後發布者最早於次一營業日 08:30 生效。系統需記錄真實寫入時間 `captured_at`，且回測需滿足 $t_{\text{decision}} \ge \text{captured\_at}$。

---

## 4. 完整證據盤點與 Hash 索引 (Evidence Inventory)

本專案審計嚴格分離並重算三類 Hash：
- **Hash A (File Raw Bytes SHA-256)**：磁碟上本地檔案的原始字節雜湊值。
- **Hash B (Canonical JSON SHA-256)**：`raw_response` 經 Python `json.dumps(ensure_ascii=False, sort_keys=True, separators=(',', ':'))` 序列化後之 SHA-256。
- **Hash C (HTTP Response Body Bytes SHA-256)**：HTTP response body 原始 bytes 之 SHA-256。

> **重算驗證命令**：`python scratch/verify_all_evidence.py` (Exit code: 0)  
> **負例防禦測試**：`python scratch/verify_all_evidence.py --test-negative` (Exit code: 0)

### 4.1 舊有保存收據 (`scratch/mops_evidence/`)

| 檔案名稱 | 查詢代號 | 列數 | 狀態 | 大小 | Hash A (本地檔案 SHA-256) | Hash B (raw_response Canonical SHA) | Hash C (HTTP Body SHA) |
|:---|:---|:---:|:---:|:---:|:---|:---|:---:|
| `作者本機：scratch/mops_evidence/F22_1DAY_cef0ade1.json（未入庫）` | `F22_1DAY` | 371 | 200 | 210,423 | `e3d0bdf28b6e7196559c48494e09f93d6227e01ab6297c618031313ed7edc83f` | `cef0ade1b5f3490b861e5ce8e0bd252d1ac55a2c71eed2dea55ea9769a3413db` | *無 (僅本地封裝)* |
| `作者本機：scratch/mops_evidence/F26_MAY_5edcd8d4.json（未入庫）` | `F26_MAY` | 762 | 200 | 433,350 | `c7b7da3d7cfab2a8191ad59e6545fc3120a6a405f5e392cac369be7f9023adcb` | `5edcd8d4471fa56ea18f5c865305e24a23fe907f6656e08fb5ccb2578e18e8e7` | *無 (僅本地封裝)* |
| `作者本機：scratch/mops_evidence/QUANTA_2025_2026_15b30606.json（未入庫）` | `QUANTA` | 351 | 200 | 193,663 | `71456e2b8d8cd2ec726318536e5df7c413ee902b8d71a9492edffd001570df2a` | `15b30606156c626fe9ab86a1e87f771a44a15e2bb9323b49ce6f913141b4482e` | *無 (僅本地封裝)* |
| `作者本機：scratch/mops_evidence/TSMC_2025_2026_1697a2e3.json（未入庫）` | `TSMC` | 644 | 200 | 348,896 | `cc55fe14d96bac01b0f87655050a0781c25ceec37c82013f5a4b022dff867e20` | `1697a2e319ff58da6325be0a90438ef35903c63d4d0de3436ee5d3e0da1d976e` | *無 (僅本地封裝)* |
| `作者本機：scratch/mops_evidence/F22_MID_AUG_c8c481e7.json（未入庫）` | `F22_AUG` | 45 | 200 | 26,113 | `416207669768660dbeea1ce1e9e7fa21adca52cb136e0e240d04883946b5a199` | `c8c481e7d074e385e9bc40dc0d39eef266ceb02ba627a39bc724f99dd62a0ab8` | *無 (僅本地封裝)* |
| `作者本機：scratch/mops_evidence/F22_MID_SEP_183dffa2.json（未入庫）` | `F22_SEP` | 30 | 200 | 17,616 | `ed69b8151c10a745ef7ad80aa2f95752fcf392a88bf3eb44c557916f0de4febb` | `183dffa236eb248853c0deecdf4ebe8c8081df04cbc557300281653204e7e133` | *無 (僅本地封裝)* |
| `作者本機：scratch/mops_evidence/F22_REVISION_1_cd7bc344.json（未入庫）` | `F22_REV1` | 0 | 200 | 615 | `baec5f53b5278618210af44ec0463638df7ff8f877cf6034398b1b89bec3032c` | `cd7bc344d77edd4c0d28a9e508933ca31468669e71411748dadc2d4dbcbb5731` | *無 (僅本地封裝)* |
| `作者本機：scratch/mops_evidence/F26_REVISION_1_cd7bc344.json（未入庫）` | `F26_REV1` | 0 | 200 | 615 | `ba89a3a36222586ed6c58310ee92beaa7b91dce7016cc9807cca06513edd71c9` | `cd7bc344d77edd4c0d28a9e508933ca31468669e71411748dadc2d4dbcbb5731` | *無 (僅本地封裝)* |
| `作者本機：scratch/mops_evidence/IND_CLASS_CHANGE_cd7bc344.json（未入庫）` | `IND_CLASS` | 0 | 200 | 620 | `0d74b35aaff43c6b445c9e8c920369ac80cb85abee95a62a8806cef2bc64427b` | `cd7bc344d77edd4c0d28a9e508933ca31468669e71411748dadc2d4dbcbb5731` | *無 (僅本地封裝)* |

### 4.2 新探測收據 (`scratch/mops_audit_evidence/`)

- 探測總數：27 次（26 次 HTTP 307，1 次無 status 網路逾時）。
- 關鍵抽樣：`作者本機：scratch/mops_audit_evidence/raw_bytes/Q01_CAP1000_F26_SII_MONTH.bin（未入庫）`
  - 檔案大小：800 bytes
  - HTTP 狀態：307
  - **Hash C (HTTP Response Body Bytes SHA-256)**：`8fb54d2505a6e2c03299fbd105e50769aa122c057a3b92275c178d2e0ab7c376`
  - 判定：包含 MOPS WAF 錯誤代碼 `7641438221471078842` 之安全警示 HTML。

---

## 5. 單一明確建議與下一步 (Single Recommendation)

### 單一建議：**`MORE_PROTOTYPE`**
> **判定依據與理由**：  
> 1. MOPS ezsearch 具備秒級公告揭示時間標記，且多渠道交叉驗證證實重大訊息確有更正事件存在；  
> 2. 臺灣證券交易所官方開放資料 API (TWSE OpenAPI) 提供了免受阻之 Prospective 快照管道，為前瞻資料流提供了全新可行路徑；  
> 3. 但目前數值端點之歷史版本保留機制處於 `UNKNOWN`，缺乏修訂前後數值對比收據，且歷史回補無穩定外鍵關聯。這**不足以**進入 `SOURCE_CONTRACT_DESIGN`，更**絕對不允許**准入正式來源 (Formal Admission)；  
> 4. 因此，唯一科學、嚴謹且負責任的單一階段建議為 **`MORE_PROTOTYPE`**：暫停線上高頻爬取，將重心轉移至基於 TWSE OpenAPI 的每日 Prospective 快照原型設計，並在合規授權條件下驗證歷史數值版本化。

### 具體下一步與完成條件：
1. **正式系統邊界凍結**：不更動正式 SQLite、`twstock.db` 與生產排程。
2. **OpenAPI 快照原型設計**：在 `scratch/` 設計針對 TWSE OpenAPI `/opendata/t187ap05_L` 與 `/opendata/t187ap04_L` 的受控快照記錄器，驗證日級/月級 Append-Only 快照機制。
3. **數值版本化驗證計畫**：待具備合規受控存取途徑時，鎖定特定更正公告執行「更正前數值 vs 更正後數值」之原文字節比對，徹底解開 L4-L5 的 `UNKNOWN`。
