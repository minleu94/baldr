# R020 實際 scorer 後置篩選特性化

**日期：** 2026-09-24

**性質：** 合成資料 QA 證據；沒有修改產品程式，也不是 R020／V-REPLAY 驗收。

## 目的與範圍

本檢查把 `RecommendationDataFrameProvider` 的 fast prefilter 與實際 `StrategyConfigurator` scorer 串在一起，固定量比 20／21 列邊界、RSI-only 篩選、scorer 回空列時的 terminal，以及可見 v1 row。測試沒有替換 scorer：觀測 wrapper 只記錄呼叫與原方法的回傳值，隨即委派原實作。21 列的同模式 baseline 另直接呼叫一個新的 `StrategyConfigurator`，並以固定 v1 literal 核對 provider 輸出。

資料只在測試內合成：每日日期 2026-09-01 起算、收盤價固定 100、前列成交量固定 1000、RSI 固定 50。每次 provider cutoff 等於該案例最後一個資料日，沒有加入未來列或正式資料讀取。

## 觀測結果

| 案例 | 舊 scorer 直接呼叫 | Provider fast prefilter 與 scorer 的結果 | handoff 可見內容 |
|---|---|---|---|
| 20 列、`volume_ratio_min=1.5`、末日量 1000 | `StrategyConfigurator` 回空 DataFrame | fast prefilter 將量比標為不足窗口，交給 scorer；scorer 以可用的前 19 列算出 0% 變化，按 50% 門檻回空 | evaluator 內部 terminal 為 `SKIPPED_EMPTY`；v1 rows 與 scoring outcomes 都是空 tuple/list |
| 21 列、`volume_ratio_min=1.5`、末日量 1500 | scorer 保留末列，`TotalScore=50.00`、`IndicatorScore=50`、`PatternScore=50`、`VolumeScore=50`、量變 `50.0` | fast prefilter 的 20 列視窗計得 50%；real scorer 的 20 列衍生視窗亦為 50%，保留候選 | 一個 v1 row：`VOL21`、分數 50.0、factor scores `{technical: 50.0, pattern: 50.0, volume: 50.0, broker_flow: 0.0, revenue: 0.0}`、理由「符合策略條件」；一個同碼 `SCORED` outcome |
| 21 列、僅 `rsi_min=101`、RSI 50 | scorer 回空 DataFrame | RSI 未進 fast policy；candidate 到達 real scorer 後由 scorer 篩掉 | evaluator 內部 terminal 為 `SKIPPED_EMPTY`；handoff 沒有 v1 row 或 scoring outcome |

20 列案例的前置路徑在 `app_module/recommendation_dataframe_provider.py` 將 volume metric 標成 `INSUFFICIENT_WINDOW`；不足窗口不觸發 fast reject。後續仍將含完整 `filters` 的 config 傳入 `StrategyConfigurator.generate_recommendations`。該 scorer 將量比 `1.5` 換算成 50%，並在最新列執行 price、volume、RSI 門檻。`decision_module/derived_market_features.py` 對至少 21 列採前 20 列；少於 21 列則採全部前列，因此 20 列案例使用 19 列計算。

以上確認目前量比門檻在兩個階段都具有輸出影響：21 列時 fast prefilter 先比較，候選再進 scorer；20 列時 fast prefilter 延後比較，scorer 以 19 列 fallback 仍可拒絕。RSI 則只在 scorer 後置篩選。這是現況特性化，尚未裁決 R020 是否需把 scorer 後置門檻移入 evaluator，或如何保留與版本化其歷史語意。

`SKIPPED_EMPTY` 是呼叫 evaluator completion 時觀測到的內部 terminal；目前 `ReplayProviderCallResultV1.scoring_outcomes` 由最後輸出的 candidate rows 對齊建立，所以空結果不會回傳這個 skipped outcome。此測試只記錄此 handoff 邊界，不把空 outcomes 說成 terminal evidence 已持久化或完整可重建。

## 重現與驗證

