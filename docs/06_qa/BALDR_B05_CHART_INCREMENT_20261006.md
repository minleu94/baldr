# B05 原生圖表增量收據（2026-10-06）

固定 base：`ba4e9e59da7946aa66fd5eac3729e091dfe5cced`。Branch：`lane/baldr-b05-chart-20261006`。Worktree：`C:/Projects/PythonProjects/technical_analysis/output/worktrees/baldr-b05-chart`。唯一 dev 整合 owner：`01a11020-88c2-7506-acc3-d51ecb674032`。

沿唯一原計畫 `output/plans/baldr_product_experience_plan_20261004.md` §7.4–7.6 與 completion inventory/review 的 B05；三份 plan/review 只讀，沒有第二路線或原計畫改寫。base 已含的摘要 change／區塊 sufficiency 修復保留，沒有修改摘要 render。七個 closed 與性能例外不重開。

## 實際增量與身份邊界

- `StockChartMarkerDTO` 與獨立 `StockChartMarkerIdentityDTO` 位於新的 owned 純模組。候選須與 caller 已核 record pin 的 record ID、kind、股號、記錄日、source ID、source row hash、帳本 ID／種類、可得時鐘、完整 chart source context 一致。候選／pin 重複 ID、無 scope、空身份、缺可得時鐘、晚於 cutoff、早於事件日的可得時鐘、非圖內有收盤值日槽皆不畫；單次各至多128筆，超界全拒。
- **hash 域分開**：`source_row_hash` 是 reader 已核原記錄的 lowercase SHA-256；`content_sha256` 是 `stock_chart_marker.v1` 的展示投影 hash，涵蓋 source row hash 及所有 marker 身份／時鐘／context。價格 row hash、保存 envelope hash、原記錄 hash、marker content hash 不互換。caller 必須先驗來源 custody／帳本身份，不能從候選自己產出 pin 再宣稱真記錄已核。
- `RECOMMENDATION_CONFIRMED` 僅接受 `account_kind=research`，圖上「研」與明細顯示「推薦確認（研究）」；`RECORDED_BUY/SELL` 僅接受 `account_kind=actual`，圖上「買／賣」與明細顯示「實際記錄買入／賣出」。Paper、聲明持倉或研究入選不轉成實際成交。沒有標記不代表沒有交易。同日不同類型並列，完整記錄留同源標記表及 tooltip。
- 舊 `StockEvidenceEventDTO` 缺 stock/hash/account，仍留 unverified candidates，不變成可畫的 typed marker。沒有修改 shared DTO、保存圖 codec、producer、Portfolio 或 main；沒有真帳本讀取。
- 純 payload 追加 optional `marker_candidates/marker_identities`，輸出 `verified_markers`。舊 caller 預設空 tuple 相容，原 `table_rows`／MA／saved payload 核驗照舊。cutoff 仍是既有報告日界，**不授歷史 PIT 或精確決策時刻資格**。
- 價格 widget 可 Tab 取得焦點；左右鍵、Home／End 選日期，Esc 清除十字線。滑鼠與鍵盤共用日期選取，畫垂直／收盤水平虛線，選取同步完整價格與 MA 精確表的同日列；tooltip／無障礙文字保留 Decimal 原精度。既有 viewport 按鈕明示 StrongFocus，可用空白鍵，縮放不截精確全表。
- 外部入口只沿既有 UX07 官方主站核實清冊：TWSE:2382、TWSE:1477、TPEX:6488、TWSE:00878、TWSE:IX0001。其他代碼（包括未核的2330）停用；不按股碼形狀猜交易所、不拼接任意 caller URL。只有明確按鈕動作才開外部瀏覽器，送出的 URL 只含公開 exchange/symbol，不含帳本、hash、context 或私人資料。外部最新價格與本機保存來源獨立，不承諾鎖住原 cutoff，切換後舊按鈕回呼拒收。

## UX07 有限選型決議

本輪沿已授權決議採**原生圖 default＋精確全表＋optional 已核外連**。不新增 WebEngine、LWC bundle、網路讀價或依賴下載。既有五個主站身份收據只授外部查圖入口；126格 Widget coverage 全 unknown 不改成支援。沒有 LWC／Hosted Widget 原型、封裝／授權驗收或效能比較，不將本有限選型稱為 UX07 原全部 prototype 完成。

## Focused 驗證

Interpreter：`C:/Projects/PythonProjects/technical_analysis/.venv/Scripts/python.exe`；工作目錄為上述 B05 worktree；`QT_QPA_PLATFORM=offscreen`。

