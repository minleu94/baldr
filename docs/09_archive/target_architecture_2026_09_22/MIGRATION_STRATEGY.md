> **已被取代，僅供審查歷史（2026-09-22）**：本草案不再作為實作依據。請閱讀 [FINAL_MIGRATION_SEQUENCE.md](../../01_architecture/target_architecture_2026_09_22/FINAL_MIGRATION_SEQUENCE.md)；所有目標架構決策以 [FINAL_TARGET_ARCHITECTURE](../../01_architecture/target_architecture_2026_09_22/FINAL_TARGET_ARCHITECTURE.md) 為準。下文保留原稿供核對紅隊引用，與 FINAL 衝突的條文全部失效。

# 五步漸進遷移策略

> 文檔交付，不授權執行下面的 production changes。遷移沿用 [工程 Roadmap](../../00_core/ROADMAP_6M_ENGINEERING.md) 與產品 Gate，不新增版號／自然 evidence credit；每步採小而完整的垂直責任切片，不另外展開數十個 micro-phase。

## 1. 原則與先後關係

```text
1 鎖定行為與相容證據
→ 2 完整執行結果，消除跨 run 隱藏狀態
→ 3 分離讀取／計算／決策／保存責任
→ 4 統一欄位映射與開發導航
→ 5 收口相容層與 enforce 邊界
```

每步不以搬檔數衡量。先鎖 oracle，再形成 request/result 與資料 ports，最後才依 ownership 重新定位 package。ML internals 從第一步起凍結；只在外侧接線，內部整理是後續獨立 Gate，不是完成推薦重構的前提。

## 2. 步驟 1：鎖定既有行為與相容性基線

| 項目 | 要求 |
|---|---|
| 目標 | 知道哪些差異是 regression，哪些是舊行為／資料限制，讓每次抽取可回滾 |
| 影響子系統 | 推薦、ranking、save、replay、data fallback、ML manifests／small numeric fixtures、UI caller |
| 必須保持 | score/rounding、排序/tie-break、universe/candidate limits、filter順序、regime、cost／成交時間、empty/error／cancel 語意、原 IDs/hash/source clock |
| 相容機制 | 獨立 frozen request/input/output fixtures；舊 JSON/SQLite copy；原 feature/matrix/model fixtures；原 entry points 保留 |
| 前置 | 記錄 HEAD／dirty files／正式資料設定；確認隔離測試 root；不覆寫現有任務檔案 |
| 完成條件 | 選定代表案例的 pre-change outputs、已知 failures、數值/identity/side-effect oracle 可重跑；全部受影響 artifact 契約有 owner；正式資料只讀 |
| 可移除的舊結構 | 無。這步不能以「先清理」刪 API、資料或測試 |

至少涵蓋：fixed、quantile／母體太小、缺指標、基本面 unavailable、PIT 成分缺失、合法零候選、部分股票 exception、SQLite→CSV、calibration unavailable、A/B 交錯執行、重複保存、identity conflict、保存時來源更新、取消、舊格式 load。

同一套 tests 不能新舊都呼叫新 helper 當 oracle；小型手算、舊 snapshot、獨立 baseline 保留。ML 本步只讀 manifests／既有小 fixtures，不啟動 full rebuild。

## 3. 步驟 2：一次執行回傳完整結果

| 項目 | 要求 |
|---|---|
| 目標 | 不再把 items、negative evidence、quality、run context 分離運送 |
| 影響子系統 | `RecommendationService`、DTO／ports、execution coordinator、save coordinator、UI worker、CLI／replay caller |
| 必須保持 | 原算法／預設／cutoff modes／rule selection authority、UUID 與 exact projection identity、明示保存、合作式取消、legacy callers |
| 相容機制 | 先把既有 evaluator 呼叫包成 invocation-scoped complete result；原 list API 投影同一 result；舊 `last_*` façade 只用於未遷移 caller並立即 capture |
| 前置 | 步驟 1 的時序、保存／identity fixtures 與 call-site inventory |
| 完成條件 | 新 API 所有 terminal outcomes 帶同一 result identity；UI與CLI只持完整 result；save 只讀 frozen result；A/B interleave、延後保存、rerun/cancel 都不混資料 |
| 可移除的舊結構 | 已遷移 caller 的 `getattr(last_*)`、config `_recommendation_run_context` 暫存、UI 保存 DTO builder；所有 callers 切完才移除舊 last-state port |

關鍵時序修正：現況保存可能重新 detect regime；目標必須保存執行時 regime。這不是任意算法改良，而是執行一致性缺口修正；須以「run A 完成→source/regime 改變→保存 A」測試清楚列 before/after。若找不到 A 執行時 evidence，legacy adapter 標 unknown，不能偷偷重查現在值。

