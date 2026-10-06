> **已被取代，僅供審查歷史（2026-09-22）**：本草案不再作為實作依據。請閱讀 [FINAL_EXTENSIBILITY_MODEL.md](FINAL_EXTENSIBILITY_MODEL.md)；所有目標架構決策以 [FINAL_TARGET_ARCHITECTURE](FINAL_TARGET_ARCHITECTURE.md) 為準。下文保留原稿供核對紅隊引用，與 FINAL 衝突的條文全部失效。

# A–J 擴充情境檢驗

> 這是對 [目標架構](TARGET_ARCHITECTURE.md) 的設計檢驗，並非已完成十項程式實作。以下「改動點」指有語意責任的模組／設定，數量不含測試、文件與過渡期 import alias；不保證永遠只改一個檔案。

## 共同成功標準

概念變更應只碰概念 owner、必要邊界 mapping 與明示呈現。execute、save coordinator、replay、UI 不應各自新增一次同樣欄位搬運。需要新增資料取得、SQL index 或複雜互動時可以增加改動點，但要有直接理由。

所有情境保留 existing behavior，預設關閉新政策；方法／預設值真的改變時另行版本化，不把架構整理當成授權。金融值用 Decimal／整數 bp／scale；沒有 evidence 的值為 unavailable，不是 0。新功能實作時另跑 Look-ahead 自查。

| 情境 | 正常改動面積 | 主要隔離契約 |
|---|---:|---|
| A 推薦新欄位 | 3–4 個責任點 | canonical RecommendationItem＋一個 versioned codec |
| B 技術指標 | 2–3；若持久化再加 1–2 | indicator spec／FeatureFrame |
| C 推薦 filter | 2–3 | FilterDecision／CandidateAssessment |
| D ranking factor | 2–3 | FactorContribution＋versioned ranking policy |
| E 新策略 | 2–4 | StrategySpec／StrategyExecutor／DailySignalFrame |
| F 新來源 | 3–4；新語意再加對應 owner | SourceObservation／MarketSlice／eligibility |
| G 新排除／降級原因 | 2–3 | typed Reason event／同一 assessment |
| H persistence 新欄位 | storage-only 1–2；業務值 3–4 | versioned codec／repository port |
| I 新 UI view | 2–3 | application query／read model |
| J 新 ML feature | 4–5 個相容責任點 | 新 registry/schema/transform＋舊 reader |

## A. 新增 `confidence_score`

**先定義語意**：本例是可解釋的規則信心指標，採 optional `confidence_score_bp` 或 Decimal＋unit，不當成勝率。如果需求實為 calibrated probability，使用既有 calibration contract，不平行建立另一個 probability owner。

- **現有入口**：`app_module/dtos/__init__.py` 的 `RecommendationDTO`、`decision_module/scoring_engine.py`、`app_module/decision_presentation.py`、推薦 presenter。
- **目標改動**：① decision recommendation contracts 定義單一欄位與 method/version；② 其 domain calculator 產生值與 evidence；③ result codec 增加可選欄位讀寫；④ 要顯示時才改 presentation column/formatter。通常 3–4 個責任點。
- **不應改**：data source、DB index、run orchestration、save coordinator、replay engine、ML registry、其他 UI views。它們傳遞整個 item／execution，不逐欄抄寫。
- **隔離契約**：`RecommendationItem` 為唯一業務 schema；persistence codec 寫讀同一型別，舊 DTO 只是 re-export／兼容視圖。
- **相容**：舊 JSON 缺欄為 None＋unavailable；新 schema 保留既有 score/rank。不能為舊推薦以今日算法補算 confidence。舊讀者若不能忽略新增欄位，以已驗證相容 decoder 或 export v1 處理，不能宣稱所有未知 client 都可讀。
- **驗收**：同輸入既有欄位完全相同；新舊 payload round-trip；保存後 UI 與直接結果一致；沒有意外加入 confidence 排序。

## B. 新增技術指標或數值 feature

- **現有入口**：`analysis_module/technical_analysis/technical_indicators.py`、`indicator_parameter_registry.py`；現行 publication 由 `UpdateService.calculate_technical_indicators` 組合。
- **目標改動**：① analysis calculator；② indicator spec（inputs、parameters、window/warmup、output id/dtype/unit/missing）；③ 若選用 UI 需自訂參數，補該參數 presenter。若要寫回 technical table/cache，再改 data writer mapping／additive schema，不能要求所有指標都自動持久化。
- **不應改**：推薦 save/replay/receipt、portfolio、report exporter、ML。新增指標不意味新 ranking factor，更不自動加入模型。
- **隔離契約**：versioned indicator spec → FeatureFrame；decision 宣告 required feature IDs，由 app 準備。
- **相容**：原指標名字、參數 defaults、運算順序、warmup／NaN、捨入不變；新輸出不回寫舊 frozen datasets。DB 缺欄時舊 reader 繼續可讀，依 contract 標 feature unavailable。
- **驗收**：固定已知序列／短歷史／缺值／跨日窗口，新增特徵不使用未來 rows；舊指標 parity。若更改既有公式，另建 version 和重算影響計畫，不藏在加指標中。

