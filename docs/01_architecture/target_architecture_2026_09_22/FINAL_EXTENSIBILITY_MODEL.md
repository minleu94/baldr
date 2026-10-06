# 最終擴充模型與變更影響推演

> 設計定案，尚未實作。本分冊展開唯一權威 [FINAL_TARGET_ARCHITECTURE](FINAL_TARGET_ARCHITECTURE.md)。下面的局部修改承諾以 canonical row、schema-driven codec、完整 execution 與 replay 遷移已完成為前提；不把目前仍存在的多份 dict/DTO 當作已消除。

## 1. 如何決定 owner

先按語意找 owner：來源事實歸 data、技術公式歸 analysis、業務解讀／選取歸 decision、執行／保存／治理歸 app、呈現歸 UI、feature/label/model ABI 歸 ML。新增欄位不代表每一層都加一份 DTO。只在真實變動點擴充現有 registry，不新增全域欄位平台、plugin bus 或泛用 manager。

新 scalar 透過 typed contract 自動往返新格式；contract 是唯一欄位 schema。SQL index、legacy wire 與 UI label 都有各自必要投影，但不得手工複製一整列。非索引欄位不改 repository；新增 UI 不改 evaluator；新增模型特徵不修改舊 feature contract。

## 2. 常見修改導航

| 需求 | 精確起點／預期修改 | 不應修改的邊界 | 相容驗收 |
|---|---|---|---|
| 新推薦業務欄位 | `decision_module/recommendation/contracts.py` 加 typed optional 欄與語意；app recommendation contract 的格式 revision 宣告；產值的 evaluator/factor；需要顯示才改 presenter | execute/save/replay 不逐欄搬運；非索引欄不改 store/SQL/codec body | 新舊 artifact、null/0、欄位不漏存、原排序未變 |
| 新執行 metadata | `app_module/recommendation/contracts.py` 與真正產生該 metadata 的 use case | 不塞進 RecommendationItem；不讓 UI 偽造 provenance | execution schema revision、深凍結、來源真實性 |
| 新計算／技術指標 | `analysis_module/technical_analysis/` 的 calculator/kernel 與既有參數 registry；需要物化時改具名 app job/data writer | 不改 strategy、ML registry 或 UI，除非明示使用它 | 公式、warmup、null、日期、可得時間；既有欄精度不變 |
| 新 filter | `decision_module/recommendation/filters.py`；必要的 typed config 與具名 reason code | 不改 save/repository、report row、ML | candidate/assessment 一致；禁用預設不影響原結果；PIT 自查 |
| 新 ranking factor | `decision_module/factors/<factor>.py` 的語意轉譯／公式／eligibility；既有 factor registry；選用設定/權重 | vendor mapping 不放 app；不需要改 execute／codec；僅新來源事實才改 data | factor unit/version、missing/eligibility、tie-break、母體與原策略預設 |
| 完全新策略 | `decision_module/strategies/<strategy_id>.py`、既有 registry 的目標位置、StrategySpec/Meta 必要參數描述 | 不改 engine dispatcher 的策略 if/else、store、ML、runtime、backtest 撮合核心 | 相同 StrategyExecutor signal 契約、look-ahead、成本/成交、舊策略回歸 |
| 新 datasource | `data_module/sources/<source>.py`、標準 observation mapping、具名 composition/provider 選擇 | 同標準事實的 factor 不改；不因此取得 formal eligibility | unit/calendar/revision/available_at、fallback、source custody、candidate root |
| 新持久化欄位 | 業務值仍從 domain/app contract 開始；只有 SQL 查詢需求才加 `result_artifact_store.py` index projection 與 migration | 不再定義另一份保存 DTO；不逐個修改 UI/save caller | 非索引自動 roundtrip；索引可重建，舊 payload 不覆寫 |
| 新 UI output／報表 | `ui_qt/views/<feature>/` presenter/model；新報表在既有 reporting 用例下呈現 execution/query | 不新增 score 公式、不從 live service 重組保存 payload | 顯示 unit、None、排序與 precision；Manual 同步 |
| 新 ML feature | `ml_module` 對應 feature contract/builder 與 registry 新版本；需要時新 dataset/model release | 舊 ordered schema、bytes/hash、transform、checkpoint、active model 不變 | 有序欄位／尺度／mask／cutoff、新舊 model load、opt-in lineage |