失敗／取消與 `[]` 拆開是新 API 契約；舊 API 的 exception 和 list 行為由 adapter 維持。新 UI 收到 cancelled 不套用 partial rows。Validation error 發生在 engine 開始前時也不保留上一輪 `last_*` 作此次結果。

## 4. 步驟 3：分開來源、計算、決策、保存

| 項目 | 要求 |
|---|---|
| 目標 | domain 無隱式 I/O，application 能直接看到資料選擇與 side effects |
| 影響子系統 | market/regime/screener readers、recommendation evaluate/rank、update technical job、source adapters、app persistence、portfolio/advice pure policies |
| 必須保持 | 原 source priority/fallback、公式/warmup、filters/weights、歷史日期 parser、成本/撮合、candidate/formal gates、原 storage 路徑 |
| 相容機制 | 沿用現有 providers/composition，逐個 default I/O 改注入；舊 import 以 alias 過渡；repository port 後面仍可使用原 implementation |
| 前置 | 步驟 2 有完整 result；相關輸入與副作用 oracle 已固定；ML hash敏感清單已排除 |
| 完成條件 | 同輸入 domain 可無 DB/HTTP 執行；依賴違規表逐項有 A/B 處置；fallback event端到端可查；Qt/CLI用同一用例，舊資料可讀 |
| 可移除的舊結構 | decision 內 sqlite/CSV reader、library對scripts的非凍結依賴、重複 default provider constructors、移轉後舊 orchestration body |

先做最有證據的 seams：`stock_screener_sqlite_reader` 外移；regime/industry 注入已存在可延續；ranking pipeline 轉純 owner；technical indicator compute 與 publication writer 分開。每次抽取只改一條責任鏈，不能同時換公式、依賴版本與 numeric format。

Regime 的歷史確認／cooldown 必須以明示 prior state 與更新輸出保留，再抽離 JSON I/O；不能只移除 history file 讓每次計算從空狀態開始。baseline 必須加入多日序列、相同日重跑、historical mode 與來源失敗案例。

`paper_daily_execution_producer`、`prospective_technical_shadow_producer` 這類跨服務 job 應向外移；其 low-level reader／writer 留 data。ML Direct source fingerprint 涉及檔案先保持原位，以外側 façade 接線；不能為通過 import guard 改 hash 定義。

## 5. 步驟 4：集中 field mapping、版本 codec 與功能入口

| 項目 | 要求 |
|---|---|
| 目標 | 新欄位／filter／reason 改動局部且可預測，讀寫／UI 不各自維護相同資料形狀 |
| 影響子系統 | canonical recommendation item／assessment、reason分類、persistence codec、query/presenter、strategy/indicator/factor registry |
| 必須保持 | 舊 JSON key與舊版本讀取、原 scalar precision/null、unknown codes、result/replay references、歷史權限與證據狀態 |
| 相容機制 | 一個版本 decoder/encoder；新 format additive、舊格式唯讀保留；DB只在查詢需求成立時新增可選 index/column |
| 前置 | 步驟 3 domain與I/O邊界清楚；step 2 caller不再逐欄讀 live state |
| 完成條件 | A/G/H 至少以隔離測試示範局部修改；其他 A–J 各有 owner/contract；沒有平行 DTO field maps；未知欄位／reason不破壞歷史讀取 |
| 可移除的舊結構 | UI逐欄save mapping、分散 `to_dict/from_dict` 副本、獨立維護的 excluded/why-not/liquidity清單；只保留 codec產生的legacy projections |

canonical schema 不是所有領域共用一個超級 DTO。recommendation、ledger、evidence各自有生命週期，只用 reference相連；query可有自己的顯示欄位，但業務值不得再計算一遍。

本步同步 developer navigation／新增欄位指南；功能真的可見時才同步 Manual 的入口、參數、結果、安全與排錯。資料格式改動另做受控 migration plan，不把正式 schema apply綁在 app啟動或 import。

## 6. 步驟 5：移除過渡 runtime 路徑，鎖定依賴

| 項目 | 要求 |
|---|---|
| 目標 | 只有一套有效 engine、清楚入口與守得住的 import／欄位規則 |
| 影響子系統 | compatibility façades、composition、dependency guards、affected caller tests、導航與架構文件 |
| 必須保持 | 舊 artifacts 可讀、正式權限不變、ML frozen identity、原 UI／CLI外部支援期限與已明示public契約 |
| 相容機制 | 短期 alias有owner/退出條件；歷史format decoder維持單引擎旁的讀取能力；ML凍結例外 exact列管 |
| 前置 | 全部 repo callers含scripts、scheduler string entries、plugins、tests已檢查；新路徑整合驗證通過；外部caller支援期已決定 |
| 完成條件 | 無 business `last_*` 跨run依賴；非凍結domain無I/O／逆向import；所有A–J符合改動範圍；既有guard違規已有明確修正，不靠廣泛豁免；相容readback與回滾演練通過 |
| 可移除的舊結構 | 無caller的runtime adapter／舊DTO副本／舊engine body。原資料、舊schema decoder與必要模型class aliases不能因runtime去重而刪 |

