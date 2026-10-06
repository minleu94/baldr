# P2 Paper producer selected routing 合成驗收（2026-10-06）

## 固定基準與排他 ownership

唯一主 owner：01a11020-88c2-7506-acc3-d51ecb674032；未派子 agent。固定中央基準 e1857a310daa3b4803bb9c9fd1a06a7d31079fea。P1 原 commit d4d32fe277e40e2649733d3ef193e38e8672135a 與中央 pick e1857a31 的兩 ledger、新 test／QA 四個 blobs 相同（四檔 git diff 空）。

專屬 branch：lane/p2-paper-producers-20261006；worktree：<repo>/.t/p2-paper-producers。從 immutable commit 建立，未取 dirty tree。派工正文 BALDR_NEXT_OWNERSHIP_DISPATCH_20261006.md 與中央 output/qa/baldr_next_dispatch_20261006.json 已讀；manifest 保存舊 source pins，ownership 以正文與本次直接派工為準。

僅以下五檔可寫：

- app_module/paper_equal_weight_benchmark_builder.py
- scripts/run_paper_portfolio_daily.py
- scripts/build_paper_equal_weight_benchmark.py
- tests/test_baldr_personal_paper_producers.py（新增）
- docs/06_qa/BALDR_PERSONAL_PAPER_PRODUCERS_20261006.md（新增）

P1、pure daily runner、Snapshot repository、shared paths/routes/config、main/UI/Manual 與 source_id 三檔未修改。中央未修改，不 cherry-pick/push、Task/migration/正式寫入/資格升格。精確 ownership 優先，shared state／Manual素材記於本 QA 供中央接手，不擴寫其他檔。

## API 與 custody

Builder ctor 保留原 keyword 介面，增加 route=None／personal_paths=None；無 route 的 benchmark default 保持 paper-main-equal，有 route 必須 caller 明示 benchmark_id，不從 portfolio_id 推導。

preview/build_entries/commit 原參數保留。write_new_ledger(path, entries, *, route=None, personal_paths=None, portfolio_id=None, benchmark_id=None) 保留原 positional 呼叫。daily.run 原 keyword 參數保留，增 route=None／personal_paths=None；帳戶 exact route.identity.key。baseline 若聲明不同 portfolio ID，建立 state schema 前拒絕。

P1 allowlist 不擴張。P2 GeneratedPaperStaging 綁本次 mkstemp exact temporary、selected target、相同 parent、建立 FD 的 dev/inode，以及 parent inode。逐次 I/O 核 selected target／main／journal/wal/shm、祖先 no-link/junction、canonical path、single-link regular file、main identity、parent identity；只有 I/O 使用既有 extended-length renderer。public 任意 db_path 不能成為 selected staging。

_GeneratedBenchmarkLedger 只替換 connect custody 與 benchmark identity 守衛，schema／append SQL／Decimal／benchmark公式全沿 P1；沒有複製金融 SQL。partial append failure 不出版；Windows rename create-only，其他平台以原子 create-only hardlink建立目標，再移除本次 temporary。競態目標保留；cleanup遇 alias 拒絕刪除可疑檔，保留synthetic證據，不放行整個 parent/root。

status 由 mkstemp FD 寫入、fsync，publication前重驗後 atomic replace selected status；benchmark仍 create-only。

兩 CLI 使用 TWStockConfig 與既有 selector；root-only/mode-only/blank/unknown 拒絕，override exact，不先 resolve掩蓋alias。daily新增 --portfolio-id；selected benchmark需要另明示 --benchmark-id，selected可省略原四個path選項，legacy實際四個path要求保留。市場由原 market config或獨立 --market-db readonly開啟，不從private推導；private/legacy子樹市場拒絕。selected daily忽略 PAPER_EXECUTION_LEDGER_DB，selection／selected writer錯誤只輸出JSON/exit2，不補寫legacy status。

## 驗證與 local evidence

先行六個 affected subset已為104 passed；新增最後三個案例及 readonly guard調整後，正式驗證綁 immutable owned local commit。最終數量、exit codes、raw/JUnit SHA256、owned blobs與readonly pins，見 local output/qa/p2_personal_paper_producers_20261006/receipt.json。raw只local，不stage。

