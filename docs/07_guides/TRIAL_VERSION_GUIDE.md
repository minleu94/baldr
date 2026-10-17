# 目前指定的本機日常研究入口

**目前指定日常研究116，固定來源 `1cf80e32b4c2`。** 雙擊 [Launch-Baldr.cmd](../../output/trial/Baldr-Daily-Research-116/Launch-Baldr.cmd) 開啟；先看包內[操作指南](../../output/trial/Baldr-Daily-Research-116/TRIAL_GUIDE.md)及[已知問題](../../output/trial/Baldr-Daily-Research-116/KNOWN_ISSUES.md)。完整SHA、來源、EXE與定向QA由[交付收據](../../output/trial/Baldr-Daily-Research-116/DELIVERY_RECEIPT.json)固定，工程證據見[116固定交付QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment116-fixed-trial-delivery)。一般操作看[完整手冊](APPLICATION_MANUAL.md)，目前狀態看[Snapshot](../00_core/PROJECT_SNAPSHOT.md)。

## 可以試什麼

| 主要任務 | 入口與資料範圍 |
|---|---|
| 看市場、查個股 | 市場探索／個股研究；一般個股只含2317、2330、2382、2454，截至2026-09-23。 |
| 價格選股、比較、收藏 | 推薦分析 → 每日研究條件 → 價格研究；明選2026-10-16的1,989宣告／1,951處理來源。指南提供兩股及MA金叉39檔的操作。 |
| 觀察清單與持倉回訪 | 同來源收藏可重開；持倉位於四卡下方，唯一精確代號／名稱可互補，未綁來源部位可回一般個股重載。 |
| 單股回測、保存與重開 | 策略回測；保存原run，從歷史核原條件／規則、開明細並返回。窄視窗以「查看實驗結果」／「編輯回測設定」切換，結果可捲動。 |

四條第一版範圍維持原計畫。116納入批次比較、啟動修正與保存精度修復：來源Main完成四筆執行／保存，固定EXE另驗高精度新保存、原四筆歷史／規則／返回及另一程序讀回，並核實際可視區的拒比原因。未改的單股雙策略旅程沿用112證據，價格／收藏及舊推薦沿相應既有證據；沒有在116重跑全部四旅程，真人／不同DPI仍待。

第二階段可試批次逐股原結果回訪、舊推薦1528的逐期品質限制，步驟集中在包內指南。批次一般績效比較會明示不可直接比較；缺來源、幣別、成本與歷史PIT資格時不並列績效與標準化權益。單股對照仍是原保存研究值，不代表策略有效性接受。

## 版本與保存

116已納入保存精度修復；有限Decimal欄可精確保存／重開，原float DTO維持原型別，不補造已失精度。舊CSV及SQLite摘要不遷移；步驟及限制見[保存格式說明](manuals/RECOMMENDATION_AND_RESEARCH_LAB.md#舊回測保存格式與精度)。

116使用自己的 `state/`，18份固定輸入由109核SHA另複製；不自動匯入其他版的收藏、持倉、回測或私人帳。115、112、109、71、66及更早包與原收據保留，各版回報只歸屬該版。原66指南D的個股入口勘誤及六配對run尚未定位的限制，不能用新版測試覆蓋。

保留本包、`dist/candidate_1cf80e32b4c2_feef21b1/baldr`及`output/rc101/research_snapshots/technical-store`的位置；尚非跨機可攜安裝驗收。啟動器先核EXE，`--check`只查版本而不開主視窗；後續程式碼不會更新固定EXE。

## 金融與資料限制

當期1,951檔來源只服務價格研究，與四股一般價庫分開；5筆價格UNKNOWN、38檔缺價排除及舊列缺漲跌方向維持原狀。名錄用途與來源clock仍未接受，無歷史PIT或正式真N資格。財報缺幣別／期間／用途或前期時，相關指標保持不可用。

Paper外部帳本未配置；不以手動持倉造現金、NAV或Health。SOP／Baseline FAIL、未做Walk-forward、晉升禁止、未成熟期限及自然排程限制各自保留。程式碼、EXE或局部QA不授來源權威、有效績效、真人接受、跨機安裝或完整G0–G4；本機試用不修改正式資料或正式Task，也不執行交易。

<a id="入口與資料範圍"></a>
<a id="increment71開發來源修正尚未替換試用包"></a>
<a id="increment71-開發來源修正尚未替換試用包"></a>

舊錨點保留供原連結導覽；71歷史與當時未打包項目回[原QA](../06_qa/BALDR_DATA_POLICY_IMPLEMENTATION_20261014.md#increment71真人試用回報的四流程可用性修正)核對，不作目前版本入口。
