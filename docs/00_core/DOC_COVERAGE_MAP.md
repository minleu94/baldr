# 文檔覆蓋矩陣（Documentation Coverage Map）

## 2026-10-08 封存舊版每日更新故障排除指南

將包含過時 log／資料路徑、CLI 命令及可能資料清理建議的每日更新故障排除指南原文保留於 archive；舊路徑改為短導引，指向目前操作手冊第 4 節（更新操作與安全限制）及第 12 節（常見問題）。README、快速參考、每日更新指南與資料獲取文件的現行入口已改指 Manual；每日更新詳細指南則明確標示早期 CSV／CLI 範例為歷史參考，保留 2026 freshness／隔離補充與券商分點說明。未執行舊命令；封存副本只重設兩個跨目錄相對連結並清除尾端空白。

| 原路徑 | 歸檔路徑 | 原文 bytes / SHA-256 | 封存 bytes / SHA-256 |
|---|---|---|---|
| docs/03_data/TROUBLESHOOTING_DAILY_UPDATE.md | [TROUBLESHOOTING_DAILY_UPDATE_HISTORY.md](../09_archive/TROUBLESHOOTING_DAILY_UPDATE_HISTORY.md) | 13,070 / `0CE96D05410F0AAC78D64E8477A4817CC97BA2458569DED01145ADD57CD768ED` | 13,088 / `544714E7D02A10637AEBD974D16816E9220E7E92E6ACF6F78716DD4711B5AEAD` |

## 2026-10-08 歸檔舊版推薦分析資料流程

將舊版 `DATA_FLOW_LOGIC.md` 內容移至 [`RECOMMENDATION_ANALYSIS_DATA_FLOW_LOGIC_HISTORY.md`](../09_archive/RECOMMENDATION_ANALYSIS_DATA_FLOW_LOGIC_HISTORY.md)，原路徑保留導引。舊文把 CSV 當唯一／首選行情來源、推薦指標一概描述為即時計算，並引用已淘汰的 `ui_app` 路徑；現行流程有 SQLite 優先、PIT membership cutoff、指標 JOIN／符合條件時重用等差異。封存副本只清除尾端空白並保留內容；原文與歸檔副本雜湊分列如下。歷史 Catalog、Index 與提案原有引用由導引承接，不改寫快照。資料區 README 改指 current architecture，Archive README 增加歷史入口。

| 原路徑 | 歸檔路徑 | 原文 bytes / SHA-256 | 封存 bytes / SHA-256 |
|---|---|---|---|
| docs/03_data/DATA_FLOW_LOGIC.md | [RECOMMENDATION_ANALYSIS_DATA_FLOW_LOGIC_HISTORY.md](../09_archive/RECOMMENDATION_ANALYSIS_DATA_FLOW_LOGIC_HISTORY.md) | 4,421 / `720F14286B4AF492C4E79B4A5CFF04D9EEBE1DB8F05F87C9CD3053CE2AD28211` | 4,418 / `8CC1DF986D8DF3FDCD1CC38FCBE3FC99CE452F005015D2F49D949DFD70623583` |

## 2026-10-08 修復封存文件失效連結

全文件 Markdown 本機連結盤點發現 7 個失效連結。兩份歷史 readiness 報告的 3 個連結改指向 QA 區仍存在的收據；測試資產歷史清冊的 4 個連結所指測試檔已不存在，保留原檔名文字並移除失效跳轉，避免把歷史快照誤當成目前可開啟的測試。未刪除任何證據內容；同步移除本矩陣重複的 SQLite 歸檔標題。修正後 Markdown 本機連結檢查為 0 個失效。

| 文件 | 修正前 bytes / SHA-256 | 修正後 bytes / SHA-256 |
|---|---|---|
| [PROGRAM_READINESS_AUDIT_2026_08_27.md](../09_archive/PROGRAM_READINESS_AUDIT_2026_08_27.md) | 24,249 / `EE1FEE9FEB44E804F34A03565045CD8F6DF3DB005EF3C8804F0678CCFDC11F44` | 24,258 / `B69C47A60DC674C5EDFCBEC96AB0BC0956C29D13D0AA01361984D6CC278CD458` |
| [PROGRAM_READINESS_AUDIT_2026_08_28.md](../09_archive/PROGRAM_READINESS_AUDIT_2026_08_28.md) | 138,627 / `3F0423EF60E7CAB9F1800D4BC936B6D5487E804DA24F3412303AC77FF4B5BC4B` | 138,645 / `A478B67F96584ABED1AAC37DEAFABA2A7728D83254B1075A868784BFFD6919D0` |
| [TEST_ASSET_RELATIONSHIP_AUDIT_2026_09_17.md](../09_archive/TEST_ASSET_RELATIONSHIP_AUDIT_2026_09_17.md) | 38,300 / `6623A4A02F05851E1EFB1FB090A02327604C9EABA71E160F7AF8B58E23E0A723` | 37,922 / `EA6714B3AE2AD98252FC43C7B8D8CBDDBD8942C8E2A8C27C43B24416B99679C4` |

## 2026-10-08 修復現行架構頁的絕對連結

將 `system_architecture.md` 的 13 個與 `target_system_architecture.md` 的 2 個 `C:/Projects/...` 工作區連結改為相對路徑；15 個目標在 repo 內均存在。只修連結目的地，保留段落與架構判斷；歷史 review 收據中的絕對路徑維持原樣。架構主文的日期化增量仍需逐段審核，不在本次批次移動。

同一輪日期化內容核對發現 UX16 區塊保留「原排名尚無不可變 publisher」的早期審查結論，與後續已落地 publisher／版本化收藏章節矛盾。已將過時狀態流水帳收斂為指向 UX16／UX18／UX19 QA 的歷史收據入口；保留 UX16 的母體來源契約及後續原排名架構內容，未移除 QA 證據。

## 2026-10-08 修復功能文件的絕對連結

將 `UI_FEATURES_DOCUMENTATION.md`、`USER_GUIDE.md`、`BACKTEST_LAB_FEATURES.md` 的 8 個本機絕對連結改為 repo 相對路徑。Manual 與 TASK_LOOP handoff 目標均已驗證存在；只修連結，不改功能描述。

## 2026-10-08 標記券商分點手動腳本暫停執行

券商分點指南的三組舊命令指向不存在的 `scripts/test_*.py`；實際檔案位於 `tests/scripts/`，但其 `project_root` 計算目前落在 `tests/`。腳本會連網並可能寫入設定的 `DATA_ROOT`，全分點腳本另強制重抓。指南改以暫停提示取代可複製命令，並移除「測試必讀」標籤，連回 Manual 與 tests_readme。腳本未修改、未執行；恢復命令前仍需修正 repo-root import 與配置隔離資料根目錄。

## 2026-10-08 操作手冊依任務分段閱讀

APPLICATION_MANUAL 有 13 個工作區章節及日期化補充。docs/07_guides/README.md 新增章節標題地圖，Codex、Gemini、Documentation、Testing／QA 與 Antigravity 入口改為依任務讀相關章節；跨工作區流程讀涉及章節，日期化細節讀相關附冊／QA。Manual 本身仍是操作權威，沒有改寫其內容；這項調整只改閱讀路由，避免一般任務載入整份長手冊。

## 2026-10-08 Month 5 Fundamental inventory 歷史歸檔

將 87,587-byte、510 行的 Month 5 基本面來源盤點移至 `docs/09_archive/`；原文最後更新記錄到 2026-08-12，且包含大量逐日研究／來源採集流水帳。原路徑改為短導引，指向現行 Snapshot、current architecture、來源審查、snapshot config 與 source acceptance QA；QA README 增加基本面／估值來源地圖。原文沒有需重設的本地相對連結，封存 bytes 與原件 SHA-256 相同。

| 原路徑 | 歸檔路徑 | 原件 bytes / SHA-256 | 封存 bytes / SHA-256 |
|---|---|---|---|
| docs/03_data/FUNDAMENTAL_SOURCE_INVENTORY.md | [FUNDAMENTAL_SOURCE_INVENTORY_HISTORY_20260812.md](../09_archive/FUNDAMENTAL_SOURCE_INVENTORY_HISTORY_20260812.md) | 87,587 / 337851783F76C0013771C3D70D88D26C1B8CAC184B1AFE9A114BCD8539D3302C | 87,587 / 337851783F76C0013771C3D70D88D26C1B8CAC184B1AFE9A114BCD8539D3302C |

## 2026-10-08 舊版 CSV 全量重建指南歸檔

將 4,603-byte 舊版 `DATA_REBUILD_GUIDE.md` 移至 archive，原位置保留警示導引。原文直接建議 `--force-all` 重寫合併 CSV 與重算衍生資料，並使用固定個人路徑；它未反映目前受控來源／projection、資料修復與 QA 邊界。`data_audit_agent.md` 改指每日更新指南、current architecture 與具名 QA 收據，明確將舊全量命令列為歷史操作。封存只修正 1 個指向備份稽核的相對連結；其餘原文保留。來源 SHA-256 為 `1876E8FC64C825F4CF72CC29927FAA079BBC8DE04AB4B9E2D2DD8862905BCDAD`；更新連結後 archive 為 4,613 bytes，SHA-256 為 `558974868D100BBB71FC223DC4FBFB4860D3AF1A7F39D010FCD14CFCD3D1A443`。

## 2026-10-08 舊版 SQLite 雙軌指南歸檔

將 2026-06-02 v1.1 SQLite 雙軌指南移至 `docs/09_archive/`，原路徑留下導引。原文的 CSV 唯一真實來源／SQLite 快取定位、322 倍效能聲稱與全量遷移步驟不再代表目前資料契約；現況依據為 current architecture、每日資料更新指南及 Manual。同步修正 UI feature 文件的維護指向與資料專區入口；歷史索引的舊路徑由導引承接。歸檔原文未改寫，bytes 與 SHA-256 保持不變。

| 原路徑 | 歸檔路徑 | 原件 bytes / SHA-256 | 封存 bytes / SHA-256 |
|---|---|---|---|
| docs/03_data/SQLITE_STORAGE_GUIDE.md | [SQLITE_STORAGE_GUIDE_HISTORY_20260602.md](../09_archive/SQLITE_STORAGE_GUIDE_HISTORY_20260602.md) | 9,490 / 63639D5EEC98F96FBD75B53BED528521942973C0726A02C6C2ADFE83BE7B20E3 | 9,490 / 63639D5EEC98F96FBD75B53BED528521942973C0726A02C6C2ADFE83BE7B20E3 |

## 2026-10-08 資料文件導覽與舊實作摘要歸檔

`docs/03_data/README.md` 改按日常更新、流程／儲存、來源／保留盤點及歷史摘要分組，補上原先漏列的備份保留、SQLite、資產登記與 quarantine 文件，並標示各日期化盤點的範圍與限制。兩份描述舊 CSV/API 操作的一次性摘要移入 archive；原路徑留下導引，現行入口指向每日更新指南、Manual 與 current architecture。歸檔原文未改寫，封存前後 bytes 與 SHA-256 相同。歷史目錄與索引中的舊路徑由導引頁承接。

