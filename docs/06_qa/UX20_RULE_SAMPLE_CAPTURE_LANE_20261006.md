# UX20 固定 MA 研究樣本 capture 獨立 lane

日期：2026-10-06。基線：`be8aac332`，分支：`lane/stage5-sample-capture-20261006`。
工作樹：`C:/Projects/PythonProjects/technical_analysis/output/worktrees/technical_analysis_sample_capture_lane`。
主線唯一整合 owner：`01a10b0e`；本 lane 不整合／不推送。停止期限為 UTC 07:00，本包完成即停止，不自行恢復。

## 範圍與排他權

僅新增以下三檔；建立前確認路徑／分支及檔案不存在，沒有覆寫既有檔。

| 新增檔 | 用途 | 回滾 |
|---|---|---|
| `app_module/rule_research_sample_capture.py` | 純 MA 控制組投影、pinned 唯讀 adapter、隔離 bounded writer／reader | 未整合保留 lane；整合後由 owner revert 本包 commit |
| `tests/test_rule_research_sample_capture.py` | 合成小 cohort 與故障／容量／版本／修訂驗證 | 與本包 commit 一併 revert |
| 本文件 | 契約、QA、缺件與交接 | 與本包 commit 一併 revert |

回滾前先核對 owner／status，不執行 worktree／branch 清理。回滾會移除新 adapter，既有 Evidence／Paper producer、正式 DB、raw、UI 不受影響。沒有新依賴、正式資料讀寫、Windows Task、全市場收集、ML 訓練、Native、私人 notes／ledger、分享、永久清理或自動合併。

入口遵循 AGENTS 與 execution／testing／documentation／quant guard；本任務明示三檔限制優先於 shared-state 或全域文件同步建議。Coverage Pass：本限定 QA 必須新增；Manual／Snapshot／Architecture／原 plan 如主線接線時需要同步，由唯一整合 owner 處理，本 lane 不改。本包沒有使用者可見功能變更。graphify 先查既有圖（149 個相關節點，含 EvidenceCaptureService）；最新 MA／universe／snapshot 以現有來源檔核驗，不重建或提交圖譜。

## 資料契約

`build_rule_research_capture(verified_snapshot, as_of=aware_datetime, observed_at=aware_datetime)` 是純投影。不開 source 檔、不讀 DB、不使用 ranking 或個人收藏；重用既有逐股 `_validate_snapshot_payload` 純 validator、`adapt_daily_market_snapshot` 與 consensus。對私有 validator 的依賴是明示相容耦合，未變更其 API；未來 repository 重構時須一併核對。

`read_rule_research_capture(repository, manifest_sha256=..., cohort_id=..., decision_date=..., as_of=..., observed_at=...)` 只讀固定 manifest pin。既有 repository 重新核對 manifest／逐股 hash／method version／universe 原件；不讀 latest，不補查 live。`capture_pinned` 先讀來源，writer 在 staging 前與 rename 前再讀相同 pin，來源改變或缺件立即拒絕。

固定方法只包含 close_above_ma20／close_above_ma60，沿既有版本／參數／暖機及 Decimal 結果，不新增公式、家族或績效。每方法逐股完整列出：

| state | 意義 |
|---|---|
| matched | 已合格輸入符合該 MA 觀察 |
| notmatched | 已合格輸入未符合該 MA 觀察；不是損失或負 label |
| unknown | 方法／輸入／artifact 缺件，或 partial snapshot；保留 reason／unknown_reason |
| excluded | 原明示 universe 排除，逐股保留排除理由；不是 notmatched |

每方法 `matched + notmatched + unknown + excluded = represented_denominator`；included 分母另列，兩方法相同母體，不把兩條 MA 當兩個策略家族或兩倍股票數。合成完整示例：included 2＋excluded 1＝represented／population 3，保存 6 個方法觀測列。partial 示例如缺 3034：兩個 included 都保 unknown，missing_count／missing_stocks 保留；沒有部分成功冒充完整 cohort。

