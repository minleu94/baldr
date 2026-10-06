# P1 Paper ledger 個人路由與 custody 收據

固定 base：`917f6af0387a4d9944b261eddbc0c46e84cf34b2`。分支：`lane/baldr-p1-paper-ledgers-20261006`；worktree：`output/worktrees/baldr-p1-paper-ledgers`。
dispatch 正文 `5d9ddf9d` 是先前提案基準；本次直接指令與 manifest.final_head 明示以上固定 base，四檔 ownership 一致。

## 排他範圍與接口（供 P2）

- `app_module/paper_trade_ledger.py`
- `app_module/paper_equal_weight_benchmark_ledger.py`
- `tests/test_baldr_personal_paper_ledgers.py`
- 本 QA 文件。

```python
PaperTradeLedgerRepository(db_path, *, route=None, personal_paths=None,
                           portfolio_id=None, read_only=False)
EqualWeightBenchmarkLedger(db_path, *, route=None, personal_paths=None,
                           portfolio_id=None, benchmark_id=None, read_only=False)
```

`route: PersonalStoreRoute | None`、`personal_paths: PersonalDataPaths | None`；兩個 identity keyword 為 `str | None`。
route caller 必須明示 exact `portfolio_id == route.identity.key`，benchmark 另明示非空 `benchmark_id`，不從 portfolio 推導。
原 positional `db_path` 與 append／append_many／append_batch／list／list_transitions 公開參數不變；custom 帳戶 trade list 必須傳 `portfolio_id`。
benchmark append 的 entry.benchmark_id 與 list 的 positional benchmark_id 都 exact 匹配 ctor 明示身份。

`read_only=True` ctor 只驗路由，不 mkdir/connect/schema；reader 用 `mode=ro/query_only`，不存在不建庫。
LEGACY_READ_ONLY 未明示 read_only 的 writer ctor 在 mkdir/schema/connect 前拒絕；reader 的 append/_ensure_schema 亦拒。
每次 connect 前重驗 selected exact DB、main/journal/wal/shm 與 custody；只 I/O 使用既有長路徑 renderer。
沒有 route 的舊 writer API 保持相容。明示配置 CLI fail-closed 是 P2 範圍；本包不能替代 CLI 接線。

## 任務入口／回滾清單

執行／測試角色由本 owner 承擔；SQLite custody 屬高風險邊界，僅 isolated synthetic 驗證，正式 writer 未授權。
本次 direct scope 四檔優先於 shared-state/Manual 額外寫入建議；不碰其他 owner。

| 檔案 | 類型 | 摘要 | 回滾方式 | 風險 |
|---|---|---|---|---|
| paper_trade_ledger.py | 修改 | 路由與連線前 custody | 從固定 base 還原此檔 | P2 接口依賴 |
| paper_equal_weight_benchmark_ledger.py | 修改 | 獨立 benchmark 身份與 custody | 從固定 base 還原此檔 | P2 接口依賴 |
| test_baldr_personal_paper_ledgers.py | 新增 | synthetic 正負鏈 | 核對 ownership 後移除新增檔 | 喪失驗證覆蓋 |
| 本文件 | 新增 | 接口／證據 | 核對 ownership 後移除新增檔 | 喪失交接證據 |

依序核 lane 未提交變更、核 P2 尚未依賴、還原本四檔、跑兩 ledger focused 回歸。沒有原始資料回滾或刪除。

## 量化與限制

Look-ahead 自查：不改訊號、features、benchmark mark 的 available_date/price_date 判斷；僅路由儲存邊界。Decimal、bp、cost/schema/query/去重與單交易 fills＋transition 原子性保留。
source_id 三檔、P2 builder/CLI、純 daily runner、shared routes/paths/config/DTO/Snapshot、Manual 與 roadmap 均唯讀。
沒有真資料／帳戶／migration／Task／ACL／Native／交易／fit／push／dev cherry-pick；unknown 與自然資格不提升。