| 原路徑 | 歸檔路徑 | 原件 bytes / SHA-256 | 封存 bytes / SHA-256 |
|---|---|---|---|
| docs/03_data/INDUSTRY_INDEX_UPDATE_SUMMARY.md | [INDUSTRY_INDEX_UPDATE_SUMMARY_HISTORY.md](../09_archive/INDUSTRY_INDEX_UPDATE_SUMMARY_HISTORY.md) | 3,120 / 129551C5E5221E6D8703D3072BA7149656D579381BDC855C203BC48A509B08DC | 3,120 / 129551C5E5221E6D8703D3072BA7149656D579381BDC855C203BC48A509B08DC |
| docs/03_data/MERGE_AND_MARKET_INDEX_SUMMARY.md | [MERGE_AND_MARKET_INDEX_SUMMARY_HISTORY.md](../09_archive/MERGE_AND_MARKET_INDEX_SUMMARY_HISTORY.md) | 4,023 / 28AE1A86BD43B35234162D2011400BEC3DDD1A9BBB4508A30453A4537A76F92D | 4,023 / 28AE1A86BD43B35234162D2011400BEC3DDD1A9BBB4508A30453A4537A76F92D |

## 2026-10-08 早期資料收集架構歸檔

將 2026-06 的 496 行資料收集藍圖移至 docs/09_archive/；原 2026-10-03 freshness 補記與 2026-06-11 券商 E/B 契約均保留。它們的目前適用結論分別由 Integration Repair QA／Manual，以及 system_architecture §9／DATA_FETCHING_LOGIC 承接。舊架構路徑保留導引，現行 README、資料操作指南、Agent 參考與本 Coverage Map 均已改指現況或標示歷史。原文 14 個本地連結均有效，僅重設 1 個 system_architecture 同層連結。

| 原路徑 | 歸檔路徑 | 原件 bytes / SHA-256 | 封存 bytes / SHA-256 |
|---|---|---|---|
| docs/01_architecture/data_collection_architecture.md | [DATA_COLLECTION_ARCHITECTURE_HISTORY.md](../09_archive/DATA_COLLECTION_ARCHITECTURE_HISTORY.md) | 20,394 / AF8407BA1DDF1412764436F3C80675E942136BA6B83C58A449A1FB72E971876B | 20,413 / 02AB755F5C4772E60B8B55466F85703C2A370A8FAE74F32BAF2AB354423E4883 |


## 2026-10-08 全文件目錄快照歸檔

將 2026-10-06 的 1,133 行 tracked-file Catalog 從 00_core 移至 09_archive，舊核心路徑保留轉址。封存副本只調整 16 個同層核心文件連結與 1 個自我連結；原有 1,022 個本地 Markdown 連結已全部解析通過。docs/README、PROJECT_NAVIGATION、DOCUMENTATION_STRUCTURE、DOCUMENTATION_GRAPH_GUIDE、舊次整理 Manifest 與 QA 收據已改指歸檔副本；現行 DOCUMENTATION_INDEX 的既有舊路徑由轉址承接。Catalog 的日期、清點範圍及其餘內容保持不變。

| 原路徑 | 歸檔路徑 | 原件 bytes / SHA-256 | 封存 bytes / SHA-256 |
|---|---|---|---|
| docs/00_core/DOCUMENTATION_CATALOG_20261006.md | [DOCUMENTATION_CATALOG_20261006_HISTORY.md](../09_archive/DOCUMENTATION_CATALOG_20261006_HISTORY.md) | 141,321 / 11B478D49DB1CC06DC16F39BFCD44A82E2262635A756BBC48D5151338F4C8813 | 141,505 / E0249E4831E9856EA4DFA5C841E3C373AA0CC2CD507F6F982149ED8D69C6AB98 |


## 2026-10-08 Phase 文件 V1.1–V2.0 歷史路徑校正

13 份 docs/05_phases/ 歷史設計與研究 SOP 原先連到 docs/00_core/ 的舊版本路線導引頁，現改為直接連至 docs/09_archive/ 的 V1.1–V2.0 歷史原件。docs/05_phases/README.md 原本已直連封存原件，保持不變；舊核心路徑繼續保留導引，以承接其他舊引用。沒有改寫 Phase 正文或目前成熟度定義。


## 2026-10-08 Roadmap 空歷史章節收斂

6M Roadmap 的 Gate 7 原有 8 個日期小節，各節只有同一個歷史歸檔連結；已合併為條件式 Gate 說明，補上 Gate 7 工程入口、Snapshot 與歷史流水帳。版本成熟度 Roadmap 的 6A 章節只含歷史交接導引，已收斂為第 7 節前的一則歷史提示。具體日期化紀錄仍完整保存在各自 archive；未變更 Gate 條件、版本成熟度標準或目前狀態。


## 2026-10-08 Workbench 歷史 UI closeout 歸檔

將兩份 2026-07-07 一次性 Workbench UI closeout 原文移至 docs/09_archive/，原 QA 路徑保留導引頁。SHA-256 與大小核對搬移前原件；舊靜態 Catalog 與歷史索引仍可由導引頁到達原文。QA README 與 Archive README 已新增分類入口；目前操作看 Manual、目前狀態看 Snapshot。

| 原路徑 | 歸檔路徑 | 原件 bytes | SHA-256 | 歸檔理由 |
|---|---|---:|---|---|
| docs/06_qa/WORKBENCH_LEFT_NAVIGATION_IA_CLOSEOUT_2026_07_07.md | [WORKBENCH_LEFT_NAVIGATION_IA_CLOSEOUT_2026_07_07_HISTORY.md](../09_archive/WORKBENCH_LEFT_NAVIGATION_IA_CLOSEOUT_2026_07_07_HISTORY.md) | 2,881 | 5B436C77E20D3558C062894517DFB9DD4ECBF5317364DB20D82AAD7A52979DE0 | 單次導覽 IA closeout；現況由 Manual、Snapshot 與近期 QA 承接，歷史測試結果保留原文。 |
| docs/06_qa/WORKBENCH_VISUAL_HIERARCHY_POLISH_CLOSEOUT_2026_07_07.md | [WORKBENCH_VISUAL_HIERARCHY_POLISH_CLOSEOUT_2026_07_07_HISTORY.md](../09_archive/WORKBENCH_VISUAL_HIERARCHY_POLISH_CLOSEOUT_2026_07_07_HISTORY.md) | 3,568 | 2EE487D1544D9EBA4CD9972AD51F4896A6F0E2179AD8C4039EF09BB19CE4EA9B | 單次視覺層級 polish closeout；保留當時 UI 邊界與驗收收據，不代表目前 Gate 狀態。

## 2026-10-08 歸檔三份一次性 QA 收據

將已完成的文件治理稽核、V2.0 非排程 closeout 與 ML Shadow 工程操作 closeout 移入 `docs/09_archive/`；內容各保留原文與原路徑轉址。下表 SHA-256 為搬移前工作樹原件；歷史 `DOCUMENTATION_CATALOG_20261006.md` 與既有 archive/history 引用繼續由轉址承接。QA README、Archive README 已新增分類入口；Superpowers README 的 push 前稽核連結改為直達歸檔副本。現況以 Snapshot、現行 Runbook 與具名最新 QA 為準。

| 原路徑 | 歸檔路徑 | 原件 bytes | SHA-256 | 歸檔理由 |
|---|---|---:|---|---|
| `docs/06_qa/DOCUMENTATION_PRE_PUSH_AUDIT_2026_07_06.md` | [`DOCUMENTATION_PRE_PUSH_AUDIT_2026_07_06_HISTORY.md`](../09_archive/DOCUMENTATION_PRE_PUSH_AUDIT_2026_07_06_HISTORY.md) | 4,816 | `180FD1F6BCAB2727255CCEAB13A9DBBF177E53952D90914DDF327C2E2771FFA4` | 單次文件治理盤點；後續 2026-09-27／10-06 rebaseline 已更新入口與結構。 |
| `docs/06_qa/PRE_V2_NON_SCHEDULE_READINESS_CLOSEOUT_2026_07_06.md` | [`PRE_V2_NON_SCHEDULE_READINESS_CLOSEOUT_2026_07_06_HISTORY.md`](../09_archive/PRE_V2_NON_SCHEDULE_READINESS_CLOSEOUT_2026_07_06_HISTORY.md) | 8,990 | `BBEFCDFD0EC32BA23A7A2B7578EE6C99BA929EF20F7EAE1ABD3386DFCA852748` | V2.0 前的時間點 closeout；剩餘時間門檻及 scheduler 狀態不代表目前 readiness。 |
| `docs/06_qa/ML_SHADOW_INFERENCE_OPERATIONS_CLOSEOUT_2026_07_15.md` | [`ML_SHADOW_INFERENCE_OPERATIONS_CLOSEOUT_2026_07_15_HISTORY.md`](../09_archive/ML_SHADOW_INFERENCE_OPERATIONS_CLOSEOUT_2026_07_15_HISTORY.md) | 3,343 | `73957B26B668AD601BD512D4952054D3577D7534A9DD3A5528D8E9DD3C28EA75` | 一次性受控工程 closeout；真實 frozen artifact smoke 當時 blocked，current steps 仍見 Runbook。 |

## 2026-10-08 歸檔舊端到端架構藍圖

將 `docs/01_architecture/system_flow_end_to_end.md` 的 8,440-byte 舊流程藍圖移至 [`docs/09_archive/SYSTEM_FLOW_END_TO_END_BLUEPRINT_HISTORY.md`](../09_archive/SYSTEM_FLOW_END_TO_END_BLUEPRINT_HISTORY.md)。搬移前 SHA-256：`BFEE295DF4EFCAC0ED678DEAEEA589681258BD72EC87BACC2C634A35AB8911ED`；保留原文段落，只移除檔尾多餘的空白行。該藍圖描述舊 feature store／recommendation／UI 路徑與建議新增模組，不再作現況權威。原架構路徑改為導引，接住 2026-10-06 靜態 Catalog、歷史計畫與 QA 引用；架構 README、Archive README 已更新現況入口。不改未提交的 `DOCUMENTATION_INDEX.md`。

## 2026-10-08 封存被拒絕的 prospective clock staging

將 `docs/06_qa/PROSPECTIVE_FORMAL_RESTART_CLOCK_2026_08_27_V2_STAGING.md` 的 6,246-byte 歷史收據移至 [`docs/09_archive/PROSPECTIVE_FORMAL_RESTART_CLOCK_2026_08_27_V2_STAGING_HISTORY.md`](../09_archive/PROSPECTIVE_FORMAL_RESTART_CLOCK_2026_08_27_V2_STAGING_HISTORY.md)。封存前 SHA-256：`D3BCEB710AB0CDCF1CEF82B7F0DF28F8378AB6AAA3F5D1C8B4C52378F4F1555F`。只將原文指向同目錄 v3 successor 的絕對本機連結改成相對連結；其餘 staging、clock、calendar 與 PIT hashes 原樣保留。原 QA 路徑改為轉址頁，接住歷史 `DOCUMENTATION_CATALOG_20261006.md` 引用；QA README 與 Archive README 已同步標示「V2 當時被拒絕、v3 當時為 successor」，避免被解讀為目前狀態。沒有更改外部 DATA_ROOT 的任何資料或 staging。

## 2026-10-08 架構重構證據包索引

