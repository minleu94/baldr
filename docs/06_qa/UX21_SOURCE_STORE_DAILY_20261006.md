# UX21 實際來源、隔離保存與日報限定收據

基準 `48feaf7061c15b54db5062a3b2c9e6bfc731cf01`，只承接 UX21；沒有重做 learner／Library／personal，沒有另開 agent。原計畫保留原文，只追加本包及進度分類。

## 已交付

`rule_research_forward_source.py` 以既有 query-only SQLite transaction 讀取明示股票、最多 120 筆既存價格，僅取原決策日及 H5／10／20 exact endpoints。原決策價必須符合 exact parent 保存 snapshot 的 close feature 指紋；修訂、重複、缺列或無效價保持缺件，不借用鄰日／latest。原母體、exact children、排除與未捕捉分母完整保留。

日曆必須指定已存在、hash/raw/全年範圍及 freshness 驗證通過的 TWSE 年度 cache 原檔；沒有網路補抓或 directory latest。session 只代表年度計畫，臨時休市仍未知，跨年度覆蓋不足不推算。cache 的動態 validated_at 不作 revision identity；保存 envelope 另記 observed_at。價格 current-observed、available-at／公司行動 basis 未知，沒有歷史 PIT 或實際成交資格。

`rule_research_forward_store.py` 保存 parent／runtime／DB main+WAL/schema／calendar／row fingerprints／clock／cost／projection identity。沿用原 atomic staging→hash reread→source revalidation→rename、200 GiB reserve、256 KiB envelope、8 MiB／128 包上限，mkdir 前先做容量 preflight。不刪歷史、partial 或 rotate；新來源 revision 追加新 identity，同來源重試 duplicate。完整 projection 壓縮保存以容納多批母體，解壓有 2 MiB 上限、長度/hash/eof/尾資料及完整語意核對，不截斷分母。saved reader 不再查 current DB，後續市場 revision 不改寫舊日期。

新 CLI `scripts/scheduled/run_rule_research_forward_isolated.py` 預設 preflight，明示 `--execute-isolated` 才保存；可把 policy／acceptance 日報接到同 parent 的所有 outcome revisions。既有 daily isolated CLI 增加唯讀 `--outcome-root`，預設流程不變。Qt 母體收據對話框可明示選保存 outcome receipt，背景 worker 重讀，主文顯示目前觀察／年度計畫界線，診斷折疊。取消後若已發布會如實回報保存收據，舊 callback 不套用。

benchmark adapter 本包僅接受明示 null，未配置即未知；沒有把 market_indices 的名稱／調整 basis 自動當相容 benchmark。成本可 null，或明示版本及既有比例 entry/exit 整數 bp 契約；不補零。已配置 target 成本可計 net，benchmark 未配置則 excess 仍 null。這項 benchmark 來源接線仍屬工程缺件，不稱自然等待。

## 實際市場鏈與失敗證據

只讀 `D:/Min/Python/Project/FA_Data/sqlite/twstock.db` 與明示既存 `twse_holiday_schedule_2026_20261006T002502660076Z_21ea36fd2769.json`；隔離 output/qa 保存 1477、2382 及一股明示排除，兩方法完整分母各 3。

| 原決策日／股票 | H5 毛報酬 bp | H10 毛報酬 bp | H20 毛報酬 bp | 資格 |
|---|---:|---:|---:|---|
| 2026-09-01／1477 | 128 | -179 | -256 | 目前觀察來源的事後研究 |
| 2026-09-01／2382 | -409 | -263 | -234 | 同上；符合方法不是 selected |
| 2026-10-06／兩股 | null／未成熟 | null／未成熟 | null／未成熟 | 當日 exact 價格缺件，不借 10/5 |

年度計畫 endpoints：9/8、9/15、10/1；今日計畫為 10/14、10/21、11/5。成本／benchmark null，因此 net／excess null。歷史 capture 是現在觀察，不回填 fixed-day acceptance；今日實際 producer→parent→日期接受（recorded incomplete）→outcome→日報→新程序／offscreen UI 已執行，沒有宣稱今日完整觀測或自然成熟。兩路 duplicate、新程序結果一致，main/WAL size／mtime／inode pins 前後不變。不存在來源 DB 的路徑明確 blocked，未建立 outcome root，沒有 fabricated 成功。