domain factor 解讀例如「某比例是否足以構成風險」；data mapping 例如「來源以百分比文字提供、轉為標準整數 bp」。這兩者可分開修改，但同一 factor 的數學定義與語意轉譯必須相鄰。app 只選定已標準化的 input，不再有 `adapters/factors` 公式副本。

## 3. 必測推演 A：confidence_score → 歷史 → UI → 未來可選 ML

### 3.1 本次功能假設與欄位定案

這裡的 confidence 是**規則推薦的信心指標**，不等同預測勝率，也不覆蓋現有 calibration 的 `evidence_confidence`。目標 contract 採：

```text
RecommendationItem.confidence_score_bp: int | None = None   # 0..10000
RecommendationItem.confidence_method_version: str | None = None
RecommendationItem.confidence_status: str = "not_computed" # 受契約枚舉驗證
```

對外需求名稱是 `confidence_score`；canonical unit 明示 bp，UI 可顯示百分比並標示方法與缺值原因。若實際需求是模型預測信心，owner 必須改為既有 ML projection contract，不把模型輸出偷渡為規則欄位。計算方法與範圍須由功能需求定義；本架構不發明統計方法或承諾其投資有效性。

### 3.2 實際改動順序

1. **單一欄位契約與版本**：在 `decision_module/recommendation/contracts.py` 加上上述 typed 欄及 range／status／method 一致性驗證；在固定的 `app_module/recommendation/contracts.py` 增加 `EXECUTION_SCHEMA_REVISION`，並宣告仍支援的舊 revisions。這一處只管理格式 header，不抄欄位清單。`None` 是未計算／無法計算，0 是有效最低分。歷史舊 artifact 的 decode view 使用明示 default，不改原 bytes/hash。
2. **單一產值點**：在 `decision_module/recommendation/evaluate.py` 呼叫的具名 confidence 計算函式產值；若已有相關 factor，可使用其 typed contributions，禁止 app/UI 各算一次。公式用整數／Decimal、只用決策當時資料；confidence 預設只 annotation，不能順便更動 rule ranking。
3. **自動保存**：既定 codec 從 typed schema 遍歷新欄，產生可辨識 revision；save/persistence/data store/replay 無欄位清單修改。沒有搜尋／排序需求，SQLite 無 migration。若這一步仍需要手工加欄到另一個 row mapping，區塊 5 驗收失敗，先修正遷移。
4. **必要呈現**：推薦當次與歷史頁共用 `ui_qt/views/recommendation/presenter.py` 的 confidence 格式定義；Qt column/model 指定顯示位置。這是目標具名 presenter，需由原 view 的格式化抽取。一般 JSON 匯出由 codec 自動涵蓋；有固定欄序的 CSV/報表才各加所需 display 欄。
5. **未來 ML opt-in**：本次不修改任何 ML feature list。之後若選用，建立新 feature ID/version、registry/dataset schema，從不可變 execution 以 `(result_id, stock_code)` 及 decision cutoff 取值，保存 method/version 與 missing policy；沒有當時值不能用未來重算冒充歷史觀測。

核心程式變更是「欄位契約＋格式版本宣告＋計算＋呈現」四個固定落點；版本宣告只有 header 與支援範圍，不是手工序列化。型別與 UI 可能各跨鄰近檔案，不用精確檔案數掩蓋工作。另需相應測試與 Manual。無需搜尋整個 repository 來尋找每條 execute/save/replay 的欄位搬運。

### 3.3 設計驗收

| 測試 | 必須成立 |
|---|---|
| confidence=None／0／10000／越界 | 前三者保存、讀取、顯示正確；越界拒絕 |
| execute→延後 save→load→歷史 UI | confidence/method/status 不變；來源更新或新 run 不污染 |
| input/output 巢狀修改 | sealed execution 無法被修改，原輸入修改不影響 bytes/hash |
| 舊無 confidence 的 artifact | 可顯示未知；不回查現在值、不重寫 artifact |
| 新 schema revision 被舊 reader 開啟 | 明示 unsupported，不丟欄再回存 |
| 沒有改 ML contract | 原 matrix/registry hash/model input 完全不變 |

**設計推演結論：通過。** 消除手工 codec／replay mapping 是前提；上述測試尚未執行，不能宣稱目前程式通過。

## 4. 必測推演 B：完全新策略

