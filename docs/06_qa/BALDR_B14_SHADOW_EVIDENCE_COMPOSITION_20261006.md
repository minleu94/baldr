# BALDR B14：隔離 shadow evidence composition（2026-10-06）

本包只新增 composition、freeze store、focused tests 與本 QA 四檔。固定 base 為 `909b3409da7bd10b15e80c3349a204524d3289a5`，branch 為 `lane/baldr-b14-shadow-evidence-20261006`。原 B13 adapter、B14 control、ML、shared DTO、UI、main、Task、Manual、B01 allowlist 均只讀；沒有 CLI 或 production wiring。

## 固定來源與資格

- B13 中央來源：`9266e7e3df73c8aec7bcc7bc76fc066a1f2852fa`；adapter blob：`490d9fdf8a7a6a1af08f8d74e04ed0e8b23c9a8a`。
- 原 control 包：`671b9a970fbf839dc1cd498e88be07d49d87cadd`，本 lane 的 dependency commit 是上述固定 base；control blob `3490ffcb81f57826234d1b827af88ab3ef76e310`、store blob `cd4a50c9075232e31e9929d00c2ba58b5b14b0cf`。
- 原 B13 ready 僅代表 synthetic offline 工程契約通過，包含離線 evaluation path；不代表 prospective prediction、自然成熟、正式 PIT、訓練或執行資格。
- 所有研究來源的 formal/training/historical PIT/natural authority/execution 旗標保留 false。composition 的 `production_action_allowed` 永遠 false。沒有真 model、fit/train、registry write、Task enable、真資料庫或交易。

## API 與來源 custody

`FrozenShadowEvidence` 持有原 `PreparedModelInput` 與原 `ModelInputRunResult`，加 exact model revision、method、aware prediction availability、decision cutoff、timezone 與 capture clock。沒有第二份 ModelInput 或 PredictionDTO。

`freeze_shadow_evidence` 透過原 `run_prepared_model_input` 注入只回傳原 result bytes 的 replay runner，要求回驗結果與原結果完全相同。fresh process 先用原 public `prepare_model_input` 重建合法新 seal，再以原 public run 重驗原 payload；不持久化或偽造 private seal。原六種 pins、metadata、policy、sample/path、denominator、preprocessing audit 與原 payload bytes 都保留。

`ShadowEvidenceCustody` 由 caller 注入：核定 frozen/research binding，另以獨立 custody 儲存 evidence revision/hash witness。binding 自身的 hash 只證明一致性，不是核准。測試的 fresh process 從 caller 獨立檔讀取已核集合與 witnesses；不能從 freeze receipt 自行產生 approved 集合。

`ReadonlyResearchPort.read` 是注入邊界：caller 呼叫原 label/fair wrapper，交還原報告 bytes、原來源 pins 與 aware availability。production 新模組不 import ML 或會 transitively import ML 的舊 wrapper。原始報告 hash、schema、policy、method、target horizon/gross metric、完整 denominator、common cohort、model/dataset/artifact 與原 candidate prediction 欄位逐項回驗。

## Freeze、maturity 與 monitoring

`ShadowEvidenceStore.create` 要求明示全新 absolute root 與 `synthetic://` namespace，限 temp 或隔離 lane output；既存 root 拒絕。append 預設 `execute=False`，以 exclusive lock、expected revision CAS、fsync staging、caller witness 與 exclusive link 發布 append-only receipt。readback 全 chain 逐項 public B13 回驗；tail truncate、gap、污染、link/reparse、revision/hash 不符均 fail closed，不回傳部分成功。

caller CAS 成功是 commit point。之前 cancel/timeout/late cutoff 拒絕且不發布；之後即使 cancel/timeout 到達仍完成 link/readback，回報 committed revision。程序 crash 或 link I/O 失敗仍可能使 witness 超前，namespace fail closed，不能自動回退或重建。同理 bootstrap mkdir 後故障可留下不可用新 root；無自動清理。

monitoring policy 必須由 caller 明示 id/version、exact model revision、原 target policy hash、全部 method ids、被監控 method、minimum mature samples、maximum MAE 整數 bp、原 label/split policy hashes。沒有自選 threshold、last-approved 或自動補政策。

monitor cutoff 必須 aware 且不晚於目前 aware clock；來源 availability 晚於 cutoff 或未知時等待。原 label 的 availability unknown 不轉 known；只使用截止當時已宣告 known 且到期、evaluation window、matched/notmatched、horizon/end/availability 與原 path target 一致的 label。以 stock/decision date 去重，分母保留完整 dates × symbols × methods，缺 prediction、未成熟、unknown 皆保留；同股票日期重複 frozen 拒絕。未成熟 fair ledger 也逐欄核對原 label，不能以 included=false 掩蓋欄位改寫。

