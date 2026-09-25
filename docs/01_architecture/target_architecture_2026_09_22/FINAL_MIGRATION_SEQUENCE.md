# 最終漸進遷移順序

> 狀態：架構定案、尚未實作。本文件只定義遷移順序及退出條件；[FINAL_TARGET_ARCHITECTURE.md](FINAL_TARGET_ARCHITECTURE.md) 是六份 final 文件的唯一架構 SSOT。以下 block 是未來實作驗收要求，不是本輪測試或遷移完成紀錄。

配套文件：[資料流](FINAL_DATA_FLOW.md)、[擴充模型](FINAL_EXTENSIBILITY_MODEL.md)、[ML 相容契約](FINAL_ML_COMPATIBILITY_CONTRACT.md)、[架構不變條件](FINAL_ARCHITECTURE_INVARIANTS.md)。本序列取代舊 [MIGRATION_STRATEGY.md](MIGRATION_STRATEGY.md) 的實作順序；舊稿只保留設計歷史，不再作為新增實作的依據。

## 1. 唯一實作順序

```text
Block 1  固定行為、精確 caller 與 ML 相容基線
   ↓
Block 2  canonical typed contracts＋單一 schema-driven codec＋最小完整 execution capture
   ↓
Block 3  UI／CLI／save／replay 接收完整 execution，停止讀 live last_*
   ↓
Block 4  分離 I/O、計算與 domain；共用 evaluator，保留既有模式政策差異
   ↓
Block 5  移除暫時 runtime 相容路徑，執行邊界與三項擴充驗收
```

**Canonical schema 與 codec 必須先於引擎責任拆分。** 不先搬目錄、不先建立新舊 DTO 間大量逐欄 adapter，也不以建立空 package 作為完成證據。Block 2 的 capture 只是使既有行為得到完整、凍結的輸出；主要 caller 切換在 Block 3，計算與 I/O 的抽離在 Block 4。

ML 從 Block 1 起維持凍結邊界。初輪推薦重構完成不代表 ML internals 已重構、資料已正式接受、自然 evidence 已成熟或模型已獲 promotion。既有金融浮點邊界、計算次序與 rounding 的改造必須另作數值遷移驗證；本次責任抽離不得同時改它們，新金融核心計算仍須遵守 Decimal／整數單位規範。退休帳中 `TMP-NUM-01`、`TMP-ML-01/02` 有獨立驗證 gate；尚未退休時必須保持列管，不能把推薦五 blocks 完成宣稱為整體 numeric／ML 遷移完成。

## 2. Block 1：固定基線與精確接線清冊

| 必填項目 | 執行要求 |
|---|---|
| Objective | 形成可獨立重跑的行為 oracle、精確 caller inventory 與 ML 相容清冊，知道何種差異必須停止遷移。 |
| Affected area | 推薦、ranking、negative evidence、UI worker／save、排程與個人化 CLI、歷史 replay、repository、受影響 ML consumers。 |
| Prerequisites | 記錄當次 HEAD／dirty files；依 `TWStockConfig` 確認正式與隔離資料根；不覆寫其他任務變更，不以正式資料跑寫入測試。 |
| Preserve | 原 score／rounding／tie-break、filter 次序、universe 與 candidate limit、cutoff、來源 priority／fallback、regime 歷史狀態、成本／成交時間、identity、ML bytes／hash／載入拒絕政策。 |
| Validation | 固定輸入及既有輸出；涵蓋 fixed／quantile、母體不足、合法零候選、部分失敗、取消、缺資料、來源 fallback、A/B 交錯、來源改變後延遲保存、identity conflict、重試、舊 JSON／SQLite copy。以舊 snapshot、手算例或獨立 oracle 比較，不能讓新舊測試共同呼叫新 helper 後宣稱相等。 |
| Temporary mechanisms | `TMP-REC-06` 的隔離新舊比較 harness；只讀同一固定輸入，副作用使用隔離 fixture，禁止正式雙寫。 |
| Deletion / cleanup | Block 5 caller 切換與相容驗收通過後刪除臨時 harness 接線；保留固定 fixtures 與回歸測試。此 block 不刪 API、資料或 decoder。 |
| Expected end-state | 每個待動責任有 owner、caller、基線、已知失敗、回滾接點及證據位置；未覆蓋範圍明示，不宣稱全庫相容。 |

### 必須核實的 caller 起點

| 目前檔案／symbol | 必須辨識的責任 |
|---|---|
| `app_module/recommendation_service.py::RecommendationService.run_recommendation` | list 回傳、`last_*`、result identity、calibration projection receipt 的發生時間。 |
| `ui_qt/views/recommendation/execution_coordinator.py`、`recommendation_view.py::_on_recommendation_finished` | worker 結果與 request correlation；以當次原始碼核實 callback symbol，不只查直接 imports。 |
| `ui_qt/views/recommendation_view.py::_build_current_result_snapshot`、`_save_recommendation_result` | 未保存 Portfolio 來源與保存時重建 DTO、live service context 的使用點。 |
| `app_module/recommendation_save_coordinator.py::RecommendationSaveRequest.build_result/persist` | 保存時重新 detect regime、重新組合 profile、personalization binding 與 watchlist 後續結果。 |
| `scripts/scheduled/run_scheduled_recommendation_snapshot.py` | producer 呼叫、逐欄結果組裝、排程 identity 與保存；另查 wrapper 的字串式入口。 |
| `scripts/run_personalization_recommendation.py` | producer context、保存、exact readback、delivery ACK；保留原權限與發生順序。 |
| `app_module/recommendation_replay_service.py::RecommendationReplayService.run_snapshot`、`recommendation_dataframe_provider.py::RecommendationDataFrameProvider.__call__` | replay 簡化 dict 與獨立篩選／計分／排序，不能把它誤當成只有日期不同的互動 caller。 |
| `app_module/recommendation_repository.py::RecommendationRepository.save_result/save_result_create_only/load_result` | ordinary replace 與 create-only 的不同語意、file/index 恢復及回讀。 |

以上是清冊起點，**不是全庫 caller 已查完的宣告**。實作時必須補上測試、runtime、scheduler、re-export、函式內 import、可觀察到的動態／字串入口與外部支援契約。各 caller 記錄實際 symbol／mode／writer 權限／遷移 block，不能只登錄 package。