1. 從 `decision_module/strategies/` 建立具名 executor，實作 [StrategyExecutor](../../../decision_module/strategies/contracts.py) 的 `generate_signals` 契約，定義 strategy ID/version、參數、minimum history 與理由。沿用 [StrategyRegistry](../../../decision_module/strategies/registry.py) 的唯一 ID／duplicate 拒絕語意；不建立新的 plugin discovery。
2. 只在該 registry 登錄此 executor。app profile/lifecycle 繼續保存 spec/version 並依既有流程選用；若策略需要新參數，補該策略的 spec/metadata。研究合格、promotion 與使用權限不由 registry 自動授予。
3. 需要新技術計算時依情境「新計算」新增 analysis 指標；需要新來源時依 datasource 流程新增 data observation。這是需求增加了資料或計算，不能假裝所有全新策略永遠只改一檔。
4. backtest 呼叫同一 signal 介面，成本、撮合、資金與績效核心不改。推薦若原產品支援此類 signal→candidate 路徑，沿用既有 adapter；若新策略產生不同型態行為，例如事件交易或期權，而現有 signal contract 無法表達，必須另作介面演進決議，不在 generic dict 偷渡。
5. UI 從 registry metadata 顯示策略與通用參數；只有新互動元件才改專屬 UI。結果透過 canonical contracts/codec 保存 strategy ID/version，不改 repository schema。

驗證新策略 look-ahead、warmup、同日可得性、重跑決定性、reason 與 signal shape；驗舊策略、持倉／成本／成交結果保持基線。應比較同一既有模式，不能拿 interactive 與 replay policy 差異當新策略 regression。

**設計推演結論：通過既有 signal 契約內的全新策略。** 預期改策略實作＋registry／spec，額外能力只修改真正需要的 owner；execute/save/ML 不因 strategy ID 新增而加分支。

## 5. 必測推演 C：新增一個技術特徵，歷史 ML 保持有效

1. 在 `analysis_module/technical_analysis/` 增加新 calculator 與既有參數 registry，定義精度、單位、warmup、available time；不重命名或重算既有技術欄。
2. 若需要落地，新欄使用獨立版本或 additive publication，保留舊資料。先檢查是否觸及 [ML source 凍結清單](FINAL_ML_COMPATIBILITY_CONTRACT.md) 或既有 ML 依賴的物化時序；觸及即走獨立相容實驗，不直接改 old computation identity。
3. 非 ML 消費者可明示選用。舊 `core-long-history-features-v1` 的 20 欄、feature order、scale、missing、transform、store bytes 與模型全部不變。
4. ML 要使用新欄時，新增 feature registry／dataset/model release 版本。不可在 v1 ordered list 後面直接 append 並仍宣稱 v1；新資料沒有該時點值就保留 missing。
5. 格式支援 immutable extension block 時以 exact row identity/parent hash 連接；不支援就發布新 artifact，不能承諾零重建／零額外容量。禁止按新版排序位置與舊 row refs 拼接。
6. 舊模型仍解析其原 schema、input matrix 與 fitted transform。新模型只依新契約進行另案訓練、驗證、promotion；架構或指標發布不切換 active pointer。

驗收：舊資料/hash/readback 不變、舊模型載入及 prediction parity、新欄 missing/zero/年度 carry/cutoff 正確、不同 schema 混用被拒絕。source identity 改變就新 run，不偽造 resume 相容。

**設計推演結論：通過明示版本 opt-in 的擴充。** 保持歷史有效不等於讓所有舊模型直接接受新特徵，也不等於禁止建立新 artifact。

## 6. 何時應拒絕「看似方便」的新增

- app/UI 想放一份新 score 公式：回到 domain owner。
- 新欄位要改五條手工 save/replay row dict：canonical 遷移尚未完成，先收斂 mapping。
- 用 `extended_attributes` 放正式核心值：改成 typed field 或既有 typed factor contribution。
- 為單一新來源增加抽象 provider hierarchy：先用現有 narrow port 與 composition；只有第二個實際需要的變體才新增機制。
- 用「向後相容」保留雙引擎：保留歷史 decoder／必要 ABI，移除沒有 caller 的 runtime body。

每個實作 PR 以本表報告「起點、修改範圍、未受影響契約、驗證」，不能只以資料夾變漂亮宣稱架構改善。
