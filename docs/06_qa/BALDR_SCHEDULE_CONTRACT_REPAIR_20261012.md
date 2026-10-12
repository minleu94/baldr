# 2026-10-12 Paper 身分與 G9 日曆契約修正

本次是使用者另行授權的人工工程修正及本機 commit，不是 06:20 唯讀 automation。未修改 Windows Task、automation 時間／目標／啟用／通知、正式資料、Paper 帳本、sidecar 或模型；未啟動 producer、抓資料、正式訓練、promotion、交易或 push。既存 Snapshot 與補完進度文件的未提交修改保留，不納入本次 commit。

## 已定位與修正

| 用途 | 精確問題 | 工程修正 | 驗收界線 |
|---|---|---|---|
| Evidence 的 Paper Health 來源 | `paper_health_source_receipt.blockers` 為 `position_health_market_source_unhandled:PositionHealthMarketSourceError:health_baseline_identity_entry_date_invalid`。上游 baseline 把 entry 保存在 `position_identity_source`，carry helper 卻讀外層缺失欄位，並漏傳 `available_at`；pipeline child 本身 exit 0。 | `PaperPositionIdentityProvider` 沿巢狀原 entry 日期、fill／event、hash、可得時鐘及 coverage pin 延續；核對身分與日期／時鐘。缺失、未來、錯身分或 CLOSED 不授 carried identity。 | 跨日 refresh→再次 refresh→公開 market source producer 通過，並保留 Paper／ledger 原 bytes。舊 baseline 已遺失的證據保持 unknown；沒有手填、回溯補鐘或直接宣稱自然排程恢復。 |
| G9 live capture session proof | `live_capture.calendar_diagnostic=ValueError:hash-bound official annual calendar cache is required`。caller 還讀已移除的私有 `_schedule_evidence`，即使有效官方 cache 亦無法通過。 | 改以公開 `OfficialTradingCalendar.read_operation(allow_online_probe=False)` 在同次 operation 判定交易日及取得 evidence。 | 有效 cache 可建立 research-only proof；缺檔、過期、hash 損壞仍拒絕，本地市場指數列不能取代官方年表。source revision／technical prospective／自然成熟／人工接受 gates 不變。 |

Owner 為排程／Health 與 G9 caller 維護者。本次修正來源取得與契約傳遞，沒有更動任何金融計算。Look-ahead 自查：entry 必須早於原 snapshot，原 snapshot 不晚於目標 snapshot，原 `available_at` 不晚於本次觀測；日曆沿 live operation 重驗 cache bytes／freshness，不引入歷史 clock override 或線上 fallback。量化 guard 不取代這些語意檢查。

## 同次來源與仍未解事項

來源根沿 wrapper 與 `output/ml_research_storage.json`：正式市場為 `D:/Min/Python/Project/FA_Data`；G6 research 為 `D:/Min/Python/Project/FA_ML_Research`；G9／Bank 分別為 sibling `FA_Data_Shadow`／`FA_Data_Shadow_BankTaiwan`；Paper 與 ML Forward config／child 各沿 repository 隔離根。下列 SHA 均為本輪唯讀重算的 **file bytes SHA-256**，不是 canonical content hash。

| 原結果／用途 | 精確 receipt／run 與 bytes SHA | 仍須驗收 |
|---|---|---|
| Evidence 原 wrapper failed／exit 2 | 正式 `output/scheduled/evidence_pipeline_dry_run/latest_status.json`，05:15:02 PDT；SHA `69cc0c025e67998a9c4a5768cddeae8ec05ba1d7c4f5ad49f55d2956eec6552f`。 | 下次自然執行沿同次 producer、baseline、market source 與 consumer 重驗；原歷史 entry 缺件由 owner 取得原證據，另行受控處理。 |
| Paper EOD blocked | repository `output/paper_execution_eod_replay/receipts/paper_execution_2026-10-12_3217b90caba33a8e_20261012T130117301757Z.json`；SHA `c69d061bc2db1696fbeb6f254907c8b39b48b878edb892c75d99bf19017183ed`。 | `result.blockers=[daily_prices.open:1435 is missing]`；決策 10/08、T+1 official execution 10/12。Data owner 需取得該日 1435 官方開盤來源與原資格證據；不補價、不換 frozen recommendation、不把 gate ready 當成交通過。 |
| G6 research completed、formal raw hold | run／cycle `raw-pit-20261012T120503297513Z-38512-4fb13c31a4e54359807c666c778281d5`；research terminal `current_stock_cycles/2026-10-12/2f8841e8abda9b545c0af1e26804ddcd/terminal_receipt.json`，SHA `af6b286d8ecbfe230b092bc2a30cdb986e39b5b850bf1667907dcad4ffe01191`，與 parent pin 相符。 | Formal raw 仍為 `blocked_source_revision`／`DailyPriceSourceRevisionError`，2014-01-02 起歷史需 revision-aware 資格；research 完成不授歷史 PIT 或正式訓練。 |
| G9 原 terminal failed_dependency | `FA_Data_Shadow/recommendation_learning/runs/2026-10-12/scheduled-snapshot-f96890dc3ff235c3-eff4d2a/attempts/attempt-d90f0590d0d7fc33e3ecaebf.json`；SHA `768a9ea30ced6e5b066fae268af8c8cbf254b689d3ec6ba6a47cabd4a5402856`。parent 06:44:54 PDT 結束，未超 CMD 四小時預算。 | 除本次日曆 caller 修正，仍有 `prospective_receipt_or_symbol_coverage_incomplete`、`prospective_feature_snapshot_failed:DailyPriceSourceRevisionError`、`formal_technical_source_contract_unverified`，不能全部歸為自然樣本不足。Bank 06:45:02 結束 `failed_dependency` 也不改判成功。 |
| ML Forward 當次 child 被擋 | 沿 launcher `20261012T002501062569Z-6a688525/stdout.bin`、當日 config 追 child 根 `output/v4_ml_daily_derived_shadow_real_v2/scheduled/ml_allocation_forward/receipts/20261012T003003695101Z-41316.json`；SHA `d837b79439aa7a2f5b079a75ec022f15280d107e3495d2844598cec6e38c2e94`。 | `blocked_child_exit`、child return 1／`blocked_source_revision_release`，另有 post-deadline maturity blocked。repository scheduler 舊休市 latest 不能代表當次結果；release／Data owner 需補實際 source/release 資格，未 promotion 或重訓。 |

