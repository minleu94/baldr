# Track C：儲存、Retention 與 ML Readiness（2026-10-22）

本輪只盤點與建立有界工具，未執行刪移、重訓、正式 Producer、排程修改或 Promotion。安全可回收量目前核定為 **0 bytes**；候選尚待引用閉包、開啟控制代碼、恢復與 Owner 批准。這是有限工程／研究審查，不是全系統或金融 Gate 驗收。

## 身分與 Scope

- 起始 HEAD：`4dd820139148089ec09635ac5b0818409aa915df`，branch `codex/baldr-v2-product`；沿用工作區，不建立大型 worktree。期間 A 已提交 `1bf874e2d489`；本線不重寫其 commit。
- 本線 task：`output/tasks/track-c-storage-ml-20261022-01a164e7/task.json`，owner `root-track-c-01a164e7`。
- 初始 dirty：`BALDR_V2_RELEASE_CLOSEOUT_20261021.md`；後續 A 的 UI／測試及 B 的 custody 檔案也保持他人所有權。既有 task／singleton 不覆寫。
- 新工具、測試及本目錄屬 Track C；`main.py`、DTO、設定、金融服務、Snapshot、Feature Map、共享索引與手冊不在本線寫入範圍。
- Data Cleanup、Data Audit、Tech Lead、Execution、QA、Documentation 由 root 分階段履職；另有 Luna 唯讀 ML 審查與 Sol 獨立儲存架構審查。

## 量測口徑與空間

環境 `DATA_ROOT`／`OUTPUT_ROOT` 與 `TWStockConfig` 預設一致。F 是 NTFS，初始總容量 `1,024,191,361,024` bytes（953.85 GiB），可用 `64,686,292,992` bytes（60.24 GiB）。Get-Volume 的 CIM 存取不可用，改用 DriveInfo；未查得整卷 extent／MFT／叢集配置，不能把逐檔配置總和當整卷已用容量。

`output`、`dist`、`.t` 分別指向 `BaldrStorage/repo-output`、`repo-dist`、`pytest-temp`。掃描使用具名實體根，觀測到的 reparse 即略過；hardlink 按 `(volume, file ID)` 去重。邏輯路徑 bytes、已知唯一身分 bytes 與 Windows `FILE_STANDARD_INFO.AllocationSize` 分列；配置量仍不等於實體占用或可回收量，resident metadata、共享 extent、未知外部 link 與開啟中的 writer 均有界線。最終工具對壓縮／sparse 檔回報 unknown，不以一般 AllocationSize 推導其實體配置。

第一輪 `inventory.json`：350,000 檔，67.719 秒，606,696,583,146 logical bytes；檔案預算在 pytest 區達限，1,425 個長路徑／存取等錯誤、9 個 omission，後續根未覆蓋。第一輪舊配置查詢值僅作邏輯量，不作實體配置證據。定向補量避開 pytest 區，使用修正後配置查詢；兩輪重疊，不相加。

後續 `inventory-priority.json` 量到456,916檔，但有9,218筆Trial超長路徑錯誤；修復extended-length metadata查詢後，`inventory-confirmed.json` 對出錯版本、ML分類及packaging量到308,527檔、45.390秒、errors／omissions／links／unknown allocation均0。最後這份只對其列明roots完整，不能代替全F。合併時替換出錯Trial版本、dist只補未完成版本，重疊量測不相加；組合結果見 `capacity-summary.json`。

