# 全 repo 文檔整理驗收（2026-10-06）

> Fixed code HEAD：`07da90c164d762966302008c0be8efbb0d9b4cfe`。只改文檔；功能 audit 分開使用 `output/qa/baldr_full_function_audit_20261006/`，本輪不冒稱全產品功能已驗。

## 落地成果

- 原 993 份 tracked 文檔完成路徑／SHA／分類盤點；[全文件目錄](../09_archive/DOCUMENTATION_CATALOG_20261006_HISTORY.md) 提供 root、docs 與 module 說明的可達入口。完全相同 bytes 的重複為 0，沒有因主題相似刪除設計或驗收證據。
- Snapshot 改為當前 bounded 狀態，Index／docs README 只維護導航；三份原累積全文封存，[old→new manifest](../09_archive/DOCUMENTATION_REORGANIZATION_MANIFEST_20261006.md) 保存日期、superseded-by 與恢復。原 bytes 本機備份另存；Git baseline 可恢復 tracked 原文。
- 開發 plans／specs 原地歸檔，以 lifecycle manifest 連回現行權威，保留 QA 歷史交叉引用；原 plan 不因日期或未勾選被取消。
- 唯一 Danny Quant plan 原 bytes 快照核對，原路徑不變。4461 份 ignored plan／QA text 的 metadata 初盤點保存於本輪 audit；最終盤點為 4502 份（排除本輪 audit，其他驗收工作持續產生紀錄）。原 raw／JUnit／receipts／失敗場景不搬不改。
- [資產登記](../03_data/STORAGE_ASSET_REGISTER_20261006.md) 標示 C／D／E 用途、生成來源、引用、量測日期／容量、owner unknown、保留與恢復。cleanup terminal 只有 8 個空目錄、0 bytes；其他候選保留，沒有釋放 50.6 GiB。
- 已修 7 個原失效檔案連結與 2 個 anchor。refactor 舊 code 指向歷史恢復 mapping，缺失 fixture 保留原 SHA／bytes 與 missing，不用另一份 fixture 冒同 bytes。
- 目前治理文件四處「8 個工作區」已更正為 9，逐項對照 fixed code `ui_qt/main_window_coordinator.py` 的 `WORKSPACE_DEFINITIONS`；僅更正文案，不改導航或角色流程。

## 檢查與原始證據

本機 audit 固定：`output/qa/baldr_documentation_reorganization_20261006/`。

| 檢查 | 命令／證據 | 結果與限制 |
|---|---|---|
| 初始 Git | `git status --short`、`git branch -v`、`git worktree list` | clean；只 dev／main，一 worktree；未新建或 push |
| 全文件／ignored 歷史盤點 | `.venv/Scripts/python.exe .../reorganize.py`、`catalog.py`；CSV manifests | tracked SHA／分类；ignored 僅 metadata、無來源／私人 DB 內容 |
| local file links | `.../check_links.py`；`link_check.json` | 初始 7 missing；最終 1002 Markdown 檔／4918 local links／0 missing／0 bytes 相同重複。排除 fenced code、外部連結與 raw prose path |
| anchors | `.../check_anchors.py`；`anchor_check.json` | 初查 91／2 unmatched，修正後 92／0；GFM Unicode slug approximation＋explicit anchors |
| 可達與孤頁 | `.../check_reachability.py`；`reachability_check.json` | 最終 1005 text 文件全由 root README 可達／0 orphan；catalog 導航不等於 semantic 正確性 |
| 編碼 | `.../check_encoding_scoped.py`；`encoding_check_scoped.json` | 1007 檔 UTF-8（992 無 BOM／15 有 BOM），0 invalid／0 mojibake；使用原 audit function 加 tracked 白名單，避免 recursively 掃 output／private |
| 唯一 plan | `unique_plan_backup.json` | SHA／bytes 與原件逐 byte 相同；沒有修改或冒完成 |
| 全文封存完整性 | `.../check_preservation.py`；`preservation_check.json` | 3 份原 bytes SHA 核對、除新標頭／連結目標外全文相同；原 newline 備份不變，封存 Windows 重複換行已修正 |
| 產品碼隔離 | 最終 `git diff --name-only`／commit changed list | 28 個 root／docs Markdown 路徑；無產品程式／測試／assert／公式／Task／資料差異 |