為 `docs/01_architecture/target_architecture_2026_09_22/` 的重構證據補上逐檔導航：上層入口直達 `REFACTOR_REPORTS/README.md` 與 `REFACTOR_DISPATCH/README.md`；前者依 R-task、C1 與 Wave 索引 143 份報告／審查／checkpoint，後者依 R-task 與 Wave 索引 18 份分派封包。只增加目錄連結，未移動或改寫任何架構、任務、報告或 dispatch 原文；狀態與接受判讀仍看 Snapshot 及具名 QA closeout。

## 2026-10-08 Superpowers 清冊生命週期校正

修正 `docs/09_archive/SUPERPOWERS_PLAN_SPEC_ARCHIVE_MANIFEST_20261006.md` 的適用範圍與導覽：165 筆清冊記錄明確限定為歷史追溯文件，排除唯一現行進行中的 `docs/superpowers/plans/baldr_product_completion_plan_20261006.md`；補上該計畫與 `docs/superpowers/README.md` 的生命週期連結，並將版本入口分開指向 V1.1–V2.0 歷史與 V2.1–V4.0 現行成熟度標準。同步修正 Archive README 將整個 Superpowers 目錄一概描述為歷史文件的句子。沒有改動 165 筆清冊資料列、歷史 plan/spec/prompt 原文或進行中計畫正文。

## 2026-10-08 文件入口整理首批

整理範圍限定為閱讀路徑，不改系統狀態、產品方向、操作流程或 QA 原始收據：`docs/README.md` 明確標示 2026-10-06 全文件目錄是歷史快照；`docs/01_architecture/README.md` 增加大型現況架構主文的按節速讀路徑，`system_architecture.md` 頂端新增正文錨點與現況入口；`docs/06_qa/README.md` 按主題連到既有綜整與重要收據，並明示各驗收邊界；`docs/07_guides/README.md` 校正 Manual 為 9 個頂層工作區，並補列可攜、排程搬機與 Phase3C candidate 專項指南。架構、QA 與指南專區入口原已由全域文件索引導覽；docs 根入口維持在 `docs/README.md`。不新增文件或改變目錄歸屬，故本批不搬移檔案，也不改 Snapshot／Roadmap／Architecture 主文內容／Manual。後續歸檔須另以逐檔引用清冊同步 Index、所在目錄 README、Archive README 及恢復／coverage 記錄；日期或檔名本身不能作為搬移依據。

## 2026-10-08 V4 計畫歷史歸檔

將 `docs/00_core/V4_COMPLETION_PLAN_2026_09_07.md` 的原文完整移至 [`docs/09_archive/V4_COMPLETION_PLAN_2026_09_07_HISTORY.md`](../09_archive/V4_COMPLETION_PLAN_2026_09_07_HISTORY.md)，保存原 bytes；封存 SHA-256：`C812B1A98B68968DE3D17DA1EFEE232787778C95DFD5D2C66D92BC7557DBE005`。原文最後記錄截至 2026-09-10 仍為「進行中」，不得解讀為目前狀態或已完成。舊核心位置保留短導引，維持日期化 catalog 與歷史快照中的連結；全庫 10 處舊路徑引用皆落在歷史／快照文件。README 已同步，現況仍以 Snapshot 與 V2.1–V4.0 成熟度階梯為準。未變更 `DOCUMENTATION_INDEX.md`：本次查核未找到該索引對此計畫的引用；索引目前另有未提交編輯，避免觸碰。

## 2026-10-08 QA 稽核歸檔第二批

以下一次性稽核原文移入 `docs/09_archive/`，原位置保留轉址，接住 2026-10-06 靜態 catalog 與 2026-09-27 歷史索引的舊連結；保留原 bytes／SHA，不將單次 probe 的未重現解讀為問題不存在。現行 Index 未直接列出這三份文件，本次不改仍有其他對話未提交變更的 `DOCUMENTATION_INDEX.md`。

| 原路徑 | 封存路徑 | SHA-256 | 保留理由 |
|---|---|---|---|
| `docs/06_qa/QT_SQLITE_INSPECTOR_SHUTDOWN_PROBE_2026_09_15.md` | [`docs/09_archive/QT_SQLITE_INSPECTOR_SHUTDOWN_PROBE_2026_09_15.md`](../09_archive/QT_SQLITE_INSPECTOR_SHUTDOWN_PROBE_2026_09_15.md) | `78E0775E3B4A6A70616311A6EC9256132CD40B0D00B983D14317D51E5F5A7B91` | 單次 bounded probe；未重現 deadlock，仍不能排除其他 signal race。 |
| `docs/06_qa/DOCUMENT_ENCODING_AUDIT_2026_06_16.md` | [`docs/09_archive/DOCUMENT_ENCODING_AUDIT_2026_06_16.md`](../09_archive/DOCUMENT_ENCODING_AUDIT_2026_06_16.md) | `350A0999F0FAEDCEA568F24E7E132388BF3BDF11275FC9DC60FF9150707FE835` | 一次性掃描結論；不作目前 repo 完整編碼狀態保證。 |
| `docs/06_qa/DOCUMENTATION_ROADMAP_REBASELINE_AUDIT_2026_07_03.md` | [`docs/09_archive/DOCUMENTATION_ROADMAP_REBASELINE_AUDIT_2026_07_03.md`](../09_archive/DOCUMENTATION_ROADMAP_REBASELINE_AUDIT_2026_07_03.md) | `E29EC4897AE201B6EF22E65E5170A8CC433B11DAD9B64C606BE92E1AAA3A3C16` | 一次性治理稽核；Phase 歷史判讀與歸檔規則已納入現行 `DOCUMENTATION_STRUCTURE.md`。 |

## 2026-10-08 QA 導覽瘦身與超長報告導讀

`docs/06_qa/README.md` 已收斂為八個主題地圖、近期證據入口與歷史／操作路徑；將重複報告摘要改為導向專題入口，保留原始 QA 文件與目錄路徑。主題涵蓋 H20、R026/R031、UX、BALDR、WP、Task Loop、ML Shadow／前瞻證據與 Data Governance。對 `TEST_ASSET_CONSOLIDATION_CLOSEOUT_2026_09_17.md` 加入範圍卡，明示 bounded union、139 組候選、26 組已明確處置、113 組僅靜態篩選的界線；未把靜態清冊描述成完整測試母體或動態回歸。未搬移、改名或刪除其他 QA 原始報告；本次已將 V1.5–V2.0 的 8 份及 V2.1–V2.5 中 11 份已結束的 readiness／closeout 歷史里程碑移入 archive，保留舊路徑轉址。仍具來源或政策用途的 P0 register、approval 收據保留於 `docs/06_qa/`。

## 2026-10-08 V1.5–V2.0 QA 里程碑歸檔

下列已結束的版本 closeout 與 release checklist 原文移入 `docs/09_archive/`，保留原 bytes／SHA-256；舊 `docs/06_qa/` 路徑留下短轉址頁，以承接 `DOCUMENTATION_CATALOG_20261006.md`、歷史文件與 Superpowers plan/spec 的既有引用。主 QA 入口與 Archive README 已更新。這批只移動 V1.5–V2.0；V2.1–V2.5 的來源／政策／approval 原件仍留在 QA，readiness／closeout 歷史按引用用途分批歸檔。

| 原路徑 | 歸檔路徑 | 原文 SHA-256 |
|---|---|---|
| `docs/06_qa/V1_5_DATA_CREDIBILITY_CLOSEOUT_2026_07_04.md` | [`V1_5_DATA_CREDIBILITY_CLOSEOUT_2026_07_04.md`](../09_archive/V1_5_DATA_CREDIBILITY_CLOSEOUT_2026_07_04.md) | `D724E17729068C78D98D33DB90E66B42FD8049D398F7870F964B134A5145F892` |
| `docs/06_qa/V1_6_CROSS_SECTIONAL_FACTOR_PIPELINE_CLOSEOUT_2026_07_05.md` | [`V1_6_CROSS_SECTIONAL_FACTOR_PIPELINE_CLOSEOUT_2026_07_05.md`](../09_archive/V1_6_CROSS_SECTIONAL_FACTOR_PIPELINE_CLOSEOUT_2026_07_05.md) | `15023E60FCC3FE4E332F7C03CC423D0D25F184291BE2573C82B4FB1F8B01F476` |
| `docs/06_qa/V1_7_NEGATIVE_EVIDENCE_CLOSEOUT_2026_07_05.md` | [`V1_7_NEGATIVE_EVIDENCE_CLOSEOUT_2026_07_05.md`](../09_archive/V1_7_NEGATIVE_EVIDENCE_CLOSEOUT_2026_07_05.md) | `51E9372DAE4F2E84F000670871E8F6285C8CB619CD8F7B8E725A236A81F2A191` |
| `docs/06_qa/V1_8_PORTFOLIO_SANDBOX_CLOSEOUT_2026_07_05.md` | [`V1_8_PORTFOLIO_SANDBOX_CLOSEOUT_2026_07_05.md`](../09_archive/V1_8_PORTFOLIO_SANDBOX_CLOSEOUT_2026_07_05.md) | `DF465A5733A3C0F8C5D79EAEAA056E9122F3B7412068A5A11266E193A3D59822` |
| `docs/06_qa/V1_9_READ_ONLY_AGENT_MCP_CLOSEOUT_2026_07_06.md` | [`V1_9_READ_ONLY_AGENT_MCP_CLOSEOUT_2026_07_06.md`](../09_archive/V1_9_READ_ONLY_AGENT_MCP_CLOSEOUT_2026_07_06.md) | `6F0098CE7585A8FB07A8BF87EC056245BF31C53BF736D152F0C04CBA7D44C65F` |
| `docs/06_qa/V1_RELEASE_CHECKLIST_2026_06_30.md` | [`V1_RELEASE_CHECKLIST_2026_06_30.md`](../09_archive/V1_RELEASE_CHECKLIST_2026_06_30.md) | `E545B8A76C7D0160CE99240F7057727339B0EA72EC39D1BCA16F15194C44E8EE` |
| `docs/06_qa/V2_0_WORKBENCH_PHASE1_CLOSEOUT_2026_07_06.md` | [`V2_0_WORKBENCH_PHASE1_CLOSEOUT_2026_07_06.md`](../09_archive/V2_0_WORKBENCH_PHASE1_CLOSEOUT_2026_07_06.md) | `A458FBF2D0F61EC9ECCF7CA39D3D4C865E73940AA3A77EA366803F2EFEA7ED41` |
| `docs/06_qa/V2_0_WORKBENCH_READ_ONLY_SOURCE_ADAPTER_CLOSEOUT_2026_07_06.md` | [`V2_0_WORKBENCH_READ_ONLY_SOURCE_ADAPTER_CLOSEOUT_2026_07_06.md`](../09_archive/V2_0_WORKBENCH_READ_ONLY_SOURCE_ADAPTER_CLOSEOUT_2026_07_06.md) | `9275C008CBA88A4D9CEF6420312A8038878A31C6C071DCCD4239090EDE0E7138` |

## 2026-10-08 V2.1–V2.5 readiness／closeout 歷史歸檔

