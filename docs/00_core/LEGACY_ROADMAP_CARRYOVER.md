# 舊 Roadmap 移交矩陣

> **原始移交日期**：2026-06-15
> **最後整理**：2026-10-08（僅補歷史 Gate 與現行路線界線）
> **定位**：本文件是舊 Roadmap 未完成事項的結案與移交證據。它不新增平行 Roadmap，而是確保每個舊項目都有唯一處置。
> **現行路線**：第 2–4 節出現的 Month 1–3 標籤都指 2026-06-15 當時的新版 Roadmap 移交安排，不對應目前 6M Roadmap 的相對月份或目前進度；目前工程順序看 [6M Engineering Roadmap](ROADMAP_6M_ENGINEERING.md)，目前狀態看 [PROJECT_SNAPSHOT](PROJECT_SNAPSHOT.md)。

## 1. 判讀規則

每個舊項目只能有下列一種處置：

- **已完成**：功能與必要機制已存在；若仍需實證，實證另列為獨立項目。
- **移交**：新版 6M Roadmap 有明確月份、交付物與驗收標準。
- **被取代**：舊解法已被更完整的新架構取代，並指出替代方案。
- **正式取消**：記錄不做的原因與影響。

禁止使用「之後再做」、「持續改善」或沒有月份與驗收標準的模糊狀態。

## 2. 舊 Roadmap 未勾選項目

| Legacy 項目 | 處置 | 新版落點 | 完成或驗收定義 |
|---|---|---|---|
| 指標參數改進（RSI/MACD/KD/ADX/MA/ATR/BBANDS） | 已完成 | Month 2「參數與權重治理」 | Indicator Parameter Registry、版本化欄位與 Research Run 快照的歷史交付見 [Month 2 Registry 治理計畫](../09_archive/superpowers/plans/2026-06-14-month-2-parameter-run-storage-governance.md)。 |
| buy_score / sell_score 改為分位數 | 已完成 | - | fixed / quantile 雙模式與 2026-06-14 十檔 OOS pilot 的數據、Gate 及限制見 [Walk-forward 比較報告](../06_qa/WALK_FORWARD_COMPARISON_REPORT.md)；結果不代表全市場或 quantile 優於 fixed。 |
| 推薦系統參數改進 | 已完成 | Month 2「參數與權重治理」 | Recommendation Weight Contract 與參數保存的歷史交付見 [Month 2 Registry 治理計畫](../09_archive/superpowers/plans/2026-06-14-month-2-parameter-run-storage-governance.md)。 |
| 完整測試與穩定性驗證 | 已完成 | Month 2 Registry | 2026-06-14 範圍內完成十檔 OOS pilot、Unified Research Run Registry、hash integrity、crash reconciliation、UI 保存／比較與 promotion gate；分項結果及驗證邊界見 [Walk-forward 比較報告](../06_qa/WALK_FORWARD_COMPARISON_REPORT.md)與 [Month 2 Registry 治理計畫](../09_archive/superpowers/plans/2026-06-14-month-2-parameter-run-storage-governance.md)，不是目前全 App 的完整驗收聲明。 |
| 大表格分頁 | 已完成（歷史實作） | Month 1「Phase 5 最小可用輸出」 | SQLite Inspector 分頁實作記於 [V1 完成紀錄](../09_archive/ROADMAP_6M_ENGINEERING_V1_COMPLETION_RECORD_2026_07.md)；Full App Healthcheck 將 U-024 列為通過，但註明近期 compact pagination 有回歸風險、需維持 direct bridge，見 [Coverage Mapping](../06_qa/FULL_APP_HEALTHCHECK_COVERAGE_MAPPING_2026_06_24.md)。這不單獨宣稱目前 UI 無回歸。 |
| 匯出研究報告（Excel / PDF） | 部分完成 | Month 1「Phase 5 最小可用輸出」；PDF 移交研究輸出 backlog | Excel 報告格式化、追溯 metadata、TaskWorker 與原子寫入的歷史交付見 [V1 完成紀錄](../09_archive/ROADMAP_6M_ENGINEERING_V1_COMPLETION_RECORD_2026_07.md)。Full App Healthcheck 將 B-037／R-019 匯出仍列為 candidate、B-040 批次結果的匯出仍是 candidate，故這些工程交付不代表所有 UI 匯出流程已正式驗收，見 [Coverage Mapping](../06_qa/FULL_APP_HEALTHCHECK_COVERAGE_MAPPING_2026_06_24.md)。PDF 尚未完成；後續規格與限制如原列。 |
| 回測結果摘要模板 | 已完成（歷史實作） | Month 1「Phase 5 最小可用輸出」 | Excel 報告中的 metadata 與資料完整性區域見 [V1 完成紀錄](../09_archive/ROADMAP_6M_ENGINEERING_V1_COMPLETION_RECORD_2026_07.md)；UI 匯出驗收仍應依 [Coverage Mapping](../06_qa/FULL_APP_HEALTHCHECK_COVERAGE_MAPPING_2026_06_24.md) 的 candidate 範圍判讀。 |

