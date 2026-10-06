# BBUI01 有限 BB 上軌第三條件 UI（2026-10-07）

## 範圍與固定身份

唯一 dispatch：`output/plans/baldr_parallel_remaining_dispatch_20261007.md`。固定 base：`d222ba0dbd3e87991ba5404fec29470646af2c68`（已用 `git rev-parse d222ba0d` 核對，不使用 mutable HEAD）。獨立分支 `lane/baldr-bbui01-research-20261007`、worktree `output/worktrees/baldr-bbui01-research`。開始時主 checkout owned files 無 tracked 差異，沒有借用 BBP01 未提交檔。

原三檔排他 ownership：`ui_qt/views/daily_market_research_view.py`、`tests/test_baldr_bbands_research_view.py`、本 QA 文件。新中央 `01a11248-f4c3-71b5-b778-002864d08005` 直接明示批准擴鎖 `app_module/daily_market_research_bookmark.py` 與 `tests/test_baldr_bbands_research_bookmark.py`；原因是 base 的原 codec 僅接受兩 MA，無法保存 BB 查詢。共五檔，沒有其他產品寫入。完整 commit／blob／工作樹比對見 raw `commit_readback.json`。

## 原 API 與完成行為

保留 `DailyMarketResearchView(service,parent,watchlist_service,*,bookmark_confirmation_callback)` 與原 `stockResearchRequested(object)`／`ResearchStockContextDTO`。新增 `bbands30_upper_checkbox`，條件只有 `close_above_bbands30_upper`；預設不勾選，原兩 MA 預設與原 v2 producer 呼叫保持。勾選且明示「更新研究快照」才傳 `produce_snapshot(include_bbands30_upper=True)`，工作開始前凍結選擇；原 generation／worker／取消／source guard 保留。

沿已核 `daily-market-feature-snapshot.v3.bbands30-upper` 原 repository、screener、cohort projection 呈現保存上軌值與三態。v3 全 cohort 投影使用該版原完整 method keys，避免兩 MA 假設造成投影失敗；表格保留原 0..10 logical columns，新增 11 BB 比較、12 保存上軌值，視覺位置把 BB 比較放在 MA 旁。BB Decimal 指標排序使用原 projection sorter；未知後置由原 sorter 處理，沒有金融數值重算。方法／來源 tooltip保留保存 feature/warmup JSON、manifest SHA、原方法參數；選取摘要與技術 trace 仍可下鑽。

v2 不冒 BB 證據；29 根有效觀測、缺上軌、來源身份未知均保留 unknown。有效上軌比較可符合／不符合，但來源參數 `parameter_lineage_verified=false` 仍獨立明示「lineage 未核驗（未知）」，不因本地方法契約核驗便宣稱來源參數已核。原 calendar／official availability／historical PIT／模型／交易資格不升格。

codec 公開 API、bookmark v1／原排名 bookmark v2 schema、原 body keys／DTO identity不造版。create 以 verified manifest feature version 限 v2 或 v3；v2 不接受 BB condition/sort，未知版拒絕；原 root→exact manifest/artifact核驗保持。decode依原已捕獲完整 method_contracts 分辨兩 MA／三方法，BB 方法／參數須精確等於原 v3 registry；v3 另用有界原 reader 核同 SHA/cohort/date/stocks、feature version、source identity、原 row 與條件結果。v3 只核保存來源、不查 DB、不讀 latest，缺件明拒；v2 原 codec/body/hash保持。JSON Watchlist consumer 原樣使用新 codec，不停在獨立 JSON 無 consumer。

## 驗證與證據

raw 位於本 worktree `output/qa/bbui01_20261007/`：