以下已結束的工程 readiness、formal closeout 與舊 Workbench 階段收據移入 `docs/09_archive/`。表內 SHA 是移動前的原始文件雜湊；歸檔內容保留原文，V2.3 readiness 內指向仍留在 QA 的 P0 source register 之相對連結因路徑調整為 `../06_qa/`。原 `docs/06_qa/` 路徑保留轉址，接住靜態 catalog、歷史索引、舊 plan/spec 與相互引用。明確承載目前來源／政策／approval 的文件不搬移。

| 原路徑 | 歸檔路徑 | 原文 SHA-256 |
|---|---|---|
| `docs/06_qa/V2_1_ENGINEERING_READINESS_2026_07_12.md` | [`V2_1_ENGINEERING_READINESS_2026_07_12.md`](../09_archive/V2_1_ENGINEERING_READINESS_2026_07_12.md) | `5BFFF5214A34D76CD7BD51611C8AB4FDC233FA068C75C298DDCA2819EAF0F569` |
| `docs/06_qa/V2_1_FORMAL_CLOSEOUT_2026_07_12.md` | [`V2_1_FORMAL_CLOSEOUT_2026_07_12.md`](../09_archive/V2_1_FORMAL_CLOSEOUT_2026_07_12.md) | `4935379822CA55928A733B3BBA889BD84162F2AB81B73A4C6AD83765AE7DD2D8` |
| `docs/06_qa/V2_1_WORKBENCH_PHASE2_CLOSEOUT_2026_07_07.md` | [`V2_1_WORKBENCH_PHASE2_CLOSEOUT_2026_07_07.md`](../09_archive/V2_1_WORKBENCH_PHASE2_CLOSEOUT_2026_07_07.md) | `6445BE33890A9572D39E2D53949AD2A5458BC8980F2DDA032223812989CAAA81` |
| `docs/06_qa/V2_2_ENGINEERING_READINESS_2026_07_12.md` | [`V2_2_ENGINEERING_READINESS_2026_07_12.md`](../09_archive/V2_2_ENGINEERING_READINESS_2026_07_12.md) | `9C11B90D71DA20A2F8F447B7C738CB7A31702C63193426B17BBDC1E5BE6DB4EB` |
| `docs/06_qa/V2_2_EVIDENCE_OPERATING_LOOP_READONLY_CHECK_2026_07_07.md` | [`V2_2_EVIDENCE_OPERATING_LOOP_READONLY_CHECK_2026_07_07.md`](../09_archive/V2_2_EVIDENCE_OPERATING_LOOP_READONLY_CHECK_2026_07_07.md) | `F9EA344828B1B222CBB91DC700AFF2F3100125573D69BE5753621C4B5F14AAD3` |
| `docs/06_qa/V2_2_SIMULATED_PHASE_PROGRESS_QA_2026_07_07.md` | [`V2_2_SIMULATED_PHASE_PROGRESS_QA_2026_07_07.md`](../09_archive/V2_2_SIMULATED_PHASE_PROGRESS_QA_2026_07_07.md) | `AE0E033472A5BE406B9B8657027AA7665E655D98B7A9B1DEBD3A9B9554D2F1D1` |
| `docs/06_qa/V2_2_WEEK1_REVIEW_2026_07_12.md` | [`V2_2_WEEK1_REVIEW_2026_07_12.md`](../09_archive/V2_2_WEEK1_REVIEW_2026_07_12.md) | `8393E2C40773E5011C6DA553AA913CE31D9BA7887045B3B8F39D260F365048E8` |
| `docs/06_qa/V2_3_ENGINEERING_READINESS_2026_07_12.md` | [`V2_3_ENGINEERING_READINESS_2026_07_12.md`](../09_archive/V2_3_ENGINEERING_READINESS_2026_07_12.md) | `98F6D4FE0A23B983F4B19E093E01C69E3DE784252DB88BBB791ED2F2EDAA2DEA` |
| `docs/06_qa/V2_3_OFFICIAL_SOURCE_EVIDENCE_PASS_2026_07_12.md` | [`V2_3_OFFICIAL_SOURCE_EVIDENCE_PASS_2026_07_12.md`](../09_archive/V2_3_OFFICIAL_SOURCE_EVIDENCE_PASS_2026_07_12.md) | `165BFA98D3882FD5A06214960363CEC4266369F35943A12E372ED593DF1D118C` |
| `docs/06_qa/V2_4_ENGINEERING_READINESS_2026_07_12.md` | [`V2_4_ENGINEERING_READINESS_2026_07_12.md`](../09_archive/V2_4_ENGINEERING_READINESS_2026_07_12.md) | `0B25ACE761E232A8EE696595166264F129D7282113E4242E1EDCEE76F56F8633` |
| `docs/06_qa/V2_5_ENGINEERING_READINESS_2026_07_12.md` | [`V2_5_ENGINEERING_READINESS_2026_07_12.md`](../09_archive/V2_5_ENGINEERING_READINESS_2026_07_12.md) | `18848A5862A7C58EC86AFD1D5FCC695BC808C13BB722CDAA76256D50F2B25000` |

## 2026-10-08 QA 巨型報告導讀卡

對 [V4 data recovery（2026-09-07）](../06_qa/V4_DATA_RECOVERY_2026_09_07.md) 補上當日 scope、唯讀與未 apply 邊界，並連到 Snapshot 與後續 data closeout；對 [V4 automated review（2026-09-07）](../06_qa/V4_AUTOMATED_REVIEW_2026_09_07.md) 明示 machine evidence 不取代 owner acceptance；對 [Full App healthcheck（2026-06-16）](../06_qa/FULL_APP_HEALTHCHECK_2026_06_16.md) 標出舊 8-workspace 基線並連到現行 9-workspace 架構與 Manual。只增加閱讀提示，不重寫原驗收內容或數字。

## 2026-10-08 QA 歷史盤點封存第二批

將已被後續狀態重整取代的 Program Readiness 稽核與已結案的測試資產盤點收至 `docs/09_archive/`；五個舊 `docs/06_qa/` 路徑保留短轉址，歷史索引與目錄不會斷鏈。8/27 稽核新增一行歷史定位；測試資產 V1/V2 只把已搬入 archive 的相互連結改為相對路徑；其餘原文保留。當前狀態以 Snapshot 為準，當前測試路由以 QA README 為準。

| 原路徑 | 歸檔路徑 | 原文 SHA-256 | 處置 |
|---|---|---|---|
| `docs/06_qa/PROGRAM_READINESS_AUDIT_2026_08_27.md` | [`PROGRAM_READINESS_AUDIT_2026_08_27.md`](../09_archive/PROGRAM_READINESS_AUDIT_2026_08_27.md) | `F4E94F47DA5E3CB451BC34B6129EEBEA2F5473B044FB176AE79BDBC1B89071F8` | 追加歷史定位；當時 readiness 與目前狀態分開閱讀。 |
| `docs/06_qa/PROGRAM_READINESS_AUDIT_2026_08_28.md` | [`PROGRAM_READINESS_AUDIT_2026_08_28.md`](../09_archive/PROGRAM_READINESS_AUDIT_2026_08_28.md) | `9C5C36F3A8CE9B5D28BB38BFC29879E3BC7B86ACF1415C6099EDC6D94083F192` | 保留 8/29 supersession 標記與後續處置指引；P0 register 改為直接連到此原文。 |
| `docs/06_qa/TEST_ASSET_RELATIONSHIP_AUDIT_2026_09_17.md` | [`TEST_ASSET_RELATIONSHIP_AUDIT_2026_09_17.md`](../09_archive/TEST_ASSET_RELATIONSHIP_AUDIT_2026_09_17.md) | `DAA003E73CFB5F5EB0A02AC3A5A194FEEDDAEF82AAFA0557CDA1996EBB199175` | 保留 V1 撤回紀錄；V2 連結改為 archive 相對路徑。 |
| `docs/06_qa/TEST_ASSET_RELATIONSHIP_AUDIT_2026_09_17_V2.md` | [`TEST_ASSET_RELATIONSHIP_AUDIT_2026_09_17_V2.md`](../09_archive/TEST_ASSET_RELATIONSHIP_AUDIT_2026_09_17_V2.md) | `6A73E630818AB5615963E6A3522C61AC8F8B2316260E6C9B2DA6596958632722` | 保留 V2 方法補正與歷史基準；將 V1／V2 archive 內的絕對 file URI 修為相對連結。 |
| `docs/06_qa/TEST_ASSET_CONSOLIDATION_CLOSEOUT_2026_09_17.md` | [`TEST_ASSET_CONSOLIDATION_CLOSEOUT_2026_09_17.md`](../09_archive/TEST_ASSET_CONSOLIDATION_CLOSEOUT_2026_09_17.md) | `BE39D28089755B06870DECA85BA7C0519E4BA0E472377E3CD0020389C536D935` | 保留既有導讀卡；139 組／1,107 檔僅是 bounded union，不代表完整測試母體。 |

現行 [V2.3 P0 source register](../06_qa/V2_3_P0_SOURCE_ACCEPTANCE_REGISTER.md) 對 V2.3 readiness 原文的 12 個 review 連結，以及對 8/28 readiness audit 的完整盤點連結，均已改為直達 archive。舊路徑轉址保留給 10/06 靜態 Catalog、歷史快照與 plan/spec 引用。

## 2026-10-08 核心入口歷史內容瘦身