| 實體根／子類 | 已觀測 logical GiB | 已觀測 AllocationSize GiB | 分類與界線 |
|---|---:|---:|---|
| FA_Data/output/release_v4 | 443.935 | 444.150 | 混合PIT、Direct、模型與證據，整根不得清理 |
| └ Direct numeric v4_v2 | 203.975 | 203.982 | 包含多個run與assembly；REVIEW_REQUIRED，不能刪當前模型所依賴的舊run |
| └ PIT year shards | 176.053 | 176.053 | 原件／版本／下游閉包未結清，MUST_KEEP |
| └ OOC training v5 | 51.537 | 51.722 | 家族全部run占用，不是單一compact模型尺寸；KEEP_SHADOW／REVIEW |
| FA_Data/output/scheduled | 74.453 | 74.481 | 含正式修復stage／收據，B／原修復owner核定 |
| FA_Data/output/research_only | 10.549 | 10.549 | 研究模型與資料，引用／可再生性未證 |
| FA_Data/output/evidence_working_copies | 3.082 | 3.082 | 證據副本，不由名稱授予可刪 |
| FA_ML_Research | 110.464 | 110.468 | current_stock_cycles配置110.202 GiB，registry／snapshot保留 |
| FA_Data_candidate | 1.878 | 1.879 | 修復候選與收據，非通用cache |
| FA_Data_Shadow | 0.800 | 0.802 | 保持shadow consumer依賴 |
| FA_Data_Shadow_BankTaiwan | 0.531 | 0.531 | 個別根，不重複加進Shadow |
| BaldrStorage/repo-dist | 65.953 | 66.643 | 521,236檔，RC／rollback／舊build逐版本審核 |
| BaldrStorage/repo-output/trial | 25.744 | 26.008 | 197,348檔，已替換長路徑失敗版本的觀測 |
| repo-output/ml_research（本機可見） | 0.009 | 0.010 | 不是全部外部冷封存模型；既有E槽登記保持 |
| repo-output/release | 0 | 0 | 本次根下沒有普通檔配置，現行RC在dist |
| repo packaging source | 0.000186 | 0.000233 | 26檔；根目錄無build資料夾 |
| FA_Data/sqlite（第一輪） | 5.206 | 未以最終方法重測 | DB／WAL／SHM等只看metadata，不讀內容、不checkpoint |
| BaldrStorage/pytest-temp（第一輪子集） | 5.048 | 未以最終方法重測 | 達預算、有錯誤，全部保留，不能當總量 |

Direct／PIT／OOC列已包含於release_v4，不重複加總。其餘正式原價、技指、meta_data等第一輪量測留原清冊，不把未完整量測的repo QA、外部E封存或非Baldr根算入已知總量。最後F可用 `64,584,908,800` bytes（約60.15 GiB）；與初始差異含其他Track／writer，本輪釋放量為0。

完整具名路徑、身分、mtime、配置與未核引用在 ignored `review-manifest.json`：33個大檔共244,477,730,816 logical bytes，是待審核觀測量，不能當可回收預估。大型assembly單檔最高約20.84 GiB，正式修復computed約23.92 GiB。SHA未重讀大型DB，使用file ID／bytes／mtime，restore及open handles保持UNKNOWN。靜態搜尋已找到5筆歷史文件引用，同一候選`direct-ooc-3cec102bc9f96e2219319560`有未完成checkpoint歷史，不能刪。其他候選即使沒有靜態命中，也不能排除動態pointer／排程／人工用途。

### 唯讀工具入口

