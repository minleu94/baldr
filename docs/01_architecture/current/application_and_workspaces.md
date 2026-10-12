# UI 與應用流程

本冊描述目前 PySide6 UI 與 application layer 的責任。系統全貌見[目前系統架構](../system_architecture.md)，操作步驟與畫面判讀見[Application Manual](../../07_guides/APPLICATION_MANUAL.md)。工作包完成度仍以 Snapshot 與具名 QA 收據為準。

## 入口與分層

```text
使用者
  → ui_qt/main.py（視窗、工作區、表單與呈現）
  → app_module/（use case、service composition、DTO、repository）
  → decision_module/、backtest_module/、portfolio_module/、analysis_module/
  → data_module/（來源、reader、writer 與市場資料保存）
```

Windows 由 `baldr_launcher.py` 啟動；source 與 frozen 執行都交給既有 Qt composition。`ui_qt/main.py` 建立視窗與 widget，`app_module/` 的 composition factory 建立服務並以 DTO／明示 provider 注入 UI。Domain 與 Runtime 不反向依賴 Qt。

## 九個頂層工作區

1. 決策工作台
2. 市場探索
3. 推薦分析
4. 策略回測／Research Lab
5. 觀察清單
6. 個股研究
7. 持倉管理
8. 數據更新
9. Runtime Observatory

Daily Decision Desk 沒有第二個頂層 widget；它位於「市場探索 > 市場總覽」，決策工作台的「決策來源」只導向同一個畫面。`StockResearchWorkspace` 是主視窗中的單一工作區，會以明示的研究 context 在報告、結果與來源之間導覽。

<a id="daily-decision-desk"></a>
<a id="4-daily-decision-desk"></a>
## 工作區責任

| 層 | 主要責任 | 不負責 |
|---|---|---|
| `ui_qt/` | 收集參數、送出 application 請求、顯示 DTO／圖表／狀態、工作區導航及 worker lifecycle | 評分、策略、撮合、資料資格判斷與直接維護正式資料 |
| `app_module/` | 組合 use case、選擇來源、整理 DTO、管理保存流程與服務協調 | 持有 UI 狀態或複製領域計算 |
| `ui_qt/workers/` | 在背景執行長任務，回報進度及結果；透過取消與請求世代拒收過期結果 | 成為資料或決策權威 |

View 只把已驗證的 application 結果投影到畫面。來源、時間、狀態不明時保留 unknown／degraded；呈現層不補值、不把研究訊號升級為正式 Advice。

## 主要資料流

### 更新市場資料

```text
數據更新工作區
  → UpdateService／來源更新服務
  → TWSE、TPEX 或其他明示來源
  → raw CSV／市場 SQLite sync
  → 技術指標 job（由父程序單一 writer 發布）
  → 更新結果 DTO 與來源品質提示
```

更新步驟與錯誤處理由 `app_module/` 的服務與 `ui_qt/views/update/` coordinator 分工；UI 收集日期、來源與選項，不能繞過明示 write path。狀態與詳情查詢保持唯讀，SQLite 不存在或不可讀時顯示 diagnostics。

### 市場觀察與推薦

```text
既有 market frame／來源 observations
  → application composition 與 RecommendationService／ScreeningService
  → decision_module 的 regime、screening、scoring 與 reasons
  → recommendation／Decision Desk DTO
  → 市場探索、推薦分析與 Workbench 呈現
```

服務先依決策日、資料可得日與來源資格界定輸入，再執行計算。Recommendation 結果保存來源、設定、母體與負面證據 metadata；畫面、報告與重開都讀取已產生或已保存的 DTO，不在 UI 重新評分。

### 研究與持倉

回測、批次、最佳化、Walk-forward 與推薦組合回放由 application service 協調 `backtest_module/` 與既有策略；UI 呈現結果或提交保存請求。持倉管理把手動帳務、使用者聲明研究持倉與 paper research lane 分開；名稱相似不代表來源身份可互換。見[決策、研究與 Portfolio 分冊](decision_research_portfolio.md)。

## 研究畫面與保存身份

市場研究畫面消費具來源版本、日期、母體、方法與 hash 的 snapshot／manifest。Daily Research、候選摘要、研究書籤與跨頁投影沿同一已核驗來源和 query；readback 按保存的 source identity 重開，不搜尋 latest、不在 UI 重算指標或重新執行 producer。來源缺件、修訂、方法不相容或日期不可判定時保留 unknown／拒絕，不能套用舊投影或改讀一般即時行情。

原生個股排名是獨立研究來源，須以已驗證的 feature snapshot 與明示母體作 parent。原排名發布者、reader、每日研究 consumer 與 pinned 個股 context 保留同一 manifest／artifact 身份；版本化收藏保存方法、比較窗、母體、排序與所選股票。舊 v1 收藏維持原 bytes／identity 語意，rank context 走明示 v2。另開 latest 個股研究是不同路由，不改寫原收藏；收藏也不造新的 Recommendation `result_id` 或持倉 ledger。

保存母體的多 artifact reader 只有在呼叫端明確 opt-in、且原 TaskWorker 能發行綁定原 worker／取消 event／callback／執行緒的一次性能力時，才可使用合作式取消 probe。能力 claim 只可成功一次；callback、執行緒或封印不符時不提供 probe，該次 claim 已消耗並退回序列讀取。只有明確支援此能力的 task 可取得它；取消 callback 存在但 reader 沒有該能力時不得平行讀取。合格讀取最多保留 8 個未完成 future，結果與回呼依原 artifact index 順序消費。取消或錯誤時停止提交後續工作，並等待已啟動讀取自然收尾；不強制終止 worker／future，也不把取消當成 rollback。

固定篩選 preset 和 multi-method summary 是唯讀投影，只讀已發布候選與完整 declared denominator，不新增資料來源、打分方法或正式資格。現行條件若來自同一方法家族，不按不同均線數量冒充獨立證據家族；跨來源／跨方法資料不足時留 unknown。使用者確認後才可把來源和 query 存入既有收藏；單純套用 preset 不改變收藏的方法身份。

保存的 Recommendation 圖表使用原次 request 的 prepared market frame、選中範圍與同次指標，不讀最新行情、不補算缺失均線。Stock Research 的切股、返回及 viewport 投影都要先核 source/context/generation identity；來源變更或過期 worker 回應不能覆蓋目前選取。共用狀態顯示 helper 只翻譯已知狀態，未知值保留原碼與明細，不改 DTO/domain 資格。

## 邊界與導覽

- QWidget 不直接查詢 Runtime store；Runtime Observatory 顯示透過 application／Runtime DTO 注入的狀態。
- 保存後重新開啟結果時，應按保存 identity、版本與 source pins 讀回，不隱式改讀最新資料。
- 產品操作與安全限制以 Manual 為準；架構契約不代表按鈕已開啟、資料來源已接受或 Gate 已通過。
- 舊相容錨點 `system_architecture.md#4-daily-decision-desk` 仍由目前架構首頁導向本節。
