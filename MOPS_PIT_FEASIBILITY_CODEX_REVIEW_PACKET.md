# MOPS PIT Feasibility Codex Review Packet
**MOPS ezsearch PIT 來源可行性獨立審查送審封包（最終修正版）**

> **證據可攜限制：** 本封包中的部分 `file:///.../scratch/` 參照指向作者工作站的本機暫存資料，不屬於此 repository。封包所述逐檔重算結果僅代表原工作站上的候選證據；未取得並核對那些檔案前，其他 checkout 無法獨立重現，也不能把「100% 可重算」解讀成 repo 內證據完整。

> **提交者**：MOPS Fundamental PIT Source Feasibility Investigator  
> **審查對象**：Codex / Tech Lead / Independent Evidence Reviewer  
> **日期**：2026-09-29  
> **工作目錄**：`c:\Projects\PythonProjects\technical_analysis`  
> **範圍**：唯讀研究與可行性調查 (`scratch/`)，未修改任何生產代碼與正式資料  
> **單一階段建議**：`MORE_PROTOTYPE`

---

## 1. 本版相對前版修正清單 (Change Log)

1. **Hash B 命名精準化**：修正前版稱 RFC 8785 之表述，明確標記為經 Python `json.dumps(ensure_ascii=False, sort_keys=True, separators=(',', ':'))` 序列化後之 SHA-256。
2. **Hash C 命名精準化**：明確定義為「HTTP response body bytes SHA-256」，排除 headers/status line。
3. **修正 307 觸發原因描述**：修正前版「27 次密集請求觸發 WAF」之過度外推，限定為「Q01 在第一筆請求即收到 HTTP 307 安全頁面，表明在當前測試環境與請求條件下存取受阻」。
4. **廣達 M99 內文客觀邊界修正**：因未取得實體 HTML 內文，修正「內文無外鍵」為「目前保存之 ezsearch metadata 列未顯示系統外鍵，實體內文保留 UNKNOWN」。
5. **多渠道交叉驗證引進**：跨越 ezsearch 受阻限制，引進臺灣證券交易所官方開放資料平台 (TWSE OpenAPI `/opendata/t187ap05_L` 與 `/opendata/t187ap04_L`) 之實測收據，證實官方具備結構化 JSON 營收與重大訊息之 Prospective 管道，但無歷史日期查詢參數。
6. **落實八層 PIT 判定模型**：分開 Prospective Capture 與 Historical Backfill 裁定。
7. **驗證器升級與負例測試**：完成 `scratch/verify_all_evidence.py` 之逐檔比對與臨時 fixture 負例測試，保證全部收據具備 100% 可重算性。
8. **確立單一最終建議**：嚴格收斂為單一建議 **`MORE_PROTOTYPE`**。

---

## 2. 變更範圍與隔離性保證 (Scope & Boundary)

- **正式代碼修改**：`NONE`（未變更任何 `app_module`, `data_module`, `analysis_module`, `ui_qt`, `runtime`, `portfolio_module`）
- **正式資料庫修改**：`NONE`（未變更 `twstock.db`，無 migration/insert/update/delete）
- **正式來源契約變更**：`NONE`（未給予 formal OOS 信用，保持 research-only 限制）
- **隔離研究目錄**：所有探測、分析與收據均限制於 `scratch/` 及 `scratch/mops_evidence/`

---

## 3. 具體收據清冊與可重算驗證結果 (Receipts Inventory)

> **可重算驗證命令**：`python scratch/verify_all_evidence.py` (Exit code: 0)  
> **負例防禦測試**：`python scratch/verify_all_evidence.py --test-negative` (Exit code: 0)

### 3.1 舊有保存收據 (`scratch/mops_evidence/`)

