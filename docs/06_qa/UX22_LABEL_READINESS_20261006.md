# UX21 endpoint label → UX22 樣本／公平比較 readiness（2026-10-06）

> 文末「UX23 仍 pending」與 24UX 統計屬本 UX22 收據凍結時點；後續 [UX23 scoped 整合](UX23_REGISTRY_INTEGRATION_20261006.md) 已採納唯讀 lane，但未證正式 shadow 啟用或整體 UX23／產品 gate 完成。不同收據的進度數字不可直接相加。

基線 `8104d0a921fe020b7640250ef62221e44252e55b`；承接已接受的 benchmark source／store／UI。本包是有界唯讀 consumer，不重造 learner，不訓練真模型。root 負責 CLI、整合 review 與收據，唯一 Luna Max 實作薄 adapter／focused cases。

## 既有元件與真正缺口

| 既有元件 | 本包重用／界線 |
|---|---|
| `read_forward_receipt` | 核驗 exact parent、封存 outcome 與 source pins；不查較新市場 DB |
| `HistoricalLabelSpec`／`HistoricalLabelRow` | 整數基點、endpoint／availability 與成熟時間契約；unknown 不填日期或 0 |
| `PurgedWalkForwardSplitter` | 現有 label end 跨入評估期的排除原則；本入口明示固定 train／evaluation windows，不選自動 fold 參數 |
| `HistoricalDatasetBuilder`／`HistoricalTrainingService` | 已有 T-1 feature／成熟 label join、fold-only 前處理及 linear baseline；本包不呼叫 build／fit，endpoint policy 不冒充完整 20 日 downside schema |
| `MLChampionComparisonService` | 已有 same-sample champion／challenger 比較；缺同源 predictions、downside policy／target 與明示 k 時不可呼叫，不造候選勝出 |

新增的只有 policy→封存 label ledger→時間分區／readiness 入口。全母體與逐方法 matched／notmatched 對照仍保留；方法符合不是交易 selected。label policy 可選 gross、net、gross_excess、net_excess 及 H5／10／20 子集；不替使用者選唯一目標，也不預設成本或 benchmark。

## 明示輸入與保存

`scripts/run_rule_research_label_readiness.py` 可重複 `--receipt PARENT OUTCOME`，最多 32 對；`--label-policy`、`--split-policy` 指向版本化 JSON。省略時輸出缺件而非選預設，未知版本／錯型態／不合法日期／重疊界線拒絕。政策檔有 64KiB 上限、重複 JSON key 拒絕；JSON report 有 2MiB 上限，不截斷分母。

readiness JSON 保存原 parent／outcome identity、內容 hash、label／split policy 與 hash、成本／基準 lineage、逐列來源及全母體分母；label 列最多4096，完整報告最多2MiB，超限整批拒絕。stdout 可以保存到明示研究檔；同輸入新程序重讀須一致。沒有正式 ML registry、model artifact、Task 或 DB 寫入。

## 時間與資格

明示 train_start／train_end、evaluation_start／evaluation_end 與 training_as_of；訓練窗不能與評估窗重疊，training_as_of 必須早於 evaluation_start。label 必須在訓練 cutoff 可得且期末早於評估起點，才能成為時間合格候選；評估樣本不回填訓練。研究報酬已知與歷史 availability 已知分開呈現，unknown 不建立虛構的 HistoricalLabelRow availability。

UX21 current-observed／年度計畫日曆來源不能因 label ledger 而取得 PIT、natural authority、formal／training／execution 資格。候選時間分區不等於合法完整 feature dataset 或 baseline 公平比較。單決策日收據沒有跨日訓練／評估閉環時明示空分區／缺件，不造 fold 或新最低樣本量 gate。

## 尚缺工程與外證

明示目標到既有 learner 的完整 label schema 映射、決策時可得 feature registry／來源、同 cohort／policy／horizon／cost／split 的 baseline 與候選 prediction pins、所選比較指標仍需接線。官方 actual-session／custody、調整 basis 與 historical availability、期間 OHLC／MFE／MAE／停牌 label 若產品選用仍是既有 UX21 缺口；endpoint policy 不要求偽造這些路徑指標。真模型 fit、formal 發布、自然成熟與效果沒有本包證據。

## 驗證收據

最終 focused／CLI 22 通過，既有 forward／store／reader／benchmark integration 與 ML label／purged-split 回歸61通過，去重共83個不同案例、0失敗／0略過；full mypy 816來源檔、4檔compile、量化精度／未來函數與diff檢查通過。沒有UI修改，不重跑已接受的Native／首版性能gate。raw權威為 `output/qa/ux22_label_readiness_20261006/validation_receipt.json`，commit後另有 `commit_readback.json`。

actual synthetic pipeline 的 CLI 收據：母體3筆／included2；兩方法 `close_above_ma20`／`close_above_ma60` 共6列，matched2／notmatched2／excluded2。H5／10／20共18 label，12有值／6缺件；18個availability都是unknown，temporal train候選0，12個只供事後研究評估。明示benchmark qualified_research與fixture-cost-v2封存原值；gross396／net365／gross excess196／net excess165bp各自對應已驗。行情及benchmark的兩個fixture DB移開後，新程序重讀同JSON identity `11b6f11b10b08d173e33a52bc802521b986665d46d50853a20d4025014d54800`；6個原封存檔hash不變。所有training／PIT／formal／natural／execution旗標仍false，selection unknown；baseline未呼叫且不可評估。

人工宣告日期的測試是在real reader回來後，以synthetic unit data替換日期／source模式；只驗時間契約，不是重新seal的歷史權威來源。另驗availability晚於training cutoff、label end跨入evaluation、evaluation label不回流training及4096列／2MiB界線完整拒絕。實際sealed current-observed收據仍unknown／blocked，兩類證據不可互代。

保留首輪fixture driver的Windows SQLite helper未close導致移檔鎖定失敗；只收回未使用的fixture connection後final重跑，沒有產品改動或正式DB操作。root新增時序unit setup初次未替excluded blank horizon建立availability容器，3個測試建構失敗；修正fixture後22通過，初次XML／log保留。回歸61的本機pytest cache permission warning未影響結果，後續用既有no-cacheprovider模式。Temp synthetic資料與raw均保留、不清理，沒有真實模型fit／FA_Data寫入。

本包readiness工程終點完成，所以UX22／stage7由pending進入partial；UX21完整labels與公平比較未done，UX23仍pending。9stage 1done／8partial／0pending，24UX 2done／21partial／1pending。Manual／Snapshot／架構／導航／索引／coverage／QA routing同步；原plan完整227435-byte前綴與原SHA保留，只追加，raw prefix proof留本機、不stage。完成本地commit／readback後停止，07:00UTC安全暫停界線有效。
