# 官方大盤來源修復後的全市場 H5 模型驗收

## 目前狀態

完整 v3 資料、H5 全量重訓、heldout 指標獨立驗算與 13 檔最新資料推論均已完成。市場組原本極端的風險誤差已收斂，但下跌機率仍未勝過 train-only 基準，校準後反而較差；**本輪工程修復完成，模型品質仍不支持正式啟用**。原模型隔離、rule_only、production alpha=0 與正式權限保持。

本次修復沿用 62 欄名稱、順序、scales、既有模型家族及原始 targets。本研究建置當時只替換新研究資料集，未寫回正式大盤 SQLite／CSV；舊模型與 v2 資料保留。同日較晚的正式大盤與歷史交易日修復另見[正式資料修復](FORMAL_DATA_REPAIR_2026_09_23.md)，不回寫本版資料、模型或驗收結果。來源事故、153 個月／306 份官方回應及 bounded 新模型驗收見[大盤來源稽核](MODEL_REPAIR_MARKET_SOURCE_AUDIT_2026_09_23.md)及[bounded 評估](BOUNDED_RESTATED_RESEARCH_FIT_QA_2026_09_23.md)。

## 封存資料與來源證據

資料目錄為 `E:/codex_model_repair_20260923/dataset/full_restated_official_market_v3`，共 13 年、3,496,189 列，其中原 Direct 基線 3,353,096 列及 143,093 個追加列。原列的 cash-only targets 保留，追加列目標缺值，沒有創造新的配置答案。官方來源截止日為 2026-09-22。

| 證據 | SHA-256 |
| --- | --- |
| Dataset identity | `ce6cda0acd5a2e8b0403b695bd3270a081dfc743114c33e276e5c4f283109d8c` |
| `manifest.json` 檔案 | `80154115b3fddb1ff2fc0a2470879b0f377b7200f5e29aa7112412af09b37655` |
| 外部 `source_custody.json` | `c6ea6a83ecf9f5667db94f0504e463c120a90e3a6a3fd84b18bd4b1812bfa97a` |
| 官方市場來源清冊 | `4bc1917cbbc46334b10b40012d569d63db4084bae8e17972d46795bf01c8839f` |

外部證據目錄為 `E:/codex_model_repair_20260923/training/full_official_v3_run01_custody`。開始鐘 `08:15:12.906022 UTC`、來源核驗／修訂鐘 `08:15:16.387440 UTC`、資料清冊建立 `09:26:21.493421 UTC`、custody 完成 `09:26:22.036997 UTC`，均為 2026-09-23 真實執行時間。producer 固定在隔離 `56fc40be` 工作區；結束重新核對官方月報、run02 股票快照、六個計算來源檔及原 Direct targets。不是事後補造開始證據，也沒有將修訂鐘回填到歷史決策日。

## 完整資料的獨立核對

Root verifier 逐批讀取新舊 Parquet，核對全部 row IDs、順序、日期、stock events、local row indices、fold metadata、targets／masks 與股票修訂身分；**171,313,261 個非市場 feature slots 及其 masks**與 v2 完全一致。另以核驗官方原始來源和獨立 Decimal／整數計算，逐列核對 **45,450,457 個市場／品質 slots**。全部 3,496,189 列的市場 payload 至少有一項值或 mask 變動。

四個 horizon 的結束日共 13,984,756 項均符合官方交易日；非官方決策日或不足完整 horizon 的列保持全缺 label。與 v2 相比：

| Horizon | 新版有 benchmark label 的列 | 原本有值、現在缺值的列 | Label 值或 mask 改變列 |
| ---: | ---: | ---: | ---: |
| 5 | 3,433,790 | 34,464 | 3,258,355 |
| 10 | 3,365,623 | 77,305 | 3,236,784 |
| 20 | 3,237,427 | 161,782 | 3,202,186 |
| 60 | 2,749,235 | 531,556 | 3,101,860 |

新的缺值是按修正後日曆／價格路徑的可用性保留，不填補或偽造行情，也不刪除原始 row。尤其較長 horizon 更容易碰到缺價日，不能把上述數量解讀成此次新增了同等數量的錯誤價格。

