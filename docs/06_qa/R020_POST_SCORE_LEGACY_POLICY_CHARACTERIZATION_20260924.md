# R020 後置 scorer 篩選政策特性化

## 範圍與目的

本切片只固定目前 `RecommendationDataFrameProvider` 與真實
`StrategyConfigurator` 的同模式可觀測行為，供後續 post-score policy 遷移前對照。
沒有修改 production、既有 R005 oracle、R020 主報告或交易計算，也不代表 R020、
TMP-REC-04、TMP-NUM-01 或完整 V-REPLAY 已驗收。

測試直接呼叫 `StrategyConfigurator.generate_recommendations` 建立 legacy scorer
基準，再以具體 `RecommendationDataFrameProvider.run_with_as_of_handoff` 驗證 v1
rows、typed outcomes、scorer 呼叫與 terminal。Expected score、量變化率、列數、
例外類型與狀態均是固定 literal；測試沒有用 provider 結果自行產生期望值。

## 凍結的舊行為

- **19／20／21 列量能窗口：**合成歷史每列量 1,000，末列量 1,500，門檻
  `volume_ratio_min=1.5`。直接 scorer 在三種列數都產生一列，`TotalScore` 為
  `50.00`、`成交量變化率%` 為 `50.0`。Provider 在 19 列由 history preflight
  先行略過，沒有 scorer call 或 terminal；20 列的 fast volume window 尚不足，
  scorer 以舊 19 列 fallback 接受，21 列 fast filter 與 scorer 均接受。20／21 列
  provider v1 row 固定為 total score `50.0`、technical/pattern/volume 分數
  `50.0`、broker-flow/revenue 分數 `0.0`，且各有同碼 `SCORED` outcome。
- **兩個 volume alias 同時出現：**末列量增為 40%。當
  `volume_ratio_min=1.3`、`min_volume_ratio=1.5`，fast stage 以直接 key 的 30%
  門檻放行，scorer 以 `min_volume_ratio` 優先的 50% 門檻拒絕，terminal 為
  `SKIPPED_EMPTY`。反向設定為 1.5／1.3 時，native scorer 依 alias 30% 門檻產生
  一列，但 provider fast stage 先用直接 key 50% 門檻拒絕，scorer 無呼叫、無
  terminal。兩階段在相同 config 下確實能作出不同決定。
- **RSI 後置篩選：**`rsi_min=51` 或 `rsi_max=49` 對 RSI=50 由 scorer 產生空列，
  terminal 為 `SKIPPED_EMPTY`；上下界均為 50 時接受。輸入缺 RSI 欄位時，
  `rsi_min=101` 仍接受，固定目前缺欄即跳過的行為。
- **價格 alias：**`min_return_pct=1` 對零漲幅候選不由 fast stage 篩掉；真實 scorer
  被呼叫後回空列，terminal 為 `SKIPPED_EMPTY`。
- **錯誤時點：**無效 `volume_ratio_min="bad"` 時，native scorer 會拋
  `TypeError`。Provider 19 列在 scorer 前略過且沒有 terminal；20 列呼叫 scorer，
  捕捉 `TypeError` 並留下 `SKIPPED_SCORER_EXCEPTION`；21 列 fast threshold 的
  `float()` 先拋 `ValueError`，沒有 scorer call 或 terminal。另以
  `price_change_min=100` 搭配無效 max/volume threshold 固定 min 先拒絕的 lazy
  順序：provider 空結果且不解析後續門檻；native scorer 路徑仍拋 `TypeError`。
- **cutoff 負例：**決策 cutoff 為 2026-09-21 時，最大 row date 為 2026-09-22，或
  row date 合規但最大 `available_date` 為 2026-09-22，都在 scorer 前以
  `ValueError` fail closed。這只是該 provider entry 的合成負例，不替代完整
  row-level PIT／portfolio V-REPLAY gate。

## QA 證據

- 新測試：`tests/test_r020_post_score_legacy_policy_characterization.py`，已登錄
  `service-oracle-recommendation`。
- 測試清冊（保留既有 R020 scorer entry 與 R027 的 R026 entry）SHA256
  `754EC0A17816B608BE51E3560A08775FC66D64742C259B9FB9B312BFE3A4638F`。
- 凍結識別：新測試 SHA256
  `3BC8A019D4C9AADEBB80108854B38DD27403BCF5DB95E94A23AD039322A312BC`；測試時
  `RecommendationDataFrameProvider` SHA256
  `F0B50C21D08D7867BE2B59D4F9B54D1A33C9E9CCD17A6788FAB2FDFBCDFC6630`、
  `StrategyConfigurator` SHA256
  `0793723E8CAA78184EB2C892C94B13DAABBE3147B3B8F0D387F3F0DC91CC2A70`、
  `strategy_screening_support.py` SHA256
  `A3FBDC613798F947F24733CD8FBD6B1406EF49FCFB75F0BC54E109071B085F9E`。
- 測試以 `PROFILE=test`、獨立短 TEMP `DATA_ROOT`／`OUTPUT_ROOT` 執行；不讀寫正式
  資料。執行環境為 Windows、Python 3.11、pandas 2.3.3、NumPy 2.3.5。