Raw 收據（ignored）：`output/qa/ux21_source_20261006/actual_pipeline_receipt.json`、各路 producer/outcome/duplicate/new_process JSON、today/daily_report.json、historical_actual.png、today_actual.png 與 UI 文字讀回。背景圖片使用明示中文字型，已視覺核對；不是 Native／真人驗收。

## 驗證

初輪長 Windows pytest 路徑觸發既有 producer publish_failed；短隔離 root 後驗證成功，未改 producer 或放寬 guard。日曆動態 validated_at identity 差異已修正，來源 revision guard 保留。focused、UI 強制檢查與最終數字於本節追加；不把重跑案例加總。

Look-ahead 自查：原訊號只用保存決策截點；forward 價格只作事後成效且不回灌訊號；as-of 不接受未來，horizon 未成熟 null；沒有交易選擇、MFE/MAE、期間停牌、ML labels／fit／promotion。全部 PIT/formal/training/natural/execution false。未知成本與 basis 不補值；既有效能接受例外不重開 gate。

## 原計畫 partial 分類（沿最新收據，未重啟全面審查）

計數仍為九階段 done 1（0）／partial 7（1/2/3/4/5/6/8）／pending 1（7）；24 UX done 2（01/02）／partial 20／pending 2（22/23）。下表「工程就緒」僅指已有具名收據的有限切片，不升格整項 done；本包沒有足夠證據將所有 partial 說成只等自然或真人。

| Partial 項目 | 已交付工程／可用範圍 | 程式／整合仍缺 | 外部驗收／證據 |
|---|---|---|---|
| UX03 | 收藏 exact 來源／返回切片工程就緒 | 全九工作區整鏈尚無完整接受收據（由 UX24 收尾） | 新跨頁 Native／真人 |
| UX04 | 具名 cohort 名單及 pinned 下鑽已就緒 | 正式資料 owner 配置／部署沿 UX19/20；不新增限定名單人工 gate | 整鏈與真人 |
| UX05 | AND/OR、預設、why/why-not、原排序切片就緒 | 更多方法屬 UX18 擴充；不把未開方法當現功能失敗 | 真人理解／整鏈 |
| UX06 | 當期／原保存來源、摘要與舊 1477 重試重讀已就緒 | 完整圖表能力沿 UX08，整鏈沿 UX24 | 新畫面／跨頁 Native、真人 |
| UX07 | 官方文件與 coverage 矩陣完成 | 圖商 prototype／嵌入／封裝與 fallback 實測仍缺 | 逐格商品支援不可由文件推定 |
| UX08 | 原生同源歷史價／MA20/60／精確表就緒 | 保存技術 artifact、其他指標、markers、viewport／paint fault 等仍缺 | 新 Native／真人 |
| UX09 | 歷史索引／分頁／索引版本復原工程就緒 | 整鏈接受歸 UX24；沒有本包新增索引工程缺陷證據 | 新分頁／跨頁 Native、真人，真長期增長 |
| UX10 | 雙 MA／方法與家族分離 pinned consumer 就緒 | 跨策略家族仍缺第二合格 family 來源／接線 | 真人，不把符合數當機率 |
| UX11 | 設定規則卡／Registry 保存 source-only 讀回就緒 | 完整 typed execution／績效相容來源仍缺，未知不造結果 | 新 Native／真人 |
| UX12 | Journal 有限操作流／保存查找已有接受收據 | 全歷史 store 可比性尚無整項完成收據，不能判「只等外驗」 | 新整鏈／真人；微小速度差已接受 |
| UX13 | 具名母體盤勢、收藏原研究切片就緒 | 完整提醒／個人資料種類接線未有整項完成收據 | 真實使用／提醒理解 |
| UX14 | 風險與系統缺件分區已交付 | 完整分帳／portfolio、notes、ledger 等 personal 接線仍缺（其他 owner） | 真實帳戶操作／真人 |
| UX15 | Manual 與已交付功能文件同步 | 沒有本包已知程式缺件；真人發現問題再修 | 3–5 位未參與開發者任務驗收尚未完成 |
| UX16 | close/MA current-observed 能力與來源 contract 就緒 | 全方法／正式母體來源與 consumer 覆蓋仍缺 | 官方 available-at／歷史 membership／PIT |
| UX17 | 基線／既有改善、F1 性能例外已接受 | 新功能全資源整鏈歸 UX24；不重開 18.6219658% gate | 同機器長流程資源證據 |
| UX18 | 共用 close/MA、固定方法／原排名 consumer 就緒 | 完整 feature/method 字典及其他 consumer 擴充仍缺 | 未開方法相應資料資格 |
| UX19 | 隔離完整 producer／atomic／fault recovery 已就緒 | 正式 roots／ACL／segment rollover／長期容量部署仍缺 | 真增長、正式位置決策 |
| UX20 | 多批 parent／policy／isolated daily owner 工程就緒 | official/upstream terminal date 接線、正式 source/output、Task dry-run／監控部署仍缺 | 正式 Task/account 決策、自然逐日收據／custody |
| UX21 | 純 endpoint／實際 source／atomic 保存／UI 與隔離日報切片就緒 | qualified benchmark adapter、完整 labels／正式 daily 部署仍缺 | 成本／benchmark 政策決策、實際 session/custody、自然成熟／準確度、Native／真人 |
| UX24 | 各包 targeted 與 UI 必要檢查已有證據 | 新功能全鏈 lineage／容量／資源整合接受尚未完成，不能以單包替代 | 新 Native／真人、長流程資源與自然證據 |

