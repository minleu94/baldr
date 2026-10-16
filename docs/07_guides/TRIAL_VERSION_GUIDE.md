# 目前指定的本機日常研究入口

目前狀態以 [PROJECT_SNAPSHOT](../00_core/PROJECT_SNAPSHOT.md) 為準。截至 2026-10-15 最新另交的固定本機候選為 **日常研究71（`f9b4e7d12149`）**，從 `output/trial/Baldr-Daily-Research-71/Launch-Baldr.cmd` 啟動。先看同目錄的 [TRIAL_GUIDE.md](../../output/trial/Baldr-Daily-Research-71/TRIAL_GUIDE.md)、[KNOWN_ISSUES.md](../../output/trial/Baldr-Daily-Research-71/KNOWN_ISSUES.md)；版本、來源、EXE 路徑與完整 SHA 在 [DELIVERY_RECEIPT.json](../../output/trial/Baldr-Daily-Research-71/DELIVERY_RECEIPT.json)。一般操作見[完整手冊](APPLICATION_MANUAL.md)。本頁提供入口，不取代 Snapshot 或原交付收據。

<a id="入口與資料範圍"></a>

## 版本與資料範圍

| 版本 | 入口與適用範圍 |
|---|---|
| 日常研究71／固定 `f9b4e7d12149` | 上述新獨立候選；包含 Increment71 試用回報修正，限定 EXE／fresh 工程驗證見原 QA456／458。新版真人手勢、真私人帳及完整 Gate 仍待。 |
| 日常研究66／固定 `ec5c95733608` | 原 `output/trial/Baldr-Daily-Research-66/Launch-Baldr.cmd` 與其狀態保留；原真人回報與限制仍屬這版，不能用71測試改寫。 |
| `9fa`、`4b530`、`0f644faa` | 歷史原包與各自原收據保留；版本相同才套用其操作與驗收。 |

啟動器先核對收據所列 EXE；後續開發程式碼不會自動更新固定包。保留完整候選目錄及啟動檔所指向的 `dist/candidate_f9b4e7d12149_d5e4efe4/baldr`，不要只複製 EXE。這是本機候選，技術母體仍唯讀依賴已核驗的本機封存絕對路徑；不是可攜版或移機驗收。

71 的行情、收藏、回測與本機輸出放在獨立 `state/`，不接續舊試用或正式帳本；Paper root 在本試用啟動檔停用。只有2317、2330、2382、2454四股，價格截至2026-09-23，大盤截至2026-10-14；不是即時或全市場行情。977列沒有明確價格方向，保留未知，不用相鄰收盤價推算。逐筆來源及缺值見包內已知問題與[價格方向收據](../../output/trial/Baldr-Daily-Research-71/PRICE_DIRECTION_RECEIPT.json)。

## 日常操作入口

1. 從71目錄的 `Launch-Baldr.cmd` 啟動，確認同目錄已知問題；新狀態沒有匯入你的舊持倉、收藏、回測或Paper帳戶。
2. 在「推薦分析 → 每日研究條件 → 價格選股」查版本，明選同一保存批次並嚴格核驗。`已處理4/4` 是來源分母，另看目前符合幾檔；來源日期、缺件與符合數分開判讀。
3. 只見一列時，可按「顯示此來源全部股票」清除本頁代碼、價格、技術及未知值篩選，重查同一已核來源。修改條件再按套用，不猜換來源或改用每日快照。只有原來源確實有兩檔，才能逐檔加入同源比較籃並重驗比較；單列亦可收藏。
4. 雙擊價格列開啟「原價格條件研究」獨立視窗；沿原返回入口回到來源。需要一般個股報告時，從左側「個股研究」明選代碼載入。舊66指南 D 的主個股頁描述錯誤仍是歷史勘誤，不沿用為71步驟。
5. 手動交易只在本機名冊唯一且完全相符時互補代號／名稱，歧義或矛盾不猜配。未連結保存研究的持倉下鑽讀目前一般個股 scope；已連結者仍核原保存來源。固定 EXE 已驗表格訊號至價量重載，真滑鼠雙擊與真帳效果待真人回報。
6. 單股回測的設定與結果按視窗寬度排列；三個選用查找預設收起、一次展開一個，摘要可在自身捲動。保存／歷史／返回核同一 run，完成配對、成交、明細列數與期末持股分開；使用者原六配對 run 尚未取得身份，不能用隔離結果代替。
7. 保存或讀回失敗時保留原 run／result ID、日期、來源與錯誤，不改 hash 或以最新檔替原件。來源回訪核同一版本，不等於重新取得最新行情。

<a id="increment71開發來源修正尚未替換試用包"></a>
<a id="increment71-開發來源修正尚未替換試用包"></a>

## Increment71 固定候選與後續來源修正

Increment71 已從開發修正形成上述獨立71候選。原 QA447–455 的建置／沙箱／工具失敗保留；後續 QA456 的同版 EXE／fresh 限定旅程及 QA458 的啟動器檢查另有原收據，不能只讀較早「尚未有本 Increment Native／EXE」的段落。完整過程與適用範圍見 [Increment71 QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment71真人試用回報的四流程可用性修正)。原66不被覆寫，兩版不共用個人狀態。

後續 [Increment72 舊歷史缺件與空交易表判讀](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment72舊回測歷史缺件與空交易表的金融判讀)只在開發來源，**未納入固定71 EXE**。它區分缺值與真零、明細缺件與零交易，仍未以使用者原六配對 run 重現；來源版測試不代表新包或真人接受。本指南只記固定71的交付內容與限制。

## 金融與研究安全界線

baldr 提供研究與持倉檢視，沒有自動券商交易；畫面不是委託、投資建議或收益保證。缺件、unknown、stale、partial、零筆與失敗分開，不補零、不拼接不同來源／日期，不把回測、Advice、Paper、投影、測試或排程狀態當實際績效。

本候選未授歷史PIT、完整市場／來源資格、可排名的完整策略績效、真N、Paper／Forward自然成熟、跨機安裝或完整 Gate。原 SOP／Baseline FAIL、Walk-forward未做及晉升禁止依原收據保留。私人帳本與正式資料由owner管理，不把試用狀態寫回正式資料根；可攜版與安裝看[Windows指南](PORTABLE_WINDOWS.md)。