- 新檔獨立初跑 `14 passed`；含既有 scorer、R005 volume-boundary、strategy screening、
  joint replay 與 inventory collection-status 的最終六檔路由 `21 passed`。
  最終路由收據位於
  `C:\Users\archi\AppData\Local\Temp\r020_postscore_route_20260924_c\pytest.log`，
  SHA256 `2EC01EF99172A84F20F4CD1F2FA2E2AF3C8B9B56C95F96B141057C01658468E9`。
- Focused 命令：

  ```powershell
  $env:PROFILE='test'
  $env:DATA_ROOT='<fresh-temp>\data'
  $env:OUTPUT_ROOT='<fresh-temp>\output'
  .\.venv\Scripts\python.exe -B -m pytest `
    tests/test_r020_post_score_legacy_policy_characterization.py `
    tests/test_r020_real_scorer_filter_stage.py `
    tests/test_recommendation_replay_characterization.py::test_dataframe_provider_volume_fast_filter_has_a_fixed_boundary `
    tests/test_strategy_screening_support.py::test_filter_completed_frame_preserves_order_and_applies_price_volume_and_rsi `
    tests/test_r020_replay_pipeline_composition.py::test_joint_provider_and_snapshot_slice_case_matrix_preserves_r005_rows_and_child `
    tests/test_full_app_healthcheck_test_inventory.py::test_inventory_exposes_pytest_collection_statuses `
    -q -o addopts= -p no:cacheprovider --basetemp '<fresh-temp>\pytest'
  ```

  新測試檔獨立初跑：`14 passed`。上方六檔最終相鄰路由：`21 passed`。新測試檔
  mypy 無問題；py_compile、inventory membership 與 whitespace 檢查通過。SHA 以
  凍結後檔案為準。

### 2026-09-25 補充：`min_return_pct=pd.NA` scorer oracle

新增測試 `test_min_return_alias_pd_na_keeps_real_scorer_warning_and_empty_terminal`，只補
nullable 價格 alias 的 legacy observation。21 列合成歷史以 `min_return_pct=pd.NA` 同時呼叫
原生 `StrategyConfigurator.generate_recommendations` 與 concrete provider。literal oracle 為：
原生 scorer 回空 DataFrame；provider 對該 21 列呼叫 scorer 一次、v1 rows 與 typed outcomes
皆為空，並完成同碼 `SKIPPED_EMPTY / scorer_empty_result` terminal；兩次呼叫各記錄一次
`[漲幅篩選] 要求 >= <NA>%, 但樣本值=0.00%` warning，因此計數為 2。這證明 alias 和
nullable scalar 留在舊 scorer 的投影／診斷時序，並未被 provider fast prefilter 消耗。

Fresh TEMP、`PROFILE=test` 相鄰三檔路由：`tests/test_r020_post_score_diagnostics_characterization.py`、
`tests/test_r020_post_score_legacy_policy_characterization.py`、
`tests/test_r020_real_scorer_filter_stage.py`，結果 **32 passed**。命令使用 `-B`、停用
pytest cache，TEMP 為 `C:\t\r20postscore_final_20260925`；log SHA256 為
`687396FFF60A3BC02217D76D8656A4836911A740FECFF751B98F7E48E71BFBF4`。新增測試 SHA256
`6B27AB51C7BE478375DD9496B5DF8F04FEEE8AE26275559C15AFEEB0AD9186D6`；測試仍登錄於
`service-oracle-recommendation`。此補充不改 provider、Strategy、evaluator、codec 或 inventory，
也不改變 R020／TMP-REC-04／TMP-NUM-01 尚未完成的邊界。

## 未完成邊界

本證據揭露 fast prefilter、`StrategyConfigurator` 後置 filter 具有不同的門檻來源、
window 與錯誤時點。它沒有授權以文字描述把兩階視為同一 policy owner，也沒有
解決如何在 R020「single evaluator／同模式輸出相等」下讓 scorer 衍生事實、alias
與 20-row fallback 有明確 typed ownership，同時保留 interactive scorer ABI、
`SKIPPED_EMPTY`、terminal 與 v1 row order。該設計仍須由 R020 owner/root 明確裁決；
production evaluator cutover、full same-mode parity、跨 runtime numeric、完整
future/PIT 與 portfolio 證據仍未由此切片覆蓋。

## 2026-10-11 後續 R020 disposition（保留本收據範圍）

本文件的 2026-09-24／25 legacy-policy observation 仍是日期化行為 oracle。後續 [R020 implementation report](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R020_IMPLEMENTATION_REPORT.md) 記錄 post-score cutover 僅在已測 Win32／Python 3.11.9／Pandas 2.3.3／NumPy 1.26.4 與 2.3.5 profiles bounded accepted；[R029 ledger](../01_architecture/target_architecture_2026_09_22/REFACTOR_REPORTS/R029_IMPLEMENTATION_REPORT.md) 與 [R031 closeout](R031_FINAL_REFACTOR_CLOSEOUT_20260925.md) 將 R020 R005 replay/recovery bounded scope、`TMP-REC-04`、原範圍 `TMP-NUM-01` 列為已關閉，C2 為 `ACCEPTED_WITH_NAMED_QA_BASELINE`。

後續狀態不改寫本文件凍結的舊 scorer 結果，也不表示此 slice 單獨證明 full same-mode parity、所有 runtime/profile/caller、無界 V-REPLAY 或完整 future/PIT／portfolio evidence。
