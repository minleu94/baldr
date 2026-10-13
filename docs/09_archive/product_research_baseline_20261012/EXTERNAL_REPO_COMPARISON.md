# 七個外部專案與 baldr 的初步比較

> 2026-10-12 研究的歸檔閱讀版。下文的現況、執行與未執行描述固定於原研究時點；本次只整理導航與保存，不重跑研究或改變原結論。來源 SHA／修訂範圍見 [清冊](ARCHIVE_MANIFEST.json)，後續沿用方式見 [基線入口](README.md)。

研究日期：2026-10-12。各 repo 查詢時的 HEAD、README blob 與本機副本範圍保存在 [SOURCE_BASELINES.json](SOURCE_BASELINES.json)。本頁是技術選型研究紀錄，不變更產品方向、工程 Gate、架構或來源接受資格。

判斷：優先深入 Qlib 的研究流程，以及 daily_stock_analysis 的每日產品旅程；OpenBB 適合參考資料接口，vn.py 適合參考桌面模組與事件架構，Vibe-Trading 適合限縮參考工具化研究與可追溯產物。兩個 ML 教材庫適合做算法候選與教育材料。此優先序是依 baldr 目標作出的建議，不是預測準確度、收益或原碼品質排行榜。

## 個別優點與適用範圍

| 專案 | 已讀來源支持的優點 | 對 baldr 的參考方式 | 邊界 |
|---|---|---|---|
| [Stock-Prediction-Models](https://github.com/huseinzol05/Stock-Prediction-Models) | 多種時序模型、stacking、agent 和 Monte Carlo Notebook，容易對照不同方法。 | 建立研究候選清單，整理單一可重現教材／模型比較樣例。 | 2023-07-27 已封存，查詢時 HEAD 在 2021；主要是實驗範例，依賴、資料切分和績效定義需另核。 |
| [Qlib](https://github.com/microsoft/qlib) | Dataset、Model、Strategy、Evaluation、Recorder 解耦；配置化 workflow、明示 train/valid/test 與 fit window、多模型 benchmark、市場動態研究。 | 在既有 Research Run／ML Registry 上保存同一資料版本、split、設定、成本、benchmark 與完整結果，公平比較 baseline/challenger。 | 需適配台股資料、交易日、費用與訊號／成交時間；範例參數不能直接當台股契約。主分支與正式套件版本也需分清。 |
| [vn.py / VeighNa](https://github.com/vnpy/vnpy) | 事件引擎、gateway/app/datafeed/database 模組化、Qt 桌面工具；現有 vnpy.alpha 提供因子、Lasso/LightGBM/MLP、策略與 Lab 流程。 | 參考 UI 和服務的事件／模組邊界，以及以一致接口切換簡單 ML 模型；選讀 Alpha Lab。 | 自動交易和券商接線超出 baldr 目前範圍；平台 API、生態與資料服務不直接代替我們的台股領域。 |
| [Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | 自然語言研究、skills/tool registry、研究任務進度、trace/run card、保存報告、交易日誌／shadow 比較和因子工具。 | AI 從已保存證據查詢、整理成可檢查研究產物；對照交易日誌行為診斷、任務恢復與明示工具責任。 | Agent/工具數量是維護成本；其交易能力不能隨研究接口帶入 baldr。README 功能敘述未經本次 runtime 驗證。 |
| [OpenBB](https://github.com/openbq-org/OpenBB) | 同一資料接口供 Python、API、MCP 等使用；Fetcher 分查詢轉換、資料取得、結果轉換，提供型別契約。 | 補強 provider capability registry、來源欄位映射、單位與缺件語意；讓 UI、研究與 AI 讀取同一契約。 | 公開 repo 主要是資料平台；Workspace 是另一個 UI 產品。接入更多 provider 不代表資料時間可得性或正式來源資格已成立。 |
| [daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) | 自選股→資料／新聞→分析報告→推送的明確旅程；Web/桌面工作台、歷史、設定、任務狀態與快速部署說明。 | 非開發者的首頁、今日摘要、下一步、風險與歷史回訪；借鑑報告與來源品質摘要。 | LLM 綜合分數與分析文字需維持輔助定位；採用操作流程不等於採用其分數作 formal evidence。 |
| [Deep_Learning_Machine_Learning_Stock](https://github.com/LastAncientOne/Deep_Learning_Machine_Learning_Stock) | Notebook 對資料清理、特徵選擇、PCA、統計、樣本內外、回歸與分類提供較多入門材料。 | 補研究 onboarding、特徵 sanity check 和簡單 baseline 的解釋材料。 | 根目錄和 README 以教材為主，尚未在本次閱讀中建立其作為整套產品／研究治理框架的證據。 |

## 核心實作來源

- Qlib：[workflow 定義](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/docs/component/workflow.rst)將模型、資料、record、fit 範圍與 train/valid/test 範圍放入同一設定；[TRA](https://github.com/microsoft/qlib/blob/54355232463878d2eebb91fe0ee5fa7fa1f5976c/examples/benchmarks/TRA/README.md)研究多種股票交易模式及路由，附具名基線與評估。
- OpenBB：[Fetcher](https://github.com/openbq-org/OpenBB/blob/7c9d4221bdf66965e3f6c7f4dc6ee848073e5ae2/openbb_platform/core/openbb_core/provider/abstract/fetcher.py)有 transform_query、extract_data、transform_data 等接口；這是資料邊界參考，不是來源品質或金融正確性保證。
- Vibe-Trading：[Regime 原碼](https://github.com/HKUDS/Vibe-Trading/blob/c25fea2bc261a2d0ed971c989d194de9f04ec963/agent/backtest/regime.py)以 rolling pairwise correlation 的 edge density、尾隨平滑及進出雙門檻判斷 FUSED；此實作屬統計／規則 state machine，沒有 ML fit，輸出被定位為描述性風險 context。
- 本機 DSA：`src/schemas/analysis_context_pack.py:38` 的狀態分 available、missing、not_supported、fallback、stale、estimated、partial、fetch_failed；field/block 保存 source、timestamp、warning 等，pipeline 產生低敏 overview。可借鑑將現有品質 metadata 轉成使用者可理解的報告，避免另建品質真源。

## 如果重點是 Regime／ML

優先看 Qlib 的市場分布變化研究、rolling baseline 與 TRA，比較方法如何適應不同模式。TRA 的 latent pattern／model routing 不等於帶固定經濟語意的多頭／空頭標籤，不能直接映射到 baldr 的 Trend／Reversion／Breakout。

Vibe 的 correlation regime 提供另一個可解釋維度：資產是否變得高度同步，可作 portfolio 共振風險／市場診斷的候選參考。它與趨勢／盤整分類不同，也不因由 Agent 呼叫而成為 ML。採用前仍需核 universe、資料可得時點、缺件、參數穩定性和我們已有相關功能。

先固定問題、label 語意與時間契約，再在同一凍結資料及 purged walk-forward 下比較現行規則、簡單 ML 與較複雜模型。股票預測示例圖、模型數量、Agent 數量或 repo 星數都不能代替這個比較。

## 本機 daily_stock_analysis 與上游差異

本機 HEAD 可讀為 `ecf87ea0107f1394c7e7f2c0e21362a70c0244d1`（2026-06-24），已讀 `docs/README_CHT.md`、context schema、pipeline 與 analyzer 的相關片段。這是本機工作樹的閱讀結果，不能將 HEAD 當成所有本機繁體化改動的版本證明；本次受限環境沒有成功取得工作樹 clean/dirty 狀態。

目前上游 [市場支援文件](https://github.com/ZhuLinsen/daily_stock_analysis/blob/c3349de46965a12d6b74ce8489eba0e39e03ba44/docs/market-support.md#台湾个股支持suffix-onlyissue-1772--1777)已列 `.TW`／`.TWO` 的台股個股路徑、YFinance 行情與三大法人報告；完整台股股票池／自動補全、市場寬度、大盤復盤和完整 TWD Portfolio 估值仍有邊界。此為文件宣告，本次沒有逐一實測外部 API 或台股全流程。

因此後續若深入此 repo，先比較本機繁體化／功能改動與上游增量，再規劃選擇性更新；不直接 pull 覆蓋使用者成果。本次沒有 fetch/pull 或修改本機 DSA。

## 對 baldr 的建議順序

1. 產品旅程：以 DSA 對照目前九個工作區，把「今日要看什麼→為什麼→風險與缺件→保存／回訪」做成能找到入口的流程。README 保持定位、核心能力與快速開始；詳細操作、契約與歷史各自有清楚入口。
2. 研究重現性：以 Qlib 對照既有 Research Run、Dataset／Model Registry 和 shadow 契約，定位真正缺件；研究設定、基線、樣本、split、指標、失敗與產物相互關聯。
3. 資料接口：以 OpenBB 的 provider 邊界對照現有 source registry，補單位、schema、品質與 capability 的一致投影；來源日期、PIT、missing 不依 UI 或 LLM 重新推測。
4. 模組與 UI：選讀 vn.py 的事件／plugin 邊界、Alpha Lab；不因借鑑而重寫整套 UI 或加入 broker execution。
5. AI 研究接口：選讀 Vibe 的技能／工具路由、trace、run card、交易日誌與資料風險呈現，維持 read-only evidence 與可審核責任。
6. 教材／模型庫：其餘兩個 Notebook repo 留在研究清單，挑特定範例驗證，不作正式架構或產品 Gate 依據。

Qlib、vn.py、OpenBB 已在 baldr `EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md` 有具名參考定位；本次研究只補更具體的選讀方向，不自行改寫採用分級或 Roadmap。baldr 的現況、架構與產品邊界仍依 `PROJECT_SNAPSHOT.md`、`docs/01_architecture/current/decision_research_portfolio.md`、Product Roadmap 與工程 Gate。

## 驗證範圍

已執行公開 repo／README／指定來源閱讀、HEAD metadata 查詢、本機 DSA 檔案唯讀閱讀及 baldr 圖索引／契約對照。本次沒有 clone 七個 repo、安裝依賴、import 外部程式、執行單元測試、資料下載、回測或收益比較，也沒有更新任何產品程式、產品權威文件、正式資料或排程。新產物僅為 ignored 任務紀錄、比較頁、來源 metadata 與 Graphify 查詢記憶。純查詢不需要修改 Application Manual 或產品 SSOT。