`scripts/audit_storage_lifecycle.py`只將JSON寫到stdout；沒有刪移、訓練或自動TTL模式。於共用規則指定的owned Job／mutex內，使用repo虛擬環境及UTF-8，例如：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B scripts/audit_storage_lifecycle.py --root F:/Min/Python/Project/FA_ML_Research --max-files 20000 --max-entries 50000 --max-depth 16 --max-seconds 60 --top-n 40
```

只傳具名實體根；指定junction或經junction祖先的根會拒絕。輸出若需保存，另導向本線ignored task目錄，不能覆寫正式來源。`complete`看其roots／errors／omissions／reparse與identity／allocation完整性，`largest_files`只有top-N，並非逐檔完整manifest。exit0僅代表工具正常產生觀測；UNKNOWN、預算略過或top-N限制均不授清理資格。超長路徑沿extended-length API查詢，不改Windows設定或ACL；仍有錯誤時保留具名unknown。

## 保留矩陣與回收順序

| 分類 | 本線處置 | 核對／恢復條件 |
|---|---|---|
| MUST_KEEP | 原始金融資料、正式 DB／WAL／SHM／journal、唯一備份、source／PIT／custody、Ledger、私人 H20 activation、現行 consumer 及依賴模型 | 不開啟 DB／pickle，不改寫、不 vacuum；來源與正式 writer 交 B |
| KEEP_REFERENCE | 固定 RC `06a4e1c15ed9`、必要 rollback、Golden、具名 QA／FAIL、遷移原件與收據 | 舊 Release 仍可能被文件／恢復引用，不能依 age 刪除 |
| REGENERABLE | 僅限已證明來源、版本、工具與參數固定且可重建的衍生物 | 本次尚未授予某一大型 run 此分類，需逐項驗重建及成本 |
| REVIEW_REQUIRED | `.work-year-*/assembly.sqlite`、舊 build／Trial、resume／failed run、未核 cache、未知用途模型 | 必須查 resume／registry／schedule／release／QA 動態引用、鎖、hardlink、reparse 及可讀還原 |
| DELETE_CANDIDATE | 目前 0 個已合格 | 具名 manifest＋身分／有界 SHA＋無引用證據＋恢復方式＋實際配置估算，Owner 明確批准後另案執行 |

先查大型 Direct assembly SQLite，再查冗餘 build／Trial，最後查小型 cache／log。assembly 名稱不證明它已廢棄；正式修復 staging 尤其可能是唯一回復證據。相同 F 槽隔離不計釋放，未知 hash 或引用不補造 PASS。假設未批准任何刪除，清理後可用容量預估仍等於實測可用量，另受其他 writer 變動影響。

## ML Pipeline 與訓練裁決

| 家族／版本契約 | 目標與輸入 | Consumer／本輪裁決 |
|---|---|---|
| Historical technical shadow | Ridge／Logistic、HGB；歷史技術 features，return／downside，manifest 指定 horizon | `HistoricalTrainingService` → Shadow inference／prediction registry／drift；KEEP_SHADOW 僅限既有合法研究身分，實體 champion 未全驗，Formal／效益 UNKNOWN |
| Recommendation absolute calibration v1／Personal H20 | 20 交易日絕對報酬及正報酬機率；after-cost label 缺成本保留 null，benchmark 只評估 | `RecommendationCalibrationConsumer` → `RecommendationService`；KEEP_ACTIVE 僅保護既存個人 activation bytes，不新增啟用；訓練為 NEEDS_DATA_QUALIFICATION，global promotion 不成立 |
| Allocation artifact v2／OOC training v5 | 5／10／20／60 日，各 pack 9 heads；Ridge-Logistic／HGB，19 維 expert→OOF Meta | Portfolio allocation、copilot、forward、promotion；KEEP_SHADOW／NEEDS_DATA_QUALIFICATION，正式 alpha 0，rule-only 不作 ML 效益 |
| Current-restated CORE19 | 修訂後來源／non-PIT 的研究 outcome 模型；精確 source／feature／model manifests | 研究 loader／Legacy→Bank；ARCHIVE_REFERENCE／KEEP_SHADOW，非 historical PIT，不能升 Formal OOS |
| 舊 EnsembleModel pickle | 正式根 models 下觀測到檔案 metadata；目的、label、時間切分、consumer 及增量效果未證 | UNKNOWN，保留，不反序列化、不因舊版本直接 RETIRE |

實作入口：`ml_module/historical_training_service.py`、`allocation_training_service.py`、`recommendation_calibration_training.py`、`dataset_manifest.py`、`model_artifact_loader.py`、`scripts/train_bounded_restated_research.py`。既有研究有 dataset／feature／label hash、fold 內前處理、成熟 cutoff、60 日 purge／5 日 embargo 及 OOF 防線；本線未逐筆重驗正式來源可得性，不能因此宣稱無 leakage。

[Gate 7](../GATE_7_ML_SHADOW_ENGINEERING.md) 記錄的 11 symbols／22,093 rows／4 folds、426,624 base OOF／12,984 meta OOF 是日期化工程證據；ECE／Brier、PSI、獨立成本後 Formal OOS、bootstrap 超額下界、MDD／CVaR／turnover、coverage 與自然 shadow credit 未評估。沒有可接受的樣本量／不確定性／成本後增量效果可供判定正式模型值得重訓。舊 compact model hash `92668aa574967990fa560aef8a48e595296eb22f3fef2a4264cff08210d78b6d` 只作歷史參照，不當現行 registry 身分。

目前小型manifest實讀到15個latest pointers，保存pointer raw SHA、目標raw SHA與選定metadata，未反序列化模型。OOC當前`allocation-ooc-868b7e805f5c03c65dc303e4`為`allocation-ooc-training.v5`，3,353,096列、62 features、41 folds；其canonical manifest hash為`314f29f16037572854d0561f08f52716c29ce6f1c848b68b46d1e6e9f729d118`，file-byte SHA為`f814e5b56180983f6bbed7e2334f9f58a709288b5fea992276b29356c904ef04`，兩種hash不得混用。

該OOC指向舊Direct `direct-ooc-505c6adaf3f71a0c8f0a274e`，而Direct最新pointer為`direct-ooc-a1e00e51c5144283b7dbe72f`；latest不同不代表舊Direct可刪。final Meta manifest `67e65ecf6417456129ceb402c0f58f86d763053460b55958cea455709f02f281`有2,897,709 train rows、test rows=0、label cutoff=`9999-12-31`，只是全資料fit，不是OOS，也不單憑此宣判leakage。

已核此第一跳Direct file SHA `61d806ef005d0881911201104079c1acc92826a26bd8a331b9bd79156983ffe8`及canonical hash `e053aaf32bf978834eaf158791ad1170cf0d2909fea0f3a207bbe801150f0689`均等於OOC所釘選；來源manifest覆蓋2014–2026年shards、`training_as_of=2026-09-04T08:30:00+08:00`。這只驗第一跳小型manifest，未驗完整shards／raw／模型byte閉包，不能授來源PIT或重建資格。

現行OOC的cross-fitted OOF診斷已量到ECE 2627 bp（門檻500）、Brier 3175 bp；未校準基線分別2576／2956，校準未改善。`oof_diagnostic_only=true`、`promotion_pass=false`、`production_eligible=false`；drift仍無post-freeze輸入。這些是manifest記錄的研究診斷，本線未重算，不是Formal OOS投資效果。七個blocker含20日自然shadow不足、classifier calibration未附模型、正式Rule歷史、PIT sector、cash-only ledger、成本後OOS比較及drift缺件；不應先重跑大型fit。

日常狀態依 [B 的原收據](../BALDR_DAILY_OPERATIONS_RECOVERY_20261021.md)及10/22工作樹交付契約：copilot `passed_rule_only`、forward缺PIT archive、evidence blocked、authority skipped。新B契約`docs/03_data/BALDR_TRACK_B_DATA_READINESS_CONTRACT.md`（閱讀時WIP；file SHA `7c1a54bb484aa954e008f9953ee27c9e36949124e166d2b01078823d9c29041e`）已明定Source／Version／Time／Coverage／Quality／Execution／Consumer／Qualification；本線採用此交付要求，不另造資料資格。B記錄10/22 Raw PIT blocked_upstream、formal compatible=0，172個Forward更新仍有21缺價／56pending，不能視為已交付可訓練資料集；自然狀態與其修復由B核定，本線未獨立重驗原收據。

### 具名重訓候選與成本界線

- `CORE19-current-restated-successor`：僅考慮修訂來源研究比較；必須先凍結新資料 identity、時間切分、Rule／舊 CORE19 benchmark 與成本／換手評估，另批執行。現有研究檔不覆寫。
- `allocation-v2-causal-successor`：先解決 Rule state／sector／health custody、完整 Meta OOF 及 replay semantics；cash-only state 不用 sidecar 升格。正式資料資格與自然 maturity 未成立前 NEEDS_DATA_QUALIFICATION。
- `H20-calibration-successor`：待成熟、可接受來源與成本情境／calendar 及最低樣本數預註冊；個人樣本不能混作全域效益證據。

現有 `data_module/ml_storage_capacity.py` 的排程預算為 persistent 35 GiB＋temporary 40 GiB＋reserve 20 GiB＝95 GiB；初始 60.24 GiB 不足，缺約 34.76 GiB。其他 heavy-chain 預算較小也不代表某次 fit 可行。完整重訓 CPU、RAM 與 wall time 尚無同機實測，保持 UNKNOWN；不提出虛構節省率。未授新訓練 run；日後小型隔離工程試驗建議上限 1 GiB persistent、1 GiB temporary、20 GiB reserve、8 GiB Job RAM、12 程序，仍須事先定義驗證目的與時限，不能代替完整訓練估算。

## 長期生命週期政策提案

以下為 dry-run 設計，不安裝 TTL、不修改既有 producer／設定／排程。

| 改善 | 空間與讀寫／CPU成本 | 相容與恢復條件 |
|---|---|---|
| Build／Trial 保留 current＋已接受 rollback＋具名 regression，其餘待核 | 上限由本輪候選量測；只讀 manifest，避免重新 build／複製整包；釋放量未批准 | A／Integration Owner 提供完整 RC／QA／launcher 依賴；還原整包及 source pin |
| Failed／resume assembly 完成或放棄後進人工 queue | 可涉及數十 GiB／檔；不要重 hash／copy 大 SQLite，先核小型 manifests；丟棄即喪失 resume | 查 active lock／writer、上游原價、可重算版本及恢復成本；B 保護唯一修復 staging |
| Immutable feature／dataset block 按內容身分重用 | 節省額＝重複配置−索引成本，目前 UNKNOWN；可減新 SSD writes，但首次 hash／index 有讀取成本 | 優先沿既有 Direct／OOC block reuse，不能跨不同 PIT／revision／source identity 合併 |
| Checkpoint 保留 latest resumable＋best accepted＋reference | 模型／optimizer 尺寸與訓練 framework 支援尚待逐 run 量測，不先訂破壞性數量 | 不把 optimizer state 與只供 inference 的 artifact 當可互換；失去 state 必須新 run |
| Cache TTL／log 旋轉採 preview | 小 cache 先核重建成本，壓縮額外 IO／CPU 未實測；禁止全量重壓 DB／FA_Data | 精確 namespace 排除 source／receipts／FAIL／Golden；TTL 不依 mtime 自動刪 |
| Parquet row-group／增量處理 | 優先新隔離輸出做小樣本 A/B 比較 bytes、peak RAM、read／write latency；目前未實測 | 保持 schema、排序、precision、PIT、hash／registry identity，先取得新 reader 相容證據 |

## 跨線 Contract／Patch Proposal

1. **B：資料資格輸入**：對具名 dataset 提供 source／unit／venue／revision／availability／calendar／cutoff custody、train/validation/OOS freeze、成熟 labels、缺值／coverage 及用途接受；另提供 raw／promotion 自然 run exact receipt。不得用 current-restated 或 current-only 月營收替代歷史 PIT。
2. **A／Integration Owner：Release 引用閉包**：明列 current RC、rollback／Golden／QA 及 launcher；核 build／Trial 候選是否還被 UI regression 或文件引用，再決定需保留版本。
3. **B／原 migration owner：staging 與 SQLite**：明列大型 computed／assembly 仍需續跑或恢復的 exact identity；鎖檔存在不等於活躍，未核 handle 也不等於可刪。
4. **唯一 Integration Owner：文件整合**：本線不接管共享權威；核本 commit 後，將本目錄入口連入 Data/ML QA index，核新 CLI 說明是否適合架構／維運手冊。Feature Map 新工具 coverage 與 Snapshot 狀態若有需要，由該 owner 採用具名 patch；本輪不改產品 Gate。

## QA 與限制

原始命令、stdout／stderr、Windows Job 終態與 SHA 留在本 task。使用共用 workspace mutex、kill-on-close、8 GiB committed memory、12 程序；root 串行執行。鎖忙的 attempt 沒啟動子程序；初始化編碼錯誤與 supervisor 終端輸出編碼錯誤保留。後者的子程序 exit0、Job 自然排空與 handle／mutex 終態由原收據另核，不能只看外層工具 exit。

最終Python編譯與8項定向測試通過（0.49秒）；測試涵蓋hardlink／重疊roots、祖先junction、depth／files／entries預算、unknown allocation、普通未壓縮NTFS配置與超長路徑。收據`single_owned_qa_532f0fe4f6e64c19921c615882c2e681/receipt.json` SHA `9568d957189455a75daf3666a91bd6058099864ce937427e1ae10ea2ed54e4ef`記錄exit0、剩餘Job程序0、handle關閉、mutex釋放、未強制清理。

Task／文件結構與兩個連結來源最終檢查通過，errors=[]；收據`single_owned_qa_b5390a73444b4f4bad2c86c6fed3232c/receipt.json` SHA `02dc1f45d6e4e78b1d193c7b3087e3e32516027f39b84b3b139557929f5ff3b1`。中途缺evidence子目錄及category=qa欄位的失敗收據保留；只修紀錄位置／標記，未改測試門檻。

未改UI、金融計算、服務或排程，不重跑完整UI／mypy／全產品驗收；這不代表那些項目通過。大檔SHA、全F extent、私人模型內容、全部registry閉包與open handles未驗；盤點僅呈現已觀測子集，非同時點全量或實體可回收下限。沒有刪除、釋放或模型升格成果。