整合 owner 訊息工具兩次回 `invalid turn/start params: AbsolutePathBuf deserialized without a base path`；以上為可直接讀取的早期 API handoff。
P2 必須等待本包 immutable commit/hash，僅以以上 ctor kwargs 注入既有路由。

## 驗證

10 個 focused 檔案共 **172 passed**，含本包 44 cases；兩 production 的 targeted mypy **2 source files 無錯誤**，兩 production＋新增 test compile 通過。
最初 deep fixture 只有 234 UTF-16 units，門檻 assert 正確拒絕；增加六層後正向保存、新程序及 schema readback 全通過，不放寬 >260 assertion。
後續 raw 驗證在本四檔 local immutable commit 執行；結果與 commit／blobs／SHA-256 在根工作區 ignored `output/qa/baldr_p1_ledgers_20261006/receipt.json`，不提交 raw output。

| 驗證 | 證據 |
|---|---|
| 原 ledger／import／reconciliation／synthetic execution producer／benchmark CLI／daily CLI 相容 | pytest.txt、pytest.xml（172 cases） |
| selected 完整 fills＋transition＋benchmark、新程序、同帳戶與同 canonical path、Decimal cost | 新測試一般與六層中文／emoji 路徑正向；sentinel bytes/hash/mtime 前後 exact |
| missing paths/account、wrong domain/account/DB/root、LEGACY_READ_ONLY writer、`..` alias | connect/mkdir 被 sentinel 函數禁止，拒絕先於任何寫入 |
| readonly 缺庫與真 legacy route | 不新建 parent/庫；query_only=1；append/schema writer 拒絕 |
| ctor 前 sidecar alias、ctor 後 main／journal／wal／shm hardlink、Windows junction | 每 logical operation 的連線前 custody 拒絕；sentinel 不變 |
| public db_path 改指 benchmark | schema file existence 查詢／connect 前 exact selected 拒絕 |
| 原交易原子性 | 第二 batch 插入 fills 後撞 transition PK，全 rollback；原 fill/transition 保留 |
| 金融計算、DTO/readback、SQL/schema/source pins | invariants.json（AST/SQL 對固定 base，unowned dispatch source pins exact） |
| typing／syntax／quant | mypy.txt、compile.txt、quant.txt（exit 0） |

命令：根 `.venv/Scripts/python.exe -m pytest` 的指定 10 檔／`-q -o addopts= --junitxml=<raw>/pytest.xml`；`-m mypy` 只兩 production、`--follow-imports=silent`；`-m py_compile` 三 Python 檔；既有 `scripts/quant_guard_linter.py`。
不將 targeted typing 當全 roots mypy、不將 focused pytest 當全 registry PASS；未重跑四用途／Workbench／validator／UI mandatory。

既有 graphify query 使用快取 BFS 639 nodes、1000 token budget，新增 extraction token 成本 0；graph 舊行號只作導覽，實際接口以固定 base 原始碼與本包 diff 為準，不重建 graph。

## 中央 Manual 素材與釋放

P2 caller 保存需注入原 selector 的 route＋selection.paths 與 exact portfolio_id；benchmark_id 由原 caller 明示。PERSONAL paths 缺失、DB override 不符或身份未知，在任何目錄／schema／connect 前停止。
預覽／readiness 使用 read_only=True，不創建庫；不存在回報缺件，不能讀回 legacy。正式 writer 尚未授權；本包只證明 synthetic custody，不代表 P2 CLI／builder 已接線或正式私人儲存已啟用。
本包不允許任意 staging DB：P2 不得把 public db_path 偷轉成 selected；temporary publication custody 必須依原 dispatch 另完成。
完成 raw receipts 後 P1 API／四檔釋放給中央與 P2；沒有任何 dev cherry-pick 或 push。P2 後續修改屬新 owner 包，本 owner 不接續擴 scope。
