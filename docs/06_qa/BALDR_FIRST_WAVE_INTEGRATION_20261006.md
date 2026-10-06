# 原產品計畫首波整合收據（2026-10-06）

唯一dev owner：`01a11020-88c2-7506-acc3-d51ecb674032`。原需求只沿 `output/plans/baldr_product_experience_plan_20261004.md`（Danny Quant即此原plan）；本文件是有限scope驗收，不是新roadmap。接手base `a42b2cb9df44b2fd928104ae02992b0e557c2a39`，開場tracked clean。

## 接受與保留

有界review接受Astra B01–B15及修正DAG：B12/B13契約與拒絕路徑可先行，不等第二家族／自然成熟；正式source／target comparison仍依合法契約。父層首波鎖B01/B02/B03三Sol獨立worktree，我主線B08一Luna Max；未喚醒舊main／idle lane。

原七有限closed（UX03/04/05/06/09/15/17）、F1改善18.621965821542936%未達20%及Journey8.109s未達8s的已接受例外保留。9stage仍1done/8partial/0pending、24UX仍2done/22partial/0pending；沒有新增整項done或資格。自然累積不是工程gate，unknown不補0，不以fixture授PIT/ML/交易資格。

## 已整合提交與實際scope

| lane／中央 | 接受範圍 | 主線commit／依賴 |
|---|---|---|
| B01 `49da8bd9` | registry三個exact symbols審查／負例，V5日期/OHLCV與足缺fixture | `a4dfed1a145b30bb8514ceab923dad6d0fa39a72` |
| B03 `00a0628a` | 首頁四用途／明示當下股號搜尋、技術詞分層、大盤刷新保收合及缺件三態 | `8ace306e`；lane QA見[B03](BALDR_B03_MARKET_HOME_20261006.md) |
| B08共用IO helper | canonical path不變，Windows UTF16門檻／extended OS I/O、SQLite ro/rw URI | `8f580a68035bf2430af0c6ec42ab52a6c889e03b`；B02獨立lane可cherry此依賴，不重複採納 |
| 中央產品修補 | 個股focus summary漏change與ML遮蔽區塊sufficiency；市場舊indicator測試先明示展開 | 本次中央ownfiles；不改DTO、結論、資格或五問結構 |

registry仍只接受owner提供的sidecar-free一致snapshot，拒live WAL／SHM／journal，不做正式checkpoint。stop receipt仍是隔離投影描述，不是實際modelcontrol。capture現行200GiB與中央20GiB政策差異已確認；本波不降reserve。

### B01真數目

接手ML AST為659 files／11 violations／exit1，舊8＋新3。B01審module import-time/transitive I/O與DTO本體，沿既有exact-symbol allow模式，拒initializer、register／append、trainer、wildcard、namespace與其他caller。新3消除後仍8違例／exit1，不能稱repo pass。舊8分：composer反向app3、maturity verifier1、calibration error1、HistoricalLabelRow/Spec2、current-restated loader1；各自owner／退出條件見lane `output/qa/b01_20261006/handoff.md`。舊85 registry targeted收據沿用原scope，不當新blob驗證。

B01 lane final74pass/2summaryfail屬未套中央view；中央產品真修後足／缺基本面與ML未知assert保留。不是xfail或刪assert。舊fixture「值得看」第一assert失敗的兩次過渡命令保留為失敗，不列接受分母。

### B08 helper界線

public helper是lexical OS renderer，不自行授writer或替caller檢查來源custody；caller仍先核canonical／containment／links／hardlinks。`_absolute`／`_reject_links`／personal control checks改以renderer做OS查驗，長suffix不能誤當不存在。外部device namespace／ADS／保留裝置名／尾空白點仍拒絕；extended字串不進receipt/hash。

既存同檔SQLite218/263/319字元三層、中文／空格/#/% filename的helper URI ro/rw對照通過；UTF16 chars236／units256的emoji path轉extended且不建目錄。初probe用rw開不存在檔案導fail是probe誤用，rw禁止create正確。worker初次TemporaryDirectory teardown失敗後，在中央通知前移除唯一自建Temp子目錄；後續probe root留存，沒有正式資料清理。

## 中央驗證（新增差異，不全面重測）

主venv、`QT_QPA_PLATFORM=offscreen`；pytest加`-o addopts= -p no:cacheprovider`，避免本機cache permission提示；資料／writer測試使用合成Temp。

| 命令／scope | 真結果 |
|---|---|
| 原碼AST `scripts/check_ml_shadow_boundary.py` 接手 | 659files／11violations／exit1 |
| 採B01後V5 summary missing/available＋hover三node | 3pass／1.19s；保change／基本面／ML未知assert |
| `tests/test_ui_qt_market_regime_view.py tests/test_baldr_b03_market_home.py` | 17pass／2.02s；完整indicator與defaultcollapsed/expanded兩次refresh |
| 強制 `tests/test_ui_qt_update_view_workbench.py` | 85pass／2.52s |
| 強制 `scripts/qa_validate_update_tab.py` | 25pass／4skip／0fail；只Temp合成更新，raw `output/qa/update_tab/VALIDATION_REPORT.md` |
| helper `tests/test_personal_data_paths.py -k 'not cow_synthetic_pipeline_with_new_internal_root'` | 101pass／3deselected／2.40s；三COW由B02同版converter驗，不稱全部pass |
| `mypy app_module/personal_data_paths.py` | Success1檔 |
| 強制 `mypy ui_qt app_module data_module analysis_module backtest_module decision_module portfolio_module runtime` | Success：823 source files；含當時 B08 selector 初版，不含尚未交付 B02 最終 converter |
| helpercompile／diffcheck | pass |

UI產品穩定後WorkBench／validator已按順序跑一次，完整 roots mypy 已通過。B02 最終 converter 採納後僅針對新增差異做型態／compile 檢查，不重跑不受影響的 UI。Native／真人未做，offscreen不代替；B03 lane環境CJK字型限制見原收據。

## 後續具名工程與未驗範圍

B02須完成同版helper canonical DB本身>260、suffix、JSON/SQLite v1/v2 convert→activate→append→rollback→新程序、source pins不變與target新歷史保留、hardlink/reparse/capacity/race防護。父層已擴鎖activation.py及watchlist_repository.py，只限IO boundary不改schema/query/write語義。

B08私人domain typed routes仍以契約交付；不等於B09/B10 caller已接。PERSONAL私人read/write同target，空庫不借legacy；市場Evidence reader獨立無私人writer；Review與Evidence/Gap/Decay source-writer分流及DecisionQuality notes漏selector留B10。Portfolio trades／聲明／Paper／ledger caller留B09。

B03額外核對在未改base重現 `test_mainwindow_portfolio_return_requires_current_exact_result_identity` 失敗（result_id空而非result-r1）；具名列B06/B09修，不能baseline當pass，不由B03越權改。其餘B03 central nav/update/runtime等未完成工程仍保留B03/B15清單。

原plan已append1133bytes，舊237637bytes逐byte完整保持，prefix SHA256 `b88864218e1856e954d559e6d91ced7b57ee21311a4df3b34092874da8be8ace`；新238770bytes SHA256 `9730be99e060ea467827a532abb24a2342db1a3ecc2e5f756d0a979ee2a28543`。本機review位於 `output/plans/baldr_completion_review_sol_20261006.md`，不stage ignored output。

無push/mainmerge／正式DBwrite／personal migration或activation／正式Task／ACL／交易／foregroundNative／真訓練。自然成熟、正式source資格與部署另列X/U；不把這些時間／批准條件當工程完成gate，也不把尚缺caller／控制port寫成工程closed。
