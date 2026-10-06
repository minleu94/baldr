# UX08 純圖表範圍 controller 交接

基準：`1454a125db0e61dbecc7522c48b236997ff7b242`（已核對 dev）。分支：`lane/ux08-chart-viewport-20261006`。worktree：`C:/Projects/PythonProjects/technical_analysis/output/worktrees/ux08-chart-viewport`。本 lane 只新增 controller、專屬 tests、本文件，不改共享 renderer、主視窗、Manual、config 或原計畫。唯一整合 owner：`01a10f1e-1fa7-7660-b46e-4e2107d52078`；尚未接入產品按鈕，UX08 整項仍 partial。

## 既有契約核對

graphify query 查 `StockPriceChartWidget set_points viewport stock_research_chart_payload`；索引位置已落後，以下結論再核對基準的實際 source。沒有 `chart_viewport_state.py` 或相同純 controller。`ui_qt/views/stock_research_report_view.py:153` 原生 `StockPriceChartWidget` 使用全量 `set_points`，提供 hover、paint、OHLC／收盤模式與 `set_technical_lines`；沒有 zoom／pan 狀態。`_render_price` 在同檔約 2038 行核驗 `project_stock_chart_payload` 後建立 widget。

既有 `StockChartPayloadDTO.price_points` 同時供精確表；`source_context`、cutoff 及價格逐列指紋語義不得混用。controller 不重造投影，不讀 DB、不查行情、不授 PIT；只接投影已接受的資料。技術線仍用既有 `_technical_segments`，None／缺列斷線。renderer 本來會過濾沒有 close 的槽，這一展示限制仍存在；controller 保留原槽並提供 `nearest_index`，owner 若採日期槽座標，paint 與 hover 必須同時使用相同索引映射，不能單改 hover。

## 可執行 API

- `ChartViewportIdentity(stock_code, source_id, version, cutoff_date, source_context=())`：不可變身份；上下文配對排序，重複 key 拒絕。版本必須由 caller 的原核驗 artifact／rowset 身份明示，不拿 MA 值、股票碼或資料筆數冒充版本。空白、unknown／未知等身份不可 reload 保留。
- `ChartViewportState.load(dates, identity, preserve=True)`：日期必須為嚴格遞增、不重複的 ISO 日期，且不晚於 cutoff；無效載入不改原狀態。完整同身份保留原可見日期交集，沒有交集重設全量。原本全量保持全量；空資料清除範圍；身份任何欄位改變或 `preserve=False` 都重設。
- `set_range(start, stop)`：半開索引範圍，越界平移回合法邊界；非空至少一槽。
- `zoom(numerator, denominator=1, anchor=None)`：可見槽數乘正整數比例；`zoom(1, 2)` 放大，`zoom(2)` 縮小。anchor 是全資料索引且須可見；保留相對位置並 clamp，最少一槽。浮點或 bool 輸入拒絕。
- `pan(slots)`：正數往較新槽；保留槽數且不超界。`reset()`：全量。
- `.range`：frozen `ChartViewportRange(start, stop, total, first_date, last_date)`，含 `.count`／`.is_full`；`.visible_dates`：原日期 tuple。
- `slice_points(points)`：驗日期和槽數後回傳原 DTO 切片，不複製或補造價格、不改 None。caller 必須傳同份核驗 payload；此方法不驗證來源指紋或值內容。
- `nearest_index(x, left, right)`：整數 pixel 對可見原資料索引，圖外／空資料回 None；缺價槽仍是原槽。

## 整合 owner 接線位置與最小範例

在 `StockResearchReportView._render_price` 的 projection 接受後，使用 view 所持有的 controller（不要每次 render 重建）載入同份 payload 日期。股票、來源、version 或 cutoff 改變會由 controller 重設。若 page 每次 `_reset_page` 重建 widget，controller 留在 view；回報拒絕／缺件時清空 renderer，不保留上一來源圖。owner 自行補 Manual 與共享 UI 驗證。

```python
from app_module.chart_viewport_state import ChartViewportIdentity, ChartViewportState

# view 初始化一次；version/source_id 來自既有核驗來源 envelope。
viewport = ChartViewportState()
viewport.load(
    tuple(point.data_date for point in payload.price_points),
    ChartViewportIdentity(
        payload.stock_code, verified_source_id, verified_version,
        payload.cutoff_date, payload.source_context,
    ),
)

def redraw():
    # 價格表仍用全量 payload.table_rows，不因 zoom 改寫來源證據。
    chart.set_points(viewport.slice_points(payload.price_points))
    # set_points 會清技術線，所以每次重畫後恢復同源全線供日期對齊。
    chart.set_technical_lines(payload.technical_lines)

def zoom_in():
    viewport.zoom(1, 2)
    redraw()

def pan_newer():
    viewport.pan(max(1, viewport.range.count // 4))
    redraw()

def reset():
    viewport.reset()
    redraw()
```

期間按鈕可呼叫 `set_range`，日期槽僅含已有資料，不能補休市 calendar 或把缺口補價。按鈕／鍵盤／wheel callback 綁上面 API；viewport 身份不足時每次 reload 合理重設，但同次載入內仍能操作。此範例利用既有 renderer 可直接運作，tests 已用實際 widget 驗放大範圍→平移→重設與 MA 缺值分段；不只是介面設計文件。

## 驗證與限制

使用主 repo `.venv/Scripts/python.exe`，workdir 是本 lane，Qt 設 `QT_QPA_PLATFORM=offscreen`。專屬測試 **34 passed**，涵蓋空資料、單槽、邊界、縮放 anchor、連續縮放、缺口原槽、身份／版本／cutoff 改變、日期交集、錯誤 load atomic、非整數拒絕與真實 native widget 接合。既有三檔圖表回歸 **61 passed**；單模組 mypy **1 source file 成功**，兩檔 py_compile 與 diff check 成功。commit hash 由本次交付 final 提供。

命令：`python -m pytest tests/test_chart_viewport_state.py -q -o addopts=`；既有回歸 `tests/test_stock_research_chart_payload.py tests/test_ui_qt_stock_research_report.py tests/test_ui_qt_saved_stock_chart.py`；`python -m mypy app_module/chart_viewport_state.py`；`python -m py_compile app_module/chart_viewport_state.py tests/test_chart_viewport_state.py`；`git diff --check`。

本包無 foreground／真人／Native 互動驗收，offscreen 不代表真人接受；沒有 DB／migration／Task／安全設定、推薦 writer、交易 markers 或金融計算變更。所有範圍／pixel 計算採整數；日期不晚於 cutoff，既有 projection 的 availability 與 PIT 限制保留。共享 UI 尚未修改，所以更新頁強制作業與全域 mypy 留 owner 接線後執行。

## 回滾與安全接手

三檔均為新增。整合前先檢查工作樹，再 `git revert <本 lane commit>`；不覆寫其他工作。整合後需同時檢查 owner 接線依賴。shared state 依使用者三檔範圍不寫，本文件／final 作限定 handoff。只做 local commit；不 cherry-pick 到 dev，不 push，不清理工作樹。交付後停等唯一 owner 整合。


## 2026-10-06 dev owner後續整合

純controller以cd33ddd6採納，產品按鈕與來源identity接入；原「renderer過濾缺收盤槽」限制已由整合端改為保留原槽、paint/hover一致與斷線。詳見[整合QA](UX08_VIEWPORT_INTEGRATION_20261006.md)。Native／真人仍未完成。