ML 清冊至少包含 feature／label registry、historical matrix、OOC／Direct numeric store、dtype／endianness／mask／scale／row key、fold refs、checkpoint／carry、model manifest／qualified class path、fitted transform、projection receipt 與 computation dependencies。程式常數清單不是磁碟 artifact inventory；移轉前只在已授權範圍核對實際 manifest／bytes hash，未知值保留 unknown。詳見 [ML 相容契約](FINAL_ML_COMPATIBILITY_CONTRACT.md)。

## 3. Block 2：先固定 typed schema、codec 與完整 capture

| 必填項目 | 執行要求 |
|---|---|
| Objective | 建立唯一推薦欄位 owner 與完整執行結果，使後續抽離不再依賴破碎 DTO 或逐欄搬運。 |
| Affected area | `decision_module/recommendation/contracts.py`、`app_module/recommendation/contracts.py`／`codec.py`／`execute.py`；既有 DTO 相容入口及最小 capture。 |
| Prerequisites | Block 1 的 caller、時序與數值 oracle；ML 凍結與 hash-sensitive 路徑已標記。 |
| Preserve | 現有 evaluator、score、排序、source policy 與 ML producer 不改；result ID 在執行前配置，projection、執行與保存沿用同一 ID。既有字典／中文 JSON 欄位仍可解碼。 |
| Validation | 新舊格式 round-trip、所有已知欄位保存、不支援型別拒絕、optional scalar 自動序列化、None 與 0 分離；巢狀不可變與原輸入 alias 修改測試；completed-empty／failed／cancelled 的 identity 與事件不混淆。 |
| Temporary mechanisms | `TMP-REC-01`（原始設計曾把 private body 與 invocation capture 合併列管；2026-09-24 依已驗收責任拆分，現僅指 legacy latest-state/matrix→canonical **rule** DecisionBatch／assessment／item／rule-context bridge）、`TMP-REC-02` list/latest-state 與 v1 event/callback compatibility outputs、`TMP-REC-05` 非序列化用途的舊 DTO import 相容。全部使用同一計算結果，不新增第二套 engine。 |
| Deletion / cleanup | R019 依 C3B／C3C2／C3C3 及 parity evidence 關閉 `TMP-REC-01` 的窄 rule bridge；這不刪 app 內私有 source-orchestration body，也不移除 invocation capture。clocks/error/progress 由 app execution telemetry 邊界列管；ML availability/projection receipt 仍由 capture 提供，歸 `TMP-ML-01`／R026 管理。`TMP-REC-02/05` 按退休帳各自退出條件，在 caller 完成切換與支援期結束後刪除。 |
| Expected end-state | 新的完整 execution 可獨立保存／重讀；新增符合契約的 typed optional scalar 自動進入 codec，尚未宣稱所有 caller 已切換或 domain 已無 I/O。 |

具體契約落點：

- `decision_module/recommendation/contracts.py::RecommendationItem` 擁有規則分數、理由、因子與可選 confidence；`CandidateAssessment` 擁有各候選篩選結果。兩者不含 storage、Qt 或 ML 模型 schema。
- `app_module/recommendation/contracts.py` 擁有 request、context 與 `RecommendationExecution`：組合 `decision: DecisionBatch | None`，連同 quality、events、source refs 與 ML projection refs；items、assessments、regime 保留在同一 DecisionBatch，不複製第二份。既有 ML 欄位仍由 ML 契約定義，不在此抄出第二套 ML schema。
- 使用 `frozen=True` dataclass、tuple；mapping 必須先遞迴複製其 keys／values，再以 `MappingProxyType` 封裝。直接包住原 dict 仍會共享可變來源，屬驗收失敗。拒絕 DataFrame、connection、logger、callback 等進入 persisted aggregate。
- `app_module/recommendation/codec.py` 是唯一 typed、schema-driven codec。它沿已登錄 dataclass 欄位與明確支援的有限型別遞迴編解碼，只有一份 schema；新 optional scalar 使用契約 default，無須在 codec 新增逐欄名單。新 artifact 的 schema revision 必須可辨識，舊 reader 遇到不支援 revision 拒絕完整 decode，不能丟欄後重存。版本 dispatch、legacy alias、Decimal／時間／enum／typed reference 的轉換仍集中此處；不以 `extended_attributes` 或任意 `dict[str, Any]` 規避型別。
- 最小 capture 必須在該 invocation 返回 worker 之前完成。若既有 engine 尚寫 `last_*`，只能使用 invocation 專屬實例，或保護「執行直到 capture 完成」的同一序列化區間；capture 之後不再讀 live 狀態。無法證明取消／例外時 partial state 歸屬時，不發布可採用推薦。

過渡呼叫方向固定為「舊 public list façade → 新 execute → 私有 app source-orchestration body／capture → execution → list 投影」。抽出的私有 body 保留 source preparation／orchestration 與尚未搬移的 I/O，不保留第二份 rule evaluator；不能再呼叫 public façade。新 execute 不可呼叫已改為委派 execute 的 `run_recommendation`，否則形成遞迴。R019 已關閉的是 legacy state/matrix 到 canonical rule result 的重建橋接；不代表私有 body 或 execution capture 整體移除。仍讀 last_* 的舊 caller 只能取得此次 façade 的投影，不能讓共用 service latest state 再成為 canonical rule result 的輸入。

**Scope supersession（2026-09-24）**：原始 Block 2／Block 4 草案把 `TMP-REC-01` 寫成整個 private body 與 execution capture 的暫時機制，並預期 R019 直接組裝 execution 後一併刪除。C3B／C3C2／C3C3 parity 後，該帳目縮窄為 rule DecisionBatch、assessment、item 與 rule-context 的 legacy state/matrix bridge；私有 body 留作 app source orchestration。invocation clocks/error/progress 仍由 capture 提供並由 app execution telemetry 邊界列管；ML availability/projection receipt 仍由 capture 提供，歸 `TMP-ML-01`／R026 管理。此修訂分清 canonical rule output 與 execution telemetry 責任，不宣稱完整 Context／ML 已不讀 capture。

舊浮點分數在相容邊界保留原語意，不因新的 typed dataclass 就更換計算精度、四捨五入或零值預設。新 confidence 使用主 SSOT 的整數 bp／明確缺值契約；對既有數值格式的改造另行驗證。

