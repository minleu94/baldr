> **已被取代，僅供審查歷史（2026-09-22）**：本草案不再作為實作依據。請閱讀 [FINAL_ARCHITECTURE_INVARIANTS.md](FINAL_ARCHITECTURE_INVARIANTS.md)；所有目標架構決策以 [FINAL_TARGET_ARCHITECTURE](FINAL_TARGET_ARCHITECTURE.md) 為準。下文保留原稿供核對紅隊引用，與 FINAL 衝突的條文全部失效。

# 架構不變條件

> 後續實作代理必須遵守。這些是本次目標設計的驗收約束，不表示程式目前已全面滿足；repository `AGENTS.md`、既有資料／產品 gate 與明確使用者授權仍適用。

## 1. 行為與數值

| ID | 必須遵守 | 可驗證條件 |
|---|---|---|
| INV-01 行為相容 | 架構遷移不改演算法、filter 順序、config defaults、母體、score/rank、tie-break、成本、成交時點、benchmark 或 policy。已證實錯誤另列 before/after 與獨立測試 | 固定輸入對照舊 oracle，所有既有可見業務欄位相同；差異逐項解釋，不只比較總列數 |
| INV-02 金融精度 | 金融核心不新增裸 float；使用既有 Decimal／整數 bp／股數／分或明示 scale。保留 rounding、overflow／invalid 處理 | 小型手算與 extreme/missing fixtures；新增程式通過量化邊界檢查；不能全庫轉 dtype 改舊結果 |
| INV-03 分析邊界 | numpy/pandas/sklearn 浮點只在已有分析／模型矩陣／呈現轉換邊界；不能透過隱式 cast 回傳未定義精度的 decision 值 | 邊界輸出有 unit/scale/rounding；persisted core outputs 精確比對 |
| INV-04 決策時間 | 所有特徵、篩選、universe、normalization、regime、停損停利與 benchmark 只用該次決策可取得資料 | available_at≤decision_at；缺證據則 unavailable；日期YYYYMMDD、晚到revision、future row與跨年窗口負例 |
| INV-05 未知不是零 | missing／unavailable／estimated／observed 不互換；沒有資料不得補中性值取得 eligibility | 真0與None／mask分開測試；缺權重／缺機率／缺原始日期不補造 |

## 2. Run／result 一致性

| ID | 必須遵守 | 可驗證條件 |
|---|---|---|
| INV-06 完整執行邊界 | 一次執行的items、assessments、quality、events、context、source/evidence/projection refs 一起回傳 | 保存／UI／報告只接完整execution，不另讀service最新欄位 |
| INV-07 身分一致 | 推薦result_id在發布projection前固定；所有candidate/receipt/readback同ID；其他領域保留自己的ID並用references連接 | 兩輪同秒執行不同ID；同ID異內容拒絕；wrong candidate/date/cost/result精確拒絕 |
| INV-08 無隱藏跨run狀態 | business output不可藏在共享`last_*`、module global、UI暫存或service cache；cache只可保存有完整input/version key的可重建資料 | A完成、B完成、再保存A；A失敗/B成功；取消重跑；多caller交錯均不混用 |
| INV-09 不可變快照 | config、regime、universe與巢狀collections不得被後續UI/service mutation改寫 | 修改原config/list不影響execution/hash；frozen dataclass內mutable dict也要防護 |
| INV-10 狀態分離 | completed-empty、failed、cancelled不同；quality與persistence狀態不同。progress不是business evidence | empty可以保存；cancel不套用partial；save失敗不把算法結果變0筆或宣稱durable |
| INV-11 保存不重算 | save只保存該次frozen execution，不能讀最新regime／features／calibration補成當時結果 | 執行後更新source再保存，payload仍對應原input；saved_at不冒充decision_at |

## 3. 保存、來源與歷史

INV-08 禁止的是跨 run 隱式運送結果，不禁止 domain 必要歷史狀態。regime hysteresis／cooldown、持倉／帳務與 lifecycle state 必須明示輸入、transition 與保存 owner，維持原先語意；不能把「無狀態」當作刪除業務歷史的理由。

| ID | 必須遵守 | 可驗證條件 |
|---|---|---|
| INV-12 原始資產保護 | 不修改／刪除正式raw data、舊snapshots、replay、推薦history、numeric stores、models或persisted evidence來完成重構 | 移轉前後bytes/hash與精確path inventory；正式writes另有明示授權 |
| INV-13 Provenance不降級 | ID/hash/schema/source/as-of/available/revision/strategy/transform/cost refs完整保存；缺值不以現在資訊追認 | codec round-trip與exact readback；unknown保留unknown；new sidecar引用原hash |
| INV-14 單一wire mapping | 同概念只有一份canonical欄位owner；所有persistence/replay mapping由一個versioned codec提供 | A/H新增欄位不修改各coordinator；legacy payload只是投影，不獨立更新 |
| INV-15 Idempotency與恢復 | 同identity同payload可重試；異內容拒絕。JSON與SQLite部分成功要可辨識，不宣稱跨store原子 | crash-point、orphan、missing artifact、hash mismatch、index failure fixtures |
| INV-16 歷史顯示與重算分離 | load歷史只解碼原保存事實；replay產生新identity並保存parent/version/input refs | latest資料更新不改歷史畫面；不相容時不做優劣排名；缺PIT阻擋而不補當前分類 |
| INV-17 不同權限保持 | candidate、research、historical replay、shadow、formal、natural credit、broker是不同狀態；讀到資料不代表可採用 | 新adapter不得提升eligibility；fixture/replay不折抵natural maturity或promotion |