- `focused_raw.txt`／`focused.xml`：64 passed，8個具名檔；新 view 11、新 codec 17，另既有每日研究 UI、原收藏、原排名收藏／flow、presets、cohort 回歸。原 UI tests 唯讀。
- `mypy_raw.txt`：targeted mypy `--follow-imports=silent`，2 source files 通過；不等同全倉 mypy。
- `compile_raw.txt`：2產品檔＋2新測試 py_compile 成功。
- `quant_raw.txt`：原精度／look-ahead whitelist guard 通過；本修改沒有新增 float 或金融運算，仍僅保存來源投影與原條件篩選。沒有用決策日之後資料補 BB，未知保留。
- `offscreen_v3.png` 與 `visual_fixture/`：實際合成 DTO→原 producer→保存 manifest→原 repository→view。CJK 顯示方框，僅 offscreen，不宣稱 Native 或完整中文字體視覺通過。
- `commit_readback.json`：固定 base、完整 commit、五檔 blob、raw/JUnit SHA與 clean 狀態。

兩版完整 saved fixture 全由合成 DTO建立，沒有即時 DB造 UI 訊號；原保存/source bytes與mtime不變。測試沿保存→原reader→表格→點股→exact DTO→返回及兩次刷新；BB 收藏→原 Watchlist JSON→重開→原decoder→exact context／條件還原；五種 v3 狀態均新程序讀回。固定 base 原 codec exec oracle比對 v2 全body、bookmark_id、query SHA、payload SHA完全一致。重算payload/query/identity的v2來源偽BB仍由來源版核驗拒絕；異版／未知版／錯hash／錯root／錯參數／錯狀態與缺原artifact fail closed，不fallback latest。

## 中央 Manual 精確素材與剩餘接線

入口：選股研究→每日研究條件→「收盤價高於布林上軌（30）」。先選既有保存來源；勾選只篩選該來源，不更新資料。要明示產生含 BB 的 v3 保存快照，再按「更新研究快照」。重讀、篩選、排序、返回、收藏不重算模型，也不補今天的指標。

參數：BB 研究契約為 timeperiod=30、nbdevup/nbdevdn=2.0、matype=SMA、方向 strict above；等於上軌為不符合。30根是有效OHLC觀測暖機，不等同官方交易session完整。AND／OR與三態沿原規則；兩MA presets會明示清除 BB勾選，BB手動查詢保留自訂。

結果判讀：表格 BB 比較與保存值分開，狀態描述該保存資料的比較；不構成概率、排名完成、買入或模型準確度資格。v2／缺件／暖機不足明示未知，來源參數lineage未核驗另列未知。technical tooltip可核manifest SHA與warmup/feature原數值，點股票沿原exact DTO下鑽。收藏保持原來源與查詢身份；重開後可以明示沿該cohort查最新研究，不能將新版本冒充原收藏版本。

排錯：BB收藏缺原保存manifest/artifact或來源pin錯誤顯示不可核驗，不补latest、重算、改hash或修改舊快照；核對原snapshot_root/cohort/date/raw SHA/feature version。关闭後返回與晚到callback拒收。

中央仍持有 main/config/shared DTO/Manual/Scoped SSOT/原plan/整合；正式日常owner/parent v3 acceptance接線與BBP01 localdev採入由中央處理，本包未替pick或抽檔。重型Workbench mandatory、update validator、fullmypy只由中央稳定union一次。九Stage／24UX、七有限closed、performance例外、compression/U1未決不改。本包不宣稱完整日常模型選股或自然credit完成，不執行Task/ACL/真資料搬移/DB寫入/交易/push/cleanup/Native。

## 回滾

先核本 lane 未提交變更歸屬，僅兩修改檔可用 `git restore --source=d222ba0dbd3e87991ba5404fec29470646af2c68 -- ui_qt/views/daily_market_research_view.py app_module/daily_market_research_bookmark.py`。三新增檔如需回滾，用精確 `Remove-Item -LiteralPath` 各檔；先确认無他人接線依赖。本任务沒有執行回滚或清理。風險為 BB入口／收藏退回不可用，正式資料無刪改。