## C. 新增推薦 filter

- **現有入口**：`RecommendationService.run_recommendation` 的 filters 與 `decision_module/factors`，遷移時依既有排序抽出。
- **目標改動**：① `decision_module/recommendation/filters/<name>.py`；② 固定順序的 filter registry/config schema；③ reason 定義（若已有可用 code 則不新增）。UI 如需新控制項可增加一個直接相關 presenter。
- **不應改**：ranking engine、repository、negative evidence builder、replay、runtime log handler。filter 回 typed assessment，它們既有通路就能保存與顯示。
- **隔離契約**：filter 消費 prepared features/context，回 pass/fail/missing/degraded、observed/threshold、stable reason；不抓 DB 或改 score。
- **相容**：預設 disabled；舊 config 不含新鍵即採舊行為。filter order 和 early-stop policy 是策略版本的一部分；不默默改原 filters 的應用順序。
- **驗收**：邊界等於門檻、缺值、unavailable、正負例；相同 config 舊結果不變；被排除者進入同一 run 的 Why Not。

## D. 新增 ranking factor

- **現有入口**：`decision_module/factors/`、`scoring_engine.py`、`app_module/recommendation_ranking_pipeline.py`、既有 weight contract。
- **目標改動**：① 因子計算／spec；② versioned weight/policy registry；③ contribution 呈現 metadata（通用 factor 明細已支援時可免）。實際 ranker 將來只需消費明確 policy 和有序 contributions。
- **不應改**：data storage（既有 inputs 夠時）、run result container、save、歷史 decoder、backtest engine、ML dataset。若新因子需要新來源，額外組合 F，不假稱兩檔完成全部工作。
- **隔離契約**：`FactorContribution`（id/version/value/unit/weight_bp/quality/evidence）；score combiner 與排名保持不同責任。
- **相容**：舊 profile weight set 不變，新增 policy/version 才啟用因子；總權重與 Decimal rounding 依既有契約。不能用缺因子=0 假裝觀測值，不能擅自重正規化剩餘權重。
- **驗收**：逐項分數、總分、fixed／quantile、母體與 tie-break；舊 version replay parity，新 version 顯示 method 差異而非覆寫舊分數。

## E. 新增完整策略

- **現有入口**：`app_module/strategy_spec.py`、`strategy_registry.py`、`strategy_executor_adapter.py` 與既有 strategy configurator。
- **目標改動**：① decision strategies 下新 executor；② 同域 registry 登錄 spec／version；③ profile/preset mapping（若要向使用者提供）；④ 只有特殊參數才新增專屬表單。
- **不應改**：推薦 execution／persistence、backtest撮合、report、UI task worker、來源 ingestion。strategy 不應私下另開 backtest。
- **隔離契約**：`StrategyExecutor.generate_signals` → 既有 DailySignalFrame；signal timing、score/reason schema、required indicators 明示。
- **相容**：新 strategy_id/version；舊 registry entry、config 和保存結果可讀。策略 promotion 與可見性遵守既有 gate，註冊不等於批準正式投資用途。
- **驗收**：warmup與 execution_start_date、同日訊號／次日撮合界線、缺值、空信號；通過共用 backtest／replay route，禁止模型或未來值進 signal。

## F. 新增市場／基本面 datasource

- **現有入口**：`data_source_capability_registry.py`、`p0_source_contract_registry.py`、source acceptance、fundamental provider；新 source 不繞過它們。
- **目標改動**：① source adapter/parser/raw custody；② source schema／availability／license／quality contract；③ registry/composition routing；④ 有新儲存需求才加 data repository/schema。若提供新的 domain 語意，再增明示 factor mapping。
- **不應改**：推薦 evaluator、策略、UI view、ML trainer；先輸出既有 SourceObservation/MarketSlice，與其他 adapter 同樣處理。
- **隔離契約**：source-owned normalized record＋eligibility；app adapters 將基本面觀測轉成 domain facts，來源 API 欄名不進 domain。
- **相容**：現有 source priority／fallback 不變；新 source 先 candidate lane。available_at、revision、units 沒有證據就 unknown；不拿今天看到的歷史財報回填當時可知資料。
- **驗收**：recorded response fixtures、缺欄／改版／停機／重複 key、日期與單位、正式 root 拒絕、candidate 不影響原推薦；新來源接受要另走正式 gate。

## G. 新增同時出現在 runtime／保存／重播／UI 的排除或降級原因