有明示 universe 時保存 ID／version／scope／included／excluded／population／原 source_ref／source_sha256。沒有 universe 時保留 legacy 明示 cohort，population_count=null、full-market population unknown。來源 producer／reader 最多16 included，included＋excluded最多32；本包完整保存這個 bounded cohort，不稱全市場／全合格市場母體。沒有 silent truncate 或自動分批收全市場。

capture 同時保存 snapshot_id／snapshot_sha256、snapshot schema／feature contract version、method specs／hash、cohort pin、universe canonical hash、逐股 artifact／snapshot／input hashes、完整 source_refs／source_ref。新增 `source_sha256` 是上述來源 refs 的 canonical composite hash；不是對 raw DB 重新讀取後計算的整檔 hash，也不冒稱官方 custody。原有 hash 欄位完整保留。

## 時鐘、去重與資格

`decision_date`／`decision_cutoff` 保留原 snapshot；`as_of` 為呼叫端明示固定 aware 時鐘，必須不早於 cutoff／published；`observed_at` 是捕獲此研究包的觀測時鐘，必須不早於 as_of。純函數允許明示合成觀測；`capture_pinned` 使用實際 UTC now，仍不授 natural authority。

`artifact_published_at` 只表示 artifact 發布。當前 MA artifact 沒有可證逐股源資料當時 observed／available 時鐘，所以 `source_observed_at`／`source_available_at` 明示 null，不能以 as_of、published 或結果回填。保留 nested source_ref 原件 metadata 不等於授予其歷史 availability 資格。PIT／Formal／training／natural authority 全部 false。

identity 包含 schema、as_of、來源／snapshot／方法／母體／結果／分母；僅排除本次 observed_at 與 identity 自身。相同 pin＋as_of 重跑去重並返回首次保存 receipt；不更新舊觀測時鐘。同日來源修訂或不同 as_of 有新 identity，舊 capture／receipt 保留。把不同 as_of 當同一次自然決策不成立，未來 caller 必須固定其語義時鐘。

matched 不等於批准入選。全部 row.selected=false；selection_predicate=null、selection_status=unknown、selected_count=0。ranking 沒有批准 predicate，不納 selected；收藏／榜單不產生 capture 母體。沒有 Outcome label、交易或績效輸出。

## 隔離 writer 與 receipt

`BoundedRuleResearchCaptureWriter(output_root)` 只接受本工作樹 `output/qa/` 下的明示子目錄或系統 Temp 子目錄，拒正式 root／repository source 路徑。`capture_pinned` 另拒 source／destination 互相包含。沒有預設正式目的地或 config 接線。

容量政策：capture ≤256KiB、留存≤8MiB、≤128 captures，磁碟 reserve 固定200GiB，首次 staged 寫入前預留兩倍新 bytes，rename 前再核對。測試只在合成容量 provider 上覆寫 free probe／常數，production constructor 沒有降低 reserve 參數。duplicate 驗證舊 receipt 後直接返回，不重寫樣本；來源不匹配、容量不足、busy／未知目錄／partial 全部拒絕。

每次以 exclusive `.writer.lock` 阻止同目錄雙 writer；`.partial-<uuid>` 使用 create-only、flush＋fsync 寫 capture.json／receipt.json，bounded readback 及來源重核後，在同一 volume 將整目錄 rename 成 `<capture_identity_sha256>/`，完整包才可按身份讀。receipt 綁 schema、complete、capture identity／bytes hash、rows_count、首次 observed_at 與 research_only。

`writer.read(identity_sha256)` 單包唯讀核對 schema／hash／分母／receipt，禁止路徑 traversal、不建立目錄或 lock；已在新 Python 程序核對。writer inventory 有 entries／bytes 上限，拒 symlink／Windows reparse／hardlink。故障留下 partial 證據，沒有 latest 成功指標；下次 fail closed，不自動清理或續寫。只有本次已取得的 transient lock 於 finally 移除。