## 4. Block 3：遷移完整 execution 的所有使用者

| 必填項目 | 執行要求 |
|---|---|
| Objective | UI、CLI、保存、重播與查詢沿同一 execution 傳遞資料，停止在消費端重建業務結果。 |
| Affected area | 上述 caller 清冊；`app_module/recommendation/save.py`／`queries.py`／`ports.py`／`persistence.py`；`data_module/result_artifact_store.py`。 |
| Prerequisites | Block 2 codec／immutability／terminal outcome 驗收通過；每一保存 caller 的權限與明示保存時點已固定。 |
| Preserve | 使用者明示保存、原 CLI／scheduler 已授權保存政策、exact projection identity、watchlist soft failure 與 personalization ACK 狀態分離；不增加自動交易、訓練或資料更新。 |
| Validation | A 完成→B 執行→保存 A；來源與 regime 改變後保存 A；重試同 ID 同 hash、同 ID 異 hash 拒絕、file 成功/index 失敗及反向不一致；UI stale callback／取消／關閉；CLI exact readback 與 ACK 失敗後不重算。 |
| Temporary mechanisms | `TMP-REC-03` 保存 caller adapter、`TMP-REC-04` replay provider parity boundary；concrete provider typed handoff 已接線，generic v1 row→canonical child builder 已移除；尚未遷移 caller 才可使用 `TMP-REC-02`。 |
| Deletion / cleanup | 已切換 caller 當個切片就刪除以 live `last_*`／DTO 重建 canonical rule result 的讀取與 builder；clocks/error/progress 的 app execution telemetry capture、ML availability/projection receipt capture 依各自 owner/TMP 留存。`TMP-REC-03` 在最後一個保存 caller 切換後刪除；`TMP-REC-04` 的 19-row app early gate 已接 evaluator count-only minimum-history preflight 並 bounded accepted；blank-code active-filter compatibility terminal slice 依 R023 frozen 156P 獨立 review（無 P1/P2）bounded accepted。完整 typed identity 與 full replay parity 通過後才可刪除 TMP-REC-04。Generic v1 row→canonical child builder 已移除，單獨移除此 builder 不代表 TMP-REC-04 退出。 |
| Expected end-state | canonical result 的保存／查詢及 UI 不依賴 service latest-state；app 可按明示 execution telemetry 契約保留 invocation capture。每個 replay 日期有完整 child execution，外層 replay summary 引用它並保留 `RecommendationSnapshotDTO.recommendations` v1 list live compatibility projection（現存 portfolio／factor-manifest consumers 仍使用）；移除的是重複的內部 DataFrame row-dict engine／bridge，不是外層相容輸出。 |

保存的唯一新路徑為 `save.py` → `ports.py` → `persistence.py` → `data_module/result_artifact_store.py`。後者只接受 bytes、hash 與 index metadata，不 import app DTO；承接現有 JSON artifact／SQLite index 機制，不建立 generic repository framework。新 API 採 create-only／同 identity 與 payload hash 冪等保存；普通 legacy replace 不得成為新 API 的隱藏 fallback。結果 hash、annotation 與 receipt 分工依主 SSOT，不由 repository 改寫 execution。

`queries.py` 以 exact result identity 讀同一 artifact，經唯一 codec 驗證後回傳。label、notes、persisted_at 或 delivery outcome 不得透過重新執行推薦來取得。watchlist／ACK／journal 以明示後續 command 處理；主結果成功而後續 command 失敗，須能獨立重試及辨識。

`RecommendationSaveRequest._regime_snapshot()` 的再次偵測在此 block 移除。新的保存行為只保存原 execution regime；舊資料缺執行時 snapshot 時標 unknown，不能查詢今天的市場替歷史補值。這是明列的執行一致性修正，須保存 before／after fixture，不能泛稱所有舊 bug 都維持。

Replay 的 concrete provider 以同次 scorer outcomes 建立 canonical child；custom／legacy provider 只保留 v1 rows 與 transient parent，不再由 generic row-dict builder 補造 canonical child。`TMP-REC-04` 中 19-row app early gate 已以 count-only preflight 接 evaluator 並 bounded accepted；blank-code compatibility terminal slice 已 bounded accepted，完整 replay parity 仍待收口，原互動與歷史模式的選取差異仍需保留。統一容器不代表此時已統一算法，也不授權將 replay 靜默改成互動規則。

## 5. Block 4：抽離 I/O、計算與 domain 責任

| 必填項目 | 執行要求 |
|---|---|
| Objective | 在穩定契約上形成可無 I/O 執行的決策能力，保留單一有效 evaluator 與各模式明示 policy。 |
| Affected area | data source/read/storage、analysis calculator、decision recommendation／factors／strategies／market、app execute／composition；ML 凍結區排除。 |
| Prerequisites | Block 3 主要 caller 接完整 execution；Block 1 已核實 interactive／replay policy 差異及 ML dependency inventory。 |
| Preserve | 原來源優先序、cutoff／available_at、window／warmup、filter 次序、weights、rounding、rank／tie-break、universe／candidate limit、regime cooldown／history、historical mode 與 execution timing。 |
| Validation | fake provider／禁止 DB、HTTP、檔案 I/O 的 domain 測試；各模式分別對原 oracle 比較；多日 regime／同日重跑；日期 `YYYYMMDD` parser；來源 fallback 及 missing/degraded；既有 ML gate、source fingerprint／receipt identity 不變。 |
| Temporary mechanisms | `TMP-REC-01` 的窄 rule bridge 依 R019 C3B／C3C2／C3C3 與 parity evidence 已 `CLOSED`；R019 不退役 app private source-orchestration body 或 execution capture。`TMP-REC-04` 仍依其 replay engine 條件退役；必要舊公開入口暫留 `TMP-REC-02/05`。`TMP-NUM-01`、`TMP-ML-01/02` 保持具名列管，hash-sensitive 移動維持凍結，不以臨時假 hash adapter 通過驗收。 |
| Deletion / cleanup | 每條責任鏈完成 parity 後刪除已被替代的 pure rule body／重複 mapping／隱式 default provider constructor；保留仍承擔 source orchestration 的 app private body，以及 clocks/error/progress 所需的 app execution telemetry capture。ML availability/projection receipt 所需 capture 依 `TMP-ML-01`／R026 驗收。不得刪掉尚有 caller 的入口。 |
| Expected end-state | data 解碼 vendor、analysis 計算、decision 解釋 facts 與選取、app 組合依賴和執行；互動與 replay 使用同一 evaluator，但以明示政策保留原行為差異。 |