新測試：`tests/test_r020_real_scorer_filter_stage.py`，已登錄 `service-oracle-recommendation`。inventory 同時保留 R027 新增的 `tests/test_r026_calibration_legacy_preparation_baseline.py` entry。

Fresh TEMP 使用 `PROFILE=test`、`DATA_ROOT`／`OUTPUT_ROOT`／`TEMP`／`TMP` 均指向 `C:\Users\archi\AppData\Local\Temp\r020_scorer_filter_0924d`。Python 3.11.9、pandas 2.3.3、NumPy 2.3.5。

執行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_r020_real_scorer_filter_stage.py tests/test_recommendation_replay_characterization.py::test_dataframe_provider_volume_fast_filter_has_a_fixed_boundary tests/test_strategy_screening_support.py::test_filter_completed_frame_preserves_order_and_applies_price_volume_and_rsi tests/test_r020_replay_pipeline_composition.py::test_joint_provider_and_snapshot_slice_case_matrix_preserves_r005_rows_and_child -q -o addopts=
```

結果：`6 passed in 1.01s`。QA log 位於 TEMP 的 `pytest.log`；新測試 `py_compile` 通過，單檔 mypy 為 `Success: no issues found in 1 source file`。inventory membership 檢查確認新路徑恰一筆且分類正確，R026 entry 仍存在。`git diff --check` 對 inventory 通過；Git 僅提示該既有檔案會由 LF 轉 CRLF。

## 證據識別與限制

本證據凍結的是 Windows Python 3.11.9／pandas 2.3.3／NumPy 2.3.5 下的合成 scorer 行為。它不涵蓋其他 runtime、price max/min 門檻、全部 R005 vectors、portfolio 結果、保存／讀回或 full V-REPLAY，也沒有把 downstream scorer filter 移除或改寫。

| 檔案 | SHA-256 |
|---|---|
| `tests/test_r020_real_scorer_filter_stage.py` | `FC7C689F9B1ABF7D801705DFA4198CC85131AF33D5E0EE13CDC6B522941904A2` |
| `qa/full_app_healthcheck/test_inventory.py` | `88DC175E413606DB516B4D860B0C11FC527946E4FADD8C3ABBC316CF6156584D` |
| `app_module/recommendation_dataframe_provider.py` | `F0B50C21D08D7867BE2B59D4F9B54D1A33C9E9CCD17A6788FAB2FDFBCDFC6630` |
| `decision_module/strategy_configurator.py` | `0793723E8CAA78184EB2C892C94B13DAABBE3147B3B8F0D387F3F0DC91CC2A70` |
| `decision_module/strategy_screening_support.py` | `A3FBDC613798F947F24733CD8FBD6B1406EF49FCFB75F0BC54E109071B085F9E` |
| `decision_module/derived_market_features.py` | `FA60BADCA63AAE754344BAAA58CF2D0886677CA582457F5466EDD09E6257869E` |
| `decision_module/recommendation/evaluate.py` | `88B55FC4F450230ADFB92E46C7BC30ABD67A28AF4FC83C31138D8A96EC73F6CC` |
| TEMP `pytest.log` | `E8BA77F470FFE3AB7AFB49A222B14F5C5182AE1D44816CB8069FAA383FD92725` |

## 2026-10-11 後續 R020 disposition（保留本收據範圍）

本文件的 2026-09-24 real-scorer observation 仍是固定 legacy behavior evidence。後續 [R020 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R020_IMPLEMENTATION_REPORT.md) 記錄 post-score cutover 僅在已測 Win32／Python 3.11.9／Pandas 2.3.3／NumPy 1.26.4 與 2.3.5 profiles bounded accepted；[R029 ledger](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R029_IMPLEMENTATION_REPORT.md) 與 [R031 closeout](R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) 將 R020 R005 replay/recovery bounded scope、`TMP-REC-04`、原範圍 `TMP-NUM-01` 列為已關閉，C2 為 `ACCEPTED_WITH_NAMED_QA_BASELINE`。

此裁定不把本文件單獨提升為 full same-mode parity、完整 V-REPLAY、跨 runtime／caller 或 official PIT 證據；原測試只描述記錄時點的 synthetic Windows profile。