```powershell
python -m pytest tests/test_baldr_b05_chart_markers.py tests/test_stock_research_chart_payload.py tests/test_ui_qt_chart_viewport.py -k 'b05 or marker or external or projector_uses_same_exact or saved_controls_full_table or interaction_renderer_failure' -q -o addopts=
```

最終 **51 passed／22 deselected**。新增正向研究確認／actual buy／actual sell、各身份 pin 失配／缺件、hash修訂、UTC跨臺北日界、matching pins＋重算 content hash 仍拒晚到／無時區／Paper、重複／超界、外部五商品與 injection/unknown；新增 offscreen 鍵盤同日表、marker stale scope、external stale callback及同日研究／actual買／actual賣不混同。沿用兩個既有保存圖／viewport相容案例，保留全表、MA、精確 tooltip、reset 與 renderer failure assert；未跑 viewport 全集或 producer 留存全集。

第一輪 7 failed／35 passed：typed 候選參數被舊事件局部變數覆蓋、synthetic 缺值 fixture 誤請求完整 OHLC hash、兩保存案例的 sandbox handle 拒絕。前兩者已修；第二輪 sandbox 40pass／2fail定位保存 reader 的 Windows no-follow ancestor handles。相同 synthetic tmp_path 範圍經自動審核 escalation 後2pass；最終 focused亦在同界線 escalation 通過，沒有弱化 reader／ACL／path guards 或把失敗略過。

- targeted mypy 四個 production 檔：`Success: no issues found in 4 source files`。
- py_compile：上述四個 production 檔＋新 marker tests／owned viewport tests 六檔，exit0。
- `scripts/quant_guard_linter.py`：精度及 look-ahead whitelist 靜態 gate exit0；新增程式人工 review 沒有 float、指標重算、策略／成交／績效計算。
- `git diff --check`：exit0。
- synthetic chart grab 位於 ignored `output/qa/b05_chart_increment/synthetic_chart.png`；採既有 `register_qt_chinese_fonts`／Microsoft JhengHei，已核對原生K／量、研究文字與十字線。首份未載 app 字型的隔離 grab 有方框，沿既有字型初始化重新核對；未改字型或啟 main／Native。PNG 留本機，不 stage。

mandatory Workbench／update validator／全 roots mypy **由中央穩定 union 跑一次**，本 lane 未重跑。這些 focused 不替代 Native／真人、正式來源或自然效果。

## 中央接線與文檔精確交接

`ui_qt/main.py` base 約982–1004建立 `stock_research_workspace`；owned view 新 API：

```python
def set_chart_marker_evidence(
    self, candidates: Sequence[StockChartMarkerDTO],
    identities: Sequence[StockChartMarkerIdentityDTO],
) -> None: ...
```

此方法只設定 immutable tuple、每次 report scope 重核；有已載 report 時只重新 render 價格頁，不開新查詢。中央已核 reader 若提供同 report 的兩組 tuple，可在原背景讀回完成／request＋stock＋context stale 核驗後，對 `self.stock_research_workspace.report_view` 呼叫此方法。清除來源時呼叫 `set_chart_marker_evidence((), ())`。**base 沒有能完整提供 account/source-row-hash 的 chart record reader**；因此沒有捏造 reader 名稱或把 `report.events` 轉成交，沒有可直接啟用的正式 producer patch。此來源 adapter／caller 是中央待接 I，本 lane consumer 已交付；unknown 時維持不畫。

Manual patch 建議（由唯一 owner 套用，lane 不直接改）：在 `APPLICATION_MANUAL.md`「個股研究→價格／技術」原生圖章之後追加下列操作段，並去除同章仍描述「尚無產品縮放／平移」的現行矛盾，保留歷史 QA：

> 在價格／技術頁按 Tab 到圖表，左右鍵逐日選取，Home／End 到首末資料日，Esc 清除十字線；滑鼠也可選日期。日期與精確原值同步下方完整價格／MA表，Tab 到縮放／平移／重設按鈕後用空白鍵操作，操作不查新行情或截斷表格。研表示已核帳本身份的推薦確認研究記錄，買／賣表示已核實際帳本的記錄；缺股號、日期、來源、原記錄hash、帳本、可得時鐘或 exact scope 時不畫，沒有標記不能推定沒有交易。尚未接入完整身份來源時保留缺件，不能手填 pin 冒稱合格。TradingView 外部參考只在已核交易所／代碼時啟用，需連線且另開瀏覽器；外部最新價格與原保存圖獨立，不能當成原 cutoff／歷史 PIT 證據。未知商品入口停用；本機 renderer 故障仍看同源精確表，缺保存圖不借今天補圖。