| 原路徑 | 封存路徑 | 原文 SHA-256 | 處置 |
|---|---|---|---|
| `docs/00_core/VERSION_ROADMAP_V1_1_TO_V2_0.md` | [`docs/09_archive/VERSION_ROADMAP_V1_1_TO_V2_0_HISTORY.md`](../09_archive/VERSION_ROADMAP_V1_1_TO_V2_0_HISTORY.md) | `626D90738E07CE7A3D25044901A9D8B34395F0B580FBCC05316328B374B025FC` | 已完成版本演進移出核心；核心舊路徑保留轉址，現行入口與歷史引用已更新。封存原文只調整相對連結，讓歸檔位置可正常導航。 |
| `docs/00_core/AI_CONTEXT_PACK.md` | [`docs/09_archive/AI_CONTEXT_PACK_HISTORY_20260830.md`](../09_archive/AI_CONTEXT_PACK_HISTORY_20260830.md) | `E6EB1267BC06C40DAE1F02C552C655D34EED52D4DD3F1F911EF1F5DD9E04591B` | 舊上下文包含過期優先事項與 8 工作區數量；根目錄舊路徑導向 `AGENT_CONTEXT.md` 與 Scoped SSOT。 |
| `docs/00_core/ROADMAP_6M_ENGINEERING.md` 開頭 dated status | [`docs/09_archive/ROADMAP_6M_ENGINEERING_STATUS_HISTORY_20260712_TO_20260917.md`](../09_archive/ROADMAP_6M_ENGINEERING_STATUS_HISTORY_20260712_TO_20260917.md) | `B70EA0F3A13B9B93C188DE44F34268A1A5E9E48D9AD185F28E04D235EBF3FFDB` | 保留原開頭狀態／QA 補記；核心首屏只留 Gate 職責、Snapshot 狀態入口與歷史連結。 |
| `docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md` 開頭 dated status | [`docs/09_archive/PRODUCT_ROADMAP_STATUS_HISTORY_20260712_TO_20260917.md`](../09_archive/PRODUCT_ROADMAP_STATUS_HISTORY_20260712_TO_20260917.md) | `E8BDE0CF8FCC1C3323772D21F80555DCE0FBB9E6FCED2186BAD22D8B86AC8916` | 保存原工程／handoff 快照；核心首屏回到產品方向、Snapshot 與 6M Roadmap 的職責。 |
| `docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md` §14 與更新記錄 | [`docs/09_archive/PRODUCT_ROADMAP_STATUS_HISTORY_20260712_TO_20260917.md`](../09_archive/PRODUCT_ROADMAP_STATUS_HISTORY_20260712_TO_20260917.md) | `9B0E3D9BD78CD43E6CB5DBE36406300F5FD1B99213793C00A9D43ECBC586828E`；`4ADEE85A7FC5B8E90EB35C3957B95C6AAA51EC858B4F1C2DDD66AD1165F98CE2` | 原始 30／60／90 日行動草案已由 6M Roadmap 承接；歷史更新記錄保留於同一 archive。 |
| `docs/00_core/ROADMAP_6M_ENGINEERING.md` 單輪 Gate 交接、Gate 7 狀態、Gate 校正與更新記錄 | [`docs/09_archive/ROADMAP_6M_ENGINEERING_STATUS_HISTORY_20260712_TO_20260917.md`](../09_archive/ROADMAP_6M_ENGINEERING_STATUS_HISTORY_20260712_TO_20260917.md) | `D5452DEEC9A5C4569992881F58AAEE3DA825BB3FC2BBC1B0C56F3602558084F8`；`91C1E0C5F4F9DE9003CB82FCD9BA290D33A776A7A149235DCC017515911B9B6C`；`5EA60A15730B7248073C2D2E30B9D58A810A1EE25237E1D426B6927092E79E18`；`8DF39676D2CE3AB8F14C434C0EBDA332C2B991477F635E05FDCC8B08F7F5DCE4` | 日期化執行收據移出工程 Gate 標準；每個原標題保留短導引，完整原文可追溯。 |
| `docs/00_core/DEVELOPMENT_ROADMAP.md` 的 UX23 日期狀態補記 | 已有 [`docs/06_qa/UX23_REGISTRY_INTEGRATION_20261006.md`](../06_qa/UX23_REGISTRY_INTEGRATION_20261006.md)、[`docs/09_archive/PROJECT_SNAPSHOT_HISTORY_20261006.md`](../09_archive/PROJECT_SNAPSHOT_HISTORY_20261006.md) | — | 移除 Hub 中的重複狀態行；保留專項 QA 與整理前快照，不新增第二份紀錄。 |
| `docs/00_core/VERSION_ROADMAP_V2_1_TO_V4_0.md` §6A | [`docs/09_archive/VERSION_ROADMAP_V2_1_TO_V4_0_ENGINEERING_HANDOFF_20260915_HISTORY.md`](../09_archive/VERSION_ROADMAP_V2_1_TO_V4_0_ENGINEERING_HANDOFF_20260915_HISTORY.md) | `C646B548594A97E41B4543FF52F1459EC68E519BC25D3F6A45BDCA849C6411A6` | 2026-09-15 工程分流、觀測與下一步移出成熟度標準；原 §6A 標題與導引保留。 |
| `docs/00_core/VERSION_ROADMAP_V2_1_TO_V4_0.md` 的日期化版本狀態 | [`docs/09_archive/VERSION_ROADMAP_V2_1_TO_V4_0_STATUS_HISTORY_20260712_TO_20260830.md`](../09_archive/VERSION_ROADMAP_V2_1_TO_V4_0_STATUS_HISTORY_20260712_TO_20260830.md) | `CB43F6AED0CCBA9FCADBA523C8BB501ED84ABE54C7EE8FA5A0D9BCB2A61E3A2C` | 保留 9 段原狀態文字；成熟度條件留在核心文件，現況只看 Snapshot。 |
| `docs/01_architecture/system_architecture.md` §16 更新記錄 | [`docs/09_archive/SYSTEM_ARCHITECTURE_UPDATE_HISTORY_202606_TO_202610.md`](../09_archive/SYSTEM_ARCHITECTURE_UPDATE_HISTORY_202606_TO_202610.md) | `6b086fd3da22096c819001e2fa8923f5bffb16d3b448af6e80b049a8882884dc` | 原始 25,705-byte 記錄完整保留；現架構文件保留 §16 錨點轉址，其他日期增量未移動。 |

## 2026-10-08 Roadmap 日期化內容歸檔

