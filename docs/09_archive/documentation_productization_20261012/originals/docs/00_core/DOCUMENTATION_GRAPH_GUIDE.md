# 文件知識圖與維護入口

> 2026-10-06。Graphify 是導航輔助；文件內容正確性、原驗收與 Scoped SSOT 不由圖譜成功決定。

> 2026-10-09 本機重驗：`graphify-out/.graphify_python` 指向的 Python 可載入 `graphifyy 0.9.11`；但 `graphify --version` 回報 `uv trampoline failed to canonicalize script path`，`uv tool list` 因工具鎖檔存取遭拒而失敗。因此套件版本已由該 interpreter 確認，CLI 啟動器與工具清單仍未能驗證。執行 recipe 前仍須依安全範圍重新檢查工具與路徑。

目前文件導航以 [文檔索引](DOCUMENTATION_INDEX.md) 與各專區 README 為準；[2026-10-06 全文件目錄快照](../09_archive/DOCUMENTATION_CATALOG_20261006_HISTORY.md) 僅供追溯。圖譜用於跨文件／程式結構關係，來源事實仍應回讀原頁／原 code，不能把推論 edge 當完成證據。

## 安全範圍

只處理受控的 repo 文件與程式結構；exclude 私人／來源 DB、模型 bytes、備份、資料 roots、大型 output、raw QA 與安裝環境。既有 `{REPO}/graphify-out` 含 query memory／reflections／learning，不刪除、不覆蓋。每輪新結果與工具核驗放在日期化的 `output/qa/baldr_documentation_reorganization_YYYYMMDD/` 專用分區，維持 ignored，不 commit 巨型 graph/cache。

執行前核本機已安裝 graphify CLI／interpreter、輸入白名單、輸出位置與 network／模型行為。不得為建圖安裝不明套件、加金鑰、改權限或把資料送到新外部服務；需要這些動作時回報 exact action。本輪授權限定本機可核工具。semantic 關係與 AST／Markdown 明示連結分開，未實際 semantic 抽取就列為限制。

## 更新流程

1. 先完成 Coverage 與原文／唯一證據備份，保存 baseline HEAD、SHA 與移動 mapping。
2. 更新 Scoped SSOT／Manual／索引，再驗 local file links、anchor、重複文件、孤頁與衝突狀態。
3. 原 bytes 與歷史 receipts 保留，graph source list 排除敏感 roots；等待任何 cleanup writer terminal。
4. 使用已核工具向新輸出建圖，或在完整備份後依工具正式 incremental 流程更新；不得盲目覆蓋 query memory。
5. 保存 input manifest、命令／工具版本、nodes／edges／communities、diagnostics／token cost、輸出位置與 unknown。圖譜不提升產品 Gate。
6. 只 stage 本輪文檔／小型維護入口；新 graph JSON／HTML／cache／raw output 按 [Git exclusions](../agents/git_exclusions.md) 維持 ignored。

2026-10-06 的整理結果、當時限制與精確命令見[歷史驗收原文](../09_archive/DOCUMENTATION_REORGANIZATION_20261006_HISTORY.md)；它只代表該次 fixed HEAD snapshot。每輪仍須重新核對當前輸入、依賴與輸出。圖譜若未完成，必須明列 blocker，不能用另一份自製圖冒稱完整 Graphify semantic build。

## 本機受控方法（Graphify 0.9.11；CLI 啟動器不可用）

目前記錄的 interpreter 可載入 `graphifyy 0.9.11`；CLI 啟動器本次無法執行，工具來源清單也因本機鎖檔權限無法讀取，不自動安裝。repo ignore 規則會排除 `output/` 下的 snapshot，普通 CLI 探測得到零輸入，不能當成功。因此本輪對複製到受控 input 的 Python 白名單使用正式本機 API：

```python
from graphify.extract import extract

# paths 是受控 snapshot 內明示的 Python Path 清單，不能是資料 root。
assert all(path.suffix == ".py" for path in paths)
result = extract(paths, cache_root=isolated_input, parallel=True, max_workers=4)
```

分區以同一明示清單／cache root 抽取 AST；若另做全清單 import reconcile，須保存獨立成功收據，未完成時保留跨 chunk 未解析診斷。Markdown links 另以 deterministic parser 抽取，須以 `posixpath.normpath` 折疊 `../`，再確認沒有超出 repo 與來源白名單。原 AST missing endpoints 清單保留，展示圖可以 scope filter，但必須同時報告剔除數與 unknown。

本機 recipe 保存在每輪 audit 的 `prepare_graphify_corpus.py`、`run_graphify_ast.py`、`merge_ast_chunks.py`、`build_documentation_graph.py` 與 `verify_graphify_out_unchanged.py`。這些是 ignored 輔助程式；換機器須先核 input／output 路徑與工具版本，或按本指南建立新 recipe，不把本機 cache 當必要產品依賴。原 Graphify 通用 `graphify update .` 模板不適用本 repo 保護範圍，不能直接在 repo root 使用。

## 2026-10-09 受控刷新結果

