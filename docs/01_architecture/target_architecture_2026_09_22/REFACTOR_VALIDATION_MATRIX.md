# 重構驗證矩陣

> 每個task只跑足以證明該切片的 focused validation；四個 checkpoint 再跑完整相關suite。正式資料、完整ML rebuild、scheduler實跑與model promotion不在本計畫的自動驗證範圍。

## 1. 驗證 bundle

| Bundle | 內容 |
|---|---|
| `V-SOURCE` | `rg` direct/dynamic/string/serialized caller清冊、import DAG、`git diff --check`、changed-file `py_compile`。 |
| `V-REC` | `test_task_loop_03_contract.py`、`test_recommendation_run_support.py`、negative evidence、fundamental filters、ranking service、market/PIT provider與新增characterization。 |
| `V-EXEC` | execution contract/deep-freeze tests、execution coordinator、A/B interleave、empty/failed/cancelled/stale callback。 |
| `V-CODEC` | DTO/legacy/new codec roundtrip、revision/null/Decimal/time/unknown schema、canonical bytes/hash。 |
| `V-PERSIST` | save coordinator、personalization save integration、repository create-only/orphan/concurrency、exact readback與index recovery。 |
| `V-REPLAY` | replay characterization、historical replay、timeline、portfolio backtest的replay/cutoff/factor manifest子集。 |
| `V-UI` | affected recommendation UI tests；再跑 repo強制 `test_ui_qt_update_view_workbench.py`、`qa_validate_update_tab.py`、全指定範圍mypy。 |
| `V-ML-SMALL` | historical snapshot/feature computation、model artifact manifest/loader、recommendation calibration integration、training lineage、shadow boundary。 |
| `V-ML-DIRECT` | direct computation dependency guard、checkpoint provenance/recovery、shared reuse；僅隔離fixture。 |
| `V-SCREENER` | stock screener sqlite reader/first/provider及task-loop-02相關screening tests。 |
| `V-REGIME` | market regime kernels/detector/provider、walkforward regime history與save-after-source-change。 |
| `V-FACTOR` | factor contract/adapters/gate/registry、fundamental/revenue/statement/valuation data與factor packs。 |
| `V-STRATEGY` | strategy threshold modes、params persistence、backtest/walkforward、registry/list/UI strategy selection。 |
| `V-BOUNDARY` | ML shadow guard及新data/domain/app/UI/last-state/schema mapping窄guards；既有4項baseline違規不可被抹掉。 |

## 2. Task matrix