| 活躍文件中的歷史區塊 | 歷史保存位置 | 原區塊 SHA-256 | 處置 |
|---|---|---|---|
| `ROADMAP_6M_ENGINEERING.md` Gate 3 的 2026-08-26 read-model 狀態 | [`ROADMAP_6M_GATE_STATUS_HISTORY_20260826_TO_20260828.md#gate3-20260826`](../09_archive/ROADMAP_6M_GATE_STATUS_HISTORY_20260826_TO_20260828.md#gate3-20260826) | `7DABCA53D95A4FF01F2041BBE038048531253CA55214B552BCCE4F8A20F3DE3E` | Gate 3 保留 read-model 交付定義，日期化實作快照移出。 |
| `ROADMAP_6M_ENGINEERING.md` Gate 4 的 2026-08-27 至 08-28 四則 Portfolio／Paper 進度 | [`ROADMAP_6M_GATE_STATUS_HISTORY_20260826_TO_20260828.md#gate4-20260827-28`](../09_archive/ROADMAP_6M_GATE_STATUS_HISTORY_20260826_TO_20260828.md#gate4-20260827-28) | `B1D1B78AF1EF26D3AFF4F0127AF58C360D6AC0DBA6C814701BBFE053B7B287C9` | Gate 4 只留交付、測試與 evidence gate；原四段狀態完整保存。 |
| `PRODUCT_ROADMAP_POST_REFACTOR.md` §10.1 的 2026-09-14 至 09-21 handoff | [`PRODUCT_ROADMAP_HANDOFF_HISTORY_20260914_TO_20260921.md`](../09_archive/PRODUCT_ROADMAP_HANDOFF_HISTORY_20260914_TO_20260921.md) | `22814E3A3489E2EFD11ACE22B40014E48B44DEBA3C4FA71DFC12FFAA17049807` | 核心文件保留 V5／V6 的穩定產品邊界，日期化驗收與當時 next 移入歷史檔；只省略原區塊尾端分隔空行。 |
| `VERSION_ROADMAP_V2_1_TO_V4_0.md` `## 更新記錄` | [`VERSION_ROADMAP_V2_1_TO_V4_0_UPDATE_HISTORY_20260711_TO_20260915.md`](../09_archive/VERSION_ROADMAP_V2_1_TO_V4_0_UPDATE_HISTORY_20260711_TO_20260915.md) | `F7A6AD5A012BFD41589143E0E4F08FDBB51D35551AD9E403E35A20D2F7A57DE5` | 成熟度 spec 保留版本 Gate；舊日期化狀態與 handoff 保留在更新歷史。 |

另外，`LEGACY_ROADMAP_CARRYOVER.md` 第 4 節已明示為 2026-06-15 的歷史 Month 1–3 Gate；`EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md` 的 Roadmap 審查也標成 2026-07-11 歷史截面。兩份文件保留研究／移交內容，當前狀態與交付次序分別以 Snapshot、6M Roadmap 為準；外部 repo 未在本輪重新查核。

## 2026-10-08 工作區數量一致性

依 [現行架構主文](../01_architecture/system_architecture.md) 第 3 節，主 UI 為 9 個頂層工作區；同步修正 `docs/02_features/README.md` 與 `USER_GUIDE.md` 的現行操作手冊介紹。日期化 QA 收據中 8／8 的歷史測試結果維持原文，不回寫成新的測試結果。

## 2026-10-06 原計畫首波coverage

Must：Manual現行六處舊路徑／保存圖／CSV說明校正，以及首頁四用途／當下搜尋／大盤刷新／個股摘要操作與限制；Snapshot目前摘要、現行Architecture、Index與QA routing對應[首波QA](../06_qa/BALDR_FIRST_WAVE_INTEGRATION_20261006.md)。原plan只append、prefix保持；沒有方向／maturity／6M gate變更，相關roadmap不擴改。B08/B02工程與B09/B10 caller未完成不寫done；後續依真交付更新來源／步驟／排錯。歷史QA收據保留原policy／失敗，不回寫為成功。

## 2026-10-06 label readiness覆蓋

新增[QA](../06_qa/UX22_LABEL_READINESS_20261006.md)；Manual同步明示policy／split、repeat exact receipts、JSON保存／重讀、缺件判讀與安全。Snapshot／現行架構／index／QA路由同步有限入口；只開始UX22 readiness，不宣稱fit、公平比較或完整labels已完成。


## 2026-10-06 明示benchmark覆蓋

新增[benchmark來源／保存／唯讀UI QA](../06_qa/UX21_BENCHMARK_SOURCE_STORE_UI_20261006.md)，Manual／Snapshot／architecture同步具名無預設、v1/null與v2保存、same-period basis gate、成本版本、query-only公開資料與fixture分報、取消stale與完整label最小缺口。UX21仍partial；正式／PIT／fit與Task未啟用。

## 2026-10-06 UX08 保存圖表覆蓋

新增[QA收據](../06_qa/UX08_SAVED_CHART_READBACK_20261006.md)對應versioned nested artifact／producer／exact parent讀回、原精度及MA缺列、舊保存缺件與最新研究分離、合作取消返回與stale。Manual同步入口、步驟、cutoff／120列參數、資格限制及排錯；Snapshot與現行架構同步有限範圍。251案例不等於Native／真人、推薦writer／舊補建或全部UX08驗收。

2026-10-06 UX24第一版有限工程封存：同步Snapshot／Manual／Index／QA routing及原計畫追加；只修既有mapping optional context，不改架構、資料流、產品方向或roadmap gate，故不擴改architecture／6M／version。限定七項工程完成不取代整體UX狀態；見[封存收據](../06_qa/UX24_FIRST_VERSION_ENGINEERING_SEAL_20261006.md)。

> **給 Documentation Agent 用來判斷 coverage 的規則文件**

## 2026-10-08 Roadmap 邊界與技術保存母體架構契約

核心文件分工已校正：Snapshot 是目前狀態唯一入口；Product Roadmap 維護產品問題、能力、證據與非目標；6M Roadmap 是唯一工程順序與交付規格，Month 1–6 明示為相對順序；Roadmap Hub 只導覽；Version Roadmap 維護成熟度，不代表工程 Gate 順序；Legacy 月份標籤明示為 2026-06-15 歷史交接語境。External Reference 中 2026-07-11 的 Hub Next 建議也明確降為歷史記錄。Product Gate 表的工程內容改為連到對應 6M Gate，避免兩份文件重複維護工程交付清單。未指定計畫起日，也未改目前狀態或 dirty Index。

`system_architecture.md` 尾端 M2 日期化增量已收斂為契約與 QA 入口：UI／worker 生命週期放在 §3，明示 identity 與 fail-closed 流程放在 §4，immutable source／256 分段及全域排序邊界放在 §8，來源資格限制放在 §11。原逐輪實作、測試範圍、效能觀測與未驗事項仍由 [M2 completion QA](../06_qa/BALDR_COMPLETION_M2_20261007.md) 和 [逐段核驗 QA](../06_qa/TECHNICAL_VERIFIED_PARENT_STREAM_20261007.md) 保留；Snapshot 仍是目前進度權威。這次架構文字整理不改產品成熟度或 Roadmap Gate。

## 2026-10-08 QA 收據直達索引

在 [QA README](../06_qa/README.md) 新增 5 條近期閱讀路徑，為 25 份 2026-10-06 至 10-09 tracked 收據補上直達入口；原始收據不搬移、不重寫，索引只標示主題與來源，不宣稱目前狀態。F02 saved-feature gap 收據暫緩加入此索引，待其未追蹤的同主題 review 工作收束後再一起核對路由。未修改 dirty `DOCUMENTATION_INDEX.md`、`PROJECT_SNAPSHOT.md` 或 `APPLICATION_MANUAL.md`。

`docs/05_phases/README.md` 的首次狀態導覽改為 Snapshot 管目前狀態、6M Roadmap 管工程順序、Roadmap Hub 僅導覽；當時尚未搬動 Phase 原文。後續逐檔生命週期核對及歸檔結果見下文。

隨後將 13 份 Historical Phase／SOP 原文按原相對層次移入 `docs/09_archive/`，內容 bytes 不改；各原路徑改為短轉址，維持 Phase 2 strategy spec 及舊清冊的入口。Phase root／SOP README 改連 archive 原文，Archive README 新增清單，Structure 更新歸屬；唯一直接 Active 引用仍經舊路徑導向 `PHASE2_ARCHITECTURE.md` 原文。未編輯 dirty Index、Snapshot 或 Manual。

首次整理 Phase 導覽時，逐檔路徑已補齊，`phase3_5_research/README.md` 改為純歷史索引，功能目錄改連 Phase README；該階段尚未搬移原文。後續逐檔生命週期核對與 13 份原文歸檔結果見上文；整段整理均未改動 dirty Index、Snapshot 或 Manual。

`system_architecture.md` 的 F4 Watchlist COW 日期增量已收斂為 QA 導覽；穩定儲存、格式相容與正式 apply 邊界歸入 §4／§8／§11。四份 2026-10-05 原 QA 收據保留原文並由架構 README、QA README 建立主題入口；明確區分隔離工程驗證與正式資料轉換／啟用批准，沒有聲稱已套用正式 store。

`docs/superpowers/README.md` 新增主題閱讀入口，按 Research Lab、scoring、ML、valuation、Portfolio／Watchlist、資料更新／UI 導向現行權威與少量歷史 plan/spec；保留 165 項 manifest，不推定完成狀態。另明示舊外部證據授權、任務 prompts 及日期稽核的 Next Action 只能作歷史追溯，避免被搜尋後誤當現行指令。未移動或改寫 superpowers 原文件。

`docs/08_technical/PARAMETER_DESIGN_IMPROVEMENTS.md` 的標題與前言標明為 Phase 2.5 歷史建議／當時清單，README 不再將其列為現行改進計畫；原建議與完成狀態全文保留，現況導回 Snapshot、6M Roadmap、Score Explanation 與 QA。Index 正有其他工作修改，本批不移動檔案或修改 Index。

將 2024-10-16 `path_isolation_update.md` 歸檔為 `docs/09_archive/PATH_ISOLATION_UPDATE_V1_3_HISTORY_20241016.md`，加上歷史標示；原技術路徑保留轉址，技術／Archive README 同步導覽。2026-10-06 文件目錄快照與舊 Index 歷史中的原路徑刻意保留，連到轉址頁仍可追溯；核心 Index 沒有該檔案的個別條目，故本次不修改正由其他工作編輯的 Index。

## 2026-10-08 Post-V1 QA 歷史歸檔

將 21 份 2026-07 Post-V1 Evidence Pipeline 收據從 `docs/06_qa/` 歸檔至 `docs/09_archive/`，按 Evidence store／review／scheduler 分組建立入口；原文內容保留，舊路徑改為短轉址，已檢查歸檔後的相對連結。QA README 與 Archive README 同步；`DOCUMENTATION_STRUCTURE.md` 明確規定一次性證據先核對再歸檔、不因一次性而刪除。核心 `DOCUMENTATION_INDEX.md` 正有其他工作，未修改；既有路徑仍可透過轉址追溯。當時的 scheduler SOP 與 readiness 不代表目前操作或狀態。

## 2026-10-08 V4 9/7 bounded QA 歷史歸檔

將三份 2026-09-07 V4 data recovery、automated review 與 ML release 收據移至 Archive；原文保留，舊路徑改為短轉址，`V4_DATA_RECOVERY` 中指向 10/03 closeout 的相對連結改為 `../06_qa/` 明確路徑。QA／Archive README 與 Structure 同步；Snapshot 仍是現況權威，9/7 bounded evidence 不用來判斷目前 source／ML qualification。

## 2026-10-08 Full App healthcheck QA 歷史歸檔

將 2026-06-16 的早期 8-workspace Full App 人工 smoke 收據移至 Archive，原文保留、舊 QA 路徑改為短轉址；QA README 標明為歷史快照，Archive README 導向現行 Architecture／Manual。此報告不作目前 UI 操作或狀態依據。

## 一、文件權威邊界（Scoped SSOT）

本專案不再使用單一文件承擔所有最高權威。當文件描述衝突時，先判斷主題，再依主題對應的權威文件處理。

| 主題 | 權威文件 | 判斷規則 |
|---|---|---|
| 目前狀態、本週優先事項、高風險區 | `docs/00_core/PROJECT_SNAPSHOT.md` | 開場與日常工作先看 Snapshot。 |
| 重構完成後產品方向、投資問題、產品能力演進 | `docs/00_core/PRODUCT_ROADMAP_POST_REFACTOR.md` | 定義 bounded advice、Portfolio、Exit、Evidence、Data、ML 與 pruning 產品 Gate；不保存工程 checklist。 |
| 未來 6 個月工程路線 | `docs/00_core/ROADMAP_6M_ENGINEERING.md` | 里程碑、交付物與驗收標準以 6M Roadmap 為準；Month 1–6 是相對順序，進度看 Snapshot。 |
| 外部專案參考、資料源優先序、V1.5-V2.0 版本形狀 | `docs/00_core/EXTERNAL_REFERENCE_VERSION_BLUEPRINT.md` | 作為 6M Roadmap / Version Roadmap companion；不取代 Vision 或目前狀態權威。 |
| V2.0 之後長期產品成熟度 | `docs/00_core/VERSION_ROADMAP_V2_1_TO_V4_0.md` | 維護 V2.1-V4.0 maturity milestone；不代表 6M 工程 Gate 順序，也不取代 Product / 6M Roadmap、Vision 或目前狀態權威。 |
| Roadmap 入口與權威導覽 | `docs/00_core/DEVELOPMENT_ROADMAP.md` | Roadmap Hub 只連結權威文件，不複製 Next、狀態、風險或完整歷史。 |
| 舊 Roadmap 項目處置與移交 | `docs/00_core/LEGACY_ROADMAP_CARRYOVER.md` | 每個 Legacy 項目有唯一處置；移交項目標示新版落點與驗收，舊月份標籤只供歷史追溯。 |
| 系統架構、模組邊界、資料流 | `docs/01_architecture/system_architecture.md` | 架構描述衝突時，以系統架構文件為準。 |
| 理想目標架構與 Current → Target 演進 | `docs/01_architecture/target_system_architecture.md` | Target capability 不代表目前已實作；現況仍回到 system architecture。 |
| North Star、Bounded Advice、Evidence、Success Levels、Non-goals | `docs/01_architecture/system_vision_specification.md` | 不保存詳細 implementation checklist 或完成流水帳。 |
| 目前使用者完整操作流程 | `docs/07_guides/APPLICATION_MANUAL.md` | 9 個頂層工作區、跨工作區流程、安全限制與排錯以本手冊為準；較長的操作補充與受控維運保存在同屬手冊的 `APPLICATION_MANUAL_SUPPLEMENTS.md`，涉及該入口時同步檢查附冊。 |
| 文檔位置與分類 | `docs/00_core/DOCUMENTATION_INDEX.md` | 只作導航，不取代狀態或架構權威。 |
| 文檔生命週期與歸檔規則 | `docs/00_core/DOCUMENTATION_STRUCTURE.md` | 刪除、搬移、歸檔 Markdown 前必須參考。 |
| 歷史 Phase、舊 Done、舊 Roadmap current section | `docs/09_archive/DEVELOPMENT_ROADMAP_LEGACY_2026_06.md` | 只作追溯，不作目前狀態依據。 |

其他專項文件權威：

1. **`PROJECT_NAVIGATION.md`** - 開發者導航權威
   - 三層架構（UI / Service / Domain）的導航說明
   - 功能導航（我要做 X，要去哪裡看？）

2. **`AGENTS.md` / `docs/agents/`** - Codex 與 Agent 指引權威
   - `AGENTS.md` 是 Codex 自動讀取的 repo 指令入口
   - `docs/agents/` 保存完整 Agent 職責、Prompt 與共用上下文

3. **其他專項文檔** - 功能特定權威
   - `docs/02_features/UI_FEATURES_DOCUMENTATION.md` - UI 功能說明
   - `docs/07_guides/APPLICATION_MANUAL.md` - 完整使用手冊
   - `docs/02_features/USER_GUIDE.md` - 進階專題教學
   - `docs/02_features/STRATEGY_DESIGN_SPECIFICATION.md` - 策略設計規格

**衝突處理規則：**
- 若 Snapshot、Product Roadmap、6M Roadmap、Architecture 之間衝突 → 先判斷主題，依上表權威文件修正。
- 若 Index 路徑與實際檔案不符 → 以實際檔案與文件結構規則修正 Index。
- 若 Active 專項文檔仍引用舊 Phase 或舊 Roadmap current section → 更新為 scoped authority；歷史內容移至 archive 或保留歷史語意。
- 無法判斷主題歸屬時，標示「需要確認」，不要自行建立第二套權威。

## 二、變更類型 → 必須更新的文件對照表

### UI / View / Tab 變更

**變更範圍：**
- `ui_qt/views/*.py` 新增/修改/刪除
- Tab 結構變更（新增 Tab、合併 Tab、Tab 順序變更）
- UI 功能新增/修改/移除

**必須更新（Must）：**
- `docs/02_features/UI_FEATURES_DOCUMENTATION.md` - UI 功能說明
- `docs/07_guides/APPLICATION_MANUAL.md` - 新增或改變使用者可操作功能、參數、結果或限制時
- `docs/00_core/PROJECT_SNAPSHOT.md` - 「現在的工作模式」段落（如影響使用流程）
- `docs/00_core/DOCUMENTATION_INDEX.md` - 若新增文檔，需更新索引

**應該更新（Should）：**
- `docs/02_features/USER_GUIDE.md` - 使用者指南（如有操作流程變更）
- `PROJECT_NAVIGATION.md` - 「功能導航」段落（如新增功能）
- `docs/00_core/DEVELOPMENT_ROADMAP.md` - Roadmap Hub（如影響權威入口或歷史導引）

**可選更新（Nice-to-have）：**
- `README.md` - 專案主文檔（如為重大功能變更）

---

### Service / Domain / DTO 變更

**變更範圍：**
- `app_module/*.py` 新增/修改/刪除
- `decision_module/*.py` 新增/修改/刪除
- DTO 結構變更（`app_module/runtime_dtos.py` / `app_module/decision_desk_dtos.py`）

**必須更新（Must）：**
- `PROJECT_NAVIGATION.md` - 「三層架構導航」段落（如架構變更）
- `docs/01_architecture/system_architecture.md` - 系統架構文檔（如架構變更）

**應該更新（Should）：**
- `docs/00_core/PROJECT_SNAPSHOT.md` - 「高風險區」段落（如涉及高風險模組）
- `docs/00_core/DEVELOPMENT_ROADMAP.md` - Roadmap Hub（如影響權威入口或歷史導引）

**可選更新（Nice-to-have）：**
- `PROJECT_INVENTORY.md` - 專案盤點（如為重大模組變更）

---

### 回測 / 推薦核心邏輯變更

**變更範圍：**
- `app_module/backtest_service.py` 修改
- `app_module/recommendation_service.py` 修改
- `backtest_module/*.py` 修改
- `decision_module/scoring_engine.py` 修改
- `decision_module/reason_engine.py` 修改
- Strategy registry / preset / promotion 相關服務變更

**必須更新（Must）：**
- `docs/02_features/BACKTEST_LAB_FEATURES.md` - 回測功能文檔（如回測邏輯變更）
- `docs/07_guides/APPLICATION_MANUAL.md` - 回測模式、參數、結果判讀或 Promote 規則變更
- `docs/02_features/USER_GUIDE.md` - 使用者指南（如操作流程變更）
- `docs/00_core/PROJECT_SNAPSHOT.md` - 「高風險區」段落（這些都是高風險區）

**應該更新（Should）：**
- `docs/02_features/STRATEGY_DESIGN_SPECIFICATION.md` - 策略設計規格（如策略邏輯變更）
- `docs/00_core/DEVELOPMENT_ROADMAP.md` - Roadmap Hub（如影響權威入口或歷史導引）
- `docs/00_core/DOCUMENTATION_INDEX.md` - 若新增文檔，需更新索引

**可選更新（Nice-to-have）：**
- `docs/02_features/UI_FEATURES_DOCUMENTATION.md` - UI 功能說明（如 UI 行為變更）

---

### Agent 文件變更

**變更範圍：**
- `docs/agents/*.md` 新增/修改/刪除
- Agent 職責變更
- Agent Prompt 模板變更

**必須更新（Must）：**
- `AGENTS.md` - 若 Codex 自動讀取入口或強制必讀順序變更
- `docs/agents/README.md` - Agent 總覽（如新增 Agent 或職責變更）
- `docs/00_core/DOCUMENTATION_INDEX.md` - 文檔索引（如新增 Agent 文檔）

**應該更新（Should）：**
- `docs/00_core/PROJECT_SNAPSHOT.md` - 「Tech Lead 的預設任務」段落（如 Tech Lead 變更）

**可選更新（Nice-to-have）：**
- `README.md` - 專案主文檔（如為重大變更）

---

### 使用流程、目前狀態或 Roadmap 變更

**變更範圍：**
- 目前狀態或產品閉環狀態變更
- 工作流程變更（「現在的工作模式」）
- 優先事項變更
- 系統定位變更
- 未來 6 個月工程路線變更

**必須更新（Must）：**
- `docs/00_core/PROJECT_SNAPSHOT.md` - 目前狀態、工作模式、優先事項、高風險區
- `docs/00_core/ROADMAP_6M_ENGINEERING.md` - 若影響 6 個月里程碑、交付物或驗收標準
- `docs/00_core/DEVELOPMENT_ROADMAP.md` - 若新增或調整 Roadmap Hub 的權威入口
- `docs/00_core/DOCUMENTATION_INDEX.md` - 若索引內進度文字過期，需更新

**應該更新（Should）：**
- `README.md` - 專案主文檔（如 Phase 狀態變更）
- `PROJECT_NAVIGATION.md` / `PROJECT_INVENTORY.md` - 若影響開發導航或盤點

**可選更新（Nice-to-have）：**
- `PROJECT_INVENTORY.md` - 專案盤點（如為重大狀態變更）

---

### 資料處理 / 資料架構變更

**變更範圍：**
- `data_module/*.py` 修改
- 資料格式變更
- 資料流程變更

**必須更新（Must）：**
- docs/01_architecture/system_architecture.md - 現行系統資料流與資料層架構（架構變更時）
- docs/03_data/DATA_FETCHING_LOGIC.md - 現行來源、欄位與獲取邏輯
- docs/03_data/daily_data_update_guide.md - 使用者更新流程（流程變更時）
- `docs/03_data/DATA_FETCHING_LOGIC.md` - 資料獲取邏輯（如資料獲取邏輯變更）
- `docs/03_data/daily_data_update_guide.md` - 每日資料更新指南（如更新流程變更）

**應該更新（Should）：**
- `docs/00_core/DOCUMENTATION_INDEX.md` - 若新增文檔，需更新索引

**可選更新（Nice-to-have）：**
- `docs/02_features/USER_GUIDE.md` - 進階使用者指南（如影響使用者操作）
- `docs/07_guides/APPLICATION_MANUAL.md` - 完整操作手冊（如影響使用流程、參數、結果判讀或安全限制）

---

### 容量 / retention / immutable artifact 清理

**變更範圍：**
- 正式 output、immutable run、模型 publication、checkpoint 或大型 QA artifact 的刪除／搬移
- retention 規則、保留數、current pointer、dependency closure 或 recovery 語意變更
- 容量 blocker 的建立或解除

**必須更新（Must）：**
- `docs/06_qa/<DATED_CLEANUP_AUDIT>.md` - owner 授權、exact scope、before／after bytes、全部刪除／保留 ID、pointer／hash、依賴、不可逆性、recovery 與 post-check
- `docs/00_core/PROJECT_SNAPSHOT.md` - current capacity、readiness 影響、stale status supersession
- `docs/01_architecture/system_architecture.md` - 若改變 retention／pointer／custody／tombstone 邊界
- `docs/00_core/DOCUMENTATION_INDEX.md` - 新增 durable audit 入口

**應該更新（Should）：**
- `docs/07_guides/APPLICATION_MANUAL.md` - 若使用者日後需判讀、執行或排錯 retention／preflight
- `docs/00_core/ROADMAP_6M_ENGINEERING.md` - 若容量影響 Gate／里程碑／production canary
- 既有 readiness／runbook 文件 - 保留歷史 ID，不偷換；artifact 已刪時新增 tombstone／supersession

**固定安全檢查：**
- 不破壞 raw source；不對 broad root／wildcard 做遞迴刪除
- 先做 untruncated inventory、active lock／process、repo reference、pointer 與完整 dependency closure 檢查
- resume deletion 與 complete-run deletion 分開核准；明示只能重算或冷 archive 的 recovery 界線
- read-only inspector 的 `automatic_delete_allowed=false` 不因一次人工授權而變成長期自動刪除權

---

### 策略設計 / 策略規格變更

**變更範圍：**
- `docs/strategies/*.md` 新增/修改/刪除
- 策略邏輯變更
- 策略參數變更

**必須更新（Must）：**
- `docs/02_features/STRATEGY_DESIGN_SPECIFICATION.md` - 策略設計規格（如策略規格變更）
- `docs/00_core/DOCUMENTATION_INDEX.md` - 若新增策略文檔，需更新索引

**應該更新（Should）：**
- `docs/02_features/USER_GUIDE.md` - 使用者指南（如影響策略使用）
- `docs/02_features/BACKTEST_LAB_FEATURES.md` - 回測功能文檔（如策略回測變更）

**可選更新（Nice-to-have）：**
- `docs/00_core/DEVELOPMENT_ROADMAP.md` - Roadmap Hub（如為重大策略方向或入口變更）

---

### 文檔結構 / 文檔組織變更

**變更範圍：**
- 新增/刪除/重組文檔
- 文檔索引結構變更

**必須更新（Must）：**
- `docs/00_core/DOCUMENTATION_INDEX.md` - 文檔索引（必須反映最新結構）
- `docs/00_core/DOCUMENTATION_STRUCTURE.md` - 若資料夾歸屬、刪除/歸檔規則、文件生命週期有變更

**應該更新（Should）：**
- `docs/00_core/PROJECT_SNAPSHOT.md` - 「指定權威文件」段落（如權威文件變更）

**可選更新（Nice-to-have）：**
- `README.md` - 專案主文檔（如為重大結構變更）

## 三、Documentation Definition of Done（DoD）

文件更新完成必須滿足以下所有條件：

### 必須條件（Must）

1. **所有 Must 優先級的文件已更新**
   - 根據「變更類型 → 必須更新的文件對照表」檢查
   - 所有標示為 Must 的文件都已更新

2. **Scoped Authority 一致性檢查通過**
   - `PROJECT_SNAPSHOT.md` 的目前狀態與本週優先事項合理反映當前工作。
   - Snapshot 的近期工作能對應 6M Roadmap 中的 Gate 與依賴；未設定計畫起日時，不將相對月份推斷成目前月份。
   - Roadmap Hub 正確連到 Snapshot、Product Roadmap 與 6M Roadmap，不複製任何一份文件的 Next 或狀態。
   - `system_architecture.md` 的架構描述不落後於 Snapshot 的已完成能力。
   - `DOCUMENTATION_INDEX.md` 包含新增、搬移或歸檔的 Markdown。
   - 若發現不一致，必須依主題權威文件修正，而不是一律回寫 Roadmap。

3. **文件結構已更新**
   - 新增/刪除/搬移 Markdown 後，`DOCUMENTATION_INDEX.md` 必須同步
   - 若文件分類或刪除規則改變，`DOCUMENTATION_STRUCTURE.md` 必須同步

4. **相關使用指南已更新**
   - 若變更影響使用者操作流程，`docs/07_guides/APPLICATION_MANUAL.md` 必須更新
   - 若變更影響進階專題教學，`docs/02_features/USER_GUIDE.md` 必須更新
   - 若變更影響 UI 功能，`docs/02_features/UI_FEATURES_DOCUMENTATION.md` 必須更新

5. **Manual 完整性 Gate 已通過**
   - 每個使用者可見工作區都有入口與前置條件。
   - 每個可操作功能都有步驟與參數意義。
   - 結果頁有判讀方式，不只列出功能名稱。
   - 危險操作、不可逆行為與目前限制有明確警告。
   - 至少包含常見失敗與排錯入口。

6. **變更日誌已記錄**
   - 根據 `docs/agents/shared_context.md` 的「更新記錄 / 變更日誌規範」記錄變更
   - 若存在變更日誌文件（如 `docs/UPDATE_LOG_*.md`），需記錄變更

### 應該條件（Should）

1. **所有 Should 優先級的文件已更新**
   - 根據「變更類型 → 必須更新的文件對照表」檢查
   - 所有標示為 Should 的文件都已更新

2. **架構文檔已更新**
   - 若變更影響系統架構，`docs/01_architecture/system_architecture.md` 或 `PROJECT_NAVIGATION.md` 已更新

3. **專案主文檔已更新**
   - 若為重大變更，`README.md` 已更新

### 可選條件（Nice-to-have）

1. **所有 Nice-to-have 優先級的文件已更新**
   - 根據「變更類型 → 必須更新的文件對照表」檢查

2. **專案盤點已更新**
   - 若為重大結構變更，`PROJECT_INVENTORY.md` 已更新

---

## 一致性檢查清單

每次文件更新後，必須檢查以下一致性：

### Snapshot ↔ Roadmap Hub ↔ 6M Roadmap 一致性
- [ ] Snapshot 的近期優先事項可對應到 6M Roadmap 的 Gate／依賴；沒有明確起日就不宣稱當前 Month N。
- [ ] Roadmap Hub 連結正確指向 Snapshot、Product Roadmap 與 6M Roadmap，且不複製 Next 或狀態。
- [ ] Snapshot 的高風險區涵蓋 6M Roadmap 近期任務的高風險模組。
- [ ] Product Roadmap 定義產品問題與 Gate；6M Roadmap 只轉成工程交付、依賴、測試與 Exit Criteria。
- [ ] Vision 只保存 North Star / Policy / Evidence / Success / Non-goals，不複製詳細工程 checklist。
- [ ] Current Architecture 與 Target Architecture 清楚分開；Target-only 模組不得寫成已存在。

### Index ↔ Scoped Authority 一致性
- [ ] Index 的進度描述不與 Snapshot、6M Roadmap 或 Architecture 衝突。
- [ ] 文檔索引完整（所有新文檔已加入索引）

### 專項文檔 ↔ Scoped Authority 一致性
- [ ] UI 功能描述與 Snapshot / UI docs 一致。
- [ ] 完整操作手冊與目前 9 個工作區、按鈕啟用狀態及工作模式一致。
- [ ] 進階使用者指南與完整操作手冊不衝突。
- [ ] 架構文檔與目前模組實際邊界一致。

---

## 容易被忽略但必須更新的文件清單

以下文件在變更時容易被忽略，但根據變更類型，必須檢查：

### 所有變更類型都必須檢查

1. **`docs/00_core/PROJECT_SNAPSHOT.md`**
   - 當變更影響「現在的工作模式」時 → 必須更新
   - 當變更影響 Phase 狀態時 → 必須更新
   - 當變更影響優先事項時 → 必須更新
   - 當變更涉及高風險區時 → 必須更新

2. **`docs/00_core/DOCUMENTATION_INDEX.md`**
   - 當新增/刪除文檔時 → 必須更新索引
   - 當文檔結構變更時 → 必須更新索引
   - 當進度描述過期時 → 必須依 Scoped Authority 更新

3. **`docs/00_core/DOCUMENTATION_STRUCTURE.md`**
   - 當新增/刪除資料夾時 → 必須更新資料夾歸屬
   - 當刪除 Active Markdown 時 → 必須確認符合 Delete 條件
   - 當文件被改為 Historical 時 → 必須確認是否應移入 `09_archive/`

4. **`docs/00_core/DEVELOPMENT_ROADMAP.md`**
   - 當 Roadmap Hub 的權威入口或連結目標變更時 → 必須更新。
   - 不再把完整歷史 Done、長期架構細節或所有風險都塞回本文件。

5. **`docs/00_core/ROADMAP_6M_ENGINEERING.md`**
   - 當 6 個月工程方向、月度里程碑、交付物或驗收標準變更時 → 必須更新。
   - 當只是單日完成小修復，且不影響 6 個月方向時 → 不需要更新。

### 特定變更類型必須檢查

6. **`PROJECT_NAVIGATION.md`**
   - 當架構變更時 → 必須更新「三層架構導航」
   - 當功能變更時 → 必須更新「功能導航」

7. **`README.md`**
   - 當為重大功能變更時 → 應該更新（雖然優先級較低，但容易被忽略）

## 使用說明（給 Documentation Agent）

1. **收到變更請求時**：
   - 根據「變更類型 → 必須更新的文件對照表」識別需要更新的文件
   - **特別檢查「容易被忽略但必須更新的文件清單」**
   - 標示優先級（Must / Should / Nice-to-have）

2. **執行 Coverage Pass 時**：
   - 列出所有需要更新的文件清單（包括容易被忽略的文件）
   - 檢查 Snapshot / Roadmap Hub / 6M Roadmap / Architecture / Index 一致性（使用下方「一致性檢查清單」）
   - 標示需要更新的具體段落

3. **執行 Patch Pass 時**：
   - 僅更新已確認的 Coverage 清單中的文件
   - 確保所有 Must 優先級的文件已更新
   - **特別確保 Snapshot / Roadmap Hub / 6M Roadmap / V2.1-V4.0 Roadmap / Architecture / Index 已更新並一致**

4. **完成後驗證**：
   - 執行「一致性檢查清單」
   - 確認所有 DoD 條件已滿足
   - **確認所有容易被忽略的文件已檢查並更新（如適用）**

---

**最後更新**：2026-10-08

## 更新記錄

- 2026-10-08：校正 Scoped SSOT 的產品、工程、現況、成熟度與歷史移交邊界；將 Hub 定義為純導覽、6M 月份明示為相對順序，並以 6M Gate 連結取代 Product Roadmap 重複維護工程交付清單。未修改當前狀態或 dirty Index。
- 2026-08-30：補入 P0／Evidence／Paper／Formal／Runtime／Performance／Data Update refresh 文件，並把 UI 舊 readiness artifact marker、週末 freshness 語意與最新測試 inventory 納入 coverage。
- 2026-09-10：補入 V4.1 A 線推薦機率校準的 QA handoff、Snapshot、Current architecture、Manual 與 Index；確認 20／5 outcome contract、walk-forward split、整數 bp calibration、read-only DB boundary 與自然 forward evidence 尚未成熟的 not-evaluable 狀態。chip／funding、industry、PIT theme 保持 deferred，沒有回填歷史 event。
- 2026-09-12：補入 V4.1 A 線第二輪歷史研究與候選方法包的 QA handoff、Snapshot、Current architecture、Navigation、Manual、Runbook 與 Index；新增逐列 manifest、gap／candidate coverage、自然時間分類與 create-only frozen artifact，確認正式 DB 僅 query-only 讀取且沒有 promotion／formal writer 變更。
- 2026-09-30：新增七項排程修復當日 QA，並將 Paper EOD no-work、queue historical diagnostic proof、Evidence #3 engineering readback／business degraded、Bank #1 failure／#2 Quick barrier、Formal denominator QA、fundamental dry-run、PIT 1,932／1,988 taxonomy mismatch 與 ML forward 9/30 child blocker 同步至 Snapshot、Current architecture、Application Manual、QA README、scheduled README。DOCUMENTATION_INDEX 已有 QA 入口；QA 同時保留 02:12 初始 inventory 及 04:23:28 PDT 最新 21-task native matrix，沒有宣稱自然 Quick 已 terminal 或全鏈通過。
- 2026-08-29：新增容量／retention／immutable artifact 清理的文件 coverage、custody、pointer／dependency、tombstone 與安全檢查要求。
- 2026-07-06：新增 `VERSION_ROADMAP_V2_1_TO_V4_0.md` 的 scoped authority 邊界，定位為 V2.0 之後長期版本階梯 companion。
- 2026-07-11：新增 Post-Refactor Product Roadmap、Target Architecture 與新版 Vision scoped authority；補充 Product / Engineering、Current / Target 一致性 Gate。


## 2026-09-07 專案整併覆蓋

[本輪查核](../06_qa/PROJECT_CONSOLIDATION_REVIEW_2026_09_07.md) 保存精確回滾與驗證。Current architecture 記錄共用分析流程及保留政策；tests_readme、manual README 與測試分類摘要同步移除失效路徑；PROJECT_INVENTORY／PROJECT_NAVIGATION／DOCUMENTATION_INDEX 指向同一報告與[LUNA 執行 companion](../09_archive/LUNA_PARALLEL_PLAN_2026_09_07.md)（歷史歸檔）。

本輪未變更 UI 或正式推薦行為；新增的是 research-only CLI 與 Manual 操作說明，核心金融結果只使用整數 bp／Decimal。A／B／C 後續使用者功能變更仍須由對應 owner 同步。不得以清理報告、sample 或 replay 取代 Snapshot 或正式 Gate。


### 2026-10-06 UX21 source/store/daily coverage

source adapter／sealed outcome 保存與只讀日報→system_architecture、APPLICATION_MANUAL、UX21_SOURCE_STORE_DAILY_20261006；Qt outcome receipt入口→UI_FEATURES_DOCUMENTATION；測試→FEATURE_TEST_ROUTING_MATRIX。全產品9stage/24UX仍1/7/1與2/20/2，有限工程、程式缺件與外驗分列QA，不升格done。


### 2026-10-06 UX22 公平比較 coverage

Must已同步：Manual入口／步驟／policy與bundle／結果／安全限制／排錯；Snapshot實際狀態；current architecture exact讀取與ML邊界；Navigation／Index新入口；QA routing與tracked QA。原plan僅追加，raw proof在output/qa/ux22_fair_comparison_20261006，不stage。產品／6M／長期／target無方向或部署改變，UX22仍partial，既有gate不重開。


### 2026-10-06 UX23 隔離工程狀態

Manual 已覆蓋 preview／明示 save／exact read／stop、參數與 DTO 匯出、三軸判讀、版本失配／缺件／容量／殘件與安全限制；Snapshot 與 QA 區分工程 partial、自然成熟／漂移／採用／效果缺口。architecture／navigation／index／測試路由同步，不更動產品方向或正式部署契約。


### 2026-10-06 UX08 推薦保存圖表入口與驗證

[推薦writer→保存圖／精確表收據](../06_qa/UX08_RECOMMENDATION_SAVED_CHART_20261006.md)；Manual入口／步驟／參數／缺件／安全／排錯同步。新增pure helper15案例、writer／新程序／scheduled日期／來源失配及實際offscreen取消重試stale；既有execution、daily保存圖、read service／projection／技術歷史／shared consumer／研究畫面／scheduled日期，去重182相關案例。Workbench85／validator25+4skip／mypy819／compile／quant通過。UX08整項partial，viewport／CSV lanes未採納，不新增done。


### 2026-10-06 UX08 可操作viewport

[縮放／平移／重設與日期槽hover整合收據](../06_qa/UX08_VIEWPORT_INTEGRATION_20261006.md)：全量精確表／完整同身份保留、未知與source版本切換reset，115相關通過、V5兩項基線失敗另記；Manual／架構／Snapshot同步，UX08仍partial。


### 2026-10-06 明示市場CSV consumer／CLI

[隔離preview→明示接受→execute與canonical收據整合](../06_qa/MARKET_CSV_EXPORT_INTEGRATION_20261006.md)：192synthetic、深路徑88重複驗、修正錯名／假完成；完整Manual步驟／參數／判讀／排錯／Windows與真分享限制同步，無正式啟用，不增加done。


### 2026-10-06 UX23 registry readonly 整合補記

UX23 registry integration：Manual 操作／限制、QA UX23_REGISTRY_INTEGRATION_20261006、Snapshot／目前架構同步；無 UI 與方向變動。
