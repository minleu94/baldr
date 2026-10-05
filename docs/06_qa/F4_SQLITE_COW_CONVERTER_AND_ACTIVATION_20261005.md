# F4 SQLite COW converter 與 activation 工程收據（2026-10-05）

## 授權與範圍

基線 dev `830f30ac6a027513a4189ca68fea402145e53ffc`。父層明示授權完成 SQLite v1/v2→v3 COW converter、activation／rollback、隔離驗證與本地 commit，不授正式使用者資料遷移。兩位 LunaMax 分別處理 converter／codec 與 activation／service，root 整合 CLI、必要 governance adapter、文檔與有限驗證。其他 owner 三檔保留排除；Paper 不讀不動。沒有新增子代理、全量 regression／producer／ML、Native、排程、清理或 push。

## 行為與邊界

CLI 提供 dry-run／convert／activation-preview／activate／status／rollback。converter 固定 source hash/stat、read lock 與 sidecar 狀態，建立獨立 stage／target，保留原庫。逐版 raw JSON、完整 hash、ID／revision number／metadata／timestamps／source hash／item order 必須相同；lexical codec 保留原 item raw text 及 array 外文字／分隔。import provenance 與 synthetic baseline 明示 v1 缺失歷史，不能補造。新 native revision 仍原 compact codec，原 native chain guard 不放寬。

activation pointer 與舊 `.active` 分離，回復審計保存原模式。fresh service 辨識 canonical path 的明示 marker；錯 marker 不回退 JSON writer。target 正常 append 後以 bounded chain inventory 核驗原 baseline，不固定整個持續變動 DB 的檔案 hash。rollback 保留 target 新 revision、回原 v1 readonly／v2 模式，兩庫及審計均留存。

governance 將 COW JSON 視為 audit metadata，核驗收據／backup／pointer 的 path/hash 綁定，掃兩個 DB 並共用既有 bounded inventory 驗 chain；不把 `scan_complete` 等同歷史 full-payload replay 或正式 activation approval。converter 的逐版精確回放與 activation preview 是另一路驗證。4MiB／32MiB／64MiB／4096 rows 不變，所有 capacity 使用當下中央 policy，不改其他 owner 的政策。

## 驗證結果

限定統一路由 **72 passed**；mypy 793 source files + CLI 1 source file pass。11個變更Python編譯、精度／未來函數AST守衛0違規。17份已接受immutable來源SHA與原舊20-session fixture一致。

CLI隔離實際20-session副本完成dry-run、convert、preview、activate、fresh-service r20讀回、repeat activate、target r21追加、status／governance、rollback、fresh-service source r20讀回、repeat rollback、rollback governance。所有child exit 0，write/network guards無違規；source binary SHA保持，target新r21與雙DB／audit留存。實際case與精確尺寸／SHA見收據，不是正式使用者migration。

本批所授COW實作工程全部關閉，沒有留到下一批設計的實作項；真正使用者store／mode確認及apply批准單列。

## 正式套用另行核准

本批只讀 config 與檔案 metadata：預設 output_root `D:/Min/Python/Project/FA_Data/output`，canonical `watchlist/watchlists.db`、候選 `watchlists.v3-cow.sqlite` 與 `.cow-active.json` 當時不存在，legacy `default.json` 1948 B 存在。沒有讀 JSON 內容、開正式 SQLite 或初始化路徑；現有使用者程序是否以 override 路徑啟動未知。真正套用前須由父層／使用者確認實際來源路徑、目前模式、停止並發 writer、點時容量及明示批准；不能把不存在的預設 SQLite 當已完成正式 migration。這是實際部署批准邊界，並非等自然成熟。

## 交付、原計畫與回滾