Coverage：Manual／Snapshot／現行 Architecture／Index／QA routing 為中央 Must，Index 新增本收據；Snapshot 保留原9stage／24UX與partial界線，Architecture 追加 typed marker 純投影與 trusted-pin 邊界。產品／6M／maturity／target方向與原plan不因本lane改變，無需新增道路或資格。中央 source adapter 接通後再更新 Manual 的實際來源範圍。

## 回滾清單

| 檔案 | 類型 | 內容 | 回滾 | 風險 |
|---|---|---|---|---|
| app_module/stock_research_chart_payload.py | 修改 | optional typed marker 投影 | restore指定base該檔 | 移除標記，原圖／表仍在 |
| ui_qt/views/stock_research_report_view.py | 修改 | marker／鍵盤／十字線／外連 | restore指定base該檔 | 移除本輪操作，保留base摘要修復 |
| tests/test_ui_qt_chart_viewport.py | 修改 | 三個B05 focus | restore指定base該檔 | 移除新增覆蓋 |
| app_module/stock_research_chart_markers.py | 新增 | 型別／hash／pin核驗 | 先移除owned引用，再僅刪該新檔 | 有引用時不可單刪 |
| app_module/stock_research_external_chart.py | 新增 | 有限主站清冊 | 先移除owned引用，再僅刪該新檔 | 有引用時不可單刪 |
| tests/test_baldr_b05_chart_markers.py | 新增 | synthetic正負例 | 僅刪該新檔 | 移除覆蓋，無資料風險 |
| docs/06_qa/BALDR_B05_CHART_INCREMENT_20261006.md | 新增 | 本收據／中央patch | 保留交接備份後僅刪該檔 | 移除交接資訊 |

回滾順序：先檢查該lane `git status --short`及整合owner變更；對三個既有檔執行 `git restore --source=ba4e9e59da7946aa66fd5eac3729e091dfe5cced -- <指定檔>`，再用 PowerShell `Remove-Item -LiteralPath <本lane精確新增檔>`逐檔處理；重新跑相同focus。整合後應由owner revert整個lanecommit，不覆寫別人變更。沒有正式資料遺失風險。

本lane只有localcommit交付，不dev cherry-pick、不push／main merge、不清理worktree、不真migration／Task／ACL／資料清理／Native／訓練／交易。待中央整合，完整commit與blob由交接訊息列出。
## B05 第二次交付：原始保存紀錄唯讀閉環（2026-10-06）

此節取代下方首次交付的「尚無 chart record reader」限制；首次提交 `62b205672b4982a38c0591a9abf9fe770f0d18f1` 不重寫。新增 ownership 僅為 `app_module/stock_research_chart_marker_reader.py`、`tests/test_baldr_b05_chart_marker_reader.py`，並修改既有 owned view 與本 QA。

### API 與身份契約

`StockResearchChartMarkerReader(trade_records=..., confirmation_records=...)` 注入既存唯讀 callback；`read(StockChartMarkerReadRequest, price_points=..., cancelled=...)` 回傳 immutable candidates、independent identities、diagnostics，`historical_pit_eligible=False`。不建立 store，不呼叫會寫 lock 的 `PortfolioJsonlStore.load_*`。可使用現有 `JsonlPortfolioTradeReadAdapter.list_trades` 或由既存 journal read service 封裝 `JsonlJournalReadAdapter._records`；原 service、store、adapter 與 shared DTO 均未修改。

Request 必須由已選取的來源／帳戶帶入 stock、cutoff、account、source ID、result ID、decision date、snapshot ID/hash、完整 chart context，以及獨立 `expected_record_hashes=((trade_id/revision_id, raw_row_sha256), ...)`。Custody pin 取自原保存列 canonical JSON；測試另核對其 SHA 與原 JSONL 每列 bytes SHA 相同。它不是 display candidate 的 content hash，也不得由 candidate 自簽取得。未知或缺少 pin 不画 marker；不新增 custody store。

