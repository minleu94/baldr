# 歷史測試資料集中清冊與還原指南

## 狀態與範圍

2026-10-06 使用者在主要對話批准下列 10 個目錄完整集中，條件是文件記錄用途、保留必要性、原新位置與還原方式。本頁目前為**批准已轉送、執行仍被審核阻擋**；同命令重試一次後，自動審核仍不接受轉送內容作為可信授權，於 CreateProcess 前拒絕。10 個來源保留原處，集中目錄未建立，沒有改路線或再次重試。只有搬移完成並全量 metadata 複驗通過後，才更新為完成。

這批盤點共 5,633,484,456 logical bytes（約 5.247 GiB）、147,573 個檔案路徑。計畫採同 C 槽目錄 rename，不永久刪除內容，不釋放容量；空目錄只保存拓樸紀錄，不視為重要資料。**目前實際位置仍是下表「原位置」；「計畫目標位置」尚未建立或搬入。批准記錄不是搬移證據，這批實際搬移量為 0 bytes。**

## 原新位置、用途與保留必要性

| 原位置（目前實際位置） | 計畫目標位置（未執行） | Logical bytes／檔案數 | 用途及保留理由 |
|---|---|---:|---|
| `C:/t` | `C:/Projects/RepositoryBackups/historical_test_quarantine_20261006/C_root_t` | 786,467,101／39,441 | R020/R026/C2 等歷史 QA 短 TEMP 根；保留原 log、manifest、合成 fixture 與既有驗證證據，供歷史重播。文件有 73 處歷史絕對路徑引用。本輪先前隔離沒有將資料搬入 C:/t；未由時間猜測建立者。 |
| `C:/c3c2a` | `C:/Projects/RepositoryBackups/historical_test_quarantine_20261006/C_root_c3c2a` | 390,294／46 | generation CLI／legacy retry pytest fixture，對應 `tests/test_personalization_generation_cli.py`；保留原測試證據與合成資料 bytes，非正式私人資料。 |
| `C:/ta_iso_1005` | `C:/Projects/RepositoryBackups/historical_test_quarantine_20261006/previous_isolation_ta_iso_1005` | 4,845,871,595／108,054 | 10/05 原 879-root 可恢復隔離；可能是原 fixture/cache 的唯一現存副本，完整保留還原能力。只集中，不因有其他備份或可重建而刪除唯一 bytes。 |
| `C:/r26raw_h_6441fa` | `C:/Projects/RepositoryBackups/historical_test_quarantine_20261006/C_root_r26raw_h_6441fa` | 20,480／1 | `history.db` 與 41 個已確認 R026 合成 fixture SHA256 相同；保留原測試 DB 與 data/out 空目錄。僅以唯讀 immutable/query_only 查 schema，未查資料列。 |
| `C:/Projects/PythonProjects/technical_analysis/' + $pytestTmp + @'` | `C:/Projects/RepositoryBackups/historical_test_quarantine_20261006/repo_literal_pytestTmp` | 0／0 | 空的 `test_portfolio_drill_down_pass0` fixture；保留原拓樸以便還原。字面名称像拼接誤建只是推論，未證建立命令或 actor。所有處理採 literal Path，不執行名稱中的變數或字串。 |
| `C:/Projects/PythonProjects/technical_analysis/rtmp_rs_20261004` | `C:/Projects/RepositoryBackups/historical_test_quarantine_20261006/repo_rtmp_rs_20261004` | 734,986／31 | research screener 的 advice/data-date/receipt pytest fixture；保留歷史測試證據與合成輸出，不是正式模型或目前 UI 資料。 |
| `C:/Projects/PythonProjects/technical_analysis/qa_artifacts` | `C:/Projects/RepositoryBackups/historical_test_quarantine_20261006/repo_qa_artifacts` | 0／0 | 未追蹤空根；僅拓樸紀錄，無檔案內容。 |
| `C:/Projects/PythonProjects/technical_analysis/.ipynb_checkpoints` | `C:/Projects/RepositoryBackups/historical_test_quarantine_20261006/repo_.ipynb_checkpoints` | 0／0 | 未追蹤空根；僅拓樸紀錄，無 notebook 內容。 |
| `C:/Projects/PythonProjects/technical_analysis/root` | `C:/Projects/RepositoryBackups/historical_test_quarantine_20261006/repo_root` | 0／0 | 未追蹤空根；文字匹配為 JSON 欄位等，非此根依賴，僅拓樸紀錄。 |
| `C:/Projects/PythonProjects/technical_analysis/technical_analysis` | `C:/Projects/RepositoryBackups/historical_test_quarantine_20261006/repo_technical_analysis` | 0／0 | 未追蹤空根；程式同名引用為 package 或 DATA_ROOT 子目錄，不是這個 repo 空根，僅拓樸紀錄。 |