## 3. 舊 Roadmap current section 的後續工作

| Legacy 後續工作 | 處置 | 新版落點 | 驗收定義 |
|---|---|---|---|
| fixed / quantile 真實 walk-forward 比較 | 已完成（10 檔 OOS pilot） | - | 同股票池與成本。2026-06-14 以 fixed 55/45 完成 10 檔、單一策略與固定成本組合、每檔 8 個 OOS fold；fixed 57 筆、quantile 79 筆交易皆通過 20 筆最低樣本 Gate，並完成 100% Regime coverage 的分層歸因。此結果只證明該 pilot 範圍，不代表更大真實股票池或全市場 Gate 已通過。 |
| 推薦組合跨 run 比較 | 已完成 | Month 2 | Research Lab 比較子頁支援 2-5 個 registry run，比較 OOS 指標、參數差異、Regime、benchmark 與正規化 equity；incompatible run 不產生優劣排名。 |
| Benchmark-relative attribution | 已完成 | Month 2 | Cross-run comparison 只使用 run 已保存的 benchmark results，顯示 benchmark-relative attribution，不於比較時重新抓取目前資料。 |
| Factor / failure attribution | 移交 | Month 3 與 Month 6 | Month 3 先完成更多 Research Lab 路徑的 factor contribution 與 Portfolio Replay 可信度；Month 6 再完成 Portfolio post-trade attribution，區分訊號、執行、資料與市場落差。 |
| 自動參數建議 | 被取代 | Month 2 Cross-run + Month 6 策略生命週期 | 不直接做黑箱自動調參；先用可追溯 run 比較與 rule-based promote/demote/retire。 |
| 清理過期 `app_module/README.md`、`ui_qt/README.md` | 已納入本次文件重構 | 2026-06-13 Documentation Patch Pass | README 必須反映 `ui_qt` 主入口、目前 service 邊界與已完成 Phase。 |

## 4. Carryover Gate（2026-06-15 歷史交接條件）

> 以下 Month 1–3 語彙只描述舊 Roadmap 移交當時的 Gate，不代表目前 6M Roadmap 的 Gate 狀態或執行順序。

當時交接基線中的新版 Roadmap 可執行 Month 1 與 Month 2，但 **Month 3 Factor Layer 不得在下列項目仍無正式結果時宣告開始**：

1. fixed / quantile 的 10 檔、單一策略與固定成本 walk-forward pilot Gate 已通過；報告保留 quantile 未優於 fixed 的結果，且 quantile 維持 opt-in。此歷史結案不推定更大真實股票池或全市場已驗收。
2. Phase 5 最小可用輸出已有實作結果，不只是設計稿。
3. Indicator Parameter Registry 與 Recommendation Weight Contract 已完成。
4. Research Run Registry 能保存資料、策略、參數、成本與成交假設，並支援比較、hash integrity、archive/promote guard 與 registry-based promote gate。
5. 本矩陣每個項目都有完成證據、移交狀態或正式決策記錄。

這個 Gate 防止舊 Roadmap 尚未結案時，直接用新資料源或新 Factor 擴張系統。

## 5. 結案判定

- 舊 Roadmap 文件維持 Archive，不再回寫新進度。
- 新進度只更新 `PROJECT_SNAPSHOT.md`、`ROADMAP_6M_ENGINEERING.md` 與對應專題文件。
- 當本矩陣所有「移交」項目完成後，保留本文件作為歷史交接證據，不刪除。

## 6. 更新記錄

- 2026-06-15：對齊 baldr 願景與新版 6M Roadmap，明確 PDF 屬研究輸出 backlog，不阻塞 Month 3 / Month 4；Factor / failure attribution 拆為 Month 3 factor contribution / Portfolio Replay 可信度與 Month 6 post-trade attribution。