Factor ownership 按最終裁決處理：來源欄名／日期／unit 解碼位於 data；標準 facts→factor 的語意轉換及因子公式位於 `decision_module/factors/`，application 只準備標準 facts 與選擇已宣告 policy。禁止在 `app_module/adapters/factors` 維持第二份 factor 解釋，也禁止 decision 為了取得欄位而直接查 vendor API／DB。

先抽已存在且有證據的 seam，例如 screener reader、ranking、regime state I/O、composition 建構；純計算直接呼叫，不為每個 helper 新增 Protocol／factory。重構之前與之後都用同一模式對其原 oracle 驗證，不能把 interactive 結果當 replay 的既有真值。若兩模式需要不同篩選或 candidate policy，由同一 evaluator 的明示政策選擇表達，不保留兩份編排／計分實作。

Regime 的 prior state 與 transition 必須顯式輸入／輸出；保持原 state file、更新時點、confirmation／cooldown 語意，不能靠移除檔案 I/O 讓每次計算回到空狀態。

`app_module/recommendation/ml_adapter.py` 是目標系統的永久邊界，不是待刪 package。只有其中初期呼叫 frozen builder／原 provider 並保留舊讀取時序的分支屬 `TMP-ML-01`；它在明示 preparation→`PreparedMLInput`→projection 的相容驗收完成後退出。Rule 與 ML 的輸入版本須分別記錄、對齊 decision-time 與 result/candidate identity，不因來自同一 DB 就宣稱相同 snapshot。

### 獨立實驗：technical publication 搬移

`UpdateService.calculate_technical_indicators` 搬至 app job 的安全性狀態為 **NEEDS IMPLEMENTATION EXPERIMENT**；本輪未執行。它不是 Block 4 的預設搬檔工作，也不能為了目錄整齊先動再補證據。

在隔離工作區以固定小型資料比較搬移前後：`_DIRECT_COMPUTATION_DEPENDENCY_RELATIVE_PATHS` 的精確依賴、原 computation fingerprint、feature materialization／publication 時點、writer 呼叫次序、checkpoint resume 接受／拒絕、既有 numeric output。需讀取實際依賴而非只比函式名字；呼叫方／間接來源也可能影響 hash 或時間。

未證明不影響前，保留原路徑與實作；可先完成不觸碰該 frozen source 的其他責任切片。若實驗證明 computation identity 改變，必須另行規劃新 identity／artifact 及原 checkpoint 處置，不能重寫 path 清單、重新 hash 後冒稱舊身份等價，亦不能將「接受新 hash」視為舊 resume 相容。

## 6. Block 5：退休 runtime 相容、enforce 邊界與擴充驗收

| 必填項目 | 執行要求 |
|---|---|
| Objective | 收斂為一套有效執行架構，證明常見變更不再要求修改無關 transport／persistence。 |
| Affected area | 暫時 façades／bridges、caller／import guards、composition、回歸測試、開發導航與實際變動功能的 Manual。 |
| Prerequisites | Blocks 1–4 的每模式 parity、完整執行與保存 readback 通過；所有已知 direct／dynamic caller 和外部支援契約已核實。 |
| Preserve | 歷史 artifacts、永久版本 decoder、必要 joblib／pickle qualified-name alias、原 ML gate／quarantine／權限及原金融數值語意。 |
| Validation | 全部退休帳退出條件、狹義 dependency guards、三項 change-impact 演練、舊格式讀取、取消／交錯／恢復整合及 rollback；已知 baseline guard residual 不得用整包 allowlist 消失。 |
| Temporary mechanisms | 只允許退休帳仍有未滿退出條件的項目；每項需有 owner、剩餘 caller 與具體 blocker，不能宣稱完整 runtime 收口。 |
| Deletion / cleanup | 刪除無 caller 的 runtime adapter、逐欄 mapper、舊 engine body、臨時雙路比較接線；保留獨立 fixtures。永久歷史 decoder 與序列化 alias 不列必刪清單。 |
| Expected end-state | 新開發沿 final 文件即可定位 owner；無跨 run 的業務 `last_*` 依賴；canonical item 自動保存；domain 無未列管 I/O；ML 凍結例外清楚且不被誤報為完成重構。 |

三項驗收以 [FINAL_EXTENSIBILITY_MODEL.md](FINAL_EXTENSIBILITY_MODEL.md) 的具體落點為準：

1. **confidence_score**：typed owner／固定 contract header revision 宣告／calculator／指定 presentation；歷史保存自動包含 scalar，不改 codec 欄位名單、save、execute、replay 或 DB index。若未來 ML 使用，再新增明示 opt-in 的 versioned feature binding；本次輸出新增不觸發舊 dataset／模型修改。
2. **新完整策略**：策略 spec／executor／既有 registry 與必要參數呈現；既有 signal→backtest 契約不變，不修改推薦傳輸、repository 或撮合 engine。
3. **新 technical feature**：calculator／feature 定義及必要的新版本 publication／模型綁定；舊 registry hash、矩陣順序、numeric bytes、transform、model 與 checkpoint 保持原樣。新資料不得以欄位名相同冒稱舊資料相容。

文件中的上述走查是設計檢驗；實作完成後仍須以隔離 fixture 證明。若 confidence 仍需在多個 coordinator 複製欄位、若策略另起 backtest、或新 feature 要改舊 binary 才能工作，對應 block 不得判定完成。

## 7. 暫時機制退休帳