Sector DNS、verified PIT denominator、sidecar／formal input 與 weekly 查詢失敗依原 owner／來源接受流程處理；本次沒有以 retry、補造歷史或降門檻解除。Forward 的 `outcome_price_missing` 保留，原收據列 1538 的 official maturity 2026-09-17／09-24；新行情不能解除歷史缺價。上述資格／缺價均未由本次程式回歸接受。

## 驗證與可回滾範圍

Windows inspector 先依 runbook stdout-only 查 21 tasks；sandbox 返回 query unknown，經精確 host read-only 工具核准後，同一查詢於 **2026-10-12 10:52:21 PDT（17:52:21 UTC，台北 10/13 01:52:21）** 回讀全部 21 tasks：存在／啟用、action／trigger／cwd 匹配、missed runs 0。這是登記核對，不是 21 條 producer／consumer 全鏈 PASS。

Root 序列 QA 使用 suspended assign-before-resume、全 Job 8GiB committed memory／12 process 限制與 readback、啟動前可用 RAM ≥8GiB、workspace mutex。每輪 terminal 後確認 Job 自然 0、process／Job handles 關閉及 mutex 釋放；不依賴強制清除才成功。原測試未降低斷言。

- Paper identity focused：22 PASS。
- Identity／daily Health／market source／Forward thesis／Evidence wrapper 五檔：134 PASS、1 既有 SKIP；短路徑重驗的 native exit 0。
- G9 public calendar operation：4 PASS、36 deselected；有效／缺檔／過期／損壞各一案例。
- G9 完整 learning-loop：40 PASS／73.88秒；Job native exit 0、自然排空。
- 兩個產品來源定向 mypy：PASS；四個變更 Python 檔語法檢查：PASS；金融精度與 look-ahead AST guard：PASS。各 Job native exit 0、自然排空與 handles 關閉。

接受的本機 Job receipts：`regression_1791829116816319700.json`、`learning_1791829363617780700.json`、`types_1791829499280726400.json`、`compile_1791829508114165800.json`、`guard_1791829508856434500.json`。最終 source／test bytes SHA：identity provider `ef5d406b11c2352a987c8bd6ad6fb2d8d09d0066031d5afc04f27446ef2ddd58`；G9 caller `e2030c2d824bcc3c937c8d78906475f736b8d2a298bbf1ef2fedd7320b3af555`；identity tests `4dc6eec26af85fb19958104196b4bbe8b275e904cb42a04f4023176eb7384b3e`；learning-loop tests `012c9df8bb54efd843b2525ae72d52baae6f77cd2e06910c2d98da3a431a6775`。

初始 sandbox focused 因暫存路徑 `WinError 5` 失敗；host 隔離重驗後通過。首輪五檔 regression 在過深 Windows QA 路徑的 machine-policy fixture 失敗，改用已排除的短根後原全部斷言通過。learning-loop 初輪 39 PASS／1 FAIL，runner 強制 `PROFILE=test` 導致設定根增加 `_test` 子目錄，lineage 臨時路徑建立失敗；移除該環境污染、保留隔離 DATA_ROOT／OUTPUT_ROOT 後原40項全部通過。初輪不作接受證據。本機 log／Job receipt 保存於 ignored `output/qa/schedule_identity_repair_20261012/`，不提交 raw output。

回滾只撤回本任務 commit 的 source／tests／文件差異；原資料與歷史失敗收據不回滾、不刪除。操作說明同步 Manual §12 與 audit runbook；營運 QA 索引可到達本文件。產品方向、Roadmap、架構模組邊界與正式接受標準未變；沒有將局部工程修正推升為完整產品或自然排程接受。

本輪來源閱讀：graphify CLI trampoline 無法解析安裝路徑；唯讀核對既有 graph 的 `PaperPositionIdentityProvider` 節點後，以當前原始碼與實際 receipt 判斷，不重建圖譜或把舊圖當最新證據。