沒有 UI／產品 Python 修改，本輪不重跑 UI union、mypy 或金融測試。原功能首紅與後續精確重驗仍是其原 QA 收據；文檔檢查不能把那些 raw 改為全綠。

## Graphify

已核本機 `graphifyy 0.9.11`。受控 snapshot 含 993 份 root/docs Markdown／text 候選及 967 份 production Python，source snapshot 時點 20:12:50 UTC；SHA256 `10c01f2a36c44615bb78047283e372b3a7feb4d518da152a973d804e9c52eba1`。不含 tests／scripts／fixtures、DB／私人 roots／backup／大 output。超過 skill 的 500 files 門檻已明示並以 15 個模組分區＋cached reconcile；只做本機 AST＋明示 Markdown links，semantic LLM 未執行，extract token 0 input／0 output，無新服務／金鑰／安裝／資料傳輸。

最終圖 **28,876 nodes／89,501 edges／668 communities**；HTML 只呈現 **668 社群 nodes／2,868 跨社群 edges**，不用超過 5000 nodes 的 full viz。4,478 文件與 141 code links 已解析；509 external、21 anchor、293 assets／其他範圍外 target 分報。社群名稱由主要 source_file stem 自動取 2–5 詞，原精度 cohesion 保存 CSV，標籤不代表語意審定。

原 AST **7,511 unresolved edges**（5,529 imports_from／1,968 imports／14 indirect_call；839 distinct missing targets）保留清單，不全猜為 stdlib。scope filter 後展示 extraction dangling／missing／self-loop 為 0；仍有 **8,223 undirected／7,991 directed endpoint collapses** 的平行關係證據，原 AST 與 diagnostics 不抹除。16,725 edges（18.69%）為靜態 heuristic INFERRED，非 semantic LLM／runtime／測試證明。這是圖譜可用範圍，不是原 AST 全 resolved。

CLI 探測因 repo ignore 得零輸入，原 probe 保留；用正式 `graphify.extract.extract(paths, cache_root=INPUT, parallel=True, max_workers=4)` 對明示 Python paths 成功。root review 發現 `../` 未折疊，修成 `posixpath.normpath`；原無效 pre-normalization summary／report 另保留，不冒成功。community label 重讀 exported node-link data，避免對自訂 doc IDs 重複 rekey。

原 `graphify-out` query memory／reflections／learning metadata 前後完全相同：6,993 檔／26 dirs／645,585,051 bytes，digest `bfba4549fc142eb9ff476fd7394a58b2468ef17998bf7b7a754a44e16b83ace8`；未讀取或 hash 舊內容。新結果：本輪 audit `graphify_runs/system_graph/{GRAPH_REPORT.md,graphify_build_summary.json,graphify_unresolved_ast_edges.csv}`，其 `graphify-out/{graph.json,graph.html,community_cohesion.csv}` 維持 ignored。更新方法與安全邊界見 [Graph 維護入口](../00_core/DOCUMENTATION_GRAPH_GUIDE.md)；doc snapshot 是生成時候選版，最終 QA／圖譜說明補登不冒稱已在原 snapshot 內。

## 衝突判讀與剩餘

U1/U2 早期 pending 對目前已接受、舊 worktree 數對唯一 checkout、H20 尚未接通對已啟用保存 cohort，各自歸入原日期化歷史，現況由 Snapshot／Manual 顯式更正。工程完成、personal 使用、自然成熟、機率 head 品質與 gross 報酬 head 分開，不合併為一個 done。產品方向／6M／版本 maturity 保留其 Gate，沒有從新文檔宣告升級。

本輪做全量位置／連結／編碼／分類盤點及可核現況更正；不是重新審定每一份歷史技術敘述或 993 文檔的所有外部連結。外部連結未重新 HTTP 驗證；prose code paths／歷史 command 任意環境可用性與完整 semantic 閱讀仍有 unknown，日期化原文不作新命令授權。

owner／dynamic consumer／部分 uniqueness／重建成本仍 unknown；缺失歷史 fixture 不冒重新生成原 bytes。自然 10 pending／0 成熟、下一 Task 2026-10-07 12:45 UTC 真自動 run、Native 真人、機率 head 未勝 null 與原性能例外仍待／保留。後續 `baldr.exe` 與 main／dev 再評估由另 owner 執行；必要 scheduler、安裝／設定與模型載入操作文檔保留，本輪只 commit dev，不同步 main。