| ID | 暫時機制與具體 caller | Owner | 引入／最晚收口 | 刪除條件與必要證據 |
|---|---|---|---|---|
| `TMP-REC-01` | **CLOSED（R019 bounded scope，2026-09-24）**。原始／已 supersede 定義涵蓋從舊 `run_recommendation` 抽出的私有 body 與整體 invocation capture。現行退休範圍縮窄為 legacy latest-state/matrix → canonical **rule** DecisionBatch／assessment／item／rule-context bridge；C3B／C3C2／C3C3 與 parity evidence 已驗收。app private body 保留 source orchestration；clocks/error/progress capture 由 app execution telemetry 邊界列管，ML availability/projection receipt capture 歸 `TMP-ML-01`／R026。 | app recommendation rule bridge | Block 2／Block 4 | 已證明 canonical rule outputs 直接來自同 invocation typed evaluator result，而不是 `last_*`／legacy matrix 重建；execute/body/capture identity parity 通過。此 CLOSED 不代表刪除 private body、`_r011_invocation_capture` 或完整 execution capture。 |
| `TMP-REC-02` | **ACTIVE（聯合退出）**。原始範圍為 `RecommendationService.run_recommendation() -> list` 相容 façade；2026-09-24 擴明列管 service list/latest-state 輸出與 v1 event/callback sidecar。服務清冊仍有待切換的 Qt、scheduled／personalization CLI 與已知外部 caller。 | app recommendation compatibility | Block 2／Block 5 | **兩個獨立子條件均完成後才能關閉整項：** (1) 所有 direct/dynamic/string/scheduler/UI/CLI caller 切離 list/latest-state facade，外部支援期結束，caller inventory／smoke 通過；(2) v1 event/callback sidecar 的 consumer inventory 完成、consumer 改接 typed execution/read model 並通過 parity，再移除 sidecar。任一條件未完成，REC-02 維持 ACTIVE。歷史 artifact/JSON decoder 是永久 read compatibility，不是此項退出或刪除目標。 |
| `TMP-REC-03` | **已退休（R015）**：已移除 `RecommendationSaveRequest.build_result/persist` 舊呼叫形狀 coordinator；Qt、scheduled、personalization 新 producer 均保存 sealed execution | app recommendation persistence | Block 3／Block 3 | R013 Qt manual 與 R014 scheduled callers 已接 frozen execution，R015 personalization CLI 完成同次 capture → create-only save → exact canonical readback → 延後 Journal CAS ACK；`recommendation_save_coordinator.py` 與純 API mirror test 已移除，runtime/import/QA/Manual coordinator 名稱搜尋零命中。personalization legacy JSON exact retry 仍只讀原 artifact 並保留既有 DTO/run_context decoder 相容，不重寫舊 bytes。詳見 `REFACTOR_REPORTS/R015_IMPLEMENTATION_REPORT.md`。 |
| `TMP-REC-04` | `RecommendationReplayService.run_snapshot` 的 replay provider parity boundary。R023 已移除 generic v1 row→canonical child builder；concrete provider 以 typed scorer outcome 產生 child，custom／legacy provider 只保留 v1 rows＋transient parent、canonical child 為 `None`。`<20` rows 已呼叫 evaluator count-only minimum-history preflight，該 bounded slice 已獨立 accepted；reject 不代表 CandidateAssessment。blank `stock_code` + active filters 使用 compatibility-only observations/key、共用 pure evaluator，且 scorer success／empty／exception／projection exception 均有 request-bound noncanonical terminal 與 call-local audit；canonical `scoring_outcomes` 仍為 `None` 且無 child；R023 frozen SHA 獨立 review 的 156P route 無 P1/P2，blank compatibility terminal slice bounded accepted | app research／recommendation | Block 3／Block 4 | 19-row／blank-code slices 各自 bounded accepted；兩者皆不具 canonical Assessment/child。完整 V-REPLAY／R005 replay policy parity 通過後才可退休。保留外層 `RecommendationSnapshotDTO.recommendations` v1 list projection 及既有 portfolio／factor-manifest consumers 為 live compatibility output。 |
| `TMP-REC-05` | `app_module/dtos/__init__.py` 中僅為 source import 相容留下的 recommendation re-export／薄 wrapper；caller 由 Block 1 inventory 逐項列出 | recommendation contract owner | Block 2／Block 5，受外部支援期約束 | source caller 全切換且支援期結束、確認無已留存序列化物依賴後刪除。若 qualified path 確為 joblib／pickle 所需，改列永久相容記錄，不強制刪除。 |
| `TMP-REC-06` | 實作測試中的 legacy/new 隔離雙路比較 harness，使用 Block 1 固定輸入與各自隔離 side effects；不對正式 UI／scheduler 暴露第二 engine | 測試／推薦 owner | Block 1／Block 5 | 所有模式 parity 與 caller cutover 完成後移除臨時執行選擇，保留 fixtures／預期輸出／單一路徑 regression。 |
| `TMP-STR-01` | 暫留 source compatibility facade：`app_module.strategy_spec`、`app_module.daily_signal`、`app_module.strategy_registry`、`app_module.strategies`（含三個舊 executor 子模組）、`app_module.strategy_executor_adapter.SimpleStrategyExecutor` 與 `app_module.reason_tags.ReasonTagGenerator`；所有實作與唯一 mutable registry 均委派到 `decision_module.strategies`／`decision_module.reason_tags`，不複製 body 或重複註冊。**現況（R025，2026-09-23）：ACTIVE；新 owner 與舊 alias parity 已完成，R029 retirement evidence 尚未完成。** | decision strategies owner；app compatibility facade | R025／最晚 R029 | R029 完成 direct/dynamic/string/external source caller 清查且支援期結束後，逐個舊 qualified source path 移除 facade；若發現已留存 serialized artifact 明確依賴某 class path，先將該 alias 從 TMP 列拆為永久相容項，保留其 exact deserialize test，再只移除其餘 aliases。R025 目前 repo JSON/YAML inventory 僅證實保存 strategy ID/spec fields，未證實有保存 executor class path；不把此 source facade 宣稱為永久 artifact alias。 |
| `TMP-NUM-01` | `RecommendationService.run_recommendation`、`RecommendationDataFrameProvider.__call__` 與 `RecommendationDTO` 的既有浮點分數／row dict 到 canonical contract 邊界 | decision recommendation／app codec | Block 2／獨立 numeric 驗證 gate | 先以原 precision／rounding／tie-break 證明 typed 封裝與原結果等價；以十進位字串保存既有值不得量化為 bp。generic row-dict→canonical child bridge 已隨 R020 移除；仍需保留的浮點算法與 v1 projection 邊界，只有獨立數值改造的同值／相容測試與 caller 切換通過才刪 legacy 分支。ML／NumPy 的合法浮點矩陣不是此項待刪對象。 |
| `TMP-ML-01` | `ml_adapter.py` 內呼叫 frozen legacy 讀取的分支；此外，R019 後 `app_module/recommendation/execute.py` 的 MLAvailability／projection-receipt 組裝仍讀 invocation capture／legacy context，尚未完成 explicit prepared-input cutover；對照 `RecommendationService._apply_recommendation_calibration` → `MLHistoricalSnapshotProvider.load` → `HistoricalFeatureBuilder.compute` | app recommendation／ML compatibility；R026 負責 preparation、execute 接線與退出證據 | Block 2／獨立 ML preparation 相容 gate | **ACTIVE，直到 R026 提供並通過退出證據。** 明示 preparation 產生 `PreparedMLInput`，移除上述 MLAvailability／receipt projection 對 invocation capture／legacy context 的讀取；驗證來源版本／可得時點／feature 值與順序、模型輸出、receipt identity、更新競爭與 unavailable fallback。永久 `ml_adapter.py` 保留，不能為退休強改凍結 builder。 |
| `TMP-ML-02` | `portfolio_ml_direct_numeric_store.py::_DIRECT_COMPUTATION_DEPENDENCY_RELATIVE_PATHS` 及其列明的 assembler／OOC／teacher 等 source-path 凍結例外；含可能改變 materialization 時序的 `UpdateService.calculate_technical_indicators` 搬移限制 | data numeric store／ML／update job owner | Block 1／獨立 computation identity gate | 依 ML 分冊完成精確 caller／source inventory 與隔離 hash／bytes／timing／resume 實驗；證明透明相容或明示建立新 identity／run 並決定舊 checkpoint 處置後，才刪舊 runtime 接線及 source-path 例外。不能改寫原 hash 偽造等價，舊 artifact reader／必要 class alias 保留。**現況（R027，2026-09-23，R023 source freeze 後重跑）：TMP-ML-02=ACTIVE、R027=INCONCLUSIVE、AB-ML-01=OPEN、R028=BLOCKED。** Full receipt SHA256 `4fe75c19e16e7bd241108638813f5ba5d89235cdc884dff224f337a8c9847616`，17,045,681 bytes：8/8 情境、16/16 worker return code 0、15/15 ordered Direct paths、semantic differences=0、4/4 negative controls，仍有 848 個 exact timing／snapshot 差異。Candidate extraction、16 個 worker 結束時 UpdateService source SHA 與 projection-time source SHA 均為 `df1d04445f23ff07f2eb45eab7b024b819ba511928b8cc2d25ee3bc3c69dae88`；摘要 `run.head` `777c06d039a7676475f7f6eecebf9a24bb790692` 僅為 projection-time metadata，full receipt 不證明 worker-time HEAD。此 receipt supersedes source SHA `dbf18eaf…` 的 pre-freeze receipt。詳見 [R027 QA 報告](../../06_qa/R027_TECHNICAL_PUBLICATION_ML_IDENTITY_ISOLATION_20260923.md)。 |

