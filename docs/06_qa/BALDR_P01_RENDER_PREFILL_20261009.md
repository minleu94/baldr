# BALDR P01 純詞法 render 預填候選

## 狀態

實作與定向驗證已完成，待 root review。此文件記錄核准範圍、回滾方式與驗證證據；目前不宣稱效能改善已成立，也不代表完整 P01 矩陣通過。

## 問題與候選

P01 的 page operation 已先對路徑 leaf 執行 strict absolute-syntax validation，再逐項檢查其 component tuple。後續 leaf I/O 仍會對同一字面 leaf 再做一次純語法解析。候選把 strict guard 已驗證的 leaf `Path` 直接交給純 rendering helper，並將結果依原有 key 與預算放入 page render memo，供接續 I/O 重用。

此候選只重用純詞法 rendering。每個 component 仍重新組成、逐次通過既有 `lstat`、reparse/junction 與其他來源驗證；不快取檔案狀態、bytes、SHA、schema/DTO、授權或取消結果，不改選股、cutoff、資料讀取或金融計算。

## 範圍與不變條件

- 正式變更範圍限 `app_module/personal_data_paths.py` 與 `tests/test_p01_page_path_component_memo.py`；本 QA 文件是驗證紀錄。
- 僅精確內建 `Path` 子型、目前 owner thread、絕對且已通過 strict lexical validation 的路徑可預填；invalid、relative、Path subclass、closed memo、suspended scope 與 foreign thread 保持 strict fallback。
- 保留 4096 entries、1 MiB UTF-16 byte cap、達上限停止新增、不驅逐既有 entry、scope 結束清空與巢狀 scope 還原。
- Windows extended-path rendering 門檻與 UNC 行為不變。
- fresh `lstat`、reparse/junction、fresh read、SHA、取消 callback、selection 與 finance cutoff 守衛逐次執行，不移除、不跨讀取快取。

## 回滾

若任一定向測試、mypy、py_compile 或行為比對失敗，保留第一個紅測輸出與收據，停止後續驗證。回滾僅撤銷上述兩個正式檔案中本候選的 diff，還原到實作前的凍結版本；QA 文件與收據保留為歷史證據。不得重寫 benchmark store/runtime、F12 pins、其他 agent 變更或既有測試基線。

## 待驗項目

1. 既有 P01 memo 測試與新增機制測試：證明同 scope 下 components 後首次 leaf I/O 的 strict syntax/render 呼叫次數下降，輸出與 strict clone 完全一致。
2. memo 預算與生命週期：4096 entry、1 MiB、停止新增不驅逐、clear/exception、nested/suspended/foreign-thread、Path subclass、invalid/relative fallback。
3. guard 回歸：strict clone 與 page scope 的 fresh `lstat` 順序一致；selected 與 unselected、mtime restore/reparse、取消相關精確回歸保持原證據。
4. 執行指定測試集合、targeted mypy 與 py_compile，逐一保存原生 stdout/stderr、process exit code、命令、前後 SHA 與 log SHA。
5. 由 root 實讀 diff 與收據後，再決定是否核准更新 F12 pin 及後續完整矩陣；本候選階段不跑 producer、不跑矩陣、不 commit。

## 本輪驗證結果

- path memo 測試加上 page query regression 共 19 cases 通過，exit 0。涵蓋 strict clone fresh-I/O 事件、cancel callback scope、selected 與 unselected artifact 在 mtime restore 後重讀、Windows junction/reparse，以及 lone-surrogate tuple 與 renderer error 時點。
- 定向 mypy、source/test py_compile、`git diff --check` 均 exit 0。
- sandbox 內首次測試的 strict `realpath` fixture 存取遭拒，兩份 exit 1 原始輸出保留；相同測試以核准的 elevated process、workspace-local TEMP/TMP 重跑後通過。失敗只在 fixture root 權限，未進入來源讀取。
- 原始 pytest log 與逐項 command/exit/SHA 收據位於 `output/qa/p01_render_prefill_formal_20261009_a/`：`focused_regressions_01.log`、`focused_regressions_02.log`、`focused_regressions_03_escalated.log`、`focused_regressions_03_escalated_RECEIPT.md`、`targeted_mypy_02.log`、`py_compile_02.log`、`diff_check_02.log`、`static_checks_02_RECEIPT.md`。
- 驗證後正式 source SHA-256：`e5ba2dcb73cf1f34ce4f393fb8ab303f07fe19b9ede45ac5e29305a072f1692d`；path memo test SHA-256：`43071318ddd61c950376a419fe2bdabd875f53b45e7ed41a532ccf4552a9e851`。
- 完整 P01 矩陣、producer、store/runtime 操作、commit 與 F12 pin 更新均未執行，需待 root 實讀本候選 diff 與收據後另行核准。