證據為 integration `output/qa/model_repair_review/full_official_v3_independent_values.json`，file SHA `3b374228873dab65406ce669da2935a6bae2414a094282fed91c309822ec1ded`，verifier SHA `602730e8161de7bf7c34185f55236461a64655a2c97c23b35f71773ffc9d60d0`。新舊清冊和所有分片於驗算前後 hashes 一致。這次完整掃描沒有獨立重算所有股票 outcome 值；另有四檔樣本 2,308 個 excess／downside，以及 bounded 69,140 組四 horizon outcomes 的獨立價格算式核對，範圍見前述來源稽核。

## 訓練與並行重構界線

訓練使用另一個乾淨、固定在 `2292e660` 的隔離工作區，輸出為新的 `E:/codex_model_repair_20260923/training/full_h5_official_v3_release_20260923`。使用 H5、既有 ridge/logistic recipe、8192 batch、6 次 logistic iteration，沒有 `max-fit-rows`，process threadpool 上限為 2；所有 fit 候選列須先通過既有成熟度、purge、embargo 與資料完整性檢查。前處理 median 原有 100,000 列 deterministic cap 不等於模型 fit rows cap。

15 個與大型重構協調的 frozen ML 檔相對 `2268a98a` 無變更。整合分支的 `2292e660` 已合入 dev `bcde4094`：當時 211 個其他 owner dirty 檔中，210 檔 bytes 一致，R012 實作報告在並行期間變動且不屬本次修改，未暫存／回復。後續純 QA 文件 `5b61ea2f` 合入 `36ff61f6`，214 個既有 dirty 檔全部 bytes 一致、index 空。執行中不更新 producer 或 trainer 程式。

正式 calibration active pointer 於本輪唯讀 readback 仍為 `rule_only`、candidate/artifact/dataset=null、formal_order_allowed=false，file SHA `1b156104152f74dbc38c588c5c5c3107f2a186e2a62f8dbb7db47bb45f94c1a1`。不因研究模型 fit 成功自動切換正式模型。

## 完整 fit 與 release

實際訓練於 `09:26:44.504593 UTC` 啟動、`09:31:07.999519 UTC` exit 0。最終 fit 使用全部 **3,433,790** 個有成熟 H5 label 的候選列，沒有 row cap；其中 456 列沒有股票事件前綴，仍按原缺值契約保留 masks，不假造價格。獨立評估 fit 使用 3,066,279 列，兩段校準各 51,273／43,531 列，三個 packs 各有同一批 **144,088 個** heldout rows。heldout 自 2026-05-20 開始；切分、purge、embargo、preprocessor train-only 與 source hashes 均由原 runner 嚴格核驗。

Release 為 `restated-repair-a24d7db1658e6579`，位於上述 output root 的 `runs/`。staged／final loader 均通過；另有 25 檔資料集內最新列 smoke 通過，但這不取代下一節真正的新來源擷取。

| 產物 | SHA-256 |
| --- | --- |
| Model artifact | `59da6686c99c09dd2f0216ab6efb397f7818a24f7201fcd7a74fd9de7afe1edd` |
| Release identity | `421555ff6240111d366ee339b49b8f37eae696e73a026fffec1234a45967ca2f` |
| Release manifest 檔案 | `ae7c6fd6a2f8bbffc92176d7cf394a4f91686825e9719df947e9b18d72c6b42f` |
| Training manifest 檔案 | `37bcb685a0ef094570c5f2924556dd27dcb36aa98a5994e64947ba73e9adaf90` |
| Evaluation metrics 檔案 | `8a4045cde44b3b5de70ac2b7c22e44a6177b93891670fd16ee2d986eec547567` |

執行紀錄觀察到的 peak working set 約 6.23 GB，最低可用系統記憶體約 23.04 GB；OpenBLAS／OpenMP 皆為 2 threads。這是本機本次 fit 的資源觀察，不外推其他設備或日常 UI 效能。

## Heldout 獨立驗算與品質判定