## 4. ML 專屬

| ID | 必須遵守 | 可驗證條件 |
|---|---|---|
| INV-18 Frozen schema | 舊feature order/id/dtype/unit/scale、mask、normalization、labels、targets、row/fold identity不變 | 依ML分冊做binary／matrix／prediction parity，wrong schema拒絕 |
| INV-19 版本演進 | 新feature／語意／transform用新registry與artifact；舊numeric不原地插欄，不強迫重訓 | v1 reader/model仍配v1；v2明示binding；unknown版本保留但拒絕推論 |
| INV-20 Safe load | 原hash、schema、library、path、quarantine、shadow驗證先於反序列化 | wrong hash/schema／隔離artifact不得進joblib.load；fallback保持原rule |
| INV-21 Resume／路徑身分 | Direct computation dependency清單與qualified model paths初期凍結；不能搬檔後偽造舊fingerprint | 同checkpoint合法續跑，不同code identity拒絕；必要alias不重寫模型 |
| INV-22 Train/inference隔離 | fit只用允許的train資料；推論不fit，不偷讀未成熟labels；training/inference各自source hash保留 | split/purge/embargo／fitted transform／natural label cutoff負例 |
| INV-23 ML權限不擴張 | 架構重構不改rule top-N、active pointer、production alpha、promotion或broker；模型欄位是受控projection | 無ML／blockedML仍保留原Rule；projection失效撤回模型欄位，不改選股 |
| INV-24 資源保護 | capacity reserve／reservation、bounded memory、正式與shadow path guards不因測試或遷移變弱 | 小型fixture注入probe只在隔離範圍；保留low-space拒絕及無寫入副作用案例 |

## 5. 責任、依賴與擴充

| ID | 必須遵守 | 可驗證條件 |
|---|---|---|
| INV-25 單向依賴 | 按TARGET_ARCHITECTURE的子套件matrix；domain不依UI/DB/app/CLI；use case不自行建concrete I/O | AST guard含函式內／relative imports；fake ports禁止I/O；composition唯一接線 |
| INV-26 正確判斷位置 | 發現逆向依賴先判A錯依賴／B錯歸屬；不為保持錯誤目錄加generic interface掩蓋 | 評估表每條有owner/目標落點；job向外移，pure contract向owner移 |
| INV-27 原因單一 | runtime/persistence/replay/UI消費同一reason event；category明示，不靠字串猜分類 | G新增reason 2–3責任點完成四端一致性；unknown code仍可讀 |
| INV-28 局部擴充 | 一個新業務field不應到每個service/DTO/UI重複抄寫；遵守A–J範圍 | PR列owner／必改／不改；超出表中面積需以新責任説明，不用萬用dict躲型態 |
| INV-29 單一engine | 暫時façade只轉接同一實作；不得永久legacy/new兩套評分／訓練／保存規則互相漂移 | 每個adapter有owner、退出條件；歷史decoder可保留，無重複evaluator body |
| INV-30 最小抽象 | 不新增generic common/utils/helpers/shared dumping ground、萬用repository/manager/factory | 新模組有一句可界定的責任；interface有實際替換／I/O需求 |
| INV-31 UI／報告只是呈現 | 同一read model/field不在UI重算分數、機率、權重；stale callback不套錯結果 | 同result跨頁值一致；loading/error/cancel/close測試；report綁saved ID/hash |
| INV-32 文件與證據 | current/target分清；新功能／參數／流程更新Manual；設計文件不冒充實作驗收 | 改動清單、測試命令與限制誠實記錄；舊失敗數不當現況、局部pass不稱全域完成 |

## 6. 最低合併／交付條件

後續implementation PR須提供：所改責任及契約、原始行為oracle、數值與PIT自查、 affected persistence／ML相容範圍、已跑測試、剩餘違規、相容層退出條件、rollback以及文件同步。未變ML時明示其凍結邊界，而不是為了報告完整重訓。

既有錯誤必須誠實保留baseline；這次ML guard四項違規見[評估](SYSTEM_ARCHITECTURE_ASSESSMENT.md)。不能用「非本次造成」當新增相同違規的理由，也不能直接放寬guard換綠燈。

## 更新記錄

- 2026-09-22：建立32條實作不變條件與可驗收規則；現況差距以評估文件為準。