限制：測試涵蓋受控 OSError／rename 失敗，不宣稱突然斷電或檔案系統 crash durability 已驗收；未提供目錄 fsync 跨平台保證。path lstat／fstat／重核守衛拒已存在 links／hardlinks與已知替換，但不是對惡意同步置換的完整 Windows no-follow handle 證明。`write(capture, revalidate=...)` 是有界低階測試／整合入口，callable 必須重讀合法 pin；自行回傳相同合成物件不構成 source custody。正式來源整合應使用 `capture_pinned`。

## 驗證收據

短路徑隔離命令（共享 venv，cwd 是本 lane）：

```powershell
..\..\..\.venv\Scripts\python.exe -m pytest tests/test_rule_research_sample_capture.py tests/test_daily_market_snapshot_repository.py tests/test_multi_method_research_consensus.py tests/test_daily_market_research_universe.py -q -o addopts= --basetemp C:/Users/archi/AppData/Local/Temp/ux20-r4 --tb=short --junitxml=output/qa/ux20_contract_suite.xml
..\..\..\.venv\Scripts\python.exe -m mypy app_module/rule_research_sample_capture.py --follow-imports=silent
..\..\..\.venv\Scripts\python.exe -m py_compile app_module/rule_research_sample_capture.py tests/test_rule_research_sample_capture.py
..\..\..\.venv\Scripts\python.exe scripts/quant_guard_linter.py
git diff --check
```

截至首次完整回歸：**124 passed／1 skipped**。新包38pass／1skip；既有 repository24＋consensus45＋universe17＝86pass；重跑不加總。唯一 skip 是本機一般 symlink 建立權限不足，hardlink 拒絕已實測。mypy1檔、兩檔 compile、quant guard 前後與 diff check通過；guard 是白名單靜態檢查，新檔另人工確認無 float／無 future window／無 outcome 反推 availability。

新包測試包含完整分母／partial／排除理由、unknown availability 不補入、純投影無 IO／frozen、latest 壞而 pinned 成功、來源 bytes不變、aware/future clocks、重跑去重、同日修訂保舊、新 as_of身份、實際 observed 時鐘、三種寫入故障、前後來源修訂拒絕、capacity preflight／commit前 reserve、duplicate receipt tamper、busy／未知檔保留、source/output overlap、版本／source／method／condition拒絕、新程序讀回、重新 hash 的分母／policy／重複列／availability損壞拒絕。

最初 QA parent 缺少造成30 setup errors，第二次長 Windows 路徑造成29 failures／1pass，均未當有效產品驗證；改短 Temp path 後通過。原失敗與完成產物均留 ignored 的 lane output／Temp，不提交或永久清理。

最終追加 source refs composite hash 核對、16股完整不截斷及 parse前 bytes界線後，同四檔 suite於短 Temp `ux20-r6`：**126 passed／1 skipped（3.73s）**；新包40pass／1skip，既有86pass，不與先前重跑加總。收據 `output/qa/ux20_final_r6.xml`。最終 mypy1檔／compile2檔通過；新模組AST float constant／float call為0。沒有改 UI，因此沒有執行 UI三項專用gate或全域回歸，不冒稱全專案型態通過。

## 未完成依賴與 owner 交接

本包可用純 contract＋pinned reader／bounded writer，不假稱自然 scheduler ready。仍缺正式來源的固定決策時點及可證 source availability、正式 capture owner／日曆／漏日政策／時點失敗與修訂接受流程、超過16股完整市場母體及合法分批 producer、長期保留容量治理、Outcome H5／10／20與政策／calendar成熟核對。沒有更改既有 Evidence／Paper capture producer或 scheduler，本包不能代替它們。

主線 review 後可 cherry-pick 本包限定 commit；Manual／UI／config／原計畫整合由唯一 owner 承接。stage5／UX20 只能標有限工程切片，不能整項 done、自然樣本成熟、正式資料可寫或 ML fit ready。本包完成停止，保留 branch／worktree／證據，不自行恢復。
