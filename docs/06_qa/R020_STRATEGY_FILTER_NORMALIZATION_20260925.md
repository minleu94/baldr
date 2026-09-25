# R020 scorer 後置篩選 alias normalization helper

## 範圍

本切片把 `StrategyConfigurator.generate_recommendations` 原有的篩選 alias／量能門檻
映射抽成 `normalize_recommendation_filter_aliases()`，原方法仍在 scorer 完成、取出最新列
之後呼叫同一 helper。此變更只搬移設定映射；不接 replay provider/evaluator、不剝除 scorer
filters、不改預設輸出，也不改篩選、警告或例外的執行時點。

`min_return_pct` 先提供 `price_change_min`，之後明確的 `price_change_min` 仍覆寫它；
`min_volume_ratio` 仍優先於直接 `volume_ratio_min`。直接 volume alias 仍以原始
`-50 <= value <= 10` 邊界決定是否換算；原有算式與輸入數值型別均保留。其他 price、RSI
與 market-cap 篩選鍵仍直接傳遞。

## 未來函數與數值自查

helper 只讀當次設定 mapping，不讀 DataFrame、日期、外部資料或跨候選狀態；呼叫位置仍在
當次 scorer 返回後的原本位置。沒有新增 feature、視窗、標準化、排序或 eligibility 規則，
因此本切片沒有新增 look-ahead 資料路徑。

量能轉換的算式是從原本方法原樣搬移，沒有新增裸 `float` 或額外數值運算。測試驗證
NumPy float16/float32/float64 與 int64 scalar 的結果維持原生運算型別；較廣 numeric-domain
一致性仍屬 TMP-NUM-01，不能由此切片推論。

## 測試與靜態檢查

- 新測試：`tests/test_r020_strategy_filter_normalization.py`，登錄為
  `service-oracle-recommendation`。
- 測試固定空／缺少 alias、price alias 覆寫、min-volume 優先、直接 volume alias 兩個
  inclusive 邊界及邊界外直通、NumPy scalar 型別、`None`／`pd.NA` 行為。
- 整合測試確認 `generate_recommendations` 先完成 scorer，再呼叫 helper，並把相同映射結果
  傳給後置篩選；壞 volume alias 仍在 scorer 後、篩選器前拋出 `TypeError`。
- Fresh TEMP `PROFILE=test` 九檔路由：新測試、R020 legacy policy、diagnostics characterization
  與 observer、unsupported metric characterization、真實 scorer filter stage、strategy screening
  support、R005 volume boundary，以及 inventory collection-status，結果 **59 passed**。
- 路由 log：
  `C:\Users\archi\AppData\Local\Temp\r020_filter_alias_final_3465704fc0954c92aeb203878744002c\pytest.log`；
  SHA256 `6CCB8C19E9527E83E20A06996C837C7BE59673887677DB87B82F0A14CBF838F2`。
- scoped mypy：`python -B -m mypy decision_module/strategy_configurator.py`，1 source file、0 issues。
- py_compile：`decision_module/strategy_configurator.py` 與新測試通過。
- `scripts/quant_guard_linter.py` 通過精度與 look-ahead 靜態檢查。
- 執行環境：Windows、Python 3.11、pandas 2.3.3、NumPy 2.3.5；資料／輸出根目錄均設於上述
  fresh TEMP 測試環境，未使用正式資料。

測試先行時，新測試因 helper 尚未存在而在 collection 失敗；抽取後上述路由全綠。此切片
只驗證 normalization 責任可共用，**不代表** R020、TMP-REC-04 或 TMP-NUM-01 已完成，也不
代表 provider/evaluator cutover 或 full V-REPLAY 已通過。

## 獨立複審與限定接受

R027 獨立複審未發現 P1/P2，對此 alias normalization 切片給予 bounded `ACCEPTED_SCOPE`。
複審 fresh TEMP 相鄰路由為 **84 passed**，scoped mypy 與 py_compile 通過。正確路由只呼叫
inventory 中單一 collection-status 測試並搭配相鄰 scorer/filter tests；沒有把整個
inventory 模組的全域 audit 當作此功能 gate。

複審前一次 QA 嘗試誤納入整個 inventory 模組，結果 **89 passed／1 failed**。該次 failure
屬全域 inventory guard，故該結果不作為 alias helper 功能失敗或接受的證據；後續改用單一
collection-status 測試後的 84 passed 路由才是獨立複審收據。此限定接受仍不涵蓋 provider／
evaluator cutover、legacy diagnostics／threshold parity 或 R020 全體 gate。

複審時核對的 source SHA-256：`decision_module/strategy_configurator.py`
`3C11ED4402C4A39C65AD93FB8EE958658D0C82CE63B3B17B26BA1515E14F9F8B`；測試 SHA-256：
`tests/test_r020_strategy_filter_normalization.py`
`FF71B2D0C1B267728860B0EE6D787706C9FF3C04385D85BECF64323F29540E8F`。R020 保持
`IN_PROGRESS`；`TMP-REC-04` 與 `TMP-NUM-01` 保持 `ACTIVE`。
