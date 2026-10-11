# UX11 保存結果與規則來源核對限定收據（2026-10-06）

基線 be8aac332c3f856c58eda001e6e873ca2252c140。只新增 saved_strategy_rule_card adapter／兩個專用測試，修改既有 Registry widget及規則Dialog，不改producer、Registry writer／schema、策略公式、正式資料或UX20 lane。没有新增代理。原plan§8.3／UX11要求版本可追、缺值保留，本包完成單筆保存來源→規則卡readback限定子項，不新增性能或投資效果硬閘。

## 真實介面與來源邊界

BacktestRun舊schema沒有strategy_version；不能套目前1.0替它補來源。ResearchRunMetadataDTO已有id/version、normalized params、universe、期間/cutoff、data fingerprint、整數fee/slippage、execution contract、benchmark聲明及Parquet hashes。本adapter使用已傳入的ResearchRunService.load_run_data核對committed/valid、既有payload／sidecar／Parquet完整性，不初始化新service、不save／promotion／重算。

只從來源data_manifest取strategy_spec及rule_card_identity。若來源沒有捕獲的full Spec／rule pin，保持not_evaluable，不在consumer替舊run寫章或填defaults。完整Spec對id/version/params/data_version核對；保存pin對當前同版Registry內容hash及保存context核對，Registry同版內容修訂也拒絕連結。context包含result kind、母體／窗口／cutoff、params及parameter contract、資金／風控、成本、execution、data/payload hashes與benchmark聲明。資料來源SHA格式是聲明身份，不代表已驗原始行情custody。

選取metadata與worker讀回metadata完整canonical hash不符拒絕；來源只取已保存輸入。實際fee/slippage需原raw_params明示及記錄整數bp×100一致，未知／錯型別／精度不能確認不補預設。benchmark缺失保留None，存在時也只是保存聲明，尚未核對。source_ref_only只表示保存身份與說明pin吻合；rule_status/performance_status維持not_evaluable，不驗executor程式、完整稅費、OOS或投資效果。既有reader對legacy非marked payload的hash／讀取邊界不在本包提升或放寬。

single/batch/fixed-basket stock run分類歷史回測；明示research_forward分類研究追蹤，兩者pin不能混。其他kind維持unknown，不稱live。研究追蹤分支只驗合成Registry對等fixture；未接自然Evidence/Paper producer、成熟outcome或正式forward資格。

## 使用者呈現

研究實驗室→研究Registry選取單筆→「查看單筆結果與規則」。背景一次只讀一筆，顯示保存期間、cutoff、標的（主文前三筆及總數、完整清單在來源核對）、保存成交假設／費率、基準未知及資格。來源不能連結時明示下方只是Registry說明與保存參數、未核對保存時規則。字段plain text，工程reasons、version/hash與檔案ref預設收合；不新增勝率、曲線、排名或自動套用。

TaskWorker最多一個，選取／metadata更新時拒絕舊回呼；取消在既有reader前後協作，关闭後不套結果。reader底層IO不能强制中止，但不阻塞UI、未起無界queue／新process；native完成後清理wrapper。讀取失敗保留人類可讀status並可重試，不無限loading。沒有碰使用者正在用的程式。

## 隔離驗證

實際小型Temp ResearchRunService.save_run→committed Registry／Parquet→load_run_data→結果與規則Dialog，来源bytes/mtime不變。這是合成對等保存來源，不是真回測／自然producer。

- focused39 passed：adapter18（版本／日期／窗口／source／params／cost型別／universe／kind／選取修訂／Parquet tamper）、consumer5（actual worker、unknown成本、換選取、忙碌关闭、error恢復）、既有Dialog4及Registry12。
- 六個既有backtest shell幾何案例通過；共45項distinct，不把UI5重驗算新增案例。
- Workbench85、validator25／0fail／4skip、full roots mypy802、compile5、quant precision/look-ahead及diffcheck通過。唯一pytest warning是sandbox cache不可寫，不是功能skip。
- 合成offscreen截圖與readback JSON位於output/qa/ux11_saved_result_rule_card_20261006/；不是Native／Formal资格。首次指錯一個既有測試檔名，沒有執行測試，修正至test_ui_qt_run_registry_compare.py後全部通過。

## 結案及剩餘

按需設定卡及保存結果readback兩個有限工程子項已完成。UX11整項沿前plan保留partial：現有來源未有完整typed入場／出場／稅費及原始資料／executor資格證據時維持unknown，這是明示資料／執行來源限制，不新增人工blocking gate；不要求先有自然樣本才可使用介面。Stage6仍partial；Native／真人放在原整合驗收範圍，本包不冒稱已完成。

UX20 4bcc842獨立lane已交父層，本包不review/pick／擴16股條件或改其檔案。UTC 2026-10-06 07:00 暫停 review 是當日交接時點；本頁不確認該暫停於後續日期仍生效，也不設定新期限。真 migration／activation、push／清理未執行，所有 worktrees 保留。
