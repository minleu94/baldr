# 文件知識圖與維護入口

> 2026-10-06。Graphify 是導航輔助；文件內容正確性、原驗收與 Scoped SSOT 不由圖譜成功決定。

目前文件導航以 [文檔索引](DOCUMENTATION_INDEX.md) 與各專區 README 為準；[2026-10-06 全文件目錄快照](../09_archive/DOCUMENTATION_CATALOG_20261006_HISTORY.md) 僅供追溯。圖譜用於跨文件／程式結構關係，來源事實仍應回讀原頁／原 code，不能把推論 edge 當完成證據。

## 安全範圍

只處理受控的 tracked repo 文件與程式結構；exclude 私人／來源 DB、模型 bytes、備份、資料 roots、大型 output、raw QA 與安裝環境。既有 `{REPO}/graphify-out` 含 query memory／reflections／learning，本輪不刪除、不覆蓋。新結果與工具核驗放在 `output/qa/baldr_documentation_reorganization_20261006/` 專用分區，維持 ignored，不 commit 巨型 graph/cache。

執行前核本機已安裝 graphify CLI／interpreter、輸入白名單、輸出位置與 network／模型行為。不得為建圖安裝不明套件、加金鑰、改權限或把資料送到新外部服務；需要這些動作時回報 exact action。本輪授權限定本機可核工具。semantic 關係與 AST／Markdown 明示連結分開，未實際 semantic 抽取就列為限制。

## 更新流程

1. 先完成 Coverage 與原文／唯一證據備份，保存 baseline HEAD、SHA 與移動 mapping。
2. 更新 Scoped SSOT／Manual／索引，再驗 local file links、anchor、重複文件、孤頁與衝突狀態。
3. 原 bytes 與歷史 receipts 保留，graph source list 排除敏感 roots；等待任何 cleanup writer terminal。
4. 使用已核工具向新輸出建圖，或在完整備份後依工具正式 incremental 流程更新；不得盲目覆蓋 query memory。
5. 保存 input manifest、命令／工具版本、nodes／edges／communities、diagnostics／token cost、輸出位置與 unknown。圖譜不提升產品 Gate。
6. 只 stage 本輪文檔／小型維護入口；新 graph JSON／HTML／cache／raw output 按 [Git exclusions](../agents/git_exclusions.md) 維持 ignored。

本輪執行結果、剩餘限制與精確命令見 [整理驗收](../06_qa/DOCUMENTATION_REORGANIZATION_20261006.md)。圖譜若未完成，必須明列 blocker，不能用另一份自製圖冒稱完整 Graphify semantic build。

## 本輪可重用的本機方法

已安裝工具為 `graphifyy 0.9.11`；先用 `graphify --help`／`uv tool list` 核來源，不自動安裝。repo ignore 規則會排除 `output/` 下的 snapshot，普通 CLI 探測得到零輸入，不能當成功。因此本輪對複製到受控 input 的 Python 白名單使用正式本機 API：

```python
from graphify.extract import extract

# paths 是受控 snapshot 內明示的 Python Path 清單，不能是資料 root。
assert all(path.suffix == ".py" for path in paths)
result = extract(paths, cache_root=isolated_input, parallel=True, max_workers=4)
```

分區後以同一明示清單／cache root reconcile 跨檔 import；Markdown links 另以 deterministic parser 抽取，須以 `posixpath.normpath` 折疊 `../`，再確認沒有超出 repo 與來源白名單。原 AST missing endpoints 清單保留，展示圖可以 scope filter，但必須同時報告剔除數與 unknown。

本機 recipe 保存於本輪 audit 的 `prepare_graphify_corpus.py`、`run_graphify_ast.py`、`reconcile_graphify_shards.py`、`build_documentation_graph.py` 與 `verify_graphify_out_unchanged.py`。這些是本輪 ignored 輔助程式；換機器須先核其 input／out 路徑與工具版本，或按本指南建立新 recipe，不把本機 cache 當必要產品依賴。原 graphify 輸出的通用 `graphify update .` 模板不適用本輪保護範圍，不能直接在 repo root 使用。

source-based community labels 只描述主要來源檔，AST 的 INFERRED 關係是靜態 heuristic，不是 LLM 或 runtime／測試事實。超過 5000 nodes 只用 aggregate HTML；原 JSON、diagnostics、raw cohesion 與圖譜 snapshot SHA 維持 ignored。