| `TMP-RGM-01` | `RecommendationService.__init__` 未注入 `regime_service` 時建立 persistent service 的 fallback、舊 `regime_detector` adapter、`detect_regime`／`get_strategy_config_for_regime` wrappers，以及測試／QA fake detector seam；目前已知 production UI、composition、personalization、scheduled callers 明示共用／注入 RegimeService | app regime／application composition | R022／最晚 R029 | **現況（R022，2026-09-23）：ACTIVE；R022 bounded gate 已 `ACCEPTED_SCOPE`。** R029／Block 5 完成 direct、dynamic、scheduler、CLI 及 external source caller 清查、支援期結束，所有 active producer 明示注入同一 RegimeService 並以 identity／多日／source-failure 測試通過後，逐步移除 fallback、舊 detector adapter 與 source compatibility wrappers。此項是暫時 source API，不宣稱存在 serialized artifact alias。2026-09-24 Wave 7–10 至 R020 checkpoint 僅釋出 R020 bounded implementation；未宣告 Wave 7–10 full closeout／C2，R027 仍 `INCONCLUSIVE`、`AB-ML-01` OPEN，R028 BLOCKED。詳見 [R022 實作報告](REFACTOR_REPORTS/R022_IMPLEMENTATION_REPORT.md) 與 [checkpoint 報告](REFACTOR_REPORTS/WAVE7_10_R020_BOUNDED_RELEASE_CHECKPOINT_20260924.md)。 |

**2026-09-24 R020 progress update（較早狀態快照；Stage D／recovery 狀態由下方後續 receipts 更新）**：provider 的 typed scorer outcome→canonical child handoff、invocation parent 與 Registry `run_id` 分離、R012 create-only child artifact、versioned lineage sidecar 與 Registry manifest staging/readback 已有 bounded synthetic evidence。缺 child 時保存 v1 Registry result 並標記 lineage `unavailable`；v1 recommendation list 與 legacy portfolio JSON／decoder 不變。2-child UI→R012→Registry synthetic readback 已驗 child bytes並驗證損毀 child 時整批 fail-closed。先前五檔 cross-store recovery route `77 passed／4 skipped`（`tests/test_r020_cross_store_recovery.py` SHA-256 `9A72105242CF2DBD55E16DC9F40D8B93EF5419CC50C64C4ACD487DDFDE11FEA6`）保留為歷史證據，涵蓋 child2 failure/retry、Registry staging/files_ready reconcile 與 post-commit corruption fail-closed。Generic v1 row→canonical child builder 已移除，custom／legacy provider 只保留 v1 rows＋transient parent、canonical child 為 `None`。本輪 `<20` count-only preflight 與 blank-code compatibility scorer lifecycle 各有 bounded acceptance；詳細 R005/R020 evidence 見實作報告。Stage C 完整 DTO readback 已 bounded accepted；該較早快照記錄 Stage D Registry 專屬 UI「待獨立 review」及 process-crash／child-missing recovery「仍缺」；兩項後續狀態已由下方獨立 receipts 更新。Full V-REPLAY parity 仍待驗。legacy history dropdown 維持只列舊 repository records。`TMP-REC-04`、`TMP-NUM-01`、C2 仍未結案，R020 維持 `IN_PROGRESS`。

