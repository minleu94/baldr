# 中央完整模型名單／自然 caller／BB UI 整合

## 接任與採入

接任基準 `f344c0d7ed214a6bfc8318666d22c4feee708020`，tracked clean；原 handoff SHA-256 `db0f47fe4946378b530eb609f1088ebff18f4117b8a20e30e8d0ce24b77f2a81` 相符。三 lane 固定 base `d222ba0dbd3e87991ba5404fec29470646af2c68`，只在 immutable commit 交付後轉鎖。中央不重審／重跑已完成大 gate。

| lane | 原交付 | dev 採入 | 驗核 |
|---|---|---|---|
| H20C01 | `0b6455dc748e1c7945f1838a6ea4982b293efa3d` | `9e6b2246` | 五新增檔／frozen API／blobs／43 focused receipt |
| H20N01 | `4b2a89a298511cacafc1d6342ded3d3ddec81e29` | `e61ae912` | 五新增檔／exact request codec／blobs／42 focused receipt |
| BBUI01 | `1e5e9cede5c22c7093299203d7732e091a852f5c` | `30193df6` | 五檔含明示擴鎖 bookmark codec／v2 body/hash oracle／64 focused receipt |

上述 lane 計數不相加作完整 App 通過數。三包新增 exact tests 與中央兩 tests 入冊；前輪 `test_baldr_daily_bbands30_upper.py` 漏登分類本輪補記。filesystem／inventory **1302／1302**，missing／stale／docdrift **0**，direct **12** 保持。metadata audit 明示 skip-pytest-collection，分類不授 runtime credit。

## 中央產品接線

推薦工作區新增「個人模型選股研究（H20毛報酬）」分頁，TaskWorker 唯讀原 activation／reference／manifest／逐股 public prediction reader。manifest 原完整分母 1–50 股，gross 用 int bp 排序、同值股票穩定排序、unknown 保留後置；刷新先清旧列，背景 generation／配置路徑／closing／shutdown 不符回呼拒收。選取再次驗原母體，建立原 ResearchStockContextDTO，result_id 留空，source_id 為原 prediction identity；sample 不冒 canonical result。報告沿原決策日，卡片驗 expected reference；返回重讀、恢復同份記憶中的 exact selection，不以同股／最新名單替代。

日常主流程三分支均接 register caller，原 no-model entry body／schema 不改。原 batch 全員驗明 exact entry 後，私人 root 的 `h20_natural_entry_bindings/{原capture raw SHA}.json` create-only 保存 manifest／entry pins 元資料指標；不複製預測。每個原 outcome 已由原 verifier 保存讀回、取得 immutable pins 後，consume caller 以 capture SHA 定址登記，重核完整 manifest／source／模型／row／20 session，成熟 join 沿原 publisher 保存。此設計能處理後續舊預測成熟，不掃 latest/glob，也不替午夜錯配登記。缺件回完整 pending，disabled／未配置零 ports；錯配 blocked，不吞為成功或提升原 global/formal。

結果路徑：`current_observed_input_capture.personal_h20_natural`、`current_observed_natural_research.personal_h20_outcomes`；原 private prediction 是唯一預測保存來源。既有05:45 Task 設定／principal／trigger／action 未改，未手動啟動。

BB 第三條件 UI／完整 saved v3 methods、BB 表格／source trace／收藏／精確 DTO 路由已整合。bookmark v2 全 body/hash 保持；v3 decoder 重驗原保存 manifest、stocks、row、conditions、方法與版號，不查 DB/latest。30 根不足、缺件、來源參數 lineage 未核分別保留 unknown；有限 BBANDS30 upper 不等於 compression／U1 完成。

## 本輪同 source 驗證