focused subset：

- tests/test_baldr_personal_paper_producers.py
- tests/test_build_paper_equal_weight_benchmark_cli.py
- tests/test_run_paper_portfolio_daily.py
- tests/test_paper_equal_weight_benchmark_ledger.py
- tests/test_paper_portfolio_daily_runner.py
- tests/test_baldr_personal_paper_ledgers.py

正向閉環使用原P1 fill append → selected daily cost投影/Snapshot append/status → 原benchmark writer → 新程序B09 readiness/weekly同root/account/benchmark exact讀回。普通與中文/emoji >260路徑均驗；市場、baseline、legacy sentinel hash/mtime不變，新程序consumer也不改state/cost/benchmark/status。

負例包含preview不寫/confirm=False/readonly writer/取消；future與unknown calendar不建state或提高資格；缺paths/identity/benchmark/任意staging/mismatch/市場private override；post-preview與post-constructor hardlink、junction、lexical alias、temp main/sidecar alias、partial fail與publication race；CLI錯誤不legacy fallback；私baseline缺件不讀legacy；repreview價格變動拒絕出版。疑似alias temporary保留不任意刪除。

targeted mypy使用 --explicit-package-bases --follow-imports=silent，三個changed production roots。四個Python compile、既有quant guard與diff whitespace另落raw。不重全UI/mandatory全量/真排程。Graphify現有corpus可找到builder/CLI節點，但不當freshness或驗收權威，未rebuild。

## 金融與時間自查

只改I/O路由與custody，pure daily runner/P1公式未動。投影 prior_date <= event_date < decision_date，T-1行情、08:30 Asia/Taipei、future/unknown與frozen benchmark保留。原fee/cash Decimal結算與benchmark1050.00在synthetic驗證。新增無financial float；quant白名單AST不等於完整PIT/投資有效性證明。原schema、200GiB/role reserve政策未變。

## Manual素材：中央整合時同步，本包Manual唯讀

成對配置 PERSONAL_STORE_ROOT 與 PERSONAL_STORE_MODE=personal，保留 DATA_ROOT/OUTPUT_ROOT作原市場/legacy定位。daily提供同帳 --portfolio-id，fill/baseline/state/status exact selected；legacy ledger env不採用。benchmark另明示已知 --benchmark-id，先preview再由已授權caller明示 --confirm-build-paper-benchmark；本收據只synthetic，不授權正式writer。

--baseline/--state-db/--ledger-db/--output-ledger若明示必須exact selected；不作搬庫或借legacy。--output-root為原config legacy root，不是另一private writer selector。unknown/future/缺件/取消維持保守判讀。exit2時先核mode/root/account/benchmark/canonical與aliases，不自動migration、刪除、擴權限。PASS不折抵真fills/source acceptance、自然evidence、formal/broker/Advice授權。

## 回滾清單

| 檔案 | 類型 | 摘要 | 回滾方式 | 風險 |
|---|---|---|---|---|
| app_module/paper_equal_weight_benchmark_builder.py | 修改 | selected builder/staging | 限lane還原固定基準blob | synthetic writer接口中斷 |
| scripts/run_paper_portfolio_daily.py | 修改 | daily/state/status/cost custody | 限lane還原固定基準blob | synthetic CLI中斷 |
| scripts/build_paper_equal_weight_benchmark.py | 修改 | selector/exact override/identity | 限lane還原固定基準blob | synthetic CLI中斷 |
| tests/test_baldr_personal_paper_producers.py | 新增 | 正負合成閉環 | 核owner後移除此新增檔 | 失去回歸覆蓋 |
| docs/06_qa/BALDR_PERSONAL_PAPER_PRODUCERS_20261006.md | 新增 | 交接與Manual素材 | 核owner後移除此新增檔 | 失去交接記錄 |

先核lane dirty與其他owner變更，限上述五檔；三修改還原固定基準、兩新增移除，再重跑affected legacy subset。已提交整包可於隔離lane revert本包commit。不清理synthetic原證據/正式資料，不動中央dev/main。交主審查，尚無中央整合/正式升格資格。