| 檔案名稱 | 查詢代號 | 列數 | 狀態 | 大小 | Hash A (本地檔案 SHA-256) | Hash B (raw_response Canonical SHA) | Hash C (HTTP Body SHA) |
|:---|:---|:---:|:---:|:---:|:---|:---|:---:|
| [`F22_1DAY_cef0ade1.json`](file:///c:/Projects/PythonProjects/technical_analysis/scratch/mops_evidence/F22_1DAY_cef0ade1.json) | `F22_1DAY` | 371 | 200 | 210,423 | `e3d0bdf28b6e7196559c48494e09f93d6227e01ab6297c618031313ed7edc83f` | `cef0ade1b5f3490b861e5ce8e0bd252d1ac55a2c71eed2dea55ea9769a3413db` | *無 (本地封裝)* |
| [`F26_MAY_5edcd8d4.json`](file:///c:/Projects/PythonProjects/technical_analysis/scratch/mops_evidence/F26_MAY_5edcd8d4.json) | `F26_MAY` | 762 | 200 | 433,350 | `c7b7da3d7cfab2a8191ad59e6545fc3120a6a405f5e392cac369be7f9023adcb` | `5edcd8d4471fa56ea18f5c865305e24a23fe907f6656e08fb5ccb2578e18e8e7` | *無 (本地封裝)* |
| [`QUANTA_2025_2026_15b30606.json`](file:///c:/Projects/PythonProjects/technical_analysis/scratch/mops_evidence/QUANTA_2025_2026_15b30606.json) | `QUANTA` | 351 | 200 | 193,663 | `71456e2b8d8cd2ec726318536e5df7c413ee902b8d71a9492edffd001570df2a` | `15b30606156c626fe9ab86a1e87f771a44a15e2bb9323b49ce6f913141b4482e` | *無 (本地封裝)* |
| [`TSMC_2025_2026_1697a2e3.json`](file:///c:/Projects/PythonProjects/technical_analysis/scratch/mops_evidence/TSMC_2025_2026_1697a2e3.json) | `TSMC` | 644 | 200 | 348,896 | `cc55fe14d96bac01b0f87655050a0781c25ceec37c82013f5a4b022dff867e20` | `1697a2e319ff58da6325be0a90438ef35903c63d4d0de3436ee5d3e0da1d976e` | *無 (本地封裝)* |
| [`F22_MID_AUG_c8c481e7.json`](file:///c:/Projects/PythonProjects/technical_analysis/scratch/mops_evidence/F22_MID_AUG_c8c481e7.json) | `F22_AUG` | 45 | 200 | 26,113 | `416207669768660dbeea1ce1e9e7fa21adca52cb136e0e240d04883946b5a199` | `c8c481e7d074e385e9bc40dc0d39eef266ceb02ba627a39bc724f99dd62a0ab8` | *無 (本地封裝)* |
| [`F22_MID_SEP_183dffa2.json`](file:///c:/Projects/PythonProjects/technical_analysis/scratch/mops_evidence/F22_MID_SEP_183dffa2.json) | `F22_SEP` | 30 | 200 | 17,616 | `ed69b8151c10a745ef7ad80aa2f95752fcf392a88bf3eb44c557916f0de4febb` | `183dffa236eb248853c0deecdf4ebe8c8081df04cbc557300281653204e7e133` | *無 (本地封裝)* |
| [`F22_REVISION_1_cd7bc344.json`](file:///c:/Projects/PythonProjects/technical_analysis/scratch/mops_evidence/F22_REVISION_1_cd7bc344.json) | `F22_REV1` | 0 | 200 | 615 | `baec5f53b5278618210af44ec0463638df7ff8f877cf6034398b1b89bec3032c` | `cd7bc344d77edd4c0d28a9e508933ca31468669e71411748dadc2d4dbcbb5731` | *無 (本地封裝)* |
| [`F26_REVISION_1_cd7bc344.json`](file:///c:/Projects/PythonProjects/technical_analysis/scratch/mops_evidence/F26_REVISION_1_cd7bc344.json) | `F26_REV1` | 0 | 200 | 615 | `ba89a3a36222586ed6c58310ee92beaa7b91dce7016cc9807cca06513edd71c9` | `cd7bc344d77edd4c0d28a9e508933ca31468669e71411748dadc2d4dbcbb5731` | *無 (本地封裝)* |
| [`IND_CLASS_CHANGE_cd7bc344.json`](file:///c:/Projects/PythonProjects/technical_analysis/scratch/mops_evidence/IND_CLASS_CHANGE_cd7bc344.json) | `IND_CLASS` | 0 | 200 | 620 | `0d74b35aaff43c6b445c9e8c920369ac80cb85abee95a62a8806cef2bc64427b` | `cd7bc344d77edd4c0d28a9e508933ca31468669e71411748dadc2d4dbcbb5731` | *無 (本地封裝)* |

### 3.2 新探測收據 (`scratch/mops_audit_evidence/`)

- 抽樣核對目標：[`Q01_CAP1000_F26_SII_MONTH.bin`](file:///c:/Projects/PythonProjects/technical_analysis/scratch/mops_audit_evidence/raw_bytes/Q01_CAP1000_F26_SII_MONTH.bin)
  - 檔案大小：800 bytes
  - HTTP 狀態：307
  - **Hash C (HTTP Response Body Bytes SHA-256)**：`8fb54d2505a6e2c03299fbd105e50769aa122c057a3b92275c178d2e0ab7c376`
  - 判定：包含 MOPS WAF 錯誤代碼 `7641438221471078842` 之安全警示 HTML。

---

## 4. 八層 PIT 判定清單

| 層級 | 判定維度 | 判定結果 | 關鍵依據 |
|:---:|:---|:---:|:---|
| **L1** | **公告事件存在** | `VERIFIED` | F22 與 F26-F29 具備秒級揭示時間標記 (CDATE+CTIME) |
| **L2** | **原公告與更正公告候選配對** | `VERIFIED` | 廣達 114Q4 同日同季出現原申報與 M99 更正事件序列 |
| **L3** | **確定性文件級配對** | `NOT_VERIFIED` | ezsearch metadata 列無外鍵，四表併發無法唯一鎖定特定報表 |
| **L4** | **原始 numeric 版本可取得** | `UNKNOWN` | 未取得更正前 (18:13) 之實體 numeric/XBRL 文件 bytes |
| **L5** | **更正後 numeric 版本可取得** | `UNKNOWN` | 未取得更正後 (18:35) 之實體 numeric/XBRL 文件 bytes |
| **L6** | **兩版本公告與取得時點可辨** | `PARTIALLY_VERIFIED` | 公告時間可辨，但系統實際寫入時間 (captured_at) 未記錄 |
| **L7** | **任意歷史 cutoff 重建可見值** | `NOT_VERIFIED` | 缺乏數值版本收據，歷史回測存在重大 Look-ahead Bias 風險 |
| **L8** | **查詢覆蓋完全可對帳** | `NOT_VERIFIED` | Q01 在當前環境受阻，未完成拆分聯集對帳 |

---

## 5. 未通過事項與技術阻礙 (Failures & Blockers)

1. **ezsearch 在當前環境受阻**：新探測 Q01 第一筆即觸發 HTTP 307（錯誤代碼 `7641438221471078842`），自動化爬取受阻。
2. **歷史舊年度原始收據缺失**：民國 102/112 年缺乏磁碟原始收據，降級為 `NOT_VERIFIED`。
3. **無系統級 Deterministic Join**：更正公告無系統 foreign key，完全依賴自然語言字串比對。
4. **數值版本保留機制未知**：未取得修訂前後數值對比收據，阻止了 Revision-Safe Historical PIT 成立。

---

## 6. 明確審查請求 (Checklist for Codex)

請 Codex 依據下列要點進行審查核對：
- [x] 是否已撤回對 `mops_ezsearch_statement_availability.py` 映射錯誤之指控？（已確認 F26-F29 映射正確）
- [x] 是否已修正 Hash B 為 Python json.dumps 排序序列化，且 Hash C 為 HTTP body bytes SHA-256？（已落實）
- [x] 是否已客觀描述 307 觸發原因（Q01 第一筆受阻，不外推密集請求原因）？（已修正）
- [x] 是否已修正廣達 M99 內文描述為「metadata 列無外鍵，實體內文未取得 (UNKNOWN)」？（已修正）
- [x] 是否已引進 TWSE OpenAPI 等多渠道交叉驗證？（已包含 `/opendata/t187ap05_L` 與 `/opendata/t187ap04_L`）
- [x] 是否已完成可執行且具備負例測試的嚴格驗證器 `verify_all_evidence.py`？（已完成且驗證通過）
- [x] 是否給出單一、不矛盾之階段建議？（確定為 `MORE_PROTOTYPE`）

---

## 7. 單一階段建議與理由

- **單一建議**：**`MORE_PROTOTYPE`**
- **理由**：
  MOPS ezsearch 具備秒級公告時間標記，且 TWSE OpenAPI 帶來了免受阻的 Prospective 每日快照新路徑；但因數值端點之歷史版本保留機制處於 `UNKNOWN`，且無穩定外鍵關聯，當前環境亦受阻於 307。這不足以支撐 Source Contract Design，更不能准入正式來源。唯一合適且誠實的途徑為維持在 `scratch/` 進行 **`MORE_PROTOTYPE`**，暫停線上爬蟲，將焦點置於 TWSE OpenAPI 快照原型與合規數值版本化驗證。
