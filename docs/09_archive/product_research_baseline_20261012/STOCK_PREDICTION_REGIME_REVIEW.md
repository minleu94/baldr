# stock_prediction：Regime ML 初步研究審查

> 2026-10-12 研究的歸檔閱讀版。下文的現況、執行與未執行描述固定於原研究時點；本次只整理導航與保存，不重跑研究或改變原結論。來源 SHA／修訂範圍見 [清冊](ARCHIVE_MANIFEST.json)，後續沿用方式見 [基線入口](README.md)。

審查日期：2026-10-12。來源：[KittenCN/stock_prediction](https://github.com/KittenCN/stock_prediction)。唯讀研究副本位於 `C:/Projects/PythonProjects/technical_analysis/output/external_references/stock_prediction`，以 depth=1 取得完整當前檔案樹，HEAD 為 `d463cdebb63eda0153d41bb9655a3cf48e8d3a8c`（2026-09-28）。沒有取得完整 Git 歷史。

本頁是本次研究紀錄，不是 baldr 產品、架構或模型採用權威。結論為：值得借鑑機率輸出、Regime 感知融合和模型診斷介面；目前不適合直接移植其 Regime 判斷或完整訓練流程。研究實作的存在不證明樣本外增益。

## 可借鑑的設計

| 設計 | 觀察到的實作 | baldr 適合借鑑的部分 |
|---|---|---|
| 市場狀態機率 | VSSM 的神經網路分類頭輸出多類機率 | 在研究 lane 保存完整機率、模型版本與特徵時間，而不只保存單一類別；機率需校準。 |
| Regime 感知融合 | PTFT、VSSM 預測與 Regime 機率共同決定 soft gating 權重 | 研究「不同狀態下不同方法是否有優勢」，並保留權重與 fallback 證據。 |
| 不確定性輸出 | PTFT 提供 0.1／0.5／0.9 分位預測；融合層支持 MC Dropout | 研究可校準的區間、覆蓋率及樣本不足時的拒絕條件。 |
| 共用研究流程 | 多個模型共用資料、訓練與推理入口，保存權重與正規化檔 | 在 baldr 既有 Dataset／Model Registry 上比較模型；不另建一套平行產品 pipeline。 |

來源：[VSSM](https://github.com/KittenCN/stock_prediction/blob/d463cdebb63eda0153d41bb9655a3cf48e8d3a8c/src/stock_prediction/models/vssm.py#L40)、[PTFT/VSSM 融合](https://github.com/KittenCN/stock_prediction/blob/d463cdebb63eda0153d41bb9655a3cf48e8d3a8c/src/stock_prediction/models/ptft_vssm.py#L65)、[模型測試](https://github.com/KittenCN/stock_prediction/blob/d463cdebb63eda0153d41bb9655a3cf48e8d3a8c/tests/test_models.py#L72)。

## 已確認的程式路徑與需先解決的問題

### 1. Regime 標籤是 batch 內 target 分組，市場語意沒有固定

`PTFTVSSMLoss._regime_auxiliary_loss()` 以 `target.mean(dim=-1)` 取得各樣本值，再從當次 batch／預測步的分布計算分位門檻並分類。相同 target 值換一組 batch 成員，類別可能改變。四類不能直接映射成多頭、空頭、盤整或 baldr 的 Trend／Reversion／Breakout。

前次說明將這稱為「報酬分組」需再收窄：loss 將該變數命名為 returns，但沒有強制 target 是報酬率。`init.py` 的預設 `use_list` 選取 OHLC；FeatureEngineer 的 return 設定是附加欄位，不能僅靠設定名證明訓練 label 已改為報酬率。採用前須核對 exact target 欄位、單位與標準化方式。

來源：[分類標籤](https://github.com/KittenCN/stock_prediction/blob/d463cdebb63eda0153d41bb9655a3cf48e8d3a8c/src/stock_prediction/models/ptft_vssm.py#L256)、[預設 target 選欄](https://github.com/KittenCN/stock_prediction/blob/d463cdebb63eda0153d41bb9655a3cf48e8d3a8c/src/stock_prediction/init.py#L73)、[收益特徵](https://github.com/KittenCN/stock_prediction/blob/d463cdebb63eda0153d41bb9655a3cf48e8d3a8c/src/stock_prediction/feature_engineering.py#L126)。

### 2. 帶日期的資料路徑存在時間方向不一致

FeatureEngineer 將單股資料依日期升序排列；queue dataset 的 load_data 保留這個順序。取樣函式卻以第 i 列為單步 label，取 i+1 到 i+SEQ_LEN 為輸入，再反轉窗口。若輸入是升序，輸入列晚於 label 日期；反轉窗口或最後反轉樣本序列不會修正這個時間關係。這是依 source 可追蹤的前瞻風險，必須先用具日期的 fixture 重現並修正，才可判讀預測成效。

此結論限於保留日期並經 FeatureEngineer 的路徑。另一路 train.py 在建 Stock_Data 前移除日期，會略過特徵工程；不能把所有入口當作同一資料契約。

來源：[日期排序](https://github.com/KittenCN/stock_prediction/blob/d463cdebb63eda0153d41bb9655a3cf48e8d3a8c/src/stock_prediction/feature_engineering.py#L118)、[queue load_data](https://github.com/KittenCN/stock_prediction/blob/d463cdebb63eda0153d41bb9655a3cf48e8d3a8c/src/stock_prediction/common.py#L505)、[queue 取樣](https://github.com/KittenCN/stock_prediction/blob/d463cdebb63eda0153d41bb9655a3cf48e8d3a8c/src/stock_prediction/common.py#L631)、[另一訓練入口](https://github.com/KittenCN/stock_prediction/blob/d463cdebb63eda0153d41bb9655a3cf48e8d3a8c/src/stock_prediction/train.py#L1610)。

### 3. Hybrid 的 Regime 輔助 loss 已被切斷梯度

TemporalHybridNet 保存 `vssm_regime` 時使用 `.detach()`，HybridLoss 又以該欄位計算 Regime alignment loss。該損失對模型參數沒有回傳梯度的路徑；增加它的權重不能由這項 loss 訓練 Regime 分支。主預測路徑仍使用未 detach 的 regime_feature，仍可透過主損失學習；這與 PTFTVSSMEnsemble 保留可微分 vssm_result 的做法不同，不能把兩種模型的 Regime 監督混為一談。

來源：[Hybrid detach](https://github.com/KittenCN/stock_prediction/blob/d463cdebb63eda0153d41bb9655a3cf48e8d3a8c/src/stock_prediction/models/temporal_hybrid.py#L232)、[Hybrid alignment loss](https://github.com/KittenCN/stock_prediction/blob/d463cdebb63eda0153d41bb9655a3cf48e8d3a8c/src/stock_prediction/models/hybrid_loss.py#L119)。

### 4. 目前讀到的測試不足以證明 Regime 有效

Regime 相關模型測試主要檢查 tensor shape、KL 非負、融合權重加總及任意參數有 gradient。沒有在這些測試中驗證 Regime 分支的輔助梯度、固定語意、機率校準或樣本外增益。主訓練路徑呼叫 train_with_trainer 時也未傳入 val_loader；這不表示沒有其他 test mode，但不能將 early stopping 解讀為該路徑具有獨立驗證。

此外，VSSM 在 eval 模式仍抽樣潛在狀態。這是可用的機率模型設計，但評估時需要區分單次抽樣、固定 seed、posterior mean 與 MC 彙整，避免把抽樣變化誤當 regime 轉換。

維護文件揭露舊 CI 曾忽略失敗，近期已修正；文件所記 49 項通過是作者的具名環境結果，本次沒有重跑。README 本身也要求獨立樣本與真實成本驗證。

來源：[模型測試](https://github.com/KittenCN/stock_prediction/blob/d463cdebb63eda0153d41bb9655a3cf48e8d3a8c/tests/test_models.py#L82)、[訓練呼叫](https://github.com/KittenCN/stock_prediction/blob/d463cdebb63eda0153d41bb9655a3cf48e8d3a8c/src/stock_prediction/train.py#L1660)、[VSSM 抽樣](https://github.com/KittenCN/stock_prediction/blob/d463cdebb63eda0153d41bb9655a3cf48e8d3a8c/src/stock_prediction/models/vssm.py#L76)、[維護狀態](https://github.com/KittenCN/stock_prediction/blob/d463cdebb63eda0153d41bb9655a3cf48e8d3a8c/docs/oss_maintenance_2026-09.md)。

## 與 baldr 的關係及後續研究順序

baldr 目前 MarketRegimeDetector 用技術指標、規則分數及確認／冷卻機制產生 Trend／Reversion／Breakout，偏策略適用性分類。外部 repo 的四類 target 分組是不同問題，不能直接替換或將機率對應到現有三類。baldr 已有 shadow、模型 registry、時間邊界與 promotion 契約，適合將新方法放進既有研究治理比較。

1. 先定義研究目標：判斷當下市場結構，或預測未來方向／波動；分別定義 feature cutoff、label horizon、label 可得時間、類別與版本。
2. 重現上述資料時間方向、label batch 敏感性、輔助梯度及推理穩定性；先解決這些問題再訓練。
3. 在同一凍結、PIT、purged walk-forward 資料集比較現有規則、簡單 ML baseline 和 VSSM；正規化只 fit 訓練窗，門檻在訓練窗固定。
4. 比較 OOS 分類／機率校準、狀態持續時間和切換頻率；若要影響策略，另比較相同成本模型下的回撤、換手與淨效用，並做有／無 regime 的 ablation。
5. 僅在證據支持增益時提出 challenger shadow 設計；是否能影響正式產品依原有 Gate、review 與 rollback 判斷。

本機參照：`decision_module/market_regime_detector.py:374`、`docs/01_architecture/current/decision_research_portfolio.md`、`docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md:290`。外部原碼採 GPL-3.0；若後續要複用程式碼，另核對專案授權適配。

## 本次驗證與交付界線

- 已執行：clone、核對 HEAD、來源與測試靜態閱讀、比對 baldr 目前契約；clone 工作樹乾淨。
- 未執行：依賴安裝、外部程式 import、pytest、資料下載、模型訓練、推理、歷史回測或 OOS 效果驗證。
- 沒有修改 baldr 程式、產品權威文件、正式資料或排程；沒有 stage／commit。原有兩份未提交文件保持原狀。
- 新增本機產物僅為 ignored 研究副本、此審查頁、task.json 與 Graphify 查詢記憶。純研究未改產品行為，無需同步 Application Manual 或現況／目標架構 SSOT。