ML 內部巨大函式仍列後續技術債；本五步不宣稱它們已重構。後續只有在 [ML 相容 Gate](ML_COMPATIBILITY_PLAN.md) 成立、確定checkpoint處置與模型qualified paths後才抽內部責任，仍保持單一 trainer／builder。

## 7. 相容層退休帳

| 暫時結構 | Owner | 退出條件 | 刪除前驗證 |
|---|---|---|---|
| `run_recommendation -> list` 舊 façade | app recommendation | repo全部caller改consume execution；公開外部契約有deprecation決議 | direct/dynamic/call-site查核、CLI/UI integration |
| `last_*` compatibility port | app recommendation | 沒有保存／查詢caller讀它；同run freeze全面成立 | interleave/cancel/failed-run regression |
| 舊 DTO import re-export | contract owner | 外部import相容期限已滿，序列化model不依賴它 | imports＋pickle/joblib path inventory |
| 舊 JSON format decoder | persistence owner | 對應artifact留存期限結束且移轉獨立獲準 | 通常不刪；多版本解碼不是第二套runtime |
| ML source-path exception | ML/data owner | 新identity/resume/serialized-path相容計畫完成 | 舊store byte parity與resume拒絕/成功測試 |

禁止新增没有owner與退出條件的adapter，也禁止讓legacy/new互相呼叫形成雙向循環。

## 8. 驗證、回滾與風險控制

每個實作切片跑相應 focused tests／changed Python compile／型態檢查。推薦可從 DTO roundtrip、run support、ranking、negative evidence、save coordinator、recomputation、replay、calibration integration開始。需要驗證依賴就跑現有 ML boundary guard並新增狹義規則；已知四項baseline違規不能悄悄抹掉。

UI改動必跑 repo指定三項：UpdateView pytest、`qa_validate_update_tab.py`、全域mypy；再跑 affected UI caller route。ML只跑小型隔離相容fixtures；大型formal canary、資料修復/回填、scheduler實跑另獲授權。

回滾以程式切片為單位：

- 未改wire/schema的slice可回到原接線，保留此期間新結果與diagnostics。
- 已發布新schema時，先停止新writer；保留新readers與原artifact，不讓舊writer覆寫新格式。additive DB欄不做破壞性drop，索引可延後回收。
- JSON/index部分成功依同ID/hash恢復；不能刪全部output或用另一輪重算覆盖。
- 行為不符oracle就停止擴大，保留差異與before/after evidence；先排除已證實bug，再做獨立修正決議。
- 不使用shadow parity雙寫正式store。若需比較新舊引擎，只用同一凍結input、隔離temp output，不增加外部副作用。

## 9. 本輪文檔 coverage 與交付邊界

| 文件 | 本次處理 | 原因 |
|---|---|---|
| 指定七份文件 | 新增於本目錄 | 使用者明確要求的設計交付 |
| `target_system_architecture.md` | 加分冊入口與狀態說明 | 保持唯一目標架構權威與工程細節導引 |
| `DOCUMENTATION_INDEX.md`／架構 README | 加導航與更新記錄 | 可定位七份文件 |
| Snapshot／目前架構／Roadmap Hub／Product／6M／Version／Carryover | 檢查，不改完成／優先序內容 | 未實作、沒有重新核準產品方向／版本 |
| Application Manual | 檢查相關推薦／ML限制，不修改 | 沒有可見功能改動，且已有其他任務dirty變更 |

安全接手點是步驟1的受控實作規劃。這次沒有執行任何migration、模型反序列化、正式DB查核或full pytest；不要把文件完成寫成架構已遷移。

### 本次文件驗證結果

- 七份指定檔案均存在；A–J 共10個情境、INV-01–32均完整。
- 七份文件及新增導航共67個本地連結檢查通過；Markdown code fences與新檔尾端空白檢查通過。
- 四個主要函式的AST行號／範圍與評估引用一致；11個程式樹合計731份Python來源。
- `git diff --check`通過（僅Git LF/CRLF提示）；本次tracked差異只涉及三份文件入口，另有七份新增文件。未stage、commit或push。
- ML guard實際檢查525檔，exit 1、4項既有違規已逐項記錄於評估，不能宣稱guard通過。
- 其他工作將HEAD從`574de045`推進至`f3c3f23e`，差異只有操作手冊；本次未改它，前後SHA-256一致。未追蹤`=`亦保留不動。
- 沒有production Python或UI改動，因此本次未跑pytest、UI validator、mypy、py_compile；這不構成功能或遷移驗收。

## 更新記錄

- 2026-09-22：建立五步遷移、相容層退休、驗證與回滾策略；狀態為設計完成、實作未開始。