UX22／23 仍 pending，不 fit、不開 shadow Task。以上列的是原計畫差距，並非本包新增 gate；官方全市場、更多方法／新家族等擴充不阻擋已批准的具名研究切片。完整完成判準大於單包，因此 done 保持 2，工程已交付範圍另列，不再用同一 partial 隱藏。

完成本地 commit／readback 後停交父層；UTC 07:00 安全停止約束有效。沒有正式 Task／DB 寫入、migration、訓練、push、清理或前景 Native。


## 最終驗證收束

受影響 XML：92 passed（7檔最終廣域）、39 passed（store/daily修改後）、19 passed（reader/UI修改後）；按classname＋name去重為 94 個不同案例，沒有重複相加。Workbench 85 passed、validator 25 passed／4 skip／0 fail；full mypy 812 source files、另CLI 2檔、9檔py_compile、quant guard／diff check通過。實際 CLI saved/duplicate＋同 parent 日報與兩張 offscreen 畫面讀回已驗。日報 store 只掃一次再按exact parent分組；不拿未核對 parent record 授 outcome verified，避免按每筆日期重掃整個 store。明示 JSON input 即使命名 receipt.json 仍按schema讀取，保持舊輸入相容。Raw validation_receipt.json及三份XML保留於本包QA root。

有限第一版切片工程就緒、主要待外驗／整鏈收據者為 UX03/04/05/06/09/15/17；仍明確程式或部署缺件為 UX07/08/10/11/14/16/18/19/20/21/24；UX12/13缺整項完成收據，不能擅稱全部程式已就緒。此分類不把有限切片等同整項，整項done維持2，外驗等待不阻擋已批准可用工程。


### 最後畫面缺件可讀性補正

今日未成熟結果的原決策日價格缺件也明示於主文：2筆價格資料不足；來源未調整收盤價，非含息總報酬。結果與缺件分開保留，不隱藏已知不足。8個結果UI案例最終通過；Workbench85／validator25+4skip／mypy812再次通過。首次新UI test只因ASCII連字號與既有em dash占位符不符失敗，修正test接受既有符號，沒有改數值或guard，原失敗XML保留。最後XML去重 95不同affected案例passed，10變更Python檔compile，quant/diffcheck通過；前段94為補正前數字，由本段取代。95不包含Workbench85。原計畫只追加、原prefix完整；進度1/7/1與2/20/2不變，完成commit/readback後停止。
