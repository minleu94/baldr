# BBP01 BBANDS30 上軌完整具名母體驗證（2026-10-07）

本包沿唯讀派工 `output/plans/baldr_bbp01_parent_v3_dispatch_20261007.md` 與唯一原 plan，固定 base `d89fad0f8057ec7ccf8af15d74a7d16986754ad5`。分支 `lane/baldr-bbp01-parent-v3-20261007`，工作樹 `output/worktrees/baldr-bbp01-parent-v3`。只修改 parent capture、原 snapshot CLI、新專屬測試與本 QA 四檔。沒有修改中央 daily owner/runtime/acceptance policy、config/main、Manual 或 plan。

## Frozen API 與保存契約

`produce_parent_rule_samples(..., contract_version: str | None = None)` 與 `read_parent_rule_sample_readiness(..., contract_version: str | None = None)` 都新增 keyword-only 參數。producer 的 None 在呼叫時解析原 v2；reader 的 None 依保存 parent 判版，只有沒有 `feature_contract_version` 欄位的舊包視為 v2。明示 null／未知版本拒絕；caller 明示 expected version 必須與保存版本精確相同。

v3 常數為 `daily-market-feature-snapshot.v3.bbands30-upper`；沿原 `feature_contract_for_version` frozen descriptor 取得完整 method payload/SHA，來源呼叫原 `load_input(..., include_bbands30_upper=True)`，producer 明示同版。v3 parent body 與 plan 加入 `feature_contract_version`，因此 identity／batch cohort／保存路徑都綁版與方法 SHA；每個已保存 child 的 version／method payload／SHA 必須相同。讀回由原 child readiness 再核 immutable manifest 與 capture，不用 v2 child 補第三方法。

v2 不新增 body／plan／readiness 欄位，原 plan 四項算式、兩方法與 registry SHA `029bcb5ada592619d9748d327eef509db0642a1c6904b652b31f186027025dc5` 保留。原 v2 method-change hooks 的拒絕檢查保留；三方法的選版與統計由保存 descriptor 決定。原 input／snapshot／canonical payload 四固定 pins 以 A01 單一既有 node 再核，沒有重跑 A01 155 項。

CLI 原 `--include-bbands30-upper` 現可搭配 `--parent-universe-config`，明示 opt-in v3；不帶 flag 的發布仍 v2。`--read-parent-identity` 直接使用上述 parent reader：沒有 BB flag 依保存版讀回，有 flag 核 expected v3；不開 DB／source loader／producer。原 capture-root/as-of 配對、output 隔離與 cutoff/as-of 檢查保持。

## 真實隔離工程鏈與界線

合成 SQLite 既存 BB_Upper → 17 股 included＋2 個具理由 excluded → 2 批 → 三方法原 producer/immutable repository/capture → parent receipt → 全新 Python 程序唯讀同 identity/tallies。普通正例有 65 筆 valid OHLC，另兩股分別缺 band／只有末段 29 筆 OHLC，皆為 unknown、不補 0。BB 統計：matched 13／notmatched 2／unknown 2／excluded 2／uncaptured 0，三方法共同 represented denominator 19。這是完整具名 cohort，沒有宣稱全台市場。

fresh interpreter 封鎖 `sqlite3.connect`、source/loader/producer 及 parent producer，仍只讀 parent／receipt／immutable children 得到完全相同 readiness。固定 as_of 重試為 duplicate，parent identity 與所有既存 snapshot/capture bytes／mtime 不變；SQLite 主檔 SHA256／mtime 不變。另驗先發布 v2 再發布 v3，舊 artifacts 的 SHA／mtime 全保留。截止後巨額價格與 band 不影響原 cutoff 的 input fingerprints、features、conditions 或三方法 tallies；原保存 parent 仍可讀。

錯 expected version、非法版號、mixed-version 第二批、wrong-method SHA、缺一批、source revision、取消／安全重試均拒絕或保存 incomplete，不宣告完整分母已收齊。原 21 項 parent 回歸另涵蓋 duplicate members、完整上界 layout、partial receipts、source/universe/method changes、取消後 capture coverage 與錯 child pins。每批 included≤16、最多 16 批／included≤256、每 root 64MiB/4096 entries、原 writer retention／200GiB reserve 均保持，超界拒絕、不截斷。

只做 `close_vs_bollinger_upper` 有限比較，不重算指標。來源只讀同 transaction/revision pin，沒有新金融裸 float；availability/calendar/outcome maturity 維持 unknown，historical PIT/natural/formal/training 資格維持 false。參數程式存在不代表每筆 lineage verified；compression U1 不升完成。自然成熟不是工程 gate。

## 驗證命令與 raw 證據

Python：`C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe`，命令 cwd 均為本 worktree。raw 位於本 worktree `output/qa/bbp01/`，忽略且不提交。