**2026-09-24 R020 blank-code lifecycle update**：此更新取代前段 151P receipt 對 blank scorer terminal 的描述；fresh TEMP 12-file R005/R020 route 為 156P，mypy 3 source files／0，py_compile 與 source/test whitespace check 通過。R023 對 frozen provider/evaluator/test SHA 的獨立 review 無 P1/P2，blank-code compatibility terminal slice bounded accepted。`NeedCompatibilityScoring` 的成功、empty、scorer exception、row projection exception 現由同 evaluator 以 identity-bound noncanonical terminal 關閉，並提供不進 SnapshotDTO／child／保存 bytes 的 call-local audit tuple；v1 rows 與 canonical `scoring_outcomes=None` 不變。`<20` count-only preflight 亦為獨立 bounded accepted；兩者均不產生 canonical assessment／child，完整 V-REPLAY parity 未完成。legacy history dropdown 依 R020 scope addendum D 刻意只列舊 repository records；`tests/test_r020_ui_replay_lineage_save.py` 的 Registry save exclusion 是隔離回歸條件，不是待新增／合併功能。此較早更新當時記錄 Stage D 新入口「待獨立 review」；其後狀態由下方最新 UI／Stage C/B2 route receipt 取代。`TMP-REC-04`、`TMP-NUM-01`、C2 繼續 ACTIVE，R020 維持 `IN_PROGRESS`。

**2026-09-24 scope update**：經 R019 C3B／C3C2／C3C3 bounded acceptance 與 parity 證據，將 TMP-REC-01 從「整體 private body/capture」縮窄並標示 rule bridge CLOSED；將 list/latest-state 與 v1 event/callback sidecar 分列為聯合 ACTIVE 的 TMP-REC-02 兩個退出子條件。保留 app source orchestration、invocation telemetry capture、永久歷史 decoder，避免把 R019 接受誤讀成全 capture 移除。

**2026-09-24 R020 portfolio Registry latest gate update**：Stage A codec、Stage B1 repository CAS、Stage B2 Registry publish、Stage C strict DTO/child reader 與 Stage D Registry UI/Manual 各自 bounded `ACCEPTED_SCOPE`。B2 先前 accepted source receipt 為 service/repository/tests SHA `18CE2A329A1F8092EAC4BD280E536D24E08060476B04CBE57D03BEE67D91E7B8`／`8AA0454D124615B0CD783C83826A678A04CCD54BC47740571E825446729AE503`／`BDFA08912679D2053F14187C889866A77BB0B61B4B7BC1CE2AF723BFBA0D8827`、103P/1S；其後 B2 guard 更新至 service `DC47816C62D1249629B2CE6303608B52503E3735882EAD74A68C75AF7D7B00CF`、repository `8AA0454D124615B0CD783C83826A678A04CCD54BC47740571E825446729AE503`、tests `CA18D12AF9F483C8302BF3C146D915B272BE42E79AED4A81C88AE9BE46B6D1C1`，已由 R015 獨立 bounded `ACCEPTED_SCOPE`：fresh TEMP non-UI route 70P、mypy 0／compile 通過。Stage C reader/tests SHA 為 `812ED626377812F53650EBDEA0E587A036AC6BED80E060CF532B085E18ADFACB`／`1C5E68904A4956C9416EE99B2986EABD78C36752A9C7C4C193462832EA02D124`，獨立 14P、交叉 79P/1S。Stage D BacktestView save/open 與 Manual/UI docs 已同步，由 R023 獨立 bounded `ACCEPTED_SCOPE`：7-file fresh TEMP route 95P、Workbench 84P、broad mypy 712 files/0、compile/diff-check 通過。Update QA 分別為 R027 25P/0F/4S exit 0，以及 R023 25P/1F/4S；後者唯一失敗是 WinError32 TEMP SQLite teardown，非功能 assertion，不計 reviewer pass。Registry 單選 open 不污染 legacy dropdown、只接受同次 typed DTO、嚴格讀回並不抓目前 benchmark；有推薦 snapshots 但無 child 時保留推薦列，零 snapshots 則不發布空 lineage sidecar、以 parent-bound `unavailable` 讀回空 DTO並明示沒有 snapshots／canonical child 不可用。BacktestView 先寫有可驗 child 的 R012 artifacts 再呼叫 B2，後續 Registry metadata validation 若失敗可能留下同 ID 可重試的 child。Process-crash／missing-child recovery 有限度 evidence 見下方獨立 receipt；完整 recovery gate 與完整 V-REPLAY parity 尚未通過。顯式 `reconcile_incomplete_saves` 僅能在 writers quiescent 時執行。此狀態更新取代本節較早 progress rows 的 Stage D「待獨立 review」狀態。R020 為 `IN_PROGRESS`，`TMP-REC-04`／`TMP-NUM-01` 為 `ACTIVE`，C2 未放行，R028 維持 `BLOCKED`。

**2026-09-24 R020 same-mode fixed-vector parity receipt**：R023 獨立 bounded `ACCEPTED_SCOPE` `tests/test_r020_concrete_portfolio_parity.py` SHA-256 `9A274320B298C6C4BE659FD35A607187E9A455556FDF4CA453ADD872F66F8BC1`；fresh TEMP 16-file R005／V-REPLAY／R020 route `211P`、24 個既有 warnings，scoped mypy 4 files／0 issues、compile 通過。此 gate 固定 scorer/reason 與 synthetic vectors，不代表完整 V-REPLAY corpus 或所有 caller/mode parity；`TMP-REC-04`、`TMP-NUM-01`、C2 與 R020 overall completion 均未解除。

**2026-09-24 R020 process-crash／missing-child bounded receipt**：R015 frozen `tests/test_r020_process_crash_recovery.py` SHA-256 `07C2A71B44CB5A3462D0A800FE7EE9F793A6CFA19A487CE7846681352AF39C63`；R027 獨立 fresh TEMP 7-file route `142P/3S`、scoped mypy `7 files/0 issues`、py_compile 通過。精確為 **3 個 `spawn`／`os._exit` 真正 crash 點**（child artifact 發布後／index 前、所有 children 完成後／Registry save 前、Registry `files_ready` CAS 後／artifact publish 前）＋ **1 個 committed child 缺檔情境**；第四情境不是 hard-exit。child 缺失時 strict readback fail closed，修復需明確重發同 hash 原 `RecommendationExecution`；同 ID／同 bytes 可重試，異 bytes 不覆寫。較早 R015 摘要若將四者稱為「四個硬退出窗口」，本次更正為三個 crash 點加一個缺檔負向／修復情境。此 bounded receipt 不關 full recovery gate：未覆蓋所有 partial-publish windows、R012／Registry 間共同原子交易或補償 rollback，也不會自動重建原 execution；reconcile 只能在 writers quiescent 後明確執行。R020 維持 `IN_PROGRESS`，`TMP-REC-04`／`TMP-NUM-01` 為 `ACTIVE`，C2 未放行，R028 維持 `BLOCKED`。