實際交易只讀原 Trade `4.1` 的 `trade_id/portfolio_id/stock_code/side/trade_date/source_id/source_snapshot_hash/source_summary/created_at`，以原 `source_summary` 核對研究 lineage。來源為實際 trades callback；Paper 來源或顯式非 actual account_kind 拒絕。確認只讀原 accepted decision revision：原 JournalService envelope 實際為 `4.1`，另支援原 continuity DTO 的 `decision-continuity.v1`；原 `decision_identity`、outer envelope、payload 的 identity/來源/帳戶/時鐘必須一致。確認 marker 日期為原 aware `created_at` 的臺北當日，不倒填到 decision_date。

`view.set_chart_marker_reader(reader, request)` 可直接注入單一既存唯讀來源；每次 `_render_price` 核對 active stock、cutoff、完整 report context，再讀原 rows、驗 custody hash、投影原 typed marker。stale scope 清空舊 marker 並留下 `marker_request_scope_stale`。也可在中央既有 worker 中呼叫各來源 `read`，合併成功的 candidates/identities，再沿原 `set_chart_marker_evidence` 接入同一 projector；中央須保留既有 request serial／stock／context stale guard。callback 應為本機已選取、有限的唯讀來源；reader 至多接受 5000 rows、128 pins，支援取消。

### 原 producer metadata 缺口與中央鎖定

`app_module/portfolio_service.py::record_trade`（固定 base 約第 105 行）原本產生 naive `datetime.now().isoformat()`；這些舊紀錄 reader 回傳 `saved_record_clock_unknown`，不補現在、不宣稱 PIT。若中央要求該入口新交易可畫圖，最小 producer patch 是只將新保存 `created_at` 改為明確 aware UTC，保留既有紀錄原樣；writer 歸中央／Portfolio owner，本 lane 未改。`record_trades` 已可保存呼叫端原有 aware clock，原 TradeDTO/store 可用；JournalService.accept_decision 原本保存 aware canonical clock，已完成合成閉環。

中央 main 最後接線：在已核 source selection/account/chart request 的位置建立上述 read request，從原始唯讀保存來源取得獨立 custody pins，向 `stock_research_workspace.report_view.set_chart_marker_reader` 注入；未取得原始 source metadata／aware clock／帳戶時停用並顯示診斷。不能從 report.events 造原交易、不能從 marker candidate 推 pins。切换来源须清空/更新 request；本 lane 沒改 main、Portfolio producer、Personalization、B09/B10、Manual、共享 DTO 或主 plan。

Manual 精確待中央同步文字：原生圖表只顯示來源、帳戶、股票、日期、原始保存列雜湊與 aware 保存時間皆通過驗證的推薦確認／已記錄買賣。推薦確認是研究紀錄；實際交易紀錄由原 trades 保存來源讀取。未知身份、時鐘或保存列變動時不顯示 marker，診斷可供排錯；不是成交同步服務，不取得外部價格，不增加歷史 PIT 資格。舊 naive-clock 紀錄需保留原樣。

### 聚焦驗證與回滾

`QT_QPA_PLATFORM=offscreen`，根 repo `.venv` 執行：

```text
python -m pytest tests/test_baldr_b05_chart_marker_reader.py tests/test_baldr_b05_chart_markers.py tests/test_ui_qt_chart_viewport.py -k "reader or b05 or marker" -q -o addopts=
74 passed, 11 deselected
python -m mypy app_module/stock_research_chart_marker_reader.py ui_qt/views/stock_research_report_view.py
Success: no issues found in 2 source files
python -m py_compile app_module/stock_research_chart_marker_reader.py ui_qt/views/stock_research_report_view.py tests/test_baldr_b05_chart_marker_reader.py
exit 0
python scripts/quant_guard_linter.py
exit 0：精度與未來函數檢查通過
git diff --check
exit 0
```

兩個正例均由原 store/JournalService 合成保存 → 現有唯讀 adapter → 獨立原列 custody pin → 同源 payload → offscreen 可見 marker/table/tooltip → 全新 Python/Qt process 再讀原檔及畫圖；跨程序 content hash 相同，read 前後原檔 bytes、mtime 與檔案集合不變。負例覆蓋錯 source/hash/account/stock/lineage、缺 pin、naive/缺時鐘、after cutoff、早於事件、Paper、非 accepted、envelope/payload 衝突、重複 record、取消、來源錯誤、row 上限及 stale context。不重跑 viewport 全集或中央重型 gate。

回滾只 revert 本次後續 commit 的 reader、新 test、view 注入 API 與此節；保留首次 B05 commit（中央 `491fb26b`）與 base change/sufficiency 修正。全部 save 與子程序均為 OS temp 合成資料，沒有正式 Task、真資料 migration、清理、交易或網路取價。
