# 決策、研究與 Portfolio

本冊涵蓋目前的 Recommendation、回測、研究證據與 Portfolio 責任。產品能力與 Advice 契約以 [Product Roadmap](../../00_core/PRODUCT_ROADMAP_POST_REFACTOR.md) 為準；工程 Gate 及驗收標準以 [6M Roadmap](../../00_core/ROADMAP_6M_ENGINEERING.md) 為準；現況只看 [Snapshot](../../00_core/PROJECT_SNAPSHOT.md)。

## 模組責任

| 模組 | 主要責任 |
|---|---|
| `decision_module/` | 策略與評分契約、推薦排序、理由、篩選、Regime、Factor 與純計算核心 |
| `analysis_module/` | 技術指標、型態、訊號及其他分析計算 |
| `backtest_module/` | 策略模擬、台股撮合限制、成本、部位與績效分析 |
| `portfolio_module/` | Portfolio 領域帳務投影；服務組合、研究 read model 與 UI orchestration 位於 `app_module/` |
| `app_module/` | Recommendation、Backtest、Research Run、Evidence、Portfolio、Position Health 等 use case 與 DTO 組合 |
| `financial_module/` | 金額、比例、股數等核心數值單位 |
| `ml_module/` | 受治理的模型研究、校準與 shadow 路徑；不因 package 存在而取得正式推薦權限 |

## Recommendation 與 Decision

`RecommendationService`、`ScreeningService` 及其 composition 位於 `app_module/`；`ScoringEngine`、策略契約、`StockScreener`、市場 Regime 與 Factor 契約位於 `decision_module/`。資料 provider 由 application 明示注入，Decision 層不自行建立資料路徑或 SQLite connection。

核心契約如下：

- 正式推薦權重使用整數 bp，總和為 10,000；評分與金融核心精度以 Decimal／整數治理。
- 舊設定未指定 threshold mode 時維持 fixed；quantile 為明確 opt-in。quantile 門檻只使用 T-1 以前資料，暖機需要足夠歷史觀測。
- 當日 eligible universe 先固定，再計算橫斷面百分位；同分保留同一排名語意，母體不足時明確拒絕，不靜默改用其他模式。
- 新 factor 必須保存 `as_of_date`、`available_date`、來源版本、品質與 missing policy。晚於決策日或可得日未知的資料不能供當下決策使用。
- Candidate／shadow 輸入與 formal decision layer 分開。診斷、Research metadata、保存排名或負面證據不等於正式分數、Advice 或 Promotion。
- Regime 的 `date`／effective date 表示請求的判斷日；`details.source_data_date` 表示實際可用行情日，兩者不得混用。此來源日期隨 DTO／snapshot lineage 傳遞；缺日期或超過 cutoff 時，不得借另一個資料集補值，也不改變分類或 PIT 資格。

## 回測與研究時間軸

`app_module/backtest_service.py`、`batch_backtest_service.py`、`optimizer_service.py`、`walkforward_service.py` 與推薦組合回放服務組合 `backtest_module/`。服務負責資料讀取、策略執行、結果保存與交接；UI 不自行計算訊號、撮合、權重或績效。

- `next-session-open.v2` 在 T 日收盤形成委託，於下一個有效且可交易 session 開盤撮合；停牌、零量或缺開盤時不回退到收盤價。
- 明確標記的舊同日收盤路徑保留其舊語意；未版本化舊 run 不會被改寫成新契約。
- benchmark、特徵、標準化、篩選、停損停利與交易價格只使用決策當時可取得的資料。
- Walk-forward 的 OOS 交易狀態在測試窗起點重設；訓練窗口可提供 T-1 歷史特徵，不能把訓練期持倉或交易混進 OOS 績效。
- Replay、OOS、forward、paper 與 live 是不同證據層級。歷史回放不能替代真實決策日後的 outcome。

金融核心金額、成本、股數、PnL、權重與風控不得新增裸 `float` 計算；使用 Decimal、整數股數、整數 bp 或分為單位的整數金額。浮點數只在隔離的 analytics／展示邊界使用。

## Portfolio、Paper 與持倉研究

手動 Portfolio 既有帳務、使用者聲明持倉、虛擬 execution trace 與 Paper Trade Ledger 是不同來源。它們的 identity、保存位置、寫入者與證據資格不能因共用股票代碼或畫面而合併。