| Task | Unit / characterization | Integration | Persistence | Replay | Architecture | UI | ML | Success proof |
|---|---|---|---|---|---|---|---|---|
| R001 | — | — | artifact inventory | caller inventory | `V-SOURCE` | caller list | ML/class-path inventory | 清冊可重跑、owner/TMP完整 |
| R002 | `V-REC` | recommendation service | — | mode只讀 | numeric oracle | — | annotation baseline | 刻意semantic drift會使測試失敗 |
| R003 | `V-EXEC` | worker/service | — | — | hidden-state inventory | coordinator char | receipt timing char | 所有terminal狀態可區分 |
| R004 | persistence char | save/readback | `V-PERSIST` | legacy load | format inventory | — | receipt refs | 原bytes、failure windows有oracle |
| R005 | replay char | portfolio replay | manifest read | `V-REPLAY` | mode diff清冊 | — | — | 每mode各自固定 |
| R006 | ML char | loader/provider | ML artifact read | — | boundary baseline | — | `V-ML-SMALL`＋`V-ML-DIRECT` | ABI與unknown資產分帳 |
| R007 | contract unit | — | — | — | no-I/O import | — | leaf可import | contract immutable且無逆向依賴 |
| R008 | contract/deep-freeze | execute fixtures | — | — | INV-07/08/09 | — | typed refs | mutation與非法狀態拒絕 |
| R009 | `V-CODEC` | legacy/new read view | bytes/hash | old format | schema guard | — | projection refs | 一份欄位schema、未知revision拒絕 |
| R010 | Prepared input unit | adapter contract | refs only | — | no app import | — | binding validation | pure ML-owned contract成立 |
| R011 | `V-REC`＋`V-EXEC` | old/new entry parity | — | — | façade方向 guard | indirect | `V-ML-SMALL` focused | execution完整、list parity、無遞迴 |
| R012 | codec/store unit | save/query | `V-PERSIST` | legacy read | data store no app import | — | receipt readback | create-only/recovery全部通過 |
| R013 | presenter/coordinator | Qt flow | save caller | — | no last_* search | `V-UI` | projection display | Qt只持execution/read model |
| R014 | wrapper unit | scheduled flow | exact save | — | no last_* in production script | — | receipt透傳 | calendar/clock/order不變 |
| R015 | adapter unit | personalization E2E | `V-PERSIST` | retry read | no producer live state | host smoke | calibration/receipt | save與ACK outcome分離 |
| R016 | query projection | evidence/advice/desk | verified read | historical display | no duplicate decoder | indirect | stored refs only | 無live lookup／recompute |
| R017 | bridge unit | portfolio replay | optional refs | `V-REPLAY` | TMP-REC-04登錄 | backtest indirect | — | typed child execution且算法未變 |
| R018 | provider unit | execute/service | — | historical input | INV-02/03/05 | — | legacy branch untouched | 同source/fallback output parity |
| R019 | pure evaluator | execute parity | — | interactive policy | no-I/O decision | — | rule selection parity | 唯一evaluator產DecisionBatch；C3B/C3C2/C3C3 gate 關閉 REC-01 窄 rule bridge；clocks/error/progress 由 app execution telemetry 邊界列管，ML availability/projection receipt capture 由 TMP-ML-01/R026 列管 |
| R020 | policy/evaluator | portfolio replay | refs | `V-REPLAY` full relevant | no duplicate engine | backtest indirect | — | TMP-REC-04可刪、mode diff保留 |
| R021 | reader/provider | screening | readonly source | — | data→decision direction | market UI indirect | — | `V-SCREENER`、decision無I/O |
| R022 | state transition | RegimeService/save | state file | walkforward | decision無file I/O | regime UI focused | refs unchanged | `V-REGIME`、多日/cooldown parity |
| R023 | data/factor unit | factor service | source records | PIT dates | no data→decision import in slice | — | exclusion unchanged | `V-FACTOR` fundamental subset |
| R024 | data/factor unit | statement/valuation | source records | PIT dates | residual reverse-edge guard | — | eligibility unchanged | `V-FACTOR` full relevant |
| R025 | contract/registry | backtest/optimizer | spec roundtrip | walkforward | one registry/no switch | strategy list focused | — | `V-STRATEGY` |
| R026 | adapter/provider | execute/calibration | receipt | — | explicit prepare path | annotation indirect | `V-ML-SMALL`＋race barriers | projection parity、old data可用 |
| R027 | experiment oracle | isolated process | isolated only | — | path/hash report | — | `V-ML-DIRECT` | PASS/FAIL/INCONCLUSIVE有完整證據 |
| R028 | update job unit | technical publication | isolated writer | — | job/data direction | Update focused | R027＋`V-ML-DIRECT` | identity/timing/bytes完全符合 |
| R029 | old API regression | all migrated consumers | old artifacts | old replay | search/guard zero；canonical rule 無 latest-state 重建、保留 telemetry capture 有 owner/TMP | `V-UI` focused | permanent ABI load | TMP closure與無雙架構；REC-02 兩退出子條件均須通過 |
| R030 | bad-fixture guards | synthetic extensions | codec locality | replay locality | `V-BOUNDARY` | confidence presenter | new feature/old model | 三項extensibility推演通過 |
| R031 | affected unit集合 | full relevant checkpoint | `V-PERSIST` | `V-REPLAY` | `V-SOURCE`＋`V-BOUNDARY` | `V-UI` | `V-ML-SMALL`；按gate `V-ML-DIRECT` | 所有證據、risk/TMP狀態封存 |

## 3. 必跑 checkpoints

### C1 — R012 後：contract／execution／persistence

必跑 `V-REC`、`V-EXEC`、`V-CODEC`、`V-PERSIST`、focused `V-ML-SMALL`。未通過不得開始consumer cutover。

### C2 — R020 後：所有consumer與單一 evaluator/replay

必跑 C1 加 `V-REPLAY`、scheduled、personalization、saved-result readers及affected `V-UI`。同mode任何numeric/order差異必須停止並分類。

### C3 — R029 後：legacy retirement

必跑 C2 加 `V-SCREENER`、`V-REGIME`、`V-FACTOR`、`V-STRATEGY`、`V-BOUNDARY`、old artifact/model class-path readback。搜尋不得只查import，還要查strings與serialized inventory。

### C4 — R031：final relevant regression

重跑C3、changed Python `py_compile`、repo指定mypy/UI三項、`git diff --check`。R027/R028只在授權隔離fixture範圍重跑；不以full-market rebuild作一般closeout。

## 4. 失敗判讀

- characterization在原程式就失敗：先證明是環境／既有baseline或測試錯誤，不能在結構task順手修產品。
- exact numeric/order/hash差異：該task rollback，保存diff；另開bug或行為變更task。
- unknown old artifact/class path：保留檔案與reader/alias，標unsupported/unverified；不得刪除或轉存。
- ML source/hash/timing差異：R027 FAIL，啟動 `AB-ML-01`，R028停止。
- UI強制check與本切片無關但為既有紅燈：記錄exact baseline，仍需跑affected UI tests；不得把整個check移除或allowlist。