MAE 使用原已核 fair report 的整數 metric，不重做策略／績效公式。原 common cohort 必須等於 cutoff 成熟且有原 prediction 的集合；候選 prediction id、model、dataset、symbol、date、return/ranking/downside/uncertainty、availability 全部對應 frozen 原 result。不足樣本／缺來源／缺政策維持 waiting；caller 門檻超過才為 review_required。

容量是 fail-closed 契約：最多 128 frozen receipts、每份 16 MiB、label rows 8192；原 control pin 仍每 role 64 KiB、最多 16 roles、總量 256 KiB。大型 batch 不會截斷或擅改原 port。

## 兩條獨立實測

1. **真原 wrapper 正向研究路徑**：既有隔離 fixture 產原 sealed source receipts，真正呼叫 `build_label_readiness_batch` 與 `build_fair_comparison`（原 module），得到 `research_only`／`research_only_comparison`、共同樣本 2。原 observed label availability 仍 unknown，原 bytes 經注入 port 回驗後 composition 為 waiting、mature count 0，保留全部原 label rows 分母。原 parent/outcome bytes 與 mtime 前後相同；來源 receipt bytes、原 module 報告與 source SHA 都另存 final QA output。這條路徑不觸發 stop，不能升格自然成熟。
2. **明示 known-clock synthetic 工程 positive**：固定合成已核 clocks/policies/pins → 原 B13 result freeze/持久回讀 → mature count 1、完整分母 4 → review_required → caller 獨立 proof 與 exact 已核 rule artifact → 原 control service 預設 preview 保持 rev0 → execute 完成 rev1 stopped_rule → dispatcher spy 由 model 一次切成 rule 一次。fresh process 重新 public prepare/new seal/run replay，保持原 payload bytes、同 monitoring identity，並讀持久 control；model callback 設為 AssertionError，仍成功 rule route、同 rule hash。這是合成工程閉環，不宣稱原 observed wrapper 已成熟。

`apply_monitoring_control` 重算完整 monitoring decision、核對 exact command model revision、issued clock、monitoring raw pin 與全部原 prediction bytes pins，再交原 ControlPort。`execute=False`、port unavailable、proof missing、resume 無核准、wrong model、unknown last-rule 等維持原 port fail-closed 規則。沒有 registry append 或 stopped receipt 代替 dispatcher 的假控制。

## 最終 focused 與可核證據

工作目錄：`C:/Projects/PythonProjects/technical_analysis/output/worktrees/baldr-b14-shadow-evidence`。

```powershell
& C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe -X utf8 -B -m pytest tests/test_baldr_b14_shadow_evidence_composition.py -q -o addopts= -p no:cacheprovider --tb=short --junitxml=output/qa/baldr-b14-evidence-final/final.junit.xml --basetemp=output/qa/baldr-b14-evidence-final/final-sources
```

53 focused tests 全數通過。包含原 wrapper 正向／missing-policy waiting、freshprocess 閉環、晚 freeze、未來 monitor cutoff、cancel/timeout 前後 CAS、mismatch、自核 custody、偽 seal、naive clock、future/unknown label、duplicate stock/date、缺完整分母、candidate/model/artifact/ledger 改寫、原 bytes pin 改寫、proof 缺失、stale CAS、tail truncate 與 corrupt receipt。未重跑原 control 47 或 B13 全 suite；中央再做 union。

- raw log：`output/qa/baldr-b14-evidence-final/final.raw.log`。
- JUnit：`output/qa/baldr-b14-evidence-final/final.junit.xml`。
- synthetic 閉環原 bytes/hash、六個 B13 pins、fresh stdout：`final-sources/test_full_freeze_maturity_moni0/`。
- 真原 module 報告、兩份 source receipt byte copies 與 source hashes：`final-sources/test_original_positive_readonl0/`。
- `source-checks.json` 保存三個 Python source SHA、float literal 0、direct ML import 0。
- mypy 三檔無錯、py_compile 三檔通過、quant guard（precision／look-ahead）通過。無新增財務 float 計算；監控數值只有原 int bp metric 與 caller int bp 門檻。

output raw 證據依 git exclusions 不提交；四檔 commit 的 full HEAD／blobs 與 raw/JUnit SHA 由 owner handoff 提供。Manual/UI/production wiring 不在本包 scope，中央統一同步；沒有 dev pick、push 或 main 改動。