固定來源 HEAD 為 `217115f2348e3aa1cdaecce870b034fa66d34d65`。輸入 manifest 僅取自該 commit 的 Git blobs，包含 `docs/` 與 repo 根目錄的 1,475 份 Markdown／文字文件及 1,069 個正式 Python 檔；排除另一 Agent 的 `docs/06_qa/BALDR_F03_PREPARE_ROOT_FOLLOWUP_20261009.md`、`app_module/daily_market_technical_official_disposition_composite_bookmark_v1.py`、tests、scripts、examples、output、Graphify 舊目錄、資料庫、備份、資料根目錄及 untracked agent shared state。2,544 個輸入來源與固定 commit 一致。Manifest 的來源指紋為 `e92d4b74e4f4d8f9180bdc317e6d35e0830190d5fadeb83a063e5349b1583f75`。

使用 Graphify 本機 API 做 AST 結構抽取，另用確定性 Markdown parser 建立明示文件連結；沒有 semantic extraction，沒有 token 費用或 network transfer。全清單 reconcile 執行逾四分鐘未產生結果後停止，改合併 38 個分塊 AST；因此跨 chunk import 未 reconcile。診斷列出 8,116 條端點無法解析的 AST 邊，最後圖只保留來源與目標都存在的邊。這個結果適合導覽及提出回查問題，不是語義完整的程式關係圖或正文核讀證據。

最終圖有 35,299 個節點、102,233 條邊及 990 個 communities。Graph JSON、aggregate HTML、`GRAPH_REPORT.md`、diagnostics、unresolved edges、manifest 與 recipe 均保存在 ignored `output/qa/baldr_documentation_reorganization_20261009/`。原 `graphify-out` metadata 前後一致：7,000 files、26 directories、645,610,308 bytes，metadata SHA-256 為 `ee8800cce274fb1cab612471d0076d6c5e9858f2cda450d9484003dcd68aa911`；只核對 metadata，未讀取或雜湊原圖內容。

source-based community labels 只描述主要來源檔，AST 的 INFERRED 關係是靜態 heuristic，不是 LLM 或 runtime／測試事實。超過 5000 nodes 只用 aggregate HTML；原 JSON、diagnostics、raw cohesion 與圖譜 snapshot SHA 維持 ignored。

## 2026-10-11 前次刷新（歷史）

全 docs 基線分類與逐檔清冊見[文件治理狀態矩陣](DOCUMENT_GOVERNANCE_STATUS_MATRIX_20261011.md)及[逐檔路徑 manifest](DOCUMENT_GOVERNANCE_PATH_MANIFEST_20261011.csv)；各線路的演進、閉環、狀態證據與待核處置見[開發線路矩陣](DEVELOPMENT_LINE_EVOLUTION_MATRIX_20261011.md)。線路矩陣與導覽修訂已精確路徑提交；本輪最終 Graphify 使用其後的 clean HEAD，且只取 clean tracked 文件及核准的正式 Python 原始碼，dirty／受保護路徑不讀取、不納入。

前一批固定於 `fbb698aa` 的刷新與 build summary 保存在 ignored `output/qa/baldr_documentation_reorganization_20261011_final2/`；較早固定於 `ecfb720b` 的結果留在 `output/qa/baldr_documentation_reorganization_20261011/`。這些是 10/11 的歷史輸出。每次後續文件修訂都須另建獨立 run 目錄，不覆寫前次結果或根目錄既有 `graphify-out`；每批的輸入 manifest 與 build summary 記錄實際 HEAD、來源指紋、Graphify 版本、nodes／edges／communities 及 diagnostics。本流程使用本機 AST 與確定性 Markdown 連結，不做 semantic extraction 或 network transfer；圖譜仍是導航輔助，不提升任何產品 Gate。

## 2026-10-12 全治理範圍後刷新

所有文件修訂、逐檔清冊與矩陣提交後才刷新 Graphify。早期的 `output/qa/baldr_documentation_reorganization_20261012_governed_final/` 曾排除受保護補完計畫、預期 1,516 份文件；那是當時的暫時範圍。前輪 `d929e003` 的定版驗證實際納入該計畫的已提交 Git blob，為 1,517 份文件，收據在 `output/qa/gf613_verification/`。歷史輸出不覆寫；不把另一任務正在編輯的未提交內容納入 snapshot，也不修改該內容。

本次五項治理修復新增一份 QA 收據；最新定版驗收入口為 ignored `output/qa/gov5gf2/graphify_final_verification.json`，固定 HEAD 必須與最後提交一致，只有 `passed=true` 才成立。預期 1,518 份文件及 1,087 個 production Python 檔：文件包含 `docs/` 受控類型及 `docs/` 外全部 26 份 tracked Markdown；僅排除狀態矩陣與逐檔 manifest 兩份 self-reference 輸出。開發線路矩陣、補完計畫的已提交 blob 均納入；不以 Graphify 內容提升產品 Gate。tests／scripts／examples 的程式、既有圖譜、DB、備份及資料根不抽 AST，其中屬治理範圍的 tracked Markdown 仍納入文件節點。

`6d18a4d6` 的 production code 已於 `output/qa/gov5gf/` 重新抽取本機 AST。只改文件的後續定版可以重用這次抽取，但必須先驗前次收據通過、所有 code path／blob OID map 完全相同，並記錄原 AST hash／來源 HEAD；任一程式碼不符即拒絕重用。Markdown links 每次重新抽取，不以舊文件圖取代新導覽。build summary 與最終 verifier 核來源 fingerprints、local links、dangling／missing endpoints，未解析 AST edges 另列診斷；chunk imports 未 reconcile，不宣稱語義完整性。原 root `graphify-out` metadata 必須前後不變。HTML 僅社群摘要，完整關聯保存 JSON；本機 AST／明示 links 無 semantic model 或 network transfer。