- 中央新增接線及原 product evidence：**18 passed／5.82s**；首輪原11項 sandbox ancestor no-follow handle 阻擋8 fail／3 pass，未改 guard，在合成 Temp 允許環境11 pass／4.35s，紅結果不隱藏。
- affected 12檔一次 **200 passed／1 failed，33.18s**。唯一 `test_new_process_same_original_cohort` 在原 source reader 因祖先 metadata 變動 `source_changed_during_read`，未到新 assertion；同原節點／guard／assertion隔離Temp重驗 **1 passed／0.65s**。因此 coverage **201 passed**，不是單次201全綠，不與lane收據相加。
- 刷新清旧表列後只重驗中央 UI兩項：**2 passed／1.48s**，取消、stale、配置改變、關閉與 exact route/return均保留。
- mandatory 順序：Workbench **85 passed／2.98s** → update validator **25 pass／4 skip／0 fail** → full-roots mypy **848 sources／0 errors**。pytest cache write warning只記環境限制，未改 production。
- scripts explicit-package-bases targeted mypy **3 sources／0 errors**；原先同時檔案路徑與namespace名稱重覆的診斷保留，未加ignore或改public模組。
- inventory治理 **13 passed／9.50s**；metadata audit exit0。**21 changed Python files compile**、quant precision/look-ahead、diff-check通過。量化guard為靜態邊界，不冒全面金融證明。

raw／JUnit／compile清單／metadata／新程序結果保存在 ignored `output/qa/baldr_central_resume_20261007/`，最终收據集中記 source blobs 與 SHA。完整操作入口、步驟、參數、結果、限制與排錯已同步 Manual；架構／Snapshot／Index同步本增量，不改產品方向、目標 maturity 或原路線。

## 實際啟用、排程與自然品質分列

既有真私人 root `D:/Min/Python/Project/FA_Data/personal/recommendation_h20` enabled revision1，模型 `rec-cal-3f8b2c276ef316e28de3806d` 保持，未新fit。中央另以新程序、producer禁止、Qt offscreen 唯讀完整真保存10股：**10 available**，manifest `sha256:a2cad4b3ac8ff978f52ecb28d006da37573cd1313efcee28bfc1d5d632661e76`；原cycle `raw-pit-20261006T120503289532Z-37376-cc45d548162349fd97ee2dcf08a345ae`，decision10/07／source10/06／feature10/05。gross排序：1477=2557、1225=2204、1560=2135、1721=2093、1714=1931、1465=1673、9935=1314、3207=835、2382=684、1256=365bp。exact selection可恢復；私人所有已存檔bytes／mtime不變。新程序核保存與widget，不宣稱前景Native或完整真MainWindow點擊驗收。

此十股已有真推論保存，現新增產品完整名單／排序 consumer；不是全市場模型排序，也不替換原 canonical機率／ranking。真自然結果仍 **10 pending／0成熟**，10/06 entry不補配10/07預測。Brier2730 vs2500是機率head揭露；gross／成本後品質未成熟另列，不當永久個人啟用gate。

下一原自然排程 **2026-10-07 12:45 UTC＝Pacific05:45＝Taipei20:45**，父層唯讀驗收新 raw-cycle／terminal／manifest／全原 prediction pins。未手動trigger，未宣稱下一run成功。自然caller接線合成可用；其真登記、成熟與品質尚待原自然週期。原Stage1done/8partial、UX2done/22partial、七有限closed UX03/04/05/06/09/15/17與F1 18.6219658% vs20%／Journey8.109s vs8s保持。

## 唯一仍受批准阻擋的工程

BBP01 `b7830889437365df7ec7d9bbb399cf1895686ab6` 已交四檔44pass，仍未採入。先前自動審核拒 `git cherry-pick b7830889437365df7ec7d9bbb399cf1895686ab6`，將no mainmerge解讀為禁止localdev採入；父層已向使用者詢問。中央未重試、未抽檔、未間接採入。須父層提供直接human批准後，才原工具一次localdev cherry-pick，然後真v3 owner→parent→acceptance→saved/newprocess小型delta；不重44或全面gate。此阻塞不取消已完成三包接線，不宣稱BB全母體日常完整鏈done。

無push/main merge、market DB write/migration、ACL/憑證、舊私人資料搬移、清理、自動交易、真fit或前景Native。回滾先核其他dirty，僅具名中央整合提交revert；會停止新增入口／caller，原保存資料不刪。