**2026-09-24 TMP-NUM-01 NumPy 1/2 follow-up**：R015 對 provider `app_module/recommendation_dataframe_provider.py` SHA-256 `F0B50C21D08D7867BE2B59D4F9B54D1A33C9E9CCD17A6788FAB2FDFBCDFC6630` 與 differential/C1b/provider-adapter frozen tests 給 `ACCEPTED_SCOPE`，無 P1/P2。NumPy 1.26.4 的 RankWarning 位於 `np.RankWarning`，不在 `np.exceptions.RankWarning`；舊 provider 在 scorer try 內取缺失屬性，導致候選被記為 scorer exception 並略過。現在先取 `np.exceptions.RankWarning`，缺席時才 lazy fallback 至 `np.RankWarning`，只忽略此警告類別。差異 test SHA `D792F2B4AED996474FA4086C20F8C7C4CD63891C9606B639C297262AF1B01157`、C1b runtime-native test SHA `F6954D4E19607304F4F8D5C4A4C9CAF923686A387A431D5171795B61A48739AF`、provider-adapter test SHA `568E73E4C6DF26959F3A331C668DECF630A85EF4C3ADEA9AEC510D05896908C2`；C1b vectors 改為各自比對同 runtime 的 legacy native operators，不假設跨版本數值相同。相同 15-file R005/R020 route 在 Windows NumPy 1.26.4／Pandas 2.3.3 與 NumPy 2.3.5／Pandas 2.3.3 各 `216P/1S`；獨立四檔 route（differential、C1b、provider staged adapter、scorer handoff）各 `58P/1S`，receipt log SHA 分別為 NP1 `CC719394E8C6B96818802B92C32F0EAEB532E0B792891CBBB0E26B91E318CB9D`、NP2 `7C479D5862F5C130539DB06D98DE3AEDB2110E5DA9590262005D811E17D63074`。NumPy1 full provider route 因 `fastdtw==0.3.4` sdist 缺 `longintrepr.h` 曾無法建立環境；後以 repo `.venv` 中已安裝純 Python 套件（逐項 RECORD hash 驗證）只複製到 TEMP profile，provenance JSON SHA `D5006DEE131E0552CA479AA66A4AC625A80B426D7A8C5DD27C17D29FA054EC74`，不改 repo environment／dependency declaration。此 bounded evidence 僅證明各 runtime 內與各自 native oracle 相符，不證明 NumPy 1 與 2 的結果相同或完整 R005/V-REPLAY parity。Windows `longdouble` 是 `<f8` alias；Linux／wider longdouble、其他 NumPy 1.x 版本與平台未驗。`TMP-NUM-01`、`TMP-REC-04` 仍 `ACTIVE`，R020 `IN_PROGRESS`、C2 未放行、R028 `BLOCKED`；詳見 [R020 report](REFACTOR_REPORTS/R020_IMPLEMENTATION_REPORT.md)。

永久相容能力另列：`codec.py` 的歷史版本 decoder、必要 artifact loader、已證實被留存模型引用的 qualified-name alias。它們只提供讀取／名稱解析，不能藏第二套 evaluator、trainer 或新 writer；不以「所有 adapter 都要刪」為理由破壞歷史資料。

不新增未登錄的 runtime adapter。若實作發現新的暫時路徑，必須先補上 ID、精確 caller、owner、退出 block 與可驗證刪除條件，再納入切片。

## 8. 驗證範圍、回滾與接手邊界

每個實作切片依變動範圍跑 focused tests、changed Python compile 與適用型態檢查。UI 修改還必須依 repo 規則執行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_ui_qt_update_view_workbench.py -q -o addopts=
.\.venv\Scripts\python.exe scripts\qa_validate_update_tab.py
.\.venv\Scripts\python.exe -m mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime
```

此外應跑實際受影響的 recommendation／save／replay／calibration caller 測試；前三項不能替代這些測試。ML 僅使用經授權的小型隔離 fixtures，正式 canary、大型重建、資料修復／回填、scheduler 實跑及 model promotion 不包含在本架構遷移授權中。

回滾以可驗證切片為單位：未發布新 wire 的切片可回復原接線；已發布新格式則先停止新 writer，保留新 reader 與 artifacts，禁止舊 replace writer 覆寫新結果。file/index 不一致依原 identity／hash 恢復，不能重新計算另一個結果冒充原保存。Additive schema 不做破壞性 drop，不刪正式原始資料或整個 output。任何結果偏離原 oracle，先保存差異並停止擴大該切片，再判定 regression 或另外核准的行為修正。

本文件原始交付時尚未實施上述 blocks，亦未執行 technical publication 搬移實驗；R027 隔離實驗後於 2026-09-23 執行，結果為 `INCONCLUSIVE`，狀態與證據見上方 `TMP-ML-02` row 及 [R027 QA 報告](../../06_qa/R027_TECHNICAL_PUBLICATION_ML_IDENTITY_ISOLATION_20260923.md)。production migration 仍未執行；本文件不以架構定義或實驗報告替代數值、資料、UI 或 ML 相容驗收。

## 更新記錄

- 2026-09-22：依紅隊裁決重排為五個 blocks；固定 schema／codec 優先、完整 execution caller 切換、factor ownership、暫時機制退休及 ML 搬移實驗限制。尚未實作。
- 2026-09-23：R015 personal producer/save/ACK slice 獲 bounded `ACCEPTED_SCOPE`；`TMP-REC-03` 已依上方退休帳列為 retired。Wave 7–14 仍 BLOCKED；未改已凍結的 TMP-REC-03 row。
- 2026-09-23：登錄 R022 `TMP-RGM-01`；pure regime policy／state transition 與 app history I/O adapter 已獲 bounded `ACCEPTED_SCOPE`，暫時相容入口仍 ACTIVE；Wave 7–14 仍 BLOCKED。
