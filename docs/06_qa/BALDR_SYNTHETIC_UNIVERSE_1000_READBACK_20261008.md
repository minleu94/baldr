# 1,000 檔合成保存研究產製與獨立讀回

依使用者明確授權，在全新隔離目錄建立合成股票資料、執行產製器並保存測試封套。正式資料與正式排程不在此測試範圍。

## 有限接受結果

固定來源為 Git archive `2897f269d6b5ee6618698f191ad117adb73c0672`，不是目前候選執行檔。隔離 case `C:/t/p01_b3mrz9_8` 的產製器收據為 complete：四個分段完成、納入1,000檔全部處理、待處理0。原始代碼1,002筆，去重後1,001檔；其中1檔明示排除。納入列另有1檔缺資料，保持缺件，不改為成功資料或待處理。

中央獨立 public `StoreReader.read_exact` 核驗同一 generation／plan／receipt 與各 bytes SHA，session82282 terminal0，收據 status verified。來源 archive／tree、合成 SQLite 及 sidecars、整份保存來源、原失敗封套／phase／manifest 前後身分一致。補驗未載入 producer 或 ML，SQLite、網路、子程序、被拒寫入計數均0。

新證據位於 `output/qa/p01_b3mrz9_8_readback_qualification_20261008_b/readback_qualification.json`，SHA256 `f1a69b9d2e2f729cf49cd5610e8ca4acd8c0f2298f99601853d254db1368b3bf`；helper SHA256 `82a26815d4e4b30cb1e1d9b2f595e7cabff3ab38d9141f3edd1efca31906d037`。helper只建立新的獨立證據，不覆寫原failed結果。

## 身分與完整性

| 項目 | 已核值 |
|---|---|
| Generation | `34066dc3d86cf4bc70bcac84b543290cb6b047bd0df295d13b8c2e4c6a2a0c02` |
| Plan identity | `08b757c0b9e86e82394d52dca8a0ebb6033665e282211ef56caed353e9224d17` |
| Receipt identity | `b278e93058fc537dc87af98117c17a8e5d8771653464aaed3e496401778f28ff` |
| Receipt bytes SHA | `1f357f468150e595c3af33797a0b5e94afb4adcf13a38cd8cf15f79ea25ce1f2` |
| Source clock identity | `9606c2267746cf621f314235c5e7464cad5ebaab7b89955268ab572242714286` |
| Method contracts SHA | `d3254c71badda536fa91856e5aef53b56d71f4138430a0386b55e60fb367c0da` |
| Calculation identity | `3ae700370a0043f9a85cc8f694575075d60b5985bcc927a16860fa6ff0f40f10` |
| 合成 SQLite bytes SHA | `e87a96c7cbabaac8f208b64bb8de57ef383f3d6100fccee3660862fd5ca4593d` |
| 封存來源 tree SHA | `a8d9946d94361733d8f268894e8452a73999c22ff47676528f8660f769e7f3b9` |

保存寫入事件1,070筆逐筆核對固定writer、精確暫存／目的路徑、原生descriptor身分與容量；拒絕0、未關閉追蹤descriptor0，事件計數對帳。原產製封套未保存逐筆SQL連線清單或精確總數；只能依固定控制器在失敗前已通過的檢查，確認至少一筆連線且限制為該合成source.sqlite的ro模式。獨立補驗沒有SQL連線。Store writer原事件的容量參數為null，另依固定來源的plan／receipt容量常數核對，不捏造原記錄內容。

## 原失敗與尚未授予資格

原產製控制器C63在產製完成後誤用不存在的receipt.counts，原結果仍為failed／checks空。第一補驗最後輸出因Windows audit預設O_NOINHERIT旗標被誤拒；窄修後第二補驗保存failed，錯誤為報告使用不存在的Plan日期／方法屬性。新helper改由已驗證的Plan.to_dict取值，先通過純型別／API自檢，再完成本次完整讀回。所有舊失敗保留，沒有重跑producer或改判舊結果。

本結果只接受固定來源的合成產物與獨立讀回，不授予原控制器整體成功、正式來源／歷史PIT、實際市場N、效能、MainWindow、Native／exe或真人資格。冷5／暖30效能與正常資料產製仍須分別完成，完整P00–P14／M1–M3目標不變。

## Source-only benchmark 守衛中央補驗（2026-10-08）

root 獨立執行 parent／worker 組合自測，exit 0；新 case `C:/t/p01_hgz9tl64`，log `output/qa/p01_b3mrz9_8_source_benchmark_20261008_a/root_guard_composition_20261008_a.log`。固定 controller SHA256 `79f402906920754e5a5f97c4691d34a20983f0b260a3639dd2d958929c9955dc`，selftest SHA256 `784cf2ffc51f7c4f05c94272e29b8c3c426c3dc605a581d9fb939c088ce6a510`；C63 helper 未變。

六個合成 worker 成功，六個錯誤啟動反例拒絕；network／SQLite 都為 0。實際 parent guard 的拒絕被 fake worker 吞下並回傳 passed 後，after-worker gate 仍拒絕；下一次 before-launch gate 不呼叫 launch，failure envelope 保留有界 denial snapshot。來源與 protected sentinel 前後 SHA 一致，沒有產品 API、模型、產製器或 benchmark 執行。

本項只接受 QA 守衛組合與立即停跑契約，不授予正式 worker 或冷暖效能接受。中央 F17 回歸仍執行中，完整冷 5／暖 30 矩陣須等其他重測停止後單獨執行；原失敗 attempts 不覆寫。