- 手動交易不會由 backtest 或 recommendation 自動匯入；回測 run 不是實際 fill。
- 使用者聲明持倉只形成研究投影，依 cutoff、可得時間、來源品質與 snapshot hash 判讀；缺少 entry lineage 時不能當成實際成交、已實現損益或績效校準。
- Paper trade event 使用明示的 research-only identity；paper snapshot、benchmark、成本與 execution gap 必須可追溯。查詢服務不建 schema、不寫資料、不把 paper 結果轉成正式 Portfolio。
- Paper daily account 的 writer 以策略 id/version、paper account namespace、operation id、execution date、portfolio identity、aware decision／mark cutoff、selected READY route 與 policy 綁定同一 operation；金融量值採固定 Decimal context。ledger 與 state 各有獨立 SQLite transaction；兩庫之間沒有原子提交保證，`PENDING → LEDGER_COMMITTED → FINALIZED` 未到 `FINALIZED` 不可供 availability reader 當完成結果。重試必須核同一 operation identity、payload、marker/hash 與既有 checkpoint；不可跳過 partial finalize、以新 identity 重做同一 operation，或把部分提交投影成可用 Paper snapshot。
- Position Health／Exit 輸出是具來源及資料品質的 read model 或 proposal；不自動交易、平倉或改寫持倉 lifecycle。Saved Health 結果以 immutable result、receipt、baseline 與 source witness 綁定及各自 hashes 發布；writer 在發布並讀回後才簽發 aware UTC `available_at`，相同有效重試沿用原 receipt clock。這個 writer availability 只表示 exact receipt 可讀，不替代 witness 的 source availability 或 PIT 資格。讀取以 exact `receipt_id` 選取，並核 portfolio、snapshot、decision date、完整 position IDs／股票／股數及 aware cutoff；要求 receipt 可得時間不晚於 cutoff、result `observed_at` 不晚於 writer availability，且 result、receipt、baseline、source witness 的 identity／hash／scope 全部相符。缺件、晚到、identity 或 hash 不符一律拒絕；不以 mutable latest 補件。
- Portfolio research scenario 將 account kind、portfolio、snapshot、source hash、request 與 aware cutoff 綁成 exact context。`portfolio-research-scenarios.v3` 是 canonical JSON artifact payload，`portfolio-research-store.v1` 是獨立 SQL store schema，不能混為同一版本；reader 以原 bytes/hash 核版本、canonical encoding 與完整欄位，未知 schema、浮點／非有限金額或含糊 payload 一律拒絕。保存完整 cash、shares、mark、market value 與 NAV；以 Decimal／整數單位維持金額守恆，bp 僅供呈現、不反推金額，正股數即使呈現為 0 bp 仍是持倉。讀取只沿 `PORTFOLIO_RESEARCH` 明示 route，不 fallback 到其他帳戶或市場資料。
- 新增或重播資料以不同 namespace／evidence tier 保存；不得以目前市場資料補回舊保存結果。

## Evidence 與模型權限

```text
Recommendation／Portfolio／Health 輸出
  → Forward outcome／Paper／Live evidence
  → 人工 review 與效果歸因
  → 保留、限制、降權、退休或另行提出 promotion
```

Evidence Event／Outcome、Research Run Registry、Evidence Review 與 Workbench read model 以已保存 metadata 和 source trace 建立可回溯投影。缺少來源、期限、樣本或可得時間時保留 blocker／unknown，不用歷史 replay 補足正式資格。Promotion、Demotion、Retirement 與 production scheduler 必須經各自受控權限，不由 dashboard、readiness 或 ML projection 自動觸發。

Paper adapter 將一般 Portfolio alerts／risk prompts 與 Paper research lane 的 alerts、risk、status、readiness、blockers 分開保存；研究 seed 不覆蓋使用者持倉。Health read model 將機器治理缺件與使用者待辦分列。排程摘要也要分辨 child return code、來源／研究資格、工程故障與使用者待辦；控制 run 的 evidence writers 留在 QA 控制 namespace，不能因 wrapper 成功就寫入正式市場、Paper 或 Evidence store。

需跨觀測日或保存樣本的研究沿明示 parent／child receipts、calendar、price point、benchmark、cost policy 與固定 cutoff 建立 exact projection。讀者重驗來源 pins，不掃 latest、不呼叫 producer、不寫 outcome store；沒有官方可得時點、benchmark 或 custody evidence 時，狀態仍為未接受。Forward close-to-close return 固定 `is_execution_pnl=false`，不可作為成交損益、next-open 回測或績效校準。

Forward rule observation producer 只接受 exact parent plan／receipt、完整 cohort／generation 與來源 cutoff 等已釘選輸入，predicate 由服務依來源資料計算；caller 不可提供 score、target、fill 或 source clock 來宣稱結果。來源 `captured_at` 不早於 parent receipt completion，parent receipt completion 不早於 source cutoff；artifact 與 receipt 寫入並讀回後才由 writer 產生 `available_at`。reader 要求 aware cutoff 不早於該時間，並重核 parent、cohort、generation、來源時鐘與 hashes。它是窄用途的 regular-file/no-follow bounded reader：單次 capture 至多 2 MiB、256 captures、保留 bytes 合計至多 64 MiB；此限額只適用此 observation reader，不是一般檔案或全域讀取預算。

sealed label readiness、模型公平比較與 shadow acceptance 可讀既有 sealed evidence／匯出 DTO，核同一 sample IDs、decision-source pins、label envelope、split 與成本契約。研究 consumer 不 fit、不改寫 registry、不啟用 model loader，也不把 read-only acceptance 轉成 promotion。Person H20 是個人研究 lane：自然成熟 caller 先核 exact completed terminal，再按完整 `current_symbols` 建獨立 cohort／daily／entry／outcome identity；一般推薦 current-observed eligible 子集合不得替代完整母體。候選 `training_as_of` 是 fit cutoff；merged-lineage manifest 的 `training_as_of` 是 lineage cutoff，兩者不可混為一個欄位。若 candidate 有獨立 `training_cutoff`，它必須等於 lineage cutoff，且 fit cutoff 不晚於 lineage cutoff；沒有獨立欄位的 legacy candidate 只有在 fit cutoff 等於 lineage cutoff 時才可讀。decision-time lane 的兩個 cutoff 均不得晚於 decision date，sample label availability 也須不晚於相應 training cutoff。歷史漏日不回填，這些 identity 規則不代表模型已具 formal 或自然成熟資格。

Recommendation ML Shadow、Portfolio Allocation ML 與 Personal H20 是不同用途及來源路徑。模型存在、訓練成功或 UI 可讀均不代表正式 ScoringEngine 已使用 ML。Formal input、自然成熟 evidence、校準、Promotion review 與 rollback 條件分別依產品 Gate 及對應 QA／運維文件核對。