這些容量是分離來源根的 logical bytes；不是新增資料量，不把先前隔離再次計為新增釋放容量。未發現來源 reparse 或外部硬連結；目前 tracked code/script/config 無這些根的直接路徑依賴。Windows Task/CIM 查詢受權限限制，未繞過，也不能保證所有外部 caller；正式 Task wrapper/source、私人資料、模型、lineage、receipt 均保留。

## 執行與保護證據

未來若完成可信批准並執行，計畫在集中根內以 `manifest.json` 記錄精確 source/destination、用途、逐項 state、metadata 摘要、舊還原證據 copy SHA256；各 `<目標名稱>.entries.json` 保存全部相對路徑、dev/inode、size、mtime、link count、attributes。metadata 摘要不是檔案內容雜湊；同槽 rename 保留原檔案本體。計畫另保存凍結 CSV、plan、本頁與還原指南，方便脫離 repo 後辨識。**目前沒有建立這批集中根、durable manifest 或證據副本。**

目前盤點與阻擋證據在 repo ignored 路徑 `output/qa/baldr_storage_inventory_20261006/`，包括 `named_history_exact_reviewable_plan.csv`、`named_history_plan.json`、`named_history_not_executed_verification.json`、`named_history_second_review_rejection.json`。`named_history_receipt.json` 是計畫執行時才產生的收據，目前未產生；不得視為已有搬移證據。不得 force-add 原始資料、DB、ignored QA 或 backup 至 Git。

搬移前先全量核對 metadata 與正式来源／私人配置／H20 保護項目；有變動立即停止。搬移後再次核對 metadata 與原路徑不存在，保存逐項狀態；失敗不得覆蓋、合併或補刪來源。

`dist/baldr/`、`dist/baldr_previous_20261006`、`dist/baldr_failed_registry_20261006`、全部 `output/packaging/`、目前使用的 appdata、正式 snapshot、ML、私人資料與排程來源都排除。不 kill、不改 ACL/Task/refs，不 fit 或重跑產品 tests。

## 歷史絕對路徑影響與還原

歷史文件仍使用原絕對路徑，本輪不偽改舊證據。需要按舊文件重播、查 log 或使用舊還原腳本時，先依 manifest 把所需根還原。

1. 選擇 `state=moved_verified` 的單一 manifest 項目，確認原 source 尚不存在，沒有新的同名資料。
2. 確認 source/destination 的所有 ancestors 不是 junction/symlink，隔離 entries metadata 與 manifest 一致。若來源已存在或 metadata 不符，停止並保留兩邊。
3. 用 manifest 完整 literal path 搬回；一般根可用 `Move-Item -LiteralPath <destination> -Destination <source>`。包含引號與 `$` 的字面名稱須從 JSON 讀取 source/destination，不能拼接或執行 shell 字串，也不能擅自展開變數。禁止 overwrite/merge。
4. 還原後全量核對相對路徑、identity、size、mtime、link count、attributes，再重播歷史操作。

**若未來執行 ta_iso 二次移位：必須先把 `previous_isolation_ta_iso_1005` 還原為 `C:/ta_iso_1005`，再使用原 10/05 manifest／restore.ps1。** 原始 `output/qa/reversible_cleanup_20261005/` 的 moves/restore CSV、approval candidates、ROLLBACK、restore.ps1 不改寫；計畫另將逐檔核對過的副本放集中根 `recovery_evidence/`，目前尚未執行。這保存舊腳本的絕對路徑前提。

集中資料應繼續保留。未來永久清理需要另行確認，不能把「測試能重跑」當作「原證據 bytes 可以刪」。

## 相關清冊

- [資料資產登記](STORAGE_ASSET_REGISTER_20261006.md)
- 先前兩批已完成隔離：`C:/Projects/RepositoryBackups/technical_analysis_temp_quarantine_20261006`、`C:/Projects/RepositoryBackups/technical_analysis_croot_temp_quarantine_20261006`。兩份 manifest 包含先前 368 個根、5,439,427,167 logical bytes，與此批不同；不得重複計量。
- 原處仍保留 repo `.t`／`.tmp_wp5f` 的實際 junction（不追蹤 target）、`.tmp_fa_data_space_audit` 的 recovery 證據，以及 `tmp75b0x72o` 的來源待確認輸出。不是整批依名稱刪除。