raw 根 `output/qa/f4_cow_converter_activation_20261005/` 保留 fixture、phase guards、logs 與收據，不 stage。唯一原 plan 只 append，基線 175392 bytes SHA `05228df2926966d012a54a8ed905618d62b009c71cd9ae3dd7240f9634b26d9a` 保留。程式回滾採 reviewed reverse patch 或新 local revert commit，不 reset/clean、不覆寫其他 owner；資料回復只透過明示 rollback，不刪兩庫／stage／收據。已啟用新庫若有新內容須保留，不能把 Git revert 當資料回復。



## 2026-10-05 F4 SQLite COW converter 與明示 activation（最新）

SQLite v1/v2→獨立v3 COW converter、CLI dry-run/convert/activation-preview/activate/status/rollback、fresh-service pointer與錯marker拒寫、bounded governance audit接線已實作並完成隔離驗證；取代前批「converter尚待工程」狀態。lexical codec保留逐版raw payload/hash、IDs/metadata/timestamps/source/order，v1缺歷史只標synthetic baseline。原4MiB/32MiB/64MiB/4096上限不變，取消、容量未知/不足、bad rows/schema、concurrent writer及身份錯誤failclosed。

限定路由 72 passed，mypy 793 source files + CLI 1 source file pass，11檔compile及精度/未來函數guard通過。已許可舊20-session fixture副本由CLI新程序完成轉換、啟用讀回、target r21追加、rollback回source r20；target r21、雙DB/audit保留，不自動合併。原fixture及17份已接受immutable pins保持相同；無producer重跑、正式資料套用、Native、清理或push。

本批COW實作工程關閉；正式使用者apply另行核准。預設canonical SQLite不存在、legacy default.json存在，實際store/mode/override仍待父層確認；沒有初始化缺失DB或讀真實JSON。F1差1.38pp交父層方向，F2/F3 A/A不重開；新Native/真人/自然資格分列，不能把部署批准寫成等自然成熟。

收據 SHA-256：`actual_cli_roundtrip_receipt.json` `4caed768d54a1b8b891db9ac49dae8baf632f0a7a1e24c1a645b4243f3f6cdc8`；`verification_summary.json` `d0c77b508ddf256ece7bcd83e3943e3bed2cfea2284f260e64b5fd011ea1568a`。精確測試／types／guards logs在raw QA根保留。


| 最終隔離20-session回放項目 | bytes |
|---|---:|
| 原v2 source DB（原樣保留） | 1,302,528 |
| v3 prepared target | 413,696 |
| target新增r21後 | 528,384 |
| 雙庫及receipt／marker／backup合計 | 1,835,546 |
| 41個immutable item objects | 198,513 |
| 21個revision headers | 25,680 |
| active／rollback governance驗證讀取 | 1,821,080／1,821,249 |

初輪Windows DirEntry inode觀測差異以一致Path.stat修正；跨查詢混讀revision的實際競爭以read-only BEGIN transaction固定同一SQLite snapshot，定向競爭測試通過。中間layout-inline實跑發現header重複item原文，已改從immutable refs還原，header不存item_json且逐版raw hash仍完全一致；原中間receipt留actual_cli_roundtrip_receipt_layout_inline_initial.json。Windows stdlib版本查詢在隔離guard前唯讀預熱／cache，後續每個受控child禁止外部程序與網路，沒有放寬應用寫入隔離。上述失敗保留，不以重跑數加總不同案例。


### 最終容量守衛收尾（2026-10-05）

啟用與回退發布 audit／marker 前重新核對當下中央 reserve；容量未知／不足具名拒絕並保留原指標、雙庫與內容。最終限定路由72 passed（focused_root_05.log；另有pytest cache唯讀警告），mypy793及CLI1通過，11檔compile／7產品檔精度與未來函數AST守衛0違規。14個獨立程序實際CLI回放全部exit0、隔離guard0違規，17份immutable來源及原20-session fixture SHA不變。最終case為output/qa/f4_cow_converter_activation_20261005/cli-roundtrip/run-615b305783f9；原失敗與中間收據保留，不替換為自然或正式驗收。