- **現有入口**：`recommendation_run_support.py` 的 matrix／buffers、reason engine、exclusion payload DTO 與 presentation。
- **目標改動**：① `reasons.py` 加 stable code/category/parameters；② 發生該條件的 filter/source stage 發出同一 typed event；③ UI 中文文案／修復提示（可使用既有 category fallback）。**正常只改 2–3 處**。
- **不應改**：log router、SQLite schema、JSON codec dispatch、historical viewer、save coordinator、replay engine。typed event 的一般欄位已能端到端傳輸。
- **隔離契約**：`Reason`＋`CandidateAssessment`；runtime 訂閱其序列化投影，保存同 event code／params／subject／stage。liquidity 依 category，不靠字串包含判斷。
- **相容**：舊 code 不改名；新 reader 保留未知 code，舊 UI 可顯示 code＋generic description。舊 artifact 未記原因只能 unknown，不追填。
- **驗收**：同 run_id/reference 的原因在四個端點一致；新 code 未登錄 UI 文案仍可讀且不崩潰；severity／品質不被遺失；為 G 增加 DB 欄或多份原因清單即不合格。

## H. 新增 persistence field

分清「storage metadata」與「業務欄位」，不要先加 DB column 再讓各層猜意義。

- **現有入口**：`RecommendationRepository` 的 JSON writer／SQLite index 與 DTO codec。
- **目標改動**：若只是 indexed tag／保存狀態，改 repository schema migration＋query mapping（1–2）；若是 recommendation 新業務值，先照 A 改 owner＋codec，僅需搜尋／聚合時才加 SQL projection（3–4）。
- **不應改**：domain evaluation（storage-only case）、UI execution、ML、replay算法。不能讓 domain 知道 column 名或 SQL default。
- **隔離契約**：repository port 接完整 execution；中央 versioned codec 負責 wire，DB index 是 projection。
- **相容**：additive nullable column／新 index，既有 JSON 不重寫；明示 old-schema reader、transaction、backup/readback/rollback。舊 writer 若可能丟失新欄，限制它只寫原格式或停止新格式寫入後回滾，不保證任意混跑。
- **驗收**：old DB copy load、new/old payload、缺欄、orphan recovery、同 ID 不同 hash 拒絕、crash at file/index 邊界；正式 migration 仍須另行授權。

## I. 新增 UI view

- **現有入口**：`ui_qt/main.py`、views、TaskWorker；`decision_presentation.py`、stock report／workbench queries。
- **目標改動**：① 新 view/presenter；② navigation registration；③ 若現有 query 不足，新增同域 application query/read model。通常 2–3 點。
- **不應改**：domain engine、market storage、ML schema、recommendation execution、其他視圖的業務欄位。新 view 不應另建 result DB 或直接 SQL。
- **隔離契約**：application query 返回有身份、quality、dates、source refs 的 read model；write action 是明示 command。
- **相容**：共用 theme、worker／取消／request identity、existing navigation context；舊 view 可繼續讀同 API。不能因新 view 加載而觸發重訓、推薦重算或資料更新。
- **驗收**：loading/error/empty/stale callback/close、同 result 的跨頁值一致、accessibility。UI 實作必跑 repo 指定 UpdateView pytest、validator、全域 mypy 與 changed Python compile，這次文件任務不代跑 UI 驗收。

## J. 新增 ML feature，保留舊 calculated datasets

- **現有入口**：`ml_module/feature_registry.py`、historical feature builder 或 allocation feature contracts；對應 dataset producer／manifest 和 loader。
- **目標改動**：① 新 feature spec/version；② calculator；③ 新 dataset manifest／extension writer；④ schema adapter／model binding；⑤ 新 shadow experiment/model config。通常 4–5 個必要相容責任點，不是十個任意 downstream consumer。
- **不應改**：舊 numeric bytes、mask/dtype/order、舊 registry hash、舊 trainer算法與 fitted transform、現有 production rule、UI、推薦 persistence。新 feature 不強迫全市場重算或舊模型重訓。
- **隔離契約**：explicit feature schema/order/unit/scale/missing/transform，per-version reader 與 artifact expectation；詳見 [ML plan](ML_COMPATIBILITY_PLAN.md)。
- **相容**：v1 model 仍用 v1 matrix；v2 model 使用 v2 contract。新 block 如可重用 base 要 exact row-key join；monolithic store 不支援加欄就生成新 publication，不原地改 binary。未知 available time 不因新 feature 被補成可得。
- **驗收**：舊資料／模型讀取和 prediction parity、wrong order/dtype/hash 負例、cross-year row refs、missing versus 0、新來源晚到／revision、capacity。未通過 shadow／promotion gate 不進正式決策。

## 設計修正與判定

對比現況，A/G/H 最容易因 DTO、last_*、UI 保存、negative evidence 多份 mapping 擴散。因此先完成執行 envelope、canonical assessment 和一個 codec，再宣稱局部擴充已成立。只加新目錄但保留原來逐欄搬運，不通過本檢驗。

J 的較大改動面積是 schema／資料／模型相容性本身需要的責任，不用萬用 registry 偽裝成一檔修改。F 的新來源若引入全新語意，也應明示組合 B/C/D/J，而不是暗中污染現有 decision。

## 更新記錄

- 2026-09-22：完成 A–J 設計檢驗、改動面積、相容政策與驗收要求；尚未實作情境。
