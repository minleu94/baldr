# Track B 金融資料交付契約

本契約約束 Track B 對 Track C（ML 資料）與 Track A（唯讀研究展示）的交付。它不建立來源接受、不啟動訓練、不改 Ledger，也不取代各來源的用途契約。2026-10-22 實際觀測、具名狀態矩陣及工程缺口見 [Track B 驗收](../06_qa/BALDR_TRACK_B_DATA_OPERATIONS_20261022.md)。

## 共通身份與資格

每個交付單位必須帶以下欄位；缺件保留 null／unknown 及具名拒絕原因，不能補零或選取鄰近版本。

| 欄位組 | 必要內容與判讀 |
|---|---|
| Source | source family／source ID、venue、endpoint、parser/schema version、用途接受 reference 與外部 SHA；公開授權不等於金融用途接受 |
| Version／Custody | 原始 bytes artifact reference／SHA、revision ID／parent revision、原件取得／保存時間、custody 根／DB 身份；file-byte SHA 與 canonical content hash 顯名區分 |
| Time | decision timestamp／timezone、source date／period、available_at 及其依據、cutoff、capture completion、persisted_at；未知官方發布時間不得用本機時間冒充 |
| Coverage | requested／eligible／observed／missing／excluded／unknown 的分母、代號與日期範圍；無明確分母不能由 row count 宣稱全市場完整 |
| Quality | 欄位／單位、缺值／重複／日期衝突／修訂／staleness 及 blocker；金額與決策運算維持 Decimal／整數契約 |
| Execution | exact task、run／parent ID、aware started/completed、terminal receipt 外部 SHA、code version、exit code；latest 僅是 locator |
| Consumer | consumer 名稱／版本、同 run/date/artifact 的唯讀讀回、warnings／reject reason；上游 passed 不推導 consumer accepted |
| Qualification | Engineering、Natural Scheduled Execution、Source Qualification、Data Coverage、PIT Validity、Consumer Readiness、External Dependencies 分列；每用途獨立判定 |

Root 新增的修訂 custody profile 只處理三份精確修訂 run 的舊資料庫身份、兩份市場來源與16份錯日排除來源定位。它固定原 hash 鏈與新唯讀保護狀態，**不是這些原件逐檔搬遷 SHA 通過的證據**。原修訂、來源取得時間、禁止歷史 PIT 及訓練資格不變；新 rollback、未知 marker、替換 DB、原 D 資料重現或 hash 漂移均重新拒絕。

## Track C：ML Data Readiness

資料集 manifest 應引用共通身份與資格，另明示 feature／label 名稱、資料期間、symbol universe、train／validation／test／OOS 分界、每筆決策 cutoff、feature available_at、label planned maturity／actual observation 及 purge／embargo 政策。沒有實際 manifest 與 consumer 讀回時，本文件只是交付要求，不是已交付可訓練資料集。

1. Feature 只取 `available_at <= decision_cutoff` 的版本；歷史值、current-observed、prospective-capture 與歷史 PIT 分開。月營收取得歷史數值不證明當年可得時間。
2. 改寫後的來源必須帶 revision lineage；目前表重算、重抓與 late correction 不回填過去 OOS 特徵。PIT 盤前 archive 依既有 Asia/Taipei 08:30 cutoff 與真實 capture completion 判定，盤後不可補抓冒充盤前。
3. 尚未成熟的 Forward label 為 null，附官方日曆的 planned maturity 與缺價理由；不得使用 row offset、近價或平盤補值。成熟標籤仍須具名價源版本／custody 與 source availability。
4. Raw PIT 上游 blocked、rule-only Copilot、candidate／shadow 或 Promotion evidence 的局部狀態不授 training／validation／OOS／promotion。Track B 不替 Track C 啟動大規模重訓。

2026-10-22 可交付的是原收據／現況與限定研究資料身份；Raw PIT 的當日來源階段未啟動，Formal compatible count=0，當日 cutoff 前 PIT capture 缺件。Forward 自然 run 有 172 筆 outcome 更新，但仍有缺價、未成熟與來源 lineage 限制，不是完整可訓練資料集。月營收 1,975 筆 YoY 的限定研究使用不能外推為正式 ML／歷史 PIT 資格。

## Track A：唯讀研究展示

透過既有 read model／DTO 與 provider port 讀取，保持 `mode=ro`／`query_only`、固定 artifact 身份及明確 source/data/decision 日期；不要求 UI 直接解析正式 DB、原始 receipt 或私人 binding。新增 UI 欄位沿 typed interface 另行接線，Track B 不修改 UI。

展示至少保留 source identity/version、資料截止日、available_at 依據、品質、coverage、各用途資格及拒絕原因。`current`／`stale`／`unknown`、`candidate`／`research_only`／`formal_qualified` 分別顯示；不可由 Task result=0 或資料檔存在變成「今日正式可用」。

月營收目前可展示具名雙市場原值、百分率／YoY與原 unknown；未有外部固定 unit proof 時不標 TWD、不推定千元或乘 1000。Paper 的舊 cash／mark、研究 sizing 或 500,000 TWD 契約數字不可展示成真帳戶當日資金。Forward 的未成熟欄位保持 null 及目標日，不宣稱績效或交易權限。

讀回不得寫行情 DB、來源檔、Ledger 或正式控制路徑；Research Run、使用者筆記的既有保存能力依原本獨立契約。金融 source gate 失敗可展示原因，不把一條線缺件擴成其他獨立研究資料的全域禁止。