Root 從三份保存的預測 Parquet 逐筆重算，**114 個整數指標**全部吻合，包括回歸 MAE／RMSE、機率 Brier／正例率／threshold accuracy，以及套用已封存校準 mapping 後的 downside Brier。每份恰為 144,088 個唯一 row IDs，來源 hash 前後一致。證據 `output/qa/model_repair_review/full_official_v3_heldout_independent_check.json`，file SHA `9da05127f778f62d12c640769143321fbbacb665ba62f3432c9bc98b582e82ad`，verifier SHA `3d53cd7e61cd5b590ef4b77429a96685815255f4fa33ec327bffb94956432839`。未獨立驗算 ECE、重執行模型預測或交易策略績效。

下表 Brier 將原整數 bp² 除以 100,000,000，顯示六位小數；越低越好。三組都使用相同 heldout labels，基準只依各自訓練列計算。

| 特徵組 | 報酬 MAE bp | 基準 MAE bp | 不利幅度預測的 MAE bp | 基準 MAE bp | Downside Brier | 校準後 Brier | 基準 Brier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 資料品質 | 488 | 488 | 321 | 322 | 0.224806 | 0.229515 | 0.224746 |
| 市場 | 483 | 488 | 353 | 322 | 0.231447 | 0.235032 | 0.224746 |
| 價格／技術 | 487 | 488 | 330 | 322 | 0.226520 | 0.231192 | 0.224746 |

同 heldout 的對照另逐列證明：v2／v3 的 144,088 個 row IDs、股票風險與成交可行性 truth／masks 完全相同，市場組「不利幅度預測的 MAE」由 **9,546 降到 353 bp**；基準為 322 bp，仍未勝出。證據為 `full_official_v3_same_heldout_comparison.json`。這是修訂多項來源及訓練樣本後的觀察，不是單一成交量特徵的因果消融。兩版所有 benchmark excess labels 有差異，其中 11,086 個 downside truth 改變，所以不能拿新舊報酬／分類分數直接宣稱同標籤的改善。

市場組報酬 MAE 只小幅優於基準，沒有顯著性或經濟效益證據；三組 downside Brier 都不如基準，校準後亦未改善。沒有據此選 heldout winner、改閾值或調參。產業超額報酬仍缺少可核驗歷史標籤；原 targets 全部 cash-only，meta 維持固定現金 policy，**沒有學會資產配置**。

## 新擷取資料與當日推論

完成 fit 後，從正式 SQLite 新的唯讀 transaction 擷取 13 檔股票前綴，大盤來自核驗官方月報；含 1256／1477，feature as-of=2026-09-22，實際 capture=`2026-09-23T17:33:24.366687+08:00`。39 個 H5 base expert outputs 全部產生，neutral fallback=0；產業 excess head 39/39 保持 missing。當日輸入 identity `b5981d5e273f82663aeca4d16734f8630e27552691a632a5022b56956640fc64` 與訓練 identity 分開，沒有改寫原模型來源。

Receipt 為 `E:/codex_model_repair_20260923/current_inference/full_official_v3_run01/current_shadow/d55fd60a206334cc3b9b63a280c734bbf51d126e9dfb29a8f0e301910663b64c.json`，file SHA `ffe1652acb7209b6da35fef2fe58f30780d77e85022cf0c3fe079c01ae76177a`，input manifest file SHA `a14d666750ed36a39fd4de4798ecd5a0d051c862aa95ef24a79239b0bc7a1c05`。

Root 重算 receipt body hash、讀回 release/model/input hashes，經 strict provider 重驗原始前綴與 prepared rows hash，並檢查全部預測型態／機率範圍及研究權限。證據 `full_official_v3_current_readback.json`，verifier SHA `b535f2133e9eb6282d1e00233107163c61d3128f19a3b58833ffd72229926291`。所有列 meta 固定現金 10,000 bp、股票目標 0；formal OOS／production action／broker order=false、alpha=0。這是接線及一致性驗證，沒有宣稱模型已能決定持股。

## 後續產品限制

本輪已完成兩個受影響模型家族的研究資料重建、完整重訓、獨立評估及最新資料讀回。本輪未完成的產品能力包括正式大盤資料寫回／來源收集器切換、模型品質提升、有效配置 targets、歷史產業 labels，以及 production promotion。這些須另按資料契約和大型重構進度規劃；不能再重跑同一組資料就宣稱解決。