| 收據 | 執行與結果 |
|---|---|
| `v2_2.log/xml` | `-m pytest tests/test_rule_research_parent_capture.py -q -o addopts= --basetemp=C:/Users/archi/AppData/Local/Temp/bbp01_v2_2 --junitxml=output/qa/bbp01/v2_2.xml`；21 passed／17.47s |
| `v3_first.log/xml` | `-m pytest tests/test_baldr_parent_bbands30_upper.py -q -o addopts= --basetemp=C:/Users/archi/AppData/Local/Temp/bbp01_v3_first --junitxml=output/qa/bbp01/v3_first.xml`；新增 cutoff case 前 21 passed／21.13s |
| `cutoff.log/xml` | `-m pytest tests/test_baldr_parent_bbands30_upper.py::test_future_price_and_band_do_not_change_cutoff_features_or_tallies tests/test_baldr_a01_bbands_upper.py::test_v2_all_pins_remain_exact_and_v3_registry_is_detached -q -o addopts= --basetemp=C:/Users/archi/AppData/Local/Temp/bbp01_cutoff --junitxml=output/qa/bbp01/cutoff.xml`；2 passed／2.78s |
| `mypy_first.log` | `-m mypy app_module/rule_research_parent_capture.py scripts/produce_daily_market_research_snapshot.py`；2 source files／0 errors／exit 0 |
| `compile.log` | `-m py_compile app_module/rule_research_parent_capture.py scripts/produce_daily_market_research_snapshot.py tests/test_baldr_parent_bbands30_upper.py`；exit 0 |
| `quant.log` | `scripts/quant_guard_linter.py`；精度／look-ahead AST guard 通過／exit 0 |

原失敗 `initial.log`／`baseline.xml`（16 failed／5 passed）保留；原因是本包新增核對曾誤把 writer 的 status/receipt 結果當成 capture body，已改成 reader 核保存 capture 後才掛 completed identity。修正後原 21 項全通過，未放寬任何 guard／assert。原 source 與容量 policies 未變。

三份成功 JUnit SHA256：v2 `01222e18968cfac54df104b0107734cfef4c0f78e555a2ed100a3be49cc8a5d3`；v3 `de2f4dae9f6bbe011afaa1be02d77fb83bc13ad1e452c048d2433ff101d90dcf`；cutoff/pins `db5cfafe0fa1e7f43bb245d3316e666b0528ce7a3db25db48df56114cf6de7df`。數量不重複累加為全 App 或自然驗收。

最終本機提交後只執行一次 immutable focused union：原 parent 21＋本專屬 22＋A01 原固定 pins 1，共 44 cases；完整 command/exit/raw/JUnit SHA、tested full commit、各檔 base/head blobs 與 working SHA 保存於 `output/qa/bbp01/handoff_receipt.json`，最後 raw 為 `final_focused.log/xml`。以該 receipt 的實際結果為準，前述分批收據不冒充固定 HEAD 單次全綠。兩 source targeted mypy、三 changed Python compile、quant／diff check 的固定 HEAD 收據同目錄保存。沒有全倉 pytest／A01 155／UI mandatory union，本包無 UI 修改。

## 中央剩餘接線與安全接手點

中央 `01a11020` 需接 `rule_research_daily_owner.py`、`rule_research_daily_runtime_adapter.py` 與 `rule_research_observation_acceptance.py` 的明示 contract version。acceptance policy loader 原固定 v2 method SHA 必須按明示版解析；runtime parser 需傳同版到本 frozen APIs。正式 Task 原定義／開關沒有變更，不用保存工程通過冒稱每日正式 caller 已接通。

日常研究列表另由 UI owner 接 v3-only 第三條件、BB 正確 label／why-not／exact 下鑽返回；原 two-MA checkbox／restore allowlist／非 MA20 一律 MA60 的 label 邏輯不能套給 BB。中央同步 Manual、Snapshot／架構／索引、唯一 plan 與新增 test inventory；本包不共編。沒有真資料搬移／原 DB write／Task 修改／ACL／交易／push／清理／fit／artifact deserialize，未知 PIT 不補造。

## 回滾清單

| 檔案 | 類型 | 回滾方式 | 風險 |
|---|---|---|---|
| `app_module/rule_research_parent_capture.py` | 修改 | 由 owner revert 本 lane commit | 新 v3 parent 無法由舊 parent reader 讀取，保存資料保留 |
| `scripts/produce_daily_market_research_snapshot.py` | 修改 | 同一 revert | parent BB flag 恢復拒絕；原 v2 可用 |
| `tests/test_baldr_parent_bbands30_upper.py` | 新增 | 同一 revert | 移除新 scope 驗證 |
| 本 QA | 新增 | 同一 revert | 提交歷史／raw 收據保留 |

回滾前核 dirty tree／中央 caller 依賴與 exact commit，中央同步停用 v3 caller，僅 revert 本 lane 四檔後跑原 parent focused；不得移除 snapshots/captures、正式資料、其他 agent commit 或清理分支。此次未執行回滾。
